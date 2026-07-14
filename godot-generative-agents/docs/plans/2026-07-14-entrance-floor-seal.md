# Seal `entrance_floor` on `FORCED_CLOSED` + Ghost-Door Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `add_entrances.py` repaint a `FORCED_CLOSED` door's `entrance_floor` tile to wall (so a regen no longer re-opens hand-sealed doors), repair the one committed ghost door (Sweeten Alumni), and add a `validate_tmj.py` guard so this drift class fails CI.

**Architecture:** Three coordinated changes — a pure repaint helper in `add_entrances.py` (Task 1), a surgical one-cell edit to the committed pretty tmj (Task 2), and a new consistency check in `validate_tmj.py` (Task 3). Task 2 precedes Task 3 so the guard is clean on the committed map the moment it lands.

**Tech Stack:** Python 3.12 (geo tooling under `godot-generative-agents/tools/geo/`). Tests are pytest, run via `uv run --no-sync pytest godot-generative-agents/tools/geo/ -q` (bare module imports; pytest puts the dir on `sys.path`).

## Global Constraints

- **Targets `godot-ga-main`** (geo tooling + map + geo tests). Branch `feat/entrance-floor-seal-556` (already created off `godot-ga-main`).
- **`FLOOR` = 621 (open door art), `WALL` = 543** (`add_entrances.py:103-104`, from `block_furniture`). Use the constants, never hardcode the gids in `add_entrances.py`.
- **Never commit a regenerated (minified) tmj.** The committed tmj is Tiled-pretty (data is one map-row per line, 245 values, `, `-separated). Task 2's edit is a surgical, format-preserving one-line change verified to leave the full JSON identical except the target cell.
- **The ghost-door guard checks ONE direction only:** a cell drawn `FLOOR` in `entrance_floor` while `collision=="1"` is an error. Do NOT add the reverse (walkable-but-not-floor-drawn) — legitimately walkable cells get floor art from other layers and would false-positive.
- The collision seal (`add_entrances.py:835-836`) stays where it is — it must run before the collision matrix is written (~line 867); the `floor` array doesn't exist until ~line 877, so the tile repaint is necessarily a separate call after `paint_interior`.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Run git from the repo root `/Users/yh/Documents/GitHub/agent-sandbox`.
- No changes to collision/matrix content, other buildings' doors, `FORCED_DOORS`, or the sim. The layer-id churn in `insert_entrance_layers` is explicitly out of scope.

---

### Task 1: `add_entrances.py` — repaint `FORCED_CLOSED` tiles to `WALL`

**Files:**
- Modify: `godot-generative-agents/tools/geo/add_entrances.py`
- Test: `godot-generative-agents/tools/geo/test_add_entrances.py` (new)

**Interfaces:**
- Produces: `seal_forced_closed_floor(floor: list, W: int) -> None` — repaints every `FORCED_CLOSED` cell in the `entrance_floor` `floor` array to `WALL`.

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/tools/geo/test_add_entrances.py`:

```python
"""add_entrances FORCED_CLOSED -> entrance_floor repaint tests (#556)."""

import add_entrances as ae

W, H = 245, 279  # the real map dims; the helper only needs a correctly-sized list


def test_seal_forced_closed_floor_repaints_open_door_to_wall():
    # Every FORCED_CLOSED cell starts drawn as open door art (FLOOR)...
    floor = [0] * (W * H)
    for cells in ae.FORCED_CLOSED.values():
        for fx, fy in cells:
            floor[fy * W + fx] = ae.FLOOR
    ae.seal_forced_closed_floor(floor, W)
    # ...and ends repainted to WALL, matching its collision seal.
    for cells in ae.FORCED_CLOSED.values():
        for fx, fy in cells:
            assert floor[fy * W + fx] == ae.WALL


def test_seal_forced_closed_floor_touches_only_forced_closed_cells():
    floor = [ae.FLOOR] * (W * H)
    ae.seal_forced_closed_floor(floor, W)
    closed = {fy * W + fx for cells in ae.FORCED_CLOSED.values() for (fx, fy) in cells}
    assert all(floor[i] == ae.WALL for i in closed)
    sample = next(i for i in range(W * H) if i not in closed)
    assert floor[sample] == ae.FLOOR  # a non-closed cell is untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest godot-generative-agents/tools/geo/test_add_entrances.py -q`
Expected: FAIL — `AttributeError: module 'add_entrances' has no attribute 'seal_forced_closed_floor'`.

- [ ] **Step 3: Add the helper**

In `godot-generative-agents/tools/geo/add_entrances.py`, add this function immediately after `paint_interior` (which ends around line 445):

```python
def seal_forced_closed_floor(floor, W):
    """Repaint FORCED_CLOSED door cells as WALL in the entrance_floor tile data,
    so the drawn tile matches the sealed collision and a regen never re-opens a
    hand-sealed door (issue #556). Complements the collision seal in main()."""
    for cells in FORCED_CLOSED.values():
        for fx, fy in cells:
            floor[fy * W + fx] = WALL
```

- [ ] **Step 4: Call it in `main()` after the floor is painted**

In `main()`, the floor is built and painted here (around lines 877-882):

```python
    floor = [0] * (W * H)
    for name, foot, perimeter, door in picture_jobs:
        ...
        paint_interior(floor, perimeter, foot, door, W)
    insert_entrance_layers(tmj, W, H, floor)
```

Insert the repaint call between the `paint_interior` loop and `insert_entrance_layers`:

```python
    floor = [0] * (W * H)
    for name, foot, perimeter, door in picture_jobs:
        ...
        paint_interior(floor, perimeter, foot, door, W)
    seal_forced_closed_floor(floor, W)  # #556: closed doors are wall art, not open floor
    insert_entrance_layers(tmj, W, H, floor)
```

(Keep the existing per-building collision seal at `add_entrances.py:835-836` exactly as-is — it must run before the collision matrix is written.)

- [ ] **Step 5: Run the test + full geo suite**

Run: `uv run --no-sync pytest godot-generative-agents/tools/geo/test_add_entrances.py -q`
Expected: PASS (2 tests).
Run: `uv run --no-sync pytest godot-generative-agents/tools/geo/ -q`
Expected: PASS (whole geo suite still green).

- [ ] **Step 6: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
git add godot-generative-agents/tools/geo/add_entrances.py \
        godot-generative-agents/tools/geo/test_add_entrances.py
git commit -m "fix(geo): FORCED_CLOSED repaints entrance_floor to WALL, not open door (#556)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Surgically seal Sweeten Alumni's committed ghost door

Repair the one ghost door already in the committed map: `entrance_floor` at `(46,99)` `621`→`543`. This is a data edit to the Tiled-pretty tmj, applied with a verified format-preserving script (a `json.dump` would reformat the whole file — forbidden).

**Files:**
- Modify: `godot-generative-agents/godot/maps/upenn_core_urban.tmj` (one cell)

- [ ] **Step 1: Confirm the ghost door is present**

Run:
```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
python3 -c "
import json
tmj=json.load(open('godot-generative-agents/godot/maps/upenn_core_urban.tmj')); W=tmj['width']
ef=next(L for L in tmj['layers'] if L['name']=='entrance_floor')['data']
print('entrance_floor(46,99) =', ef[99*W+46], '(expect 621, the ghost door)')
"
```
Expected: `entrance_floor(46,99) = 621`.

- [ ] **Step 2: Apply the surgical, format-preserving seal**

This script edits exactly the (46,99) value on its map-row line inside the `entrance_floor` data block, leaving every other byte unchanged. Run:

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
python3 - <<'PY'
import json
p = "godot-generative-agents/godot/maps/upenn_core_urban.tmj"
t = open(p).read()
tmj = json.loads(t)
W = tmj["width"]
ef = next(L for L in tmj["layers"] if L["name"] == "entrance_floor")["data"]
bx, by = 46, 99
idx = by * W + bx
assert ef[idx] == 621, f"expected 621 at (46,99), found {ef[idx]}"
lines = t.split("\n")
# entrance_floor's data block: "data":[ ... ] sits just above its "name" key.
name_i = next(i for i, l in enumerate(lines) if l.strip().startswith('"name":"entrance_floor"'))
data_i = next(i for i in range(name_i, -1, -1) if '"data":[' in lines[i])
# data is row-wrapped (W values per map row); row 0 shares the "data":[ line, row k is data_i+k.
row_line = data_i + by
line = lines[row_line]
indent = line[: len(line) - len(line.lstrip())]
vals = line.strip().rstrip(",").split(", ")
assert len(vals) == W and vals[bx] == "621", (len(vals), vals[bx])
vals[bx] = "543"
trail = "," if line.rstrip().endswith(",") else ""
lines[row_line] = indent + ", ".join(vals) + trail
open(p, "w").write("\n".join(lines))
# verify: only the target cell changed, full JSON otherwise identical
tmj2 = json.loads(open(p).read())
ef2 = next(L for L in tmj2["layers"] if L["name"] == "entrance_floor")["data"]
assert ef2[idx] == 543
tmj["layers"][[L["name"] for L in tmj["layers"]].index("entrance_floor")]["data"][idx] = 543
assert tmj == tmj2, "more than the target cell changed!"
print("sealed (46,99): 621 -> 543; only-target-changed OK")
PY
```
Expected: `sealed (46,99): 621 -> 543; only-target-changed OK`.

- [ ] **Step 3: Confirm the diff is exactly one line**

Run: `git diff --stat godot-generative-agents/godot/maps/upenn_core_urban.tmj`
Expected: `1 insertion(+), 1 deletion(-)` (a single row line changed). If the diff shows the whole file (minified), STOP — the edit reformatted; revert with `git checkout -- <tmj>` and report BLOCKED.

- [ ] **Step 4: Geo suite still green (no test depends on the ghost door)**

Run: `uv run --no-sync pytest godot-generative-agents/tools/geo/ -q`
Expected: PASS. Also run `uv run --no-sync python godot-generative-agents/tools/geo/validate_tmj.py` — expected exit 0 (the seal only improves consistency; the ghost-door guard doesn't exist yet).

- [ ] **Step 5: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
git add godot-generative-agents/godot/maps/upenn_core_urban.tmj
git commit -m "fix(geo): seal Sweeten Alumni ghost door in entrance_floor (46,99) 621->543 (#556)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `validate_tmj.py` — ghost-door consistency guard

**Files:**
- Modify: `godot-generative-agents/tools/geo/validate_tmj.py`
- Test: `godot-generative-agents/tools/geo/test_validate_tmj.py`

**Interfaces:**
- Consumes: `add_entrances.FLOOR` (621); `self.w.tile_layers["entrance_floor"]`, `self.w.collision`, `self.w.W`; `self.add(severity, category, building, code, message)` (all existing).
- Produces: `Checker.check_entrance_floor_sealed(self)` — emits an `error` Finding with code `ghost_door` per run when any `FLOOR`-drawn cell is collision-sealed.

- [ ] **Step 1: Write the failing tests**

Append to `godot-generative-agents/tools/geo/test_validate_tmj.py`:

```python
def test_no_ghost_doors_on_real_map():
    # After Task 2 sealed Sweeten, the committed map has zero ghost doors.
    w = real_world()
    c = v.Checker(w)
    c.check_entrance_floor_sealed()
    assert [f for f in c.findings if f.code == "ghost_door"] == []


def test_ghost_door_detected_when_open_tile_over_sealed_collision():
    # Draw open-floor art (FLOOR) on a currently-sealed cell -> a ghost door.
    w = real_world()
    ef = w.tile_layers["entrance_floor"]["data"]
    idx = next(i for i, g in enumerate(ef) if w.collision[i] == "1")
    ef[idx] = v.FLOOR
    c = v.Checker(w)
    c.check_entrance_floor_sealed()
    assert any(f.code == "ghost_door" and f.severity == "error" for f in c.findings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest godot-generative-agents/tools/geo/test_validate_tmj.py -k "ghost_door or no_ghost" -q`
Expected: FAIL — `AttributeError: 'Checker' object has no attribute 'check_entrance_floor_sealed'` (and `v.FLOOR` may be undefined until Step 3).

- [ ] **Step 3: Import `FLOOR` and add the check**

In `godot-generative-agents/tools/geo/validate_tmj.py`, add `FLOOR` to the existing `from add_entrances import (...)` block (line 22):

```python
from add_entrances import (
    FLOOR,
    # ...existing names, unchanged...
)
```

Add the check method to `class Checker` (place it right after `check_collision_vs_walls`, which ends around line 586):

```python
    def check_entrance_floor_sealed(self):
        # A "ghost door": an entrance_floor cell drawn as open floor art (FLOOR)
        # whose collision is sealed ("1"). The tile lies about walkability and a
        # regen re-opens it (#556). ONE direction only -- walkable cells legit-
        # imately get floor art from other layers, so the reverse is not an error.
        layer = self.w.tile_layers.get("entrance_floor")
        if layer is None:
            self.add("info", "MATRIX_TMJ", "", "entrance_floor_absent",
                     "no entrance_floor layer -- ghost-door check skipped")
            return
        W = self.w.W
        ghosts = []
        for i, gid in enumerate(layer.get("data", [])):
            if (gid & 0x1FFFFFFF) == FLOOR and self.w.collision[i] == "1":
                ghosts.append((i % W, i // W))
        if ghosts:
            shown = ", ".join(f"({x},{y})" for x, y in ghosts[:8])
            more = "" if len(ghosts) <= 8 else f" (+{len(ghosts) - 8} more)"
            self.add("error", "MATRIX_TMJ", "", "ghost_door",
                     f"{len(ghosts)} entrance_floor cell(s) drawn open (FLOOR/{FLOOR}) "
                     f"but collision-sealed: {shown}{more} -- repaint the tile to WALL")
```

Register it in `run()` (the method list around lines 763-780), right after `self.check_collision_vs_walls()`:

```python
        self.check_collision_vs_walls()
        self.check_entrance_floor_sealed()
```

- [ ] **Step 4: Run the tests + the real-map validator**

Run: `uv run --no-sync pytest godot-generative-agents/tools/geo/test_validate_tmj.py -q`
Expected: PASS (existing tests + the two new ones).
Run: `uv run --no-sync python godot-generative-agents/tools/geo/validate_tmj.py`
Expected: exit 0 — no un-baselined errors (Sweeten sealed in Task 2, Van Pelt already consistent, so zero `ghost_door` findings on the real map).

- [ ] **Step 5: Full geo suite**

Run: `uv run --no-sync pytest godot-generative-agents/tools/geo/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox
git add godot-generative-agents/tools/geo/validate_tmj.py \
        godot-generative-agents/tools/geo/test_validate_tmj.py
git commit -m "feat(geo): validate_tmj ghost-door guard — entrance_floor drawn-open vs collision-sealed (#556)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Notes for the implementer

- **Why the collision seal isn't moved:** `FORCED_CLOSED`'s `collision[...] = "1"` at `add_entrances.py:835-836` runs inside the per-building loop and must precede the collision-matrix write (~line 867). The `floor` array is built later (~line 877), so the tile repaint is a separate call after `paint_interior` — this is intended, not a duplication to consolidate.
- **The surgical edit is line-addressed, not text-anchored:** the pretty tmj wraps data at the map width (245 values/row), and short value windows are NOT unique in the file (verified). The script locates the `entrance_floor` data block relative to its `"name"` key, then the row-99 line by index — do not swap it for a context-based text replace.
- **Idempotency after the fix:** once Task 1 lands, re-running `add_entrances.py` paints `(46,99)` and Van Pelt's east door as `WALL` — matching the committed tmj — so a regen no longer flips those cells. (The layer-id churn is a separate, out-of-scope quirk; a raw regen still isn't byte-identical, but regens are never committed.)

## Self-review

- **Spec coverage:** repaint helper + call (spec §Design 1) → Task 1; surgical Sweeten seal (§Design 2) → Task 2; `validate_tmj` one-directional ghost-door guard (§Design 3) → Task 3; geo pytest for repaint + guard + real-map-clean (§Verification) → Tasks 1 & 3; commit discipline / no minified regen (§Verification) → Task 2 Steps 2-3 + Global Constraints; out-of-scope (layer-id churn, collision content) honored. All covered.
- **Type consistency:** `seal_forced_closed_floor(floor, W)`, `check_entrance_floor_sealed(self)`, `FLOOR`/`WALL` constants, `self.add(...)`, `Checker`, `v.FLOOR`, `real_world()` all match `add_entrances.py`/`validate_tmj.py`/`test_validate_tmj.py` as they exist.
- **Placeholder scan:** no TBD/TODO; every step carries complete code or an exact verified command with expected output.
