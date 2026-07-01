#!/usr/bin/env python3
"""Give campus buildings a door and a walkable interior, so agents can go inside.

Out of the box the campus is solid: ``osm_to_ville.py`` makes every building
footprint a wall (``collision=1``) and only tags the 1-tile walkable *apron* around
it, so "go to College Hall" means "walk to its edge" -- agents never go in. This
post-process opens each target building up:

  * **Matrix** (``the_upenn/matrix``): hollow the footprint -- the inside becomes
    walkable floor, the 1-tile perimeter stays a wall, and exactly ONE perimeter
    cell is opened as a *door*. Because the backend pathfinder
    (``gen_agents/path_finder.py``) is a breadth-first search over this collision
    grid, a wall ring with a single gap means an agent can ONLY get in or out
    through that gap -- "enter/exit through the door" is enforced by the map
    itself, with no movement-code changes. The interior is tagged as a new arena
    so its address ``UPenn:<building>:lobby`` resolves and agents can be sent
    inside (``UPenn:<building>:grounds`` still means the outside edge).

  * **Picture** (``upenn_core_urban.tmj``): "open the roof" of each building (zero
    the ``buildings``/``trees`` layers over its footprint) and paint a plain
    cutaway -- floor inside, wall around, a door tile at the gap -- exactly like
    ``furnish_building.py`` does for Williams Hall, whose low-level tile/`.tmj`
    helpers we reuse. (Williams already has a *furnished* cutaway, so we leave its
    picture alone and only carve its collision, lining the door up with its art.)

**Doors** go where a natural OSM footway leads up to the building. A wall cell is
opened when a path tile (the ``paths`` layer) sits *directly against* it; the run of
such cells along one wall becomes one door, as wide as its walk (capped). A building
reached by several walks gets several doors. If no path touches the wall at all we
fall back to a single door at the nearest approach (a flood-fill of walking distance
from the paths picks the closest wall). A door is just an open gap in the wall ring
-- a passage framed by the surrounding wall, with no door leaf -- so it reads the
same whichever way the wall faces.

We also tidy the building tables: name the few footprints OSM left unnamed (by
their street address) so they become enterable too, and drop the stale "phantom"
sector entries whose footprints were cropped out of the frame.

The script is **idempotent**: it strips the ``entrance_*`` layers it adds before
re-applying, and recomputes the interior from the *original* footprint each run, so
it is safe to re-run and safe to run after a fresh ``osm_to_tiled.py`` bake +
``furnish_building.py``.

Run order::

    uv run python tools/geo/osm_to_tiled.py --area core --theme urban   # bake map
    uv run python tools/geo/furnish_building.py                          # Williams
    uv run python tools/geo/add_entrances.py                             # doors!
    uv run python godot-generative-agents/sim/generate_building_labels.py
    uv run python godot-generative-agents/sim/generate_penn_replay.py
    # then commit the updated .tmj + matrix CSVs
"""

from __future__ import annotations

import argparse
import collections
import json
import os

# Reuse furnish_building's tile palette + .tmj helpers so our plain cutaway uses
# the exact same interior tiles (and tilesets) as the Williams Hall one.
import furnish_building as fb

WORLD = "UPenn"
GROUNDS = "grounds"  # the outside-edge arena every building already has
LOBBY = "lobby"  # the new interior arena this tool adds
INTERIOR_ARENA_BASE = 1000  # interior arena id = base + sector id (no id clashes)
ROOM_ARENA_BASE = (
    10000  # room arena id = base + sector*100 + index (clears lobby range)
)
VAN_PELT = "Van Pelt Library"
FISHER = "Fisher Fine Arts Library"  # the Furness building at 220 South 34th Street
MEYERSON = "Meyerson Hall"
HOUSTON = "Houston Hall"
IRVINE = "Irvine Auditorium"
COLLEGE = "College Hall"
ROOM_SUBDIVIDE = {
    VAN_PELT,
    FISHER,
    MEYERSON,
    HOUSTON,
    IRVINE,
    COLLEGE,
}  # buildings split into rooms
MIN_INTERIOR = 4  # footprints with fewer inside tiles stay solid (too small)
MAX_DOOR_WIDTH = 6  # per-door cap; also stops a wall fronting a wide plaza from
#                     opening end to end (a building may still have several doors)
PATH_REACH = 1  # a door only forms where a footway tile sits DIRECTLY against the
#                 wall (1 tile out). A path 2+ tiles away is a walk passing by, not
#                 an approach -- looking further once let College Hall's door drift
#                 off its entrance spur onto the blank stone beside a passing walk.
FALLBACK_DOOR_WIDTH = 3  # buildings with no path touching the wall get one door at
#                          the nearest approach, this wide (a normal entrance).

# Shell tiles (same as Williams' cutaway). A door is just an open gap in the wall
# ring -- floor with no leaf sprite -- so it reads the same whichever way the wall
# faces; no door tile is needed.
FLOOR = fb.FLOOR
WALL = fb.WALL

NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))

# Footprints OSM never named (no `name` tag), keyed by a cell we know is inside
# them, with the street-address name to give each. See the plan / README.
UNNAMED = [
    # OSM left the Furness building untagged; we give it its real name (it's a
    # known landmark, not just an address) rather than the street-address fallback.
    {"name": "Fisher Fine Arts Library", "seed": (208, 150)},
    {"name": "Locust Walk Annex", "seed": (29, 76)},
]

# Williams Hall is already a furnished cutaway (furnish_building.py) with its door
# in the south wall at these columns. We carve its collision to match, and skip its
# picture so we don't paint over the furniture.
WILLIAMS = "Williams Hall"
WILLIAMS_DOOR_X = (40, 41)


# --------------------------------------------------------------------------- #
# Flat CSV maze layers: one ", "-joined row of width*height cell ids (the format
# osm_to_ville.py writes and world_map.py reads).
# --------------------------------------------------------------------------- #
def read_flat(path: str) -> list[str]:
    return open(path).read().strip().split(", ")


def write_flat(path: str, cells: list[str]) -> None:
    with open(path, "w") as fh:
        fh.write(", ".join(cells))


def read_blocks(path: str) -> list[list[str]]:
    rows = []
    with open(path) as fh:
        for line in fh:
            if line.strip():
                rows.append([p.strip() for p in line.split(",")])
    return rows


def write_blocks(path: str, rows: list[list[str]]) -> None:
    with open(path, "w") as fh:
        for row in rows:
            fh.write(", ".join(str(c) for c in row) + "\n")


# --------------------------------------------------------------------------- #
# Footprint geometry
# --------------------------------------------------------------------------- #
def component_in(mask: set, seed: tuple[int, int]) -> set:
    """The 4-connected blob of footprint cells in `mask` containing `seed`.

    Used to recover an unnamed building's footprint from the footprint mask."""
    if seed not in mask:
        return set()
    seen = {seed}
    stack = [seed]
    while stack:
        x, y = stack.pop()
        for dx, dy in NEIGHBOURS:
            nb = (x + dx, y + dy)
            if nb in mask and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen


def split_footprint(foot: set, W: int, H: int):
    """(perimeter, interior): the 1-tile wall ring vs the inside of a footprint.

    A perimeter cell is a footprint cell with a 4-neighbour outside the footprint
    (or off the map); everything else is interior."""
    perimeter, interior = set(), set()
    for x, y in foot:
        edge = False
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < W and 0 <= ny < H) or (nx, ny) not in foot:
                edge = True
                break
        (perimeter if edge else interior).add((x, y))
    return perimeter, interior


def path_distance_field(collision: list[str], paths: list[int], W: int, H: int):
    """Walking distance (in tiles, over walkable cells) from the nearest path tile.

    Multi-source BFS seeded at every `paths`-layer tile, expanding through walkable
    (collision==0) cells. Lets us put each door where a footway actually leads."""
    INF = W * H + 1
    dist = [INF] * (W * H)
    q = collections.deque()
    for i, v in enumerate(paths):
        if v != 0 and collision[i] == "0":
            dist[i] = 0
            q.append((i % W, i // W))
    while q:
        x, y = q.popleft()
        d = dist[y * W + x] + 1
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H:
                j = ny * W + nx
                if collision[j] == "0" and d < dist[j]:
                    dist[j] = d
                    q.append((nx, ny))
    return dist


def choose_door(foot, perimeter, interior, collision, dist, W, H):
    """Pick the single perimeter cell to open as the door.

    A candidate must connect inside to outside: it needs an interior neighbour AND
    a walkable neighbour outside the footprint. We score each candidate by how
    close its outside neighbour is to a footway (the path-distance field) so the
    door lands at the natural approach; ties and path-less buildings fall back to
    the most open outside neighbour, then to a deterministic cell."""
    best = None
    for x, y in perimeter:
        inside = outside = None
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < W and 0 <= ny < H):
                continue
            if (nx, ny) in interior:
                inside = (nx, ny)
            elif (nx, ny) not in foot and collision[ny * W + nx] == "0":
                outside = (nx, ny)
        if inside is None or outside is None:
            continue
        ox, oy = outside
        # openness = walkable cells in a 5x5 window around the outside neighbour
        # (the fallback when no footway is near).
        openness = sum(
            1
            for ddx in range(-2, 3)
            for ddy in range(-2, 3)
            if 0 <= ox + ddx < W
            and 0 <= oy + ddy < H
            and collision[(oy + ddy) * W + (ox + ddx)] == "0"
        )
        # Sort key: nearest-to-path first, then most-open, then a stable tiebreak.
        key = (dist[oy * W + ox], -openness, y, x)
        if best is None or key < best[0]:
            best = (key, (x, y))
    return best[1] if best else None


def links_in_out(c, foot, interior, W, H):
    """True if perimeter cell `c` could be a door: it touches the interior on one
    side and a cell outside the footprint on another (so opening it joins in+out)."""
    x, y = c
    has_in = any((x + a, y + b) in interior for a, b in NEIGHBOURS)
    has_out = any(
        (x + a, y + b) not in foot and 0 <= x + a < W and 0 <= y + b < H
        for a, b in NEIGHBOURS
    )
    return has_in and has_out


def widen_fallback(seed, perimeter, interior, foot, W, H, width=FALLBACK_DOOR_WIDTH):
    """Grow a single fallback door cell along its wall to a natural entrance width.

    Extends from `seed` in both directions parallel to the wall (perpendicular to the
    cell's outward normal), keeping cells that are themselves valid door cells, up to
    `width` total. Used only when no footway touches the building."""
    out = next(
        ((a, b) for a, b in NEIGHBOURS if (seed[0] + a, seed[1] + b) not in foot), None
    )
    if out is None:
        return {seed}
    # Wall runs perpendicular to the outward normal.
    alongs = [(0, 1), (0, -1)] if out[0] != 0 else [(1, 0), (-1, 0)]
    cells = {seed}
    for ax, ay in alongs:
        c = seed
        while len(cells) < width:
            c = (c[0] + ax, c[1] + ay)
            if c in perimeter and links_in_out(c, foot, interior, W, H):
                cells.add(c)
            else:
                break
    return cells


def find_doors(foot, perimeter, interior, paths, W, H):
    """All doors for a building -- one per footway that leads up to it.

    Many buildings are reached by more than one walk (College Hall has paths on
    several sides), so rather than a single door we open *every* place a path
    arrives. A perimeter cell belongs to a door when it both links inside to
    outside and *faces a path* -- one of its outward rays hits a `paths` tile
    within `PATH_REACH` cells (1: the path must sit directly against the wall, so a
    walk merely passing a couple of tiles away does not punch a door). Those cells
    are grouped into contiguous runs along the wall -- each run is one door, as wide
    as and aligned with its walk, capped at `MAX_DOOR_WIDTH` so a wall fronting a
    wide plaza can't open end to end.

    Returns a list of door cell-sets, or ``None`` if no path reaches the building
    (the caller then falls back to a single nearest-path door)."""

    def faces_path(c):
        # Look outward in every direction that leaves the footprint.
        for dx, dy in NEIGHBOURS:
            if (c[0] + dx, c[1] + dy) in foot:
                continue
            for k in range(1, PATH_REACH + 1):
                p = (c[0] + dx * k, c[1] + dy * k)
                if not (0 <= p[0] < W and 0 <= p[1] < H) or p in foot:
                    break
                if paths[p[1] * W + p[0]]:
                    return True
        return False

    facing = {
        c for c in perimeter if links_in_out(c, foot, interior, W, H) and faces_path(c)
    }
    if not facing:
        return None

    # Group facing cells into contiguous runs along the wall (4-connected).
    doors, seen = [], set()
    for cell in facing:
        if cell in seen:
            continue
        run, stack = [], [cell]
        seen.add(cell)
        while stack:
            x, y = stack.pop()
            run.append((x, y))
            for dx, dy in NEIGHBOURS:
                nb = (x + dx, y + dy)
                if nb in facing and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        if len(run) > MAX_DOOR_WIDTH:  # keep the cells nearest the run's middle
            cx = sum(x for x, _ in run) / len(run)
            cy = sum(y for _, y in run) / len(run)
            run = sorted(run, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
            run = run[:MAX_DOOR_WIDTH]
        doors.append(set(run))
    return doors


# --------------------------------------------------------------------------- #
# .tmj surgery (entrance_* layers; leaves williams_* and plants untouched)
# --------------------------------------------------------------------------- #
def ensure_interior_tilesets(tmj):
    """Append furnish_building's interior tilesets only if they're missing, so our
    floor/wall/door gids resolve even on a freshly-baked map."""
    have = {t.get("name") for t in tmj["tilesets"]}
    for name, img, cols, rows in fb._ALL_SHEETS:
        if name in have:
            continue
        tmj["tilesets"].append(
            {
                "firstgid": fb._FIRST[name],
                "name": name,
                "image": img,
                "imagewidth": cols * 16,
                "imageheight": rows * 16,
                "tilewidth": 16,
                "tileheight": 16,
                "columns": cols,
                "tilecount": cols * rows,
                "margin": 0,
                "spacing": 0,
            }
        )
    tmj["tilesets"].sort(key=lambda t: t["firstgid"])


def strip_entrance_layers(tmj):
    tmj["layers"] = [
        L for L in tmj["layers"] if not str(L.get("name", "")).startswith("entrance_")
    ]


def insert_entrance_layers(tmj, W, H, floor):
    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    floor_layer = {
        "type": "tilelayer",
        "name": "entrance_floor",
        "id": next_id,
        "x": 0,
        "y": 0,
        "width": W,
        "height": H,
        "opacity": 1,
        "visible": True,
        "data": floor,
    }
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + 1)
    # Sit it just above buildings (with williams_*), below trees.
    names = [L.get("name") for L in tmj["layers"]]
    at = names.index("buildings") + 1 if "buildings" in names else len(tmj["layers"])
    tmj["layers"][at:at] = [floor_layer]


def paint_interior(floor, perimeter, foot, door, W):
    """Paint one building's plain cutaway onto the floor layer.

    Floor over the whole footprint, wall around the perimeter, and each door cell
    re-opened to floor. A door is just that open gap in the wall ring -- a passage
    you walk through, framed by the surrounding wall -- with no door leaf, which
    reads the same whichever way the wall faces."""
    for x, y in foot:
        floor[y * W + x] = FLOOR
    for x, y in perimeter:
        floor[y * W + x] = WALL
    for x, y in door:
        floor[y * W + x] = FLOOR


# --------------------------------------------------------------------------- #
# Room-subdivision helpers
# --------------------------------------------------------------------------- #
def load_room_plan():
    """(rooms, wall_cells) from van_pelt_interior.json: the 25 room rects and the
    partition-wall cell set. Returns ([], set()) if the asset is missing."""
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "van_pelt_interior.json"
    )
    if not os.path.exists(path):
        return [], set()
    with open(path) as fh:
        a = json.load(fh)
    json_w = a["width"]
    rooms = a["rooms"]
    wall_cells = {(i % json_w, i // json_w) for i in a["wall_cells"]}
    return rooms, wall_cells


def load_fisher_plan(tmj, W, interior):
    """(rooms, wall_cells) for Fisher: room rects from the hand-drawn
    `fisher_arenas` object layer, and partition-wall cells derived from the same
    WALLS spec the picture uses (furnish_fisher.iter_wall_cells). Deriving the
    walls from fisher_arenas -- not the fisher_walls picture layer -- keeps the
    matrix and picture in lock-step no matter which tool runs first. Returns
    ([], set()) if fisher_arenas is absent (Fisher not authored yet)."""
    import furnish_fisher as ff

    sections = ff.read_sections(tmj)
    if not sections:
        return [], set()
    interior_idx = {y * W + x for (x, y) in interior}
    rooms = [{"name": nm, "rect": list(rect)} for nm, rect in sections.items()]
    wall_cells = {cell for _side, cell in ff.iter_wall_cells(sections, interior_idx, W)}
    return rooms, wall_cells


def load_meyerson_plan(tmj, W, interior):
    """(rooms, wall_cells) for Meyerson from meyerson_arenas + the shared WALLS
    spec (furnish_meyerson.iter_wall_cells)."""
    import furnish_meyerson as fm

    sections = fm.read_sections(tmj)
    if not sections:
        return [], set()
    interior_idx = {y * W + x for (x, y) in interior}
    rooms = [{"name": nm, "rect": list(rect)} for nm, rect in sections.items()]
    wall_cells = {cell for _side, cell in fm.iter_wall_cells(sections, interior_idx, W)}
    return rooms, wall_cells


def load_houston_plan(tmj, W, H, interior):
    """(rooms, wall_cells) for Houston from houston_arenas. Houston's partitions
    are auto-enclosed (not a fixed WALLS spec), so the wall cells come from
    furnish_houston.houston_wall_cells -- the same computation the picture uses,
    so matrix and picture stay in lock-step."""
    import furnish_houston as fh

    sections = fh.read_sections(tmj)
    if not sections:
        return [], set()
    interior_idx = {y * W + x for (x, y) in interior}
    rooms = [{"name": nm, "rect": list(rect)} for nm, rect in sections.items()]
    wall_cells = fh.houston_wall_cells(tmj, interior_idx, W, H)
    return rooms, wall_cells


def load_irvine_plan(tmj, W, H, interior):
    """(rooms, wall_cells) for Irvine from irvine_arenas. Uses the *grouped*
    sections so numbered sub-boxes (Stage 1/2/3, the foyers) become single
    arenas, matching the picture (no wall between sub-boxes). Wall cells come
    from furnish_irvine.irvine_wall_cells, the same computation the picture uses."""
    import furnish_irvine as fi

    grouped = fi._grouped_sections(tmj)
    if not grouped:
        return [], set()
    interior_idx = {y * W + x for (x, y) in interior}
    rooms = [{"name": nm, "rect": list(rect)} for nm, rect in grouped.items()]
    wall_cells = fi.irvine_wall_cells(tmj, interior_idx, W, H)
    return rooms, wall_cells


def load_college_hall_plan(tmj, W, H, interior):
    """(rooms, wall_cells) for College Hall from college_hall_arenas. Partitions
    are auto-enclosed (including the open Central/Great/Kitchen seams that are
    deliberately left wall-free), so the wall cells come from
    furnish_college_hall.college_wall_cells -- the same computation the picture
    uses, so matrix and picture stay in lock-step."""
    import furnish_college_hall as fc

    sections = fc.read_sections(tmj)
    if not sections:
        return [], set()
    interior_idx = {y * W + x for (x, y) in interior}
    rooms = [{"name": nm, "rect": list(rect)} for nm, rect in sections.items()]
    wall_cells = fc.college_wall_cells(tmj, interior_idx, W, H)
    return rooms, wall_cells


def _punch_doorway(room_cells, walk, collision, W, H):
    """Carve one cell gap between sealed room_cells and the adjacent walk.

    Called when a room's walkable cells are not connected to the rest of the
    building interior. Finds the partition-wall cell (currently collision=1)
    adjacent to room_cells that also neighbours a walk cell and opens it."""
    for x, y in sorted(room_cells):
        for dx, dy in NEIGHBOURS:
            wall = (x + dx, y + dy)
            wx, wy = wall
            if not (0 <= wx < W and 0 <= wy < H):
                continue
            if collision[wy * W + wx] != "1":
                continue
            # Is there a walk cell on the other side of this wall?
            for dx2, dy2 in NEIGHBOURS:
                nb = (wx + dx2, wy + dy2)
                if nb in walk:
                    collision[wy * W + wx] = "0"
                    walk.add(wall)
                    return


def subdivide_rooms(
    sid, name, interior, door_cells, collision, arena_m, room_rows, W, H, room_plan
):
    """Turn one building's lobby interior into per-room arenas + partition walls.
    Stamps over the already-written lobby base, so cells in no room stay lobby."""
    rooms, wall_cells = room_plan
    # partition walls become collision (but never seal the building door)
    for x, y in (wall_cells & interior) - door_cells:
        collision[y * W + x] = "1"
    walk = {(x, y) for (x, y) in interior if collision[y * W + x] == "0"}
    for idx, room in enumerate(rooms):
        rid = str(ROOM_ARENA_BASE + int(sid) * 100 + idx)
        c0, r0, c1, r1 = room["rect"]
        room_walk = {
            (x, y)
            for y in range(r0, r1 + 1)
            for x in range(c0, c1 + 1)
            if (x, y) in walk
        }
        if room_walk:
            # Check if room_walk is reachable from walk \ room_walk via BFS.
            other_walk = walk - room_walk
            reachable = False
            for cell in room_walk:
                for dx, dy in NEIGHBOURS:
                    if (cell[0] + dx, cell[1] + dy) in other_walk:
                        reachable = True
                        break
                if reachable:
                    break
            if not reachable and other_walk:
                _punch_doorway(room_walk, walk, collision, W, H)
        for y in range(r0, r1 + 1):
            for x in range(c0, c1 + 1):
                if (x, y) in walk:
                    arena_m[y * W + x] = rid
        room_rows.append([rid, WORLD, name, room["name"]])


# --------------------------------------------------------------------------- #
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--tmj",
        default=os.path.join(
            repo, "godot-generative-agents", "maps", "upenn_core_urban.tmj"
        ),
    )
    ap.add_argument(
        "--matrix",
        default=os.path.join(
            repo, "godot-generative-agents", "sim", "the_upenn", "matrix"
        ),
    )
    ap.add_argument("--dry-run", action="store_true", help="report, do not write")
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    W, H = tmj["width"], tmj["height"]
    layers = {L["name"]: L for L in tmj["layers"] if L.get("type") == "tilelayer"}
    paths_layer = layers["paths"]["data"]

    maze = os.path.join(args.matrix, "maze")
    blocks = os.path.join(args.matrix, "special_blocks")
    collision = read_flat(os.path.join(maze, "collision_maze.csv"))
    sector_m = read_flat(os.path.join(maze, "sector_maze.csv"))
    arena_m = read_flat(os.path.join(maze, "arena_maze.csv"))
    sector_rows = read_blocks(os.path.join(blocks, "sector_blocks.csv"))
    assert len(collision) == W * H, (len(collision), W * H)

    # ----- the footprint mask: the invariant source of every building's shape ---
    # The `buildings` layer holds the un-opened roofs; the floor layers we (and
    # furnish_building) paint cover an *opened* building's whole footprint. Their
    # union is the original footprint set regardless of how many times we've run,
    # so re-runs recompute identical geometry even though we hollow `collision`.
    def layer_cells(name):
        L = layers.get(name)
        return (
            set() if not L else {(i % W, i // W) for i, v in enumerate(L["data"]) if v}
        )

    foot_mask = (
        layer_cells("buildings")
        | layer_cells("williams_floor")
        | layer_cells("entrance_floor")
    )

    # ----- which sectors actually have tiles (the buildings in frame) ----------
    name_by_id = {r[0]: r[-1] for r in sector_rows if len(r) >= 3}
    sid_by_name = {name: sid for sid, name in name_by_id.items()}
    cells_by_id: dict[str, set] = collections.defaultdict(set)
    for i, sid in enumerate(sector_m):
        if sid != "0":
            cells_by_id[sid].add((i % W, i // W))
    # name -> footprint (sector tiles trimmed to the footprint mask, dropping apron).
    named_targets = {
        name_by_id[sid]: cells & foot_mask
        for sid, cells in cells_by_id.items()
        if sid in name_by_id
    }

    # ----- name the unnamed footprints (reuse the sector id on re-runs) ----------
    next_sid = max((int(s) for s in name_by_id if s.isdigit()), default=0)
    for u in UNNAMED:
        foot = component_in(foot_mask, tuple(u["seed"]))
        if not foot:
            print(f"  !! {u['name']}: no building footprint at {u['seed']}, skipping")
            continue
        if u["name"] in sid_by_name:
            sid = sid_by_name[u["name"]]  # already named on a previous run
        else:
            next_sid += 1
            sid = str(next_sid)
            name_by_id[sid] = u["name"]
            sid_by_name[u["name"]] = sid
        named_targets[u["name"]] = foot
        # Paint the sector's footprint + apron into the maze (grounds arena). The
        # apron is the walkable ring just outside the footprint.
        apron = set()
        for x, y in foot:
            for dx, dy in NEIGHBOURS:
                nb = (x + dx, y + dy)
                if 0 <= nb[0] < W and 0 <= nb[1] < H and nb not in foot:
                    if collision[nb[1] * W + nb[0]] == "0":
                        apron.add(nb)
        for x, y in foot | apron:
            sector_m[y * W + x] = sid
            arena_m[y * W + x] = sid

    # ----- door placement field -------------------------------------------------
    # Flood path-distance with every footprint treated as solid, so the field (and
    # thus the chosen door) is identical whether or not interiors are already
    # hollowed -- a re-run picks the same doors.
    solid = list(collision)
    for x, y in foot_mask:
        solid[y * W + x] = "1"
    dist = path_distance_field(solid, paths_layer, W, H)

    # ----- carve every target ---------------------------------------------------
    arena_lobby_rows = []  # (lobby_id, world, sector, "lobby")
    arena_room_rows = []  # (room_id, world, sector, room_name) for subdivided buildings
    room_plan = load_room_plan()
    picture_jobs = []  # (name, foot, perimeter, door) for the .tmj cutaway
    summary = []
    for name in sorted(named_targets):
        # Footprint from the invariant mask (not the live collision, which we hollow).
        foot = named_targets[name] & foot_mask
        perimeter, interior = split_footprint(foot, W, H)
        if len(interior) < MIN_INTERIOR:
            summary.append((name, len(foot), 0, "too small -> left solid"))
            continue

        if name == WILLIAMS:
            # Match the furnished art's single south door (those columns' bottom).
            wd = set()
            for dx in WILLIAMS_DOOR_X:
                col = [y for (x, y) in foot if x == dx]
                if col:
                    wd.add((dx, max(col)))
            doors = [{d for d in wd if d in perimeter} or {min(perimeter)}]
        else:
            # One door per footway leading in; fall back to a single nearest-path
            # door if no path actually reaches this building.
            doors = find_doors(foot, perimeter, interior, paths_layer, W, H)
            if doors is None:
                d = choose_door(foot, perimeter, interior, solid, dist, W, H)
                doors = [
                    (
                        widen_fallback(d, perimeter, interior, foot, W, H)
                        if d
                        else {min(perimeter)}
                    )
                ]
        door_cells = set().union(*doors)

        # Collision: hollow the inside, keep the ring a wall, open every door.
        for x, y in interior:
            collision[y * W + x] = "0"
        for x, y in perimeter:
            collision[y * W + x] = "1"
        for x, y in door_cells:
            collision[y * W + x] = "0"

        # Interior arena -> address UPenn:<name>:lobby
        sid = sid_by_name[name]
        lobby_id = str(INTERIOR_ARENA_BASE + int(sid))
        for x, y in interior:
            arena_m[y * W + x] = lobby_id
        arena_lobby_rows.append([lobby_id, WORLD, name, LOBBY])

        if name in ROOM_SUBDIVIDE:
            if name == VAN_PELT:
                plan = room_plan
            elif name == FISHER:
                plan = load_fisher_plan(tmj, W, interior)
            elif name == HOUSTON:
                plan = load_houston_plan(tmj, W, H, interior)
            elif name == IRVINE:
                plan = load_irvine_plan(tmj, W, H, interior)
            elif name == COLLEGE:
                plan = load_college_hall_plan(tmj, W, H, interior)
            else:
                plan = load_meyerson_plan(tmj, W, interior)
            subdivide_rooms(
                sid,
                name,
                interior,
                door_cells,
                collision,
                arena_m,
                arena_room_rows,
                W,
                H,
                plan,
            )

        if name != WILLIAMS:  # Williams' picture is already its furnished cutaway
            picture_jobs.append((name, foot, perimeter, door_cells))
        widths = ", ".join(str(len(d)) for d in sorted(doors, key=lambda s: min(s)))
        summary.append(
            (name, len(foot), len(interior), f"{len(doors)} door(s) w[{widths}]")
        )

    # ----- rebuild the block tables (drop phantoms, add new sectors + lobbies) ---
    live_ids = {s for s in sector_m if s != "0"}
    new_sector_rows = [
        [sid, WORLD, name_by_id[sid]] for sid in sorted(live_ids, key=int)
    ]
    new_arena_rows = [
        [sid, WORLD, name_by_id[sid], GROUNDS] for sid in sorted(live_ids, key=int)
    ]
    new_arena_rows += sorted(arena_lobby_rows, key=lambda r: int(r[0]))
    new_arena_rows += sorted(arena_room_rows, key=lambda r: int(r[0]))

    print(
        f"buildings in frame: {len(new_sector_rows)} "
        f"(was {len(sector_rows)} rows incl. phantoms)"
    )
    for name, nf, ni, note in summary:
        print(f"  {name:30} footprint={nf:5} interior={ni:5}  {note}")

    if args.dry_run:
        return

    # ----- write the matrix ------------------------------------------------------
    write_flat(os.path.join(maze, "collision_maze.csv"), collision)
    write_flat(os.path.join(maze, "sector_maze.csv"), sector_m)
    write_flat(os.path.join(maze, "arena_maze.csv"), arena_m)
    write_blocks(os.path.join(blocks, "sector_blocks.csv"), new_sector_rows)
    write_blocks(os.path.join(blocks, "arena_blocks.csv"), new_arena_rows)
    print(f"  wrote matrix CSVs under {os.path.relpath(args.matrix)}")

    # ----- write the picture (plain cutaways) ------------------------------------
    strip_entrance_layers(tmj)
    ensure_interior_tilesets(tmj)
    floor = [0] * (W * H)
    for name, foot, perimeter, door in picture_jobs:
        fb.clear_roof_on(tmj, "buildings", foot, W)
        fb.clear_roof_on(tmj, "trees", foot, W)
        paint_interior(floor, perimeter, foot, door, W)
    insert_entrance_layers(tmj, W, H, floor)
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"  wrote {os.path.relpath(args.tmj)} ({len(picture_jobs)} plain cutaways)")


if __name__ == "__main__":
    main()
