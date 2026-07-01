"""Turn the OSM campus into a Generative-Agents "maze" the backend can walk.

`osm_to_tiled.py` makes a *picture* (a Tiled tilemap). This makes the *world
data* the agent backend needs: the same the_ville matrix format that
`backend/world_map.py` already loads — a folder of flat CSV
"maze" layers plus "block" lookup tables:

    matrix/
      maze_meta_info.json                  grid size, tile size, world name
      maze/collision_maze.csv              0 = walkable, non-0 = wall (one flat row)
      maze/sector_maze.csv                 tile -> sector id  (a named building)
      maze/arena_maze.csv                  tile -> arena id   (a place in a sector)
      maze/game_object_maze.csv            tile -> object id  (none, from OSM)
      maze/spawning_location_maze.csv      tile -> spawn id   (none)
      special_blocks/world_blocks.csv      id, world
      special_blocks/sector_blocks.csv     id, world, sector
      special_blocks/arena_blocks.csv      id, world, sector, arena
      special_blocks/game_object_blocks.csv
      special_blocks/spawning_location_blocks.csv

We derive it from the very same OpenStreetMap data the tilemap uses:

  * collision = building footprints + water areas -> walls; everything else
    (streets, paths, lawns) walkable.
  * sectors   = each *named* OSM building (College Hall, Van Pelt, ...). Its
    footprint is a wall, so we also tag the walkable "apron" — the ring of tiles
    right around it, the doorstep an agent can actually stand on. WorldMap's
    pathfinder routes to those, so "go to College Hall" means "walk to its edge".
  * arenas    = one per building, named "grounds" (OSM has no interior rooms).
  * objects / spawns = empty (OSM has no furniture); the files are still written
    so WorldMap, which reads all five layers, is happy.

So an address resolves as  ``UPenn:<building>:grounds`` — exactly what a Penn
`world_data.yaml` location's ``tile_address`` should be.

Output goes to the **tracked** frontend_overrides tree, which `setup.sh` rsyncs
into the (git-ignored) `frontend/`. The backend can also read it straight from
there, so a headless run needs no `setup.sh`:
    generative-agents/frontend_overrides/static_dirs/assets/the_upenn/

Usage:
    uv run python tools/geo/osm_to_ville.py              # core area (default)
    uv run python tools/geo/osm_to_ville.py --area campus
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Reuse the tilemap tool's fetch/projection/rasterisation so the maze lines up
# tile-for-tile with the picture (same bbox, rotation, metres-per-tile).
from osm_to_tiled import (
    AREAS,
    METRES_PER_TILE,
    OUT_DIR,
    TILE_PX,
    Projector,
    categorise,
    crop_to_streets,
    fetch_osm,
    polygon_cells,
    resolve_rotation,
)

WORLD_NAME = "UPenn"
ARENA_NAME = "grounds"  # OSM has no rooms; every building gets one generic arena

_HERE = os.path.dirname(os.path.abspath(__file__))
_GA = os.path.normpath(os.path.join(_HERE, "..", "..", "generative-agents"))
DEFAULT_OUT = os.path.join(
    _GA, "frontend_overrides", "static_dirs", "assets", "the_upenn"
)

# 4-connectivity, matching the backend pathfinder's moves.
NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def wall_and_named(osm: dict, proj: Projector):
    """Return (blocked, named).

    `blocked` is the set of every wall cell (any building footprint or water
    area). `named` maps a building name -> the set of cells in its footprint
    (only buildings that carry an OSM `name` tag; the rest still wall, but get
    no sector).
    """
    cols, rows = proj.cols, proj.rows
    blocked: set[tuple[int, int]] = set()
    named: dict[str, set[tuple[int, int]]] = {}
    for el in osm.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        cat = categorise(tags)
        if cat is None:
            continue
        category, kind = cat
        # Only filled areas wall a tile off; skip waterway *lines* (thin rivers).
        if category not in ("building", "water") or kind != "area":
            continue
        pts = [proj.to_tile(nd["lat"], nd["lon"]) for nd in el["geometry"]]
        cells = set(polygon_cells(pts, cols, rows))
        blocked |= cells
        name = tags.get("name")
        if category == "building" and name:
            named.setdefault(name, set()).update(cells)
    return blocked, named


def apron_of(foot: set, blocked: set, cols: int, rows: int) -> set:
    """The walkable tiles 4-adjacent to a footprint — its reachable doorstep."""
    apron = set()
    for c, r in foot:
        for dc, dr in NEIGHBOURS:
            cc, rr = c + dc, r + dr
            if 0 <= cc < cols and 0 <= rr < rows and (cc, rr) not in blocked:
                apron.add((cc, rr))
    return apron


def build_matrix(osm: dict, proj: Projector):
    """Build the maze layers + block tables from the OSM features.

    Returns a dict ready for `write_matrix`, plus `reachable` (building -> a
    sample walkable tile) so a human can author `world_data` start tiles.
    """
    cols, rows = proj.cols, proj.rows
    n = cols * rows
    blocked, named = wall_and_named(osm, proj)

    def at(c, r):
        return r * cols + c

    collision = ["0"] * n
    for c, r in blocked:
        collision[at(c, r)] = "1"

    sector_maze = ["0"] * n
    arena_maze = ["0"] * n
    sector_blocks: list[tuple[int, str]] = []
    arena_blocks: list[tuple[int, str, str]] = []
    reachable: dict[str, list[int]] = {}

    # Sorted names -> deterministic ids across runs.
    for sid, name in enumerate(sorted(named), start=1):
        foot = named[name]
        apron = apron_of(foot, blocked, cols, rows)
        # Tag footprint + apron with this building's sector/arena id. The
        # footprint stays a wall (collision=1); the apron is walkable, so
        # WorldMap.walk_path() can actually reach the address.
        for c, r in foot | apron:
            sector_maze[at(c, r)] = str(sid)
            arena_maze[at(c, r)] = str(sid)
        sector_blocks.append((sid, name))
        arena_blocks.append((sid, name, ARENA_NAME))
        if apron:
            c, r = min(apron)  # deterministic sample doorstep tile
            reachable[name] = [c, r]

    meta = {
        "world_name": WORLD_NAME,
        "maze_width": cols,
        "maze_height": rows,
        "sq_tile_size": TILE_PX,
        "special_constraint": "",
    }
    return {
        "meta": meta,
        "collision": collision,
        "sector_maze": sector_maze,
        "arena_maze": arena_maze,
        "object_maze": ["0"] * n,
        "spawn_maze": ["0"] * n,
        "sector_blocks": sector_blocks,
        "arena_blocks": arena_blocks,
        "reachable": reachable,
    }


def _write_flat(path: str, cells: list) -> None:
    """One long row of cells, ', '-separated — the upstream maze CSV layout."""
    with open(path, "w") as fh:
        fh.write(", ".join(cells))


def _write_rows(path: str, rows: list) -> None:
    with open(path, "w") as fh:
        for row in rows:
            fh.write(", ".join(str(c) for c in row) + "\n")


def write_matrix(out_dir: str, m: dict) -> None:
    matrix = os.path.join(out_dir, "matrix")
    maze = os.path.join(matrix, "maze")
    blocks = os.path.join(matrix, "special_blocks")
    os.makedirs(maze, exist_ok=True)
    os.makedirs(blocks, exist_ok=True)

    with open(os.path.join(matrix, "maze_meta_info.json"), "w") as fh:
        json.dump(m["meta"], fh, indent=1)

    _write_flat(os.path.join(maze, "collision_maze.csv"), m["collision"])
    _write_flat(os.path.join(maze, "sector_maze.csv"), m["sector_maze"])
    _write_flat(os.path.join(maze, "arena_maze.csv"), m["arena_maze"])
    _write_flat(os.path.join(maze, "game_object_maze.csv"), m["object_maze"])
    _write_flat(os.path.join(maze, "spawning_location_maze.csv"), m["spawn_maze"])

    _write_rows(os.path.join(blocks, "world_blocks.csv"), [[1, WORLD_NAME]])
    _write_rows(
        os.path.join(blocks, "sector_blocks.csv"),
        [[sid, WORLD_NAME, name] for sid, name in m["sector_blocks"]],
    )
    _write_rows(
        os.path.join(blocks, "arena_blocks.csv"),
        [[aid, WORLD_NAME, sec, arena] for aid, sec, arena in m["arena_blocks"]],
    )
    # OSM gives no interior objects or spawn points; write the files empty so
    # WorldMap (which opens all five block tables) finds them.
    open(os.path.join(blocks, "game_object_blocks.csv"), "w").close()
    open(os.path.join(blocks, "spawning_location_blocks.csv"), "w").close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--area", choices=list(AREAS), default="core")
    ap.add_argument("--refresh", action="store_true", help="re-download from Overpass")
    ap.add_argument(
        "--mpt",
        type=float,
        default=None,
        help="metres per tile (default: the area's own, else %d)" % METRES_PER_TILE,
    )
    ap.add_argument(
        "--rotate", default="auto", help="'auto' (axis-align), 'none', or degrees"
    )
    ap.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="asset dir to write matrix/ into (default: the_upenn override)",
    )
    args = ap.parse_args()

    area = AREAS[args.area]
    stem, bbox = area["stem"], area["bbox"]
    print(f"=== {args.area}: {area['desc']} -> Smallville matrix ===")

    osm = fetch_osm(bbox, os.path.join(OUT_DIR, f"{stem}_osm.json"), args.refresh)
    rotate_deg = resolve_rotation(args.rotate, osm, bbox)
    # Match the tilemap's resolution: explicit --mpt wins, else the area's own
    # (core pins 2 m/tile), else the module default — so the matrix lines up
    # tile-for-tile with the picture osm_to_tiled.py draws.
    mpt = args.mpt if args.mpt is not None else area.get("mpt", METRES_PER_TILE)
    proj = Projector(bbox, mpt, rotate_deg)
    # Crop the maze to the same block the tilemap is cropped to, so the agent grid
    # stays aligned tile-for-tile with the picture.
    if area.get("crop_to_streets"):
        crop_to_streets(proj, osm, area["crop_to_streets"])
    print(f"[grid]  {proj.cols} x {proj.rows} tiles, rotated {rotate_deg:+.2f}°")

    m = build_matrix(osm, proj)
    walls = m["collision"].count("1")
    print(
        f"[maze]  {walls} wall tiles, {len(m['sector_blocks'])} named buildings "
        f"(sectors), {len(m['reachable'])} with a reachable doorstep"
    )

    write_matrix(args.out, m)
    print(f"[emit]  {os.path.relpath(args.out)}/matrix/")

    # A dev reference (not read by the backend): building -> sample doorstep tile
    # + its address, to author world_data start_tiles / schedules against.
    ref = {
        name: {"address": f"{WORLD_NAME}:{name}:{ARENA_NAME}", "tile": xy}
        for name, xy in sorted(m["reachable"].items())
    }
    ref_path = os.path.join(OUT_DIR, f"{stem}_ville_addresses.json")
    with open(ref_path, "w") as fh:
        json.dump(ref, fh, indent=2)
    print(f"[emit]  {os.path.relpath(ref_path)} ({len(ref)} addressable buildings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
