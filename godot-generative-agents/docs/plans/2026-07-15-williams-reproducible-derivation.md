# Williams Reproducible Derivation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock in and make explicit that Williams Hall's derived artifacts (the `williams_walls` tmj layer + the six matrix CSVs) regenerate byte-identically from the authored art layers, and close the two footguns that currently threaten that.

**Architecture:** Williams follows the repo's authored-art + script-derivation model. The `williams_floor` / `williams_furniture` / `williams_arenas` layers are hand-authored inputs (edited in Tiled, checked in). `furnish_williams.py` derives `williams_walls` (and re-splices the arenas) format-preservingly; `add_entrances.py` → `block_grass.py` → `block_furniture.py` → `gen_furniture_matrix.py` derive the matrices. All of this already round-trips byte-identically (measured); this plan makes the arenas a true authored input, single-sources the south door, retires the legacy `furnish_building.py` repaint path, documents the pipeline, and adds a regression test.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `black`. Geo tooling under `godot-generative-agents/tools/geo/`. No new dependencies.

## Global Constraints

- **Branch/track:** `godot-ga-main` (geo-only). Branch is `feat/williams-repro-552`, already created off `godot-ga-main` in an isolated worktree. Target the PR at `godot-ga-main`, NOT `main`.
- **Byte-identity is the acceptance bar:** no change may alter the committed `upenn_core_urban.tmj` or any matrix CSV. Every task that could touch generated output must be proven a no-op on the committed artifacts.
- **Never commit a regenerated `.tmj`:** the committed map is Tiled-pretty; `furnish_building`/`add_entrances`/`gen_furniture_matrix` write it minified. Work only on temp copies in tests; never `git add` the map or matrices in this plan.
- **Never `git add -A` / `git add .`:** stage only the exact files listed per task.
- **Commit trailer (every commit):** end the message with
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Run commands from the worktree root** `.claude/worktrees/williams-repro-552/` via `uv run`.
- **Audience:** first/second-year undergraduates — clear, readable code + comments over cleverness.
- **Formatting:** `uv run black .` must be clean before each commit.

**Paths (relative to worktree root):**
- geo tools: `godot-generative-agents/tools/geo/`
- committed map: `godot-generative-agents/godot/maps/upenn_core_urban.tmj`
- committed matrix: `godot-generative-agents/backend/penn/the_upenn/matrix/`

---

## File Structure

- `godot-generative-agents/tools/geo/furnish_williams.py` — **modify**: add `_arena_objects(tmj)` helper; use it in `apply_to_file` instead of the hardcoded `WILLIAMS_ARENA_OBJECTS`.
- `godot-generative-agents/tools/geo/furnish_building.py` — **modify**: `SOUTH_DOOR_X = (43, 44)`; gut `main()` to a hard refusal (keep all module-level constants/functions as a library).
- `godot-generative-agents/tools/geo/add_entrances.py` — **modify**: `WILLIAMS_DOOR_X = fb.SOUTH_DOOR_X` (single source).
- `godot-generative-agents/tools/geo/test_furnish_williams.py` — **modify**: add unit tests for `_arena_objects`.
- `godot-generative-agents/tools/geo/test_add_entrances.py` — **modify**: add the door single-source test.
- `godot-generative-agents/tools/geo/test_furnish_building_retired.py` — **create**: CLI-refusal + library-still-importable tests.
- `godot-generative-agents/tools/geo/test_williams_reproducible.py` — **create**: byte-identity round-trip regression tests (tmj + matrices).
- `godot-generative-agents/tools/geo/README.md` — **modify**: run order + authored-vs-derived + legacy note.

---

## Task 1: `williams_arenas` becomes a true authored input

**Files:**
- Modify: `godot-generative-agents/tools/geo/furnish_williams.py`
- Test: `godot-generative-agents/tools/geo/test_furnish_williams.py`

**Interfaces:**
- Consumes: existing `_arenas_layer(tmj)` (returns the `williams_arenas` objectgroup dict or `None`), `WILLIAMS_ARENA_OBJECTS` (list of `{name,type,x,y,width,height}` dicts).
- Produces: `_arena_objects(tmj) -> list[dict]` — the objects to splice into `williams_arenas`: the authored layer's own objects when present, else the `WILLIAMS_ARENA_OBJECTS` seed.

**Background:** `apply_to_file` currently strips the `williams_arenas` layer and re-emits it from the `WILLIAMS_ARENA_OBJECTS` constant (lines ~411–412, 418). Because the constant currently matches the committed layer, the round-trip is byte-identical — but any Tiled edit to the arenas would be silently reverted on the next run. Reading the objects back from the tmj layer produces byte-identical output today (verified: read-back preserves int/float types, so `_object_layer_block` renders identically) while making Tiled the source of truth.

- [ ] **Step 1: Write the failing tests**

Add to `test_furnish_williams.py`:

```python
def test_arena_objects_prefers_authored_layer():
    # When a williams_arenas layer exists, its own objects are the source of
    # truth -- NOT the WILLIAMS_ARENA_OBJECTS constant.
    authored = [_obj("Custom Room", 100, 200, 300, 400, t="classroom")]
    tmj = _tmj_with_arenas(authored)
    assert fw._arena_objects(tmj) == authored
    assert fw._arena_objects(tmj) is not fw.WILLIAMS_ARENA_OBJECTS


def test_arena_objects_falls_back_to_constant_when_absent():
    # Fresh bake with no arenas layer yet: seed from the constant.
    tmj = {"width": 245, "height": 279, "layers": []}
    assert fw._arena_objects(tmj) == fw.WILLIAMS_ARENA_OBJECTS


def test_arena_objects_falls_back_when_layer_empty():
    tmj = _tmj_with_arenas([])
    assert fw._arena_objects(tmj) == fw.WILLIAMS_ARENA_OBJECTS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furnish_williams.py -k arena_objects -v`
Expected: FAIL with `AttributeError: module 'furnish_williams' has no attribute '_arena_objects'`

- [ ] **Step 3: Add the `_arena_objects` helper**

In `furnish_williams.py`, add this function immediately after `_arenas_layer` (around line 42, before `read_sections`):

```python
def _arena_objects(tmj):
    """Objects to splice into williams_arenas. The authored layer is the source
    of truth (edited in Tiled, checked in), so when it exists we re-emit its own
    objects. WILLIAMS_ARENA_OBJECTS is only a seed for a fresh bake that has no
    arenas layer yet (see #552)."""
    layer = _arenas_layer(tmj)
    if layer and layer.get("objects"):
        return layer["objects"]
    return WILLIAMS_ARENA_OBJECTS
```

Note: `WILLIAMS_ARENA_OBJECTS` is defined later in the module (line ~125) but that is fine — the name is only resolved when `_arena_objects` is *called*, by which point the module is fully imported.

- [ ] **Step 4: Wire it into `apply_to_file`**

In `apply_to_file`, right after the `arena_objects` are needed. Replace the two `WILLIAMS_ARENA_OBJECTS` references. Add this line just before the `arenas_block = _object_layer_block(...)` call (currently ~line 411):

```python
    arena_objects = _arena_objects(tmj)
```

Then change the `_object_layer_block` call from:

```python
    arenas_block = _object_layer_block(
        WILLIAMS_ARENA_OBJECTS, arenas_id, "williams_arenas", obj_base, k9
    )
```

to:

```python
    arenas_block = _object_layer_block(
        arena_objects, arenas_id, "williams_arenas", obj_base, k9
    )
```

And change the `nextobjectid` bump from:

```python
    text = _bump_header(text, "nextobjectid", obj_base + len(WILLIAMS_ARENA_OBJECTS))
```

to:

```python
    text = _bump_header(text, "nextobjectid", obj_base + len(arena_objects))
```

- [ ] **Step 5: Run the arena_objects tests + the whole furnish_williams suite**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furnish_williams.py -v`
Expected: PASS (new tests + all existing tests still green)

- [ ] **Step 6: Prove byte-identity on the committed map (no-op regression)**

Run this one-off check from the worktree root:

```bash
uv run python - <<'PY'
import json, shutil, tempfile, os
sys_path = "godot-generative-agents/tools/geo"
import sys; sys.path.insert(0, sys_path)
import furnish_williams as fw
src = "godot-generative-agents/godot/maps/upenn_core_urban.tmj"
tmp = tempfile.mktemp(suffix=".tmj")
shutil.copy2(src, tmp)
fw.apply_to_file(tmp)
a = open(src, "rb").read(); b = open(tmp, "rb").read()
print("BYTE-IDENTICAL" if a == b else f"DIFFERS ({len(a)} vs {len(b)})")
os.remove(tmp); os.remove(tmp + ".bak")
PY
```

Expected: `BYTE-IDENTICAL`

- [ ] **Step 7: Format + commit**

```bash
uv run black godot-generative-agents/tools/geo/furnish_williams.py godot-generative-agents/tools/geo/test_furnish_williams.py
git add godot-generative-agents/tools/geo/furnish_williams.py godot-generative-agents/tools/geo/test_furnish_williams.py
git commit -m "$(cat <<'EOF'
feat(geo): williams_arenas is authored input, not a constant reseed (#552)

furnish_williams.apply_to_file re-emitted williams_arenas from the
WILLIAMS_ARENA_OBJECTS constant, silently reverting Tiled edits. Read the
objects from the tmj layer when present (source of truth); keep the constant
as a seed-if-absent fallback for a fresh bake. Byte-output unchanged on the
committed map (read-back preserves int/float types).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Single-source the south door at cols 43–44

**Files:**
- Modify: `godot-generative-agents/tools/geo/furnish_building.py:215-218`
- Modify: `godot-generative-agents/tools/geo/add_entrances.py:119-127`
- Test: `godot-generative-agents/tools/geo/test_add_entrances.py`

**Interfaces:**
- Produces: `furnish_building.SOUTH_DOOR_X == (43, 44)` is the single canonical Williams south-door column pair; `add_entrances.WILLIAMS_DOOR_X` aliases it.

**Background:** `add_entrances` already does `import furnish_building as fb` (line 63). The door constant only feeds `furnish_building`'s (soon-guarded) repaint path + window-skipping and `add_entrances`'s Williams door carve — both already use `(43, 44)` in effect, so aligning `SOUTH_DOOR_X` to `(43, 44)` changes no committed bytes.

- [ ] **Step 1: Write the failing test**

Add to `test_add_entrances.py` (it already imports `add_entrances`; import `furnish_building` too if not present):

```python
def test_williams_door_is_single_sourced():
    import add_entrances as ae
    import furnish_building as fb
    # One canonical value, no drift possible between the two modules.
    assert fb.SOUTH_DOOR_X == (43, 44)
    assert ae.WILLIAMS_DOOR_X == fb.SOUTH_DOOR_X
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest godot-generative-agents/tools/geo/test_add_entrances.py::test_williams_door_is_single_sourced -v`
Expected: FAIL — `assert (40, 41) == (43, 44)` (stale `SOUTH_DOOR_X`)

- [ ] **Step 3: Correct `SOUTH_DOOR_X` in `furnish_building.py`**

Replace lines 215–218:

```python
# Main entrance: a gap in the south perimeter wall, near the lobby.
# STALE: the real carved gap is at columns 43-44 (see add_entrances.WILLIAMS_DOOR_X
# and #552). Only used when repainting Williams; the committed art's door is at 43-44.
SOUTH_DOOR_X = (40, 41)
```

with:

```python
# Main entrance: a gap in the south perimeter wall, near the lobby. This is the
# CANONICAL Williams south-door column pair -- add_entrances.WILLIAMS_DOOR_X
# aliases it, so the collision door and the art can't drift apart (#552).
SOUTH_DOOR_X = (43, 44)
```

- [ ] **Step 4: Alias `WILLIAMS_DOOR_X` in `add_entrances.py`**

Replace lines 119–127:

```python
# Williams Hall is already a furnished cutaway (furnish_building.py) with its door
# in the south wall at these columns -- the floor gap in the painted williams_walls
# ring (Task 538's relayer moved the wall art; re-verify against williams_walls if
# the art changes again). We carve its collision to match, and skip its picture so
# we don't paint over the furniture.
# Columns of the real walkable gap in Williams' south perimeter (the carved
# door), matching the committed art. NOTE: furnish_building.SOUTH_DOOR_X is a
# stale (40, 41) and disagrees -- see #552 to realign the art/furniture.
WILLIAMS_DOOR_X = (43, 44)
```

with:

```python
# Williams Hall is authored art (williams_floor / williams_furniture /
# williams_arenas, edited in Tiled) whose south door is a floor gap in the
# painted williams_walls ring. We carve its collision to match, and skip its
# picture so we don't paint over the furniture. The door columns are single-
# sourced from furnish_building so the collision door and the art can't drift
# (#552); re-verify against williams_walls if the art changes again.
WILLIAMS_DOOR_X = fb.SOUTH_DOOR_X
```

- [ ] **Step 5: Run the test + the add_entrances suite**

Run: `uv run pytest godot-generative-agents/tools/geo/test_add_entrances.py -v`
Expected: PASS (new test + existing green)

- [ ] **Step 6: Format + commit**

```bash
uv run black godot-generative-agents/tools/geo/furnish_building.py godot-generative-agents/tools/geo/add_entrances.py godot-generative-agents/tools/geo/test_add_entrances.py
git add godot-generative-agents/tools/geo/furnish_building.py godot-generative-agents/tools/geo/add_entrances.py godot-generative-agents/tools/geo/test_add_entrances.py
git commit -m "$(cat <<'EOF'
fix(geo): single-source the Williams south door at cols 43-44 (#552)

furnish_building.SOUTH_DOOR_X was a stale (40,41) disagreeing with
add_entrances.WILLIAMS_DOOR_X (43,44). Make SOUTH_DOOR_X the canonical
(43,44) and alias WILLIAMS_DOOR_X = fb.SOUTH_DOOR_X so they can't drift.
No committed bytes change (both already carved at 43-44 in effect).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Hard-refuse `furnish_building`'s Williams repaint

**Files:**
- Modify: `godot-generative-agents/tools/geo/furnish_building.py` (add `import sys`; replace `main()` body)
- Test: `godot-generative-agents/tools/geo/test_furnish_building_retired.py` (create)

**Interfaces:**
- Produces: running `furnish_building.py` as a CLI exits non-zero with a refusal message; the module remains importable and all its constants/functions (`WALL`, `WINDOW`, `FLOOR`, `SOUTH_DOOR_X`, `paint_shell`, `stamp`, …) stay available for `furnish_williams` / `add_entrances` to import.

**Background:** `furnish_building.py` is Williams-specific (`ROOMS` = Williams' rooms) and superseded by authored art + `furnish_williams`. Its old `main()` would delete the authored layers and minify the whole map. Nothing calls `main()` programmatically — only the CLI — so gutting `main()` is safe and leaves the library intact.

- [ ] **Step 1: Write the failing tests**

Create `test_furnish_building_retired.py`:

```python
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "furnish_building.py")


def test_cli_refuses_and_exits_nonzero():
    r = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    msg = (r.stderr + r.stdout).lower()
    assert "furnish_williams" in msg
    assert "retired" in msg or "authored" in msg


def test_cli_refuses_even_with_dry_run():
    r = subprocess.run(
        [sys.executable, SCRIPT, "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0


def test_module_still_imports_as_a_library():
    sys.path.insert(0, HERE)
    import furnish_building as fb

    # Palette constants + helpers that furnish_williams / add_entrances rely on.
    assert isinstance(fb.WALL, int)
    assert isinstance(fb.WINDOW, int)
    assert fb.SOUTH_DOOR_X == (43, 44)
    assert callable(fb.paint_shell)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furnish_building_retired.py -v`
Expected: FAIL — the CLI currently runs (exit 0) and mutates; `test_cli_refuses_*` fail. (`test_module_still_imports` may pass already if `SOUTH_DOOR_X` is `(43,44)` from Task 2.)

- [ ] **Step 3: Add `import sys` to `furnish_building.py`**

At the top imports (currently `import argparse` / `import json` / `import os`, ~lines 42–44), add:

```python
import sys
```

- [ ] **Step 4: Replace the `main()` body with a hard refusal**

Replace the entire `main()` function (currently lines ~488–551, from `def main():` down to just before `if __name__ == "__main__":`) with:

```python
def main():
    # RETIRED. furnish_building.py was the original whole-cloth Williams
    # generator. Williams is now authored art (williams_floor /
    # williams_furniture / williams_arenas, edited in Tiled) with its walls +
    # matrices DERIVED by furnish_williams.py + add_entrances.py. Re-running
    # this legacy generator would overwrite the authored layers and minify the
    # committed map. The module is kept only as a library of palette constants
    # (WALL / WINDOW / FLOOR / SOUTH_DOOR_X) and helpers that those scripts
    # import. See tools/geo/README.md and #552.
    sys.stderr.write(
        "furnish_building.py is retired for Williams Hall.\n"
        "Williams is now authored art (williams_floor / williams_furniture /\n"
        "williams_arenas, edited in Tiled); its walls + matrices are derived by\n"
        "furnish_williams.py + add_entrances.py. This legacy generator would\n"
        "overwrite the authored layers and minify the map. Aborting.\n"
        "See tools/geo/README.md (#552).\n"
    )
    raise SystemExit(2)
```

(Keep the `if __name__ == "__main__": main()` footer unchanged.)

- [ ] **Step 5: Run the retirement tests**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furnish_building_retired.py -v`
Expected: PASS (all three)

- [ ] **Step 6: Confirm dependents still import**

Run: `uv run python -c "import sys; sys.path.insert(0,'godot-generative-agents/tools/geo'); import furnish_williams, add_entrances; print('imports OK')"`
Expected: `imports OK`

- [ ] **Step 7: Format + commit**

```bash
uv run black godot-generative-agents/tools/geo/furnish_building.py godot-generative-agents/tools/geo/test_furnish_building_retired.py
git add godot-generative-agents/tools/geo/furnish_building.py godot-generative-agents/tools/geo/test_furnish_building_retired.py
git commit -m "$(cat <<'EOF'
feat(geo): retire furnish_building's Williams repaint (hard refuse) (#552)

furnish_building.py is superseded by authored art + furnish_williams. Its
CLI now refuses (exit 2) with a pointer to furnish_williams, so it can't
clobber the authored williams_* layers or minify the map. The module stays
importable for its palette constants + helpers.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Document authored-vs-derived + fix the run order

**Files:**
- Modify: `godot-generative-agents/tools/geo/README.md`

**Interfaces:** none (docs). No test; verify by reading.

**Background:** `furnish_williams.py` is absent from the README run order, and nothing states which `williams_*` layers are authored vs derived. Add both, and flag `furnish_building.py` as the retired legacy generator.

- [ ] **Step 1: Add a legacy note under the `furnish_building.py` heading**

In `README.md`, immediately after line 176–183 (the paragraph beginning "`furnish_building.py` opens the roof…"), insert a new paragraph:

```markdown
> **Legacy — retired for Williams.** `furnish_building.py` is the original
> whole-cloth generator (it paints floor + walls + furniture from code). Williams
> Hall has since moved to the repo's authored-art model: its `williams_floor`,
> `williams_furniture`, and `williams_arenas` layers are **hand-authored in Tiled
> and checked in**, and its walls + matrices are **derived** by `furnish_williams.py`
> + `add_entrances.py` (below). Running `furnish_building.py` now refuses (it would
> overwrite the authored layers and minify the map); the module is kept only as a
> library of palette constants + helpers those scripts import. See #552.
```

- [ ] **Step 2: Add `furnish_williams.py` to the run order + note the derivation model**

In `README.md`, in the run-order code block (currently lines ~259–272), insert the `furnish_williams.py` step **before** the `add_entrances.py` line:

```bash
uv run python godot-generative-agents/tools/geo/furnish_williams.py                          # Williams walls (derived from authored arenas)
```

Then, immediately after that code block (after line ~272), insert:

```markdown
**Williams: authored vs derived.** The `williams_floor` / `williams_furniture` /
`williams_arenas` layers are authored inputs — edit them in Tiled, commit them.
`furnish_williams.py` *derives* the `williams_walls` layer from them (a
format-preserving splice, so re-running it is byte-identical), and re-splices the
authored `williams_arenas` unchanged. Everything downstream — the collision /
arena / furniture matrices — is derived by `add_entrances.py` → `block_grass.py`
→ `block_furniture.py` → `gen_furniture_matrix.py`. Re-running the whole chain on
the committed inputs reproduces the committed derived artifacts byte-for-byte
(`test_williams_reproducible.py` guards this). Note: `add_entrances.py` and
`gen_furniture_matrix.py` write the `.tmj` *minified*, but they do not touch the
Williams layers (only the matrices + other buildings' `entrance_floor`), so
Williams' tmj reproducibility is unaffected — don't commit their minified tmj
output.
```

- [ ] **Step 3: Verify the doc reads correctly**

Run: `uv run python -c "print(open('godot-generative-agents/tools/geo/README.md').read().count('furnish_williams.py'))"`
Expected: a count ≥ 3 (heading note + run-order line + derivation paragraph)

Manually re-read the two edited regions to confirm the run order now lists `furnish_williams.py` before `add_entrances.py` and the prose is coherent.

- [ ] **Step 4: Commit**

```bash
git add godot-generative-agents/tools/geo/README.md
git commit -m "$(cat <<'EOF'
docs(geo): document Williams authored-vs-derived + add furnish_williams to run order (#552)

furnish_williams.py was missing from the README run order and nothing said
which williams_* layers are authored vs derived. Add the step (before
add_entrances), spell out the authored/derived split + byte-repro guarantee,
and flag furnish_building.py as the retired legacy generator.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Round-trip regression test (tmj + matrices)

**Files:**
- Create: `godot-generative-agents/tools/geo/test_williams_reproducible.py`

**Interfaces:**
- Consumes: the committed `upenn_core_urban.tmj` and matrix CSVs (read-only; tests operate on temp copies). `furnish_williams.apply_to_file`. The CLI scripts `add_entrances.py`, `block_grass.py`, `block_furniture.py`, `gen_furniture_matrix.py` (each accepts `--tmj` and `--matrix`).
- Produces: a regression suite asserting the derived artifacts regenerate byte-identically.

**Background (measured):** running `furnish_williams.apply_to_file` on a copy of the committed tmj yields a whole-file byte-identical result; running the matrix chain on copies reproduces all six matrix CSVs byte-identically. This task locks that in so it can't silently regress.

- [ ] **Step 1: Write the test file**

Create `test_williams_reproducible.py`:

```python
"""Reproducibility guard for Williams Hall (#552).

The williams_floor / williams_furniture / williams_arenas layers are authored
inputs. Everything else Williams-related is DERIVED and must regenerate
byte-identically from those inputs: the williams_walls tmj layer (furnish_williams)
and the six matrix CSVs (add_entrances -> block_grass -> block_furniture ->
gen_furniture_matrix). These tests run the derivation on temp copies of the
committed artifacts and assert byte-identity.
"""

import filecmp
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# tools/geo -> godot-generative-agents
GGA = os.path.dirname(os.path.dirname(HERE))
COMMITTED_TMJ = os.path.join(GGA, "godot", "maps", "upenn_core_urban.tmj")
COMMITTED_MATRIX = os.path.join(GGA, "backend", "penn", "the_upenn", "matrix")

MATRIX_CSVS = [
    os.path.join("maze", "collision_maze.csv"),
    os.path.join("maze", "arena_maze.csv"),
    os.path.join("maze", "furniture_maze.csv"),
    os.path.join("special_blocks", "arena_blocks.csv"),
    os.path.join("special_blocks", "furniture_blocks.csv"),
    os.path.join("special_blocks", "furniture_spots.csv"),
]


def test_furnish_williams_roundtrip_is_byte_identical():
    import furnish_williams as fw

    tmp = tempfile.mktemp(suffix=".tmj")
    shutil.copy2(COMMITTED_TMJ, tmp)
    try:
        fw.apply_to_file(tmp)
        with open(COMMITTED_TMJ, "rb") as a, open(tmp, "rb") as b:
            assert a.read() == b.read(), "furnish_williams re-run changed the tmj"
    finally:
        for p in (tmp, tmp + ".bak"):
            if os.path.exists(p):
                os.remove(p)


def test_matrix_chain_reproduces_committed_csvs():
    workdir = tempfile.mkdtemp()
    try:
        tmj = os.path.join(workdir, "map.tmj")
        matrix = os.path.join(workdir, "matrix")
        shutil.copy2(COMMITTED_TMJ, tmj)
        shutil.copytree(COMMITTED_MATRIX, matrix)

        for script in (
            "add_entrances.py",
            "block_grass.py",
            "block_furniture.py",
            "gen_furniture_matrix.py",
        ):
            r = subprocess.run(
                [
                    sys.executable,
                    os.path.join(HERE, script),
                    "--tmj",
                    tmj,
                    "--matrix",
                    matrix,
                ],
                capture_output=True,
                text=True,
            )
            assert r.returncode == 0, f"{script} failed: {r.stderr}"

        for rel in MATRIX_CSVS:
            regenerated = os.path.join(matrix, rel)
            committed = os.path.join(COMMITTED_MATRIX, rel)
            assert filecmp.cmp(
                regenerated, committed, shallow=False
            ), f"{rel} differs after regeneration"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
```

- [ ] **Step 2: Run the reproducibility tests**

Run: `uv run pytest godot-generative-agents/tools/geo/test_williams_reproducible.py -v`
Expected: PASS (both tests). If `test_matrix_chain_*` is too slow for your CI budget, note it — do not weaken it silently; the assertion is the deliverable.

- [ ] **Step 3: Run the full geo suite + verify the tree is clean**

Run: `uv run pytest godot-generative-agents/tools/geo/ -q`
Expected: all pass.

Run: `git status --porcelain godot-generative-agents/godot/maps/upenn_core_urban.tmj godot-generative-agents/backend/penn/the_upenn/matrix`
Expected: **empty** — no committed map/matrix was modified by running the tests.

- [ ] **Step 4: Commit**

```bash
uv run black godot-generative-agents/tools/geo/test_williams_reproducible.py
git add godot-generative-agents/tools/geo/test_williams_reproducible.py
git commit -m "$(cat <<'EOF'
test(geo): byte-identity round-trip guard for Williams derivation (#552)

Lock in that the derived artifacts regenerate from the authored inputs:
furnish_williams re-run leaves the tmj byte-identical, and the matrix chain
(add_entrances -> block_grass -> block_furniture -> gen_furniture_matrix)
reproduces all six matrix CSVs byte-for-byte. Runs on temp copies; never
touches the committed artifacts.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification (after all tasks)

- [ ] `uv run pytest godot-generative-agents/tools/geo/ -q` — all green.
- [ ] `uv run black --check godot-generative-agents/tools/geo/` — clean.
- [ ] `uv run python godot-generative-agents/tools/geo/validate_tmj.py` (if present) — 0 errors.
- [ ] `git status --porcelain` shows only the five source/test/doc files + the two plan/spec docs — NO changes to `upenn_core_urban.tmj` or any matrix CSV.
- [ ] Headless smoke test still loads Williams: `./godot-generative-agents/run_smoke_test.sh` (exit 0).
- [ ] Manual: `uv run python godot-generative-agents/tools/geo/furnish_building.py` exits non-zero with the refusal message.

## Self-review notes (author)

- **Spec coverage:** #1 arenas-authored → Task 1; #2 door single-source → Task 2; #3 furnish_building hard-refuse → Task 3; #4 docs/run-order → Task 4; #5 round-trip test → Task 5. All five spec design points covered.
- **Byte-identity:** verified empirically before writing (Task 1 read-back identical; matrix chain identical). Tasks 1 & 5 assert it; Task 2/3 change no generated output.
- **Type consistency:** `_arena_objects(tmj) -> list[dict]` used consistently; `SOUTH_DOOR_X` / `WILLIAMS_DOOR_X` are `tuple[int, int]` throughout.
- **No placeholders:** every code + command step is concrete.
