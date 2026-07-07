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

IRVINE_SECTOR = "15"  # UPenn:Irvine Auditorium
IRVINE_LOBBY = "1015"  # INTERIOR_ARENA_BASE (1000) + sector 15
FLOOR_GID = 589  # interior_franuka plank_floor_light (col 6,row 2) -- the
# light wood plank Van Pelt/Fisher/Houston use.
FLOOR_LAYER = "irvine_floor"

# wall_set_red thin-line edges (interior_franuka 3x3 autotile at col0/row0,
# firstgid 519): a ~5px maroon strip on one side of the cell.
WALL_R = 553  # right edge
WALL_B = 584  # bottom edge
WALL_BR = 585  # bottom-right corner (cell needs both a right and bottom strip)
WALL_LAYER = "irvine_walls"
DOOR_W = 2  # centered doorway gap, in cells, per partition segment
WALL_SET = {WALL_R, WALL_B, WALL_BR}

# rugs sit on their own layer UNDER the furniture so a sofa/table can rest on one
RUG_LAYER = "irvine_rugs"
FURN_LAYER = "irvine_furniture"
RUGS = {"rug_red", "rug_blue", "rug_orange", "rug_green", "rug_magenta", "rug_cyan"}

OWN_LAYERS = [FLOOR_LAYER, WALL_LAYER, RUG_LAYER, FURN_LAYER]

# Tile columns per sheet (image width / 16). Firstgids are NOT hardcoded -- they
# shift whenever the tilesets are repacked, so load_sprites reads them live from
# the .tmj (matching each catalog sheet's image file to a tileset).
_SHEET_COLS = {
    "franuka": 32,
    "school": 16,
    "bath": 16,
    "kenney": 27,
    "alchemy": 32,
    "bedroom": 32,
    "clockwork": 32,
    "music": 32,
}


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
        (i % W, i // W) for i, s in enumerate(sector) if s == IRVINE_SECTOR
    } & entrance
    _perimeter, interior = split_footprint(foot, W, H)
    return {y * W + x for (x, y) in interior}


def read_sections(tmj):
    """Room name -> (c0, r0, c1, r1) inclusive tile rect, from the hand-drawn
    irvine_arenas object layer. Objects whose name contains 'rug' are rug-fill
    regions, not rooms, so they are excluded (consistent with the others)."""
    fa = next(
        (
            L
            for L in tmj["layers"]
            if L.get("name") == "irvine_arenas" and L.get("type") == "objectgroup"
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
    at = (
        names.index("entrance_floor") + 1
        if "entrance_floor" in names
        else len(tmj["layers"])
    )
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

    removed = _enforce_max3_per_2x2(data, W, H)

    # Carve the center aisle: the red carpet runs 3 wide (auditorium center) from
    # the stage front through to the lobby, so clear any wall in those 3 columns
    # where it crosses the stage and lobby partitions -- otherwise a partition
    # cell sits in the carpet. Keeps picture + matrix in lock-step (aisle walkable).
    grouped = _grouped_sections(tmj)
    if "Auditorium" in grouped:
        ac0, ar0, ac1, ar1 = grouped["Auditorium"]
        acx = (ac0 + ac1) // 2
        top = grouped["Stage"][3] if "Stage" in grouped else ar0
        bot = grouped["Lobby"][1] if "Lobby" in grouped else ar1
        for c in (acx - 1, acx, acx + 1):
            for r in range(top, bot + 1):
                if data[r * W + c] in WALL_SET:
                    data[r * W + c] = 0
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


def load_sprites(tmj):
    """catalog name -> (top_left_gid, w, h, sheet) for every catalogued sprite.

    Firstgids are read from the live tmj (matching each catalog sheet's image
    file to a tileset), so repacking the tilesets can't desync the gids."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "furniture_catalog.json")) as fh:
        cat = json.load(fh)
    file2fg = {t["image"]: t["firstgid"] for t in tmj["tilesets"] if "image" in t}
    sheet_fg = {
        s: file2fg[meta["file"]]
        for s, meta in cat["sheets"].items()
        if meta.get("file") in file2fg
    }
    out = {}
    for name, v in cat["objects"].items():
        if not (isinstance(v, dict) and v.get("sheet") in sheet_fg):
            continue
        sheet = v["sheet"]
        gid = sheet_fg[sheet] + v["row"] * _SHEET_COLS[sheet] + v["col"]
        out[name] = (gid, v["w"], v["h"], sheet)
    return out


def _stamp(data, occ, sprites, name, c, r, walk, W):
    """Place a whole multi-tile sprite with top-left at (c, r). Refuses (and
    changes nothing) unless every w*h cell is walkable floor and unoccupied --
    the cardinal rule: never place part of a sprite. Returns bool."""
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
    """Nine-slice a rug across a box so it reads as one continuous rug of any
    size (the 3x3 rug supplies corner/edge/center tiles). Only walkable cells
    are painted. Returns the count filled."""
    gid, w, h, sheet = sprites[name]
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


def _grouped_sections(tmj):
    """Merge sub-boxes into one bounding rect per room group (Stage 1/2/3 ->
    one 'Stage' rect, etc.) so each zone is furnished as a unit."""
    groups = {}
    for nm, (c0, r0, c1, r1) in read_sections(tmj).items():
        g = _group(nm)
        if g in groups:
            a, b, cc, dd = groups[g]
            groups[g] = (min(a, c0), min(b, r0), max(cc, c1), max(dd, r1))
        else:
            groups[g] = (c0, r0, c1, r1)
    return groups


def _room_layouts(sections):
    """Per-zone furniture as (name, col, row) of each sprite's top-left. An
    auditorium: pipe organ on the stage, rows of seats facing it, foyer/lobby
    lounge seating. Over-proposes; _stamp skips anything off-floor/overlapping."""
    out = []
    add = lambda *t: out.append(t)

    for name, (c0, r0, c1, r1) in sections.items():
        cx = (c0 + c1) // 2
        if name == "Stage":
            add("pipe_organ", cx - 1, r0 + 4)  # 3x4 organ, back-center
            add("plant_large", c0 + 1, r1 - 1)
            add("plant_large", c1 - 1, r1 - 1)
            add("candelabra", c0 + 3, r0 + 5)
            add("candelabra", c1 - 3, r0 + 5)
            add("lantern", cx - 1, r0 + 3)
            # music ensemble in front of the organ: each instrument gets its own
            # (distinct) chair + a sheet-music stand
            ensemble = [
                ("harp_gold", "stool_wood"),
                ("cello", "chair_wood"),
                ("violin", "armchair"),
                ("double_bass", "armchair_orange"),
                ("cello_wood", "armchair_green"),
                ("harp_silver", "armchair_red"),
            ]
            ir = r1 - 4
            for k, (inst, chair) in enumerate(ensemble):
                gc = c0 + 3 + k * 5
                add("music_stand", gc - 1, ir)  # stand holds the sheet music
                add(inst, gc, ir)
                # chair sits just past the instrument (harps are 2 wide)
                add(chair, gc + (2 if inst.startswith("harp") else 1), ir + 1)
        elif name == "Auditorium":
            # dense rows of seats facing the stage: every other row (legroom),
            # a seat in every column, with the center aisle left for the runner
            for rr in range(r0 + 1, r1, 2):
                for cc in range(c0 + 1, c1):
                    if abs(cc - cx) <= 1:  # center aisle (carpet)
                        continue
                    add("chair_wood", cc, rr)
        elif name in ("West Foyer", "East Foyer"):
            rug = "rug_blue" if name == "West Foyer" else "rug_green"
            add(rug, c0 + 1, r0 + 2)
            add("sofa", c0 + 1, r0 + 2)
            add("sofa", c0 + 1, r0 + 8)
            add("armchair", c0 + 5, r0 + 3)
            add("armchair_orange", c0 + 5, r0 + 6)
            add("side_table", c0 + 4, r0 + 4)
            add("round_table_small", c0 + 5, r0 + 9)
            add("floor_lamp", c0 + 1, r0 + 12)
            add("lantern", c0 + 3, r0)
            for px, py in ((c0, r0), (c1 - 1, r0), (c0, r1 - 1), (c1 - 1, r1 - 1)):
                add("plant", px, py)
        elif name == "Lobby":
            add("counter", c0 + 2, r0 + 1)  # ticket / info counter
            add("grandfather_clock", c1 - 2, r0 + 1)
            add("sofa", c0 + 5, r1 - 3)
            add("sofa", c1 - 7, r1 - 3)
            add("floor_lamp", c0 + 2, r1 - 3)
            add("floor_lamp", c1 - 3, r1 - 3)
            add("lantern", cx - 6, r0)
            add("lantern", cx + 6, r0)
            for px, py in ((c0, r0), (c1 - 1, r0), (c0, r1 - 1), (c1 - 1, r1 - 1)):
                add("plant", px, py)
    return out


def apply_furniture(tmj, matrix_dir):
    """Insert two stacked layers above irvine_walls: irvine_rugs (under) and
    irvine_furniture (on top), so a sofa/rug compose. Picture-only (not
    collision). Returns (placed, proposed)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {RUG_LAYER, FURN_LAYER})

    interior = irvine_interior_cells(tmj, matrix_dir)
    wl = next((L for L in tmj["layers"] if L.get("name") == WALL_LAYER), None)
    walls = {(i % W, i // W) for i, v in enumerate(wl["data"]) if v} if wl else set()
    walk = {(i % W, i // W) for i in interior} - walls

    sprites = load_sprites(tmj)
    grouped = _grouped_sections(tmj)
    rug_data = [0] * (W * H)
    furn_data = [0] * (W * H)
    rug_occ, furn_occ = set(), set()
    proposed = placed = 0
    for name, c, r in _room_layouts(grouped):
        proposed += 1
        if name not in sprites:
            continue
        if name in RUGS:
            ok = _stamp(rug_data, rug_occ, sprites, name, c, r, walk, W)
        else:
            ok = _stamp(furn_data, furn_occ, sprites, name, c, r, walk, W)
        placed += ok

    # red carpet: a runner down the auditorium center aisle (from the stage
    # front) plus the whole lobby -- one rug "leading through" to the stage.
    if "Auditorium" in grouped:
        ac0, ar0, ac1, ar1 = grouped["Auditorium"]
        acx = (ac0 + ac1) // 2
        top = grouped["Stage"][3] if "Stage" in grouped else ar0
        _fill_rug(rug_data, sprites, "rug_red", (acx - 1, top, acx + 1, ar1), walk, W)
    if "Lobby" in grouped:
        lc0, lr0, lc1, lr1 = grouped["Lobby"]
        _fill_rug(
            rug_data, sprites, "rug_red", (lc0 + 1, lr0, lc1 - 1, lr1 - 1), walk, W
        )

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
    tmj["layers"][at:at] = [rugs, furn]
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
    print(f"irvine_floor: painted {floored} interior cells (GID {FLOOR_GID})")
    walls, doors, removed = apply_walls(tmj, args.matrix)
    print(
        f"irvine_walls: {walls} wall cells, {doors} doorway cells "
        f"({removed} removed to keep <=3 per 2x2)"
    )
    fplaced, fprop = apply_furniture(tmj, args.matrix)
    print(f"irvine_furniture: placed {fplaced}/{fprop} sprites")
    if args.dry_run:
        return
    shutil.copy2(args.tmj, args.tmj + ".bak")
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")


if __name__ == "__main__":
    main()
