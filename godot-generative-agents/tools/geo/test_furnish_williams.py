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


import json, shutil


def test_apply_to_file_content_and_order(tmp_path):
    src = os.path.join(
        os.path.dirname(os.path.dirname(HERE)), "godot", "maps", "upenn_core_urban.tmj"
    )
    # note: HERE is tools/geo; the committed tmj is under godot/maps
    repo_map = os.path.normpath(
        os.path.join(HERE, "..", "..", "godot", "maps", "upenn_core_urban.tmj")
    )
    dst = str(tmp_path / "map.tmj")
    shutil.copy2(repo_map, dst)
    fw.apply_to_file(dst)
    t = json.load(open(dst))  # must parse
    layers = {L["name"]: L for L in t["layers"] if L.get("type") == "tilelayer"}
    W = t["width"]
    walls = layers["williams_walls"]["data"]
    from collections import Counter

    wc = Counter(g & fw.GID_MASK for g in walls if g)
    assert wc == {fw.WALL_GID: 340, fw.WINDOW_GID: 46}
    assert (
        sum(
            1
            for g in layers["williams_floor"]["data"]
            if (g & fw.GID_MASK) == fw.WALL_GID
        )
        == 0
    )
    assert (
        sum(
            1
            for g in layers["williams_furniture"]["data"]
            if (g & fw.GID_MASK) == fw.WINDOW_GID
        )
        == 0
    )
    ar = next(L for L in t["layers"] if L.get("name") == "williams_arenas")
    assert len(ar["objects"]) == 8
    names = [L["name"] for L in t["layers"]]
    assert (
        names.index("williams_floor")
        < names.index("williams_walls")
        < names.index("williams_furniture")
    )


def _layers_text(*blocks):
    """A minimal tmj-shaped text: a layers array of the given raw layer blocks,
    joined Tiled-style (',\\n        ' between blocks, 8-space indent)."""
    joined = ",\n        ".join(blocks)
    return '{\n "nextlayerid":9,\n "layers":[\n        ' + joined + "\n ]\n}"


def _tile_block(name, lid, data="0, 0, 0"):
    return (
        "{\n"
        f'         "data":[{data}],\n'
        f'         "id":{lid},\n'
        f'         "name":"{name}",\n'
        '         "type":"tilelayer"\n'
        "        }"
    )


def _obj_block(name, lid):
    return (
        "{\n"
        f'         "id":{lid},\n'
        f'         "name":"{name}",\n'
        '         "objects":[\n                {\n                 "id":1,\n                 "name":"R"\n                }],\n'
        '         "type":"objectgroup"\n'
        "        }"
    )


def test_strip_layer_removes_middle_block_valid_json():
    import json

    text = _layers_text(
        _tile_block("a", 1), _tile_block("williams_walls", 2), _tile_block("b", 3)
    )
    out = fw._strip_layer(text, "williams_walls")
    parsed = json.loads(out)  # still valid JSON
    names = [L["name"] for L in parsed["layers"]]
    assert names == ["a", "b"]


def test_strip_layer_removes_last_block_valid_json():
    import json

    text = _layers_text(_tile_block("a", 1), _obj_block("williams_arenas", 2))
    out = fw._strip_layer(text, "williams_arenas")
    parsed = json.loads(out)
    assert [L["name"] for L in parsed["layers"]] == ["a"]


def test_strip_layer_absent_is_noop():
    text = _layers_text(_tile_block("a", 1))
    assert fw._strip_layer(text, "williams_walls") == text


def test_strip_layer_duplicate_raises():
    import pytest

    text = _layers_text(
        _tile_block("williams_walls", 1), _tile_block("williams_walls", 2)
    )
    with pytest.raises(ValueError):
        fw._strip_layer(text, "williams_walls")


def test_replace_layer_data_duplicate_name_raises():
    import pytest

    text = _layers_text(_tile_block("dup", 1), _tile_block("dup", 2))
    with pytest.raises(ValueError):
        fw._replace_layer_data(text, "dup", [1, 2, 3], 3)


import os, shutil, subprocess, sys


def _committed_tmj():
    return os.path.normpath(
        os.path.join(HERE, "..", "..", "godot", "maps", "upenn_core_urban.tmj")
    )


def test_apply_to_file_reproduces_committed_tmj(tmp_path):
    """Running the hardened splice on a copy of the committed tmj yields a
    byte-identical file (strip-then-reinsert reuses the existing ids)."""
    src = _committed_tmj()
    dst = str(tmp_path / "map.tmj")
    shutil.copy2(src, dst)
    fw.apply_to_file(dst)
    with open(src, "rb") as a, open(dst, "rb") as b:
        assert a.read() == b.read(), "hardened apply_to_file changed the committed tmj"


def test_apply_to_file_idempotent_second_run(tmp_path):
    src = _committed_tmj()
    dst = str(tmp_path / "map.tmj")
    shutil.copy2(src, dst)
    fw.apply_to_file(dst)
    after_one = open(dst, "rb").read()
    fw.apply_to_file(dst)
    assert open(dst, "rb").read() == after_one, "second run was not a no-op"


def test_apply_to_file_no_duplicate_layers(tmp_path):
    import json

    src = _committed_tmj()
    dst = str(tmp_path / "map.tmj")
    shutil.copy2(src, dst)
    fw.apply_to_file(dst)
    fw.apply_to_file(dst)  # twice
    t = json.load(open(dst))
    names = [L["name"] for L in t["layers"]]
    assert names.count("williams_walls") == 1
    assert names.count("williams_arenas") == 1


def test_arena_objects_prefers_authored_layer():
    # When a williams_arenas layer exists, its own objects are the source of
    # truth -- NOT the WILLIAMS_ARENA_OBJECTS constant.
    authored = [_obj("Custom Room", 100, 200, 300, 400, t="classroom")]
    tmj = _tmj_with_arenas(authored)
    assert fw._arena_objects(tmj) == authored
    assert fw._arena_objects(tmj) is not fw.WILLIAMS_ARENA_OBJECTS


def test_arena_objects_falls_back_to_constant_when_absent():
    # Fresh bake with no arenas layer yet: seed from the constant.
    tmj = {"width": 245, "height": 279, "layers": []}
    assert fw._arena_objects(tmj) == fw.WILLIAMS_ARENA_OBJECTS


def test_arena_objects_falls_back_when_layer_empty():
    tmj = _tmj_with_arenas([])
    assert fw._arena_objects(tmj) == fw.WILLIAMS_ARENA_OBJECTS
