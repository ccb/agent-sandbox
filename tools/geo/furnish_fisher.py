#!/usr/bin/env python3
"""Furnish the Fisher Fine Arts (Furness) Library interior on the campus map.

Fisher is the named sector ``34`` (Fisher Fine Arts Library -- the Furness
building at 220 South 34th Street). ``add_entrances.py`` has already carved it into the
door-gated system: an ``entrance_floor`` cutaway, a one-tile perimeter wall, a
single door, and one lobby arena (``1034``). This tool layers the *detailed
interior* on top of that carve, the same way ``furnish_van_pelt.py`` does for
Van Pelt -- in its own ``fisher_*`` tile layers stacked above ``entrance_floor``
so ``add_entrances.py`` (which strips only ``entrance_*`` layers) leaves them
intact across runs.

    uv run python tools/geo/furnish_fisher.py            # paint floor + walls
    uv run python tools/geo/furnish_fisher.py --dry-run  # report, write nothing

Paints two layers, both clipped to the walkable interior (the sector-34
footprint minus its perimeter ring) so nothing lands on the brick ring:

* ``fisher_floor`` -- plank floor over the whole interior.
* ``fisher_walls`` -- the Path-1 interior partitions (wall_set_red thin-line
  edges) read off the WALLS spec + the hand-drawn ``fisher_arenas`` rects,
  each with a centered doorway. ``add_entrances.load_fisher_plan`` derives the
  matching collision/arena subdivision from the same spec, so picture and
  matrix stay in lock-step. Run order: ``add_entrances`` first (carve +
  entrance_floor + room arenas), then this tool (detailed layers above it).

Furniture is a later stage. Idempotent: strips its own layers before
re-inserting; backs up the .tmj first.
"""

import argparse
import json
import os
import shutil

from add_entrances import split_footprint

FISHER_SECTOR = "34"  # Fisher Fine Arts Library (Furness, 220 S 34th St)
FISHER_LOBBY = "1034"  # INTERIOR_ARENA_BASE (1000) + sector 34
FLOOR_GID = 589  # interior_franuka tile (col 6,row 2) = plank_floor_light;
# the same floor Van Pelt's west/east wings use.
FLOOR_LAYER = "fisher_floor"

# wall_set_red is the interior_franuka 3x3 thin-line autotile at col0/row0
# (firstgid 519): each edge piece is a ~5px maroon strip on one side of its cell,
# with a transparent backing, so it must sit on its OWN layer above the floor.
WALL_T = 520  # top edge   (strip along the cell's top)
WALL_B = 584  # bottom edge
WALL_L = 551  # left edge
WALL_R = 553  # right edge
WALL_LAYER = "fisher_walls"
EDGE_GID = {"N": WALL_T, "S": WALL_B, "W": WALL_L, "E": WALL_R}

# Path-1 interior partitions: rooms are islands separated by circulation floor;
# each entry walls one edge of a section (the side facing a nearby section) with
# a centered doorway gap so the room stays reachable. Read off fisher_arenas.
WALLS = [
    ("Fisher Core Reading Section", "S", 2),  # faces Seng Tee Lee, below
    ("Fisher Rare Books Library", "W", 2),  # faces Seng Tee Lee, to the west
    ("Staff Office", "N", 2),  # faces Computing & Printing, above
]

RUG_LAYER = "fisher_rugs"  # rugs sit on their own layer UNDER the furniture
FURN_LAYER = "fisher_furniture"  # so a table/sofa can sit on a rug (franuka idiom)
RUGS = {"rug_red", "rug_blue", "rug_orange", "rug_green", "rug_magenta", "rug_cyan"}
RUNNER_RUG = "rug_red"  # rug used to fill the hand-drawn connecting boxes
OWN_LAYERS = [FLOOR_LAYER, WALL_LAYER, RUG_LAYER, FURN_LAYER]

# Tileset firstgids + column counts, to turn a catalog (sheet,col,row) into a GID
# and to walk a multi-tile sprite's sub-tiles.
_FIRSTGID = {"franuka": 519, "school": 1543, "bath": 1799, "kenney": 1}
_SHEET_COLS = {"franuka": 32, "school": 16, "bath": 16, "kenney": 27}


def read_flat(path):
    """Read a matrix maze CSV (flat, ', '-joined, row-major) into a list."""
    with open(path) as fh:
        return fh.read().strip().split(", ")


def fisher_interior_cells(tmj, matrix_dir):
    """Walkable interior of Fisher as a set of flat indices: the sector-34
    footprint (sector cells painted into entrance_floor) minus its 1-tile
    perimeter ring. Computed like furnish_van_pelt -- from the footprint, not
    the arena ids -- so it stays correct after add_entrances subdivides the
    interior into per-room arenas (13400+), and a floor/wall tile still never
    lands on the perimeter brick ring."""
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
        (i % W, i // W) for i, s in enumerate(sector) if s == FISHER_SECTOR
    } & entrance
    _perimeter, interior = split_footprint(foot, W, H)
    return {y * W + x for (x, y) in interior}


def _obj_rect(o):
    c0 = round(o["x"] / 16)
    r0 = round(o["y"] / 16)
    c1 = round((o["x"] + o["width"]) / 16) - 1
    r1 = round((o["y"] + o["height"]) / 16) - 1
    return c0, r0, c1, r1


def _fisher_arenas(tmj):
    return next(
        (
            L
            for L in tmj["layers"]
            if L.get("name") == "fisher_arenas" and L.get("type") == "objectgroup"
        ),
        None,
    )


def read_sections(tmj):
    """Room name -> (c0, r0, c1, r1) inclusive tile rect, from fisher_arenas.

    Objects whose name contains 'rug' are rug-fill regions, NOT rooms, so they
    are excluded here -- keeping them out of the WALLS spec and out of
    add_entrances' arena subdivision (they must never become arenas)."""
    fa = _fisher_arenas(tmj)
    secs = {}
    if not fa:
        return secs
    for o in fa["objects"]:
        name = o.get("name") or ""
        if not name or "rug" in name.lower():
            continue
        secs[name] = _obj_rect(o)
    return secs


def read_rug_boxes(tmj):
    """The rug-fill regions: every fisher_arenas object whose name contains
    'rug'. Returns a list of (name, (c0, r0, c1, r1))."""
    fa = _fisher_arenas(tmj)
    if not fa:
        return []
    return [
        (o["name"], _obj_rect(o))
        for o in fa["objects"]
        if "rug" in (o.get("name") or "").lower()
    ]


def _edge_cells(rect, side):
    """The cells along one edge of a section rect, ordered along the run."""
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
    """Yield (side, (x, y)) for every partition-wall cell, doorway gaps excluded.

    The single definition of Fisher's interior walls: it reads off the WALLS
    spec and the section rects, keeping only cells on the walkable interior
    (flat indices in `interior_idx`). Shared by the picture (apply_walls) and
    the matrix (add_entrances.load_fisher_plan), so both derive identical walls
    from fisher_arenas regardless of which tool runs first."""
    for name, side, door_w in WALLS:
        if name not in sections:
            continue
        run = [
            (c, r)
            for (c, r) in _edge_cells(sections[name], side)
            if (r * W + c) in interior_idx
        ]
        n = len(run)
        d0 = max(0, (n - door_w) // 2)  # centered doorway gap
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
    """Insert the fisher_floor layer above entrance_floor, painted only on the
    walkable interior. Returns the count of floored cells."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, set(OWN_LAYERS))

    interior = fisher_interior_cells(tmj, matrix_dir)
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
    """Insert the fisher_walls layer (above fisher_floor) with the Path-1
    partition walls. Each wall hugs one section edge, only on walkable interior
    cells, with a centered doorway gap. Returns (wall_cells, doorway_cells)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {WALL_LAYER})

    interior = fisher_interior_cells(tmj, matrix_dir)
    sections = read_sections(tmj)
    data = [0] * (W * H)
    placed = 0
    for side, (c, r) in iter_wall_cells(sections, interior, W):
        data[r * W + c] = EDGE_GID[side]
        placed += 1
    # doorway cells = edge cells on the interior that were left as gaps
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


def load_sprites():
    """catalog name -> (top_left_gid, w, h, sheet) for every catalogued sprite."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "furniture_catalog.json")) as fh:
        cat = json.load(fh)
    out = {}
    for name, v in cat["objects"].items():
        if not (isinstance(v, dict) and v.get("sheet") in _FIRSTGID):
            continue
        sheet = v["sheet"]
        gid = _FIRSTGID[sheet] + v["row"] * _SHEET_COLS[sheet] + v["col"]
        out[name] = (gid, v["w"], v["h"], sheet)
    return out


def _stamp(data, occ, sprites, name, c, r, walk, W):
    """Place a whole multi-tile sprite with its top-left at (c, r). Refuses (and
    changes nothing) unless every one of its w*h cells is walkable floor and
    unoccupied -- the cardinal rule: never place part of a sprite. Returns bool."""
    gid, w, h, sheet = sprites[name]
    cols = _SHEET_COLS[sheet]
    cells = [(c + dx, r + dy) for dy in range(h) for dx in range(w)]
    if any((x, y) not in walk or (x, y) in occ for (x, y) in cells):
        return False
    for dy in range(h):
        for dx in range(w):
            x, y = c + dx, r + dy
            data[y * W + x] = gid + dy * cols + dx
            occ.add((x, y))
    return True


def _fill_rug(rug_data, sprites, name, box, walk, W):
    """Nine-slice a rug across a bounding box so it reads as one continuous rug
    of any size: the 3x3 rug sprite supplies corner/edge/center tiles. Only
    walkable cells are painted. Returns the count of cells filled."""
    gid, w, h, sheet = sprites[name]  # rug is 3x3; gid is its top-left
    cols = _SHEET_COLS[sheet]
    c0, r0, c1, r1 = box
    filled = 0
    for r in range(r0, r1 + 1):
        dy = 0 if r == r0 else (2 if r == r1 else 1)
        for c in range(c0, c1 + 1):
            if (c, r) not in walk:
                continue
            dx = 0 if c == c0 else (2 if c == c1 else 1)
            rug_data[r * W + c] = gid + dy * cols + dx
            filled += 1
    return filled


def _room_layouts(sections):
    """Per-room furniture placements as (name, col, row) of each sprite's
    top-left. Coordinates are derived from each section rect and follow the
    franuka idiom (rug centerpiece + table + armchairs; bookshelves along a
    wall; fireplace against a wall; plants in corners). Placements that would
    clip a wall/another sprite are silently skipped by _stamp, so this can
    over-propose; the render shows what actually landed."""
    out = []
    add = lambda *t: out.append(t)

    def shelf_row(c0, c1, r, name, step=3):
        for c in range(c0, c1 - 1, step):
            add(name, c, r)

    def table_set(
        c,
        r,
        table="dining_table",
        rug="rug_red",
        left="armchair",
        right="armchair_orange",
    ):
        # rug 3x3, table 2x3 on the rug's left two columns, an armchair each side
        add(rug, c, r)
        add(table, c, r)
        add(right, c + 2, r + 1)
        add(left, c - 1, r + 1)

    for name, (c0, r0, c1, r1) in sections.items():
        if name == "Seng Tee Lee Reading Room":
            shelf_row(
                c0 + 1, c1 - 3, r0 + 1, "bookshelf_wood_books"
            )  # shelves along top
            add("fireplace", c1 - 2, r0 + 1)  # hearth, top-right
            add("plant", c0, r0 + 1)
            add("plant", c1 - 1, r1 - 1)
            # two columns of reading sets (rug + dining table + armchairs) down the hall
            for rr in (r0 + 7, r0 + 13, r0 + 19, r0 + 24):
                table_set(c0 + 4, rr)
                table_set(c0 + 11, rr)
            # candelabras down the central aisle between the two columns
            for rr in (r0 + 8, r0 + 14, r0 + 20, r0 + 26):
                add("candelabra", c0 + 8, rr)
            add("candelabra", c0 + 1, r1 - 2)
        elif name == "Fisher Core Reading Section":
            shelf_row(
                c0 + 1, c1 - 1, r0, "bookshelf_wood_books"
            )  # shelves on back wall
            # the dome is only ~5 rows tall under the shelves; use a small set
            for k, cc in enumerate(range(c0 + 4, c1 - 2, 5)):
                add("rug_orange", cc, r0 + 3)
                add("round_table_small", cc + 1, r0 + 4)
                add("armchair", cc, r0 + 4)
                add("armchair_orange", cc + 2, r0 + 4)
        elif name == "Fisher Rare Books Library":
            # three packed columns of stacks (no tables) -- a dense rare-books room
            for r in range(r0 + 1, r1 - 2, 3):
                add("bookshelf_tan", c0 + 1, r)  # left wall
                add("bookshelf_tan", c0 + 4, r)  # middle stack
                add("cabinet_display", c1 - 1, r)  # right wall (display cabinets)
        elif name == "Computing & Printing":
            for r in (r0 + 2, r0 + 7):  # rows of study desks
                for c in range(c0 + 2, c1 - 1, 3):
                    add("student_desk_quill", c, r)
                    add("books_green", c, r - 1)
            add("plant", c0 + 1, r1 - 1)
        elif name == "Ross Gallery":
            add("rug_magenta", c0 + 2, r0 + 1)
            add("sofa", c0 + 2, r0 + 1)
            add("cabinet_display", c0 + 1, r1 - 3)
            add("plant_large", c1 - 1, r0 + 1)
            add("candelabra", c0 + 1, r0 + 6)
            add("plant", c1 - 1, r1 - 1)
        elif name == "Staff Office":
            add("fireplace", c0 + 1, r0 + 1)  # hearth on the left
            add("plant", c0 + 4, r0 + 1)
            table_set(c0 + 8, r0 + 2, rug="rug_green")
            table_set(
                c0 + 16,
                r0 + 2,
                rug="rug_blue",
                left="armchair_red",
                right="armchair_green",
            )
            add("crate", c1 - 1, r1 - 1)
            add("crate", c1 - 2, r1 - 1)
            add("crate", c1 - 1, r1 - 2)
    return out


def apply_furniture(tmj, matrix_dir):
    """Insert two stacked layers above fisher_walls: fisher_rugs (floor rugs)
    and fisher_furniture (everything else) on top, so a table/sofa can sit on a
    rug. Picture-only: furniture is not collision (mirrors Van Pelt). Rugs don't
    block furniture; furniture can't overlap other furniture. Returns
    (placed, proposed)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {RUG_LAYER, FURN_LAYER})

    interior = fisher_interior_cells(tmj, matrix_dir)
    wl = next((L for L in tmj["layers"] if L.get("name") == WALL_LAYER), None)
    walls = {(i % W, i // W) for i, v in enumerate(wl["data"]) if v} if wl else set()
    walk = {(i % W, i // W) for i in interior} - walls  # floor a sprite may cover

    sprites = load_sprites()
    sections = read_sections(tmj)
    rug_data = [0] * (W * H)
    furn_data = [0] * (W * H)
    rug_occ, furn_occ = set(), set()
    proposed = placed = 0
    for name, c, r in _room_layouts(sections):
        proposed += 1
        if name not in sprites:
            continue
        if name in RUGS:
            ok = _stamp(rug_data, rug_occ, sprites, name, c, r, walk, W)
        else:
            ok = _stamp(furn_data, furn_occ, sprites, name, c, r, walk, W)
        placed += ok

    # connecting runners: fill each hand-drawn rug box with one continuous rug
    rug_cells = 0
    for _name, box in read_rug_boxes(tmj):
        rug_cells += _fill_rug(rug_data, sprites, RUNNER_RUG, box, walk, W)

    base = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    rugs = _new_layer(RUG_LAYER, rug_data, W, H, base)
    furn = _new_layer(FURN_LAYER, furn_data, W, H, base + 1)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], base + 2)
    names = [L.get("name") for L in tmj["layers"]]
    anchor = next(
        (n for n in (WALL_LAYER, FLOOR_LAYER, "entrance_floor") if n in names), None
    )
    at = names.index(anchor) + 1 if anchor else len(tmj["layers"])
    tmj["layers"][at:at] = [rugs, furn]  # rugs below, furniture above
    return placed, proposed, rug_cells


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
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
    print(f"fisher_floor: painted {floored} interior cells (GID {FLOOR_GID})")
    walls, doors = apply_walls(tmj, args.matrix)
    print(
        f"fisher_walls: {walls} wall cells, {doors} doorway cells "
        f"({len(WALLS)} partitions)"
    )
    fplaced, fprop, rugcells = apply_furniture(tmj, args.matrix)
    print(
        f"fisher_furniture: placed {fplaced}/{fprop} sprites; "
        f"{rugcells} runner-rug cells"
    )
    if args.dry_run:
        return
    shutil.copy2(args.tmj, args.tmj + ".bak")
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")


if __name__ == "__main__":
    main()
