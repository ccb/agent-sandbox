#!/usr/bin/env python3
"""Frame the campus edges: straight border roads + a grass margin you can see past.

This is a *post-process* for the baked Tiled map (``osm_to_tiled.py --theme urban``
produces ``upenn_core_urban.tmj``; ``furnish_building.py`` then opens Williams Hall;
this script then tidies the OUTER EDGES). The roads come straight from OpenStreetMap,
rasterised node-by-node, so the perimeter streets are wiggly and sit right on the grid
edge -- the view "cuts off at the road" with grey void immediately beyond.

What this does (top / left / right edges only -- bottom is left as-is):

1. GROWS the grid by ``--pad`` tiles on the top, left and right (default 3). Every
   ``.tmj`` layer AND every sim matrix CSV is re-embedded into the bigger grid,
   shifted by (+pad, +pad). ``maze_meta_info.json`` and the persona ``start_tile``
   spawns in ``world_data_upenn.yaml`` are shifted to match, and the two Godot scene
   cameras are recentred. The grid stays 1:1 between the .tmj and the matrices.
2. STRAIGHTENS the top + right perimeter roads: the wiggly road band near each edge is
   cleared and a straight asphalt band (with a dashed centreline) is drawn in its place.
3. Adds a straight LEFT WALKWAY (pedestrian paving, not a vehicle road).
4. Fills the new outer ring with GRASS, so a couple of tiles of lawn show *beyond* each
   road and the screen no longer ends exactly at the road.

Run order (each step feeds the next; commit the updated artifacts):

    uv run python tools/geo/osm_to_tiled.py --area core --theme urban   # bake the map
    uv run python tools/geo/furnish_building.py                          # furnish Williams
    uv run python tools/geo/frame_edges.py                               # THIS -- run last
    uv run python godot-generative-agents/sim/generate_penn_replay.py    # re-bake the replay

Why last: it shifts whole layers, so the ``williams_*`` layers furnish_building added
get translated correctly along with everything else.

The op GROWS the grid, so it is NOT safely repeatable (a second run would grow again).
It stamps a ``framed_pad`` map property and refuses to run on an already-framed map --
re-bake from osm_to_tiled.py + furnish_building.py to start over.
"""

from __future__ import annotations

import argparse
import json
import os
import re

# --------------------------------------------------------------------------- #
# Tile GIDs. firstgid is 1 for the Kenney sheet, so a Tiled GID is the sheet
# index + 1; these mirror URBAN_TILES / DASH_* in osm_to_tiled.py (index there +1).
# --------------------------------------------------------------------------- #
GROUND = 39  # light-grey concrete base (URBAN_TILES["ground"] 38 + 1)
GRASS = 29  # green lawn (URBAN_TILES["grass"] 28 + 1)
WALKWAY = 110  # tan paving, pedestrian ways (URBAN_TILES["path"] 109 + 1)
ROAD = 462  # dark asphalt (URBAN_TILES["road"] 461 + 1)
DASH_H = 434  # horizontal lane dash, for E-W roads (DASH_H 433 + 1)
DASH_V = 463  # vertical lane dash, for N-S roads (DASH_V 462 + 1)

# Frame geometry (tiles). The margin is the pad ring of grass beyond the roads.
ROAD_THICK = 3  # straight border-road width
WALK_THICK = 2  # left walkway width (narrower than a road)

# Layers we keep clear in the grass margin (everything but ground + the grass itself).
_NON_GRASS = (
    "ground_edges",
    "water",
    "paths",
    "roads",
    "edges",
    "buildings",
    "trees",
)
MATRIX_FILES = (
    "collision_maze.csv",
    "sector_maze.csv",
    "arena_maze.csv",
    "game_object_maze.csv",
    "spawning_location_maze.csv",
)


# --------------------------------------------------------------------------- #
# .tmj helpers
# --------------------------------------------------------------------------- #
def tilelayers(tmj: dict) -> dict:
    """Map layer name -> its data list (the editable flat GID arrays)."""
    return {L["name"]: L["data"] for L in tmj["layers"] if L.get("type") == "tilelayer"}


def band_depth(rows_or_cols: list, span: int, frac: float = 0.2) -> int:
    """How many leading lines are 'mostly road' (>= frac of a full line).

    Used to find how deep the wiggly perimeter road reaches from an edge, so we
    clear exactly enough to erase it. Returns 0 if the very first line is sparse.
    """
    depth = 0
    for count in rows_or_cols:
        if count < frac * span:
            break
        depth += 1
    return depth


def road_profile(data: list, w: int, h: int):
    """Per-row and per-column road-tile counts, for band_depth detection."""
    rowc = [sum(1 for x in range(w) if data[y * w + x]) for y in range(h)]
    colc = [sum(1 for y in range(h) if data[y * w + x]) for x in range(w)]
    return rowc, colc


def grow_tmj(tmj: dict, pad: int) -> tuple[int, int, int, int]:
    """Re-embed every tilelayer into a grid grown by `pad` on top/left/right.

    Old cell (x, y) -> (x + pad, y + pad). Returns (old_w, old_h, new_w, new_h).
    """
    old_w, old_h = tmj["width"], tmj["height"]
    new_w, new_h = old_w + 2 * pad, old_h + pad
    for L in tmj["layers"]:
        if L.get("type") != "tilelayer":
            continue
        old = L["data"]
        new = [0] * (new_w * new_h)
        for y in range(old_h):
            base_old = y * old_w
            base_new = (y + pad) * new_w + pad
            new[base_new : base_new + old_w] = old[base_old : base_old + old_w]
        L["data"] = new
        L["width"], L["height"] = new_w, new_h
    tmj["width"], tmj["height"] = new_w, new_h
    props = tmj.setdefault("properties", [])
    props.append({"name": "framed_pad", "type": "int", "value": pad})
    return old_w, old_h, new_w, new_h


def fill_rect(data, w, x0, x1, y0, y1, gid):
    """Set [x0,x1) x [y0,y1) to gid (clipped is the caller's job)."""
    for y in range(y0, y1):
        row = y * w
        for x in range(x0, x1):
            data[row + x] = gid


def frame_tmj(tmj: dict, pad: int, old_w: int, old_h: int) -> None:
    """Paint the straight border roads, left walkway and grass margins."""
    w, h = tmj["width"], tmj["height"]
    lay = tilelayers(tmj)

    # How deep the (now shifted) wiggly perimeter roads reach, measured on the
    # original grid so we clear exactly enough. +pad puts it in new-grid coords.
    rowc, colc = road_profile(
        # rebuild original-extent profile from the shifted roads layer
        [
            lay["roads"][(y + pad) * w + (x + pad)]
            for y in range(old_h)
            for x in range(old_w)
        ],
        old_w,
        old_h,
    )
    top_clear = pad + band_depth(rowc, old_w) + 1
    right_band = band_depth(list(reversed(colc)), old_h)
    right_clear = w - pad - right_band - 1  # left edge of the right clear zone

    # 1. Ground fills the whole (grown) map -- no holes in the new ring.
    fill_rect(lay["ground"], w, 0, w, 0, h, GROUND)

    # 2. Grass margins: the pad ring beyond the roads, painted as pure lawn.
    def grass_margin(x0, x1, y0, y1):
        fill_rect(lay["landuse"], w, x0, x1, y0, y1, GRASS)
        for name in _NON_GRASS:
            fill_rect(lay[name], w, x0, x1, y0, y1, 0)

    grass_margin(0, w, 0, pad)  # top strip
    grass_margin(0, pad, 0, h)  # left strip
    grass_margin(w - pad, w, 0, h)  # right strip

    # 3. Erase the wiggly perimeter roads (keep buildings/trees/ground/landuse).
    def clear_road(x0, x1, y0, y1):
        for name in ("roads", "paths", "edges", "ground_edges"):
            fill_rect(lay[name], w, x0, x1, y0, y1, 0)

    clear_road(pad, w - pad, pad, top_clear)  # top band
    clear_road(max(right_clear, pad), w - pad, pad, h)  # right band
    clear_road(pad, pad + WALK_THICK + 3, pad, h)  # left band (sparse street-ends)

    # 4. Straight TOP road + dashed centreline.
    fill_rect(lay["roads"], w, pad, w - pad, pad, pad + ROAD_THICK, ROAD)
    cy = pad + ROAD_THICK // 2
    for x in range(pad, w - pad, 2):
        lay["roads"][cy * w + x] = DASH_H

    # 5. Straight RIGHT road + dashed centreline.
    rx0 = w - pad - ROAD_THICK
    fill_rect(lay["roads"], w, rx0, w - pad, pad, h, ROAD)
    cx = rx0 + ROAD_THICK // 2
    for y in range(pad, h, 2):
        lay["roads"][y * w + cx] = DASH_V

    # 6. Straight LEFT walkway (pedestrian paving, in the paths layer).
    fill_rect(lay["paths"], w, pad, pad + WALK_THICK, pad, h, WALKWAY)


# --------------------------------------------------------------------------- #
# Matrix + meta (kept 1:1 with the .tmj)
# --------------------------------------------------------------------------- #
def grow_matrix(matrix_dir: str, pad: int, old_w: int, old_h: int) -> None:
    new_w, new_h = old_w + 2 * pad, old_h + pad
    maze = os.path.join(matrix_dir, "maze")
    for fname in MATRIX_FILES:
        path = os.path.join(maze, fname)
        cells = open(path).read().strip().split(", ")
        if len(cells) != old_w * old_h:
            raise SystemExit(
                f"{fname}: {len(cells)} cells but map is {old_w}x{old_h}={old_w*old_h}"
            )
        new = ["0"] * (new_w * new_h)
        for y in range(old_h):
            src = y * old_w
            dst = (y + pad) * new_w + pad
            new[dst : dst + old_w] = cells[src : src + old_w]
        with open(path, "w") as fh:
            fh.write(", ".join(new))  # no trailing newline (matches osm_to_ville)

    meta_path = os.path.join(matrix_dir, "maze_meta_info.json")
    meta = json.load(open(meta_path))
    meta["maze_width"], meta["maze_height"] = new_w, new_h
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=1)


# --------------------------------------------------------------------------- #
# Godot scenes + world data
# --------------------------------------------------------------------------- #
def patch_scenes(scene_paths: list, new_w: int, new_h: int) -> None:
    px_w, px_h = new_w * 16, new_h * 16
    cam = (px_w // 2, px_h // 2)  # map centre
    zoom = round(1080 / px_h, 3)  # contain-fit the portrait map's height to 1080
    for path in scene_paths:
        text = open(path).read()
        text = re.sub(
            r"position = Vector2\([^)]*\)",
            f"position = Vector2({cam[0]}, {cam[1]})",
            text,
        )
        text = re.sub(
            r"zoom = Vector2\([^)]*\)", f"zoom = Vector2({zoom}, {zoom})", text
        )
        text = re.sub(r"\d+x\d+ px", f"{px_w}x{px_h} px", text)
        text = re.sub(r"\d+ \* [0-9.]+ ~= 1080", f"{px_h} * {zoom} ~= 1080", text)
        with open(path, "w") as fh:
            fh.write(text)


def patch_world_data(path: str, pad: int) -> None:
    """Shift each persona's raw `start_tile` spawn by (+pad, +pad), preserving the
    file's comments/formatting (a YAML round-trip would drop them)."""
    out, remaining = [], 0
    for line in open(path):
        if line.strip() == "start_tile:":
            remaining = 2  # the next two `- <int>` lines are x then y
            out.append(line)
            continue
        m = re.match(r"^(\s*-\s*)(\d+)(\s*)$", line)
        if remaining and m:
            out.append(f"{m.group(1)}{int(m.group(2)) + pad}{m.group(3)}")
            remaining -= 1
        else:
            out.append(line)
    with open(path, "w") as fh:
        fh.writelines(out)


# --------------------------------------------------------------------------- #
def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    godot = os.path.join(repo, "godot-generative-agents")
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--tmj", default=os.path.join(godot, "maps", "upenn_core_urban.tmj")
    )
    ap.add_argument(
        "--matrix", default=os.path.join(godot, "sim", "the_upenn", "matrix")
    )
    ap.add_argument(
        "--world-data", default=os.path.join(godot, "sim", "world_data_upenn.yaml")
    )
    ap.add_argument(
        "--scenes",
        nargs="*",
        default=[
            os.path.join(godot, "scenes", "penn_replay.tscn"),
            os.path.join(godot, "scenes", "campus_urban.tscn"),
        ],
    )
    ap.add_argument(
        "--pad", type=int, default=3, help="grass margin / grid growth (tiles)"
    )
    ap.add_argument("--dry-run", action="store_true", help="report dims, write nothing")
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    if any(p.get("name") == "framed_pad" for p in tmj.get("properties", [])):
        raise SystemExit(
            "map already framed (framed_pad property present); re-bake from "
            "osm_to_tiled.py + furnish_building.py before re-running frame_edges.py"
        )

    old_w, old_h = tmj["width"], tmj["height"]
    new_w, new_h = old_w + 2 * args.pad, old_h + args.pad
    print(
        f"framing pad={args.pad}: {old_w}x{old_h} -> {new_w}x{new_h} "
        f"(shift +{args.pad},+{args.pad}); camera -> "
        f"({new_w*16//2}, {new_h*16//2}) zoom {round(1080/(new_h*16),3)}"
    )
    if args.dry_run:
        return 0

    grow_tmj(tmj, args.pad)
    frame_tmj(tmj, args.pad, old_w, old_h)
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"  wrote {os.path.relpath(args.tmj, repo)}")

    grow_matrix(args.matrix, args.pad, old_w, old_h)
    print(f"  grew 5 matrix mazes + meta in {os.path.relpath(args.matrix, repo)}")

    patch_world_data(args.world_data, args.pad)
    print(f"  shifted start_tiles in {os.path.relpath(args.world_data, repo)}")

    patch_scenes(args.scenes, new_w, new_h)
    print(f"  recentred {len(args.scenes)} scene camera(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
