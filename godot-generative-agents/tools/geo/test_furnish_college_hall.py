import json, os
import furnish_college_hall as fc

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
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
    return {(i % W, i // W) for i in fc.college_interior_cells(tmj, MATRIX)}


def test_floor_covers_interior_only():
    tmj = _fresh()
    fc.apply(tmj, MATRIX)
    assert _cells(tmj, "college_hall_floor") == _interior(tmj)


def test_layer_stack_order():
    tmj = _fresh()
    fc.apply(tmj, MATRIX)
    fc.apply_walls(tmj, MATRIX)
    fc.apply_furniture(tmj, MATRIX)
    names = [L.get("name") for L in tmj["layers"]]
    ef = names.index("entrance_floor")
    assert names[ef + 1 : ef + 6] == [
        "college_hall_floor",
        "college_hall_walls",
        "college_hall_rugs",
        "college_hall_furniture",
        "college_hall_props",
    ]


def test_walls_on_interior_with_doorways():
    tmj = _fresh()
    fc.apply(tmj, MATRIX)
    placed, doors, _removed = fc.apply_walls(tmj, MATRIX)
    assert placed > 0 and doors > 0
    assert _cells(tmj, "college_hall_walls") <= _interior(tmj)


def test_no_double_walls():
    tmj = _fresh()
    fc.apply(tmj, MATRIX)
    fc.apply_walls(tmj, MATRIX)
    W, H = tmj["width"], tmj["height"]
    wl = next(L for L in tmj["layers"] if L.get("name") == "college_hall_walls")["data"]
    bad = 0
    for r in range(H - 1):
        for c in range(W - 1):
            quad = (
                wl[r * W + c],
                wl[r * W + c + 1],
                wl[(r + 1) * W + c],
                wl[(r + 1) * W + c + 1],
            )
            if sum(1 for g in quad if g in fc.WALL_SET) >= 4:
                bad += 1
    assert bad == 0, f"{bad} 2x2 windows hold 4 wall_set_red cells (double walls)"


def test_open_seams_have_no_walls():
    tmj = _fresh()
    fc.apply(tmj, MATRIX)
    fc.apply_walls(tmj, MATRIX)
    W = tmj["width"]
    sections = fc.read_sections(tmj)
    walls = _cells(tmj, "college_hall_walls")
    for a, b in fc.OPEN_SEAMS:
        if a not in sections or b not in sections:
            continue
        ax0, ay0, ax1, ay1 = sections[a]
        bx0, by0, bx1, by1 = sections[b]
        if ay1 <= by0 or by1 <= ay0:
            r0, r1 = (ay1, by0) if ay1 <= by0 else (by1, ay0)
            cs, ce = max(ax0, bx0), min(ax1, bx1)
            band = [(c, r) for r in range(r0, r1 + 1) for c in range(cs, ce + 1)]
        else:
            c0, c1 = (ax1, bx0) if ax1 <= bx0 else (bx1, ax0)
            rs, re = max(ay0, by0), min(ay1, by1)
            band = [(c, r) for c in range(c0, c1 + 1) for r in range(rs, re + 1)]
        assert not (set(band) & walls), f"seam {a}<->{b} still has walls"


def test_furniture_rugs_props_only_on_interior():
    tmj = _fresh()
    fc.apply(tmj, MATRIX)
    fc.apply_walls(tmj, MATRIX)
    fc.apply_furniture(tmj, MATRIX)
    interior = _interior(tmj)
    for layer in ("college_hall_rugs", "college_hall_furniture", "college_hall_props"):
        outside = _cells(tmj, layer) - interior
        assert (
            not outside
        ), f"{layer} has cells outside the interior: {sorted(outside)[:5]}"


def test_stamp_refuses_partial_sprite():
    sprites = fc.load_sprites(_fresh())
    _gid, w, h, _cols = sprites["bookshelf"]  # a 2x3 sprite
    W, GH = 10, 20
    full = {(c, r) for r in range(h) for c in range(w)}

    data = [0] * (W * GH)
    occ = set()
    assert fc._stamp(data, occ, sprites, "bookshelf", 0, 0, full - {(1, 2)}, W) is False
    assert all(v == 0 for v in data) and not occ

    assert fc._stamp(data, occ, sprites, "bookshelf", 0, 0, full, W) is True
    assert sum(1 for v in data if v) == w * h and len(occ) == w * h


def test_idempotent():
    a = _fresh()
    fc.apply(a, MATRIX)
    fc.apply_walls(a, MATRIX)
    fc.apply_furniture(a, MATRIX)
    b = _fresh()
    fc.apply(b, MATRIX)
    fc.apply_walls(b, MATRIX)
    fc.apply_furniture(b, MATRIX)
    layers = (
        "college_hall_floor",
        "college_hall_walls",
        "college_hall_rugs",
        "college_hall_furniture",
        "college_hall_props",
    )
    da = {n: next(L["data"] for L in a["layers"] if L["name"] == n) for n in layers}
    db = {n: next(L["data"] for L in b["layers"] if L["name"] == n) for n in layers}
    assert da == db
