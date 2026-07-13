"""Spatial bridge between our graph-based engine and a world's tile grid.

Our ``text_adventure_games`` engine is a graph of named ``Location``s; the
Generative Agents frontend, by contrast, animates sprites on a tile grid and
needs an ``(x, y)`` tile for every character every step. ``WorldMap`` loads a
world's maze data (the CSV matrix the frontend also renders -- the UPenn campus
is ``the_upenn``) and answers two questions the frame builder needs:

* **Where is an address?** ``tiles_for("the Ville:Hobbs Cafe:cafe")`` -> the set
  of tiles that belong to that world:sector:arena[:object] address.
* **How do I walk there?** ``walk_path(from_tile, address)`` -> the tile-by-tile
  path (via the vendored breadth-first :mod:`path_finder`) so the sprite walks
  around walls instead of straight through them.

The address scheme and the ``(x, y) = (col, row)`` convention mirror upstream
``maze.py`` exactly, so addresses resolve against the unmodified asset files.
"""

import csv
import json
import os

from . import path_finder


class WorldMap:
    """Loads a world's maze CSVs and resolves addresses to tiles + paths."""

    def __init__(self, world_dir: str):
        """``world_dir`` points at a world's asset root (e.g. ``.../the_upenn``),
        which contains the ``matrix/`` folder of maze + special-block CSVs."""
        matrix = os.path.join(world_dir, "matrix")
        meta = _load_json(os.path.join(matrix, "maze_meta_info.json"))
        self.width = int(meta["maze_width"])
        self.height = int(meta["maze_height"])
        self.tile_size = int(meta["sq_tile_size"])

        blocks = os.path.join(matrix, "special_blocks")
        world = _read_rows(os.path.join(blocks, "world_blocks.csv"))[0][-1]
        sector = _id_to_label(os.path.join(blocks, "sector_blocks.csv"))
        arena = _id_to_label(os.path.join(blocks, "arena_blocks.csv"))
        game_object = _id_to_label(os.path.join(blocks, "game_object_blocks.csv"))
        spawn = _id_to_label(os.path.join(blocks, "spawning_location_blocks.csv"))

        maze = os.path.join(matrix, "maze")
        collision = _read_flat(os.path.join(maze, "collision_maze.csv"))
        sector_m = _read_flat(os.path.join(maze, "sector_maze.csv"))
        arena_m = _read_flat(os.path.join(maze, "arena_maze.csv"))
        object_m = _read_flat(os.path.join(maze, "game_object_maze.csv"))
        spawn_m = _read_flat(os.path.join(maze, "spawning_location_maze.csv"))

        expected = self.width * self.height
        if len(collision) != expected:
            raise ValueError(
                f"collision_maze has {len(collision)} cells, expected {expected}"
            )

        # collision[y][x]: 1 = wall (any non-"0" tile id), 0 = walkable. Matches
        # maze.py's `!= "0"` rule, then normalized to ints so path_finder can use
        # collision_block_char=1 regardless of which id the export used for walls.
        self.collision: list[list[int]] = []
        # address_tiles[address] = {(x, y), ...}, built at world:sector,
        # world:sector:arena, world:sector:arena:object, and <spawn_loc> levels.
        self.address_tiles: dict[str, set[tuple[int, int]]] = {}

        for y in range(self.height):
            row = []
            for x in range(self.width):
                idx = y * self.width + x
                row.append(1 if collision[idx] != "0" else 0)

                s = sector.get(sector_m[idx])
                a = arena.get(arena_m[idx])
                g = game_object.get(object_m[idx])
                p = spawn.get(spawn_m[idx])
                addresses = []
                if s:
                    addresses.append(f"{world}:{s}")
                if s and a:
                    addresses.append(f"{world}:{s}:{a}")
                if s and a and g:
                    addresses.append(f"{world}:{s}:{a}:{g}")
                if p:
                    addresses.append(f"<spawn_loc>{p}")
                for address in addresses:
                    self.address_tiles.setdefault(address, set()).add((x, y))
            self.collision.append(row)

        # Precompute one axis-aligned bounding box per address -- (min_x, min_y,
        # max_x, max_y) -- so tile_gap() is O(1) per pair instead of comparing
        # every tile to every tile (issue #82). Computed once here; the tile sets
        # never change after load.
        self.address_bbox: dict[str, tuple[int, int, int, int]] = {}
        for address, tiles in self.address_tiles.items():
            xs = [x for x, _ in tiles]
            ys = [y for _, y in tiles]
            self.address_bbox[address] = (min(xs), min(ys), max(xs), max(ys))

        # Furniture-aware seat spots (#537): a walkable floor tile 4-adjacent
        # to furniture -- "stand AT the desk/table". The furniture tile itself
        # is NOT a spot: standing on a walk-on piece (a rug, cushion, sofa
        # seat) is meaningless as a destination and floods big pieces with
        # dots; a genuine sit-on-the-seat target waits for #446's sit verb,
        # which can use the named pieces in furniture_blocks. Grouped by arena
        # address, row-major. furniture_maze.csv is optional -- maps without it
        # (every non-Penn world) get {} and behave exactly as before.
        self.furniture_spots: dict[str, list[tuple[int, int]]] = {}
        furn_path = os.path.join(maze, "furniture_maze.csv")
        if os.path.exists(furn_path):
            furn = _read_flat(furn_path)
            if len(furn) != expected:
                raise ValueError(
                    f"furniture_maze has {len(furn)} cells, expected {expected}"
                )

            def _beside_furniture(x: int, y: int) -> bool:
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        if furn[ny * self.width + nx] != "0":
                            return True
                return False

            for y in range(self.height):
                for x in range(self.width):
                    idx = y * self.width + x
                    if (
                        collision[idx] != "0"
                        or furn[idx] != "0"
                        or not _beside_furniture(x, y)
                    ):
                        continue
                    s = sector.get(sector_m[idx])
                    a = arena.get(arena_m[idx])
                    if s and a:
                        self.furniture_spots.setdefault(f"{world}:{s}:{a}", []).append(
                            (x, y)
                        )

    def tiles_for(self, address: str) -> set[tuple[int, int]]:
        """Return the set of ``(x, y)`` tiles belonging to ``address``."""
        return self.address_tiles.get(address, set())

    def tile_gap(self, addr_a: str, addr_b: str) -> int:
        """Chebyshev gap, in tiles, between two addresses' footprints (issue #82).

        0 if they are the same address or their tiles touch/overlap; otherwise
        the number of tiles between them, counting diagonals as one step (so a
        ``vision_r`` of N covers an (2N+1)x(2N+1) square, matching upstream
        Generative Agents' tile vision). Returns a large sentinel when either address
        has no tiles (e.g. a home that's only ever a label), so it never reads as
        "nearby". Uses the precomputed bounding boxes, exact for the roughly
        rectangular arenas and slightly generous for irregular footprints."""
        if addr_a == addr_b:
            return 0
        a = self.address_bbox.get(addr_a)
        b = self.address_bbox.get(addr_b)
        if a is None or b is None:
            return self.width + self.height  # unknown footprint -> never nearby
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        dx = max(ax0 - bx1, bx0 - ax1, 0)
        dy = max(ay0 - by1, by0 - ay1, 0)
        return max(dx, dy)

    def is_blocked(self, tile: tuple[int, int]) -> bool:
        x, y = tile
        return self.collision[y][x] == 1

    def walk_path(
        self, from_tile: tuple[int, int], address: str
    ) -> list[tuple[int, int]]:
        """Tile-by-tile path from ``from_tile`` to the nearest walkable tile of
        ``address``, excluding the starting tile. Empty if the address is unknown
        or already reached."""
        targets = [t for t in self.tiles_for(address) if not self.is_blocked(t)]
        if not targets:
            return []
        target = path_finder.closest_coordinate(tuple(from_tile), targets)
        path = path_finder.path_finder(self.collision, tuple(from_tile), target, 1)
        return [tuple(t) for t in path[1:]]


# --------------------------------------------------------------------------
# CSV helpers (the upstream maze CSVs have spaces after commas and no trailing
# newline; strip every cell).
# --------------------------------------------------------------------------


def _load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _read_rows(path: str) -> list[list[str]]:
    with open(path, newline="") as f:
        return [[cell.strip() for cell in row] for row in csv.reader(f) if row]


def _read_flat(path: str) -> list[str]:
    """A maze layer CSV is one long row of width*height cells."""
    rows = _read_rows(path)
    return rows[0] if rows else []


def _id_to_label(path: str) -> dict[str, str]:
    """special_blocks row: ``id, world, [sector, [arena, ...]], label``.
    Map the tile id (first cell) to its label (last cell)."""
    return {row[0]: row[-1] for row in _read_rows(path)}
