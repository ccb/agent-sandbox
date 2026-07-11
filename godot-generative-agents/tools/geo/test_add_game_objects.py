import json
import os

import add_game_objects as ago

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SRC_MATRIX = os.path.join(
    REPO, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
)
SRC_MAP = os.path.join(
    REPO, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
)
W, H = 245, 279


def _flat(name):
    return open(os.path.join(SRC_MATRIX, "maze", name)).read().strip().split(", ")


def _blocks(name):
    rows = []
    for line in open(os.path.join(SRC_MATRIX, "special_blocks", name)):
        if line.strip():
            rows.append([p.strip() for p in line.split(",")])
    return rows


def _sector_names():
    return {r[0]: r[-1] for r in _blocks("sector_blocks.csv") if len(r) >= 3}


# Fisher Fine Arts Library's sector id in the committed matrix. Lives here (its
# only remaining user) since the generalization removed the production fallback.
FISHER_SECTOR = "34"


def _first_walkable_cell(maze_name, value):
    """First cell whose ``maze_name`` entry equals *value* and is walkable —
    a spot we can safely drop a synthetic test object on."""
    grid = _flat(maze_name)
    coll = _flat("collision_maze.csv")
    for i, v in enumerate(grid):
        if v == value and coll[i] == "0":
            return i % W, i // W
    raise AssertionError(f"no walkable cell with {maze_name} == {value}")


def _fisher_interior_cell():
    return _first_walkable_cell("sector_maze.csv", FISHER_SECTOR)


def _houston_lobby_cell():
    return _first_walkable_cell("arena_maze.csv", "1014")


def _strip_object_layers(tmj):
    tmj["layers"] = [
        L
        for L in tmj["layers"]
        if not (L.get("name") or "").endswith(ago.OBJECT_LAYER_SUFFIX)
    ]


def _object_layer(name, objects):
    return {
        "type": "objectgroup",
        "name": name,
        "objects": [
            {"name": n, "x": x * 16, "y": y * 16, "width": 16, "height": 16}
            for n, x, y in objects
        ],
    }


def _tmj_with_object(x, y):
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    # The real map carries authored *_objects layers; drop them so this
    # fixture exercises exactly one synthetic object (idx 0 -> id 134000).
    _strip_object_layers(tmj)
    tmj["layers"].append(_object_layer("fisher_objects", [("bookshelf", x, y)]))
    return tmj


def test_read_objects_absent_layer_is_empty():
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    _strip_object_layers(tmj)
    assert ago.read_objects(tmj) == []


def test_multi_layer_scan_assigns_per_sector_ids():
    """#466: two *_objects layers scan in order; ids number per sector, so
    adding a building never renumbers another building's objects."""
    x_f, y_f = _fisher_interior_cell()
    x_h, y_h = _houston_lobby_cell()
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    _strip_object_layers(tmj)
    tmj["layers"].append(_object_layer("fisher_objects", [("bookshelf", x_f, y_f)]))
    tmj["layers"].append(_object_layer("houston_objects", [("sink", x_h, y_h)]))
    coll, arena, sector = (
        _flat("collision_maze.csv"),
        _flat("arena_maze.csv"),
        _flat("sector_maze.csv"),
    )
    _, obj_maze, rows = ago.paint_objects(
        tmj, coll, arena, sector, _sector_names(), W, H
    )
    assert [r[0] for r in rows] == ["134000", "114000"]
    assert obj_maze[y_f * W + x_f] == "134000"
    assert obj_maze[y_h * W + x_h] == "114000"
    assert rows[1][2] == "Houston Hall"
    assert rows[1][-1] == "sink"


def test_paint_assigns_id_and_reopens_use_tile():
    x, y = _fisher_interior_cell()
    tmj = _tmj_with_object(x, y)
    coll = _flat("collision_maze.csv")
    coll[y * W + x] = "1"  # pretend furniture sealed it; paint must re-open
    arena, sector = _flat("arena_maze.csv"), _flat("sector_maze.csv")
    new_coll, obj_maze, rows = ago.paint_objects(
        tmj, coll, arena, sector, _sector_names(), W, H
    )
    i = y * W + x
    assert new_coll[i] == "0"  # re-opened walkable
    assert obj_maze[i] == "134000"  # 100000 + 34*1000 + 0
    assert rows[0][0] == "134000"
    assert rows[0][-1] == "bookshelf"
    assert rows[0][1] == "UPenn"


def test_object_cells_share_one_arena_containment():
    x, y = _fisher_interior_cell()
    tmj = _tmj_with_object(x, y)
    coll, arena, sector = (
        _flat("collision_maze.csv"),
        _flat("arena_maze.csv"),
        _flat("sector_maze.csv"),
    )
    _, _, rows = ago.paint_objects(tmj, coll, arena, sector, _sector_names(), W, H)
    assert rows[0][3]  # arena name resolved (non-empty)


def test_real_map_paint_matches_committed_matrix():
    """The committed game-object CSVs are exactly what a re-run would paint --
    catches hand-edit drift, and pins Fisher's ids byte-stable under the
    multi-layer scan (#466)."""
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    coll, arena, sector = (
        _flat("collision_maze.csv"),
        _flat("arena_maze.csv"),
        _flat("sector_maze.csv"),
    )
    new_coll, obj_maze, rows = ago.paint_objects(
        tmj, coll, arena, sector, _sector_names(), W, H
    )
    assert new_coll == coll  # every use-tile already open in the committed maze
    assert obj_maze == _flat("game_object_maze.csv")
    assert [r for r in rows] == _blocks("game_object_blocks.csv")


def test_degenerate_out_of_bounds_rect_is_skipped():
    """A rect fully outside the grid paints nothing and books no id."""
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    _strip_object_layers(tmj)
    tmj["layers"].append(_object_layer("fisher_objects", [("ghost", 9999, 9999)]))
    coll, arena, sector = (
        _flat("collision_maze.csv"),
        _flat("arena_maze.csv"),
        _flat("sector_maze.csv"),
    )
    new_coll, obj_maze, rows = ago.paint_objects(
        tmj, coll, arena, sector, _sector_names(), W, H
    )
    assert rows == []
    assert new_coll == coll
    assert all(g == "0" for g in obj_maze)
