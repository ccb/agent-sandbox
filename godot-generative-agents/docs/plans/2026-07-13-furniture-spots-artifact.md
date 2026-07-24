# Furniture Seat Spots as a Committed Artifact (#537) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move seat-spot computation into `gen_furniture_matrix.py` (which sees the tmj), so spots can exclude wall cells and require same-arena furniture; write them to a committed `furniture_spots.csv`; have `WorldMap` load it instead of re-deriving.

**Architecture:** The generator gains a `structural_cells` mask (wall/window/door tiles on ANY layer, from the tmj) and a new `spots()` that returns walkable floor cells 4-adjacent to same-arena furniture, skipping structural and furniture cells. `main()` writes `special_blocks/furniture_spots.csv` (`world, sector, arena, x, y` rows) and the `--debug-overlay` draws the same list — parity by construction. `WorldMap.__init__` replaces its derivation loop with a read of that file.

**Tech Stack:** Python 3.12 stdlib; the existing geo/pytest conventions.

**Spec:** `godot-generative-agents/docs/specs/2026-07-13-furniture-spots-artifact.md` (committed a0468e7)

## Global Constraints

- Branch: `feat/furniture-spots-537` (this PR #544); target `godot-ga-main`.
- Four files change total: `godot-generative-agents/tools/geo/gen_furniture_matrix.py`, `godot-generative-agents/tools/geo/test_furniture_matrix.py`, `godot-generative-agents/backend/world_map.py`, plus docs (`tools/geo/README.md`, `backend/README.md`) — and the regenerated committed artifact `godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv`.
- `furniture_maze.csv` / `furniture_blocks.csv` output stays byte-identical (this change touches only spots).
- `furniture_spots.csv` rows are `, `-separated (`world, sector, arena, x, y`), row-major — mirroring the other `special_blocks` files; building/room names carry no commas.
- The file is OPTIONAL for `WorldMap`: absent → `self.furniture_spots = {}`, non-Penn maps byte-identical.
- The generator never writes the committed tmj; only reads it.
- Run tests from the repo root; `uv run black .` before every commit; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`; never `git add -A`.

---

### Task 1: Generator computes tmj-aware spots + writes `furniture_spots.csv`

**Files:**
- Modify: `godot-generative-agents/tools/geo/gen_furniture_matrix.py` (new `structural_cells`; rewrite `spots()`; wire into `main()` + the `--debug-overlay` branch)
- Modify: `godot-generative-agents/tools/geo/test_furniture_matrix.py` (update the `spots` call + add two tests)
- Create (regenerate): `godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv`

**Interfaces:**
- Consumes: existing `GID_MASK`, `excluded_gids(catalog, tilesets) -> set[int]`, `read_flat`, `_majority_label`, the `main()` locals `tmj`, `W`, `H`, `world`, `sector_m`, `sector_t`, `arena_m`, `arena_t`, `collision`, `furn`, `skip` (= `excluded_gids(...)`).
- Produces: `structural_cells(tmj: dict, structural_gids: set[int]) -> set[int]`; `spots(furn, collision, arena_m, structural, width, height) -> list[tuple[int, int]]` (Task 2's WorldMap loads the file this writes, not these functions).

- [ ] **Step 1: Update the existing spots test + add two, to the new signature**

In `godot-generative-agents/tools/geo/test_furniture_matrix.py`, change the import line to add `structural_cells`:

```python
from gen_furniture_matrix import gid_names, pieces, spots, structural_cells
```

Replace `test_spots_are_walkable_floor_beside_furniture` with the new-signature version and append two tests:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furniture_matrix.py -q -k spots`
Expected: FAIL — `TypeError` (old `spots()` takes 4 args) / `ImportError` for `structural_cells`.

- [ ] **Step 3: Add `structural_cells` and rewrite `spots()`**

In `gen_furniture_matrix.py`, replace the whole current `spots()` function (the one whose docstring starts "Walkable floor cells 4-adjacent to furniture") with these two functions:

```python
def structural_cells(tmj: dict, structural_gids: set[int]) -> set[int]:
    """Flat indices of cells drawing a wall/window/door tile on ANY layer.

    ``excluded_gids`` only matters on ``*_furniture`` layers (it keeps
    structural tiles out of furniture_maze). This is broader: Williams'
    interior walls are painted on ``williams_floor`` and left
    collision-walkable, so a furniture-adjacent floor scan would drop seat
    spots onto them -- this mask (from the tmj, the only place the wall
    identity survives) excludes them."""
    out: set[int] = set()
    for layer in tmj.get("layers", []):
        if layer.get("type") != "tilelayer" or "data" not in layer:
            continue
        for i, g in enumerate(layer["data"]):
            if g and (g & GID_MASK) in structural_gids:
                out.add(i)
    return out


def spots(
    furn: list[str],
    collision: list[str],
    arena_m: list[str],
    structural: set[int],
    width: int,
    height: int,
) -> list[tuple[int, int]]:
    """Walkable floor cells 4-adjacent to furniture in the SAME arena --
    "stand AT it", row-major. Excludes: the furniture tile itself (no
    standing on a rug/seat -- a sit target waits for #446); structural cells
    (walls drawn on a floor layer); and cross-arena adjacency (a lobby spot
    must border the lobby's OWN furniture, not a neighbor room's through a
    doorway). The single source WorldMap loads and --debug-overlay draws."""
    out = []
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if (
                collision[idx] != "0"
                or furn[idx] != "0"
                or idx in structural
                or arena_m[idx] == "0"
            ):
                continue
            a = arena_m[idx]
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    nidx = ny * width + nx
                    if furn[nidx] != "0" and arena_m[nidx] == a:
                        out.append((x, y))
                        break
    return out
```

- [ ] **Step 4: Wire spots into `main()` and the overlay**

In `main()`, immediately after the block that writes `furniture_maze.csv` + `furniture_blocks.csv` and prints `"{len(all_pieces)} pieces -> ..."` (currently ends ~line 275), insert:

```python
    structural = structural_cells(tmj, skip)
    spot_cells = spots(furn, collision, arena_m, structural, W, H)
    spot_rows = []
    for x, y in spot_cells:
        idx = y * W + x
        spot_rows.append(
            f"{world}, {sector_t.get(sector_m[idx], '')}, "
            f"{arena_t.get(arena_m[idx], '')}, {x}, {y}"
        )
    with open(os.path.join(blocks_dir, "furniture_spots.csv"), "w") as fh:
        fh.write("".join(r + "\n" for r in spot_rows))
    print(f"{len(spot_cells)} seat spots -> furniture_spots.csv")
```

Then in the `if args.debug_overlay:` branch, change the spot-points loop from
`for i, (x, y) in enumerate(spots(furn, collision, W, H)):` to reuse the list:

```python
        for i, (x, y) in enumerate(spot_cells):
```

(`spot_cells` is now in scope above the overlay branch.)

- [ ] **Step 5: Run the generator tests + regenerate the committed artifact**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furniture_matrix.py -q`
Expected: all pass (the 9 existing incl. updated + 2 new = 11).
Run: `uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py`
Expected: prints the pieces line, then `"<N> seat spots -> furniture_spots.csv"`. Confirm `furniture_maze.csv`/`furniture_blocks.csv` are unchanged and only `furniture_spots.csv` is new:
Run: `git status --porcelain godot-generative-agents/backend/penn/the_upenn/matrix/`
Expected: only `?? .../special_blocks/furniture_spots.csv` (maze/blocks untouched).

- [ ] **Step 6: Sanity-check the real-map artifact**

Run:
```bash
uv run python - <<'PY'
import collections
rows = [r for r in open("godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv").read().splitlines() if r.strip()]
by = collections.Counter(r.split(", ")[2] for r in rows)  # arena label
print("total spots:", len(rows))
print("Williams lobby spots:", by.get("lobby", "n/a — check arena labels"))
for a, n in by.most_common(6):
    print(f"  {a}: {n}")
PY
```
Expected: a total in the low thousands; report the count. (Williams' arena label is `lobby` shared with other buildings, so this only sanity-checks non-emptiness; the per-building Williams assertion lives in Task 2's backend test.)

- [ ] **Step 7: Format and commit (code, test, artifact)**

```bash
uv run black godot-generative-agents/tools/geo/gen_furniture_matrix.py godot-generative-agents/tools/geo/test_furniture_matrix.py
git add godot-generative-agents/tools/geo/gen_furniture_matrix.py godot-generative-agents/tools/geo/test_furniture_matrix.py godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv
git commit -m "feat(geo): compute seat spots tmj-aware (no walls, same-arena) into furniture_spots.csv (#537)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: WorldMap loads `furniture_spots.csv`; docs

**Files:**
- Modify: `godot-generative-agents/backend/world_map.py` (replace the furniture-spots derivation with a loader)
- Modify: `godot-generative-agents/tests/test_furniture_spots.py` (add a load-shape assertion)
- Modify: `godot-generative-agents/tools/geo/README.md` + `godot-generative-agents/backend/README.md` (docs)

**Interfaces:**
- Consumes: Task 1's committed `furniture_spots.csv` (`world, sector, arena, x, y` rows); WorldMap's existing `blocks` dir path, `world` string.
- Produces: `WorldMap.furniture_spots: dict[address -> list[(x, y)]]` — same attribute `_pin_building_meeting_points` already reads (unchanged).

- [ ] **Step 1: Add the load-shape test**

In `godot-generative-agents/tests/test_furniture_spots.py`, append:

```python
def test_furniture_spots_loaded_from_the_committed_artifact():
    # WorldMap now LOADS spots from furniture_spots.csv (generated tmj-aware),
    # not re-derived. Every loaded spot's address is a real w:s:a string and
    # its tile is walkable; a furnished arena has some.
    import os

    wm = _world_map()
    blocks = os.path.join(
        os.path.dirname(__file__),
        "..",
        "backend",
        "penn",
        "the_upenn",
        "matrix",
        "special_blocks",
    )
    assert os.path.exists(os.path.join(blocks, "furniture_spots.csv"))
    assert wm.furniture_spots, "no spots loaded from furniture_spots.csv"
    for address, tiles in wm.furniture_spots.items():
        assert address.count(":") >= 2  # world:sector:arena
        for x, y in tiles:
            assert wm.collision[y][x] == 0  # every spot is walkable
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py::test_furniture_spots_loaded_from_the_committed_artifact -v`
Expected: PASS actually is possible if the old derivation happens to populate spots — but the `furniture_spots.csv` existence assert is the real gate; it passes because Task 1 committed the file, while WorldMap still derives. That's fine: this test pins the end state; Step 3 makes WorldMap the loader. If it already passes, proceed — Step 4 re-runs the whole suite after the loader swap.

- [ ] **Step 3: Replace the derivation with a loader**

In `godot-generative-agents/backend/world_map.py`, replace the entire furniture-spots block (the comment beginning "Furniture-aware seat spots (#537): a walkable floor tile 4-adjacent" through the end of the derivation loop that appends to `self.furniture_spots`) with:

```python
        # Furniture-aware seat spots (#537): loaded from the committed
        # furniture_spots.csv (gen_furniture_matrix computes them tmj-aware --
        # walls excluded, same-arena furniture required, the furniture tile
        # itself omitted; the file the --debug-overlay draws, so overlay ==
        # sim by construction). Rows are `world, sector, arena, x, y`, grouped
        # by address. Optional -- a world without the file (every non-Penn
        # map) gets {} and behaves exactly as before.
        self.furniture_spots: dict[str, list[tuple[int, int]]] = {}
        spots_path = os.path.join(blocks, "furniture_spots.csv")
        if os.path.exists(spots_path):
            for row in open(spots_path).read().splitlines():
                if not row.strip():
                    continue
                w, s, a, x, y = (c.strip() for c in row.split(","))
                self.furniture_spots.setdefault(f"{w}:{s}:{a}", []).append(
                    (int(x), int(y))
                )
```

(`blocks` is the `special_blocks` dir already computed in `__init__`. This removes the `furniture_maze.csv` read and the `_beside_furniture` derivation entirely — nothing else in WorldMap uses `furn`. Leave `expected` untouched; it still validates `collision`.)

- [ ] **Step 4: Run the furniture + full suite**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py -v`
Expected: all pass. If `test_williams_blackboards_are_spots` FAILS (Williams lobby loaded no spots after wall-exclusion + same-arena), that is a real result, not a test bug: Williams' blackboard-adjacent floor may all be wall or cross-arena. Do NOT loosen it silently — report it as a concern; the correct resolution is that Williams then falls back to centroid routing (like a bare building), which may mean updating that test to assert Williams is absent, but that is the controller's call.
Run: `uv run pytest godot-generative-agents/tests/ -q`
Expected: all pass (including `test_stepper_matches_simulate_prefix`).

- [ ] **Step 5: Update the docs**

In `godot-generative-agents/tools/geo/README.md`, find the regen command sequence that lists `gen_furniture_matrix.py`. Add the missing `block_furniture.py` step immediately before it (the spots rule depends on sealed collision — confirmed gap), and note the new output. The `gen_furniture_matrix.py` line becomes:

```
uv run python godot-generative-agents/tools/geo/block_furniture.py      # seal furniture into collision
uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py # furniture_maze + furniture_blocks + furniture_spots (#537)
```

In `godot-generative-agents/backend/README.md`, wherever the Penn matrix artifacts are described, add one line: `special_blocks/furniture_spots.csv` — per-arena seat spots (`world, sector, arena, x, y`), consumed by `WorldMap.furniture_spots`.

- [ ] **Step 6: Format and commit**

```bash
uv run black godot-generative-agents/backend/world_map.py godot-generative-agents/tests/test_furniture_spots.py
git add godot-generative-agents/backend/world_map.py godot-generative-agents/tests/test_furniture_spots.py godot-generative-agents/tools/geo/README.md godot-generative-agents/backend/README.md
git commit -m "feat(backend): WorldMap loads furniture_spots.csv instead of re-deriving (#537)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
