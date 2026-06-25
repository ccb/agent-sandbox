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
    # A small prototyping subset: 34th–36th St between Spruce & Walnut — the heart
    # of campus (College Green, College Hall, Van Pelt, the Locust Walk core). The
    # bbox below is a generous *fetch* window (pushed ~0.0005° past every street so
    # Overpass returns the full bounding streets plus a margin); `crop_to_streets`
    # then trims the OUTPUT grid back to exactly the rectangle those four street
    # centrelines bound, so nothing past the streets is drawn. (The Philadelphia
    # grid is rotated ~8°, so a lat/lon box can't hug the tilted streets by itself
    # — but the crop can, because after the rotation the streets are axis-aligned.)
    "core": {
        "stem": "upenn_core",
        "desc": "campus core: 34th–36th St, Spruce–Walnut",
        "bbox": dict(south=39.9502, west=-75.1953, north=39.9538, east=-75.19182),
        "crop_to_streets": dict(
            north="Walnut Street",
            south="Spruce Street",
            east="South 34th Street",
            west="South 36th Street",
        ),
        # Drawn at a fine 1 m/tile (the campus default is 4) so individual
        # features — multi-tile trees especially — have room to read as
        # themselves rather than as single coloured cells. With the area limited to
        # one block, the whole frame *is* the middle of campus. `--mpt` overrides.
        "mpt": 1.0,
    },
}

# Default metres one tile covers when an area doesn't pin its own (see AREAS["core"]
# above and the --mpt flag). Smaller = more detail + a bigger grid.
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
# Urban-theme variety. URBAN_TILES above gives every building/road/lawn the
# *same* tile, so the campus reads as one uniform block. These add per-feature
# variety on top, only for the "urban" theme. Values are 0-based indices into
# the Kenney sheet (a Tiled GID is index + firstgid, and firstgid is 1 here).
# --------------------------------------------------------------------------- #

# Clean red/orange brick "field" tiles (no cornice or edge trim). Each building
# footprint is filled with one, chosen deterministically — Penn is a red/brown
# brick campus, so a spread of brick tones reads right while breaking up the
# old "sea of identical red". (Also drops tile 18, whose tan eave-stripe was
# what made every roof look striped.)
ROOF_TILES = [72, 74, 75, 180, 182, 183]

# Lane markings, stamped down the centreline of *major* roads only (minor and
# service roads stay plain asphalt — that contrast is the road "variety"). The
# Kenney sheet has a horizontal dash and a vertical dash; we pick by segment
# orientation. DASH_H suits E–W roads, DASH_V suits N–S roads.
MAJOR_ROADS = {"motorway", "trunk", "primary", "secondary"}
DASH_H, DASH_V = 433, 462

# Trees, as MULTI-TILE stamps. A single 16px cell is far too small to read as a
# tree (it just looks like a green cell), and at the fine 1 m grid even a 1×2
# "lollipop" is a speck — so every tree is a multi-tile *stand* of foliage.
#
# The Kenney sheet has one coherent multi-tile tree: a 3×3 grove at rows 8–10,
# cols 19–21 (indices verified by eye against tilemap_packed.png; cols 22+ are
# characters). Crucially its 9 tiles are a tileable 3×3 patch — a top / interior /
# trunk-base row and a left-edge / interior / right-edge column — so we can stamp a
# canopy of *any* size from them: corners at the corners, edges along the edges,
# the interior tile repeated to fill. `make_stand(w, h)` does exactly that,
# anchored at the base-centre cell (the trunk row), canopy extending up + sideways.
# Entries are (col_offset, row_offset, 0-based sheet index); a Tiled GID is idx + 1.

# 3×3 grove tiles by role (0-based sheet indices).
_CANOPY_TOP = (235, 236, 237)  # canopy crown: left edge / interior / right edge
_CANOPY_MID = (262, 263, 264)  # canopy body
_CANOPY_BASE = (289, 290, 291)  # trunks + canopy underside


def make_stand(w: int, h: int) -> list:
    """A w×h leafy stand composed from the grove's edge/interior tiles.

    Tiles the 3×3 grove out to an arbitrary canopy: the top/base rows cap it, the
    middle row fills the height, and within each row the left/right tiles edge it
    while the centre tile fills the width. Anchored at the base-centre cell, so the
    trunks sit at the anchor row and the crown rises above it. Any size ≥ 2 reads
    as one continuous mass of foliage (3×3 reproduces the original grove exactly).
    """
    cx = w // 2
    cells = []
    for ry in range(h):
        row = _CANOPY_TOP if ry == 0 else _CANOPY_BASE if ry == h - 1 else _CANOPY_MID
        for rx in range(w):
            idx = row[0] if rx == 0 else row[2] if rx == w - 1 else row[1]
            cells.append((rx - cx, ry - (h - 1), idx))
    return cells


TREE_GROVE = make_stand(3, 3)  # the standard tree: a 3 m canopy, lines the walks
TREE_STAND = make_stand(5, 4)  # a fuller lawn tree (~5 m)
TREE_WOOD = make_stand(7, 5)  # a big stand for the open greens (College Green)

# Every tree-sprite index, for the preview legend (so previews show foliage green
# instead of undefined-GID black).
TREE_PREVIEW_IDS = set(_CANOPY_TOP) | set(_CANOPY_MID) | set(_CANOPY_BASE)

# Bottom-to-top paint order. "trees" only exists in the urban theme (rasterise
# adds that layer when variety is on); filtering by presence keeps placeholder
# maps at their original six layers, byte-for-byte identical.
LAYER_ORDER = ["ground", "landuse", "water", "paths", "roads", "buildings", "trees"]

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
      node["natural"="tree"]({b});
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


def _fit_centreline(points: list) -> tuple:
    """Least-squares centreline of a set of (x, y) points.

    Returns a point on the line and a unit direction — the principal axis of the
    points' covariance, which works for a street running in any direction
    (including the near-vertical ones a `y = m·x + b` fit would choke on).
    """
    n = len(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    sxx = sxy = syy = 0.0
    for x, y in points:
        dx, dy = x - cx, y - cy
        sxx += dx * dx
        sxy += dx * dy
        syy += dy * dy
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)
    return (cx, cy), (math.cos(theta), math.sin(theta))


def _line_intersection(a: tuple, b: tuple) -> tuple:
    """Where two lines — each a (point, direction) — cross, in the same space."""
    (px, py), (dx, dy) = a
    (qx, qy), (ex, ey) = b
    denom = dx * ey - dy * ex
    if abs(denom) < 1e-9:
        raise ValueError("street centrelines are parallel; no corner")
    t = ((qx - px) * ey - (qy - py) * ex) / denom
    return (px + t * dx, py + t * dy)


def crop_to_streets(proj: Projector, osm: dict, streets: dict) -> None:
    """Shrink `proj`'s grid to the block bounded by four named streets.

    `streets` maps north/south/east/west -> an OSM street name (e.g. "Walnut
    Street"). We fit each street's centreline in the projector's rotated-metre
    space — where the grid is axis-aligned, so the four streets form an upright
    rectangle — intersect them to get the block's corners, and reset the
    projector's origin + size to that rectangle.

    Both generators paint through `proj.to_tile` and clip to `proj.cols`/`.rows`,
    so once the projector is cropped, everything past the streets lands outside the
    grid and is simply dropped — the picture (osm_to_tiled) and the agent maze
    (osm_to_ville) stay aligned tile-for-tile, just tighter. The area's fetch bbox
    is deliberately a touch larger than the streets so each centreline has points
    on both sides to fit a line to.
    """
    want = set(streets.values())
    points: dict[str, list] = {name: [] for name in want}
    b = proj.bbox
    pad = 0.0008  # degrees; keep only street nodes within the fetch window + a hair
    for el in osm.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if el.get("type") != "way" or "highway" not in tags or name not in want:
            continue
        for nd in el.get("geometry", []):
            if (
                b["south"] - pad <= nd["lat"] <= b["north"] + pad
                and b["west"] - pad <= nd["lon"] <= b["east"] + pad
            ):
                points[name].append(proj._rotate(*proj._metres(nd["lat"], nd["lon"])))

    lines = {}
    for name in want:
        if len(points[name]) < 2:
            raise SystemExit(
                f"crop_to_streets: street {name!r} not found in the OSM data"
            )
        lines[name] = _fit_centreline(points[name])

    # Four corners = each N/S street crossed with each E/W street.
    corners = [
        _line_intersection(lines[streets[ew]], lines[streets[ns]])
        for ew in ("north", "south")
        for ns in ("east", "west")
    ]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    proj.min_x, proj.min_y = min(xs), min(ys)
    proj.cols = max(1, math.ceil((max(xs) - min(xs)) / proj.mpt))
    proj.rows = max(1, math.ceil((max(ys) - min(ys)) / proj.mpt))


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


def line_cells(p0: tuple, p1: tuple):
    """Yield the integer (col,row) cells along a segment's centreline.

    Same Bresenham walk as `draw_line`, but it just reports the centre cells
    instead of stamping a thick line — used to lay lane markings down the
    middle of a road.
    """
    x0, y0 = int(round(p0[0])), int(round(p0[1]))
    x1, y1 = int(round(p1[0])), int(round(p1[1]))
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        yield x0, y0
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


def roof_gid(el: dict, pts: list) -> int:
    """Pick a deterministic brick-roof GID for one building footprint.

    Keyed on the OSM way id so a building keeps the same colour every time the
    map is regenerated (a hash of the rounded centroid is the fallback for the
    rare way with no id). `+ 1` turns the 0-based sheet index into a Tiled GID.
    """
    key = el.get("id")
    if key is None:
        cx = int(round(sum(p[0] for p in pts) / len(pts)))
        cy = int(round(sum(p[1] for p in pts) / len(pts)))
        key = cx * 73856093 ^ cy * 19349663
    return ROOF_TILES[key % len(ROOF_TILES)] + 1


def _tree_hash(c: int, r: int) -> int:
    """A stable, well-mixed non-negative hash of a cell — drives every tree choice.

    Never random, so regenerating the map reproduces exactly the same trees. The
    avalanche mixing matters: a plain `c*A ^ r*B` leaves the low bit equal to
    (c + r) & 1, which correlates with the cell-selection patterns below (they all
    pick cells with even c+r) and would starve one tree size entirely.
    """
    mask = 0xFFFFFFFFFFFFFFFF
    h = ((c * 73856093) ^ (r * 19349663)) & mask
    h = ((h ^ (h >> 15)) * 0x2545F4914F6CDD1D) & mask
    h ^= h >> 13
    return h & 0x7FFFFFFF


def place_tree(trees: list, occupied, base_c: int, base_r: int, stamp: list) -> bool:
    """Stamp one multi-tile tree with its trunk at (base_c, base_r), canopy upward.

    Succeeds only if *every* cell of the stamp is in-bounds, unoccupied (no
    building / road / path / water under it) and not already part of another
    tree — so trees never overlap each other or sit on paving. Writes the tree
    and returns True on success; touches nothing and returns False otherwise.
    """
    rows, cols = len(trees), len(trees[0])
    cells = []
    for dc, dr, idx in stamp:
        c, r = base_c + dc, base_r + dr
        if not (0 <= c < cols and 0 <= r < rows):
            return False
        if occupied(c, r) or trees[r][c]:
            return False
        cells.append((c, r, idx + 1))
    for c, r, gid in cells:
        trees[r][c] = gid
    return True


def draw_dashes(grid: list, p0: tuple, p1: tuple, cols: int, rows: int) -> None:
    """Stamp a dashed centre line (every other cell) along one road segment."""
    horiz = abs(p1[0] - p0[0]) >= abs(p1[1] - p0[1])
    dash = (DASH_H if horiz else DASH_V) + 1
    for i, (c, r) in enumerate(line_cells(p0, p1)):
        if i % 2 == 0 and 0 <= c < cols and 0 <= r < rows:
            grid[r][c] = dash


def _plant(trees: list, occupied, base_c: int, base_r: int, stamps: list) -> bool:
    """Try each stamp at (base_c, base_r) in order; plant the first that fits."""
    for stamp in stamps:
        if place_tree(trees, occupied, base_c, base_r, stamp):
            return True
    return False


def _lawn_stamps(c: int, r: int) -> list:
    """Largest-first stamps for a lawn tree, with a deterministic size mix so the
    greens get a natural spread of big stands, medium trees and small groves."""
    h = _tree_hash(c, r) % 10
    if h < 3:
        return [TREE_WOOD, TREE_STAND, TREE_GROVE]  # ~30% big stands
    if h < 7:
        return [TREE_STAND, TREE_GROVE]  # ~40% medium
    return [TREE_GROVE]  # the rest: a single grove


def stamp_trees(layers: dict, osm: dict, proj: Projector) -> None:
    """Fill the "trees" layer with multi-tile trees (urban theme only).

    Every tree is a stand of foliage (never a lone speck), placed so it never
    overlaps a built, paved or watery cell — or another tree. Three deterministic
    sources:
      1. real trees mapped in OSM (natural=tree nodes), placed where they are;
      2. footway-lining — a grove set back beside the walks at intervals, so
         Locust Walk and the campus paths become tree-lined avenues;
      3. a scatter of mixed-size stands across the lawns (big stands on the greens).
    The grove is the smallest tree we place: where even a grove won't fit, we plant
    nothing rather than drop in a speck.
    """
    cols, rows = proj.cols, proj.rows
    trees = layers["trees"]

    def occupied(c: int, r: int) -> bool:
        return bool(
            layers["buildings"][r][c]
            or layers["water"][r][c]
            or layers["roads"][r][c]
            or layers["paths"][r][c]
        )

    # 1. Real OSM trees (nodes carry lat/lon directly, no geometry).
    for el in osm.get("elements", []):
        if el.get("type") != "node" or el.get("tags", {}).get("natural") != "tree":
            continue
        cf, rf = proj.to_tile(el["lat"], el["lon"])
        c, r = int(cf), int(rf)
        if 0 <= c < cols and 0 <= r < rows:
            _plant(trees, occupied, c, r, [TREE_STAND, TREE_GROVE])

    # 2. Line the footways: at intervals, set a grove back beside the walk. The
    #    offset clears the (now wider) path before reaching for grass, and the
    #    side-offset directions are tried in a per-cell order so trees fall on
    #    whichever side has room, naturally lining both sides of a path.
    spacing, offset = 6, 4
    for r in range(rows):
        for c in range(cols):
            if not layers["paths"][r][c] or (c + r) % spacing:
                continue
            dirs = [(offset, 0), (-offset, 0), (0, offset), (0, -offset)]
            if _tree_hash(c, r) & 1:
                dirs.reverse()
            for dc, dr in dirs:
                bc, br = c + dc, r + dr
                if _plant(trees, occupied, bc, br, [TREE_GROVE]):
                    break  # one tree per chosen path cell keeps the avenue tidy

    # 3. Scatter mixed-size stands across the lawns. A hash gate (not a fixed
    #    stride) gives an even, natural spread instead of trees marching down
    #    diagonal lines; the stand footprints + collisions thin it further.
    density = 14  # ~1 in N lawn cells attempts a tree
    for r in range(rows):
        for c in range(cols):
            if layers["landuse"][r][c] and _tree_hash(c, r) % density == 0:
                _plant(trees, occupied, c, r, _lawn_stamps(c, r))


def rasterise(osm: dict, proj: Projector, gid_of: dict, variety: bool = False) -> dict:
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
    if variety:  # urban-theme foliage, painted on top of everything else
        layers["trees"] = new_grid(cols, rows)
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
            if variety and category == "building":
                gid = roof_gid(el, pts)  # vary the roof colour per building
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
            if variety and category == "road" and tags.get("highway") in MAJOR_ROADS:
                for i in range(len(pts) - 1):  # lane markings on major roads
                    draw_dashes(grid, pts[i], pts[i + 1], cols, rows)

        counts[category] += 1
        if category == "building" and tags.get("name"):
            named.append(tags["name"])

    if variety:
        stamp_trees(layers, osm, proj)

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
    order = [name for name in LAYER_ORDER if name in layers]
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
    order = [name for name in LAYER_ORDER if name in layers]
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
    if area.get("crop_to_streets"):
        crop_to_streets(proj, osm, area["crop_to_streets"])
    print(
        f"[grid]  {proj.cols} x {proj.rows} tiles @ {mpt} m/tile, rotated {rotate_deg:+.2f}°"
    )

    t0 = time.time()
    result = rasterise(osm, proj, gid_of, variety=(theme == "urban"))
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
    if theme == "urban":
        # Map the per-feature variety tiles back to their category colour so the
        # layout preview stays legible (roofs read as buildings, dashes as road,
        # trees as green) instead of rendering as undefined black cells.
        for idx in ROOF_TILES:
            gid_to_rgba[idx + 1] = PALETTE["building"][1]
        gid_to_rgba[DASH_H + 1] = PALETTE["road"][1]
        gid_to_rgba[DASH_V + 1] = PALETTE["road"][1]
        for idx in TREE_PREVIEW_IDS:
            gid_to_rgba[idx + 1] = (60, 130, 60, 255)
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
        default=None,
        help="metres per tile (default: the area's own, else %d)" % METRES_PER_TILE,
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
        # Resolution: an explicit --mpt wins; otherwise the area's own (AREAS["core"]
        # pins 2 m/tile), otherwise the module default.
        mpt = (
            args.mpt
            if args.mpt is not None
            else AREAS[name].get("mpt", METRES_PER_TILE)
        )
        build_area(name, mpt, args.refresh, args.theme, args.rotate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
