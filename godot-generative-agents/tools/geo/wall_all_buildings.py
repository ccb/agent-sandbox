#!/usr/bin/env python3
"""Brick-wall EVERY building on the urban .tmj — named or not.

``wall_building.py`` walls one footprint (a sim-matrix sector, or a seed cell).
This driver finds *every* connected building footprint on the ``buildings`` layer
— including the unnamed OSM ones that have no sector — and gives each a single
brick wall ring, the colour chosen from the building's own roof tint (red roof ->
terracotta brick, orange roof -> brown brick).

Buildings that already carry a deliberate wall (any Franuka brick or the grey
stone frame from a previous run) are left untouched, so hand-matched colours
(e.g. Houston's grey stone, Irvine's brown) are preserved. Re-run safe.

    uv run python godot-generative-agents/tools/geo/wall_all_buildings.py --dry-run   # list what it'd do
    uv run python godot-generative-agents/tools/geo/wall_all_buildings.py             # apply
"""

from __future__ import annotations

import argparse
import collections
import json
import os
from collections import deque

from wall_building import (
    ORANGE_FILLS,
    RED_FILLS,
    ensure_interior_tileset,
    place_thin_edge,
    tile_named,
)

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
MIN_CELLS = 12  # ignore stray specks below a plausible building size

# A footprint is "already styled" if it contains any of these: the two Franuka
# bricks, or the grey stone frame's tiles (so prior deliberate walls are kept).
GREY_FRAME_GIDS = {90, 91, 92, 117, 118, 119, 144, 145, 146}


def components(data, W, H):
    """All 4-connected runs of non-empty buildings-layer cells."""
    seen = bytearray(W * H)
    comps = []
    for i in range(W * H):
        if data[i] and not seen[i]:
            seen[i] = 1
            q = deque([i])
            cells = []
            while q:
                j = q.popleft()
                cells.append(j)
                x, y = j % W, j // W
                for dx, dy in DIRS:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H:
                        k = ny * W + nx
                        if data[k] and not seen[k]:
                            seen[k] = 1
                            q.append(k)
            comps.append(cells)
    return comps


def main():
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
        "--thin-edge",
        action="store_true",
        help="instead of brick-walling, draw the thin grey kerb around EVERY "
        "footprint (including already-styled ones). Additive; leaves walls alone.",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    W, H = tmj["width"], tmj["height"]
    data = next(L for L in tmj["layers"] if L.get("name") == "buildings")["data"]

    if args.thin_edge:
        edged = 0
        for cells in components(data, W, H):
            if len(cells) < MIN_CELLS:
                continue
            roof = {(i % W, i // W) for i in cells}
            place_thin_edge(tmj, roof, W, H, args.dry_run)
            edged += 1
        print(f"thin kerb around {edged} building(s)")
        if not args.dry_run:
            with open(args.tmj, "w") as fh:
                json.dump(tmj, fh, separators=(",", ":"))
            print(f"wrote {args.tmj}")
        return

    ensure_interior_tileset(tmj, "interior_franuka")
    terracotta = tile_named("wall_brick_red")
    brown = tile_named("wall_brick")
    styled_gids = {terracotta, brown} | GREY_FRAME_GIDS

    walled = skipped_styled = skipped_small = 0
    for cells in components(data, W, H):
        if len(cells) < MIN_CELLS:
            skipped_small += 1
            continue
        if any(data[i] in styled_gids for i in cells):
            skipped_styled += 1
            continue

        fill = collections.Counter(data[i] for i in cells).most_common(1)[0][0]
        wall = brown if fill in ORANGE_FILLS else terracotta
        colour = "brown" if wall == brown else "terracotta"
        cellset = {(i % W, i // W) for i in cells}
        xs = [x for x, _ in cellset]
        ys = [y for _, y in cellset]
        print(
            f"  wall {len(cells):4d}c  bbox x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)}"
            f"  fill {fill} -> {colour} brick"
        )
        if not args.dry_run:
            for x, y in cellset:
                data[y * W + x] = fill  # reset any old ring back to roof fill
            for x, y in cellset:
                if any((x + dx, y + dy) not in cellset for dx, dy in DIRS):
                    data[y * W + x] = wall
        walled += 1

    print(
        f"\nwalled {walled} building(s); kept {skipped_styled} already-styled; "
        f"ignored {skipped_small} specks (<{MIN_CELLS} cells)"
    )
    if args.dry_run:
        return
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj}")


if __name__ == "__main__":
    main()
