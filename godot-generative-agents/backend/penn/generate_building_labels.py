"""Write the building name-plates the Godot campus viewer floats over the map.

The replay viewer (`scenes/viewer.tscn`) shows a label over each building
when you're zoomed all the way out, fading it as you zoom in. Godot can't read
the Python world, so -- exactly like `generate_penn_replay.py` -- we precompute a
tiny JSON here that the scene loads at startup.

Every building the sim knows about is a "sector": `the_upenn/matrix` stores its
name in `special_blocks/sector_blocks.csv` and, in `maze/sector_maze.csv`, the
sector id of every tile (0 = no sector). We average each sector's tiles to get
its centre tile, then hand Godot `{name, x, y}` in that same tile grid -- the
exact grid the agents walk -- so `building_labels.gd` can drop the name-plate
over the building with the agents' own tile->world transform.

Run from the repo root::

    uv run python godot-generative-agents/backend/penn/generate_building_labels.py

Writes: godot-generative-agents/godot/maps/building_labels.json
"""

import argparse
import csv
import json
import os

_SIM_DIR = os.path.dirname(
    os.path.abspath(__file__)
)  # .../godot-generative-agents/backend/penn
_GG_DIR = os.path.dirname(os.path.dirname(_SIM_DIR))  # .../godot-generative-agents
_GODOT_DIR = os.path.join(_GG_DIR, "godot")  # the Godot project (its res:// root)

MATRIX_DIR = os.path.join(_SIM_DIR, "the_upenn", "matrix")
SECTOR_BLOCKS = os.path.join(MATRIX_DIR, "special_blocks", "sector_blocks.csv")
SECTOR_MAZE = os.path.join(MATRIX_DIR, "maze", "sector_maze.csv")
META_PATH = os.path.join(MATRIX_DIR, "maze_meta_info.json")
OUT_PATH = os.path.join(_GODOT_DIR, "maps", "building_labels.json")


def load_sector_names(path: str) -> dict[int, str]:
    """sector_blocks.csv rows are `id, World, Building Name`."""
    names: dict[int, str] = {}
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if len(row) < 3 or not row[0].strip():
                continue
            names[int(row[0])] = row[-1].strip()
    return names


def sector_centres(path: str, width: int) -> dict[int, tuple[float, float]]:
    """Average each sector's tiles into a single centre tile (x = col, y = row).

    `sector_maze.csv` is one long, row-major list of `width * height` sector ids
    (the generative-agents matrix format), so tile `i` sits at column `i % width`,
    row `i // width`. The mean lands a label at the visual middle of the building.
    A sector split into disconnected pieces would average to a point between them,
    but Penn's buildings are contiguous, so the simple mean reads correctly.
    """
    sums: dict[int, list[float]] = {}  # sector id -> [x_total, y_total, count]
    with open(path, newline="") as f:
        cells = next(csv.reader(f))
    for i, cell in enumerate(cells):
        cell = cell.strip()
        if not cell:
            continue
        sector = int(cell)
        if sector == 0:
            continue
        acc = sums.setdefault(sector, [0.0, 0.0, 0.0])
        acc[0] += i % width
        acc[1] += i // width
        acc[2] += 1
    return {s: (xt / n, yt / n) for s, (xt, yt, n) in sums.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate building labels for Godot.")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    with open(META_PATH) as f:
        meta = json.load(f)
    tile_px = int(meta["sq_tile_size"])

    names = load_sector_names(SECTOR_BLOCKS)
    centres = sector_centres(SECTOR_MAZE, int(meta["maze_width"]))

    buildings = []
    for sector, name in sorted(names.items()):
        if sector not in centres:
            print(f"  (skipping {name!r}: sector {sector} has no tiles in the maze)")
            continue
        x, y = centres[sector]
        buildings.append({"name": name, "x": round(x, 2), "y": round(y, 2)})

    payload = {"tile_px": tile_px, "buildings": buildings}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1)
        f.write("\n")
    print(f"Wrote {len(buildings)} building labels to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
