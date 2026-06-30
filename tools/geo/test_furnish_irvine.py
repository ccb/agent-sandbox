import json, os
import furnish_irvine as fi

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAP = os.path.join(REPO, "godot-generative-agents", "maps", "upenn_core_urban.tmj")
MATRIX = os.path.join(REPO, "godot-generative-agents", "sim", "the_upenn", "matrix")


def _fresh():
    with open(MAP) as fh:
        return json.load(fh)


def _layer(tmj, name):
    return next(L["data"] for L in tmj["layers"] if L.get("name") == name)


def _cells(tmj, name):
    W = tmj["width"]
    return {(i % W, i // W) for i, v in enumerate(_layer(tmj, name)) if v}


def _interior(tmj):
    W = tmj["width"]
    return {(i % W, i // W) for i in fi.irvine_interior_cells(tmj, MATRIX)}


def test_floor_covers_interior_only():
    tmj = _fresh()
    fi.apply(tmj, MATRIX)
    assert _cells(tmj, "irvine_floor") == _interior(tmj)


def test_layer_stack_order():
    tmj = _fresh()
    fi.apply(tmj, MATRIX)
    fi.apply_walls(tmj, MATRIX)
    fi.apply_furniture(tmj, MATRIX)
    names = [L.get("name") for L in tmj["layers"]]
    ef = names.index("entrance_floor")
    assert names[ef + 1 : ef + 5] == [
        "irvine_floor", "irvine_walls", "irvine_rugs", "irvine_furniture",
    ]


def test_walls_on_interior_with_doorways():
    tmj = _fresh()
    fi.apply(tmj, MATRIX)
    placed, doors, _removed = fi.apply_walls(tmj, MATRIX)
    assert placed > 0 and doors > 0
    assert _cells(tmj, "irvine_walls") <= _interior(tmj)


def test_furniture_and_rugs_only_on_interior():
    tmj = _fresh()
    fi.apply(tmj, MATRIX)
    fi.apply_walls(tmj, MATRIX)
    fi.apply_furniture(tmj, MATRIX)
    interior = _interior(tmj)
    for layer in ("irvine_rugs", "irvine_furniture"):
        outside = _cells(tmj, layer) - interior
        assert not outside, f"{layer} has cells outside interior: {sorted(outside)[:5]}"


def test_furniture_gids_resolve_no_red_x():
    # locks in the firstgid fix: every placed gid (incl. the music/clockwork
    # expansion-sheet instruments + organ) must be covered by a tileset
    tmj = _fresh()
    fi.apply(tmj, MATRIX)
    fi.apply_walls(tmj, MATRIX)
    fi.apply_furniture(tmj, MATRIX)
    ts = [(t["firstgid"], t["firstgid"] + t["tilecount"] - 1)
          for t in tmj["tilesets"] if "tilecount" in t]

    def covered(g):
        g &= 0x1FFFFFFF
        return any(a <= g <= b for a, b in ts)

    for layer in ("irvine_furniture", "irvine_rugs"):
        bad = {v for v in _layer(tmj, layer) if v and not covered(v)}
        assert not bad, f"{layer} has uncovered (red-X) gids: {sorted(bad)[:5]}"
    # the organ + instruments actually landed
    sprites = fi.load_sprites(tmj)
    furn = set(_layer(tmj, "irvine_furniture"))
    for name in ("pipe_organ", "harp_gold", "cello", "double_bass"):
        assert sprites[name][0] in furn, f"{name} not placed"


def test_stamp_refuses_partial_sprite():
    sprites = fi.load_sprites(_fresh())
    _gid, w, h, _sheet = sprites["bookshelf"]  # a 2x3 sprite
    W, GH = 10, 20
    full = {(c, r) for r in range(h) for c in range(w)}
    data = [0] * (W * GH)
    occ = set()
    assert fi._stamp(data, occ, sprites, "bookshelf", 0, 0, full - {(1, 2)}, W) is False
    assert all(v == 0 for v in data) and not occ
    assert fi._stamp(data, occ, sprites, "bookshelf", 0, 0, full, W) is True
    assert sum(1 for v in data if v) == w * h and len(occ) == w * h


def test_idempotent():
    a = _fresh()
    fi.apply(a, MATRIX); fi.apply_walls(a, MATRIX); fi.apply_furniture(a, MATRIX)
    b = _fresh()
    fi.apply(b, MATRIX); fi.apply_walls(b, MATRIX); fi.apply_furniture(b, MATRIX)
    layers = ("irvine_floor", "irvine_walls", "irvine_rugs", "irvine_furniture")
    da = {n: next(L["data"] for L in a["layers"] if L["name"] == n) for n in layers}
    db = {n: next(L["data"] for L in b["layers"] if L["name"] == n) for n in layers}
    assert da == db
