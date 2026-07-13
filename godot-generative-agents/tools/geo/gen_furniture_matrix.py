#!/usr/bin/env python3
"""Export furniture as first-class matrix data (#537).

The tmj's `*_furniture` layers know where furniture is; furniture_catalog.json
knows what the tiles are. The sim sees neither: block_furniture.py seals
furniture into collision_maze.csv, byte-identical to walls. This script joins
the two and emits, in the existing matrix conventions:

    <matrix>/maze/furniture_maze.csv            per-cell piece id, 0 elsewhere
    <matrix>/special_blocks/furniture_blocks.csv  id, world, sector, arena, name

so WorldMap can derive furniture-aware destinations (seat spots), and #446's
future sit/use verbs have identities to name. `--debug-overlay` also writes a
git-ignored Tiled overlay (labeled rectangle per piece + a point per derived
seat spot) for eyeballing placements:

    uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py
    uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py --debug-overlay

Reads the committed tmj (never writes it). Idempotent: output depends only on
the tmj + catalog + arena/collision matrices.
"""

from __future__ import annotations

import argparse
import json
import os

from block_furniture import GID_MASK, _solid_layers, read_flat

CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "furniture_catalog.json"
)


EXCLUDED_CATEGORIES = {"wall", "window", "door"}


def excluded_gids(catalog: dict, tilesets: list[dict]) -> set[int]:
    """Every footprint gid of catalog entries whose category is structural
    (wall/window/door). Painted on `*_furniture` layers only so
    block_furniture seals them (williams_furniture carries 46 window tiles);
    they are NOT furniture and must not grow seat spots along the walls."""
    firstgid = {ts.get("name"): ts["firstgid"] for ts in tilesets}
    out: set[int] = set()
    for key, obj in catalog.get("objects", {}).items():
        if key.startswith("_") or not isinstance(obj, dict):
            continue
        if obj.get("category") not in EXCLUDED_CATEGORIES:
            continue
        sheet = catalog["sheets"].get(obj.get("sheet"), {})
        base = firstgid.get(obj.get("sheet"))
        cols = sheet.get("cols")
        if base is None or cols is None:
            continue
        for dy in range(int(obj.get("h", 1))):
            for dx in range(int(obj.get("w", 1))):
                out.add(base + (obj["row"] + dy) * cols + (obj["col"] + dx))
    return out


def pieces(tmj: dict, excluded: frozenset | set = frozenset()) -> list[dict]:
    """Contiguous furniture pieces across all `*_furniture` layers.

    4-connected nonzero cells within one layer form a piece (multi-tile
    furniture is placed as a block of DIFFERENT atlas gids, so grouping by
    gid would shatter one desk into six instances). Cells whose base gid is
    in `excluded` (structural wall/window/door tiles) are treated as empty.
    Returns row-major-ordered pieces of {"cells": [(x, y)...], "anchor_gid":
    top-left cell's base gid, "gids": base gids row-major}.
    """
    width = tmj["width"]
    out: list[dict] = []
    for layer in _solid_layers(tmj):
        data = [0 if (g and (g & GID_MASK) in excluded) else g for g in layer["data"]]
        seen: set[int] = set()
        for start, g in enumerate(data):
            if not g or start in seen:
                continue
            stack, cells = [start], []
            seen.add(start)
            while stack:
                idx = stack.pop()
                cells.append(idx)
                x, y = idx % width, idx // width
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    n = ny * width + nx
                    if (
                        0 <= nx < width
                        and 0 <= ny < tmj["height"]
                        and n not in seen
                        and data[n]
                    ):
                        seen.add(n)
                        stack.append(n)
            cells.sort()  # row-major: the first cell is the top-left anchor
            out.append(
                {
                    "cells": [(i % width, i // width) for i in cells],
                    "anchor_gid": data[cells[0]] & GID_MASK,
                    "gids": [data[i] & GID_MASK for i in cells],
                }
            )
    return out


def gid_names(catalog: dict, tilesets: list[dict]) -> dict[int, str]:
    """gid -> catalog object key, every footprint cell covered.

    An object at (col, row) with footprint w x h on a sheet occupies the
    w*h gids of that atlas block; all of them map to the object's key so a
    piece can be named from any of its cells.
    """
    firstgid = {ts.get("name"): ts["firstgid"] for ts in tilesets}
    names: dict[int, str] = {}
    for key, obj in catalog.get("objects", {}).items():
        if key.startswith("_") or not isinstance(obj, dict):
            continue
        sheet = catalog["sheets"].get(obj.get("sheet"), {})
        base = firstgid.get(obj.get("sheet"))
        cols = sheet.get("cols")
        if base is None or cols is None:
            continue
        for dy in range(int(obj.get("h", 1))):
            for dx in range(int(obj.get("w", 1))):
                gid = base + (obj["row"] + dy) * cols + (obj["col"] + dx)
                names[gid] = key
    return names


def piece_name(piece: dict, names: dict[int, str]) -> str:
    """The anchor cell's catalog name; else any covered cell's; else tile-<gid>
    (emitted, not dropped -- the overlay makes catalog gaps visible)."""
    if piece["anchor_gid"] in names:
        return names[piece["anchor_gid"]]
    for gid in piece["gids"]:
        if gid in names:
            return names[gid]
    return f"tile-{piece['anchor_gid']}"


def spots(
    furn: list[str], collision: list[str], width: int, height: int
) -> list[tuple[int, int]]:
    """Walkable cells ON furniture (walkable seats) or 4-adjacent to it,
    row-major. The same rule WorldMap derives at load; duplicated ~10 lines
    by design so tools/geo never imports backend."""
    out = []
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if collision[idx] != "0":
                continue
            if furn[idx] != "0":
                out.append((x, y))
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    if furn[ny * width + nx] != "0":
                        out.append((x, y))
                        break
    return out


def _majority_label(cells, maze, table, width):
    counts: dict[str, int] = {}
    for x, y in cells:
        label = table.get(maze[y * width + x])
        if label:
            counts[label] = counts.get(label, 0) + 1
    return max(counts, key=counts.get) if counts else ""


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
    ap.add_argument("--catalog", default=CATALOG_PATH)
    ap.add_argument(
        "--debug-overlay",
        action="store_true",
        help="also write tools/geo/out/upenn_furniture_debug.tmj",
    )
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    catalog = json.load(open(args.catalog))
    W, H = tmj["width"], tmj["height"]
    names = gid_names(catalog, tmj.get("tilesets", []))
    skip = excluded_gids(catalog, tmj.get("tilesets", []))

    def rows(path):  # id -> label table, world row is single
        return {
            r.split(",")[0].strip(): r.split(",")[-1].strip()
            for r in open(path).read().strip().splitlines()
            if r.strip()
        }

    blocks_dir = os.path.join(args.matrix, "special_blocks")
    world = open(os.path.join(blocks_dir, "world_blocks.csv")).read().strip()
    world = world.split(",")[-1].strip()
    sector_t = rows(os.path.join(blocks_dir, "sector_blocks.csv"))
    arena_t = rows(os.path.join(blocks_dir, "arena_blocks.csv"))
    maze_dir = os.path.join(args.matrix, "maze")
    sector_m = read_flat(os.path.join(maze_dir, "sector_maze.csv"))
    arena_m = read_flat(os.path.join(maze_dir, "arena_maze.csv"))
    collision = read_flat(os.path.join(maze_dir, "collision_maze.csv"))

    n_skipped = sum(
        1 for L in _solid_layers(tmj) for g in L["data"] if g and (g & GID_MASK) in skip
    )
    if n_skipped:
        print(f"excluded {n_skipped} wall/window/door cells (not furniture)")
    all_pieces = pieces(tmj, excluded=skip)
    furn = ["0"] * (W * H)
    block_rows = []
    for pid, piece in enumerate(all_pieces, start=1):
        for x, y in piece["cells"]:
            furn[y * W + x] = str(pid)
        block_rows.append(
            f"{pid}, {world}, "
            f"{_majority_label(piece['cells'], sector_m, sector_t, W)}, "
            f"{_majority_label(piece['cells'], arena_m, arena_t, W)}, "
            f"{piece_name(piece, names)}"
        )

    with open(os.path.join(maze_dir, "furniture_maze.csv"), "w") as fh:
        fh.write(", ".join(furn))
    with open(os.path.join(blocks_dir, "furniture_blocks.csv"), "w") as fh:
        fh.write("\n".join(block_rows))
    print(f"{len(all_pieces)} pieces -> furniture_maze.csv + furniture_blocks.csv")

    if args.debug_overlay:
        tile = tmj.get("tilewidth", 16)
        objects = []
        for pid, piece in enumerate(all_pieces, start=1):
            xs = [x for x, _ in piece["cells"]]
            ys = [y for _, y in piece["cells"]]
            sector = _majority_label(piece["cells"], sector_m, sector_t, W)
            arena = _majority_label(piece["cells"], arena_m, arena_t, W)
            objects.append(
                {
                    "id": pid,
                    "name": f"{piece_name(piece, names)} — {sector}: {arena}",
                    "type": "furniture",
                    "x": min(xs) * tile,
                    "y": min(ys) * tile,
                    "width": (max(xs) - min(xs) + 1) * tile,
                    "height": (max(ys) - min(ys) + 1) * tile,
                    "visible": True,
                }
            )
        for i, (x, y) in enumerate(spots(furn, collision, W, H)):
            objects.append(
                {
                    "id": len(all_pieces) + 1 + i,
                    "name": "spot",
                    "type": "spot",
                    "point": True,
                    "x": (x + 0.5) * tile,
                    "y": (y + 0.5) * tile,
                    "visible": True,
                }
            )
        overlay = dict(tmj)
        overlay["layers"] = list(tmj["layers"]) + [
            {
                "type": "objectgroup",
                "name": "furniture_debug",
                "id": max(L.get("id", 0) for L in tmj["layers"]) + 1,
                "objects": objects,
                "visible": True,
                "opacity": 1,
                "x": 0,
                "y": 0,
            }
        ]
        out_dir = os.path.join(here, "out")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "upenn_furniture_debug.tmj")
        json.dump(overlay, open(out_path, "w"))
        print(f"wrote {os.path.relpath(out_path, repo)} (open in Tiled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
