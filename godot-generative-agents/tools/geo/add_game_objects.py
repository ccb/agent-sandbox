#!/usr/bin/env python3
"""Paint interactable furniture into the game_object matrix layer.

Reads every hand-authored ``*_objects`` object layer of upenn_core_urban.tmj
(``fisher_objects``, ``houston_objects``, ...): each object is a named rect marking
the WALKABLE use-tile(s) for one interactable piece (the floor in front of a
bookshelf, the seat of a reading chair). For each object this:

  1. re-opens its cells walkable (collision -> "0"), so a use-tile survives
     block_furniture's blanket solidity;
  2. paints the object's id into game_object_maze.csv;
  3. writes a row into special_blocks/game_object_blocks.csv.

The id scheme parallels arenas and numbers per sector: id = 100000 + sector*1000 +
idx, where idx is numbered per sector so buildings never renumber each other. The
resulting address `UPenn:<sector>:<arena>:<object>` resolves via world_map.py
unchanged.

Run LAST, after add_entrances.py, block_grass.py, block_furniture.py. No-ops if no
``*_objects`` layer is present (objects not authored yet).

    uv run python godot-generative-agents/tools/geo/add_game_objects.py --dry-run
    uv run python godot-generative-agents/tools/geo/add_game_objects.py
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter

WORLD = "UPenn"
OBJECT_LAYER_SUFFIX = "_objects"
FISHER_SECTOR = "34"
GAME_OBJECT_BASE = 100000


def read_flat(path: str) -> list[str]:
    return open(path).read().strip().split(", ")


def write_flat(path: str, cells: list[str]) -> None:
    with open(path, "w") as fh:
        fh.write(", ".join(cells))


def read_blocks(path: str) -> list[list[str]]:
    rows = []
    with open(path) as fh:
        for line in fh:
            if line.strip():
                rows.append([p.strip() for p in line.split(",")])
    return rows


def write_blocks(path: str, rows: list[list[str]]) -> None:
    with open(path, "w") as fh:
        for row in rows:
            fh.write(", ".join(str(c) for c in row) + "\n")


def _obj_rect(o: dict) -> tuple[int, int, int, int]:
    c0 = round(o["x"] / 16)
    r0 = round(o["y"] / 16)
    c1 = round((o["x"] + o["width"]) / 16) - 1
    r1 = round((o["y"] + o["height"]) / 16) - 1
    return c0, r0, c1, r1


def read_objects(tmj: dict) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Named rects from every ``*_objects`` objectgroup, in tmj layer order."""
    out = []
    for layer in tmj["layers"]:
        if layer.get("type") != "objectgroup":
            continue
        if not (layer.get("name") or "").endswith(OBJECT_LAYER_SUFFIX):
            continue
        for o in layer.get("objects", []):
            name = o.get("name") or ""
            if name:
                out.append((name, _obj_rect(o)))
    return out


def _rect_cells(rect, W, H):
    c0, r0, c1, r1 = rect
    return [
        (x, y)
        for y in range(max(0, r0), min(H - 1, r1) + 1)
        for x in range(max(0, c0), min(W - 1, c1) + 1)
    ]


def paint_objects(tmj, collision, arena, sector, sector_names, W, H):
    """Return (new_collision, new_object_maze, block_rows). Pure."""
    coll = list(collision)
    obj_maze = ["0"] * (W * H)
    rows = []
    per_sector: Counter = Counter()
    for name, rect in read_objects(tmj):
        cells = _rect_cells(rect, W, H)
        if not cells:
            continue  # degenerate rect (fully out of bounds) -- paint nothing
        sid_counts = Counter(sector[y * W + x] for (x, y) in cells)
        sid = sid_counts.most_common(1)[0][0]
        goid = str(GAME_OBJECT_BASE + int(sid) * 1000 + per_sector[sid])
        per_sector[sid] += 1
        arena_counts = Counter(
            arena[y * W + x] for (x, y) in cells if arena[y * W + x] != "0"
        )
        arena_name = ""  # informational column; label lookup happens elsewhere
        for x, y in cells:
            i = y * W + x
            coll[i] = "0"  # re-open the use-tile
            obj_maze[i] = goid  # tag it
        rows.append(
            [
                goid,
                WORLD,
                sector_names.get(sid, sid),
                arena_name
                or (arena_counts.most_common(1)[0][0] if arena_counts else ""),
                name,
            ]
        )
    return coll, obj_maze, rows


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
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
    maze = os.path.join(args.matrix, "maze")
    blocks = os.path.join(args.matrix, "special_blocks")
    collision = read_flat(os.path.join(maze, "collision_maze.csv"))
    arena = read_flat(os.path.join(maze, "arena_maze.csv"))
    sector = read_flat(os.path.join(maze, "sector_maze.csv"))
    sector_names = {
        r[0]: r[-1]
        for r in read_blocks(os.path.join(blocks, "sector_blocks.csv"))
        if len(r) >= 3
    }

    coll, obj_maze, rows = paint_objects(
        tmj, collision, arena, sector, sector_names, W, H
    )
    print(
        f"painted {len(rows)} game objects ({sum(1 for g in obj_maze if g != '0')} cells)"
    )
    if args.dry_run:
        print("(dry run -- nothing written)")
        return 0
    write_flat(os.path.join(maze, "collision_maze.csv"), coll)
    write_flat(os.path.join(maze, "game_object_maze.csv"), obj_maze)
    write_blocks(os.path.join(blocks, "game_object_blocks.csv"), rows)
    print(f"wrote game_object_maze.csv + game_object_blocks.csv ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
