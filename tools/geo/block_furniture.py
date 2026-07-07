#!/usr/bin/env python3
"""Make furniture un-walkable: bake `*_furniture` tile art into the collision matrix.

Furniture is drawn as anonymous tiles on per-building `*_furniture` layers of
`upenn_core_urban.tmj`, but the agent pathfinder only reads
`the_upenn/matrix/maze/collision_maze.csv` (a tile is walkable iff its cell is
"0"). Until now furniture was invisible to pathing, so agents walked through it.

This walls off every furniture tile cell, EXCEPT base gids in WALKABLE_FURNITURE
(chair seats, stools, benches -- things an agent stands/sits on). Rugs live on
separate `*_rugs` layers and are never touched. Run AFTER add_entrances.py and
block_grass.py.

Idempotent: solidity is derived from the (unchanged) `*_furniture` layers, not
from the collision it writes, so running twice is a no-op.

    uv run python tools/geo/block_furniture.py --catalog   # list furniture gids
    uv run python tools/geo/block_furniture.py --dry-run    # report, change nothing
    uv run python tools/geo/block_furniture.py              # wall the furniture
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter

GID_MASK = 0x1FFFFFFF  # strip Tiled's flip flags before comparing gids
SOLID_FURNITURE_LAYERS_SUFFIX = "_furniture"

WALKABLE_FURNITURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "walkable_furniture.json"
)


def load_walkable_furniture(path: str = WALKABLE_FURNITURE_PATH) -> set[int]:
    """Base gids that stay WALKABLE (chair seats, stools, floor cushions), loaded
    from walkable_furniture.json. Empty set if the file is absent. Use `--catalog`
    to list furniture gids and the 'Furniture solidity' menu in catalog_web.py to
    edit the file."""
    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return set()
    return {int(g) for g in data.get("walkable_gids", {})}


# Base gids that stay WALKABLE despite living on a furniture layer: chair seats,
# stools, floor cushions -- tiles an agent can stand or sit on. Empty means
# "all furniture is solid".
WALKABLE_FURNITURE: set[int] = load_walkable_furniture()


def is_solid_layer(name: str) -> bool:
    return name.endswith(SOLID_FURNITURE_LAYERS_SUFFIX)


def read_flat(path: str) -> list[str]:
    return open(path).read().strip().split(", ")


def write_flat(path: str, cells: list[str]) -> None:
    with open(path, "w") as fh:
        fh.write(", ".join(cells))


def _solid_layers(tmj: dict) -> list[dict]:
    return [
        L
        for L in tmj["layers"]
        if L.get("type") == "tilelayer" and is_solid_layer(L["name"])
    ]


def furniture_gid_counts(tmj: dict) -> Counter:
    counts: Counter = Counter()
    for L in _solid_layers(tmj):
        for g in L["data"]:
            if g:
                counts[g & GID_MASK] += 1
    return counts


def tileset_of(gid: int, tilesets: list[dict]) -> tuple[str, int]:
    best = None
    for ts in tilesets:
        first = ts["firstgid"]
        if gid >= first and (best is None or first > best[0]):
            best = (first, ts.get("name", "?"))
    if best is None:
        return ("?", gid)
    return (best[1], gid - best[0])


def solid_cells(
    tmj: dict, collision: list[str], walkable_gids: set[int]
) -> tuple[list[str], int]:
    """Return a NEW collision list with every furniture cell sealed to "1",
    except empty cells, already-walls, and cells whose base gid is walkable."""
    out = list(collision)
    sealed = 0
    for L in _solid_layers(tmj):
        for i, g in enumerate(L["data"]):
            if not g:
                continue
            if out[i] != "0":
                continue  # already a wall
            if (g & GID_MASK) in walkable_gids:
                continue  # a seat / walk-on tile
            out[i] = "1"
            sealed += 1
    return out, sealed


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
    ap.add_argument(
        "--catalog", action="store_true", help="list furniture gids and exit"
    )
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))

    if args.catalog:
        counts = furniture_gid_counts(tmj)
        print(f"{len(counts)} distinct furniture gids across *_furniture layers:")
        for gid, n in counts.most_common():
            ts_name, local = tileset_of(gid, tmj.get("tilesets", []))
            mark = " [WALKABLE]" if gid in WALKABLE_FURNITURE else ""
            print(f"  gid {gid:>6}  {ts_name}#{local:<4} x{n}{mark}")
        return 0

    W, H = tmj["width"], tmj["height"]
    collision_path = os.path.join(args.matrix, "maze", "collision_maze.csv")
    collision = read_flat(collision_path)
    if len(collision) != W * H:
        raise SystemExit(
            f"collision has {len(collision)} cells, .tmj is {W}x{H}={W * H}"
        )

    new_collision, sealed = solid_cells(tmj, collision, WALKABLE_FURNITURE)
    walls = sum(1 for c in new_collision if c != "0")
    print(
        f"grid {W}x{H}: sealed {sealed} furniture tiles "
        f"({walls} wall tiles total, {100 * walls / (W * H):.1f}% of the map)"
    )
    if args.dry_run:
        print("(dry run -- collision_maze.csv unchanged)")
        return 0
    write_flat(collision_path, new_collision)
    print(f"wrote {os.path.relpath(collision_path, repo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
