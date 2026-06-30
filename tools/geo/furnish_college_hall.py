#!/usr/bin/env python3
"""Furnish the College Hall interior (UPenn's iconic green-serpentine main hall).

College Hall is the carved sector ``8`` (``UPenn:College Hall``). ``add_entrances.py``
has already carved it into the door-gated system: an ``entrance_floor`` cutaway,
a one-tile perimeter wall, a door, and one lobby arena (``1008``). This tool
layers the *detailed interior* on top of that carve, the same way
``furnish_houston.py`` / ``furnish_fisher.py`` do -- in its own ``college_hall_*``
tile layers stacked above ``entrance_floor`` so ``add_entrances.py`` (which
strips only ``entrance_*`` layers) leaves them intact across runs.

    uv run python tools/geo/furnish_college_hall.py            # paint the floor
    uv run python tools/geo/furnish_college_hall.py --dry-run  # report, write nothing

STAGE 1 (this version): the floor only. It fills the walkable interior (the
sector-8 footprint minus its perimeter ring), so a floor tile can never land
on the brick ring or outside the building. Walls + furniture follow once the
room bounding boxes are drawn (a ``college_hall_arenas`` object layer).

Idempotent: strips its own layers before re-inserting; backs up the .tmj first.
"""

import argparse
import json
import os
import shutil

from add_entrances import split_footprint

COLLEGE_SECTOR = "8"  # UPenn:College Hall
COLLEGE_LOBBY = "1008"  # INTERIOR_ARENA_BASE (1000) + sector 8
FLOOR_GID = 627  # interior_franuka floor_stone_hex (col 12,row 3) -- grey
# hex stone, fitting College Hall's stone character.
FLOOR_LAYER = "college_hall_floor"

# wall_set_red thin-line edges (interior_franuka 3x3 autotile at col0/row0):
# a ~5px maroon strip on one side of the cell, transparent backing, on its own
# layer above the floor.
WALL_R = 553  # right edge
WALL_B = 584  # bottom edge
WALL_BR = 585  # bottom-right corner (cell needs both a right and bottom strip)
WALL_LAYER = "college_hall_walls"
DOOR_W = 2  # centered doorway gap, in cells, per partition segment
WALL_SET = {WALL_R, WALL_B, WALL_BR}  # all wall_set_red edge gids this tool places

# Three stacked layers: rugs UNDER furniture (so a sofa/table sits on a rug),
# and props OVER furniture (so food/books sit ON a table, not on the floor).
RUG_LAYER = "college_hall_rugs"
FURN_LAYER = "college_hall_furniture"
PROP_LAYER = "college_hall_props"
RUGS = {"rug_red", "rug_blue", "rug_orange", "rug_green", "rug_magenta", "rug_cyan"}
PROPS = {
    "food_ham",
    "food_salad",
    "food_bowl",
    "food_fish",
    "food_sausage",
    "bread",
    "basket_fruit",
    "mug",
    "jar",
    "pot",
    "books_green",
    "book_stack_red",
    "quill_ink",
    "inkwell",
    "scroll",
}

# Room pairs that should flow openly into each other (no partition at all -- the
# whole seam between them is cleared, including any circulation gap). Keeps the
# grand central space continuous from the kitchen down through the great hall.
OPEN_SEAMS = [("Central Hall", "Great Hall"), ("Central Hall", "Kitchen In")]

OWN_LAYERS = [FLOOR_LAYER, WALL_LAYER, RUG_LAYER, FURN_LAYER, PROP_LAYER]


def read_flat(path):
    """Read a matrix maze CSV (flat, ', '-joined, row-major) into a list."""
    with open(path) as fh:
        return fh.read().strip().split(", ")


def college_interior_cells(tmj, matrix_dir):
    """Walkable interior of College Hall as a set of flat indices: the sector-8
    footprint (sector cells painted into entrance_floor) minus its 1-tile
    perimeter ring. Computed from the footprint, not the arena ids, so it stays
    correct after add_entrances subdivides the interior into per-room arenas."""
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
        (i % W, i // W) for i, s in enumerate(sector) if s == COLLEGE_SECTOR
    } & entrance
    _perimeter, interior = split_footprint(foot, W, H)
    return {y * W + x for (x, y) in interior}


def read_sections(tmj):
    """Room name -> (c0, r0, c1, r1) inclusive tile rect, from the hand-drawn
    college_hall_arenas object layer. Objects whose name contains 'rug' are
    rug-fill regions, not rooms, so they are excluded (consistent with Fisher)."""
    fa = next(
        (
            L
            for L in tmj["layers"]
            if L.get("name") == "college_hall_arenas" and L.get("type") == "objectgroup"
        ),
        None,
    )
    secs = {}
    if not fa:
        return secs
    for o in fa["objects"]:
        name = o.get("name") or ""
        if not name or "rug" in name.lower():
            continue
        c0 = round(o["x"] / 16)
        r0 = round(o["y"] / 16)
        c1 = round((o["x"] + o["width"]) / 16) - 1
        r1 = round((o["y"] + o["height"]) / 16) - 1
        secs[name] = (c0, r0, c1, r1)
    return secs


def _enforce_max3_per_2x2(data, W, H):
    """Invariant: no 2x2 block may hold 4 wall_set_red cells (always a parallel
    double wall). Scan every 2x2 window and drop a wall until none has 4.
    Returns the count removed."""
    removed = 0
    changed = True
    while changed:
        changed = False
        for r in range(H - 1):
            base = r * W
            for c in range(W - 1):
                quad = [base + c, base + c + 1, base + W + c, base + W + c + 1]
                walls = [i for i in quad if data[i] in WALL_SET]
                if len(walls) >= 4:
                    data[walls[-1]] = 0
                    removed += 1
                    changed = True
    return removed


def _clear_open_seams(data, sections, W):
    """Zero every wall cell in the seam between each OPEN_SEAMS room pair -- the
    band of cells between their two rects (over the overlapping span), including
    any circulation gap -- so the rooms flow openly into each other."""
    cleared = 0
    for a, b in OPEN_SEAMS:
        if a not in sections or b not in sections:
            continue
        ax0, ay0, ax1, ay1 = sections[a]
        bx0, by0, bx1, by1 = sections[b]
        if ay1 <= by0 or by1 <= ay0:  # vertically stacked
            r0, r1 = (ay1, by0) if ay1 <= by0 else (by1, ay0)
            cs, ce = max(ax0, bx0), min(ax1, bx1)
            band = [(c, r) for r in range(r0, r1 + 1) for c in range(cs, ce + 1)]
        elif ax1 <= bx0 or bx1 <= ax0:  # horizontally adjacent
            c0, c1 = (ax1, bx0) if ax1 <= bx0 else (bx1, ax0)
            rs, re = max(ay0, by0), min(ay1, by1)
            band = [(c, r) for c in range(c0, c1 + 1) for r in range(rs, re + 1)]
        else:
            band = []
        for c, r in band:
            if data[r * W + c]:
                data[r * W + c] = 0
                cleared += 1
    return cleared


def _runs(coords):
    """Yield (start, end) inclusive contiguous integer runs from a coord list."""
    coords = sorted(set(coords))
    s = p = coords[0]
    for x in coords[1:]:
        if x == p + 1:
            p = x
        else:
            yield (s, p)
            s = p = x
    yield (s, p)


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
    """Insert the college_hall_floor layer above entrance_floor, painted only on
    the walkable interior. Returns the count of floored cells."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, set(OWN_LAYERS))

    interior = college_interior_cells(tmj, matrix_dir)
    data = [0] * (W * H)
    for i in interior:
        data[i] = FLOOR_GID

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


def _wall_data(tmj, interior, W, H):
    """Compute the college_hall_walls tile data (flat array of wall gids) from
    the room boxes: auto-enclose every boundary where a room cell meets a
    different room or open circulation (skip the building perimeter, which
    already blocks), close 1-cell circulation gaps so abutting rooms share a
    single boundary, leave a centered doorway per partition, and enforce <=3
    wall cells per 2x2. `interior` is a set of flat indices. Returns
    (data, doors, removed). Shared by apply_walls and college_wall_cells."""
    import collections

    sections = read_sections(tmj)
    cell2room = {}
    for nm, (c0, r0, c1, r1) in sections.items():
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                idx = r * W + c
                if idx in interior and idx not in cell2room:  # first box wins overlaps
                    cell2room[idx] = nm

    # Close 1-cell circulation gaps between two rooms (avoid parallel doubles).
    base = dict(cell2room)

    def _broom(c, r):
        return base.get(r * W + c) if (0 <= c < W and 0 <= r < H) else None

    for idx in interior:
        if idx in base:
            continue
        c, r = idx % W, idx // W
        if _broom(c, r - 1) and _broom(c, r + 1):
            cell2room[idx] = _broom(c, r - 1)
        elif _broom(c - 1, r) and _broom(c + 1, r):
            cell2room[idx] = _broom(c - 1, r)

    def room(c, r):
        return cell2room.get(r * W + c)

    def inter(c, r):
        return (r * W + c) in interior

    vert = collections.defaultdict(list)  # (c, pair) -> rows; wall on (c,r) right edge
    horiz = collections.defaultdict(
        list
    )  # (r, pair) -> cols; wall on (c,r) bottom edge
    for idx in interior:
        c, r = idx % W, idx // W
        ra = cell2room.get(idx)
        if inter(c + 1, r):
            rb = room(c + 1, r)
            if ra != rb and (ra or rb):
                vert[(c, frozenset({ra, rb}))].append(r)
        if inter(c, r + 1):
            rb = room(c, r + 1)
            if ra != rb and (ra or rb):
                horiz[(r, frozenset({ra, rb}))].append(c)

    Vcells, Hcells, doors = set(), set(), 0
    for (c, _pair), rows in vert.items():
        for s, e in _runs(rows):
            d0 = s + max(0, (e - s + 1 - DOOR_W) // 2)
            for r in range(s, e + 1):
                if d0 <= r < d0 + DOOR_W:
                    doors += 1
                else:
                    Vcells.add((c, r))
    for (r, _pair), cols in horiz.items():
        for s, e in _runs(cols):
            d0 = s + max(0, (e - s + 1 - DOOR_W) // 2)
            for c in range(s, e + 1):
                if d0 <= c < d0 + DOOR_W:
                    doors += 1
                else:
                    Hcells.add((c, r))

    data = [0] * (W * H)
    for c, r in Vcells | Hcells:
        v, h = (c, r) in Vcells, (c, r) in Hcells
        data[r * W + c] = WALL_BR if (v and h) else (WALL_R if v else WALL_B)

    _clear_open_seams(data, sections, W)  # open the central-space room seams
    removed = _enforce_max3_per_2x2(data, W, H)
    return data, doors, removed


def college_wall_cells(tmj, interior, W, H):
    """The partition-wall cell set {(x, y)} -- exactly the cells apply_walls
    paints. `interior` is a set of flat indices. Used by
    add_entrances.load_college_hall_plan to derive collision from the room
    boxes, so matrix and picture stay in lock-step."""
    data, _doors, _removed = _wall_data(tmj, interior, W, H)
    return {(i % W, i // W) for i, v in enumerate(data) if v}


def apply_walls(tmj, matrix_dir):
    """Insert the college_hall_walls layer (above the floor) from _wall_data.
    Returns (wall_cells, doorway_cells, removed)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {WALL_LAYER})
    interior = college_interior_cells(tmj, matrix_dir)
    data, doors, removed = _wall_data(tmj, interior, W, H)
    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    walls = _new_layer(WALL_LAYER, data, W, H, next_id)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 1)
    names = [L.get("name") for L in tmj["layers"]]
    anchor = FLOOR_LAYER if FLOOR_LAYER in names else "entrance_floor"
    at = names.index(anchor) + 1 if anchor in names else len(tmj["layers"])
    tmj["layers"][at:at] = [walls]
    return sum(1 for v in data if v), doors, removed


def load_sprites(tmj):
    """catalog name -> (top_left_gid, w, h, cols). Firstgids/columns are read
    from the live tmj tilesets (not hardcoded), so GIDs are correct even though
    the newer sheets' firstgids differ from other branches."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "furniture_catalog.json")) as fh:
        cat = json.load(fh)

    def norm(n):
        return (
            n.replace("interior_", "")
            .replace("kenney_urban", "kenney")
            .replace("tilemap_packed", "kenney")
        )

    sheets = {norm(t["name"]): (t["firstgid"], t["columns"]) for t in tmj["tilesets"]}
    out = {}
    for name, v in cat["objects"].items():
        if not (isinstance(v, dict) and v.get("sheet") in sheets):
            continue
        fg, cols = sheets[v["sheet"]]
        out[name] = (fg + v["row"] * cols + v["col"], v["w"], v["h"], cols)
    return out


def _stamp(data, occ, sprites, name, c, r, walk, W):
    """Place a whole multi-tile sprite with its top-left at (c, r). Refuses (and
    changes nothing) unless every w*h cell is walkable floor and unoccupied --
    the cardinal rule: never place part of a sprite. Returns bool."""
    if name not in sprites:
        return False
    gid, w, h, cols = sprites[name]
    cells = [(c + dx, r + dy) for dy in range(h) for dx in range(w)]
    if any((x, y) not in walk or (x, y) in occ for (x, y) in cells):
        return False
    for dy in range(h):
        for dx in range(w):
            x, y = c + dx, r + dy
            data[y * W + x] = gid + dy * cols + dx
            occ.add((x, y))
    return True


def _room_layouts(sections):
    """Per-room furniture placements (name, col, row of each sprite's top-left),
    in the franuka Examples idiom: rug + seating clusters, shelves/desks along
    walls, counters + food in the kitchen, plants in corners. Over-proposes;
    _stamp skips anything that would clip a wall or overlap."""
    out = []
    add = lambda *t: out.append(t)

    def shelf_row(c0, c1, r, name, step=3):
        for c in range(c0, c1 - 1, step):
            add(name, c, r)

    for name, (c0, r0, c1, r1) in sections.items():
        if name == "Central Hall":
            # grand open hall: seating clusters up top, a deep field of cushion
            # floor-seating below, sofas + grandfather clock + candelabra + plants
            add("grandfather_clock", c0 + 1, r0 + 1)
            for cc in (c0 + 5, c0 + 15, c0 + 25):
                add("rug_red", cc, r0 + 1)
                add("round_table_small", cc + 1, r0 + 2)
                add("armchair", cc, r0 + 2)
                add("armchair_pink", cc + 2, r0 + 2)
            add("sofa", c0 + 10, r0 + 1)
            add("sofa", c0 + 20, r0 + 1)
            # cushion lounge: each colour is a 4x4 block of 2x2 cushions packed
            # edge-to-edge, but the centre 2x2 of each block becomes a pair of
            # dining tables -> cushions read as vertical strips flanking tables.
            for col_name, zc in (
                ("cushion", c0 + 2),
                ("cushion_red", c0 + 12),
                ("cushion_orange", c0 + 22),
            ):
                for ri, rr in enumerate(range(r0 + 6, r0 + 13, 2)):
                    for ci, cc in enumerate(range(zc, zc + 8, 2)):
                        if ci in (1, 2):
                            continue  # centre columns -> tables only
                        add(col_name, cc, rr)
                add("dining_table", zc + 2, r0 + 8)  # 2x3 tables in the centre
                add("dining_table", zc + 4, r0 + 8)
            add("candelabra", c0 + 10, r0 + 7)  # in the gaps between blocks
            add("candelabra", c0 + 20, r0 + 9)
            for px, py in ((c0, r1 - 1), (c1 - 1, r0), (c1 - 1, r1 - 1)):
                add("plant", px, py)
        elif name == "Great Hall":
            # banquet hall: dining tables with chairs on a rug
            add("rug_blue", c0 + 2, r0 + 2)
            add("dining_table_light", c0 + 3, r0 + 2)
            add("chair_wood", c0 + 2, r0 + 3)
            add("chair_wood", c0 + 6, r0 + 3)
            add("dining_table_light", c0 + 3, r0 + 6)
            add("chair_wood", c0 + 2, r0 + 7)
            add("chair_wood", c0 + 6, r0 + 7)
            add("plant", c0 + 1, r0 + 1)
            add("plant", c1 - 1, r1 - 1)
        elif name == "West Wing":
            # classroom: blackboard + teacher desk + rows of student desks + shelves
            add("blackboard", c0 + 2, r0)
            add("teacher_desk", c0 + 8, r0 + 1)
            for r in range(r0 + 4, r1 - 1, 3):
                for c in range(c0 + 1, c1 - 1, 3):
                    add("student_desk", c, r)
            shelf_row(c0 + 1, c1, r1 - 2, "bookshelf")
        elif name == "East Wing":
            # office suite: desk clusters + bookshelves + a locker + plants
            shelf_row(c0 + 1, c1, r0, "bookshelf_wood_books")
            for r in range(r0 + 4, r1 - 1, 4):
                for c in range(c0 + 1, c1 - 1, 4):
                    add("teacher_desk", c, r)
            add("locker", c1 - 1, r1 - 2)
            add("plant", c0 + 1, r1 - 1)
        elif name == "Restrooms":
            add("toilet", c0 + 1, r0)
            add("sink", c0 + 3, r0)
            add("mirror", c0 + 5, r0)
            add("bathmat", c0 + 1, r0 + 2)
            add("towels", c0 + 3, r0 + 2)
        elif name == "Kitchen In":
            # prep tables down the room with food set ON them (props render over
            # the table tops), a counter at the end -- no free-floating stove
            foods = ["food_ham", "food_salad", "bread", "food_bowl", "basket_fruit"]
            i = 0
            for cc in range(c0 + 1, c1 - 3, 4):
                add("dining_table_light", cc, r0)  # 2x3 table
                add(foods[i % len(foods)], cc, r0)  # food on the table top
                add(foods[(i + 1) % len(foods)], cc + 1, r0)
                i += 2
            add("counter", c1 - 2, r0)
        elif name == "Kitchen Out":
            for c in range(c0 + 1, c1 - 1, 2):
                add("counter", c, r0)
            add("dining_table_light", c0 + 1, r0 + 3)  # table with food on top
            add("food_salad", c0 + 1, r0 + 3)
            add("bread", c0 + 2, r0 + 3)
            add("barrel", c1 - 1, r1 - 2)
        elif name == "East Pavilion 1":
            add("teacher_desk", c0 + 2, r0 + 1)
            add("bookshelf", c1 - 1, r0 + 1)
            add("plant", c0 + 1, r1 - 1)
        elif name == "East Pavilion 2":
            for r in range(r0 + 1, r1 - 2, 4):
                add("teacher_desk", c0 + 2, r)
            add("bookshelf_wood_books", c1 - 1, r0 + 1)
            add("plant", c0 + 1, r1 - 1)
        elif name == "West Pavilion 1":
            add("rug_green", c0 + 1, r0 + 1)
            add("sofa", c0 + 1, r0 + 1)
            add("armchair", c0 + 5, r0 + 3)
            add("side_table", c0 + 4, r0 + 3)
            add("plant", c1 - 1, r1 - 1)
        elif name == "West Pavilion 2":
            add("student_desk", c0 + 1, r0 + 1)
            add("student_desk", c0 + 4, r0 + 1)
            add("plant", c0 + 1, r1 - 1)
    return out


def apply_furniture(tmj, matrix_dir):
    """Insert two stacked layers above the walls: college_hall_rugs (under) and
    college_hall_furniture (on top), so a sofa/table can sit on a rug.
    Picture-only (not collision). Returns (placed, proposed)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {RUG_LAYER, FURN_LAYER})

    interior = college_interior_cells(tmj, matrix_dir)
    wl = next((L for L in tmj["layers"] if L.get("name") == WALL_LAYER), None)
    walls = {(i % W, i // W) for i, v in enumerate(wl["data"]) if v} if wl else set()
    walk = {(i % W, i // W) for i in interior} - walls

    sprites = load_sprites(tmj)
    sections = read_sections(tmj)
    rug_data = [0] * (W * H)
    furn_data = [0] * (W * H)
    prop_data = [0] * (W * H)
    rug_occ, furn_occ, prop_occ = set(), set(), set()
    proposed = placed = 0
    for name, c, r in _room_layouts(sections):
        proposed += 1
        if name in RUGS:  # under everything
            placed += _stamp(rug_data, rug_occ, sprites, name, c, r, walk, W)
        elif name in PROPS:  # over furniture (food/books sit on tables)
            placed += _stamp(prop_data, prop_occ, sprites, name, c, r, walk, W)
        else:
            placed += _stamp(furn_data, furn_occ, sprites, name, c, r, walk, W)

    base = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    rugs = _new_layer(RUG_LAYER, rug_data, W, H, base)
    furn = _new_layer(FURN_LAYER, furn_data, W, H, base + 1)
    props = _new_layer(PROP_LAYER, prop_data, W, H, base + 2)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], base + 3)
    names = [L.get("name") for L in tmj["layers"]]
    anchor = next(
        (n for n in (WALL_LAYER, FLOOR_LAYER, "entrance_floor") if n in names), None
    )
    at = names.index(anchor) + 1 if anchor else len(tmj["layers"])
    tmj["layers"][at:at] = [rugs, furn, props]  # rugs < furniture < props
    return placed, proposed


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--tmj",
        default=os.path.join(
            repo, "godot-generative-agents", "maps", "upenn_core_urban.tmj"
        ),
    )
    ap.add_argument(
        "--matrix",
        default=os.path.join(
            repo, "godot-generative-agents", "sim", "the_upenn", "matrix"
        ),
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.tmj) as fh:
        tmj = json.load(fh)
    floored = apply(tmj, args.matrix)
    print(f"college_hall_floor: painted {floored} interior cells (GID {FLOOR_GID})")
    walls, doors, removed = apply_walls(tmj, args.matrix)
    print(
        f"college_hall_walls: {walls} wall cells, {doors} doorway cells "
        f"({removed} removed to keep <=3 per 2x2)"
    )
    fplaced, fprop = apply_furniture(tmj, args.matrix)
    print(f"college_hall_furniture: placed {fplaced}/{fprop} sprites")
    if args.dry_run:
        return
    shutil.copy2(args.tmj, args.tmj + ".bak")
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")


if __name__ == "__main__":
    main()
