# godot-generative-agents/tools/geo/test_furnish_building_gids.py
"""#746: expansion-sheet firstgids come from the map's own tilesets, not pins.

Round-trips a known tile from EACH expansion sheet through furnish_building's
gid()/tile_named() helpers onto a scratch COPY of the committed campus map and
checks validate_tmj classifies the result. The committed .tmj is only ever
READ here (#641: geo tooling must not re-serialize the pretty-printed map);
every write goes to tmp_path, and the round-trip test asserts the committed
bytes are untouched.
"""

import json
import os

import pytest

import furnish_building as fb
import validate_tmj as v

REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
TMJ = os.path.join(
    REPO, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
)
MATRIX = os.path.join(
    REPO, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
)

# One known furniture_catalog.json object per expansion sheet.
EXPANSION_SAMPLES = {
    "interior_alchemy": "shelf_metal",
    "interior_bedroom": "double_bed",
    "interior_clockwork": "pipe_organ",
    "interior_music": "wall_set_silver",  # category "wall" -> #738 classifier
}


@pytest.fixture(autouse=True)
def _restore_fb_bindings():
    """bind_sheet_firstgids mutates module state; leave fb as we found it so
    test order never leaks a rebound map into other geo test modules."""
    first, cols = dict(fb._FIRST), dict(fb._COLS)
    palette = (fb.FLOOR, fb.WALL, fb.WINDOW)
    yield
    fb._FIRST.clear()
    fb._FIRST.update(first)
    fb._COLS.clear()
    fb._COLS.update(cols)
    fb.FLOOR, fb.WALL, fb.WINDOW = palette


def _committed_tmj():
    with open(TMJ) as fh:
        return json.load(fh)


def test_unbound_expansion_sheet_fails_loudly():
    # Import-time state: no map bound yet (an earlier test module may have
    # bound one, so drop any binding explicitly; the fixture restores after).
    for sheet in EXPANSION_SAMPLES:
        fb._FIRST.pop(sheet, None)
    with pytest.raises(KeyError, match="bind_sheet_firstgids"):
        fb.gid("interior_music", 0, 0)


def test_bind_derives_firstgids_from_the_committed_map():
    tmj = _committed_tmj()
    bound = fb.bind_sheet_firstgids(tmj)
    by_name = {ts["name"]: ts for ts in tmj["tilesets"]}
    for sheet in EXPANSION_SAMPLES:
        assert bound[sheet] == by_name[sheet]["firstgid"]
        assert fb.gid(sheet, 0, 0) == by_name[sheet]["firstgid"]
    # the committed map's real layout, not the pins this fix retired
    # (3000/4024/5048/6072):
    assert bound["interior_alchemy"] == 2139
    assert bound["interior_music"] == 5211
    # base sheets + the Kenney block re-derive from the map too
    assert bound["interior_franuka"] == by_name["interior_franuka"]["firstgid"]
    assert bound["kenney_urban"] == 1


def test_expansion_paint_round_trip_classifies(tmp_path):
    with open(TMJ, "rb") as fh:
        raw = fh.read()  # byte-identity guard: the committed map is read-only
    tmj = json.loads(raw)
    fb.bind_sheet_firstgids(tmj)
    by_name = {ts["name"]: ts for ts in tmj["tilesets"]}

    # Paint one known catalog tile from each expansion sheet onto a tile layer
    # of the scratch copy, through the script's own helpers.
    layer = next(L for L in tmj["layers"] if L.get("name") == "williams_furniture")
    W = tmj["width"]
    painted = {}
    for i, (sheet, obj_name) in enumerate(sorted(EXPANSION_SAMPLES.items())):
        g = fb.tile_named(obj_name)
        obj = fb.CATALOG[obj_name]
        ts = by_name[sheet]
        # the gid lands in that sheet's block of THIS map, on the right tile
        assert ts["firstgid"] <= g < ts["firstgid"] + ts["tilecount"]
        assert g - ts["firstgid"] == obj["row"] * ts["columns"] + obj["col"]
        layer["data"][2 * W + (2 + i)] = g
        painted[sheet] = g

    scratch = tmp_path / "campus_scratch.tmj"
    scratch.write_text(json.dumps(tmj))
    world = v.World(str(scratch), MATRIX)
    checker = v.Checker(world)
    checker.check_gids_resolve()
    assert not checker.errors(), checker.findings
    # the music-sheet sample is catalog wall art; #738's map-resolved
    # classifier must recognize the gid we painted
    assert painted["interior_music"] in v.catalog_wall_gids(world)

    with open(TMJ, "rb") as fh:
        assert fh.read() == raw, "committed campus tmj was rewritten by the test"


def test_repacked_tilesets_still_resolve():
    # Simulate a map whose tilesets moved: repack every firstgid in reverse
    # name order. Only helper resolution matters here (layer data would need a
    # matching repack), so no validate run -- just the acceptance that a
    # reordered map picks up the new firstgids with zero edits.
    tmj = _committed_tmj()
    tilesets = sorted(tmj["tilesets"], key=lambda t: t["name"], reverse=True)
    g = 1
    for ts in tilesets:
        ts["firstgid"] = g
        g += ts["tilecount"]
    tmj["tilesets"] = tilesets
    by_name = {ts["name"]: ts for ts in tilesets}

    fb.bind_sheet_firstgids(tmj)
    for sheet, obj_name in EXPANSION_SAMPLES.items():
        obj = fb.CATALOG[obj_name]
        ts = by_name[sheet]
        assert (
            fb.tile_named(obj_name)
            == ts["firstgid"] + obj["row"] * ts["columns"] + obj["col"]
        )
    # the franuka-baked palette gids follow the map too
    fr = by_name["interior_franuka"]
    brick = fb.CATALOG["wall_brick"]
    assert fb.WALL == fr["firstgid"] + brick["row"] * fr["columns"] + brick["col"]


def test_ensure_sheets_appends_after_map_top_and_binds():
    mini = {
        "width": 4,
        "height": 4,
        "layers": [],
        "tilesets": [
            {
                "firstgid": 1,
                "name": "kenney_urban",
                "image": "tilemap_packed.png",
                "columns": 27,
                "tilecount": 486,
            }
        ],
    }
    bound = fb.ensure_sheets(mini)
    # every interior sheet appended in a contiguous, non-overlapping block
    spans = sorted(
        (ts["firstgid"], ts["firstgid"] + ts["tilecount"]) for ts in mini["tilesets"]
    )
    for (_, prev_end), (start, _) in zip(spans, spans[1:]):
        assert start >= prev_end, spans
    for sheet in EXPANSION_SAMPLES:
        assert fb.gid(sheet, 0, 0) == bound[sheet]
    # idempotent: a second run appends nothing
    n = len(mini["tilesets"])
    fb.ensure_sheets(mini)
    assert len(mini["tilesets"]) == n

    with pytest.raises(KeyError, match="unknown interior sheet"):
        fb.ensure_sheets(mini, ["interior_nonesuch"])
