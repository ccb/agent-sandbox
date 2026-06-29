# tools/geo/test_furnish_van_pelt.py
import copy, json, os
import furnish_van_pelt as fv

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAP = os.path.join(REPO, "godot-generative-agents", "maps", "upenn_core_urban.tmj")
MATRIX = os.path.join(REPO, "godot-generative-agents", "sim", "the_upenn", "matrix")
ORDER = ["westwing_floors", "eastwing_floors", "westwing_walls",
         "eastwing_walls", "westwing_furniture", "eastwing_furniture"]

def _fresh_tmj():
    with open(MAP) as fh:
        return json.load(fh)

def test_inserts_six_layers_after_entrance_floor():
    tmj = _fresh_tmj()
    fv.apply(tmj, fv.load_asset(HERE), MATRIX)
    names = [L.get("name") for L in tmj["layers"]]
    for n in ORDER:
        assert n in names
    ef = names.index("entrance_floor")
    # the six interior layers are a contiguous block right after entrance_floor
    assert names[ef + 1: ef + 7] == ORDER

def test_no_transplanted_cell_outside_interior():
    tmj = _fresh_tmj()
    W, H = tmj["width"], tmj["height"]
    ef = next(L for L in tmj["layers"] if L.get("name") == "entrance_floor")
    entrance_cells = {(i % W, i // W) for i, v in enumerate(ef["data"]) if v}
    interior = fv.van_pelt_interior_cells(MATRIX, W, H, entrance_cells)
    fv.apply(tmj, fv.load_asset(HERE), MATRIX)
    for n in ORDER:
        L = next(x for x in tmj["layers"] if x.get("name") == n)
        for i, v in enumerate(L["data"]):
            if v:
                assert (i % W, i // W) in interior, f"{n} cell {(i%W,i//W)} outside interior"

def test_clips_the_throat_seam_cells():
    tmj = _fresh_tmj()
    clipped = fv.apply(tmj, fv.load_asset(HERE), MATRIX)
    assert 1 <= clipped <= 50  # ~20 (10 throat cells x 2 layers); never zero, never large

def test_furniture_never_clipped_cardinal_rule():
    # The clip only ever touches floor/wall cells at the throat seam. If ANY
    # furniture cell were outside the interior it would be clipped -> a cut sprite.
    tmj = _fresh_tmj()
    W, H = tmj["width"], tmj["height"]
    ef = next(L for L in tmj["layers"] if L.get("name") == "entrance_floor")
    entrance_cells = {(i % W, i // W) for i, v in enumerate(ef["data"]) if v}
    interior = fv.van_pelt_interior_cells(MATRIX, W, H, entrance_cells)
    asset = fv.load_asset(HERE)
    for fname in ("westwing_furniture", "eastwing_furniture"):
        for idx_s in asset["layers"][fname]:
            idx = int(idx_s)
            assert (idx % W, idx // W) in interior, f"{fname} {idx} would be clipped"

def test_no_phantom_walls_after_apply():
    # No wing-wall sprite may sit on a walkable (collision==0) cell.
    tmj = _fresh_tmj()
    W = tmj["width"]
    fv.apply(tmj, fv.load_asset(HERE), MATRIX)
    coll = open(os.path.join(MATRIX, "maze", "collision_maze.csv")).read().strip().split(", ")
    for name in ("westwing_walls", "eastwing_walls"):
        L = next(x for x in tmj["layers"] if x.get("name") == name)
        for i, v in enumerate(L["data"]):
            if v:
                assert coll[i] == "1", f"{name} sprite on walkable cell {(i % W, i // W)}"

def test_idempotent():
    a = _fresh_tmj(); fv.apply(a, fv.load_asset(HERE), MATRIX)
    b = copy.deepcopy(a); fv.apply(b, fv.load_asset(HERE), MATRIX)
    da = {L["name"]: L["data"] for L in a["layers"] if L["name"] in ORDER}
    db = {L["name"]: L["data"] for L in b["layers"] if L["name"] in ORDER}
    assert da == db
    # re-applying did not add duplicate layers
    assert [L["name"] for L in a["layers"]] == [L["name"] for L in b["layers"]]
