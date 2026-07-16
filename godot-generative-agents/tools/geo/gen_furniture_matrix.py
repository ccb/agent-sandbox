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


def _sheet_firstgids(catalog: dict, tilesets: list[dict]) -> dict[str, int]:
    """Catalog sheet key -> tmj firstgid. Catalog sheets use short names
    ("franuka"); the tmj's tilesets carry asset-flavored ones
    ("interior_franuka", "kenney_urban") -- match exact, interior_-prefixed,
    or a UNIQUE "<sheet>_"-prefixed name. Unmatched or ambiguous sheets
    raise: a renamed tileset must never silently disable the identity join
    again (it once turned every piece into tile-<gid> with zero signal)."""
    out: dict[str, int] = {}
    names = {ts.get("name"): ts["firstgid"] for ts in tilesets}
    for sheet in catalog.get("sheets", {}):
        for candidate in (sheet, f"interior_{sheet}"):
            if candidate in names:
                out[sheet] = names[candidate]
                break
        else:
            prefixed = [n for n in names if n and n.startswith(f"{sheet}_")]
            if len(prefixed) == 1:
                out[sheet] = names[prefixed[0]]
            elif len(prefixed) > 1:
                raise ValueError(
                    f"catalog sheet {sheet!r} matches several tilesets: {sorted(prefixed)}"
                )
            else:
                raise ValueError(
                    f"catalog sheet {sheet!r} matches no tmj tileset "
                    f"(have: {sorted(n for n in names if n)})"
                )
    return out


def excluded_gids(catalog: dict, tilesets: list[dict]) -> set[int]:
    """Every footprint gid of catalog entries whose category is structural
    (wall/window/door). Painted on `*_furniture` layers only so
    block_furniture seals them (williams_furniture carries 46 window tiles);
    they are NOT furniture and must not grow seat spots along the walls."""
    firstgid = _sheet_firstgids(catalog, tilesets)
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
    firstgid = _sheet_firstgids(catalog, tilesets)
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


def structural_cells(tmj: dict, structural_gids: set[int]) -> set[int]:
    """Flat indices of cells drawing a wall/window/door tile on ANY layer.

    ``excluded_gids`` only matters on ``*_furniture`` layers (it keeps
    structural tiles out of furniture_maze). This is broader: Williams'
    interior walls are painted on ``williams_floor`` and left
    collision-walkable, so a furniture-adjacent floor scan would drop seat
    spots onto them -- this mask (from the tmj, the only place the wall
    identity survives) excludes them."""
    out: set[int] = set()
    for layer in tmj.get("layers", []):
        if layer.get("type") != "tilelayer" or "data" not in layer:
            continue
        for i, g in enumerate(layer["data"]):
            if g and (g & GID_MASK) in structural_gids:
                out.add(i)
    return out


_WALK_ON = ("cushion", "armchair", "chair", "stool", "sofa", "desk")


def _decorative(name: str) -> bool:
    """Rugs and floor-lamps are decorative area-fills, not interaction
    targets, so they get no spot (#537). Matched by name: any ``rug`` and
    floor-standing lamps (``floor``+``lamp`` -- floor_lamp, clockwork_lamp_
    floor -- but not candelabra/lantern/lights, which carry no "lamp")."""
    n = name.lower()
    return "rug" in n or ("lamp" in n and "floor" in n)


def piece_spot(
    piece: dict,
    furn: list[str],
    collision: list[str],
    arena_m: list[str],
    arena_t: dict[str, str],
    structural: set[int],
    names: dict[int, str],
    width: int,
    height: int,
) -> tuple[int, int] | None:
    """The single interaction spot for one furniture piece, or None (#537).

    Walk-on pieces (cushion/armchair/chair/stool/sofa/desk-with-chair) get a
    tile ON the piece -- its walkable seat/cushion/chair tile nearest the
    centre. Every other piece (blackboard/sink/bookshelf/table/...) gets the
    floor tile in front -- the nearest walkable, non-structural, same-arena
    cell 4-adjacent to the piece. Nearest-to-centre with a row-major
    tiebreak, so the choice is deterministic. Merged-blob-robust: no
    per-type table, no orientation data."""
    cells = piece["cells"]
    cx = sum(x for x, _ in cells) / len(cells)
    cy = sum(y for _, y in cells) / len(cells)

    def nearest(cands):
        return (
            min(cands, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[1], p[0]))
            if cands
            else None
        )

    name = names.get(piece["anchor_gid"], "").lower()
    if _decorative(name):
        return None
    if any(stem in name for stem in _WALK_ON):
        on_piece = [
            (x, y)
            for (x, y) in cells
            if collision[y * width + x] == "0" and (y * width + x) not in structural
        ]
        spot = nearest(on_piece)
        if spot is not None:
            return spot

    # Front bucket: nearest same-arena floor tile touching the piece.
    arena = _majority_label(cells, arena_m, arena_t, width)
    if not arena:
        return None
    cellset = set(cells)
    front = set()
    for x, y in cells:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < width and 0 <= ny < height) or (nx, ny) in cellset:
                continue
            nidx = ny * width + nx
            if (
                furn[nidx] == "0"
                and collision[nidx] == "0"
                and nidx not in structural
                and arena_t.get(arena_m[nidx], "") == arena
            ):
                front.add((nx, ny))
    return nearest(front)


def _majority_label(cells, maze, table, width):
    counts: dict[str, int] = {}
    for x, y in cells:
        label = table.get(maze[y * width + x])
        if label:
            counts[label] = counts.get(label, 0) + 1
    # Ties break on first-encountered label (row-major cell order) -- rare:
    # only a piece split exactly across a sector/arena boundary.
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
        fh.write("".join(r + "\n" for r in block_rows))
    print(f"{len(all_pieces)} pieces -> furniture_maze.csv + furniture_blocks.csv")

    structural = structural_cells(tmj, skip)
    spot_cells = []
    spot_rows = []
    for piece in all_pieces:
        spot = piece_spot(
            piece, furn, collision, arena_m, arena_t, structural, names, W, H
        )
        if spot is None:
            continue
        x, y = spot
        sector = _majority_label(piece["cells"], sector_m, sector_t, W)
        arena = _majority_label(piece["cells"], arena_m, arena_t, W)
        name = piece_name(piece, names)
        spot_cells.append((x, y))
        spot_rows.append(f"{world}, {sector}, {arena}, {x}, {y}, {name}")
    with open(os.path.join(blocks_dir, "furniture_spots.csv"), "w") as fh:
        fh.write("".join(r + "\n" for r in spot_rows))
    print(f"{len(spot_rows)} interaction spots (one per piece) -> furniture_spots.csv")

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
        for i, (x, y) in enumerate(spot_cells):
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
        out_dir = os.path.join(here, "out")
        os.makedirs(out_dir, exist_ok=True)
        # The overlay lives in tools/geo/out/ -- three dirs from the tmj's own
        # folder -- so its tilesets' `image` paths (bare filenames Tiled
        # resolves relative to THIS file) would 404 and every tile would draw
        # as the missing-texture hatch. Repoint each image at the real PNG
        # relative to out/, so the base map renders under the debug layer.
        src_dir = os.path.dirname(os.path.abspath(args.tmj))
        tilesets = []
        for ts in tmj.get("tilesets", []):
            if "image" in ts:
                img = os.path.normpath(os.path.join(src_dir, ts["image"]))
                ts = dict(ts, image=os.path.relpath(img, out_dir))
            tilesets.append(ts)
        overlay = dict(tmj)
        overlay["tilesets"] = tilesets
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
        out_path = os.path.join(out_dir, "upenn_furniture_debug.tmj")
        json.dump(overlay, open(out_path, "w"))
        print(f"wrote {os.path.relpath(out_path, repo)} (open in Tiled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
