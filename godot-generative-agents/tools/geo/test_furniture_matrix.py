"""gen_furniture_matrix unit tests (#537): synthetic tmj fixtures, no files."""

from gen_furniture_matrix import gid_names, pieces, spots

# A 4x3 map, one furniture layer. Layout (gids):
#   0 5 6 0
#   0 7 8 0
#   0 0 0 9
# -> one 2x2 piece (gids 5,6,7,8, anchor 5) + one 1x1 piece (gid 9).
_TMJ = {
    "width": 4,
    "height": 3,
    "layers": [
        {
            "type": "tilelayer",
            "name": "demo_furniture",
            "data": [0, 5, 6, 0, 0, 7, 8, 0, 0, 0, 0, 9],
        },
        {"type": "tilelayer", "name": "demo_floor", "data": [1] * 12},
    ],
    "tilesets": [{"firstgid": 1, "name": "franuka"}],
}

_CATALOG = {
    "sheets": {"franuka": {"cols": 2, "rows": 4}},
    "objects": {
        "_comment": "ignored",
        "desk_big": {"sheet": "franuka", "col": 0, "row": 2, "w": 2, "h": 2},
        "stool": {"sheet": "franuka", "col": 0, "row": 4, "w": 1, "h": 1},
        "window_a": {
            "sheet": "franuka",
            "col": 1,
            "row": 4,
            "w": 1,
            "h": 1,
            "category": "window",
        },
    },
}


def test_excluded_gids_covers_wall_window_door_footprints():
    from gen_furniture_matrix import excluded_gids

    # window_a at (col 1, row 4) on a 2-col sheet with firstgid 1 -> gid 10.
    assert excluded_gids(_CATALOG, _TMJ["tilesets"]) == {10}


def test_pieces_skips_excluded_cells():
    # A window gid (10) beside the stool must not merge into (or become) a
    # piece: williams_furniture paints windows on the furniture layer so
    # block_furniture seals them; they are NOT furniture (#537 spec §1).
    tmj = dict(_TMJ)
    tmj["layers"] = [
        {
            "type": "tilelayer",
            "name": "demo_furniture",
            "data": [0, 5, 6, 0, 0, 7, 8, 0, 10, 10, 0, 9],
        }
    ]
    got = pieces(tmj, excluded={10})
    assert len(got) == 2  # the desk and the stool; no window piece
    assert all((0, 2) not in p["cells"] and (1, 2) not in p["cells"] for p in got)


def test_pieces_groups_by_contiguity_not_gid():
    got = pieces(_TMJ)
    assert len(got) == 2
    big, small = sorted(got, key=lambda p: len(p["cells"]), reverse=True)
    assert sorted(big["cells"]) == [(1, 0), (1, 1), (2, 0), (2, 1)]
    assert big["anchor_gid"] == 5  # top-left cell's base gid
    assert small["cells"] == [(3, 2)] and small["anchor_gid"] == 9


def test_gid_names_expands_footprints_and_resolves_anchor():
    # desk_big anchors at (col 0, row 2) on a 2-col sheet with firstgid 1:
    # gid = 1 + row*cols + col -> anchor 5, footprint covers gids 5,6,7,8.
    names = gid_names(_CATALOG, _TMJ["tilesets"])
    assert names[5] == "desk_big" and names[8] == "desk_big"
    assert names[9] == "stool"


def test_spots_are_walkable_cells_on_or_beside_furniture():
    # Collision: the 2x2 desk is solid; the stool (gid 9) is a walkable seat.
    furn = ["0", "1", "1", "0", "0", "1", "1", "0", "0", "0", "0", "2"]
    coll = ["0", "1", "1", "0", "0", "1", "1", "0", "0", "0", "0", "0"]
    got = spots(furn, coll, 4, 3)
    # Row-major: (0,0)/(3,0) flank the desk, (0,1)/(3,1) flank it, (1,2)/(2,2)
    # sit below it, and (3,2) IS the walkable stool.
    assert got == [(0, 0), (3, 0), (0, 1), (3, 1), (1, 2), (2, 2), (3, 2)]
