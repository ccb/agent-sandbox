#!/usr/bin/env python3
"""Furnish the Meyerson Hall interior (Weitzman School of Design commons).

Meyerson is the carved sector ``21`` (``UPenn:Meyerson Hall``). ``add_entrances.py``
has already carved it into the door-gated system: an ``entrance_floor`` cutaway,
a one-tile perimeter wall, a door, and one lobby arena (``1021``). This tool
layers the *detailed interior* on top of that carve, the same way
``furnish_fisher.py`` / ``furnish_van_pelt.py`` do -- in its own ``meyerson_*``
tile layers stacked above ``entrance_floor`` so ``add_entrances.py`` (which
strips only ``entrance_*`` layers) leaves them intact across runs.

    uv run python tools/geo/furnish_meyerson.py            # paint the floor
    uv run python tools/geo/furnish_meyerson.py --dry-run  # report, write nothing

STAGE 1 (this version): the floor only. It fills the walkable interior (the
sector-21 footprint minus its perimeter ring), so a floor tile can never land
on the brick ring or outside the building. Walls + furniture follow once the
room bounding boxes are drawn (a ``meyerson_arenas`` object layer).

Idempotent: strips its own layers before re-inserting; backs up the .tmj first.
"""

import argparse
import json
import os
import shutil

from add_entrances import split_footprint

MEYERSON_SECTOR = "21"  # UPenn:Meyerson Hall
MEYERSON_LOBBY = "1021"  # INTERIOR_ARENA_BASE (1000) + sector 21
FLOOR_GID = 627  # interior_franuka floor_stone_hex (col 12,row 3) -- grey
# hex stone, the cooler institutional floor for a commons.
FLOOR_LAYER = "meyerson_floor"
ARENAS_LAYER = "meyerson_arenas"  # hand-drawn room boxes

# wall_set_red thin-line edge tiles (interior_franuka 3x3 autotile at col0/row0).
WALL_T, WALL_B, WALL_L, WALL_R = 520, 584, 551, 553
WALL_LAYER = "meyerson_walls"
EDGE_GID = {"N": WALL_T, "S": WALL_B, "W": WALL_L, "E": WALL_R}

# Partition the central Lounge from its three close neighbors, each with a
# centered doorway; Lounge stays open to the south (Gallery) as circulation.
WALLS = [
    ("Lounge", "N", 2),  # vs Cafe (above)
    ("Lounge", "W", 2),  # vs West Studio (left)
    ("Lounge", "E", 2),  # vs East Studio (right)
    ("West Studio", "S", 2),  # vs South Gallery (below) -- studio's own edge so it
    #                            doesn't cross the open Lounge<->Gallery boundary
    ("East Offices", "W", 2),  # vs South Gallery (to the west)
]

RUG_LAYER = "meyerson_rugs"  # rugs under furniture (a sofa/table sits on a rug)
FURN_LAYER = "meyerson_furniture"  # multi-cell furniture + seating
PROP_LAYER = "meyerson_props"  # small 1x1 items that sit ON furniture (cafe food)
RUGS = {"rug_red", "rug_blue", "rug_orange", "rug_green", "rug_magenta", "rug_cyan"}
PROPS = {
    "basket_fruit",
    "food_sausage",
    "food_ham",
    "food_fish",
    "food_salad",
    "food_bowl",
    "mug",
    "book_stack_red",
    "books_green",
    "quill_ink",
    "inkwell",
    "scroll",
}
OWN_LAYERS = [FLOOR_LAYER, WALL_LAYER, RUG_LAYER, FURN_LAYER, PROP_LAYER]


def read_flat(path):
    """Read a matrix maze CSV (flat, ', '-joined, row-major) into a list."""
    with open(path) as fh:
        return fh.read().strip().split(", ")


def meyerson_interior_cells(tmj, matrix_dir):
    """Walkable interior of Meyerson as a set of flat indices: the sector-21
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
        (i % W, i // W) for i, s in enumerate(sector) if s == MEYERSON_SECTOR
    } & entrance
    _perimeter, interior = split_footprint(foot, W, H)
    return {y * W + x for (x, y) in interior}


def read_sections(tmj):
    """Room name -> (c0, r0, c1, r1) from meyerson_arenas. Objects whose name
    contains 'rug' are rug-fill regions, not rooms, and are excluded."""
    fa = next(
        (
            L
            for L in tmj["layers"]
            if L.get("name") == ARENAS_LAYER and L.get("type") == "objectgroup"
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


def _edge_cells(rect, side):
    c0, r0, c1, r1 = rect
    if side == "N":
        return [(c, r0) for c in range(c0, c1 + 1)]
    if side == "S":
        return [(c, r1) for c in range(c0, c1 + 1)]
    if side == "W":
        return [(c0, r) for r in range(r0, r1 + 1)]
    if side == "E":
        return [(c1, r) for r in range(r0, r1 + 1)]
    raise ValueError(side)


def iter_wall_cells(sections, interior_idx, W):
    """Yield (side, (x, y)) for every partition-wall cell (doorway gaps excluded),
    keeping only cells on the walkable interior."""
    for name, side, door_w in WALLS:
        if name not in sections:
            continue
        run = [
            (c, r)
            for (c, r) in _edge_cells(sections[name], side)
            if (r * W + c) in interior_idx
        ]
        n = len(run)
        d0 = max(0, (n - door_w) // 2)
        for k, (c, r) in enumerate(run):
            if d0 <= k < d0 + door_w:
                continue
            yield side, (c, r)


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
    """Insert the meyerson_floor layer above entrance_floor, painted only on the
    walkable interior. Returns the count of floored cells."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, set(OWN_LAYERS))

    interior = meyerson_interior_cells(tmj, matrix_dir)
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


def apply_walls(tmj, matrix_dir):
    """Insert the meyerson_walls layer (above meyerson_floor) with the Lounge
    partitions, only on walkable interior cells, each with a doorway gap.
    Returns (wall_cells, doorway_cells)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {WALL_LAYER})

    interior = meyerson_interior_cells(tmj, matrix_dir)
    sections = read_sections(tmj)
    data = [0] * (W * H)
    placed = 0
    for side, (c, r) in iter_wall_cells(sections, interior, W):
        data[r * W + c] = EDGE_GID[side]
        placed += 1
    edge_total = sum(
        1
        for name, side, _dw in WALLS
        if name in sections
        for (c, r) in _edge_cells(sections[name], side)
        if (r * W + c) in interior
    )
    doors = edge_total - placed

    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    walls = _new_layer(WALL_LAYER, data, W, H, next_id)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 1)
    names = [L.get("name") for L in tmj["layers"]]
    anchor = FLOOR_LAYER if FLOOR_LAYER in names else "entrance_floor"
    at = names.index(anchor) + 1 if anchor in names else len(tmj["layers"])
    tmj["layers"][at:at] = [walls]
    return placed, doors


def load_sprites(tmj):
    """catalog name -> (top_left_gid, w, h, sheet_columns). GIDs are resolved
    against THIS map's tilesets (matched by image filename), so expansion sheets
    (alchemy/bedroom/clockwork/music) work as long as they're in the .tmj."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "furniture_catalog.json")) as fh:
        cat = json.load(fh)
    sheet_file = {k: v["file"] for k, v in cat["sheets"].items()}
    img = {
        t["image"]: (t["firstgid"], t["columns"])
        for t in tmj["tilesets"]
        if "image" in t
    }
    out = {}
    for name, v in cat["objects"].items():
        if not (isinstance(v, dict) and v.get("sheet") in sheet_file):
            continue
        f = sheet_file[v["sheet"]]
        if f not in img:
            continue
        fg, cols = img[f]
        out[name] = (fg + v["row"] * cols + v["col"], v["w"], v["h"], cols)
    return out


def _stamp(data, occ, sprites, name, c, r, walk, W):
    """Place a whole multi-tile sprite (top-left at c,r) only if every cell is
    walkable floor and unoccupied -- the cardinal rule. Returns bool."""
    if name not in sprites:
        return False
    gid, w, h, cols = sprites[name]
    cells = [(c + dx, r + dy) for dy in range(h) for dx in range(w)]
    if any((x, y) not in walk or (x, y) in occ for (x, y) in cells):
        return False
    for dy in range(h):
        for dx in range(w):
            data[(r + dy) * W + (c + dx)] = gid + dy * cols + dx
            occ.add((c + dx, r + dy))
    return True


def _fill_rug(rug_d, sprites, name, box, walk, W):
    """Nine-slice a rug across a bounding box so it reads as one continuous rug
    of any size (the 3x3 rug supplies corner/edge/center tiles). Only walkable
    cells are painted. Returns the count of cells filled."""
    if name not in sprites:
        return 0
    gid, _w, _h, cols = sprites[name]
    c0, r0, c1, r1 = box
    n = 0
    for r in range(r0, r1 + 1):
        dy = 0 if r == r0 else (2 if r == r1 else 1)
        for c in range(c0, c1 + 1):
            if (c, r) not in walk:
                continue
            dx = 0 if c == c0 else (2 if c == c1 else 1)
            rug_d[r * W + c] = gid + dy * cols + dx
            n += 1
    return n


def _box_counter(furn_d, sprites, rect, walk, W):
    """Wrap a section rect in a fully-closed ring of counters (no gaps). The
    counter is 1x2, so an odd-height wall can't be tiled without overlap; we
    cover EVERY walkable perimeter cell with a whole counter, letting a counter
    overlap a neighbor by one cell where needed (still a whole sprite, never a
    partial one). Counters are oriented to stay inside the box. Returns count."""
    if "counter" not in sprites:
        return 0
    gid, _w, _h, cols = sprites["counter"]
    c0, r0, c1, r1 = rect
    mid = (r0 + r1) // 2
    peri = (
        [(c, r0) for c in range(c0, c1 + 1)]
        + [(c, r1) for c in range(c0, c1 + 1)]
        + [(c0, r) for r in range(r0 + 1, r1)]
        + [(c1, r) for r in range(r0 + 1, r1)]
    )
    covered, n = set(), 0
    for c, r in peri:
        if (c, r) in covered or (c, r) not in walk:
            continue
        tr = r if r <= mid else r - 1  # keep the 1x2 inside the box
        if (c, tr) not in walk or (c, tr + 1) not in walk:
            tr = r - 1 if (c, r - 1) in walk else r
        if (c, tr) in walk and (c, tr + 1) in walk:
            furn_d[tr * W + c] = gid
            furn_d[(tr + 1) * W + c] = gid + cols
            covered |= {(c, tr), (c, tr + 1)}
            n += 1
    return n


def _room_layouts(sections):
    """Per-room furniture placements as (name, col, row) of each sprite's
    top-left, in the student-commons idiom. Over-proposes; _stamp skips anything
    that would clip a wall or overlap."""
    out = []
    add = lambda *t: out.append(t)
    for name, (c0, r0, c1, r1) in sections.items():
        if name == "Cafe":
            # counter runs along the top and bottom of the cafe (no side columns)
            for c in range(c0, c1 + 1):
                add("counter", c, r0)  # back counter
                add("counter", c, r1 - 1)  # front counter
            FOODS = [
                "basket_fruit",
                "food_ham",
                "food_salad",
                "food_bowl",
                "food_fish",
                "food_sausage",
            ]
            for k, c in enumerate(range(c0 + 1, c1, 2)):  # food on the top counters
                add(FOODS[k % len(FOODS)], c, r0)
            # a dining-hall table inside the box, with food on it
            add("dining_table", c0 + 4, r0 + 6)
            add("chair_wood", c0 + 3, r0 + 7)
            add("chair_wood", c0 + 7, r0 + 7)
            add("food_salad", c0 + 4, r0 + 6)
            add("mug", c0 + 5, r0 + 6)
            add("clockwork_lamp_floor", c0 + 1, r1 - 3)
        elif name == "Lounge":
            # two rows of seating (north + south) to fill the lounge: cyan rugs
            # with sofas, and dining-hall tables with chairs + food on top
            for rr in (r0 + 1, r0 + 6):
                for cc in (c0 + 1, c0 + 13):
                    add("rug_cyan", cc, rr)
                    add("sofa", cc, rr)
                for cc in (c0 + 6, c0 + 10):
                    add("dining_table", cc, rr)
                    add("chair_wood", cc - 1, rr + 1)
                    add("chair_wood", cc + 2, rr + 1)
                    add("food_bowl", cc, rr)
                    add("mug", cc + 1, rr)
        elif name == "West Studio":
            for rr in (r0 + 1, r0 + 7, r0 + 13):  # studio worktables + chairs
                add("dining_table", c0 + 2, rr)
                add("chair_wood", c0 + 1, rr + 1)
                add("chair_wood", c0 + 5, rr + 1)
            add("plant", c0, r1 - 1)
        elif name == "East Studio":
            for rr in (r0 + 1, r0 + 7, r0 + 13):
                add("dining_table", c0 + 4, rr)
                add("chair_wood", c0 + 3, rr + 1)
                add("chair_wood", c0 + 7, rr + 1)
            add("plant", c1 - 1, r0 + 1)
        elif name == "East Offices":
            for rr in (r0 + 1, r0 + 5):  # office desks
                add("teacher_desk", c0 + 2, rr)
                add("student_desk", c0 + 6, rr)
            add("plant", c1 - 1, r1 - 1)
        elif name == "South Gallery":
            # a gallery: framed paintings on the wall + display cases + plants
            add("painting_moon", c0 + 2, r0)
            add("painting_moon_light", c0 + 11, r0)
            add("cabinet_display", c0 + 18, r0 + 1)
            add("cabinet_display", c0 + 22, r0 + 1)
            add("plant_large", c0 + 7, r1 - 2)
            add("plant", c0 + 16, r1 - 1)
    return out


def apply_furniture(tmj, matrix_dir):
    """Insert three stacked layers above the walls: meyerson_rugs (under),
    meyerson_furniture, and meyerson_props (small items on top, e.g. cafe food).
    Picture-only -- furniture is not collision. Returns (placed, proposed)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {RUG_LAYER, FURN_LAYER, PROP_LAYER})

    interior = meyerson_interior_cells(tmj, matrix_dir)
    wl = next((L for L in tmj["layers"] if L.get("name") == WALL_LAYER), None)
    walls = {(i % W, i // W) for i, v in enumerate(wl["data"]) if v} if wl else set()
    walk = {(i % W, i // W) for i in interior} - walls

    sprites = load_sprites(tmj)
    sections = read_sections(tmj)
    rug_d, furn_d, prop_d = ([0] * (W * H) for _ in range(3))
    rug_occ, furn_occ, prop_occ = set(), set(), set()
    proposed = placed = 0
    for name, c, r in _room_layouts(sections):
        proposed += 1
        if name in RUGS:
            placed += _stamp(rug_d, rug_occ, sprites, name, c, r, walk, W)
        elif name in PROPS:
            placed += _stamp(prop_d, prop_occ, sprites, name, c, r, walk, W)
        else:
            placed += _stamp(furn_d, furn_occ, sprites, name, c, r, walk, W)

    # (cafe counters are top/bottom-only for now; see _room_layouts. The
    # _box_counter helper for a fully-closed ring is kept but unused.)

    # a single long horizontal runner rug filling the South Gallery floor
    rug_cells = 0
    sg = sections.get("South Gallery")
    if sg:
        gc0, gr0, gc1, gr1 = sg
        rug_cells = _fill_rug(
            rug_d, sprites, "rug_red", (gc0 + 1, gr0 + 5, gc1 - 1, gr0 + 7), walk, W
        )

    base = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    layers = [
        _new_layer(RUG_LAYER, rug_d, W, H, base),
        _new_layer(FURN_LAYER, furn_d, W, H, base + 1),
        _new_layer(PROP_LAYER, prop_d, W, H, base + 2),
    ]
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], base + 3)
    names = [L.get("name") for L in tmj["layers"]]
    anchor = next(
        (n for n in (WALL_LAYER, FLOOR_LAYER, "entrance_floor") if n in names), None
    )
    at = names.index(anchor) + 1 if anchor else len(tmj["layers"])
    tmj["layers"][at:at] = layers
    return placed, proposed, rug_cells


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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.tmj) as fh:
        tmj = json.load(fh)
    floored = apply(tmj, args.matrix)
    print(f"meyerson_floor: painted {floored} interior cells (GID {FLOOR_GID})")
    walls, doors = apply_walls(tmj, args.matrix)
    print(
        f"meyerson_walls: {walls} wall cells, {doors} doorway cells "
        f"({len(WALLS)} partitions)"
    )
    fplaced, fprop, rugcells = apply_furniture(tmj, args.matrix)
    print(
        f"meyerson_furniture: placed {fplaced}/{fprop} sprites; "
        f"{rugcells} gallery-rug cells"
    )
    if args.dry_run:
        return
    shutil.copy2(args.tmj, args.tmj + ".bak")
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")


if __name__ == "__main__":
    main()
