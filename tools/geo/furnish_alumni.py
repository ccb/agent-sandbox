#!/usr/bin/env python3
"""Furnish the Sweeten Alumni Building dorm suites: silver walls + furniture.

Reads the hand-drawn ``alumni_arenas`` object layer. Each room is named
``Room <suite>: <kind> <n>`` (e.g. ``Room 2: BD 5`` = suite 2, bedroom 5;
``BR`` = bathroom; plus ``Kitchen``, ``Living Room``, ``Hallway`` and explicit
``Wall`` boxes). Boxes are drawn to OVERLAP their neighbours by one tile, and
those overlaps are where a partition wall belongs, so:

  * ``alumni_walls``     -- silver wall (``wall_set_silver``, the music-sheet
                            3x3 frame) on every cell two boxes share, PLUS any
                            box named ``Wall`` filled solid. Two open-plan rooms
                            (kitchen / living room / hallway) never get a wall
                            between them, so they stay one connected space. A
                            centered doorway is carved in each wall between a
                            bedroom/bath and the hallway, and those partitions
                            are written into ``collision_maze.csv`` (walls block,
                            doorways stay walkable) so the suites are navigable.
                            Run this AFTER add_entrances, which resets collision.
  * ``alumni_rugs``      -- a carpet (``rug_green``, nine-sliced) down each
                            hallway corridor, plus an accent rug centered under
                            the kitchen / living-room furniture.
  * ``alumni_furniture`` -- furniture in each room's clear interior (box minus
                            wall cells), per _room_furniture: bedrooms get a bed
                            + desk + nightstand; baths a toilet + bathtub + sink;
                            the wider (suite-2) rooms also get a plant / mirror.
                            Kitchens follow the franuka eat-in style (dining
                            table + food + chairs); living rooms are a lounge
                            (sofa + fireplace + armchair + cushion + plant).

Walls use the same thin-line convention as furnish_irvine (a strip on the
right/bottom edge; corner where both meet). All gids are read live from the
tilesets so they can't desync into a red-X. Doorways are NOT carved.

    uv run python tools/geo/furnish_alumni.py
    uv run python tools/geo/furnish_alumni.py --dry-run  # report, write nothing

Idempotent: strips its own layers before re-inserting; backs up the .tmj first.
"""

import argparse
import collections
import json
import os
import re
import shutil

from add_entrances import split_footprint
from furnish_irvine import _fill_rug, _new_layer, _runs, _stamp, _strip, load_sprites

ARENA_LAYER = "alumni_arenas"
WALL_LAYER = "alumni_walls"
RUG_LAYER = "alumni_rugs"
FURN_LAYER = "alumni_furniture"
RUG = "rug_green"  # the carpet laid down the hallways (from the general-beds preset)
SWEETEN_SECTOR = "27"
TILE = 16

# By default a hallway's carpet stops at any opening onto another room (so it
# doesn't spill into the kitchen/living room). Hallways listed here keep their
# carpet right up to that edge instead. Keyed by the full arena-object name.
KEEP_EDGE_CARPET = {"Room 1: Hallway 2"}

# wall_set_silver: the music-sheet 3x3 frame (col0/row0). Same thin-line edges
# furnish_irvine picks from the red set: right edge (vertical strip), bottom
# edge (horizontal strip), bottom-right corner. Read live so repacking can't
# desync the gids.
SILVER_SHEET = "music"
SILVER_COLS = 32

# Open-plan rooms: two of these adjoining each other never get a partition wall.
OPEN_KINDS = {"kitchen", "living", "hallway"}
# A room whose clear interior is at least this wide counts as "big" and gets the
# extra accessory (suite-2 rooms are 7-wide boxes -> 6 clear; suite-1 are 5).
BIG_MIN_WIDTH = 6

# Shift a specific room's furniture down N rows inside its box (by object name).
FURNITURE_ROW_SHIFT = {"Room 1: BD 1": 1}


def _room_furniture(kind, cx0, cy0, cx1, cy1):
    """Absolute [(item, col, row), ...] for a room, sized to its clear interior.
    _stamp skips any piece that would fall outside the room or overlap another.
    Bedrooms/baths keep the earlier layout (with a plant/mirror in the wider
    rooms); kitchens and living rooms follow the franuka examples -- an eat-in
    kitchen (dining table + food + chairs) and a lounge (sofa + fireplace +
    armchair + plant)."""
    w = cx1 - cx0 + 1
    if kind == "bedroom":
        items = [
            ("bed_single_made", cx0, cy0),  # 2x3 single bed on the left wall
            ("student_desk", cx1, cy0),  # 1x2 desk on the right wall
            ("side_table", cx0 + 2, cy0),  # 1x1 nightstand by the bed head
        ]
        if w >= BIG_MIN_WIDTH:
            items.append(("plant_large", cx1, cy0 + 2))
        return items
    if kind == "bathroom":
        items = [
            ("toilet", cx0, cy0),  # 1x2
            ("bathtub", cx0 + 1, cy0),  # 2x2
            ("sink", cx0 + 3, cy0),  # 1x2
        ]
        if w >= BIG_MIN_WIDTH:
            items.append(("mirror", cx1, cy0))
        return items
    if kind == "kitchen":
        tc = cx0 + (w - 2) // 2  # dining table's left column, centered
        return [
            ("dining_table", tc, cy0 + 1),  # 2x3, sits on the rug
            ("armchair_green", tc - 1, cy0 + 2),  # chairs either side
            ("armchair_green", tc + 2, cy0 + 2),
            ("basket_fruit", cx0, cy0),  # food along the top wall
            ("food_sausage", cx1 - 1, cy0),
            ("food_ham", cx1, cy0),
            ("plant_large", cx0, cy1 - 1),  # plant in a corner
        ]
    if kind == "living":
        return [
            ("sofa_orange_sectional", cx0, cy0),  # 3x2 along the top
            ("fireplace", cx1 - 1, cy0),  # 2x3 in the top corner
            ("armchair_green", cx0, cy1),  # bottom-corner armchair
            ("cushion", cx0 + 1, cy1 - 1),  # 2x2 pouffe
            ("plant_large", cx1, cy1 - 1),  # corner plant
        ]
    return []


def _kind(name):
    """Classify a room by the words in its name."""
    tk = re.findall(r"[a-z]+", name.lower())
    if "wall" in tk:
        return "wall"
    if "bd" in tk:
        return "bedroom"
    if "br" in tk or "bath" in tk:
        return "bathroom"
    if "kitchen" in tk:
        return "kitchen"
    if "living" in tk:
        return "living"
    if "hallway" in tk:
        return "hallway"
    return "other"


def silver_tiles(tmj):
    """(right-edge, bottom-edge, bottom-right-corner) gids for wall_set_silver."""
    fg = next(
        ts["firstgid"]
        for ts in tmj["tilesets"]
        if SILVER_SHEET in (ts.get("source", "") + ts.get("image", ""))
    )
    return fg + 1 * SILVER_COLS + 2, fg + 2 * SILVER_COLS + 1, fg + 2 * SILVER_COLS + 2


def interior_cells(tmj):
    """Sector-27 footprint (painted into entrance_floor) minus its wall ring."""
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
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    sector_path = os.path.join(
        repo,
        "godot-generative-agents",
        "sim",
        "the_upenn",
        "matrix",
        "maze",
        "sector_maze.csv",
    )
    sector = open(sector_path).read().strip().split(", ")
    foot = {(i % W, i // W) for i, s in enumerate(sector) if s == SWEETEN_SECTOR}
    foot &= entrance
    _perimeter, interior = split_footprint(foot, W, H)
    return interior


def read_arenas(tmj):
    """(name, kind, c0, r0, c1, r1) inclusive tile rects from alumni_arenas."""
    layer = next(
        (
            L
            for L in tmj["layers"]
            if L.get("name") == ARENA_LAYER and L.get("type") == "objectgroup"
        ),
        None,
    )
    out = []
    if not layer:
        return out
    for o in layer["objects"]:
        name = o.get("name", "")
        c0 = round(o["x"] / TILE)
        r0 = round(o["y"] / TILE)
        c1 = round((o["x"] + o["width"]) / TILE) - 1
        r1 = round((o["y"] + o["height"]) / TILE) - 1
        out.append((name, _kind(name), c0, r0, c1, r1))
    return out


def compute_walls(rooms, interior):
    """Wall cells: every cell two boxes share (partition), except between two
    open-plan rooms; plus every cell of a box named ``Wall`` (filled solid).
    Clipped to the building interior."""
    walls = set()
    for i, (_ni, ki, a0, b0, a1, b1) in enumerate(rooms):
        if ki == "wall":
            for x in range(a0, a1 + 1):
                for y in range(b0, b1 + 1):
                    walls.add((x, y))
        for _nj, kj, c0, d0, c1, d1 in rooms[i + 1 :]:
            if ki == "wall" or kj == "wall":
                continue  # explicit Wall boxes are filled above
            if ki in OPEN_KINDS and kj in OPEN_KINDS:
                continue  # open plan: no partition between these
            ox0, ox1 = max(a0, c0), min(a1, c1)
            oy0, oy1 = max(b0, d0), min(b1, d1)
            for x in range(ox0, ox1 + 1):
                for y in range(oy0, oy1 + 1):
                    walls.add((x, y))
    return {cell for cell in walls if cell in interior}


def carve_doors(walls, rooms, interior):
    """Open one centered doorway in each wall segment that separates a private
    room (bedroom/bathroom) from a hallway corridor, so every room is reachable
    from the hallway. Room<->room and suite-divider walls stay solid. Returns
    the set of door cells."""
    hall, priv = set(), set()
    for name, kind, c0, r0, c1, r1 in rooms:
        # "Hallway 3" is an entrance vestibule: bedrooms get NO door onto it
        # (they open only onto the main corridor), so it's not a door target.
        if kind == "hallway" and "hallway 3" not in name.lower():
            bucket = hall
        elif kind in ("bedroom", "bathroom"):
            bucket = priv
        else:
            continue
        for x in range(c0, c1 + 1):
            for y in range(r0, r1 + 1):
                if (x, y) in interior and (x, y) not in walls:
                    bucket.add((x, y))
    # a door-eligible wall cell has a hallway floor on one side and this room's
    # floor on the opposite side; group eligible cells into straight runs (one
    # per room wall) and open the middle of each
    vert, horiz = collections.defaultdict(list), collections.defaultdict(list)
    for x, y in walls:
        if ((x - 1, y) in hall and (x + 1, y) in priv) or (
            (x + 1, y) in hall and (x - 1, y) in priv
        ):
            vert[x].append(y)
        elif ((x, y - 1) in hall and (x, y + 1) in priv) or (
            (x, y + 1) in hall and (x, y - 1) in priv
        ):
            horiz[y].append(x)
    doors = set()
    for x, ys in vert.items():
        for s, e in _runs(ys):
            doors.add((x, (s + e) // 2))
    for y, xs in horiz.items():
        for s, e in _runs(xs):
            doors.add(((s + e) // 2, y))
    return doors


def write_collision(matrix_dir, interior, walls, W):
    """Save the dorm partitions to the matrix: reset Sweeten's interior to
    walkable, then block every wall cell (doors were already removed from
    `walls`, so they stay open). Only interior cells are touched -- the
    perimeter and its entrances keep whatever add_entrances set."""
    path = os.path.join(matrix_dir, "maze", "collision_maze.csv")
    cells = open(path).read().strip().split(", ")
    for x, y in interior:
        cells[y * W + x] = "0"
    for x, y in walls:
        cells[y * W + x] = "1"
    with open(path, "w") as fh:
        fh.write(", ".join(cells))


def apply(tmj):
    """Paint alumni_walls (silver) + alumni_furniture. Returns (wall_cells,
    placed, skipped)."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, {WALL_LAYER, RUG_LAYER, FURN_LAYER})
    interior = interior_cells(tmj)
    rooms = read_arenas(tmj)
    sprites = load_sprites(tmj)
    R, B, BR = silver_tiles(tmj)

    # --- walls: silver strips on the wall cells, with doorways carved ------
    # `walls` stays the full partition set for layout (carpet + furniture keep
    # off the doorways); `open_walls` drops the door cells for the wall tiles and
    # the collision write, so the doorway is a real gap.
    walls = compute_walls(rooms, interior)
    doors = carve_doors(walls, rooms, interior)
    open_walls = walls - doors
    wdata = [0] * (W * H)
    for x, y in open_walls:
        horiz = (x - 1, y) in open_walls or (x + 1, y) in open_walls
        vert = (x, y - 1) in open_walls or (x, y + 1) in open_walls
        wdata[y * W + x] = BR if (horiz and vert) else (R if vert else B)

    # brick wall(s): close each cell marked by a "Brick Wall" object -- e.g. to
    # shrink the east entrance from 3 tiles to 2 (the perimeter is brick, so the
    # closed cell blends in). These block collision even on the perimeter.
    brick_gid = sprites["wall_brick"][0] if "wall_brick" in sprites else 0
    brick = {
        (x, y)
        for name, kind, c0, r0, c1, r1 in rooms
        if "brick" in name.lower()
        for x in range(c0, c1 + 1)
        for y in range(r0, r1 + 1)
    }
    if brick_gid:
        for x, y in brick:
            wdata[y * W + x] = brick_gid

    # --- carpet: nine-slice a rug down each hallway corridor. By default the
    # --- runner is kept off the open edges where a hallway borders another room
    # --- (e.g. the kitchen); hallways in KEEP_EDGE_CARPET keep those edges.
    other_open = {
        (x, y)
        for name, kind, c0, r0, c1, r1 in rooms
        if kind != "hallway"
        for x in range(c0, c1 + 1)
        for y in range(r0, r1 + 1)
        if (x, y) in interior and (x, y) not in walls
    }

    def _borders_other(x, y):
        return any(
            (x + dx, y + dy) in other_open
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )

    hall = set()
    for name, kind, c0, r0, c1, r1 in rooms:
        if kind != "hallway":
            continue
        cells = {
            (x, y)
            for x in range(c0, c1 + 1)
            for y in range(r0, r1 + 1)
            if (x, y) in interior and (x, y) not in walls
        }
        if name not in KEEP_EDGE_CARPET:
            cells = {(x, y) for (x, y) in cells if not _borders_other(x, y)}
        hall |= cells
    rdata = [0] * (W * H)
    carpeted = 0
    seen = set()
    for start in hall:  # one nine-slice per connected corridor
        if start in seen:
            continue
        comp, stack = set(), [start]
        seen.add(start)
        while stack:
            x, y = stack.pop()
            comp.add((x, y))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n in hall and n not in seen:
                    seen.add(n)
                    stack.append(n)
        cs = [c for c, r in comp]
        rs = [r for c, r in comp]
        box = (min(cs), min(rs), max(cs), max(rs))
        carpeted += _fill_rug(rdata, sprites, RUG, box, comp, W)

    # --- furniture: bedrooms, baths, kitchens, living rooms ----------------
    fdata = [0] * (W * H)
    occ = set()
    placed = skipped = 0
    for name, kind, c0, r0, c1, r1 in rooms:
        if kind not in ("bedroom", "bathroom", "kitchen", "living"):
            continue
        clear = {
            (x, y)
            for x in range(c0, c1 + 1)
            for y in range(r0, r1 + 1)
            if (x, y) in interior and (x, y) not in walls
        }
        if not clear:
            continue
        cx0 = min(x for x, y in clear)
        cx1 = max(x for x, y in clear)
        cy0 = min(y for x, y in clear)
        cy1 = max(y for x, y in clear)
        # kitchens & living rooms get an accent rug centered under the furniture
        if kind in ("kitchen", "living"):
            rw = min(3, cx1 - cx0 - 1)
            rh = min(3, cy1 - cy0 - 1)
            if rw >= 1 and rh >= 1:
                b0 = cx0 + (cx1 - cx0 + 1 - rw) // 2
                d0 = cy0 + (cy1 - cy0 + 1 - rh) // 2
                rbox = (b0, d0, b0 + rw - 1, d0 + rh - 1)
                region = {
                    c for c in clear if b0 <= c[0] <= rbox[2] and d0 <= c[1] <= rbox[3]
                }
                carpeted += _fill_rug(rdata, sprites, RUG, rbox, region, W)
        shift = FURNITURE_ROW_SHIFT.get(name, 0)
        for item, c, r in _room_furniture(kind, cx0, cy0, cx1, cy1):
            if item not in sprites:
                continue
            r += shift
            if _stamp(fdata, occ, sprites, item, c, r, clear, W):
                placed += 1
            else:
                skipped += 1

    # --- insert both layers above the floor --------------------------------
    names = [L.get("name") for L in tmj["layers"]]
    anchor = "sweeten_floor" if "sweeten_floor" in names else "entrance_floor"
    at = names.index(anchor) + 1 if anchor in names else len(tmj["layers"])
    nid = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    rug_layer = _new_layer(RUG_LAYER, rdata, W, H, nid)
    wall_layer = _new_layer(WALL_LAYER, wdata, W, H, nid + 1)
    furn_layer = _new_layer(FURN_LAYER, fdata, W, H, nid + 2)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], nid + 3)
    tmj["layers"][at:at] = [rug_layer, wall_layer, furn_layer]
    block = open_walls | brick  # collision-blocking cells (walls + brick)
    return (
        len(open_walls),
        len(doors),
        len(brick),
        carpeted,
        placed,
        skipped,
        block,
        interior,
    )


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser(description=__doc__)
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
    ap.add_argument("--dry-run", action="store_true", help="report, do not write")
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    walls, doors, bricks, carpeted, placed, skipped, block, interior = apply(tmj)
    print(f"{WALL_LAYER}: {walls} silver wall cells ({doors} doorways, {bricks} brick)")
    print(f"{RUG_LAYER}: {carpeted} carpet cells ({RUG})")
    print(f"{FURN_LAYER}: placed {placed} sprites ({skipped} skipped)")

    if args.dry_run:
        return
    shutil.copy(args.tmj, args.tmj + ".bak")
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")
    write_collision(args.matrix, interior, block, tmj["width"])
    print(f"wrote collision_maze ({len(block)} cells blocked, {doors} doors open)")


if __name__ == "__main__":
    main()
