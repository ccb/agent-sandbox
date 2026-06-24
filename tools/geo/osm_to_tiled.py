"""Turn real-world OpenStreetMap data into a Tiled tilemap (.tmj).

This is the proof-of-concept for issue #164: "import real-world map data
(GeoJSON / OSM) into Godot tiles". We target **Tiled** (.tmj) because that one
format feeds *both* renderers we care about:

    OSM/GeoJSON -> project + rasterize -> Tiled (.tmj) --+--> Phaser  (native loader)
                                                         +--> Godot 4 (YATI importer)

The pipeline, top to bottom:

  1. FETCH    pull vector features (buildings, roads, footways, water, parks)
              from the Overpass API for a lat/lon bounding box, and cache them.
  2. PROJECT  convert lat/lon -> meters (local equirectangular) -> tile (col,row).
  3. RASTER   "stamp" each feature onto a grid of tile layers: polygons get
              filled (scanline), lines get drawn (Bresenham, with a width).
  4. EMIT     write a Tiled .tmj map + an embedded tileset PNG, plus a quick
              preview PNG so a human can eyeball the result.

Zero third-party dependencies on purpose (only the Python stdlib, incl. zlib for
PNG) so it runs anywhere `uv run python` does, no extra installs.

Usage:
    uv run python tools/geo/osm_to_tiled.py                 # Penn campus, cached fetch
    uv run python tools/geo/osm_to_tiled.py --area core     # small prototyping subset
    uv run python tools/geo/osm_to_tiled.py --theme urban   # real Kenney CC0 tiles
    uv run python tools/geo/osm_to_tiled.py --refresh       # re-download from Overpass

Data (c) OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright).
Urban tiles (c) Kenney, CC0 (https://kenney.nl/assets/rpg-urban-pack).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import sys
import time
import urllib.parse
import urllib.request
import zlib

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

# Named areas to render. Each writes its own files (<stem>.tmj, <stem>_preview.png)
# and caches its own Overpass response (out/<stem>_osm.json), so areas never
# clobber each other. bbox order: south, west, north, east.
AREAS = {
    # The full UPenn campus (University City, Philadelphia): Locust Walk, College
    # Green, the Quad, Van Pelt, the engineering quad, Franklin Field.
    # OSM: https://www.openstreetmap.org/relation/2594845
    "campus": {
        "stem": "upenn",
        "desc": "full UPenn campus",
        "bbox": dict(south=39.9475, west=-75.2025, north=39.9565, east=-75.1880),
    },
    # A small prototyping subset: 34th–38th St between Spruce & Walnut — the heart
    # of campus (College Green, College Hall, Van Pelt, the Locust Walk core).
    # The bbox was derived from the real street-centreline geometry in the campus
    # OSM data (the Philadelphia grid is rotated ~8°, so this axis-aligned box is
    # the tight rectangle that still contains all four bounding streets).
    "core": {
        "stem": "upenn_core",
        "desc": "campus core: 34th–38th St, Spruce–Walnut",
        "bbox": dict(south=39.9502, west=-75.1994, north=39.9538, east=-75.19182),
    },
}

# How many real-world metres one tile covers. Smaller = more detail + bigger map.
METRES_PER_TILE = 4.0

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "agent-sandbox-geo/0.1 (https://github.com/ccb/agent-sandbox issue#164)"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")

# --------------------------------------------------------------------------- #
# Tile palette. Each category is one solid-colour tile in the generated
# tileset. GID 0 is reserved by Tiled to mean "empty cell".
# --------------------------------------------------------------------------- #

# name -> (gid, RGBA colour). Order also defines the tileset image column order.
PALETTE = {
    "ground": (1, (216, 211, 188, 255)),  # base tan/ground under everything
    "grass": (2, (150, 196, 124, 255)),  # parks, grass, recreation, wood
    "water": (3, (122, 174, 215, 255)),  # rivers, ponds
    "path": (4, (232, 219, 168, 255)),  # footways / pedestrian (Locust Walk!)
    "road": (5, (140, 140, 140, 255)),  # vehicle roads
    "building": (6, (192, 120, 78, 255)),  # building footprints
}
TILE_PX = 16  # pixels per tile in the tileset image

# --------------------------------------------------------------------------- #
# Themes — how the six categories map onto a tileset.
#
# "placeholder" (default): the six solid-colour tiles from write_tileset_png,
#   GIDs 1-6. Tiny, self-contained, good for a quick look.
# "urban": real CC0 art from Kenney's RPG Urban Pack. We reference the pack's
#   packed tilesheet (27 tiles wide, no spacing) as-is and point each category
#   at a chosen tile. Tile indices are into that sheet (index = row*27 + col);
#   a Tiled GID is the index + firstgid(1). Picked by eye from the sheet.
# --------------------------------------------------------------------------- #

ASSETS_DIR = os.path.join(HERE, "assets")
URBAN_SHEET = "tilemap_packed.png"  # Kenney RPG Urban Pack, CC0 (see assets/kenney)
URBAN_TILES = {
    "ground": 38,  # light-grey concrete (the base surface)
    "grass": 6,  # green lawn / parks
    "water": 61,  # water
    "path": 87,  # tan paving — pedestrian ways (Locust Walk)
    "road": 461,  # dark asphalt — vehicle roads
    "building": 18,  # red brick — building footprints
}

# --------------------------------------------------------------------------- #
# 1. FETCH
# --------------------------------------------------------------------------- #


def overpass_query(bbox: dict) -> str:
    """Overpass QL asking for the feature classes we render, with inline geometry."""
    b = f"{bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']}"
    return f"""
    [out:json][timeout:90];
    (
      way["building"]({b});
      way["highway"]({b});
      way["natural"="water"]({b});
      way["waterway"]({b});
      way["leisure"]({b});
      way["landuse"]({b});
      way["natural"="wood"]({b});
    );
    out geom;
    """


def fetch_osm(bbox: dict, cache_file: str, refresh: bool) -> dict:
    """Return Overpass JSON for the bbox, using the on-disk cache when possible."""
    if os.path.exists(cache_file) and not refresh:
        print(f"[fetch] using cached {os.path.relpath(cache_file)}")
        with open(cache_file) as fh:
            return json.load(fh)

    print("[fetch] querying Overpass API (real OpenStreetMap data)...")
    body = urllib.parse.urlencode({"data": overpass_query(bbox)}).encode()
    req = urllib.request.Request(
        OVERPASS_URL, data=body, headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
    parsed = json.loads(raw)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(cache_file, "w") as fh:
        fh.write(raw)
    print(f"[fetch] cached -> {os.path.relpath(cache_file)}")
    return parsed


# --------------------------------------------------------------------------- #
# 2. PROJECT  (lat/lon -> tile col/row)
# --------------------------------------------------------------------------- #


def dominant_grid_angle(osm: dict, m_per_deg_lon: float, m_per_deg_lat: float) -> float:
    """How far the street grid is rotated off the axes, in degrees (-45, 45].

    A planned city's streets share two perpendicular families (here the
    Philadelphia grid, ~8° off true E–W / N–S). To make those run straight
    along Godot's X/Y axes instead of on a slant, we first need that angle.

    Method: take a length-weighted *circular mean* of 4×(each road segment's
    angle). Quadrupling folds the two perpendicular families (θ and θ+90°) onto
    the same direction so they reinforce instead of cancelling; dividing the
    mean back by 4 returns the grid's offset from the axes.
    """
    sx = sy = 0.0
    for el in osm.get("elements", []):
        if el.get("type") != "way" or "highway" not in el.get("tags", {}):
            continue
        geom = el.get("geometry", [])
        for a, b in zip(geom, geom[1:]):
            dx = (b["lon"] - a["lon"]) * m_per_deg_lon  # east
            dy = (a["lat"] - b["lat"]) * m_per_deg_lat  # south (screen-down)
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue
            ang = math.atan2(dy, dx)
            sx += length * math.cos(4 * ang)
            sy += length * math.sin(4 * ang)
    if sx == 0.0 and sy == 0.0:
        return 0.0
    return math.degrees(math.atan2(sy, sx)) / 4.0


class Projector:
    """Local equirectangular projection: good enough for a ~1 km campus frame.

    Maps lon/lat to metres relative to the bbox centre, optionally rotates the
    whole plane by `rotate_deg` (so a tilted street grid lands axis-aligned),
    then converts to fractional tile coordinates with row 0 at the top.
    """

    def __init__(self, bbox: dict, metres_per_tile: float, rotate_deg: float = 0.0):
        self.bbox = bbox
        self.mpt = metres_per_tile
        self.rotate_deg = rotate_deg
        self.lat0 = (bbox["south"] + bbox["north"]) / 2
        self.lon0 = (bbox["west"] + bbox["east"]) / 2
        self.m_per_deg_lat = 111_320.0
        self.m_per_deg_lon = 111_320.0 * math.cos(math.radians(self.lat0))
        phi = math.radians(rotate_deg)
        self._cos, self._sin = math.cos(phi), math.sin(phi)
        # Rotating tilts the bbox, so the axis-aligned grid that still contains
        # all of it is the bounding box of the four rotated corners. (The empty
        # corners this leaves just stay GID 0 / unpainted.)
        xs, ys = [], []
        for lat in (bbox["south"], bbox["north"]):
            for lon in (bbox["west"], bbox["east"]):
                x, y = self._rotate(*self._metres(lat, lon))
                xs.append(x)
                ys.append(y)
        self.min_x, self.min_y = min(xs), min(ys)
        self.cols = max(1, math.ceil((max(xs) - self.min_x) / metres_per_tile))
        self.rows = max(1, math.ceil((max(ys) - self.min_y) / metres_per_tile))

    def _metres(self, lat: float, lon: float) -> tuple[float, float]:
        return (
            (lon - self.lon0) * self.m_per_deg_lon,  # east
            (self.lat0 - lat) * self.m_per_deg_lat,  # south (screen-down)
        )

    def _rotate(self, x: float, y: float) -> tuple[float, float]:
        return (x * self._cos - y * self._sin, x * self._sin + y * self._cos)

    def to_tile(self, lat: float, lon: float) -> tuple[float, float]:
        x, y = self._rotate(*self._metres(lat, lon))
        return (x - self.min_x) / self.mpt, (y - self.min_y) / self.mpt


# --------------------------------------------------------------------------- #
# 3. RASTER  (features -> grids of tile GIDs)
# --------------------------------------------------------------------------- #


def new_grid(cols: int, rows: int, fill: int = 0) -> list:
    return [[fill] * cols for _ in range(rows)]


def polygon_cells(pts: list, cols: int, rows: int):
    """Yield (col, row) cells whose centre lies inside the polygon (scanline).

    Shared by `fill_polygon` (which paints them) and the Smallville matrix
    emitter (`osm_to_ville.py`, which needs each building's footprint cells).
    """
    if len(pts) < 3:
        return
    ys = [p[1] for p in pts]
    row_lo = max(0, int(math.floor(min(ys))))
    row_hi = min(rows - 1, int(math.ceil(max(ys))))
    n = len(pts)
    for row in range(row_lo, row_hi + 1):
        yc = row + 0.5  # sample at the tile centre
        xs = []
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            if (y1 <= yc < y2) or (y2 <= yc < y1):
                t = (yc - y1) / (y2 - y1)
                xs.append(x1 + t * (x2 - x1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            c_lo = max(0, int(math.ceil(xs[i] - 0.5)))
            c_hi = min(cols - 1, int(math.floor(xs[i + 1] - 0.5)))
            for c in range(c_lo, c_hi + 1):
                yield c, row


def fill_polygon(grid: list, gid: int, pts: list, cols: int, rows: int) -> None:
    """Scanline polygon fill. `pts` is a list of (col, row) floats."""
    for c, row in polygon_cells(pts, cols, rows):
        grid[row][c] = gid


def stamp(
    grid: list, gid: int, c: int, r: int, radius: int, cols: int, rows: int
) -> None:
    """Set cell (c,r) and a square of given radius around it (line thickness)."""
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols:
                grid[rr][cc] = gid


def draw_line(
    grid: list, gid: int, p0: tuple, p1: tuple, radius: int, cols: int, rows: int
) -> None:
    """Bresenham line between two (col,row) float points, thickened by `radius`."""
    x0, y0 = int(round(p0[0])), int(round(p0[1]))
    x1, y1 = int(round(p1[0])), int(round(p1[1]))
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        stamp(grid, gid, x0, y0, radius, cols, rows)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


# How wide (in extra tiles each side) to draw each road class.
ROAD_RADIUS = {
    "motorway": 2,
    "trunk": 2,
    "primary": 2,
    "secondary": 1,
    "tertiary": 1,
    "residential": 1,
    "unclassified": 1,
    "service": 0,
    "living_street": 0,
}
# Pedestrian ways — Locust Walk & co. Drawn a touch wide so they read as the
# campus spine rather than a hairline.
PATH_TYPES = {"footway", "path", "pedestrian", "steps", "cycleway", "track"}


def is_closed(way: dict) -> bool:
    g = way.get("geometry", [])
    return len(g) > 3 and g[0] == g[-1]


def categorise(tags: dict) -> tuple[str, str] | None:
    """Map OSM tags to (category, geometry_kind). geometry_kind in {area,line}."""
    if "building" in tags:
        return "building", "area"
    if tags.get("natural") == "water" or "waterway" in tags:
        kind = "area" if tags.get("natural") == "water" else "line"
        return "water", kind
    if "highway" in tags:
        hw = tags["highway"]
        if hw in PATH_TYPES:
            return "path", "line"
        return "road", "line"
    if tags.get("natural") == "wood":
        return "grass", "area"
    if "leisure" in tags and tags["leisure"] in {
        "park",
        "garden",
        "pitch",
        "recreation_ground",
        "playground",
        "common",
    }:
        return "grass", "area"
    if "landuse" in tags and tags["landuse"] in {
        "grass",
        "recreation_ground",
        "forest",
        "meadow",
        "village_green",
    }:
        return "grass", "area"
    return None


def rasterise(osm: dict, proj: Projector, gid_of: dict) -> dict:
    """Return a dict of named tile layers (each a 2D grid of GIDs).

    `gid_of` maps each category (ground/grass/water/path/road/building) to the
    Tiled GID that draws it — which tileset/theme that GID points at is the
    caller's concern.
    """
    cols, rows = proj.cols, proj.rows

    # Bottom-to-top draw order. The base ground layer is fully filled; the rest
    # start empty (GID 0) and only paint where a feature lands.
    layers = {
        "ground": new_grid(cols, rows, gid_of["ground"]),
        "landuse": new_grid(cols, rows),
        "water": new_grid(cols, rows),
        "paths": new_grid(cols, rows),
        "roads": new_grid(cols, rows),
        "buildings": new_grid(cols, rows),
    }
    # Which physical layer each category paints into.
    layer_of = {
        "grass": "landuse",
        "water": "water",
        "path": "paths",
        "road": "roads",
        "building": "buildings",
    }

    counts = {k: 0 for k in PALETTE}
    named = []

    for el in osm.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        cat = categorise(tags)
        if cat is None:
            continue
        category, kind = cat
        gid = gid_of[category]
        grid = layers[layer_of[category]]
        pts = [proj.to_tile(nd["lat"], nd["lon"]) for nd in el["geometry"]]

        if kind == "area" and (
            is_closed(el) or category in ("building", "grass", "water")
        ):
            fill_polygon(grid, gid, pts, cols, rows)
        else:
            radius = 0
            if category == "road":
                radius = ROAD_RADIUS.get(tags.get("highway", ""), 1)
            elif category == "path":
                radius = 1
            elif category == "water":  # waterway line (river/stream)
                radius = 2
            for i in range(len(pts) - 1):
                draw_line(grid, gid, pts[i], pts[i + 1], radius, cols, rows)

        counts[category] += 1
        if category == "building" and tags.get("name"):
            named.append(tags["name"])

    return {"layers": layers, "counts": counts, "named": named}


# --------------------------------------------------------------------------- #
# 4. EMIT  (tileset PNG + Tiled .tmj + preview PNG)
# --------------------------------------------------------------------------- #


def _png(width: int, height: int, rgba_rows: list) -> bytes:
    """Encode RGBA pixel rows (list of bytearrays) into PNG bytes (stdlib only)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for row in rgba_rows:
        raw.append(0)  # filter type 0 (none) for this scanline
        raw.extend(row)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        sig
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def _png_size(path: str) -> tuple[int, int]:
    """Read a PNG's pixel dimensions from its IHDR header (no full decode)."""
    with open(path, "rb") as fh:
        head = fh.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    return struct.unpack(">II", head[16:24])


def write_tileset_png(path: str) -> tuple[int, int]:
    """One solid-colour TILE_PX square per palette entry, laid out in a row."""
    # palette values are (gid, colour); order the colours by gid for the strip
    colours = [v[1] for v in sorted(PALETTE.values(), key=lambda v: v[0])]
    w, h = TILE_PX * len(colours), TILE_PX
    one_row = bytearray()
    for col in colours:
        one_row.extend(bytes(col) * TILE_PX)
    rows = [bytes(one_row)] * h  # every scanline of the strip is identical
    with open(path, "wb") as fh:
        fh.write(_png(w, h, rows))
    return w, h


def write_tmj(path: str, proj: Projector, layers: dict, tileset: dict) -> None:
    """Write a Tiled (.tmj) orthogonal map with the given (embedded) tileset.

    Layer data is a flat uncompressed GID array (not base64/zlib) so Phaser's
    `tilemapTiledJSON` loader can read it directly; the tileset image is
    referenced by basename (sits next to the .tmj). Geo-referencing is stored in
    custom map properties so the map can be reproduced / round-tripped.
    """
    cols, rows = proj.cols, proj.rows
    order = ["ground", "landuse", "water", "paths", "roads", "buildings"]
    tmj = {
        "type": "map",
        "version": "1.10",
        "tiledversion": "1.10.2",
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "infinite": False,
        "width": cols,
        "height": rows,
        "tilewidth": TILE_PX,
        "tileheight": TILE_PX,
        "nextlayerid": len(order) + 1,
        "nextobjectid": 1,
        "properties": [
            {
                "name": "source",
                "type": "string",
                "value": "OpenStreetMap via Overpass (ODbL)",
            },
            {"name": "bbox", "type": "string", "value": json.dumps(proj.bbox)},
            {"name": "metres_per_tile", "type": "float", "value": proj.mpt},
            {"name": "rotation_deg", "type": "float", "value": proj.rotate_deg},
        ],
        "tilesets": [tileset],
        "layers": [
            {
                "type": "tilelayer",
                "id": i + 1,
                "name": name,
                "width": cols,
                "height": rows,
                "x": 0,
                "y": 0,
                "opacity": 1,
                "visible": True,
                "data": [gid for r in layers[name] for gid in r],
            }
            for i, name in enumerate(order)
        ],
    }
    with open(path, "w") as fh:
        json.dump(tmj, fh)


def write_preview_png(
    path: str,
    layers: dict,
    cols: int,
    rows: int,
    gid_to_rgba: dict,
    base_gid: int,
    scale: int = 3,
) -> None:
    """Flatten all layers top-down into a single PNG so a human can eyeball it.

    The preview always uses the placeholder category colours (a cheap legend),
    regardless of the real theme — it's a layout sanity-check, not the art.
    """
    order = ["ground", "landuse", "water", "paths", "roads", "buildings"]
    # Composite into a single GID per cell (topmost non-empty wins).
    flat = new_grid(cols, rows, base_gid)
    for name in order:
        g = layers[name]
        for r in range(rows):
            gr = g[r]
            fr = flat[r]
            for c in range(cols):
                if gr[c]:
                    fr[c] = gr[c]
    png_rows = []
    for r in range(rows):
        base = bytearray()
        for c in range(cols):
            col = gid_to_rgba.get(flat[r][c], (0, 0, 0, 255))
            base.extend(bytes(col) * scale)
        for _ in range(scale):
            png_rows.append(bytes(base))
    with open(path, "wb") as fh:
        fh.write(_png(cols * scale, rows * scale, png_rows))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def _placeholder_tileset() -> dict:
    """Build the 6-colour strip PNG and the Tiled tileset block that references it."""
    tileset_path = os.path.join(OUT_DIR, "tileset.png")
    w, h = write_tileset_png(tileset_path)
    return {
        "firstgid": 1,
        "name": "campus",
        "tilewidth": TILE_PX,
        "tileheight": TILE_PX,
        "tilecount": len(PALETTE),
        "columns": len(PALETTE),
        "margin": 0,
        "spacing": 0,
        "image": "tileset.png",
        "imagewidth": w,
        "imageheight": h,
    }


def _urban_tileset() -> dict:
    """Copy Kenney's packed sheet next to the map and reference it whole."""
    src = os.path.join(ASSETS_DIR, "kenney", URBAN_SHEET)
    if not os.path.exists(src):
        raise SystemExit(
            f"urban theme needs {os.path.relpath(src)} — see assets/kenney/README"
        )
    dst = os.path.join(OUT_DIR, URBAN_SHEET)
    shutil.copyfile(src, dst)
    w, h = _png_size(dst)
    cols = w // TILE_PX
    return {
        "firstgid": 1,
        "name": "kenney_urban",
        "tilewidth": TILE_PX,
        "tileheight": TILE_PX,
        "tilecount": cols * (h // TILE_PX),
        "columns": cols,
        "margin": 0,
        "spacing": 0,
        "image": URBAN_SHEET,
        "imagewidth": w,
        "imageheight": h,
    }


def resolve_rotation(rotate: str, osm: dict, bbox: dict) -> float:
    """Turn the --rotate option into a concrete degrees-to-rotate value.

    `auto` spins the map so its street grid lands axis-aligned (rotate by the
    negative of the detected grid offset); `none` leaves north up; a number
    rotates by exactly that many degrees.
    """
    if rotate == "none":
        return 0.0
    if rotate == "auto":
        lat0 = (bbox["south"] + bbox["north"]) / 2
        m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
        return -dominant_grid_angle(osm, m_per_deg_lon, 111_320.0)
    return float(rotate)


def build_area(name: str, mpt: float, refresh: bool, theme: str, rotate: str) -> None:
    """Fetch, rasterize and emit the Tiled map for one named area in AREAS."""
    area = AREAS[name]
    stem, bbox = area["stem"], area["bbox"]
    print(f"\n=== {name}: {area['desc']}  [{theme}] ===")

    # Each category's GID depends on the theme (which tileset it points into).
    if theme == "urban":
        gid_of = {cat: idx + 1 for cat, idx in URBAN_TILES.items()}
    else:
        gid_of = {cat: PALETTE[cat][0] for cat in PALETTE}

    osm = fetch_osm(bbox, os.path.join(OUT_DIR, f"{stem}_osm.json"), refresh)
    rotate_deg = resolve_rotation(rotate, osm, bbox)
    proj = Projector(bbox, mpt, rotate_deg)
    print(
        f"[grid]  {proj.cols} x {proj.rows} tiles @ {mpt} m/tile, rotated {rotate_deg:+.2f}°"
    )

    t0 = time.time()
    result = rasterise(osm, proj, gid_of)
    print(f"[raster] done in {time.time() - t0:.1f}s")
    for cat, n in result["counts"].items():
        if n:
            print(f"         {cat:9s}: {n} features")

    tileset = _urban_tileset() if theme == "urban" else _placeholder_tileset()
    out_stem = stem if theme == "placeholder" else f"{stem}_{theme}"
    tmj_path = os.path.join(OUT_DIR, f"{out_stem}.tmj")
    preview_path = os.path.join(OUT_DIR, f"{out_stem}_preview.png")

    write_tmj(tmj_path, proj, result["layers"], tileset)
    # Preview uses the placeholder colours as a legend, keyed by this theme's GIDs.
    gid_to_rgba = {gid_of[cat]: PALETTE[cat][1] for cat in PALETTE}
    write_preview_png(
        preview_path,
        result["layers"],
        proj.cols,
        proj.rows,
        gid_to_rgba,
        gid_of["ground"],
    )

    print(f"[emit]  {os.path.relpath(tmj_path)}")
    print(f"[emit]  {os.path.relpath(preview_path)}")
    sample = ", ".join(sorted(set(result["named"]))[:12])
    print(f"[check] {len(set(result['named']))} named buildings, e.g.: {sample}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--area",
        choices=[*AREAS, "all"],
        default="campus",
        help="which area to build (default %(default)s)",
    )
    ap.add_argument(
        "--theme",
        choices=["placeholder", "urban"],
        default="placeholder",
        help="tile art: solid-colour placeholders or Kenney RPG Urban (CC0)",
    )
    ap.add_argument("--refresh", action="store_true", help="re-download from Overpass")
    ap.add_argument(
        "--mpt",
        type=float,
        default=METRES_PER_TILE,
        help="metres per tile (default %(default)s)",
    )
    ap.add_argument(
        "--rotate",
        default="auto",
        help="'auto' (axis-align the street grid, default), 'none', or degrees",
    )
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    names = list(AREAS) if args.area == "all" else [args.area]
    for name in names:
        build_area(name, args.mpt, args.refresh, args.theme, args.rotate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
