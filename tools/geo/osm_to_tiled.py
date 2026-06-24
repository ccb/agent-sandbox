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
    uv run python tools/geo/osm_to_tiled.py            # Penn campus, cached fetch
    uv run python tools/geo/osm_to_tiled.py --refresh  # re-download from Overpass

Data (c) OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import time
import urllib.parse
import urllib.request
import zlib

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

# Bounding box around the University of Pennsylvania campus (University City,
# Philadelphia). Order: south, west, north, east. This frame captures Locust
# Walk, College Green, the Quad, Van Pelt, the engineering quad and Franklin
# Field. See the campus on OSM: https://www.openstreetmap.org/relation/2594845
BBOX = dict(south=39.9475, west=-75.2025, north=39.9565, east=-75.1880)

# How many real-world metres one tile covers. Smaller = more detail + bigger map.
METRES_PER_TILE = 4.0

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "agent-sandbox-geo/0.1 (https://github.com/ccb/agent-sandbox issue#164)"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
CACHE_FILE = os.path.join(OUT_DIR, "upenn_osm.json")

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


def fetch_osm(bbox: dict, refresh: bool) -> dict:
    """Return Overpass JSON for the bbox, using the on-disk cache when possible."""
    if os.path.exists(CACHE_FILE) and not refresh:
        print(f"[fetch] using cached {os.path.relpath(CACHE_FILE)}")
        with open(CACHE_FILE) as fh:
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
    with open(CACHE_FILE, "w") as fh:
        fh.write(raw)
    print(f"[fetch] cached -> {os.path.relpath(CACHE_FILE)}")
    return parsed


# --------------------------------------------------------------------------- #
# 2. PROJECT  (lat/lon -> tile col/row)
# --------------------------------------------------------------------------- #


class Projector:
    """Local equirectangular projection: good enough for a ~1 km campus frame.

    Maps lon/lat to metres relative to the bbox, then to fractional tile
    coordinates with row 0 at the north edge (Tiled's top row).
    """

    def __init__(self, bbox: dict, metres_per_tile: float):
        self.bbox = bbox
        self.mpt = metres_per_tile
        lat0 = math.radians((bbox["south"] + bbox["north"]) / 2)
        self.m_per_deg_lat = 111_320.0
        self.m_per_deg_lon = 111_320.0 * math.cos(lat0)
        width_m = (bbox["east"] - bbox["west"]) * self.m_per_deg_lon
        height_m = (bbox["north"] - bbox["south"]) * self.m_per_deg_lat
        self.cols = max(1, math.ceil(width_m / metres_per_tile))
        self.rows = max(1, math.ceil(height_m / metres_per_tile))

    def to_tile(self, lat: float, lon: float) -> tuple[float, float]:
        x_m = (lon - self.bbox["west"]) * self.m_per_deg_lon
        y_m = (self.bbox["north"] - lat) * self.m_per_deg_lat  # north -> row 0
        return x_m / self.mpt, y_m / self.mpt


# --------------------------------------------------------------------------- #
# 3. RASTER  (features -> grids of tile GIDs)
# --------------------------------------------------------------------------- #


def new_grid(cols: int, rows: int, fill: int = 0) -> list:
    return [[fill] * cols for _ in range(rows)]


def fill_polygon(grid: list, gid: int, pts: list, cols: int, rows: int) -> None:
    """Scanline polygon fill. `pts` is a list of (col, row) floats."""
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


def rasterise(osm: dict, proj: Projector) -> dict:
    """Return a dict of named tile layers (each a 2D grid of GIDs)."""
    cols, rows = proj.cols, proj.rows

    # Bottom-to-top draw order. The base ground layer is fully filled; the rest
    # start empty (GID 0) and only paint where a feature lands.
    layers = {
        "ground": new_grid(cols, rows, PALETTE["ground"][0]),
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
        gid = PALETTE[category][0]
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


def write_tmj(
    path: str, proj: Projector, layers: dict, tileset_png: str, ts_w: int, ts_h: int
) -> None:
    """Write a Tiled (.tmj) orthogonal map with an embedded tileset.

    Layer data is a flat uncompressed GID array (not base64/zlib) so Phaser's
    `tilemapTiledJSON` loader can read it directly; the tileset is embedded
    (no external .tsx). Geo-referencing is stored in custom map properties so
    the map can be reproduced / round-tripped.
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
        ],
        "tilesets": [
            {
                "firstgid": 1,
                "name": "campus",
                "tilewidth": TILE_PX,
                "tileheight": TILE_PX,
                "tilecount": len(PALETTE),
                "columns": len(PALETTE),
                "margin": 0,
                "spacing": 0,
                "image": os.path.basename(tileset_png),
                "imagewidth": ts_w,
                "imageheight": ts_h,
            }
        ],
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
    path: str, layers: dict, cols: int, rows: int, scale: int = 3
) -> None:
    """Flatten all layers top-down into a single PNG so a human can eyeball it."""
    gid_to_rgba = {gid: col for (gid, col) in PALETTE.values()}
    order = ["ground", "landuse", "water", "paths", "roads", "buildings"]
    # Composite into a single GID per cell (topmost non-empty wins).
    flat = new_grid(cols, rows, PALETTE["ground"][0])
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-download from Overpass")
    ap.add_argument(
        "--mpt",
        type=float,
        default=METRES_PER_TILE,
        help="metres per tile (default %(default)s)",
    )
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    osm = fetch_osm(BBOX, args.refresh)
    proj = Projector(BBOX, args.mpt)
    print(f"[grid]  {proj.cols} x {proj.rows} tiles @ {args.mpt} m/tile")

    t0 = time.time()
    result = rasterise(osm, proj)
    print(f"[raster] done in {time.time() - t0:.1f}s")
    for cat, n in result["counts"].items():
        if n:
            print(f"         {cat:9s}: {n} features")

    tileset_path = os.path.join(OUT_DIR, "tileset.png")
    tmj_path = os.path.join(OUT_DIR, "upenn.tmj")
    preview_path = os.path.join(OUT_DIR, "upenn_preview.png")
    ts_w, ts_h = write_tileset_png(tileset_path)
    write_tmj(tmj_path, proj, result["layers"], tileset_path, ts_w, ts_h)
    write_preview_png(preview_path, result["layers"], proj.cols, proj.rows)

    print(f"[emit]  {os.path.relpath(tmj_path)}")
    print(f"[emit]  {os.path.relpath(tileset_path)}")
    print(f"[emit]  {os.path.relpath(preview_path)}")
    sample = ", ".join(sorted(set(result["named"]))[:12])
    print(f"[check] {len(set(result['named']))} named buildings, e.g.: {sample}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
