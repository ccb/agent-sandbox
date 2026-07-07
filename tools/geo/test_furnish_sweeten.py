import json, os
import furnish_sweeten as fs

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


def _layer(tmj, name):
    return next(L["data"] for L in tmj["layers"] if L.get("name") == name)


def _cells(tmj, name):
    W = tmj["width"]
    return {(i % W, i // W) for i, v in enumerate(_layer(tmj, name)) if v}


def _interior(tmj):
    W = tmj["width"]
    return {(i % W, i // W) for i in fs.sweeten_interior_cells(tmj, MATRIX)}


def test_floor_covers_interior_only():
    tmj = _fresh()
    fs.apply(tmj, MATRIX)
    assert _cells(tmj, "sweeten_floor") == _interior(tmj)


def test_floor_sits_above_entrance_floor():
    tmj = _fresh()
    fs.apply(tmj, MATRIX)
    names = [L.get("name") for L in tmj["layers"]]
    assert names[names.index("entrance_floor") + 1] == "sweeten_floor"


def test_floor_gid_resolves_no_red_x():
    # the floor tile is read live from the franuka tileset firstgid, so it can
    # never desync into an out-of-range red-X gid
    tmj = _fresh()
    fs.apply(tmj, MATRIX)
    ts = [
        (t["firstgid"], t["firstgid"] + t["tilecount"] - 1)
        for t in tmj["tilesets"]
        if "tilecount" in t
    ]

    def covered(g):
        g &= 0x1FFFFFFF
        return any(a <= g <= b for a, b in ts)

    bad = {v for v in _layer(tmj, "sweeten_floor") if v and not covered(v)}
    assert not bad, f"sweeten_floor has uncovered (red-X) gids: {sorted(bad)[:5]}"


def test_idempotent():
    a = _fresh()
    fs.apply(a, MATRIX)
    b = _fresh()
    fs.apply(b, MATRIX)
    assert _layer(a, "sweeten_floor") == _layer(b, "sweeten_floor")
