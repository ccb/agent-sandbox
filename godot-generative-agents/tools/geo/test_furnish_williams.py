import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import furnish_williams as fw


def _tmj_with_arenas(objects):
    return {
        "width": 245,
        "height": 279,
        "layers": [
            {"type": "objectgroup", "name": "williams_arenas", "objects": objects},
        ],
    }


def _obj(name, x, y, w, h, t=""):
    return {"name": name, "type": t, "x": x, "y": y, "width": w, "height": h}


def test_read_sections_rounds_px_to_tiles():
    tmj = _tmj_with_arenas([_obj("Classroom A", 208, 3648, 144, 224)])
    secs = fw.read_sections(tmj)
    assert secs["Classroom A"] == (13, 228, 21, 241)


def test_grouped_sections_merges_numbered_and_drops_lobby():
    tmj = _tmj_with_arenas(
        [
            _obj("Classroom B 1", 832, 3776, 240, 80),
            _obj("Classroom B 2", 912, 3712, 160, 64),
            _obj("Lobby 1", 560, 3776, 256, 192),
            _obj("Office", 224, 3952, 208, 144),
        ]
    )
    g = fw.grouped_sections(tmj)
    assert "Lobby" not in g and "Lobby 1" not in g
    assert set(g) == {"Classroom B", "Office"}
    # Classroom B bbox spans both sub-boxes
    c0, r0, c1, r1 = g["Classroom B"]
    assert (c0, r0) == (52, 232) and c1 == 66 and r1 == 240


def _grid(pairs, W=245, H=279):
    d = [0] * (W * H)
    for (x, y), g in pairs.items():
        d[y * W + x] = g
    return d


def _tmj_tiles(floor, furn, walls=None):
    layers = [
        {"type": "tilelayer", "name": "williams_floor", "data": floor},
        {"type": "tilelayer", "name": "williams_furniture", "data": furn},
    ]
    if walls is not None:
        layers.insert(1, {"type": "tilelayer", "name": "williams_walls", "data": walls})
    return {"width": 245, "height": 279, "layers": layers}


def test_compute_relayer_moves_walls_and_windows():
    floor = _grid({(5, 5): fw.WALL_GID, (6, 5): 100})  # a wall + a floor tile
    furn = _grid(
        {(5, 5): fw.WINDOW_GID, (7, 5): 200}
    )  # window over the wall + furniture
    walls, new_floor, new_furn = fw.compute_relayer(_tmj_tiles(floor, furn))
    W = 245
    assert walls[5 * W + 5] == fw.WINDOW_GID  # window wins on the walls layer
    assert new_floor[5 * W + 5] == fw.FLOOR_GID  # floor painted under the moved wall
    assert new_floor[5 * W + 6] == 100  # untouched floor tile stays
    assert new_furn[5 * W + 5] == 0  # window removed from furniture
    assert new_furn[5 * W + 7] == 200  # real furniture stays


def test_compute_relayer_idempotent():
    floor = _grid({(5, 5): fw.WALL_GID})
    furn = _grid({(5, 5): fw.WINDOW_GID})
    walls, nf, nfu = fw.compute_relayer(_tmj_tiles(floor, furn))
    # feed the result back in as an existing williams_walls layer + cleaned floor/furn
    walls2, nf2, nfu2 = fw.compute_relayer(_tmj_tiles(nf, nfu, walls=walls))
    assert walls2 == walls and nf2 == nf and nfu2 == nfu


def test_williams_wall_cells_reads_walls_layer():
    floor = _grid({})
    furn = _grid({})
    walls = _grid({(5, 5): fw.WALL_GID, (6, 5): fw.WINDOW_GID})
    cells = fw.williams_wall_cells(_tmj_tiles(floor, furn, walls=walls))
    assert cells == {(5, 5), (6, 5)}
