"""Build a small synthetic ``the_ville`` maze for the offline tests.

The real Smallville map ships as ~38MB of upstream assets that live in the
git-ignored ``frontend/`` (populated by ``./setup.sh``). So the spatial/export
tests can't depend on it: on a fresh checkout there's nothing to read. This
module writes a hand-built maze with the *same on-disk layout* that
:class:`gen_agents.world_map.WorldMap` reads, so the tests exercise the real
address-resolution, path-finding, and export code with no external clone::

    <root>/the_ville/matrix/
        maze_meta_info.json
        special_blocks/{world,sector,arena,game_object,spawning_location}_blocks.csv
        maze/{collision,sector,arena,game_object,spawning_location}_maze.csv

The grid is 140x100 -- the real map's dimensions -- so every persona's real
``start_tile`` (up to ``(126, 74)``) lands in bounds. It is almost entirely
walkable; we carve out only:

  * one arena per day-destination the cast walks to (cafe, library, park, store,
    supply store, pub), each a small open rectangle the pathfinder can reach;
  * a short wall between Isabella's spawn ``(72, 14)`` and Hobbs Cafe, so the
    collision-free pathing test has a real obstacle to route around.

Homes are intentionally omitted: a persona's home address is only rendered into
a "waking up @ ..." label (a string), never resolved to tiles, so the synthetic
maze doesn't need them.
"""

import csv
import json
import os

WIDTH = 140
HEIGHT = 100
TILE_SIZE = 32
WORLD = "the Ville"

_OPEN = "0"  # "0" means empty/walkable in every maze layer
_WALL = "9999"  # any non-"0" id reads as a wall to WorldMap

# The day-destinations the 25 personas travel to. Each is one engine location
# (see gen_agents.build_world) -> (sector, arena, sector_id, arena_id, rectangle).
# The rectangle is an inclusive (x0, y0, x1, y1) tile box of open arena tiles.
_ARENAS = [
    ("Hobbs Cafe", "cafe", "1001", "2001", (70, 26, 74, 29)),
    ("Oak Hill College", "library", "1002", "2002", (118, 40, 124, 46)),
    ("Johnson Park", "park", "1003", "2003", (28, 40, 40, 46)),
    ("The Willows Market and Pharmacy", "store", "1004", "2004", (70, 78, 80, 84)),
    ("Harvey Oak Supply Store", "supply store", "1005", "2005", (50, 50, 56, 56)),
    ("The Rose and Crown Pub", "pub", "1006", "2006", (48, 10, 56, 16)),
]

# A short horizontal wall just south of Isabella's spawn (72, 14). The gap sits
# off to the right, so the only route to the cafe (70..74, 26..29) detours around
# it -- which is what gives the collision-free pathing test something to prove.
_WALL_TILES = {(x, 20) for x in range(68, 76)}  # x in [68, 75]; (76, 20) stays open


def build_synthetic_ville(root: str) -> str:
    """Write the synthetic maze under ``root`` and return its ``the_ville`` dir."""
    ville = os.path.join(root, "the_ville")
    matrix = os.path.join(ville, "matrix")
    blocks = os.path.join(matrix, "special_blocks")
    maze = os.path.join(matrix, "maze")
    os.makedirs(blocks, exist_ok=True)
    os.makedirs(maze, exist_ok=True)

    with open(os.path.join(matrix, "maze_meta_info.json"), "w") as f:
        json.dump(
            {"maze_width": WIDTH, "maze_height": HEIGHT, "sq_tile_size": TILE_SIZE}, f
        )

    # special_blocks map a tile id to its label. Format mirrors upstream:
    # world is "id, world"; sector "id, world, sector"; arena adds the arena.
    _write_rows(os.path.join(blocks, "world_blocks.csv"), [["32134", WORLD]])
    _write_rows(
        os.path.join(blocks, "sector_blocks.csv"),
        [[sid, WORLD, sector] for sector, _ar, sid, _aid, _rect in _ARENAS],
    )
    _write_rows(
        os.path.join(blocks, "arena_blocks.csv"),
        [[aid, WORLD, sector, arena] for sector, arena, _sid, aid, _rect in _ARENAS],
    )
    # No object/spawn semantics needed: empty tables resolve every cell to None.
    _write_rows(os.path.join(blocks, "game_object_blocks.csv"), [])
    _write_rows(os.path.join(blocks, "spawning_location_blocks.csv"), [])

    # maze layers are one long row of WIDTH*HEIGHT cells, read in row-major order.
    collision = [_OPEN] * (WIDTH * HEIGHT)
    sector = [_OPEN] * (WIDTH * HEIGHT)
    arena = [_OPEN] * (WIDTH * HEIGHT)
    blank = [_OPEN] * (WIDTH * HEIGHT)
    for x, y in _WALL_TILES:
        collision[y * WIDTH + x] = _WALL
    for _sector, _arena, sid, aid, (x0, y0, x1, y1) in _ARENAS:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                sector[y * WIDTH + x] = sid
                arena[y * WIDTH + x] = aid
    _write_flat(os.path.join(maze, "collision_maze.csv"), collision)
    _write_flat(os.path.join(maze, "sector_maze.csv"), sector)
    _write_flat(os.path.join(maze, "arena_maze.csv"), arena)
    _write_flat(os.path.join(maze, "game_object_maze.csv"), blank)
    _write_flat(os.path.join(maze, "spawning_location_maze.csv"), blank)
    return ville


def _write_rows(path: str, rows: list[list[str]]) -> None:
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)


def _write_flat(path: str, cells: list[str]) -> None:
    with open(path, "w", newline="") as f:
        csv.writer(f).writerow(cells)
