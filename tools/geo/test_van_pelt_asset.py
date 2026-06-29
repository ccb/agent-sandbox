import json, os

ASSET = os.path.join(os.path.dirname(__file__), "van_pelt_interior.json")

def _load():
    with open(ASSET) as fh:
        return json.load(fh)

def test_dimensions():
    a = _load()
    assert (a["width"], a["height"]) == (245, 279)

def test_layers_present_with_expected_counts():
    a = _load()
    counts = {n: len(cells) for n, cells in a["layers"].items()}
    assert counts == {
        "westwing_floors": 1685, "eastwing_floors": 2962,
        "westwing_walls": 257, "eastwing_walls": 251,
        "westwing_furniture": 457, "eastwing_furniture": 1080,
    }
    assert a["layer_order"] == [
        "westwing_floors", "eastwing_floors",
        "westwing_walls", "eastwing_walls",
        "westwing_furniture", "eastwing_furniture",
    ]

def test_25_unique_named_rooms():
    a = _load()
    names = [r["name"] for r in a["rooms"]]
    assert len(names) == 25 and len(set(names)) == 25
    for must in ("113", "114", "Kamin Gallery", "Moelis Family Grand Reading Room",
                 "Study Booths", "Entrance"):
        assert must in names

def test_wall_cells_is_union_of_wall_layers():
    a = _load()
    assert len(a["wall_cells"]) == 501
    # every wall cell index is < W*H
    assert all(0 <= i < 245 * 279 for i in a["wall_cells"])
