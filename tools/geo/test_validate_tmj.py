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
