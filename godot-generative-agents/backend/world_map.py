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
from collections import deque


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

        # Furniture-aware seat spots (#537): loaded from the committed
        # furniture_spots.csv (gen_furniture_matrix computes them tmj-aware --
        # walls excluded, same-arena furniture required, the furniture tile
        # itself omitted; the file the --debug-overlay draws, so overlay ==
        # sim by construction). Rows are `world, sector, arena, x, y, name`
        # (the optional 6th `name` field -- the furniture piece, #559 -- feeds
        # furniture_spot_type), grouped by address. Optional -- a world without
        # the file (every non-Penn map) gets {} and behaves exactly as before.
        self.furniture_spots: dict[str, list[tuple[int, int]]] = {}
        self.furniture_spot_type: dict[tuple[int, int], str] = {}
        # Lazy per-address BFS distance fields for walk_steps_from (#866);
        # None caches "address has no walkable tiles".
        self._distance_fields: dict[str, list[list[int]] | None] = {}
        spots_path = os.path.join(blocks, "furniture_spots.csv")
        if os.path.exists(spots_path):
            for row in open(spots_path).read().splitlines():
                if not row.strip():
                    continue
                fields = [c.strip() for c in row.split(",")]
                w, s, a, x, y = fields[:5]
                name = fields[5] if len(fields) > 5 else ""
                tile = (int(x), int(y))
                self.furniture_spots.setdefault(f"{w}:{s}:{a}", []).append(tile)
                if name:
                    self.furniture_spot_type[tile] = name

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
        return self._box_gap(
            self.address_bbox.get(addr_a), self.address_bbox.get(addr_b)
        )

    def _box_gap(self, a, b) -> int:
        """Chebyshev gap between two ``(x0, y0, x1, y1)`` boxes; the one formula.

        Returns a large sentinel when either box is ``None`` (no footprint), so
        an unmapped place never reads as nearby. Shared so #82's perception
        radius and #826's walk pricing cannot drift apart.
        """
        if a is None or b is None:
            return self.width + self.height  # unknown footprint -> never nearby
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        dx = max(ax0 - bx1, bx0 - ax1, 0)
        dy = max(ay0 - by1, by0 - ay1, 0)
        return max(dx, dy)

    def tile_gap_from(self, tile: tuple[int, int], address: str) -> int:
        """Chebyshev gap, in tiles, from one ``tile`` to ``address``'s footprint.

        :meth:`tile_gap`'s point-source sibling (issue #826): literally the same
        :meth:`_box_gap` with a degenerate 1x1 source box, so it reads the same
        precomputed ``address_bbox`` and stays O(1) per destination. 0 when the
        tile is inside the footprint; the same large sentinel as ``tile_gap``
        when the address has no tiles, so an unmapped place never reads as
        nearby.

        Anchored on a tile rather than an address because the caller
        (``cognition.walk_minutes_line``) prices a walk for an agent that may be
        standing on the campus hub, whose address is ``None`` -- and that is
        exactly a travel-decision point.
        """
        box = self.address_bbox.get(address)
        if box is None:
            return self.width + self.height  # unknown footprint -> never nearby
        x0, y0, x1, y1 = box
        x, y = tile
        return max(max(x0 - x, x - x1, 0), max(y0 - y, y - y1, 0))

    def is_blocked(self, tile: tuple[int, int]) -> bool:
        x, y = tile
        return self.collision[y][x] == 1

    def walk_steps_from(self, tile: tuple[int, int], address: str) -> int:
        """Actual walking distance, in tiles, from ``tile`` to ``address``.

        :meth:`tile_gap_from`'s accurate sibling (issue #866): a multi-source
        BFS field per destination address over the collision grid, so the
        number respects walls. 4-neighbor movement, matching
        :mod:`path_finder`, so the value equals the steps ``walk_path`` would
        actually take to the nearest walkable destination tile (the patched
        Penn ``walk_path`` then routes a few tiles further, to furniture or a
        rendezvous spot -- the prompt's "at least about" absorbs that).

        Falls back to the Chebyshev gap when the address has no walkable tiles
        (preserving the never-nearby sentinel) or the tile can't reach it.
        Fields are built lazily and cached per instance -- ~0.03 s each on the
        245x279 campus, and only addresses actually priced pay it.
        """
        if address not in self._distance_fields:
            self._distance_fields[address] = self._bfs_field(address)
        field = self._distance_fields[address]
        if field is not None:
            x, y = tile
            steps = field[y][x]
            if steps >= 0:
                return steps
        return self.tile_gap_from(tile, address)

    def _bfs_field(self, address: str):
        """Distance-in-steps grid to ``address``'s nearest walkable tile, or
        ``None`` when the address has no walkable tiles. ``-1`` = unreachable."""
        seeds = [t for t in self.tiles_for(address) if not self.is_blocked(t)]
        if not seeds:
            return None
        field = [[-1] * self.width for _ in range(self.height)]
        queue = deque()
        for x, y in seeds:
            field[y][x] = 0
            queue.append((x, y))
        while queue:
            x, y = queue.popleft()
            d = field[y][x] + 1
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (
                    0 <= nx < self.width
                    and 0 <= ny < self.height
                    and field[ny][nx] < 0
                    and self.collision[ny][nx] == 0
                ):
                    field[ny][nx] = d
                    queue.append((nx, ny))
        return field

    def walk_path(
        self, from_tile: tuple[int, int], address: str
    ) -> list[tuple[int, int]]:
        """Tile-by-tile path from ``from_tile`` to the nearest *reachable*
        walkable tile of ``address``, excluding the starting tile. Empty if the
        address is unknown, already reached, or unreachable.

        Descends the same multi-source BFS field :meth:`walk_steps_from`
        prices with, instead of BFS-ing to the Euclidean-closest tile: on the
        real campus an address's closest tile can sit in a walled-off pocket
        (Van Pelt's Study Booths, #904), where the old routing returned an
        empty path and the agent "arrived" without ever moving.
        """
        if address not in self._distance_fields:
            self._distance_fields[address] = self._bfs_field(address)
        field = self._distance_fields[address]
        if field is None:
            return []
        x, y = from_tile
        d = field[y][x]
        if d <= 0:
            return []  # already on a destination tile (0) or unreachable (-1)
        path = []
        while d > 0:
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (
                    0 <= nx < self.width
                    and 0 <= ny < self.height
                    and field[ny][nx] == d - 1
                ):
                    x, y, d = nx, ny, d - 1
                    path.append((x, y))
                    break
            else:  # pragma: no cover - a BFS field always steps down somewhere
                return []
        return path


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
