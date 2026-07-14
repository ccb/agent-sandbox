"""gen_furniture_matrix unit tests (#537): synthetic tmj fixtures, no files."""

from gen_furniture_matrix import gid_names, pieces, piece_spot, structural_cells

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


def _piece(cells, anchor_gid=5):
    return {"cells": cells, "anchor_gid": anchor_gid, "gids": [anchor_gid]}


def test_piece_spot_walk_on_lands_on_the_piece():
    # A 1x1 chair (name "chair_wood") that is walkable -> the spot is the
    # chair tile itself.
    names = {5: "chair_wood"}
    furn = ["5"] + ["0"] * 8  # 3x3, chair at (0,0)
    coll = ["0"] * 9
    arena = ["1"] * 9
    got = piece_spot(
        _piece([(0, 0)]), furn, coll, arena, {"1": "room"}, set(), names, 3, 3
    )
    assert got == (0, 0)


def test_piece_spot_front_lands_on_nearest_floor():
    # A solid 1x1 blackboard (not a walk-on name) with walkable floor to its
    # right -> the spot is that front floor tile, not the piece.
    names = {5: "blackboard"}
    furn = ["5", "0", "0"]
    coll = ["1", "0", "0"]  # blackboard solid; floor to the right
    arena = ["1", "1", "1"]
    got = piece_spot(
        _piece([(0, 0)]), furn, coll, arena, {"1": "room"}, set(), names, 3, 1
    )
    assert got == (1, 0)  # the adjacent floor cell


def test_piece_spot_front_requires_same_arena_non_structural():
    # The only adjacent floor is cross-arena (or structural) -> no spot.
    names = {5: "blackboard"}
    furn = ["5", "0"]
    coll = ["1", "0"]
    arena = ["1", "2"]  # the floor cell is a different arena
    assert (
        piece_spot(
            _piece([(0, 0)]),
            furn,
            coll,
            arena,
            {"1": "a", "2": "b"},
            set(),
            names,
            2,
            1,
        )
        is None
    )


def test_piece_spot_walk_on_with_no_walkable_tile_falls_to_front():
    # A "sofa" whose tile is somehow solid -> falls through to the front rule.
    names = {5: "sofa"}
    furn = ["5", "0"]
    coll = ["1", "0"]
    arena = ["1", "1"]
    assert piece_spot(
        _piece([(0, 0)]), furn, coll, arena, {"1": "room"}, set(), names, 2, 1
    ) == (1, 0)


def test_sheet_firstgids_matches_interior_and_suffixed_names():
    from gen_furniture_matrix import _sheet_firstgids

    catalog = {"sheets": {"franuka": {}, "kenney": {}, "school": {}}}
    tilesets = [
        {"name": "interior_franuka", "firstgid": 519},
        {"name": "kenney_urban", "firstgid": 1},
        {"name": "interior_school", "firstgid": 1543},
    ]
    assert _sheet_firstgids(catalog, tilesets) == {
        "franuka": 519,
        "kenney": 1,
        "school": 1543,
    }


def test_sheet_firstgids_raises_on_unmatched_sheet():
    import pytest
    from gen_furniture_matrix import _sheet_firstgids

    with pytest.raises(ValueError, match="ghost"):
        _sheet_firstgids(
            {"sheets": {"ghost": {}}}, [{"name": "interior_franuka", "firstgid": 519}]
        )


def test_sheet_firstgids_raises_on_ambiguous_prefix():
    import pytest
    from gen_furniture_matrix import _sheet_firstgids

    with pytest.raises(ValueError, match="several"):
        _sheet_firstgids(
            {"sheets": {"music": {}}},
            [
                {"name": "music_hall", "firstgid": 1},
                {"name": "music_room", "firstgid": 9},
            ],
        )


def test_real_map_artifacts_are_consistent():
    # The committed artifacts stay in lock-step with the tmj + matrices:
    # every furniture cell sits on a *_furniture layer cell, ids are dense,
    # and every id has exactly one blocks row.
    import json
    import os

    from block_furniture import _solid_layers, read_flat

    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    matrix = os.path.join(
        repo, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
    )
    tmj = json.load(
        open(
            os.path.join(
                repo,
                "godot-generative-agents",
                "godot",
                "maps",
                "upenn_core_urban.tmj",
            )
        )
    )
    furn = read_flat(os.path.join(matrix, "maze", "furniture_maze.csv"))
    assert len(furn) == tmj["width"] * tmj["height"]
    on_layers = [False] * len(furn)
    for layer in _solid_layers(tmj):
        for i, g in enumerate(layer["data"]):
            if g:
                on_layers[i] = True
    ids = set()
    for i, cell in enumerate(furn):
        if cell != "0":
            assert on_layers[i], f"cell {i} claims furniture off any layer"
            ids.add(int(cell))
    assert ids, "real map produced no furniture pieces"
    blocks = (
        open(os.path.join(matrix, "special_blocks", "furniture_blocks.csv"))
        .read()
        .strip()
        .splitlines()
    )
    block_ids = {int(r.split(",")[0]) for r in blocks}
    assert block_ids == ids == set(range(1, len(ids) + 1))

    # The identity join actually fires on the real map: cataloged names
    # appear (not only tile-<gid> fallbacks), and the cataloged window tile
    # (gid 737, window_dark_pane) is excluded from the matrix entirely.
    names = [r.split(", ")[-1] for r in blocks]
    assert any(not n.startswith("tile-") for n in names), "join emitted no names"
    assert "tile-737" not in names, "window tiles must not become furniture"
