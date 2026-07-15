#!/usr/bin/env python3
"""Furnish a building's interior as a top-down cutaway on the campus tilemap.

This is a *post-process* for the baked Tiled map (``osm_to_tiled.py --theme
urban`` produces ``upenn_core_urban.tmj``; this script then "opens the roof" of
one building and paints a furnished floor plan in its place). It is read by the
generic renderer ``godot-generative-agents/scripts/tiled_map.gd`` with **no code
changes** — we simply add two interior tilesets and two interior tile layers to
the ``.tmj``.

Run order (documented in the PR too):

    uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --area core --theme urban   # bake map
    uv run python godot-generative-agents/tools/geo/furnish_building.py                          # furnish
    # commit the updated .tmj

The script is **idempotent**: it strips any interior tilesets / ``williams_*``
layers it previously added before re-applying, so it is safe to re-run and safe
to run again after a fresh ``osm_to_tiled.py`` bake.

How it works (kept deliberately simple/readable — see CLAUDE.md):

1. Find the target building's footprint from the sim matrix CSVs. A building is a
   "sector"; its roof is every tile that is both in that sector AND solid in the
   collision maze (this excludes the 1-tile walkable apron around it). The matrix
   grid (237x271) is the SAME grid as the urban .tmj, so sector tiles map 1:1 to
   map cells.
2. "Open the roof": zero those cells on the ``buildings`` and ``trees`` layers so
   the interior shows through.
3. Paint two new layers over the footprint:
      - ``williams_floor``      floors + walls + windows  (the shell)
      - ``williams_furniture``  desks, blackboards, shelves, plants, fixtures
   Two layers because one TileMapLayer holds a single tile per cell, so furniture
   has to stack ABOVE the floor.
4. Rooms are rectangles placed inside the solid parts of the footprint; the
   leftover (irregular) space is left as open floor = lobby/corridor. Every write
   is clipped to the real footprint so nothing spills onto the street.
"""

from __future__ import annotations

import argparse
import json
import os

# --------------------------------------------------------------------------- #
# Tileset wiring. Each interior sheet becomes one Tiled tileset appended to the
# .tmj. GIDs are assigned right after the map's existing tilesets (kenney_urban
# 1..486, lawn_edges 487..518 -> first free is 519).
# --------------------------------------------------------------------------- #
FIRST_GID = 519
SHEETS = [
    # name, image file (next to the .tmj), columns, rows
    ("interior_franuka", "interior_franuka.png", 32, 32),  # main furniture sheet
    ("interior_school", "interior_school.png", 16, 16),  # desks / blackboards
    ("interior_bath", "interior_bath.png", 16, 16),  # toilets / sinks
]
# Franuka expansion sheets (each 32x32) appended later. Their firstgids are
# PINNED above decor_plants (which ends at gid 2138) so they never collide, and
# spaced 1024 apart so each sheet owns a clean block.
EXPANSION_SHEETS = [
    # name, image file, cols, rows, pinned firstgid
    ("interior_alchemy", "interior_alchemy.png", 32, 32, 3000),
    ("interior_bedroom", "interior_bedroom.png", 32, 32, 4024),
    ("interior_clockwork", "interior_clockwork.png", 32, 32, 5048),
    ("interior_music", "interior_music.png", 32, 32, 6072),
]

# Resolve each sheet's firstgid + column count.
_FIRST, _COLS = {}, {}
_g = FIRST_GID
for name, _image, cols, rows in SHEETS:
    _FIRST[name] = _g
    _COLS[name] = cols
    _g += cols * rows
for name, _image, cols, rows, firstgid in EXPANSION_SHEETS:
    _FIRST[name] = firstgid
    _COLS[name] = cols
# every appended interior sheet as (name, image, cols, rows), for tileset insertion
_ALL_SHEETS = SHEETS + [(n, i, c, r) for (n, i, c, r, _fg) in EXPANSION_SHEETS]


def gid(sheet: str, col: int, row: int) -> int:
    """Tiled GID for tile (col,row) of an interior sheet."""
    return _FIRST[sheet] + row * _COLS[sheet] + col


# --------------------------------------------------------------------------- #
# Tile palette — sourced from furniture_catalog.json, the single "what tile is
# what" table (see that file's _README and preview_catalog.py to verify a tile).
# An LLM furnishing a building edits the catalog and references objects by name
# via block_named()/tile_named(); the constants below are just the named lookups
# the room-filling code already uses, so behaviour is unchanged.
# --------------------------------------------------------------------------- #
F, S, B = "interior_franuka", "interior_school", "interior_bath"
A = "interior_alchemy"
_SHEET_ALIAS = {
    "franuka": F,
    "school": S,
    "bath": B,
    "kenney": "kenney_urban",
    "alchemy": A,
    "bedroom": "interior_bedroom",
    "clockwork": "interior_clockwork",
    "music": "interior_music",
}

# The base Kenney tileset is already in every map at firstgid 1 (27 cols), so
# catalog entries on the "kenney" sheet (street lamps, signs, trees) resolve to
# real gids too — no extra tileset is appended for them.
_FIRST["kenney_urban"] = 1
_COLS["kenney_urban"] = 27


def block(sheet, c0, r0, w, h):
    """A furniture block: a (col,row) grid of tiles, top-left anchored. None in a
    cell means "leave empty". This is the shape stamp() places on the layer."""
    return [[(sheet, c0 + c, r0 + r) for c in range(w)] for r in range(h)]


def _load_catalog():
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "furniture_catalog.json"
    )
    with open(path) as fh:
        objs = json.load(fh)["objects"]
    # Keys beginning "_" are human-readable section comments, not tile entries.
    return {k: v for k, v in objs.items() if not k.startswith("_")}


CATALOG = _load_catalog()


def block_named(name):
    """Furniture block for a catalog object name, ready for stamp(). This is the
    seam an LLM uses: pick any name from furniture_catalog.json and place it."""
    o = CATALOG[name]
    return block(_SHEET_ALIAS[o["sheet"]], o["col"], o["row"], o["w"], o["h"])


def tile_named(name):
    """Single GID for a catalog object — for the shell tiles (floor/wall/window)
    that are painted one cell at a time rather than stamped as a block."""
    o = CATALOG[name]
    return gid(_SHEET_ALIAS[o["sheet"]], o["col"], o["row"])


# Shell (single tiles, on the floor layer)
FLOOR = tile_named("floor_wood_light")
WALL = tile_named("wall_brick")
WINDOW = tile_named("window")  # drawn over a wall on the furniture layer

# Named furniture the room-filling code below places.
DESK = block_named("student_desk")  # student desk + chair (1x2)
TEACHER_DESK = block_named("teacher_desk")  # long desk w/ papers + red book (2x2)
BLACKBOARD = block_named("blackboard")  # decorated blackboard (3x2)
BLACKBOARD_BLANK = block_named("blackboard_blank")  # plain blackboard (3x2)
BOOKSHELF = block_named("bookshelf")  # tall bookshelf with books (1x2)
PLANT = block_named("plant")  # potted plant
OFFICE_CHAIR = block_named("armchair")  # single armchair
SOFA = block_named("sofa")  # long padded bench / sofa (3x2)
SIDE_TABLE = block_named("side_table")  # small table / bench
RUG = block_named("rug_blue")  # blue 3x3 rug (corners+edges+centre)
TOILET = block_named("toilet")  # toilet (1x2)
SINK = block_named("sink")  # vanity sink (1x2)
BATHMAT = block_named("bathmat")  # round bath mat


# --------------------------------------------------------------------------- #
# Room plan. Rectangles are (x0, y0, x1, y1) INCLUSIVE and include the room's own
# walls; they sit inside the solid parts of Williams Hall's footprint (verified
# against the footprint ASCII). "door" = (side, n) carves an n-wide gap in that
# wall onto the adjacent open floor. Anything not in a room stays open floor.
# --------------------------------------------------------------------------- #
ROOMS = [
    dict(
        name="Classroom A",
        kind="classroom",
        rect=(9, 224, 20, 239),
        door=("bottom", 2),
        board=BLACKBOARD,
    ),
    dict(
        name="Classroom B",
        kind="classroom",
        rect=(48, 228, 64, 238),
        door=("bottom", 2),
        board=BLACKBOARD_BLANK,
    ),
    dict(name="Office", kind="office", rect=(10, 243, 24, 253), door=("top", 2)),
    dict(name="Restroom", kind="restroom", rect=(27, 245, 38, 253), door=("top", 2)),
    dict(
        name="Classroom C",
        kind="classroom",
        rect=(52, 243, 64, 253),
        door=("top", 2),
        board=BLACKBOARD,
    ),
]
# The irregular central space (between the wings and above the south wall) is
# left open as a lobby/atrium and dressed with seating clusters + plants. Anchors
# are open-floor tiles; anything that would land on a wall/door is skipped.
SEATING_CLUSTERS = [(33, 235), (43, 246)]  # (centre x, centre y) of a rug
RECEPTION = (40, 251)  # info desk just inside the entrance
ATRIUM_PLANTS = [
    (25, 233),
    (44, 233),
    (30, 240),
    (49, 241),
    (26, 251),
    (50, 251),
    (39, 240),
    (39, 248),
]
# Main entrance: a gap in the south perimeter wall, near the lobby. This is the
# CANONICAL Williams south-door column pair -- add_entrances.WILLIAMS_DOOR_X
# aliases it, so the collision door and the art can't drift apart (#552).
SOUTH_DOOR_X = (43, 44)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def load_matrix_sector(matrix_dir, sector_name, W, H):
    """Return (roof_cells, sector_cells) for the named sector.

    roof = sector AND collision==1 (solid building); sector also includes the
    walkable apron. Mazes are flat ", "-joined cell ids, row-major by width W.
    """
    sid = None
    blocks = os.path.join(matrix_dir, "special_blocks", "sector_blocks.csv")
    with open(blocks) as fh:
        for line in fh:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3 and parts[2] == sector_name:
                sid = parts[0]
                break
    if sid is None:
        raise SystemExit(f"sector {sector_name!r} not found in {blocks}")

    sector = (
        open(os.path.join(matrix_dir, "maze", "sector_maze.csv"))
        .read()
        .strip()
        .split(", ")
    )
    collision = (
        open(os.path.join(matrix_dir, "maze", "collision_maze.csv"))
        .read()
        .strip()
        .split(", ")
    )
    if len(sector) != W * H:
        raise SystemExit(f"matrix has {len(sector)} cells but map is {W}x{H}={W*H}")

    roof, allcells = set(), set()
    for i, v in enumerate(sector):
        if v == sid:
            xy = (i % W, i // W)
            allcells.add(xy)
            if collision[i] == "1":
                roof.add(xy)
    return sid, roof, allcells


def stamp(furn, floor, W, roof, x, y, blk):
    """Place a furniture block (top-left at x,y) onto the furniture layer.

    A block is only placed if EVERY one of its cells is open floor (inside the
    footprint, floor==FLOOR, nothing already there) — so furniture never straddles
    a wall, blocks a doorway, or overlaps another piece. All-or-nothing keeps
    multi-tile objects (desks, beds, blackboards) intact.
    """
    cells = []
    for r, row in enumerate(blk):
        for c, cell in enumerate(row):
            if cell is None:
                continue
            xx, yy = x + c, y + r
            i = yy * W + xx
            if (xx, yy) not in roof or floor[i] != FLOOR or furn[i] != 0:
                return False
            cells.append((i, cell))
    for i, (sheet, col, rr) in cells:
        furn[i] = gid(sheet, col, rr)
    return True


def furnish_room(furn, floor, W, roof, room):
    """Fill one room with furniture appropriate to its kind."""
    x0, y0, x1, y1 = room["rect"]
    ix0, iy0, ix1, iy1 = x0 + 1, y0 + 1, x1 - 1, y1 - 1  # interior (inside walls)
    kind = room["kind"]

    if kind == "classroom":
        # Blackboard centred on the front (top) interior row.
        bw = len(room["board"][0])
        bx = (ix0 + ix1) // 2 - bw // 2
        stamp(furn, floor, W, roof, bx, iy0, room["board"])
        # Teacher desk just below the board.
        stamp(furn, floor, W, roof, bx, iy0 + 2, TEACHER_DESK)
        # Student desks: rows of 1x2 desks facing the board, with aisles.
        for dy in range(iy0 + 5, iy1, 3):  # desk(2) + aisle(1)
            for dx in range(ix0 + 1, ix1, 2):  # desk(1) + aisle(1)
                stamp(furn, floor, W, roof, dx, dy, DESK)

    elif kind == "office":
        stamp(furn, floor, W, roof, ix0, iy0 + 1, TEACHER_DESK)
        stamp(furn, floor, W, roof, ix0, iy0 + 3, OFFICE_CHAIR)
        for k in range(ix0 + 3, ix1, 2):  # bookshelves along the top wall
            stamp(furn, floor, W, roof, k, iy0, BOOKSHELF)
        stamp(furn, floor, W, roof, ix1, iy1, PLANT)

    elif kind == "restroom":
        for ty in range(iy0, iy1, 3):  # toilets down the left wall
            stamp(furn, floor, W, roof, ix0, ty, TOILET)
        for sy in range(iy0, iy1, 3):  # sinks down the right wall
            stamp(furn, floor, W, roof, ix1, sy, SINK)
        stamp(furn, floor, W, roof, (ix0 + ix1) // 2, (iy0 + iy1) // 2, BATHMAT)


def furnish_atrium(furn, floor, W, roof):
    """Dress the open central lobby/atrium: a reception desk, seating clusters
    (rug + flanking sofas + side tables) and scattered plants."""
    rx, ry = RECEPTION
    stamp(furn, floor, W, roof, rx, ry, TEACHER_DESK)
    for cx, cy in SEATING_CLUSTERS:
        stamp(furn, floor, W, roof, cx - 1, cy - 1, RUG)  # 3x3 rug
        stamp(furn, floor, W, roof, cx - 4, cy - 1, SOFA)  # sofa left of rug
        stamp(furn, floor, W, roof, cx + 2, cy - 1, SOFA)  # sofa right of rug
        stamp(furn, floor, W, roof, cx - 1, cy - 3, SIDE_TABLE)
    for px, py in ATRIUM_PLANTS:
        stamp(furn, floor, W, roof, px, py, PLANT)


# --------------------------------------------------------------------------- #
# Shell painting: floor everywhere, walls on room borders + footprint perimeter,
# doorway gaps, windows.
# --------------------------------------------------------------------------- #
def paint_shell(floor, W, roof):
    # 1. Floor every footprint cell (lobby gets a slightly different board).
    for x, y in roof:
        floor[y * W + x] = FLOOR

    # 2. Room divider walls + interior floor.
    for room in ROOMS:
        x0, y0, x1, y1 = room["rect"]
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if (x, y) not in roof:
                    continue
                on_border = x in (x0, x1) or y in (y0, y1)
                floor[y * W + x] = WALL if on_border else FLOOR

    # 3. Footprint perimeter is always a wall (a roof cell touching the outside).
    for x, y in roof:
        if any(
            (x + dx, y + dy) not in roof
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        ):
            floor[y * W + x] = WALL

    # 4. Carve doorways onto adjacent open floor.
    for room in ROOMS:
        _carve_door(floor, W, roof, room)

    # 5. Main south entrance (gap in the perimeter to the outside apron).
    for x in SOUTH_DOOR_X:
        col_ys = [y for (cx, y) in roof if cx == x]
        if col_ys:
            floor[max(col_ys) * W + x] = FLOOR


def _carve_door(floor, W, roof, room):
    x0, y0, x1, y1 = room["rect"]
    side, n = room["door"]
    if side in ("top", "bottom"):
        y = y0 if side == "top" else y1
        cx = (x0 + x1) // 2
        for x in range(cx - n // 2, cx - n // 2 + n):
            if (x, y) in roof:
                floor[y * W + x] = FLOOR
    else:
        x = x0 if side == "left" else x1
        cy = (y0 + y1) // 2
        for y in range(cy - n // 2, cy - n // 2 + n):
            if (x, y) in roof:
                floor[y * W + x] = FLOOR


def add_windows(furn, floor, W, roof):
    """Set windows into EXTERIOR walls (a wall cell whose outside neighbour is
    off-footprint), spaced out and away from corners/doors. Windows draw on the
    furniture layer ON TOP of the wall (their surround is transparent)."""

    def outside(x, y):
        return (x, y) not in roof

    for x, y in roof:
        i = y * W + x
        if floor[i] != WALL:
            continue
        n, s, e, w = (
            outside(x, y - 1),
            outside(x, y + 1),
            outside(x + 1, y),
            outside(x - 1, y),
        )
        corner = (n or s) and (e or w)
        if corner:
            continue
        if (n or s) and x % 4 == 0 and x not in SOUTH_DOOR_X:  # horizontal wall
            furn[i] = WINDOW
        elif (e or w) and y % 4 == 0:  # vertical wall
            furn[i] = WINDOW


# --------------------------------------------------------------------------- #
# .tmj surgery
# --------------------------------------------------------------------------- #
def strip_previous(tmj):
    tmj["tilesets"] = [
        t for t in tmj["tilesets"] if not str(t.get("name", "")).startswith("interior_")
    ]
    tmj["layers"] = [
        L for L in tmj["layers"] if not str(L.get("name", "")).startswith("williams_")
    ]


def append_tilesets(tmj):
    for name, img, cols, rows in _ALL_SHEETS:
        tmj["tilesets"].append(
            {
                "firstgid": _FIRST[name],
                "name": name,
                "image": img,
                "imagewidth": cols * 16,
                "imageheight": rows * 16,
                "tilewidth": 16,
                "tileheight": 16,
                "columns": cols,
                "tilecount": cols * rows,
                "margin": 0,
                "spacing": 0,
            }
        )
    tmj["tilesets"].sort(key=lambda t: t["firstgid"])


def clear_roof_on(tmj, layer_name, roof, W):
    for L in tmj["layers"]:
        if L.get("name") == layer_name and L.get("type") == "tilelayer":
            data = L["data"]
            for x, y in roof:
                data[y * W + x] = 0
            return


def insert_interior_layers(tmj, W, H, floor, furn):
    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1

    def mk(name, data, lid):
        return {
            "type": "tilelayer",
            "name": name,
            "id": lid,
            "x": 0,
            "y": 0,
            "width": W,
            "height": H,
            "opacity": 1,
            "visible": True,
            "data": data,
        }

    floor_layer = mk("williams_floor", floor, next_id)
    furn_layer = mk("williams_furniture", furn, next_id + 1)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 2)

    # Insert right after the buildings layer (so they sit above the ground/roads
    # we cleared) and before trees.
    names = [L.get("name") for L in tmj["layers"]]
    at = names.index("buildings") + 1 if "buildings" in names else len(tmj["layers"])
    tmj["layers"][at:at] = [floor_layer, furn_layer]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--tmj",
        default=os.path.join(
            repo, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
        ),
    )
    ap.add_argument(
        "--matrix",
        default=os.path.join(
            repo, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
        ),
    )
    ap.add_argument("--sector", default="Williams Hall")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="report footprint + cell counts, do not write",
    )
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    W, H = tmj["width"], tmj["height"]
    sid, roof, _apron = load_matrix_sector(args.matrix, args.sector, W, H)
    xs = [x for x, _ in roof]
    ys = [y for _, y in roof]
    print(
        f"{args.sector}: sector #{sid}  roof={len(roof)} cells  "
        f"bbox x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)}"
    )

    floor = [0] * (W * H)
    furn = [0] * (W * H)
    paint_shell(floor, W, roof)
    for room in ROOMS:
        furnish_room(furn, floor, W, roof, room)
    furnish_atrium(furn, floor, W, roof)
    add_windows(furn, floor, W, roof)

    painted_floor = sum(1 for v in floor if v)
    painted_furn = sum(1 for v in furn if v)
    print(
        f"  floor layer: {painted_floor} cells   furniture layer: {painted_furn} cells"
    )
    # sanity: nothing painted outside the footprint
    out = sum(1 for i, v in enumerate(floor) if v and (i % W, i // W) not in roof)
    print(f"  floor cells outside footprint: {out} (should be 0)")

    if args.dry_run:
        return

    strip_previous(tmj)
    append_tilesets(tmj)
    clear_roof_on(tmj, "buildings", roof, W)
    clear_roof_on(tmj, "trees", roof, W)
    insert_interior_layers(tmj, W, H, floor, furn)
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"  wrote {args.tmj}")


if __name__ == "__main__":
    main()
