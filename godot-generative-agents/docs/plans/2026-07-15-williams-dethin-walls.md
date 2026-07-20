# Williams Double-Wall De-thin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the owner's Tiled de-thin of `williams_walls` (+ resized `williams_arenas`) as the committed map — normalized through `furnish_williams`, with the six derived matrix CSVs regenerated, a no-double-wall regression test, and the fallback constant refreshed.

**Architecture:** The owner already edited the tmj in Tiled (removed the redundant parallel wall line; resized the room arenas). This plan is the *tooling half*: normalize that edit into `furnish_williams`'s canonical splice format (Tiled's whitespace differs), re-derive collision/arena/furniture matrices from the cleaned map, and lock it in with tests. No relayer/splice logic changes — `furnish_williams` already self-seeds the walls and (via #571) reads the authored arenas.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `black`. Geo tooling under `godot-generative-agents/tools/geo/`.

## Global Constraints

- **Branch/track:** `godot-ga-main` (geo-only). Branch `feat/williams-dethin-walls-572`, worktree at `.claude/worktrees/williams-dethin-572`, based on #571 (`feat/williams-repro-552`). PR targets `godot-ga-main`; rebase onto it if #571 merges first.
- **The committed tmj stays Tiled-pretty.** `add_entrances`/`gen_furniture_matrix` write the tmj *minified* — run the matrix chain on a COPY and commit only the CSVs. **Never commit a minified tmj.**
- **The owner's edit is uncommitted in the working tree** (`williams_walls` de-thinned, `williams_arenas` resized). Do not discard or re-edit it — only normalize its format via `furnish_williams`.
- **Reproducibility invariant (from #571):** after this change, re-running `furnish_williams` on the committed tmj must leave it byte-identical, and the matrix chain must reproduce the committed CSVs. `test_williams_reproducible.py` guards this and must stay green.
- **Never `git add -A`.** Stage only the exact files each task names. The guide artifacts under `tools/geo/out/` are NOT committed.
- **Commit trailer (every commit):** end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Run all commands via `uv run` from the worktree root `.claude/worktrees/williams-dethin-572/`.
- Audience: first/second-year undergraduates — clear, readable code + comments.

**Paths (from worktree root):**
- tmj: `godot-generative-agents/godot/maps/upenn_core_urban.tmj`
- matrix dir: `godot-generative-agents/backend/penn/the_upenn/matrix`
- geo tools: `godot-generative-agents/tools/geo/`

---

## File Structure

- `godot-generative-agents/godot/maps/upenn_core_urban.tmj` — **modify** (normalize the owner's edit; commit the canonical-format version).
- `godot-generative-agents/backend/penn/the_upenn/matrix/{maze,special_blocks}/*.csv` — **modify** (regenerate the six Williams-affected CSVs).
- `godot-generative-agents/tools/geo/test_williams_arenas.py` — **modify** (add the no-double-wall test; this is the committed-map Williams test file).
- `godot-generative-agents/tools/geo/furnish_williams.py` — **modify** (refresh the `WILLIAMS_ARENA_OBJECTS` fallback constant only).

---

## Task 1: Normalize the edit; commit the de-thinned tmj + regenerated matrices

**Files:**
- Modify: `godot-generative-agents/godot/maps/upenn_core_urban.tmj`
- Modify: the six matrix CSVs (`maze/collision_maze.csv`, `maze/arena_maze.csv`, `maze/furniture_maze.csv`, `special_blocks/arena_blocks.csv`, `special_blocks/furniture_blocks.csv`, `special_blocks/furniture_spots.csv`)

**Interfaces:**
- Consumes: the owner's uncommitted Tiled edit in the working tmj.
- Produces: a committed, canonical-format tmj that `furnish_williams` reproduces byte-identically, and matrix CSVs the chain reproduces.

**Background:** `furnish_williams` is the canonical writer of `williams_walls` + `williams_arenas`. Running it re-emits them in its splice format (Tiled saved slightly different whitespace). Verified: the result is formatting-only (tile data + arena geometry unchanged) and self-reproduces. The matrix chain then re-derives collision/arena/furniture from the cleaned map.

- [ ] **Step 1: Confirm the owner's edit is present (do not proceed without it)**

Run:
```bash
uv run python - <<'PY'
import json, sys
sys.path.insert(0,'godot-generative-agents/tools/geo'); import furnish_building as fb
M=0x1FFFFFFF
t=json.load(open('godot-generative-agents/godot/maps/upenn_core_urban.tmj')); W=t['width']
d=next(l for l in t['layers'] if l['name']=='williams_walls')['data']
wall={(i%W,i//W) for i,v in enumerate(d) if (v&M)==fb.WALL}
xs=[x for x,_ in wall]; ys=[y for _,y in wall]
bad=sum(1 for x in range(min(xs),max(xs)) for y in range(min(ys),max(ys)) if all((x+a,y+b) in wall for a in(0,1) for b in(0,1)))
print("wall_brick cells:", len(wall), " all-wall 2x2:", bad)
PY
git status --porcelain godot-generative-agents/godot/maps/upenn_core_urban.tmj
```
Expected: `wall_brick cells: 263  all-wall 2x2: 0` and the tmj shows ` M` (modified, uncommitted). If instead you see `340` / `40` or a clean tmj, STOP and report BLOCKED — the owner's edit is missing.

- [ ] **Step 2: Normalize the edit through `furnish_williams`**

Run:
```bash
uv run python godot-generative-agents/tools/geo/furnish_williams.py \
  --tmj godot-generative-agents/godot/maps/upenn_core_urban.tmj
```
This rewrites the tmj in the canonical splice format and leaves a `<path>.bak` (the pre-normalize Tiled save).

- [ ] **Step 3: Verify the normalization is formatting-only + self-reproducing**

Run:
```bash
uv run python - <<'PY'
import json, shutil, subprocess, sys, os
P='godot-generative-agents/godot/maps/upenn_core_urban.tmj'
bak=P+'.bak'
norm=json.load(open(P)); tiled=json.load(open(bak)); W=norm['width']
def L(t,n): return next(l for l in t['layers'] if l['name']==n)
for n in ('williams_walls','williams_floor','williams_furniture'):
    assert L(norm,n)['data']==L(tiled,n)['data'], f'{n} tile data changed by normalize!'
def a(t): return sorted((o['name'],round(o['x']),round(o['y']),round(o['width']),round(o['height'])) for o in L(t,'williams_arenas')['objects'])
assert a(norm)==a(tiled), 'arena geometry changed by normalize!'
# self-reproduce: run furnish_williams again on a copy -> byte-identical
tmp='/tmp/wdt_selfrt.tmj'; shutil.copy2(P,tmp)
subprocess.check_call([sys.executable,'godot-generative-agents/tools/geo/furnish_williams.py','--tmj',tmp],
                      stdout=subprocess.DEVNULL)
assert open(P,'rb').read()==open(tmp,'rb').read(), 'normalized tmj does NOT self-reproduce!'
os.remove(tmp); os.remove(tmp+'.bak')
print('OK: formatting-only + self-reproducing')
PY
```
Expected: `OK: formatting-only + self-reproducing`. Then delete the backup: `rm godot-generative-agents/godot/maps/upenn_core_urban.tmj.bak`

- [ ] **Step 4: Re-derive the matrices on a copy, then copy the six CSVs back**

Run:
```bash
WORK=$(mktemp -d)
cp godot-generative-agents/godot/maps/upenn_core_urban.tmj "$WORK/map.tmj"
cp -R godot-generative-agents/backend/penn/the_upenn/matrix "$WORK/matrix"
for s in add_entrances block_grass block_furniture gen_furniture_matrix; do
  uv run python "godot-generative-agents/tools/geo/$s.py" --tmj "$WORK/map.tmj" --matrix "$WORK/matrix" || exit 1
done
for f in maze/collision_maze.csv maze/arena_maze.csv maze/furniture_maze.csv \
         special_blocks/arena_blocks.csv special_blocks/furniture_blocks.csv special_blocks/furniture_spots.csv; do
  cp "$WORK/matrix/$f" "godot-generative-agents/backend/penn/the_upenn/matrix/$f"
done
rm -rf "$WORK"
echo "matrices copied back"
```
Expected: each script prints its summary and exits 0; `matrices copied back`. (Only the six CSVs are copied back — the minified `$WORK/map.tmj` is discarded.)

- [ ] **Step 5: Verify reproducibility + validity + the full geo suite**

Run:
```bash
uv run pytest godot-generative-agents/tools/geo/test_williams_reproducible.py -q
uv run python godot-generative-agents/tools/geo/validate_tmj.py 2>/dev/null || echo "(validate_tmj not present / non-fatal)"
uv run pytest godot-generative-agents/tools/geo/ -q
```
Expected: `test_williams_reproducible.py` passes (2 tests) — confirms `furnish_williams` reproduces the committed tmj and the chain reproduces the committed CSVs. `validate_tmj` 0 errors. Full geo suite green — **pay attention to `test_williams_arenas.py`**: if `test_williams_room_arenas_present` fails, the resized arenas changed the room IDs/count — STOP and report (do not edit the test to paper over it; it's a real signal). `test_williams_partition_walls_sealed` and reachability recompute dynamically and should pass.

- [ ] **Step 6: Confirm the committed tmj is Tiled-pretty + stage exactly the right files**

Run:
```bash
head -c 30 godot-generative-agents/godot/maps/upenn_core_urban.tmj   # expect: '{ "compressionlevel":-1,' with a newline (pretty)
git status --porcelain
```
Expected: the tmj first bytes are pretty (multi-line, leading `{ "compressionlevel"`), NOT minified (`{"compressionlevel"`). `git status` shows the tmj + the six CSVs modified (plus untracked `tools/geo/out/` guide files, which you will NOT stage).

- [ ] **Step 7: Commit the tmj + matrices**

```bash
git add godot-generative-agents/godot/maps/upenn_core_urban.tmj \
        godot-generative-agents/backend/penn/the_upenn/matrix/maze/collision_maze.csv \
        godot-generative-agents/backend/penn/the_upenn/matrix/maze/arena_maze.csv \
        godot-generative-agents/backend/penn/the_upenn/matrix/maze/furniture_maze.csv \
        godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/arena_blocks.csv \
        godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_blocks.csv \
        godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv
git commit -m "$(cat <<'EOF'
feat(geo): de-thin Williams walls + resize arenas (authored art), re-derive matrices (#572)

Land the owner's Tiled edit: williams_walls single-thickness (no 2x2 double
walls), williams_arenas resized to match. Normalized through furnish_williams
(canonical splice format; formatting-only, self-reproducing) and re-derived the
collision/arena/furniture matrices. Windows + the 43-44 door gap preserved; the
building stays enclosed (perimeter seal is footprint-based in add_entrances).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: No-double-wall regression test

**Files:**
- Modify: `godot-generative-agents/tools/geo/test_williams_arenas.py`

**Interfaces:**
- Consumes: the committed tmj from Task 1.
- Produces: `test_williams_no_double_walls` guarding that `williams_walls` has zero all-`wall_brick` 2×2 windows.

**Background:** Mirrors the sibling buildings' test (`test_furnish_houston.py::test_no_2x2_has_four_walls`, `test_furnish_college_hall.py::test_no_double_walls`). Williams' walls use `wall_brick` = `furnish_building.WALL`. The test reads the committed map directly (the file `test_williams_arenas.py` already opens).

- [ ] **Step 1: Add the test**

`test_williams_arenas.py` reads the committed map via the module-level constant
`SRC_MAP` and, in each test, does a local `import json` / `import furnish_building as
fb` then `json.load(open(SRC_MAP))`. Follow that exact pattern. Append this test to
the file:

```python
def test_williams_no_double_walls():
    # Williams walls must be single-thickness, like the sibling buildings:
    # no 2x2 window is entirely wall_brick (the #572 de-thin). Mirrors
    # test_furnish_houston.test_no_2x2_has_four_walls.
    import furnish_building as fb
    import json

    tmj = json.load(open(SRC_MAP))
    Wd, Hd = tmj["width"], tmj["height"]
    wl = next(L for L in tmj["layers"] if L.get("name") == "williams_walls")["data"]
    bad = 0
    for r in range(Hd - 1):
        for c in range(Wd - 1):
            quad = (
                wl[r * Wd + c],
                wl[r * Wd + c + 1],
                wl[(r + 1) * Wd + c],
                wl[(r + 1) * Wd + c + 1],
            )
            if sum(1 for g in quad if (g & 0x1FFFFFFF) == fb.WALL) == 4:
                bad += 1
    assert bad == 0, f"{bad} 2x2 windows are all wall_brick (double walls)"
```

(Read the map's own `width`/`height` rather than the module's `W, H = 245, 279` to
keep the test self-contained.)

- [ ] **Step 2: Run it — expect PASS (the data is already de-thinned)**

Run: `uv run pytest godot-generative-agents/tools/geo/test_williams_arenas.py::test_williams_no_double_walls -v`
Expected: PASS (Task 1 committed the de-thinned walls). If it FAILS with `bad > 0`, Task 1's tmj wasn't de-thinned — STOP and report.

- [ ] **Step 3: Run the whole arenas file (nothing else regressed)**

Run: `uv run pytest godot-generative-agents/tools/geo/test_williams_arenas.py -v`
Expected: all tests pass, including `test_williams_no_double_walls`.

- [ ] **Step 4: Format + commit**

```bash
uv run black godot-generative-agents/tools/geo/test_williams_arenas.py
git add godot-generative-agents/tools/geo/test_williams_arenas.py
git commit -m "$(cat <<'EOF'
test(geo): assert Williams walls have no 2x2 double walls (#572)

Mirror the sibling buildings' no-double-wall test for williams_walls, guarding
the #572 de-thin against regressions.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Refresh the `WILLIAMS_ARENA_OBJECTS` fallback constant

**Files:**
- Modify: `godot-generative-agents/tools/geo/furnish_williams.py` (the `WILLIAMS_ARENA_OBJECTS` list only)

**Interfaces:**
- Consumes: the committed `williams_arenas` objects from Task 1.
- Produces: a `WILLIAMS_ARENA_OBJECTS` constant matching the resized rooms.

**Background:** Per #571, `WILLIAMS_ARENA_OBJECTS` is a seed-if-absent fallback (used only for a fresh bake with no arenas layer); `_arena_objects` reads the committed layer otherwise. The constant now describes the OLD room boundaries — stale and misleading. Refresh it from the committed arenas. This does **not** change committed output (the layer is the source on the committed path), which is the safety check.

- [ ] **Step 1: Generate the new constant literal from the committed arenas**

Run:
```bash
uv run python - <<'PY'
import json
t=json.load(open('godot-generative-agents/godot/maps/upenn_core_urban.tmj'))
objs=next(l for l in t['layers'] if l['name']=='williams_arenas')['objects']
print("WILLIAMS_ARENA_OBJECTS = [")
for o in objs:
    print(f'    {{')
    print(f'        "name": {o["name"]!r},')
    print(f'        "type": {o.get("type","")!r},')
    print(f'        "x": {o["x"]!r},')
    print(f'        "y": {o["y"]!r},')
    print(f'        "width": {o["width"]!r},')
    print(f'        "height": {o["height"]!r},')
    print(f'    }},')
print("]")
PY
```
This prints the exact replacement literal (object order = the committed layer's order).

- [ ] **Step 2: Replace the constant in `furnish_williams.py`**

Open `furnish_williams.py`, find the existing `WILLIAMS_ARENA_OBJECTS = [ ... ]` block (starts around line 137), and replace the entire list literal with the output from Step 1. Keep the surrounding code and any comment above the constant. Do not touch any other code.

- [ ] **Step 3: Verify committed output is unchanged (the safety check) + suite green**

Run:
```bash
# furnish_williams on the committed tmj must STILL be byte-identical
# (constant is fallback-only; the layer is read on the committed path).
cp godot-generative-agents/godot/maps/upenn_core_urban.tmj /tmp/wdt_const.tmj
uv run python godot-generative-agents/tools/geo/furnish_williams.py --tmj /tmp/wdt_const.tmj >/dev/null
cmp godot-generative-agents/godot/maps/upenn_core_urban.tmj /tmp/wdt_const.tmj \
  && echo "OK: committed tmj still reproduces byte-identically" \
  || echo "FAIL: constant change altered committed output"
rm -f /tmp/wdt_const.tmj /tmp/wdt_const.tmj.bak
uv run pytest godot-generative-agents/tools/geo/test_furnish_williams.py godot-generative-agents/tools/geo/test_williams_reproducible.py -q
```
Expected: `OK: committed tmj still reproduces byte-identically`; both test files pass.

- [ ] **Step 4: Format + commit**

```bash
uv run black godot-generative-agents/tools/geo/furnish_williams.py
git add godot-generative-agents/tools/geo/furnish_williams.py
git commit -m "$(cat <<'EOF'
chore(geo): refresh WILLIAMS_ARENA_OBJECTS fallback to the resized rooms (#572)

The seed-if-absent fallback constant still described the old room boundaries.
Refresh it from the committed williams_arenas so a fresh bake seeds the current
rooms. No effect on committed output (the layer is the source on the committed
path; verified byte-identical).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification (after all tasks)

- [ ] `uv run pytest godot-generative-agents/tools/geo/ -q` — all green (incl. `test_williams_reproducible`, `test_williams_arenas`, the new no-double-wall test).
- [ ] `uv run black --check godot-generative-agents/tools/geo/` — clean.
- [ ] `git status --porcelain` — only the tmj, six CSVs, `test_williams_arenas.py`, and `furnish_williams.py` committed; `tools/geo/out/` guide files remain untracked; **no minified tmj**, no `.bak`.
- [ ] `head -c 30` of the committed tmj is pretty (`{ "compressionlevel":-1,` + newline).
- [ ] Headless smoke test loads Williams: `./godot-generative-agents/run_smoke_test.sh` (exit 0); building still enclosed, 5 rooms reachable.

## Self-review notes (author)

- **Spec coverage:** normalize+commit tmj → Task 1 (Steps 2–3, 6–7); re-derive matrices → Task 1 (Steps 4–5); reproducibility preserved → Task 1 Step 5; no-2×2 test → Task 2; constant refresh → Task 3. All spec deliverables covered.
- **Placeholder scan:** none. Task 2's test uses `test_williams_arenas.py`'s real conventions (module constant `SRC_MAP`, local `import json`/`import furnish_building as fb`), verified against the file.
- **Type consistency:** `fb.WALL` (int gid), `WILLIAMS_ARENA_OBJECTS` (list of dicts) used consistently.
- **Safety:** Task 1 refuses to proceed if the owner's edit is missing (Step 1); never commits a minified tmj (Steps 4, 6); stages exact files only.
