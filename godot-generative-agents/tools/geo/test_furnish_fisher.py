import copy, json, os
import furnish_fisher as ff

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
    return {(i % W, i // W) for i in ff.fisher_interior_cells(tmj, MATRIX)}


def test_floor_covers_interior_only():
    # floor fills exactly the carved interior (footprint minus perimeter ring)
    tmj = _fresh()
    ff.apply(tmj, MATRIX)
    assert _cells(tmj, "fisher_floor") == _interior(tmj)


def test_layer_stack_order():
    tmj = _fresh()
    ff.apply(tmj, MATRIX)
    ff.apply_walls(tmj, MATRIX)
    ff.apply_furniture(tmj, MATRIX)
    names = [L.get("name") for L in tmj["layers"]]
    ef = names.index("entrance_floor")
    assert names[ef + 1 : ef + 5] == [
        "fisher_floor",
        "fisher_walls",
        "fisher_rugs",
        "fisher_furniture",
    ]


def test_walls_on_interior_with_doorways():
    tmj = _fresh()
    ff.apply(tmj, MATRIX)
    placed, doors = ff.apply_walls(tmj, MATRIX)
    assert placed > 0 and doors > 0  # partitions exist, and each has a gap
    assert _cells(tmj, "fisher_walls") <= _interior(tmj)


def test_furniture_and_rugs_only_on_interior():
    tmj = _fresh()
    ff.apply(tmj, MATRIX)
    ff.apply_walls(tmj, MATRIX)
    ff.apply_furniture(tmj, MATRIX)
    interior = _interior(tmj)
    for layer in ("fisher_rugs", "fisher_furniture"):
        outside = _cells(tmj, layer) - interior
        assert (
            not outside
        ), f"{layer} has cells outside the interior: {sorted(outside)[:5]}"


def test_stamp_refuses_partial_sprite():
    # cardinal rule: a multi-tile sprite is placed whole or not at all
    sprites = ff.load_sprites()
    _gid, w, h, _sheet = sprites["bookshelf"]  # a 2x3 sprite
    W, GH = 10, 20
    full = {(c, r) for r in range(h) for c in range(w)}

    data = [0] * (W * GH)
    occ = set()
    assert ff._stamp(data, occ, sprites, "bookshelf", 0, 0, full - {(1, 2)}, W) is False
    assert all(v == 0 for v in data) and not occ  # refused -> wrote nothing

    assert ff._stamp(data, occ, sprites, "bookshelf", 0, 0, full, W) is True
    assert sum(1 for v in data if v) == w * h and len(occ) == w * h


def test_rug_runners_fill_their_boxes():
    tmj = _fresh()
    ff.apply(tmj, MATRIX)
    ff.apply_walls(tmj, MATRIX)
    ff.apply_furniture(tmj, MATRIX)
    boxes = ff.read_rug_boxes(tmj)
    assert boxes, "expected hand-drawn rug boxes in fisher_arenas"
    rugs = _cells(tmj, "fisher_rugs")
    for name, (c0, r0, c1, r1) in boxes:
        in_box = [
            (c, r)
            for r in range(r0, r1 + 1)
            for c in range(c0, c1 + 1)
            if (c, r) in rugs
        ]
        assert in_box, f"rug box {name!r} was not filled"


def test_idempotent():
    a = _fresh()
    ff.apply(a, MATRIX)
    ff.apply_walls(a, MATRIX)
    ff.apply_furniture(a, MATRIX)
    b = _fresh()
    ff.apply(b, MATRIX)
    ff.apply_walls(b, MATRIX)
    ff.apply_furniture(b, MATRIX)
    layers = ("fisher_floor", "fisher_walls", "fisher_rugs", "fisher_furniture")
    da = {n: next(L["data"] for L in a["layers"] if L["name"] == n) for n in layers}
    db = {n: next(L["data"] for L in b["layers"] if L["name"] == n) for n in layers}
    assert da == db
