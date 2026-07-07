import json
import os

import add_game_objects as ago

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
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


def _fisher_interior_cell():
    """A known walkable Fisher-sector cell we can drop a synthetic object on."""
    sector = _flat("sector_maze.csv")
    coll = _flat("collision_maze.csv")
    for i, s in enumerate(sector):
        if s == ago.FISHER_SECTOR and coll[i] == "0":
            return i % W, i // W
    raise AssertionError("no walkable Fisher cell found")


def _tmj_with_object(x, y):
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    # The real map now carries an authored fisher_objects layer; drop it so this
    # fixture exercises exactly one synthetic object (idx 0 -> id 134000).
    tmj["layers"] = [L for L in tmj["layers"] if L.get("name") != ago.OBJECT_LAYER]
    tmj["layers"].append(
        {
            "type": "objectgroup",
            "name": ago.OBJECT_LAYER,
            "objects": [
                {
                    "name": "bookshelf",
                    "x": x * 16,
                    "y": y * 16,
                    "width": 16,
                    "height": 16,
                }
            ],
        }
    )
    return tmj


def test_read_objects_absent_layer_is_empty():
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    # Strip the authored layer to exercise the absent-layer path.
    tmj["layers"] = [L for L in tmj["layers"] if L.get("name") != ago.OBJECT_LAYER]
    assert ago.read_objects(tmj) == []


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
