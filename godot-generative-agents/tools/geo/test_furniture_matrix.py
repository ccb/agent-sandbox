"""gen_furniture_matrix unit tests (#537): synthetic tmj fixtures, no files."""

from gen_furniture_matrix import gid_names, pieces, spots, structural_cells

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


def test_spots_are_walkable_floor_beside_furniture():
    # Collision: the 2x2 desk is solid; the stool (gid 9) is a walkable seat.
    furn = ["0", "1", "1", "0", "0", "1", "1", "0", "0", "0", "0", "2"]
    coll = ["0", "1", "1", "0", "0", "1", "1", "0", "0", "0", "0", "0"]
    arena = ["1"] * 12  # one arena; no structural cells
    got = spots(furn, coll, arena, set(), 4, 3)
    # Floor tiles 4-adjacent to same-arena furniture: (0,0)/(3,0) flank the
    # desk, (0,1)/(3,1) flank it, (1,2)/(2,2) sit below it. (3,1) is also
    # beside the stool. The stool tile (3,2) itself is NOT a spot -- the
    # furniture tile is never a destination, only the floor around it.
    assert got == [(0, 0), (3, 0), (0, 1), (3, 1), (1, 2), (2, 2)]


def test_spots_exclude_structural_cells():
    # A wall drawn on a floor layer beside furniture (Williams' case): the
    # cell is walkable in collision but must not become a spot.
    furn = ["0", "1", "0"]
    coll = ["0", "1", "0"]
    arena = ["1", "1", "1"]
    assert spots(furn, coll, arena, set(), 3, 1) == [(0, 0), (2, 0)]
    # Mark (0,0) structural -> only (2,0) survives.
    assert spots(furn, coll, arena, {0}, 3, 1) == [(2, 0)]


def test_spots_require_same_arena_furniture():
    # A floor cell whose only adjacent furniture is in ANOTHER arena is not a
    # spot (the doorway-threshold cross-arena case).
    furn = ["0", "1", "0"]
    coll = ["0", "1", "0"]
    arena = ["1", "2", "2"]  # (1,0) furniture is arena 2
    # (0,0) is arena 1, borders only the arena-2 desk -> not a spot;
    # (2,0) is arena 2, borders the arena-2 desk -> a spot.
    assert spots(furn, coll, arena, set(), 3, 1) == [(2, 0)]


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
