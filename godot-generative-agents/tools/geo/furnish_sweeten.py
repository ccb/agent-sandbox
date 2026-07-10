#!/usr/bin/env python3
"""Furnish the Sweeten Alumni Building interior (the merged Locust Walk block).

Sweeten is the carved sector ``27`` (``UPenn:Sweeten Alumni Building``) -- the
building that ``add_entrances.py`` produces by bridging the old ``3537 Locust
Walk`` footprint into Sweeten's, so the two now share one door-gated interior
and one lobby arena (``1027``). This tool lays a detailed floor on top of that
carve, the same way ``furnish_irvine.py`` / ``furnish_houston.py`` do -- in its
own ``sweeten_floor`` tile layer stacked above ``entrance_floor`` so
``add_entrances.py`` (which strips only ``entrance_*`` layers) leaves it intact
across runs.

    uv run python tools/geo/furnish_sweeten.py            # paint the floor
    uv run python tools/geo/furnish_sweeten.py --dry-run  # report, write nothing

The floor fills the walkable interior (the sector-27 footprint minus its 1-tile
perimeter ring), so a floor tile can never land on the wall ring or outside the
building. The tile is ``floor_tile_cream`` from the tile catalog -- the new
floor picked in the ``general-beds`` preset.

Idempotent: strips its own layer before re-inserting; backs up the .tmj first.
"""

import argparse
import json
import os
import shutil

from add_entrances import split_footprint

SWEETEN_SECTOR = "27"  # UPenn:Sweeten Alumni Building
SWEETEN_LOBBY = "1027"  # INTERIOR_ARENA_BASE (1000) + sector 27
FLOOR_LAYER = "sweeten_floor"

# floor_tile_cream: interior_franuka col 6, row 4 (the "cream square tile" from
# the general-beds preset). The franuka sheet is 32 tiles wide; the firstgid is
# read live from the .tmj (it shifts when the tilesets are repacked), so the gid
# can never desync into an out-of-range red-X.
FLOOR_SHEET = "franuka"
FLOOR_SHEET_COLS = 32
FLOOR_COL, FLOOR_ROW = 6, 4

OWN_LAYERS = [FLOOR_LAYER]


def read_flat(path):
    """Read a matrix maze CSV (flat, ', '-joined, row-major) into a list."""
    with open(path) as fh:
        return fh.read().strip().split(", ")


def floor_gid(tmj):
    """Live gid for floor_tile_cream: the franuka tileset's firstgid plus the
    tile's row-major offset in that 32-wide sheet."""
    firstgid = next(
        ts["firstgid"]
        for ts in tmj["tilesets"]
        if FLOOR_SHEET in (ts.get("source", "") + ts.get("image", ""))
    )
    return firstgid + FLOOR_ROW * FLOOR_SHEET_COLS + FLOOR_COL


def sweeten_interior_cells(tmj, matrix_dir):
    """Walkable interior of Sweeten as a set of flat indices: the sector-27
    footprint (sector cells painted into entrance_floor) minus its 1-tile
    perimeter ring. Computed from the footprint, not the arena id, so it stays
    correct even if the interior is later subdivided into per-room arenas."""
    W, H = tmj["width"], tmj["height"]
    ef = next(
        (
            L
            for L in tmj["layers"]
            if L.get("name") == "entrance_floor" and L.get("type") == "tilelayer"
        ),
        None,
    )
    entrance = {(i % W, i // W) for i, v in enumerate(ef["data"]) if v} if ef else set()
    sector = read_flat(os.path.join(matrix_dir, "maze", "sector_maze.csv"))
    foot = {
        (i % W, i // W) for i, s in enumerate(sector) if s == SWEETEN_SECTOR
    } & entrance
    _perimeter, interior = split_footprint(foot, W, H)
    return {y * W + x for (x, y) in interior}


def _strip(tmj, names):
    tmj["layers"] = [L for L in tmj["layers"] if L.get("name") not in names]


def _new_layer(name, data, W, H, layer_id):
    return {
        "type": "tilelayer",
        "name": name,
        "id": layer_id,
        "x": 0,
        "y": 0,
        "width": W,
        "height": H,
        "opacity": 1,
        "visible": True,
        "data": data,
    }


def apply(tmj, matrix_dir):
    """Insert the sweeten_floor layer above entrance_floor, painted only on the
    walkable interior. Returns the count of floored cells."""
    W, H = tmj["width"], tmj["height"]
    _strip(tmj, set(OWN_LAYERS))

    gid = floor_gid(tmj)
    interior = sweeten_interior_cells(tmj, matrix_dir)
    data = [0] * (W * H)
    for i in interior:
        data[i] = gid

    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    floor = _new_layer(FLOOR_LAYER, data, W, H, next_id)
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 1)

    names = [L.get("name") for L in tmj["layers"]]
    at = (
        names.index("entrance_floor") + 1
        if "entrance_floor" in names
        else len(tmj["layers"])
    )
    tmj["layers"][at:at] = [floor]
    return len(interior)


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
        "--matrix",
        default=os.path.join(
            repo, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
        ),
    )
    ap.add_argument("--dry-run", action="store_true", help="report, do not write")
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    floored = apply(tmj, args.matrix)
    print(f"{FLOOR_LAYER}: painted {floored} interior cells (GID {floor_gid(tmj)})")

    if args.dry_run:
        return
    shutil.copy(args.tmj, args.tmj + ".bak")
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")


if __name__ == "__main__":
    main()
