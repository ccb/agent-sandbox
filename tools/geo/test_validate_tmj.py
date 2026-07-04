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
