import json, os
import furnish_houston as fh

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAP = os.path.join(REPO, "godot-generative-agents", "maps", "upenn_core_urban.tmj")
MATRIX = os.path.join(REPO, "godot-generative-agents", "sim", "the_upenn", "matrix")


def _fresh():
    with open(MAP) as fh_:
        return json.load(fh_)


def _cells(tmj, name):
    W = tmj["width"]
    L = next(x for x in tmj["layers"] if x.get("name") == name)
    return {(i % W, i // W) for i, v in enumerate(L["data"]) if v}


def _interior(tmj):
    W = tmj["width"]
    return {(i % W, i // W) for i in fh.houston_interior_cells(tmj, MATRIX)}


def test_floor_covers_interior_only():
    tmj = _fresh()
    fh.apply(tmj, MATRIX)
    assert _cells(tmj, "houston_floor") == _interior(tmj)


def test_layer_stack_order():
    tmj = _fresh()
    fh.apply(tmj, MATRIX)
    fh.apply_walls(tmj, MATRIX)
    fh.apply_furniture(tmj, MATRIX)
    names = [L.get("name") for L in tmj["layers"]]
    ef = names.index("entrance_floor")
    assert names[ef + 1:ef + 5] == [
        "houston_floor", "houston_walls", "houston_rugs", "houston_furniture"]


def test_walls_on_interior_with_doorways():
    tmj = _fresh()
    fh.apply(tmj, MATRIX)
    placed, doors, _removed = fh.apply_walls(tmj, MATRIX)
    assert placed > 0 and doors > 0
    assert _cells(tmj, "houston_walls") <= _interior(tmj)


def test_no_2x2_has_four_walls():
    # the rule the user asked for: never two walls next to each other
    tmj = _fresh()
    fh.apply(tmj, MATRIX)
    fh.apply_walls(tmj, MATRIX)
    W, H = tmj["width"], tmj["height"]
    wl = next(L for L in tmj["layers"] if L.get("name") == "houston_walls")["data"]
    bad = 0
    for r in range(H - 1):
        for c in range(W - 1):
            quad = (wl[r * W + c], wl[r * W + c + 1],
                    wl[(r + 1) * W + c], wl[(r + 1) * W + c + 1])
            if sum(1 for g in quad if g in fh.WALL_SET) >= 4:
                bad += 1
    assert bad == 0, f"{bad} 2x2 windows hold 4 wall_set_red cells (double walls)"


def test_furniture_and_rugs_only_on_interior():
    tmj = _fresh()
    fh.apply(tmj, MATRIX)
    fh.apply_walls(tmj, MATRIX)
    fh.apply_furniture(tmj, MATRIX)
    interior = _interior(tmj)
    for layer in ("houston_rugs", "houston_furniture"):
        outside = _cells(tmj, layer) - interior
        assert not outside, f"{layer} has cells outside the interior: {sorted(outside)[:5]}"


def test_stamp_refuses_partial_sprite():
    # cardinal rule: a multi-tile sprite is placed whole or not at all
    sprites = fh.load_sprites()
    _gid, w, h, _sheet = sprites["bookshelf"]  # a 2x3 sprite
    W, GH = 10, 20
    full = {(c, r) for r in range(h) for c in range(w)}

    data = [0] * (W * GH)
    occ = set()
    assert fh._stamp(data, occ, sprites, "bookshelf", 0, 0, full - {(1, 2)}, W) is False
    assert all(v == 0 for v in data) and not occ

    assert fh._stamp(data, occ, sprites, "bookshelf", 0, 0, full, W) is True
    assert sum(1 for v in data if v) == w * h and len(occ) == w * h


def test_idempotent():
    a = _fresh()
    fh.apply(a, MATRIX); fh.apply_walls(a, MATRIX); fh.apply_furniture(a, MATRIX)
    b = _fresh()
    fh.apply(b, MATRIX); fh.apply_walls(b, MATRIX); fh.apply_furniture(b, MATRIX)
    layers = ("houston_floor", "houston_walls", "houston_rugs", "houston_furniture")
    da = {n: next(L["data"] for L in a["layers"] if L["name"] == n) for n in layers}
    db = {n: next(L["data"] for L in b["layers"] if L["name"] == n) for n in layers}
    assert da == db
