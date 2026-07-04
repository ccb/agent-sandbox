# tools/geo/test_validate_tmj.py
import os
import validate_tmj as v

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMJ = os.path.join(REPO, "godot-generative-agents", "maps", "upenn_core_urban.tmj")
MATRIX = os.path.join(REPO, "godot-generative-agents", "sim", "the_upenn", "matrix")


def real_world():
    return v.World(TMJ, MATRIX)


def test_world_loads_real_files():
    w = real_world()
    assert (w.W, w.H) == (245, 279)
    assert len(w.collision) == w.W * w.H == 68355
    assert len(w.arena) == len(w.sector) == 68355
    # block tables are non-empty lists of rows
    assert any(r[0] == "30" for r in w.sector_blocks)  # Van Pelt sector
    assert w.idx(3, 1) == 1 * w.W + 3


def test_finding_is_hashable_frozen():
    f = v.Finding("error", "INTEGRITY", "Test Hall", "some_code", "msg")
    assert f.severity == "error" and f.code == "some_code"
    {f}  # frozen dataclass -> hashable, must not raise


def test_is_decoy_and_base_covered():
    assert v.is_decoy("Rug") and v.is_decoy("Rug Rug") and v.is_decoy("Brick Wall")
    assert v.is_decoy("Room 1: Wall")
    assert not v.is_decoy("Cafe") and not v.is_decoy("Room 1: BD 4")
    assert not v.is_decoy("Correspond")
    assert v.base_covered("Stage 1", "Stage")  # split arena -> one matrix room
    assert v.base_covered("East Pavilion 1", "East Pavilion 1")  # exact
    assert not v.base_covered("Stage", "Stagecoach")


def test_object_cells_maps_pixels_to_tiles():
    obj = {"x": 32, "y": 16, "width": 32, "height": 16}  # 16px tiles
    assert v.object_cells(obj, 245, 279) == {(2, 1), (3, 1)}


def test_inventories_capture_the_known_drift():
    w = real_world()
    tmj = v.tmj_arenas_by_building(w)
    mtx = v.matrix_rooms_by_building(w)
    # Cohen & Alumni: arenas drawn in the tmj...
    assert len(tmj["Claudia Cohen Hall"]) >= 5
    assert len(tmj["Sweeten Alumni Building"]) >= 10
    # ...but no room arenas in the matrix.
    assert mtx.get("Claudia Cohen Hall", []) == []
    assert mtx.get("Sweeten Alumni Building", []) == []
    # Van Pelt: rooms in the matrix, no tmj arena layer.
    assert len(mtx["Van Pelt Library"]) == 25
    assert "Van Pelt Library" not in tmj
    # Decoys excluded: Fisher's "Rug*" objects are not counted as arenas.
    fisher_names = {o["name"] for o in tmj["Fisher Fine Arts Library"]}
    assert not any("Rug" in n for n in fisher_names)


import json as _json


def make_world(tmp_path, edit=None):
    """Minimal 5x4 world with one building 'Test Hall' (sector 1).
    `edit(tmj, matrix_files)` may mutate the structures before they're written."""
    W, H = 5, 4
    N = W * H
    # footprint = the 2x2 block at (1,1),(2,1),(1,2),(2,2); interior (2,2) opened
    foot = {(1, 1), (2, 1), (1, 2), (2, 2)}
    buildings = [0] * N
    for x, y in foot:
        buildings[y * W + x] = 1  # any valid gid
    tmj = {
        "width": W,
        "height": H,
        "tilewidth": 16,
        "tileheight": 16,
        "tilesets": [{"firstgid": 1, "name": "t", "tilecount": 10, "columns": 5}],
        "layers": [
            {
                "type": "tilelayer",
                "name": "buildings",
                "width": W,
                "height": H,
                "data": buildings,
            },
            {
                "type": "objectgroup",
                "name": "test_arenas",
                "objects": [],
            },
        ],
    }
    sector = ["0"] * N
    arena = ["0"] * N
    collision = ["0"] * N
    for x, y in foot:
        sector[y * W + x] = "1"
        arena[y * W + x] = "1"  # grounds
        collision[y * W + x] = "1"
    matrix_files = {
        "maze/collision_maze.csv": collision,
        "maze/arena_maze.csv": arena,
        "maze/sector_maze.csv": sector,
        "special_blocks/arena_blocks.csv": [["1", "UPenn", "Test Hall", "grounds"]],
        "special_blocks/sector_blocks.csv": [["1", "UPenn", "Test Hall"]],
        "special_blocks/world_blocks.csv": [["1", "UPenn"]],
        "maze_meta_info.json": {
            "world_name": "UPenn",
            "maze_width": W,
            "maze_height": H,
            "sq_tile_size": 16,
            "special_constraint": "",
        },
    }
    if edit:
        edit(tmj, matrix_files)
    tdir = tmp_path / "matrix"
    (tdir / "maze").mkdir(parents=True)
    (tdir / "special_blocks").mkdir(parents=True)
    tmj_path = tmp_path / "map.tmj"
    tmj_path.write_text(_json.dumps(tmj))
    for rel, content in matrix_files.items():
        p = tdir / rel
        if rel.endswith(".json"):
            p.write_text(_json.dumps(content))
        elif "special_blocks" in rel:
            p.write_text("".join(", ".join(r) + "\n" for r in content))
        else:
            p.write_text(", ".join(content))
    return v.World(str(tmj_path), str(tdir))


def test_integrity_clean_on_synthetic(tmp_path):
    w = make_world(tmp_path)
    c = v.Checker(w).run()
    assert [
        f for f in c.findings if f.category == "INTEGRITY" and f.severity == "error"
    ] == []


def test_gid_out_of_range_flagged(tmp_path):
    def edit(tmj, mf):
        tmj["layers"][0]["data"][6] = 9999  # no tileset covers gid 9999

    w = make_world(tmp_path, edit)
    codes = {f.code for f in v.Checker(w).run().findings}
    assert "gid_out_of_range" in codes


def test_bad_dimensions_flagged(tmp_path):
    def edit(tmj, mf):
        mf["maze_meta_info.json"]["maze_width"] = 999

    w = make_world(tmp_path, edit)
    codes = {f.code for f in v.Checker(w).run().findings}
    assert "meta_dim_mismatch" in codes


def test_referential_integrity_flagged(tmp_path):
    def edit(tmj, mf):
        mf["special_blocks/arena_blocks.csv"][0][2] = "Ghost Hall"  # not in sectors

    w = make_world(tmp_path, edit)
    codes = {f.code for f in v.Checker(w).run().findings}
    assert "arena_sector_unknown" in codes


def test_real_data_has_no_integrity_errors():
    c = v.Checker(real_world()).run()
    errs = [
        f for f in c.findings if f.category == "INTEGRITY" and f.severity == "error"
    ]
    assert errs == [], "\n".join(f"{f.building}: {f.message}" for f in errs)


def test_orphan_block_row_flagged(tmp_path):
    def edit(tmj, mf):
        # declare an arena that is never painted into arena_maze
        mf["special_blocks/arena_blocks.csv"].append(
            ["11", "UPenn", "Test Hall", "lobby"]
        )

    w = make_world(tmp_path, edit)
    codes = {f.code for f in v.Checker(w).run().findings}
    assert "arena_block_unpainted" in codes


def test_orphan_paint_flagged(tmp_path):
    def edit(tmj, mf):
        mf["maze/arena_maze.csv"][0] = "777"  # painted id with no block row

    w = make_world(tmp_path, edit)
    codes = {f.code for f in v.Checker(w).run().findings}
    assert "arena_paint_unknown" in codes


def test_id_scheme_violation_flagged(tmp_path):
    def edit(tmj, mf):
        # a "room" arena (>=10000) whose id does not match 10000 + sector*100 + idx
        mf["special_blocks/arena_blocks.csv"].append(
            ["19999", "UPenn", "Test Hall", "Parlor"]
        )
        mf["maze/arena_maze.csv"][7] = "19999"  # paint it inside the footprint

    w = make_world(tmp_path, edit)
    codes = {f.code for f in v.Checker(w).run().findings}
    assert "arena_id_scheme" in codes


def test_region_containment_flagged(tmp_path):
    def edit(tmj, mf):
        # paint Test Hall's grounds id (1) onto a cell outside sector 1
        mf["maze/arena_maze.csv"][0] = "1"  # cell (0,0), sector "0"

    w = make_world(tmp_path, edit)
    codes = {f.code for f in v.Checker(w).run().findings}
    assert "arena_region_outside_sector" in codes


def test_real_data_structural_consistency():
    c = v.Checker(real_world()).run()
    codes = {f.code for f in c.findings}
    # these structural checks should be clean on committed data
    for bad in (
        "arena_block_unpainted",
        "arena_paint_unknown",
        "arena_id_scheme",
        "arena_region_outside_sector",
    ):
        offenders = [f for f in c.findings if f.code == bad and f.severity == "error"]
        assert offenders == [], f"{bad}: " + "; ".join(o.message for o in offenders)


def test_drawn_vs_present_real_data():
    c = v.Checker(real_world()).run()

    def has(code, building):
        return any(f.code == code and f.building == building for f in c.findings)

    # Cohen & Alumni drawn but not bridged -> error
    assert has("arena_drawn_not_in_matrix", "Claudia Cohen Hall")
    assert has("arena_drawn_not_in_matrix", "Sweeten Alumni Building")
    # Van Pelt in matrix, no tmj layer, json-sourced -> info (expected)
    assert has("arena_matrix_no_tmj_layer", "Van Pelt Library")
    vp = [
        f
        for f in c.findings
        if f.code == "arena_matrix_no_tmj_layer" and f.building == "Van Pelt Library"
    ][0]
    assert vp.severity == "info"


def test_unwired_error_mentions_room_subdivide():
    c = v.Checker(real_world()).run()
    cohen = [
        f
        for f in c.findings
        if f.code == "arena_drawn_not_in_matrix" and f.building == "Claudia Cohen Hall"
    ][0]
    assert cohen.severity == "error"
    assert "ROOM_SUBDIVIDE" in cohen.message


def test_arena_layer_resolved_flags_orphan_objects(tmp_path):
    def edit(tmj, mf):
        # an arena object floating over sector 0 (no building underneath)
        tmj["layers"][1]["objects"].append(
            {"name": "Nowhere Room", "x": 0, "y": 0, "width": 16, "height": 16}
        )

    w = make_world(tmp_path, edit)
    codes = {f.code for f in v.Checker(w).run().findings}
    assert "arena_layer_unresolved" in codes


def test_collision_check_is_warn_only(tmp_path):
    def edit(tmj, mf):
        # knock a big hole: mark the whole footprint walkable though it's wall-drawn
        for i in range(len(mf["maze/collision_maze.csv"])):
            mf["maze/collision_maze.csv"][i] = "0"

    w = make_world(tmp_path, edit)
    findings = v.Checker(w).run().findings
    coll = [
        f for f in findings if f.code in ("collision_wall_gap", "collision_walls_ok")
    ]
    assert coll, "collision check produced no finding"
    assert all(f.severity != "error" for f in coll)


def test_collision_never_errors_on_real_data():
    c = v.Checker(real_world()).run()
    assert all(
        f.severity != "error" for f in c.findings if f.code == "collision_wall_gap"
    )


def test_format_report_groups_and_counts():
    fs = [
        v.Finding("error", "MATRIX_TMJ", "Cohen", "c1", "drawn not present"),
        v.Finding("ok", "INTEGRITY", "", "i1", "gids fine"),
        v.Finding("info", "MATRIX_TMJ", "Van Pelt", "c2", "json sourced"),
    ]
    out = v.format_report(fs)
    assert "MATRIX_TMJ" in out and "INTEGRITY" in out
    assert "1 ok" in out and "1 info" in out and "1 error" in out


def test_main_exit_code_and_json(tmp_path, capsys):
    w_dir = tmp_path  # reuse make_world's writer via a real build
    world = make_world(tmp_path)  # clean synthetic world -> no errors
    code = v.main(
        [
            "--tmj",
            os.path.join(str(tmp_path), "map.tmj"),
            "--matrix",
            os.path.join(str(tmp_path), "matrix"),
            "--json",
        ]
    )
    out = capsys.readouterr().out
    parsed = _json.loads(out)
    assert isinstance(parsed, list)
    assert code == 0
