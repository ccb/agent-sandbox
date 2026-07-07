#!/usr/bin/env python3
"""Make lawns un-walkable: bake the grass into the sim's collision matrix.

The campus picture (`upenn_core_urban.tmj`) paints lawns on a `landuse` layer and
sidewalks/roads on `paths`/`roads` *above* them. The agent pathfinder, though, is
a breadth-first search over `the_upenn/matrix/maze/collision_maze.csv`
(`gen_agents/path_finder.py` via `world_map.py`): a tile is walkable iff its
collision cell is `"0"`. Until now only building footprints and water were walls,
so agents happily cut straight across the lawns.

This walls off every *visible* grass tile -- a `landuse` cell with no path, road,
or floor drawn on top of it -- so pathfinding routes agents around the grass and
onto the sidewalks. A lawn tile that has a path/road/entrance/williams floor
painted over it stays walkable (it reads as pavement, not grass), and tiles that
are already walls (buildings, water) are left untouched. The grid lines up
tile-for-tile with the .tmj, so the layers index the same cells as the matrix.

Re-run safe and idempotent: grass is detected from the (unchanged) `landuse`
layer, not from the collision it writes, so running twice is a no-op.

    uv run python tools/geo/block_grass.py --dry-run   # report, change nothing
    uv run python tools/geo/block_grass.py             # wall the lawns
"""

from __future__ import annotations

import argparse
import json
import os

# A grass tile is "really pavement" -- and so stays walkable -- when any of these
# walkable surfaces is painted on top of the lawn. Everything else on the landuse
# layer becomes a wall.
RESCUE_LAYERS = ("paths", "roads", "entrance_floor", "williams_floor")


def read_flat(path: str) -> list[str]:
    return open(path).read().strip().split(", ")


def write_flat(path: str, cells: list[str]) -> None:
    with open(path, "w") as fh:
        fh.write(", ".join(cells))


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    W, H = tmj["width"], tmj["height"]
    layers = {
        L["name"]: L["data"] for L in tmj["layers"] if L.get("type") == "tilelayer"
    }
    if "landuse" not in layers:
        raise SystemExit("no 'landuse' layer in the .tmj -- nothing to block")
    landuse = layers["landuse"]
    rescue = [layers[name] for name in RESCUE_LAYERS if name in layers]

    collision_path = os.path.join(args.matrix, "maze", "collision_maze.csv")
    collision = read_flat(collision_path)
    if len(collision) != W * H:
        raise SystemExit(
            f"collision has {len(collision)} cells, .tmj is {W}x{H}={W * H}"
        )

    blocked = 0
    for i in range(W * H):
        if not landuse[i]:
            continue  # not a lawn
        if collision[i] != "0":
            continue  # already a wall (building/water) -- leave it
        if any(layer[i] for layer in rescue):
            continue  # a sidewalk/road/floor sits on top -- stays walkable
        collision[i] = "1"
        blocked += 1

    walls = sum(1 for c in collision if c != "0")
    print(
        f"grid {W}x{H}: walled {blocked} visible-grass tiles "
        f"({walls} wall tiles total, {100 * walls / (W * H):.1f}% of the map)"
    )
    if args.dry_run:
        print("(dry run -- collision_maze.csv unchanged)")
        return 0

    write_flat(collision_path, collision)
    print(f"wrote {os.path.relpath(collision_path, repo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
