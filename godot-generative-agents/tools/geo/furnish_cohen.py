#!/usr/bin/env python3
"""Furnish the Claudia Cohen Hall interior with a stone hex floor.

Cohen Hall is sector ``7`` (``UPenn:Claudia Cohen Hall``), with lobby arena
``1007``. This tool lays a floor on top of that footprint the same way
``furnish_sweeten.py`` / ``furnish_college_hall.py`` do -- in its own
``cohen_floor`` tile layer stacked above ``entrance_floor`` so
``add_entrances.py`` (which strips only ``entrance_*`` layers) leaves it intact
across runs.

    uv run python godot-generative-agents/tools/geo/furnish_cohen.py            # paint the floor
    uv run python godot-generative-agents/tools/geo/furnish_cohen.py --dry-run  # report, write nothing

The floor fills the walkable interior (the sector-7 footprint minus its 1-tile
perimeter ring), so a floor tile can never land on the wall ring or outside the
building. The tile is ``floor_stone_hex`` from the tile catalog -- the grey hex
stone floor, the institutional stone floor College Hall and Meyerson also use.

Idempotent: strips its own layer before re-inserting; backs up the .tmj first.
"""

import argparse
import json
import os

from add_entrances import split_footprint
from tmj_io import write_tmj

COHEN_SECTOR = "7"  # UPenn:Claudia Cohen Hall
COHEN_LOBBY = "1007"  # INTERIOR_ARENA_BASE (1000) + sector 7
FLOOR_LAYER = "cohen_floor"
WALL_LAYER = "cohen_walls"
COUNTER_LAYER = "cohen_counters"
COUNTER_FOOD_LAYER = "cohen_counter_food"  # dishes laid out on the counter tops
KITCHEN_PROPS_LAYER = "cohen_kitchen_props"  # crates/table in the Kitchen 2 alcove
ARENA_LAYER = "cohen_arenas"  # object layer holding the cafeteria/kitchen boxes

FLIP_V = 0x40000000  # Tiled vertical-flip flag

# floor_stone_hex: interior_franuka col 12, row 3 (the "grey hex stone floor").
# The franuka sheet is 32 tiles wide; the firstgid is read live from the .tmj
# (it shifts when the tilesets are repacked), so the gid can never desync into
# an out-of-range red-X.
FLOOR_SHEET = "franuka"
FLOOR_SHEET_COLS = 32
FLOOR_COL, FLOOR_ROW = 12, 3

# All tile offsets below are from the franuka firstgid (read live), so the gids
# never desync when the tilesets are repacked.
#
# East wall (kitchen | Cafeteria 2 seam):
#   - WALL_VERT: wall_set_red's middle-right cell (the straight vertical line,
#     gid 553, the same one furnish_college_hall uses). Runs down the seam.
#   - WALL_TOP / WALL_BOT: the transparent "corner" tiles the counter corner
#     pieces sit over at the two ends -- they carry no pixels themselves, they
#     just clear the wall line so the counter's own corner reads cleanly.
WALL_VERT_OFF = 1 * FLOOR_SHEET_COLS + 2  # col 2, row 1 of the 3x3 (gid 553)
WALL_TOP_OFF = 11 * FLOOR_SHEET_COLS + 21  # empty corner tile (gid 892)
WALL_BOT_OFF = 11 * FLOOR_SHEET_COLS + 25  # empty corner tile (gid 896)

# Counter runs (franuka col 0): a 2-tall unit, surface on top (row 23), cabinet
# front below (row 24), placed surface-up so both runs read right-side-up. Where
# a run turns into the east wall it uses a corner piece instead of the straight
# unit -- a different corner for the north end (turning down) and the south end
# (turning up).
COUNTER_TOP_OFF = 23 * FLOOR_SHEET_COLS + 0  # straight surface
COUNTER_BOT_OFF = 24 * FLOOR_SHEET_COLS + 0  # straight cabinet front
CORNER_N_TOP_OFF = 25 * FLOOR_SHEET_COLS + 8  # north-east corner, surface row
CORNER_N_BOT_OFF = 26 * FLOOR_SHEET_COLS + 8  # north-east corner, cabinet row
CORNER_S_TOP_OFF = 23 * FLOOR_SHEET_COLS + 3  # south-east corner, surface row
CORNER_S_BOT_OFF = 24 * FLOOR_SHEET_COLS + 3  # south-east corner, cabinet row

# Dining furniture: a grid of tables laid across each cafeteria, each set with a
# spread of dishes on its tabletop (the food layer stacks over the furniture).
FURN_LAYER = "cohen_furniture"  # tables (under food)
FOOD_LAYER = "cohen_food"  # dishes placed on the tabletops (over furniture)
DINING_TABLE = (12, 23, 2, 3)  # franuka col, row, w, h -- a 2x3 wooden table

# The dish palette (franuka col, row). Each table sets four cells (the 2x2 top of
# the table, above the legs); ``None`` leaves a cell bare.
_HAM, _FISH, _SALAD, _BREAD = (24, 22), (23, 19), (20, 21), (25, 21)
_SAUSAGE, _FRUIT, _MUG, _POT = (23, 18), (20, 14), (20, 15), (21, 20)
_BOWL, _BOWL_BLUE, _FOOD_BOWL = (20, 20), (20, 22), (21, 18)

# Per-table place settings, cycled by table index so the hall looks varied: some
# tables drop a dish (None), some swap the base spread for dishes that would
# otherwise go unused (sausage, fruit basket, bowls, mug, pot).
TABLE_SETTINGS = [
    [_HAM, _FISH, _SALAD, _BREAD],
    [_HAM, None, _SALAD, _BREAD],
    [_SAUSAGE, _FISH, _SALAD, _BREAD],
    [_HAM, _FISH, None, _POT],
    [_FRUIT, _FISH, _SALAD, None],
    [_HAM, _FOOD_BOWL, _MUG, _BREAD],
    [_SAUSAGE, None, _BOWL, _BOWL_BLUE],
    [_HAM, _FISH, _SALAD, None],
]

# Floor cushions (franuka col, row -- each 2x2, the same width as a table) tucked
# in as seating below the tables. Colour cycled by table index.
DINING_CUSHIONS = [
    (14, 15),  # cushion (blue)
    (12, 15),  # cushion_orange
    (16, 15),  # cushion_cream
    (18, 15),  # cushion_red
]
CUSHION_WH = (2, 2)

# Serving spread laid along the kitchen counter tops -- fruit baskets recurring
# among the menu items (ham, fish, sausage, bread, ...). Cycled along each
# counter surface; ``None`` leaves a stretch of bare counter.
COUNTER_ITEMS = [
    _FRUIT,
    _HAM,
    _FISH,
    _FRUIT,
    _SAUSAGE,
    _BREAD,
    None,
    _FRUIT,
    _SALAD,
    _POT,
    _HAM,
    _FRUIT,
    _FISH,
    None,
]

CAFETERIAS = ["Cafeteria 1", "Cafeteria 2", "Cafeteria 3"]

# Kitchen 2 (the narrow west prep alcove) -- filled with storage clutter and a
# small staff table with chairs. Each entry is (dx, dy, (col, row, w, h),
# flip_v), offset from the Kitchen 2 box's north-west corner.
_K_CRATE, _K_BARREL, _K_CHEST = (23, 14, 1, 1), (26, 13, 1, 2), (25, 14, 1, 1)
_K_POT, _K_BASKET, _K_CHAIR = (24, 14, 1, 1), (22, 14, 1, 1), (9, 17, 1, 1)
_K_TABLE = (12, 23, 2, 3)
KITCHEN2_PROPS = [
    (0, 0, _K_CRATE, False),  # storage row against the north wall
    (1, 0, _K_BARREL, False),
    (2, 0, _K_CHEST, False),
    (3, 0, _K_CRATE, False),
    (0, 1, _K_POT, False),
    (2, 1, _K_BASKET, False),
    (3, 1, _K_POT, False),
    (1, 2, _K_CHAIR, False),  # north chairs face the table (default facing)
    (2, 2, _K_CHAIR, False),
    (0, 3, _K_CRATE, False),  # a staff table flanked by storage
    (1, 3, _K_TABLE, False),
    (3, 4, _K_BARREL, False),
    (0, 5, _K_CRATE, False),
    (1, 6, _K_CHAIR, True),  # south chairs flipped to face the table
    (2, 6, _K_CHAIR, True),
    (0, 7, _K_BARREL, False),  # storage cluster at the south end
    (1, 7, _K_CRATE, False),
    (2, 7, _K_CHEST, False),
    (3, 7, _K_CRATE, False),
    (1, 8, _K_BASKET, False),
    (2, 8, _K_POT, False),
    (1, 9, _K_CRATE, False),
    (3, 9, _K_CHEST, False),
]

OWN_LAYERS = [
    FLOOR_LAYER,
    WALL_LAYER,
    COUNTER_LAYER,
    COUNTER_FOOD_LAYER,
    KITCHEN_PROPS_LAYER,
    FURN_LAYER,
    FOOD_LAYER,
]


def read_flat(path):
    """Read a matrix maze CSV (flat, ', '-joined, row-major) into a list."""
    with open(path) as fh:
        return fh.read().strip().split(", ")


def franuka_firstgid(tmj):
    """The interior_franuka tileset's firstgid (shifts when tilesets repack, so
    always read live)."""
    return next(
        ts["firstgid"]
        for ts in tmj["tilesets"]
        if FLOOR_SHEET in (ts.get("source", "") + ts.get("image", ""))
    )


def floor_gid(tmj):
    """Live gid for floor_stone_hex: the franuka firstgid plus the tile's
    row-major offset in that 32-wide sheet."""
    return franuka_firstgid(tmj) + FLOOR_ROW * FLOOR_SHEET_COLS + FLOOR_COL


def cohen_interior_cells(tmj, matrix_dir):
    """Walkable interior of Cohen Hall as a set of flat indices: the sector-7
    footprint (sector cells painted into entrance_floor) minus its 1-tile
    perimeter ring. Computed from the footprint, not the arena id, so it stays
    correct even if the interior is later subdivided into per-room arenas."""
    W, H = tmj["width"], tmj["height"]
    ef = next(
        (
            L
            for L in tmj["layers"]
            if L.get("name") == "entrance_floor" and L.get("type") == "tilelayer"
        ),
        None,
    )
    entrance = {(i % W, i // W) for i, v in enumerate(ef["data"]) if v} if ef else set()
    sector = read_flat(os.path.join(matrix_dir, "maze", "sector_maze.csv"))
    foot = {
        (i % W, i // W) for i, s in enumerate(sector) if s == COHEN_SECTOR
    } & entrance
    _perimeter, interior = split_footprint(foot, W, H)
    return {y * W + x for (x, y) in interior}


def _strip(tmj, names):
    tmj["layers"] = [L for L in tmj["layers"] if L.get("name") not in names]


def _new_layer(name, data, W, H, layer_id):
    return {
        "type": "tilelayer",
        "name": name,
        "id": layer_id,
        "x": 0,
        "y": 0,
        "width": W,
        "height": H,
        "opacity": 1,
        "visible": True,
        "data": data,
    }


def apply(tmj, matrix_dir):
    """Insert the cohen_floor layer above entrance_floor, painted only on the
    walkable interior. Returns the count of floored cells."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, set(OWN_LAYERS))

    gid = floor_gid(tmj)
    interior = cohen_interior_cells(tmj, matrix_dir)
    data = [0] * (W * H)
    for i in interior:
        data[i] = gid

    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    floor = _new_layer(FLOOR_LAYER, data, W, H, next_id)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 1)

    names = [L.get("name") for L in tmj["layers"]]
    at = (
        names.index("entrance_floor") + 1
        if "entrance_floor" in names
        else len(tmj["layers"])
    )
    tmj["layers"][at:at] = [floor]
    return len(interior)


def cohen_boxes(tmj):
    """The cohen_arenas object rectangles as {name: set of (x, y) tile cells}.
    Kitchen 1 + Kitchen 2 together are the continuous kitchen; Cafeteria 1/2/3
    together are the continuous cafeteria."""
    T = tmj.get("tilewidth", 16)
    layer = next((L for L in tmj["layers"] if L.get("name") == ARENA_LAYER), None)
    if layer is None:
        return {}
    out = {}
    for o in layer.get("objects", []):
        x0, y0 = round(o["x"] / T), round(o["y"] / T)
        x1, y1 = round((o["x"] + o["width"]) / T), round((o["y"] + o["height"]) / T)
        out[o["name"]] = {(x, y) for x in range(x0, x1) for y in range(y0, y1)}
    return out


def cohen_sections(tmj):
    """{name: (c0, r0, c1, r1)} inclusive tile rects from cohen_arenas. All five
    boxes are real rooms (no decoys), so none are filtered."""
    T = tmj.get("tilewidth", 16)
    layer = next((L for L in tmj["layers"] if L.get("name") == ARENA_LAYER), None)
    out = {}
    if layer is None:
        return out
    for o in layer.get("objects", []):
        c0 = round(o["x"] / T)
        r0 = round(o["y"] / T)
        c1 = round((o["x"] + o["width"]) / T) - 1
        r1 = round((o["y"] + o["height"]) / T) - 1
        out[o["name"]] = (c0, r0, c1, r1)
    return out


def kitchen_wall_cells(tmj):
    """The kitchen east-wall seam: Kitchen cells whose east neighbour is
    Cafeteria 2, as a set of (x, y) collision cells. This is the partition
    apply_kitchen draws as wall_set_red; the matrix subdivision and the picture
    share it so they stay in lock-step. Counters (the north/south seams) are
    furniture, not collision walls."""
    boxes = cohen_boxes(tmj)
    kitchen = boxes.get("Kitchen 1", set()) | boxes.get("Kitchen 2", set())
    caf2 = boxes.get("Cafeteria 2", set())
    return {(x, y) for (x, y) in kitchen if (x + 1, y) in caf2}


def apply_kitchen(tmj):
    """Wall off the kitchen's east side (where it meets Cafeteria 2) and run
    serving counters along its north and south sides (where they meet Cafeteria
    1 and 3). Inserts the cohen_walls + cohen_counters layers above the floor.
    Returns (wall_cells, counter_cells)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {WALL_LAYER, COUNTER_LAYER, COUNTER_FOOD_LAYER})

    boxes = cohen_boxes(tmj)
    kitchen = boxes.get("Kitchen 1", set()) | boxes.get("Kitchen 2", set())
    caf1 = boxes.get("Cafeteria 1", set())
    caf2 = boxes.get("Cafeteria 2", set())
    caf3 = boxes.get("Cafeteria 3", set())

    fg = franuka_firstgid(tmj)

    def gid(off):
        return fg + off

    walls = [0] * (W * H)
    counters = [0] * (W * H)

    # East wall: the kitchen column whose eastern neighbour is Cafeteria 2. A
    # straight vertical line down the seam, capped at each end by a transparent
    # corner tile so the counter's own corner piece reads cleanly there.
    wall_col = sorted(kitchen_wall_cells(tmj), key=lambda p: p[1])
    for x, y in wall_col:
        walls[y * W + x] = gid(WALL_VERT_OFF)
    if wall_col:
        (tx, ty), (bx, by) = wall_col[0], wall_col[-1]
        walls[ty * W + tx] = gid(WALL_TOP_OFF)  # north-east corner (transparent)
        walls[by * W + bx] = gid(WALL_BOT_OFF)  # south-east corner (transparent)
        # complete the south-east corner post as a 2x2 (all transparent tiles)
        for cx, cy in ((bx + 1, by), (bx, by + 1), (bx + 1, by + 1)):
            walls[cy * W + cx] = gid(WALL_BOT_OFF)

    # Counters: a kitchen cell on the seam with Cafeteria 1 (north) or 3 (south)
    # anchors a 2-tall counter unit stepping one cell into the kitchen, surface-up
    # (surface on the outer row, cabinet just inside). Where a run reaches the
    # east wall it turns the corner with a dedicated corner piece instead of the
    # straight unit.
    counter_n = 0
    north_surface = []  # (x, y) of each north counter's top (serving) surface
    south_surface = []  # (x, y) of each south counter's top (serving) surface
    for x, y in kitchen:
        on_wall = (x + 1, y) in caf2  # this cell is also the east wall seam
        if (x, y - 1) in caf1:  # north seam -> surface at y, cabinet at y+1
            top, bot = (
                (CORNER_N_TOP_OFF, CORNER_N_BOT_OFF)
                if on_wall
                else (COUNTER_TOP_OFF, COUNTER_BOT_OFF)
            )
            counters[y * W + x] = gid(top)
            if (x, y + 1) in kitchen:
                counters[(y + 1) * W + x] = gid(bot)
            north_surface.append((x, y))
            counter_n += 1
        if (x, y + 1) in caf3:  # south seam -> surface at y-1, cabinet at y
            top, bot = (
                (CORNER_S_TOP_OFF, CORNER_S_BOT_OFF)
                if on_wall
                else (COUNTER_TOP_OFF, COUNTER_BOT_OFF)
            )
            counters[y * W + x] = gid(bot)
            if (x, y - 1) in kitchen:
                counters[(y - 1) * W + x] = gid(top)
            south_surface.append((x, y - 1))
            counter_n += 1

    # Lay a serving spread along the counter tops: fruit baskets and menu items
    # cycled across the north-then-south surface cells (west to east).
    counter_food = [0] * (W * H)
    food_n = 0
    surfaces = sorted(north_surface) + sorted(south_surface)
    for i, (x, y) in enumerate(surfaces):
        item = COUNTER_ITEMS[i % len(COUNTER_ITEMS)]
        if item:
            ic, ir = item
            counter_food[y * W + x] = gid(ir * 32 + ic)
            food_n += 1

    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    wall_layer = _new_layer(WALL_LAYER, walls, W, H, next_id)
    counter_layer = _new_layer(COUNTER_LAYER, counters, W, H, next_id + 1)
    food_layer = _new_layer(COUNTER_FOOD_LAYER, counter_food, W, H, next_id + 2)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 3)

    # Stack just above the cohen_floor: floor < walls < counters < counter_food.
    names = [L.get("name") for L in tmj["layers"]]
    at = names.index(FLOOR_LAYER) + 1 if FLOOR_LAYER in names else len(tmj["layers"])
    tmj["layers"][at:at] = [wall_layer, counter_layer, food_layer]
    wall_n = sum(1 for v in walls if v)
    return wall_n, counter_n, food_n


def apply_kitchen_props(tmj):
    """Fill the Kitchen 2 alcove (the narrow west prep strip) with storage
    clutter -- crates, barrels, chests, pots, baskets -- plus a small staff
    table and chairs. Inserts the cohen_kitchen_props layer. Each prop is placed
    only if its whole footprint lands on Kitchen 2 floor. Returns the prop count.
    """
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {KITCHEN_PROPS_LAYER})

    k2 = cohen_boxes(tmj).get("Kitchen 2", set())
    floor = _floor_cells(tmj)
    props = [0] * (W * H)
    placed = 0
    if k2:
        fg = franuka_firstgid(tmj)
        ox, oy = min(x for x, _ in k2), min(y for _, y in k2)
        for dx, dy, (col, row, w, h), flip in KITCHEN2_PROPS:
            cells = [(ox + dx + ix, oy + dy + iy) for iy in range(h) for ix in range(w)]
            if not all(c in k2 and c in floor for c in cells):
                continue
            for iy in range(h):
                for ix in range(w):
                    g = fg + (row + iy) * 32 + (col + ix)
                    if flip:
                        g |= FLIP_V
                    props[(oy + dy + iy) * W + (ox + dx + ix)] = g
            placed += 1

    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    layer = _new_layer(KITCHEN_PROPS_LAYER, props, W, H, next_id)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 1)

    names = [L.get("name") for L in tmj["layers"]]
    at = (
        names.index(COUNTER_LAYER) + 1 if COUNTER_LAYER in names else len(tmj["layers"])
    )
    tmj["layers"][at:at] = [layer]
    return placed


def _floor_cells(tmj):
    """The walkable cohen floor as a set of (x, y) -- everything a table may
    stand on. Read from the painted cohen_floor layer."""
    W = tmj["width"]
    L = next((l for l in tmj["layers"] if l.get("name") == FLOOR_LAYER), None)
    return {(i % W, i // W) for i, v in enumerate(L["data"]) if v} if L else set()


def table_anchors(box, floor, tw, th, pitch_x=6, pitch_y=6):
    """Top-left anchors for a grid of tw x th tables inside one cafeteria box,
    inset a tile from its edges and spaced by pitch_x / pitch_y (table + aisle).
    A slot is kept only if the whole table footprint stands on walkable floor
    and inside the box, so tables never straddle a wall, aisle, or the kitchen."""
    xs = [c[0] for c in box]
    ys = [c[1] for c in box]
    x0, x1 = min(xs) + 1, max(xs) - 1
    y0, y1 = min(ys) + 1, max(ys) - 1
    anchors = []
    ay = y0
    while ay + th - 1 <= y1:
        ax = x0
        while ax + tw - 1 <= x1:
            foot = [(ax + dx, ay + dy) for dy in range(th) for dx in range(tw)]
            if all(c in box and c in floor for c in foot):
                anchors.append((ax, ay))
            ax += pitch_x
        ay += pitch_y
    return anchors


def apply_dining(tmj):
    """Furnish every cafeteria with a grid of dining tables, each set with a
    varied spread of dishes on its tabletop. Inserts cohen_furniture (tables) +
    cohen_food (dishes, on top). Confined to the Cafeteria boxes -- never the
    kitchen. Returns (table_count, dish_count)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {FURN_LAYER, FOOD_LAYER})

    boxes = cohen_boxes(tmj)
    floor = _floor_cells(tmj)
    fg = franuka_firstgid(tmj)
    tcol, trow, tw, th = DINING_TABLE

    furn = [0] * (W * H)
    food = [0] * (W * H)
    cw, ch = CUSHION_WH
    table_i = 0
    dish_n = 0
    cushion_n = 0
    for name in CAFETERIAS:
        box = boxes.get(name, set())
        if not box:
            continue
        for ax, ay in table_anchors(box, floor, tw, th):
            for dy in range(th):
                for dx in range(tw):
                    furn[(ay + dy) * W + (ax + dx)] = (
                        fg + (trow + dy) * 32 + (tcol + dx)
                    )
            # dishes on the 2x2 tabletop surface (top two rows, above the legs)
            surface = [(ax, ay), (ax + 1, ay), (ax, ay + 1), (ax + 1, ay + 1)]
            setting = TABLE_SETTINGS[table_i % len(TABLE_SETTINGS)]
            for dish, (cx, cy) in zip(setting, surface):
                if dish:
                    dc, dr = dish
                    food[cy * W + cx] = fg + dr * 32 + dc
                    dish_n += 1
            # a floor cushion tucked in as seating just below the table, kept
            # only where the whole cushion still lands on cafeteria floor
            cushion = [(ax + dx, ay + th + dy) for dy in range(ch) for dx in range(cw)]
            if all(c in box and c in floor for c in cushion):
                ccol, crow = DINING_CUSHIONS[table_i % len(DINING_CUSHIONS)]
                for dy in range(ch):
                    for dx in range(cw):
                        furn[(ay + th + dy) * W + (ax + dx)] = (
                            fg + (crow + dy) * 32 + (ccol + dx)
                        )
                cushion_n += 1
            table_i += 1

    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    furn_layer = _new_layer(FURN_LAYER, furn, W, H, next_id)
    food_layer = _new_layer(FOOD_LAYER, food, W, H, next_id + 1)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 2)

    # Stack above the counters: floor < walls < counters < furniture < food.
    names = [L.get("name") for L in tmj["layers"]]
    at = (
        names.index(COUNTER_LAYER) + 1 if COUNTER_LAYER in names else len(tmj["layers"])
    )
    tmj["layers"][at:at] = [furn_layer, food_layer]
    return table_i, dish_n, cushion_n


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    ap = argparse.ArgumentParser(description=__doc__)
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
    ap.add_argument("--dry-run", action="store_true", help="report, do not write")
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    floored = apply(tmj, args.matrix)
    print(f"{FLOOR_LAYER}: painted {floored} interior cells (GID {floor_gid(tmj)})")
    wall_n, counter_n, counter_food_n = apply_kitchen(tmj)
    print(f"{WALL_LAYER}: {wall_n} east wall cells (vs Cafeteria 2)")
    print(f"{COUNTER_LAYER}: {counter_n} counter runs (N=Cafeteria 1, S=Cafeteria 3)")
    print(f"{COUNTER_FOOD_LAYER}: {counter_food_n} items on the counter tops")
    props_n = apply_kitchen_props(tmj)
    print(f"{KITCHEN_PROPS_LAYER}: {props_n} props in the Kitchen 2 alcove")
    tables, dishes, cushions = apply_dining(tmj)
    print(
        f"{FURN_LAYER}/{FOOD_LAYER}: {tables} tables, {cushions} cushions, "
        f"{dishes} dishes across cafeterias"
    )

    if args.dry_run:
        return
    write_tmj(args.tmj, tmj)
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")


if __name__ == "__main__":
    main()
