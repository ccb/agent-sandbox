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
