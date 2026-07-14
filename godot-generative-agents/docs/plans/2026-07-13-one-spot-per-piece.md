# One Interaction Spot per Furniture Piece (#537) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make sofas walkable, then place exactly one interaction spot per furniture piece by a two-bucket rule (walk-on → on the piece; else → nearest front floor).

**Architecture:** Task 1 adds sofa's 6 gids to `walkable_furniture.json` and surgically un-seals its 114 collision cells (seal-only `block_furniture` can't). Task 2 replaces the per-cell `spots()` in `gen_furniture_matrix.py` with a per-piece `piece_spot()` over `pieces()`, regenerates the (now ~one-per-piece) `furniture_spots.csv`; the `--debug-overlay` and `WorldMap` consume it unchanged.

**Tech Stack:** Python 3.12 stdlib; the geo/pytest conventions.

**Spec:** `godot-generative-agents/docs/specs/2026-07-13-one-spot-per-piece.md` (committed 2258968)

## Global Constraints

- Branch: `feat/furniture-spots-537` (PR #544); target `godot-ga-main`.
- Sofa gids: `{1191, 1192, 1193, 1223, 1224, 1225}` (interior_franuka, sofa footprint). 114 cells across `*_furniture` layers, all currently collision `1`.
- Walk-on name stems (case-folded substring on the piece name): `cushion`, `armchair`, `chair`, `stool`, `sofa`, `desk`.
- `furniture_spots.csv` schema is UNCHANGED: `world, sector, arena, x, y`, `, `-separated, one row per piece now.
- `furniture_maze.csv` / `furniture_blocks.csv` output stays byte-identical (this change touches only spots).
- The generator never writes the tmj.
- Run tests from the repo root; `uv run black .` before every commit; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`; never `git add -A`.

---

### Task 1: Make sofa walkable (allowlist + surgical un-seal)

**Files:**
- Modify: `godot-generative-agents/tools/geo/walkable_furniture.json` (add 6 sofa gids)
- Modify: `godot-generative-agents/backend/penn/the_upenn/matrix/maze/collision_maze.csv` (un-seal 114 sofa cells)

**Interfaces:**
- Consumes: `block_furniture`'s `GID_MASK`, the tmj `*_furniture` layers.
- Produces: sofa tiles walkable in collision (Task 2's walk-on bucket relies on it), sofa in the allowlist (keeps `block_furniture` seal-only re-runs stable).

- [ ] **Step 1: Add the 6 sofa gids to the allowlist**

In `godot-generative-agents/tools/geo/walkable_furniture.json`, add these entries to the `"walkable_gids"` object (any position; JSON is unordered — put them after the last entry, before the closing `}`):

```json
    "1191": "sofa (interior_franuka) -- long padded sofa, walk-through (#537)",
    "1192": "sofa (interior_franuka) -- long padded sofa, walk-through (#537)",
    "1193": "sofa (interior_franuka) -- long padded sofa, walk-through (#537)",
    "1223": "sofa (interior_franuka) -- long padded sofa, walk-through (#537)",
    "1224": "sofa (interior_franuka) -- long padded sofa, walk-through (#537)",
    "1225": "sofa (interior_franuka) -- long padded sofa, walk-through (#537)"
```

(Remember to add a comma after the previous last entry so the JSON stays valid.) Verify: `uv run python -c "import json; json.load(open('godot-generative-agents/tools/geo/walkable_furniture.json'))"` exits 0.

- [ ] **Step 2: Surgically un-seal sofa's collision cells**

Run this one-time edit (sets every collision cell whose `*_furniture`-layer gid is a sofa gid to `"0"`):

```bash
uv run python - <<'PY'
import json, os, sys
GEO = "godot-generative-agents/tools/geo"
sys.path.insert(0, GEO)
from block_furniture import GID_MASK, read_flat, write_flat

SOFA = {1191, 1192, 1193, 1223, 1224, 1225}
tmj = json.load(open("godot-generative-agents/godot/maps/upenn_core_urban.tmj"))
path = "godot-generative-agents/backend/penn/the_upenn/matrix/maze/collision_maze.csv"
coll = read_flat(path)
cells = set()
for L in tmj["layers"]:
    if L.get("type") == "tilelayer" and L["name"].endswith("_furniture"):
        for i, g in enumerate(L["data"]):
            if g and (g & GID_MASK) in SOFA:
                cells.add(i)
flipped = 0
for i in cells:
    if coll[i] != "0":
        coll[i] = "0"
        flipped += 1
write_flat(path, coll)
print(f"un-sealed {flipped} sofa cells (of {len(cells)} sofa cells) in collision_maze.csv")
PY
```

Expected: `un-sealed 114 sofa cells (of 114 sofa cells)`.

- [ ] **Step 3: Verify the drift gate + byte-identity + suite**

Run: `uv run python godot-generative-agents/tools/geo/validate_tmj.py`
Expected: exits 0 (no new errors; furniture-solidity skips allowlisted sofa, allowlist-fresh sees sofa painted).
Run: `uv run pytest godot-generative-agents/tests/test_penn_live.py -q -k simulate_prefix`
Expected: PASS (stepper↔simulate byte-identity holds — both read the new collision).
Run: `uv run pytest godot-generative-agents/tests/ -q`
Expected: all pass. If a test asserting an exact agent tile/frame FAILS because sofa-walkability shifted a path, that is a real behavior change the PR owner opted into — do NOT loosen it silently; report DONE_WITH_CONCERNS naming the test.

- [ ] **Step 4: Commit**

```bash
git add godot-generative-agents/tools/geo/walkable_furniture.json godot-generative-agents/backend/penn/the_upenn/matrix/maze/collision_maze.csv
git commit -m "feat(geo): sofa is walkable (walk-through) — allowlist + un-seal 114 collision cells (#537)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: One spot per piece — two-bucket placement

**Files:**
- Modify: `godot-generative-agents/tools/geo/gen_furniture_matrix.py` (replace `spots()` with `piece_spot()`; rewire `main()` + overlay)
- Modify: `godot-generative-agents/tools/geo/test_furniture_matrix.py` (replace the `spots` tests)
- Modify (regenerate): `godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv`
- Modify: `godot-generative-agents/tools/geo/README.md`, `godot-generative-agents/backend/README.md` (docs)

**Interfaces:**
- Consumes: Task 1's walkable sofa collision; existing `pieces()`, `piece_name()`, `_majority_label()`, `structural_cells()`, and `main()` locals (`tmj, W, H, world, sector_m, sector_t, arena_m, arena_t, collision, furn, skip, blocks_dir, all_pieces`).
- Produces: `piece_spot(piece, furn, collision, arena_m, arena_t, structural, names, width, height) -> tuple[int,int] | None`; one-row-per-piece `furniture_spots.csv` (WorldMap loads it unchanged).

- [ ] **Step 1: Replace the spots tests**

In `godot-generative-agents/tools/geo/test_furniture_matrix.py`, change the import line to swap `spots` for `piece_spot`:

```python
from gen_furniture_matrix import gid_names, pieces, piece_spot, structural_cells
```

Delete the three tests `test_spots_are_walkable_floor_beside_furniture`, `test_spots_exclude_structural_cells`, `test_spots_require_same_arena_furniture`, and add:

```python
def _piece(cells, anchor_gid=5):
    return {"cells": cells, "anchor_gid": anchor_gid, "gids": [anchor_gid]}


def test_piece_spot_walk_on_lands_on_the_piece():
    # A 1x1 chair (name "chair_wood") that is walkable -> the spot is the
    # chair tile itself.
    names = {5: "chair_wood"}
    furn = ["5"] + ["0"] * 8  # 3x3, chair at (0,0)
    coll = ["0"] * 9
    arena = ["1"] * 9
    got = piece_spot(_piece([(0, 0)]), furn, coll, arena, {"1": "room"}, set(), names, 3, 3)
    assert got == (0, 0)


def test_piece_spot_front_lands_on_nearest_floor():
    # A solid 1x1 blackboard (not a walk-on name) with walkable floor to its
    # right -> the spot is that front floor tile, not the piece.
    names = {5: "blackboard"}
    furn = ["5", "0", "0"]
    coll = ["1", "0", "0"]  # blackboard solid; floor to the right
    arena = ["1", "1", "1"]
    got = piece_spot(_piece([(0, 0)]), furn, coll, arena, {"1": "room"}, set(), names, 3, 1)
    assert got == (1, 0)  # the adjacent floor cell


def test_piece_spot_front_requires_same_arena_non_structural():
    # The only adjacent floor is cross-arena (or structural) -> no spot.
    names = {5: "blackboard"}
    furn = ["5", "0"]
    coll = ["1", "0"]
    arena = ["1", "2"]  # the floor cell is a different arena
    assert piece_spot(_piece([(0, 0)]), furn, coll, arena, {"1": "a", "2": "b"}, set(), names, 2, 1) is None


def test_piece_spot_walk_on_with_no_walkable_tile_falls_to_front():
    # A "sofa" whose tile is somehow solid -> falls through to the front rule.
    names = {5: "sofa"}
    furn = ["5", "0"]
    coll = ["1", "0"]
    arena = ["1", "1"]
    assert piece_spot(_piece([(0, 0)]), furn, coll, arena, {"1": "room"}, set(), names, 2, 1) == (1, 0)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furniture_matrix.py -q -k piece_spot`
Expected: FAIL — `ImportError: cannot import name 'piece_spot'`.

- [ ] **Step 3: Replace `spots()` with `piece_spot()`**

In `gen_furniture_matrix.py`, replace the entire `spots(...)` function (lines ~192-224, docstring "Walkable floor cells 4-adjacent to furniture in the SAME arena") with:

```python
_WALK_ON = ("cushion", "armchair", "chair", "stool", "sofa", "desk")


def piece_spot(
    piece: dict,
    furn: list[str],
    collision: list[str],
    arena_m: list[str],
    arena_t: dict[str, str],
    structural: set[int],
    names: dict[int, str],
    width: int,
    height: int,
) -> tuple[int, int] | None:
    """The single interaction spot for one furniture piece, or None (#537).

    Walk-on pieces (cushion/armchair/chair/stool/sofa/desk-with-chair) get a
    tile ON the piece -- its walkable seat/cushion/chair tile nearest the
    centre. Every other piece (blackboard/sink/bookshelf/table/...) gets the
    floor tile in front -- the nearest walkable, non-structural, same-arena
    cell 4-adjacent to the piece. Nearest-to-centre with a row-major
    tiebreak, so the choice is deterministic. Merged-blob-robust: no
    per-type table, no orientation data."""
    cells = piece["cells"]
    cx = sum(x for x, _ in cells) / len(cells)
    cy = sum(y for _, y in cells) / len(cells)

    def nearest(cands):
        return (
            min(cands, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[1], p[0]))
            if cands
            else None
        )

    name = names.get(piece["anchor_gid"], "").lower()
    if any(stem in name for stem in _WALK_ON):
        on_piece = [
            (x, y)
            for (x, y) in cells
            if collision[y * width + x] == "0" and (y * width + x) not in structural
        ]
        spot = nearest(on_piece)
        if spot is not None:
            return spot

    # Front bucket: nearest same-arena floor tile touching the piece.
    arena = _majority_label(cells, arena_m, arena_t, width)
    if not arena:
        return None
    cellset = set(cells)
    front = set()
    for (x, y) in cells:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < width and 0 <= ny < height) or (nx, ny) in cellset:
                continue
            nidx = ny * width + nx
            if (
                furn[nidx] == "0"
                and collision[nidx] == "0"
                and nidx not in structural
                and arena_t.get(arena_m[nidx], "") == arena
            ):
                front.add((nx, ny))
    return nearest(front)
```

Note: `piece_spot` uses `names.get(piece["anchor_gid"], "")` for the name (the test's `_piece` sets `anchor_gid`), matching how `piece_name` resolves — but taking the anchor gid directly keeps the walk-on test independent of `piece_name`'s tile-`<gid>` fallback. `_majority_label` is defined below `spots()` today; `piece_spot` calls it, and Python resolves it at call time, so ordering is fine. Keep `_WALK_ON` and `piece_spot` where `spots()` was.

- [ ] **Step 4: Rewire `main()` and the overlay**

Replace the spots block in `main()` (the current lines that read `structural = structural_cells(...)` through `print(f"{len(spot_cells)} seat spots -> furniture_spots.csv")`) with:

```python
    structural = structural_cells(tmj, skip)
    spot_cells = []
    spot_rows = []
    for piece in all_pieces:
        spot = piece_spot(
            piece, furn, collision, arena_m, arena_t, structural, names, W, H
        )
        if spot is None:
            continue
        x, y = spot
        sector = _majority_label(piece["cells"], sector_m, sector_t, W)
        arena = _majority_label(piece["cells"], arena_m, arena_t, W)
        spot_cells.append((x, y))
        spot_rows.append(f"{world}, {sector}, {arena}, {x}, {y}")
    with open(os.path.join(blocks_dir, "furniture_spots.csv"), "w") as fh:
        fh.write("".join(r + "\n" for r in spot_rows))
    print(f"{len(spot_rows)} interaction spots (one per piece) -> furniture_spots.csv")
```

The `--debug-overlay` branch already iterates `enumerate(spot_cells)` — leave it; `spot_cells` is now one-per-piece.

- [ ] **Step 5: Run the generator tests + regenerate the artifact**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furniture_matrix.py -q`
Expected: all pass (the non-spots tests + the 4 new piece_spot tests).
Run: `uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py`
Expected: prints the pieces line then `"<N> interaction spots (one per piece) -> furniture_spots.csv"` with N in the ~500 range.
Run: `git status --porcelain godot-generative-agents/backend/penn/the_upenn/matrix/`
Expected: only `furniture_spots.csv` modified (maze/blocks untouched — Task 1's collision change was committed separately).

- [ ] **Step 6: Sanity-check + full suite**

Run:
```bash
uv run python - <<'PY'
rows = [r for r in open("godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv").read().splitlines() if r.strip()]
import sys, os, json
sys.path.insert(0, "godot-generative-agents/tools/geo")
from block_furniture import read_flat
MAZE = "godot-generative-agents/backend/penn/the_upenn/matrix/maze"
W = json.load(open("godot-generative-agents/godot/maps/upenn_core_urban.tmj"))["width"]
coll = read_flat(os.path.join(MAZE, "collision_maze.csv"))
spots = [(int(r.split(", ")[3]), int(r.split(", ")[4])) for r in rows]
print("spots (one per piece):", len(spots))
print("all walkable:", all(coll[y*W+x] == "0" for x, y in spots))
PY
```
Expected: ~500 spots, all walkable True.
Run: `uv run pytest godot-generative-agents/tests/ -q`
Expected: all pass. If `test_furniture_spots.py` asserts a spot COUNT or a specific tile that the one-per-piece model changed, that is expected — update the assertion to the new model (a furnished arena still has ≥1 spot; every spot walkable). Do not weaken a walkability/existence invariant; only adjust counts/specific-tile expectations, and report what changed.

- [ ] **Step 7: Docs**

In `godot-generative-agents/backend/README.md`, update the `furniture_spots.csv` line to note it is now **one interaction spot per piece** (walk-on → on the piece; else → the front floor tile). In `godot-generative-agents/tools/geo/README.md`, add one line by the `gen_furniture_matrix.py` step noting the one-per-piece model and that sofa is walk-through (walkable).

- [ ] **Step 8: Format and commit**

```bash
uv run black godot-generative-agents/tools/geo/gen_furniture_matrix.py godot-generative-agents/tools/geo/test_furniture_matrix.py
git add godot-generative-agents/tools/geo/gen_furniture_matrix.py godot-generative-agents/tools/geo/test_furniture_matrix.py godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv godot-generative-agents/tools/geo/README.md godot-generative-agents/backend/README.md
git commit -m "feat(geo): one interaction spot per furniture piece — walk-on on the piece, else front floor (#537)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
