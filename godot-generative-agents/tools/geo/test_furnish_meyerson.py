import json, os
import furnish_meyerson as fm

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MAP = os.path.join(
    REPO, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
)
MATRIX = os.path.join(
    REPO, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
)


def _fresh():
    with open(MAP) as fh:
        return json.load(fh)


def _cells(tmj, name):
    W = tmj["width"]
    L = next(x for x in tmj["layers"] if x.get("name") == name)
    return {(i % W, i // W) for i, v in enumerate(L["data"]) if v}


def _interior(tmj):
    W = tmj["width"]
    return {(i % W, i // W) for i in fm.meyerson_interior_cells(tmj, MATRIX)}


def test_floor_covers_interior_only():
    tmj = _fresh()
    fm.apply(tmj, MATRIX)
    assert _cells(tmj, "meyerson_floor") == _interior(tmj)


def test_layer_stack_order():
    tmj = _fresh()
    fm.apply(tmj, MATRIX)
    fm.apply_walls(tmj, MATRIX)
    fm.apply_furniture(tmj, MATRIX)
    names = [L.get("name") for L in tmj["layers"]]
    ef = names.index("entrance_floor")
    assert names[ef + 1 : ef + 6] == [
        "meyerson_floor",
        "meyerson_walls",
        "meyerson_rugs",
        "meyerson_furniture",
        "meyerson_props",
    ]


def test_walls_on_interior_with_doorways():
    tmj = _fresh()
    fm.apply(tmj, MATRIX)
    placed, doors = fm.apply_walls(tmj, MATRIX)
    assert placed > 0 and doors > 0
    assert _cells(tmj, "meyerson_walls") <= _interior(tmj)


def test_furniture_rugs_props_only_on_interior():
    tmj = _fresh()
    fm.apply(tmj, MATRIX)
    fm.apply_walls(tmj, MATRIX)
    fm.apply_furniture(tmj, MATRIX)
    interior = _interior(tmj)
    for layer in ("meyerson_rugs", "meyerson_furniture", "meyerson_props"):
        outside = _cells(tmj, layer) - interior
        assert (
            not outside
        ), f"{layer} has cells outside the interior: {sorted(outside)[:5]}"


def test_stamp_refuses_partial_sprite():
    # cardinal rule: a multi-tile sprite is placed whole or not at all
    sprites = fm.load_sprites(_fresh())
    _gid, w, h, _cols = sprites["dining_table"]  # a 2x3 sprite
    W, GH = 12, 24
    full = {(c, r) for r in range(h) for c in range(w)}
    data = [0] * (W * GH)
    occ = set()
    assert (
        fm._stamp(data, occ, sprites, "dining_table", 0, 0, full - {(1, 2)}, W) is False
    )
    assert all(v == 0 for v in data) and not occ
    assert fm._stamp(data, occ, sprites, "dining_table", 0, 0, full, W) is True
    assert sum(1 for v in data if v) == w * h and len(occ) == w * h


def test_gallery_rug_fills_floor():
    tmj = _fresh()
    fm.apply(tmj, MATRIX)
    fm.apply_walls(tmj, MATRIX)
    fm.apply_furniture(tmj, MATRIX)
    sections = fm.read_sections(tmj)
    c0, r0, c1, r1 = sections["South Gallery"]
    rugs = _cells(tmj, "meyerson_rugs")
    in_gallery = [(c, r) for (c, r) in rugs if c0 <= c <= c1 and r0 <= r <= r1]
    assert len(in_gallery) > 20, "expected a long runner rug filling the gallery"


def test_idempotent():
    a = _fresh()
    fm.apply(a, MATRIX)
    fm.apply_walls(a, MATRIX)
    fm.apply_furniture(a, MATRIX)
    b = _fresh()
    fm.apply(b, MATRIX)
    fm.apply_walls(b, MATRIX)
    fm.apply_furniture(b, MATRIX)
    layers = (
        "meyerson_floor",
        "meyerson_walls",
        "meyerson_rugs",
        "meyerson_furniture",
        "meyerson_props",
    )
    da = {n: next(L["data"] for L in a["layers"] if L["name"] == n) for n in layers}
    db = {n: next(L["data"] for L in b["layers"] if L["name"] == n) for n in layers}
    assert da == db
