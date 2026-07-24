# godot-generative-agents/tools/geo/test_validate_tmj.py
import os
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


def test_inventories_have_cohen_and_alumni_rooms():
    w = real_world()
    tmj = v.tmj_arenas_by_building(w)
    mtx = v.matrix_rooms_by_building(w)
    # both buildings are drawn in the tmj AND now present in the matrix
    assert len(tmj["Claudia Cohen Hall"]) == 5
    assert len(mtx["Claudia Cohen Hall"]) == 5
    assert len(tmj["Sweeten Alumni Building"]) == 22
    assert len(mtx["Sweeten Alumni Building"]) == 22


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
    game_object = ["0"] * N
    matrix_files = {
        "maze/collision_maze.csv": collision,
        "maze/arena_maze.csv": arena,
        "maze/sector_maze.csv": sector,
        "maze/game_object_maze.csv": game_object,
        "special_blocks/arena_blocks.csv": [["1", "UPenn", "Test Hall", "grounds"]],
        "special_blocks/sector_blocks.csv": [["1", "UPenn", "Test Hall"]],
        "special_blocks/world_blocks.csv": [["1", "UPenn"]],
        "special_blocks/game_object_blocks.csv": [],
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

    def finding(code, building):
        return next(
            (f for f in c.findings if f.code == code and f.building == building), None
        )

    # Cohen & Alumni: drawn AND present -> names match, no error
    assert finding("arena_names_match", "Claudia Cohen Hall")
    assert finding("arena_names_match", "Sweeten Alumni Building")
    assert not finding("arena_drawn_not_in_matrix", "Claudia Cohen Hall")
    assert not finding("arena_drawn_not_in_matrix", "Sweeten Alumni Building")
    # Van Pelt: matrix-only, json-sourced -> info (unchanged)
    vp = finding("arena_matrix_no_tmj_layer", "Van Pelt Library")
    assert vp and vp.severity == "info"


def test_arena_layer_resolved_flags_orphan_objects(tmp_path):
    def edit(tmj, mf):
        # an arena object floating over sector 0 (no building underneath)
        tmj["layers"][1]["objects"].append(
            {"name": "Nowhere Room", "x": 0, "y": 0, "width": 16, "height": 16}
        )

    w = make_world(tmp_path, edit)
    codes = {f.code for f in v.Checker(w).run().findings}
    assert "arena_layer_unresolved" in codes


def test_collision_check_is_warn_only_for_unsealed(tmp_path):
    # "Test Hall" is not a sealed (room-subdivided) building, so even a total
    # collision blow-out stays on the loose warn-only tolerance (#643 tightens
    # only the sealed buildings -- see test_sealed_* below).
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


def test_collision_reads_walls_layers_on_real_data():
    # #391: the check used to no-op on the real map (add_entrances zeroes the
    # `buildings` layer), so it never actually verified walls. It now unions the
    # per-building `*_walls` layers and checks those against collision_maze — a
    # real finding sourced from the walls, not the old info no-op.
    c = v.Checker(real_world()).run()
    coll = [f for f in c.findings if f.code == "collision_walls_ok"]
    assert coll, "no collision_walls_ok finding on the real map"
    assert any("*_walls layers" in f.message for f in coll)
    # the committed map is clean: sealed buildings have 0 walkable wall cells
    # (no collision_wall_gap_sealed error) and Cohen's 3 doorway-art cells sit
    # under the loose tolerance (no collision_wall_gap warn).
    assert all(
        f.severity != "error" for f in c.findings if f.code.startswith("collision_")
    )


def _wall_leak_edit(walkable):
    """Paint gid 7 as wall art (on a *_walls layer, at solid footprint cell
    (1,1)) and reuse the same gid on a non-walls `test_floor` layer. If
    `walkable`, put the floor copy on the walkable cell (0,0); else on the
    solid footprint cell (2,2)."""

    def edit(tmj, mf):
        W, H, N = 5, 4, 20
        walls = [0] * N
        walls[1 * W + 1] = 7  # (1,1): a footprint cell, collision "1"
        floor = [0] * N
        floor[0 if walkable else (2 * W + 2)] = 7  # (0,0) walkable | (2,2) solid
        tmj["layers"] += [
            {
                "type": "tilelayer",
                "name": "test_walls",
                "width": W,
                "height": H,
                "data": walls,
            },
            {
                "type": "tilelayer",
                "name": "test_floor",
                "width": W,
                "height": H,
                "data": floor,
            },
        ]

    return edit


def test_wall_gid_on_non_walls_layer_walkable_errors(tmp_path):
    # #561/#538: a wall-art gid (one painted on a *_walls layer) reused on a
    # NON-walls layer over a walkable cell means A* routes agents across a
    # drawn wall -- the Williams-on-williams_floor bug. Flag it as an error.
    w = make_world(tmp_path, _wall_leak_edit(walkable=True))
    findings = v.Checker(w).run().findings
    leak = [f for f in findings if f.code == "wall_on_walkable"]
    assert leak and leak[0].severity == "error", findings
    assert "test_floor" in leak[0].message and "(0,0)" in leak[0].message


def test_wall_gid_on_non_walls_layer_solid_is_ok(tmp_path):
    # Same wall-art gid on a non-walls layer but over a SOLID cell is fine
    # (that's exactly the entrance_floor perimeter ring): no error.
    w = make_world(tmp_path, _wall_leak_edit(walkable=False))
    findings = v.Checker(w).run().findings
    assert not [f for f in findings if f.code == "wall_on_walkable"], findings
    assert [f for f in findings if f.code == "wall_tiles_solid_ok"]


def test_wall_tiles_solid_on_real_data():
    # The real map: every wall-art tile outside a *_walls layer (the ~1800
    # entrance_floor perimeter cells) is solid -- no walkable wall, and the
    # regression guard reports ok.
    c = v.Checker(real_world()).run()
    assert not [f for f in c.errors() if f.code == "wall_on_walkable"]
    assert [f for f in c.findings if f.code == "wall_tiles_solid_ok"]


def _catalog_wall_edit(walkable):
    """Give the synthetic map a franuka tileset and paint wall_brick (catalog
    coords (24,0) -> firstgid 100 + 24 = gid 124) on a lone floor layer with NO
    `*_walls` layer anywhere. Layer-bound wall identity (#643) recognized a gid
    as wall art only if some `*_walls` layer used it, so this building slipped
    the check entirely; catalog-derived identity must still catch it."""

    def edit(tmj, mf):
        W, H, N = 5, 4, 20
        tmj["tilesets"].append(
            {
                "firstgid": 100,
                "name": "interior_franuka",
                "tilecount": 1024,
                "columns": 32,
            }
        )
        floor = [0] * N
        floor[0 if walkable else (1 * W + 1)] = 124  # (0,0) walkable | (1,1) solid
        tmj["layers"].append(
            {
                "type": "tilelayer",
                "name": "lonely_floor",
                "width": W,
                "height": H,
                "data": floor,
            }
        )

    return edit


def test_catalog_wall_gid_on_walkable_errors_without_walls_layer(tmp_path):
    w = make_world(tmp_path, _catalog_wall_edit(walkable=True))
    findings = v.Checker(w).run().findings
    leak = [f for f in findings if f.code == "wall_on_walkable"]
    assert leak and leak[0].severity == "error", findings
    assert "lonely_floor" in leak[0].message and "(0,0)" in leak[0].message
    # the check must not have skipped itself for lack of *_walls layers
    assert not [f for f in findings if f.code == "wall_tiles_no_walls"]


def test_catalog_wall_gid_on_solid_cell_is_ok(tmp_path):
    w = make_world(tmp_path, _catalog_wall_edit(walkable=False))
    findings = v.Checker(w).run().findings
    assert not [f for f in findings if f.code == "wall_on_walkable"], findings
    assert [f for f in findings if f.code == "wall_tiles_solid_ok"]


def test_catalog_wall_gids_resolve_against_this_tmj():
    # Resolution must use the map's own tilesets, not hardcoded firstgids:
    # wall_set_silver lives on interior_music, firstgid 5211 in the tmj (the
    # pin furnish_building carried before #746 said 6072).
    w = real_world()
    gids = v.catalog_wall_gids(w)
    assert 543 in gids  # wall_brick, franuka (24,0) @ firstgid 519
    assert 5211 in gids  # wall_set_silver top-left, music (0,0) @ firstgid 5211
    assert 6072 not in gids  # the retired-pin value would be wrong here


def _seal_rename_edit(walkable_wall_cells):
    """Rename the synthetic building to Williams Hall (a sealed building) and
    make the given footprint cells walkable though they are wall-drawn."""

    def edit(tmj, mf):
        W = 5
        mf["special_blocks/arena_blocks.csv"][0][2] = "Williams Hall"
        mf["special_blocks/sector_blocks.csv"][0][2] = "Williams Hall"
        for x, y in walkable_wall_cells:
            mf["maze/collision_maze.csv"][y * W + x] = "0"

    return edit


def test_sealed_building_wall_gap_is_error(tmp_path):
    # 1 of 4 wall-drawn cells walkable = 25%, under the loose 60% tolerance --
    # exactly the drift class that shipped past the gate before #643. On a
    # sealed building it must now error.
    w = make_world(tmp_path, _seal_rename_edit({(1, 1)}))
    c = v.Checker(w)
    c.check_collision_vs_walls()
    gap = [f for f in c.findings if f.code == "collision_wall_gap_sealed"]
    assert gap and gap[0].severity == "error", c.findings
    assert gap[0].building == "Williams Hall"
    # the loose warn did not fire (25% < 60%): without the sealed error this
    # regression would have produced no failing finding at all
    assert not [f for f in c.findings if f.code == "collision_wall_gap"]


def test_sealed_building_intact_is_ok(tmp_path):
    w = make_world(tmp_path, _seal_rename_edit(set()))
    c = v.Checker(w)
    c.check_collision_vs_walls()
    assert not [f for f in c.findings if f.code == "collision_wall_gap_sealed"]
    assert [f for f in c.findings if f.code == "collision_walls_ok"]


def test_sealed_building_wall_gap_error_on_real_data():
    # Punch one hole in Williams' collision under a williams_walls tile: the
    # sealed per-building tolerance must error where the old 60% warn stayed
    # silent.
    w = real_world()
    i = next(i for i, g in enumerate(w.tile_layers["williams_walls"]["data"]) if g)
    assert w.collision[i] == "1"
    w.collision[i] = "0"
    c = v.Checker(w)
    c.check_collision_vs_walls()
    gap = [f for f in c.findings if f.code == "collision_wall_gap_sealed"]
    assert gap and gap[0].severity == "error" and gap[0].building == "Williams Hall"


def test_van_pelt_rooms_verified_on_real_data():
    c = v.Checker(real_world()).run()
    match = [f for f in c.findings if f.code == "van_pelt_rooms_match"]
    assert match and match[0].severity == "ok"
    assert not [f for f in c.findings if f.code == "van_pelt_rooms_drift"]


def test_van_pelt_room_drop_is_error():
    # Drop one Van Pelt room row from arena_blocks: the old gate downgraded all
    # Van Pelt drawn-vs-matrix findings to info (#643); the JSON cross-check
    # must error.
    w = real_world()
    row = next(r for r in w.arena_blocks if r[2] == v.VAN_PELT and r[3] == "Entrance")
    w.arena_blocks.remove(row)
    c = v.Checker(w)
    c.check_van_pelt_interior()
    drift = [f for f in c.findings if f.code == "van_pelt_rooms_drift"]
    assert drift and drift[0].severity == "error"
    assert "missing" in drift[0].message and "Entrance" in drift[0].message


def test_van_pelt_room_rename_is_error():
    w = real_world()
    row = next(r for r in w.arena_blocks if r[2] == v.VAN_PELT and r[3] == "Entrance")
    row[3] = "Grand Foyer"
    c = v.Checker(w)
    c.check_van_pelt_interior()
    drift = [f for f in c.findings if f.code == "van_pelt_rooms_drift"]
    assert drift and drift[0].severity == "error"
    assert "renamed" in drift[0].message


def test_van_pelt_total_room_loss_is_error():
    # Losing ALL Van Pelt rooms leaves the building absent from both sides of
    # check_drawn_vs_present (no finding at all) -- the JSON cross-check is the
    # only gate that sees it.
    w = real_world()
    w.arena_blocks = [
        r
        for r in w.arena_blocks
        if not (r[2] == v.VAN_PELT and r[3] not in ("grounds", "lobby"))
    ]
    c = v.Checker(w)
    c.check_drawn_vs_present()
    assert not [f for f in c.findings if f.building == v.VAN_PELT]
    c.check_van_pelt_interior()
    drift = [f for f in c.findings if f.code == "van_pelt_rooms_drift"]
    assert drift and drift[0].severity == "error"
    assert "25 missing" in drift[0].message


def test_format_report_groups_and_counts():
    fs = [
        v.Finding("error", "MATRIX_TMJ", "Cohen", "c1", "drawn not present"),
        v.Finding("ok", "INTEGRITY", "", "i1", "gids fine"),
        v.Finding("info", "MATRIX_TMJ", "Van Pelt", "c2", "json sourced"),
    ]
    out = v.format_report(fs)
    assert "MATRIX_TMJ" in out and "INTEGRITY" in out
    assert "1 ok" in out and "1 info" in out and "1 error" in out


def test_gate_green_against_baseline():
    """With the committed baseline, main() must exit 0 — i.e. no NEW error drift.
    Fixing Cohen/Alumni later means deleting their baseline entries."""
    assert v.main([]) == 0


def test_main_exit_code_1_when_error_unbaselined(tmp_path):
    """A world with an error and no baseline -> exit 1."""

    # Inject a gid_out_of_range error into a synthetic world.
    def edit(tmj, mf):
        tmj["layers"][0]["data"][6] = 9999  # gid with no covering tileset

    w = make_world(tmp_path, edit)
    nonexistent = str(tmp_path / "no_baseline.json")
    assert (
        v.main(
            [
                "--tmj",
                str(tmp_path / "map.tmj"),
                "--matrix",
                str(tmp_path / "matrix"),
                "--baseline",
                nonexistent,
            ]
        )
        == 1
    )


def test_baseline_only_lists_real_current_errors():
    """Every baseline entry must correspond to an error the checker still emits,
    so the baseline can't silently rot."""
    import json as _j

    here = os.path.dirname(os.path.abspath(v.__file__))
    baseline = {
        tuple(e)
        for e in _j.load(open(os.path.join(here, "validate_tmj_baseline.json")))
    }
    live = {
        (f.category, f.building, f.code) for f in v.Checker(real_world()).run().errors()
    }
    stale = baseline - live
    assert not stale, f"baseline lists errors no longer present: {stale}"


def test_furniture_is_solid_on_real_data():
    c = v.Checker(real_world()).run()
    codes = {(f.code, f.severity) for f in c.findings}
    assert ("furniture-solid", "ok") in codes
    assert not [f for f in c.errors() if f.code == "furniture-not-solid"]


def test_main_exit_code_and_json(tmp_path, capsys):
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


def test_no_ghost_doors_on_real_map():
    # After Task 2 sealed Sweeten, every FORCED_CLOSED door is drawn WALL.
    w = real_world()
    c = v.Checker(w)
    c.check_entrance_floor_sealed()
    assert [f for f in c.findings if f.code == "ghost_door"] == []


def test_ghost_door_detected_when_forced_closed_drawn_open():
    # Re-open a FORCED_CLOSED door in the drawn layer -> a ghost door error.
    w = real_world()
    W = w.W
    fx, fy = next(iter(next(iter(v.FORCED_CLOSED.values()))))
    w.tile_layers["entrance_floor"]["data"][fy * W + fx] = v.FLOOR
    c = v.Checker(w)
    c.check_entrance_floor_sealed()
    assert any(f.code == "ghost_door" and f.severity == "error" for f in c.findings)
