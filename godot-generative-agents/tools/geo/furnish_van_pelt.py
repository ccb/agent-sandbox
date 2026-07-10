#!/usr/bin/env python3
"""Transplant the hand-designed Van Pelt interior (van_pelt_interior.json) onto
the campus map as its own tile layers, stacked above entrance_floor. PICTURE
ONLY -- the matrix (arenas / collision) is owned by add_entrances.py.

    uv run python tools/geo/furnish_van_pelt.py

Idempotent: strips its own layers before re-inserting; backs up the .tmj first.
Cells that fall outside Van Pelt's walkable interior (the throat-seam slivers)
are clipped, so no sprite is placed on a wall or outside the building.

Ordering requirement: must run AFTER add_entrances.py so that collision_maze.csv
reflects any doorways punched through partition walls before phantom-wall clearing."""

import argparse, json, os, shutil

from add_entrances import read_flat, split_footprint

ASSET = "van_pelt_interior.json"
SECTOR = "30"  # Van Pelt Library


def load_asset(here):
    with open(os.path.join(here, ASSET)) as fh:
        return json.load(fh)


def van_pelt_interior_cells(matrix_dir, W, H, entrance_cells):
    """Van Pelt's walkable interior as a set of (x, y), order-independent of
    add_entrances: the sector-30 footprint (sector cells that are part of the
    painted building, i.e. in entrance_floor) minus its 1-tile perimeter ring."""
    sector = read_flat(os.path.join(matrix_dir, "maze", "sector_maze.csv"))
    foot = {
        (i % W, i // W) for i, s in enumerate(sector) if s == SECTOR
    } & entrance_cells
    _perimeter, interior = split_footprint(foot, W, H)
    return interior


def _strip(tmj, names):
    tmj["layers"] = [L for L in tmj["layers"] if L.get("name") not in names]


def apply(tmj, asset, matrix_dir):
    """Insert the 6 interior layers above entrance_floor, clipped to the
    interior. Returns the number of clipped (out-of-interior) cell entries."""
    W, H = tmj["width"], tmj["height"]
    order = asset["layer_order"]
    _strip(tmj, set(order))

    ef = next(
        (
            L
            for L in tmj["layers"]
            if L.get("name") == "entrance_floor" and L.get("type") == "tilelayer"
        ),
        None,
    )
    entrance_cells = (
        {(i % W, i // W) for i, v in enumerate(ef["data"]) if v} if ef else set()
    )
    interior = van_pelt_interior_cells(matrix_dir, W, H, entrance_cells)

    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    clipped = 0
    new_layers = []
    for k, name in enumerate(order):
        data = [0] * (W * H)
        for idx_s, g in asset["layers"][name].items():
            idx = int(idx_s)
            if (idx % W, idx // W) in interior:
                data[idx] = g
            else:
                clipped += 1
        new_layers.append(
            {
                "type": "tilelayer",
                "name": name,
                "id": next_id + k,
                "x": 0,
                "y": 0,
                "width": W,
                "height": H,
                "opacity": 1,
                "visible": True,
                "data": data,
            }
        )
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + len(order))

    names = [L.get("name") for L in tmj["layers"]]
    at = (
        names.index("entrance_floor") + 1
        if "entrance_floor" in names
        else len(tmj["layers"])
    )
    tmj["layers"][at:at] = new_layers

    # Clear any wing-wall sprite that sits on a walkable (collision==0) cell so
    # that doorways punched by add_entrances.py are not blocked by phantom walls.
    collision = read_flat(os.path.join(matrix_dir, "maze", "collision_maze.csv"))
    wall_names = {"westwing_walls", "eastwing_walls"}
    for layer in new_layers:
        if layer["name"] in wall_names:
            for i, v in enumerate(layer["data"]):
                if v != 0 and collision[i] == "0":
                    layer["data"][i] = 0

    return clipped


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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    asset = load_asset(here)
    with open(args.tmj) as fh:
        tmj = json.load(fh)
    clipped = apply(tmj, asset, args.matrix)
    print(f"transplanted {len(asset['layer_order'])} layers; clipped {clipped} cells")
    if args.dry_run:
        return
    shutil.copy2(args.tmj, args.tmj + ".bak")
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")


if __name__ == "__main__":
    main()
