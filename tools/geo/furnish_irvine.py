#!/usr/bin/env python3
"""Furnish the Irvine Auditorium interior (the octagonal performance hall).

Irvine is the carved sector ``15`` (``UPenn:Irvine Auditorium``).
``add_entrances.py`` has already carved it into the door-gated system: an
``entrance_floor`` cutaway, a one-tile perimeter wall, a door, and one lobby
arena (``1015``). This tool layers the *detailed interior* on top of that
carve, the same way ``furnish_houston.py`` / ``furnish_fisher.py`` do -- in its
own ``irvine_*`` tile layers stacked above ``entrance_floor`` so
``add_entrances.py`` (which strips only ``entrance_*`` layers) leaves them
intact across runs.

    uv run python tools/geo/furnish_irvine.py            # paint the floor
    uv run python tools/geo/furnish_irvine.py --dry-run  # report, write nothing

STAGE 1 (this version): the floor only. It fills the walkable interior (the
sector-15 footprint minus its perimeter ring), so a floor tile can never land
on the brick ring or outside the building. Walls + furniture follow once the
room bounding boxes are drawn (an ``irvine_arenas`` object layer).

Idempotent: strips its own layers before re-inserting; backs up the .tmj first.
"""
import argparse
import json
import os
import re
import shutil

from add_entrances import split_footprint

IRVINE_SECTOR = "15"       # UPenn:Irvine Auditorium
IRVINE_LOBBY = "1015"      # INTERIOR_ARENA_BASE (1000) + sector 15
FLOOR_GID = 589            # interior_franuka plank_floor_light (col 6,row 2) -- the
                           # light wood plank Van Pelt/Fisher/Houston use.
FLOOR_LAYER = "irvine_floor"

# wall_set_red thin-line edges (interior_franuka 3x3 autotile at col0/row0,
# firstgid 519): a ~5px maroon strip on one side of the cell.
WALL_R = 553   # right edge
WALL_B = 584   # bottom edge
WALL_BR = 585  # bottom-right corner (cell needs both a right and bottom strip)
WALL_LAYER = "irvine_walls"
DOOR_W = 2     # centered doorway gap, in cells, per partition segment
WALL_SET = {WALL_R, WALL_B, WALL_BR}

OWN_LAYERS = [FLOOR_LAYER, WALL_LAYER]


def read_flat(path):
    """Read a matrix maze CSV (flat, ', '-joined, row-major) into a list."""
    with open(path) as fh:
        return fh.read().strip().split(", ")


def irvine_interior_cells(tmj, matrix_dir):
    """Walkable interior of Irvine as a set of flat indices: the sector-15
    footprint (sector cells painted into entrance_floor) minus its 1-tile
    perimeter ring. Computed from the footprint, not the arena ids, so it stays
    correct after add_entrances subdivides the interior into per-room arenas."""
    W, H = tmj["width"], tmj["height"]
    ef = next((L for L in tmj["layers"]
               if L.get("name") == "entrance_floor" and L.get("type") == "tilelayer"), None)
    entrance = ({(i % W, i // W) for i, v in enumerate(ef["data"]) if v}
                if ef else set())
    sector = read_flat(os.path.join(matrix_dir, "maze", "sector_maze.csv"))
    foot = {(i % W, i // W) for i, s in enumerate(sector)
            if s == IRVINE_SECTOR} & entrance
    _perimeter, interior = split_footprint(foot, W, H)
    return {y * W + x for (x, y) in interior}


def read_sections(tmj):
    """Room name -> (c0, r0, c1, r1) inclusive tile rect, from the hand-drawn
    irvine_arenas object layer. Objects whose name contains 'rug' are rug-fill
    regions, not rooms, so they are excluded (consistent with the others)."""
    fa = next((L for L in tmj["layers"]
               if L.get("name") == "irvine_arenas" and L.get("type") == "objectgroup"), None)
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


def _group(name):
    """Room-group name: boxes differing only by a trailing number are one room
    (e.g. 'Stage 1'/'Stage 2'/'Stage 3' -> 'Stage', 'West Foyer 1' -> 'West
    Foyer'). Used so sub-boxes of one area get no wall between them."""
    return re.sub(r"\s*\d+$", "", name).strip() or name


def _enforce_max3_per_2x2(data, W, H):
    """Invariant: no 2x2 block may hold 4 wall_set_red cells (always a parallel
    double wall). Scan every 2x2 window and drop a wall until none has 4."""
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
        "type": "tilelayer", "name": name, "id": layer_id,
        "x": 0, "y": 0, "width": W, "height": H,
        "opacity": 1, "visible": True, "data": data,
    }


def apply(tmj, matrix_dir):
    """Insert the irvine_floor layer above entrance_floor, painted only on the
    walkable interior. Returns the count of floored cells."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, set(OWN_LAYERS))

    interior = irvine_interior_cells(tmj, matrix_dir)
    data = [0] * (W * H)
    for i in interior:
        data[i] = FLOOR_GID

    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    floor = _new_layer(FLOOR_LAYER, data, W, H, next_id)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 1)

    names = [L.get("name") for L in tmj["layers"]]
    at = names.index("entrance_floor") + 1 if "entrance_floor" in names else len(tmj["layers"])
    tmj["layers"][at:at] = [floor]
    return len(interior)


def _wall_data(tmj, interior, W, H):
    """Compute the irvine_walls tile data from the room boxes: auto-enclose every
    boundary where a room cell meets a different room or open circulation (the
    building perimeter already blocks), close 1-cell circulation gaps so abutting
    rooms share a single boundary, leave a centered doorway per partition, and
    enforce <=3 wall cells per 2x2. `interior` is a set of flat indices. Returns
    (data, doors, removed). Shared by the picture (apply_walls) and the matrix."""
    import collections

    sections = read_sections(tmj)
    cell2room = {}
    for nm, (c0, r0, c1, r1) in sections.items():
        grp = _group(nm)  # 'Stage 1/2/3' -> 'Stage', so no wall between sub-boxes
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                idx = r * W + c
                if idx in interior and idx not in cell2room:  # first box wins overlaps
                    cell2room[idx] = grp

    # close 1-cell circulation gaps so abutting rooms share one boundary
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

    vert = collections.defaultdict(list)   # (c, pair) -> rows; wall on (c,r) right edge
    horiz = collections.defaultdict(list)  # (r, pair) -> cols; wall on (c,r) bottom edge
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

    removed = _enforce_max3_per_2x2(data, W, H)
    return data, doors, removed


def irvine_wall_cells(tmj, interior, W, H):
    """The partition-wall cell set {(x, y)} -- exactly the cells apply_walls
    paints. Used by add_entrances.load_irvine_plan to derive collision from the
    room boxes, so matrix and picture stay in lock-step."""
    data, _doors, _removed = _wall_data(tmj, interior, W, H)
    return {(i % W, i // W) for i, v in enumerate(data) if v}


def apply_walls(tmj, matrix_dir):
    """Insert the irvine_walls layer (above irvine_floor) from _wall_data.
    Returns (wall_cells, doorway_cells, removed)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {WALL_LAYER})
    interior = irvine_interior_cells(tmj, matrix_dir)
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


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tmj", default=os.path.join(
        repo, "godot-generative-agents", "maps", "upenn_core_urban.tmj"))
    ap.add_argument("--matrix", default=os.path.join(
        repo, "godot-generative-agents", "sim", "the_upenn", "matrix"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.tmj) as fh:
        tmj = json.load(fh)
    floored = apply(tmj, args.matrix)
    print(f"irvine_floor: painted {floored} interior cells (GID {FLOOR_GID})")
    walls, doors, removed = apply_walls(tmj, args.matrix)
    print(f"irvine_walls: {walls} wall cells, {doors} doorway cells "
          f"({removed} removed to keep <=3 per 2x2)")
    if args.dry_run:
        return
    shutil.copy2(args.tmj, args.tmj + ".bak")
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")


if __name__ == "__main__":
    main()
