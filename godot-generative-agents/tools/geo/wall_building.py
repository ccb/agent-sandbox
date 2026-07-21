#!/usr/bin/env python3
"""Outline a building's exterior with matching brick wall tiles.

A *post-process* for the baked urban ``.tmj`` (a sibling of ``furnish_building.py``).
``osm_to_tiled.py --theme urban`` paints every OSM building footprint as one flat
brick "field" tile on the ``buildings`` layer, so a building has no defined edge —
the brick just stops where the street begins. Real campus buildings read as a
solid massed block with a cornice along the roofline and pilasters down the
corners. This script **autotiles the footprint perimeter** with the Kenney RPG
Urban pack's brick wall frame (4 corners + 4 edges), leaving the interior fill
untouched, so e.g. Van Pelt gets a proper brick-walled outline that looks like
the real building.

Run order:

    uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --area core --theme urban   # bake map
    uv run python godot-generative-agents/tools/geo/wall_building.py --sector "Van Pelt Library" # outline
    # commit the updated .tmj

It is **idempotent**: the perimeter is re-derived from the footprint every run and
only perimeter cells are rewritten, so it is safe to re-run and safe to run again
after a fresh ``osm_to_tiled.py`` bake.

How it works (kept simple/readable — see CLAUDE.md):

1. Read the target building's footprint from the sim matrix (a "sector" AND solid
   in the collision maze), exactly like ``furnish_building.py``. The matrix grid
   is the SAME grid as the urban ``.tmj``, so cells map 1:1.
2. Pick the brick colour family (red / orange) that matches the building's CURRENT
   fill tile, so the new wall blends with the roof rather than recolouring it.
3. For each footprint cell, look at its 4 orthogonal neighbours and replace it with
   the frame tile whose trim faces the OUTSIDE — corner where two outward sides
   meet, edge where one does. Interior cells (no outward side) are left untouched.
"""

from __future__ import annotations

import argparse
import collections
import json
import os

from furnish_building import CATALOG, SHEETS, _FIRST, load_matrix_sector, tile_named
from tmj_io import write_tmj


# --------------------------------------------------------------------------- #
# Brick wall frames, by colour. The Kenney RPG Urban sheet (referenced whole as
# GID = sheet-index + 1) carries each building as a wall autotile block: a tan/grey
# cornice on the top & bottom rows, pilaster trim down the left & right columns, and
# a clean centre. We use the 3x3 of corner/edge cells that wrap a fill; the values
# are the sheet indices (GID is +1) verified by sampling the trim on each side.
#   red block  -> cols 17-19, rows 0/2/3   (row 1 is a mid-floor band, skipped)
#   orange block -> cols 17-19, rows 4/6/7 (row 5 is the mid-floor band)
# 'C' is the plain centre (used only for a stray 1x1 footprint).
# --------------------------------------------------------------------------- #
def _frame(tl, t, tr, l, c, r, bl, b, br):
    """Build a {position: GID} frame from sheet indices (GID = index + 1)."""
    keys = ["TL", "T", "TR", "L", "C", "R", "BL", "B", "BR"]
    return dict(zip(keys, (i + 1 for i in (tl, t, tr, l, c, r, bl, b, br))))


RED_FRAME = _frame(17, 18, 19, 71, 72, 73, 98, 99, 100)
ORANGE_FRAME = _frame(125, 126, 127, 179, 180, 181, 206, 207, 208)
# Grey stone block with a buff limestone border (cols 8-10, rows 3-5) — for the
# grey collegiate-gothic stone buildings (Houston Hall) that aren't brick.
GREY_FRAME = _frame(89, 90, 91, 116, 117, 118, 143, 144, 145)

# Thin "kerb" wall: the lawn_edges sheet (firstgid 487) is 2 rows x 16 masks. Row 0
# (LAWN_STYLE) is the thin concrete-grey stroke. A tile draws the stroke on the sides
# set in an N/E/S/W bitmask; GID = 487 + style*16 + mask.
LAWN_EDGES_FIRSTGID = 487
LAWN_STYLE = 0
EDGE_N, EDGE_E, EDGE_S, EDGE_W = 1, 2, 4, 8

# Which fill GIDs belong to which colour family (the ROOF_TILES of osm_to_tiled.py,
# as GIDs). A footprint filled from one family gets that family's wall frame.
RED_FILLS = {73, 75, 76}  # sheet idx 72, 74, 75
ORANGE_FILLS = {181, 183, 184}  # sheet idx 180, 182, 183


def pick_frame(fill_gid: int) -> dict:
    """Choose the wall frame whose brick colour matches the building's fill."""
    if fill_gid in ORANGE_FILLS:
        return ORANGE_FRAME
    return RED_FRAME  # red is Penn's default brick; also the safe fallback


def perimeter_tile(x: int, y: int, roof: set, frame: dict):
    """The frame GID for a footprint cell, or None to leave it as interior fill.

    Look at the 4 orthogonal neighbours: a side is "out" when it leaves the
    footprint. The frame tile is chosen so its trim faces those outward sides.
    """
    out_t = (x, y - 1) not in roof
    out_b = (x, y + 1) not in roof
    out_l = (x - 1, y) not in roof
    out_r = (x + 1, y) not in roof
    n = out_t + out_b + out_l + out_r

    if n == 0:
        return None  # fully interior — don't touch
    if n == 4:
        return frame["C"]  # isolated 1x1 footprint
    if n == 3:  # a 1-wide tip: face away from the one interior side
        if not out_b:
            return frame["T"]
        if not out_t:
            return frame["B"]
        if not out_r:
            return frame["L"]
        return frame["R"]
    if n == 2:
        if out_t and out_l:
            return frame["TL"]
        if out_t and out_r:
            return frame["TR"]
        if out_b and out_l:
            return frame["BL"]
        if out_b and out_r:
            return frame["BR"]
        # opposite sides (a 1-wide strip): use the matching straight edge
        return frame["T"] if out_t and out_b else frame["L"]
    # n == 1
    if out_t:
        return frame["T"]
    if out_b:
        return frame["B"]
    if out_l:
        return frame["L"]
    return frame["R"]


def place_thin_edge(tmj, roof, W, H, dry_run):
    """Draw a thin grey kerb on the apron ring just outside the footprint, with the
    stroke on each apron cell's building-facing side, so it hugs the building. Writes
    to the `edges` layer (which renders above the ground, below buildings). Returns
    the number of apron cells stroked."""
    edges = next((L for L in tmj["layers"] if L.get("name") == "edges"), None)
    if edges is None:
        raise SystemExit("no 'edges' layer in the .tmj")
    data = edges["data"]
    n = 0
    apron = {
        (x + dx, y + dy)
        for (x, y) in roof
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if (x + dx, y + dy) not in roof
    }
    for x, y in apron:
        if not (0 <= x < W and 0 <= y < H):
            continue
        mask = 0
        if (x, y - 1) in roof:
            mask |= EDGE_N
        if (x + 1, y) in roof:
            mask |= EDGE_E
        if (x, y + 1) in roof:
            mask |= EDGE_S
        if (x - 1, y) in roof:
            mask |= EDGE_W
        if mask and not dry_run:
            data[y * W + x] = LAWN_EDGES_FIRSTGID + LAWN_STYLE * 16 + mask
        n += 1
    return n


def flood_fill_building(data, W, H, sx, sy):
    """Footprint = the connected run of non-empty buildings-layer cells around a
    seed. For buildings that have no sim-matrix sector (unnamed OSM footprints)."""
    import collections as _c

    if data[sy * W + sx] == 0:
        raise SystemExit(f"seed {sx},{sy} is not on a building cell")
    seen = {(sx, sy)}
    q = _c.deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (
                0 <= nx < W
                and 0 <= ny < H
                and (nx, ny) not in seen
                and data[ny * W + nx] != 0
            ):
                seen.add((nx, ny))
                q.append((nx, ny))
    return seen


def outer_two_rings(roof):
    """Split a footprint into its two outermost cell rings.

    ring1 = cells touching the outside (the very edge); ring2 = the next cells in.
    Used by --outer-frame to draw a thin wall on the outermost ring and the brick
    band just inside it. Everything deeper is interior (left untouched).
    """
    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
    ring1 = {
        (x, y)
        for (x, y) in roof
        if any((x + dx, y + dy) not in roof for dx, dy in dirs)
    }
    ring2 = {
        (x, y)
        for (x, y) in roof
        if (x, y) not in ring1 and any((x + dx, y + dy) in ring1 for dx, dy in dirs)
    }
    return ring1, ring2


def ensure_interior_tileset(tmj, sheet_name):
    """Make sure an interior sheet (e.g. interior_franuka) is a registered tileset
    so a GID into it resolves. furnish_building.py normally adds these, but this
    script may run on a freshly-baked map that only has the Kenney sheet. We append
    just the one missing sheet (never strip — that would drop furnished layers)."""
    if any(t.get("name") == sheet_name for t in tmj["tilesets"]):
        return
    name, img, cols, rows = next(s for s in SHEETS if s[0] == sheet_name)
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
    ap.add_argument("--sector", default="Van Pelt Library")
    ap.add_argument(
        "--color",
        choices=["auto", "red", "orange", "grey"],
        default="auto",
        help="Kenney wall colour. 'auto' matches the current fill; 'red'/'orange' "
        "force a brick family; 'grey' is the limestone-trimmed grey stone block "
        "(for non-brick stone buildings). Only the perimeter wall is ever written — "
        "the interior fill is left untouched (it's hidden under the roof-off view).",
    )
    ap.add_argument(
        "--wall",
        default="kenney",
        help="perimeter wall tile. 'kenney' (default) uses the Kenney urban brick "
        "autotile frame (cornice + pilaster corners; see --color). Otherwise name a "
        "wall object from furniture_catalog.json (e.g. wall_brick_red) to band the "
        "perimeter with that single Franuka brick tile instead.",
    )
    ap.add_argument(
        "--outer-frame",
        action="store_true",
        help="keep a thin Kenney wall frame on the OUTERMOST ring and put the "
        "--wall brick on the ring just inside it (a planning aid). Needs --wall to "
        "name a Franuka brick; --color sets the thin frame's colour.",
    )
    ap.add_argument(
        "--seed",
        help="target an UNNAMED building by a cell inside it, as 'x,y'. The "
        "footprint is the connected run of non-empty buildings-layer cells around "
        "that seed (use this for buildings that have no sim-matrix sector, e.g. "
        "Fisher Fine Arts). Overrides --sector.",
    )
    ap.add_argument(
        "--thin-edge",
        action="store_true",
        help="instead of walling the footprint, draw a THIN grey kerb (the "
        "lawn_edges stroke) on the apron ring just outside it, hugging the building "
        "— a thin outer wall. Leaves the buildings layer untouched.",
    )
    ap.add_argument(
        "--reset-fill",
        action="store_true",
        help="repaint the whole footprint with its base fill tile before walling. "
        "Use when re-running with a different layout so an earlier run's wall tiles "
        "don't linger on cells that are now interior.",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="report counts, do not write"
    )
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    W, H = tmj["width"], tmj["height"]

    buildings = next(L for L in tmj["layers"] if L.get("name") == "buildings")
    data = buildings["data"]

    if args.seed:
        sx, sy = (int(v) for v in args.seed.split(","))
        roof = flood_fill_building(data, W, H, sx, sy)
        sid = f"seed {sx},{sy}"
        label = (
            args.sector if args.sector != "Van Pelt Library" else f"building@{sx},{sy}"
        )
    else:
        sid, roof, _apron = load_matrix_sector(args.matrix, args.sector, W, H)
        label = args.sector

    if args.thin_edge:
        n = place_thin_edge(tmj, roof, W, H, args.dry_run)
        print(
            f"{label}: {sid}  footprint={len(roof)} cells  thin kerb on {n} apron cells"
        )
        if args.dry_run:
            return
        write_tmj(args.tmj, tmj)
        print(f"  wrote {args.tmj}")
        return

    # The footprint's most common current fill tile fixes the existing colour.
    fills = collections.Counter(data[y * W + x] for x, y in roof if data[y * W + x])
    fill_gid = fills.most_common(1)[0][0] if fills else 0

    # Resolve the Kenney frame (always available) and, if --wall names a catalog
    # tile, the single Franuka brick GID.
    frames = {"red": RED_FRAME, "orange": ORANGE_FRAME, "grey": GREY_FRAME}
    if args.color == "auto":
        frame = pick_frame(fill_gid)
    else:
        frame = frames[args.color]
    family = next(k for k, v in frames.items() if v is frame)

    wall_gid = None
    if args.wall != "kenney":
        obj = CATALOG.get(args.wall)
        if obj is None or obj.get("category") != "wall":
            raise SystemExit(
                f"--wall {args.wall!r} is not a 'wall' object in furniture_catalog.json"
            )
        ensure_interior_tileset(tmj, "interior_" + obj["sheet"])
        wall_gid = tile_named(args.wall)

    # Decide the GID for every footprint cell. Three layouts:
    #  - outer-frame: thin Kenney frame on the outer ring, then a band just inside —
    #    the --wall brick if given, else the frame's own centre fill (grey-on-grey).
    #  - brick band : a single Franuka brick on the whole perimeter ring.
    #  - kenney     : the Kenney autotile frame on the whole perimeter ring.
    if args.outer_frame:
        ring1, ring2 = outer_two_rings(roof)
        band_gid = wall_gid if wall_gid is not None else frame["C"]

        def cell_gid(x, y):
            if (x, y) in ring1:
                return perimeter_tile(x, y, roof, frame)
            if (x, y) in ring2:
                return band_gid
            return None

        band_desc = f"'{args.wall}' brick" if wall_gid is not None else f"{family} fill"
        desc = f"Kenney {family} frame + {band_desc} band (gid {band_gid})"
    elif wall_gid is not None:

        def cell_gid(x, y):
            inside = all(
                (x + dx, y + dy) in roof
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
            return None if inside else wall_gid

        desc = f"Franuka '{args.wall}' ({CATALOG[args.wall]['label']}) gid {wall_gid}"
    else:

        def cell_gid(x, y):
            return perimeter_tile(x, y, roof, frame)

        desc = f"Kenney {family} brick frame"

    print(
        f"{label}: {sid}  footprint={len(roof)} cells  "
        f"fill gid {fill_gid} -> {desc} (interior left as-is)"
    )

    if args.reset_fill and not args.dry_run:
        for x, y in roof:
            data[y * W + x] = fill_gid

    painted = 0
    for x, y in roof:
        gid = cell_gid(x, y)
        if gid is None:
            continue  # interior cell — never touched
        if not args.dry_run:
            data[y * W + x] = gid
        painted += 1
    print(
        f"  perimeter cells walled: {painted}  (interior {len(roof) - painted} untouched)"
    )

    if args.dry_run:
        return
    write_tmj(args.tmj, tmj)
    print(f"  wrote {args.tmj}")


if __name__ == "__main__":
    main()
