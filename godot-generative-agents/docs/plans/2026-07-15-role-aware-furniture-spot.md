# Role-Aware Furniture Spot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A schedule stop may name the furniture the agent should occupy (`furniture: blackboard`); the router prefers a spot serving it, so Professor Tanaka's teaching stop lands her at the blackboard instead of a random student desk.

**Architecture:** Persist each spot's furniture-piece name (the generator already computes it) as a new column in `furniture_spots.csv`; `WorldMap` loads it into a parallel `furniture_spot_type: {(x,y): name}` map (the `furniture_spots` shape is unchanged). Thread an optional `furniture` hint from the schedule stop through the sole `walk_path` caller into the routing wrappers, which bias the k-nearest spot pick to matching spots. No hint (or absent furniture) → today's exact behavior; no agent is ever stranded.

**Tech Stack:** Python 3.12, `uv`, pytest. Geo tooling under `tools/geo/`; Penn backend under `backend/`. Tests live in `godot-generative-agents/tests/` (imported via the editable install).

## Global Constraints

- **Track `godot-ga-main`.** Every change is under `godot-generative-agents/`.
- **Never hand-edit `furniture_spots.csv`.** Regenerate it via
  `gen_furniture_matrix.py` (the geo drift-gate compares committed artifacts to a fresh regen).
- **`furniture_spots` keeps its shape** `address -> [(x, y)]`; the piece name goes in a
  **new parallel map** `WorldMap.furniture_spot_type: dict[tuple[int,int], str]`. This keeps
  every existing consumer and `tests/test_furniture_spots.py` assertion valid.
- **The replay contract stays unchanged.** The hint lives only on the internal normalized
  schedule dict + `ScheduleMockClient`, never on the `ScheduleStop` pydantic model
  (`persona_meta_entry` projects each stop to exactly `{place, activity, emoji, steps}`, so
  the hint — like the existing `commands` key — never reaches the serialized meta). Do **not**
  touch `backend/contract_models.py` or `SCHEMA_VERSION`; `tests/test_replay_contract.py` must
  stay green untouched.
- **No stranding.** `walk_path`'s centroid and `orig_walk_path` fallbacks are unchanged; a hint
  is a bias over the candidate set, never a hard requirement.
- **Furniture match is exact string equality** on the piece name (`s == "blackboard"`).
- **Commit trailer (every commit):**
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`/`git add .`** — stage only the exact files each step names.
- Commands assume the repo root as CWD. Tests run via
  `uv run pytest godot-generative-agents/tests/<file>.py -v`. If the worktree has no `.venv`
  yet, run `uv sync --extra dev --extra server --extra llm` once first.

---

### Task 1: Persist the furniture-piece name in `furniture_spots.csv`

**Files:**
- Modify: `godot-generative-agents/tools/geo/gen_furniture_matrix.py:354-366` (the spot-writing loop)
- Regenerate: `godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv`
- Test: `godot-generative-agents/tests/test_furniture_spots.py` (new test function)

**Interfaces:**
- Produces: each row of `furniture_spots.csv` becomes `world, sector, arena, x, y, name`
  (6 comma-separated fields; `name` is the piece's `piece_name()`, e.g. `blackboard`,
  `student_desk`). Task 2 consumes this 6th column.

- [ ] **Step 1: Write the failing test**

Add to `godot-generative-agents/tests/test_furniture_spots.py` (it already defines
`WILLIAMS_CLASSROOM_A` and the blocks-path idiom):

```python
def test_furniture_spots_csv_carries_the_piece_type():
    # #559: each spot row gains a 6th field, the furniture piece's name, so the
    # router can prefer a specific piece (a teacher -> blackboard, not a desk).
    import os

    blocks = os.path.join(
        os.path.dirname(__file__),
        "..", "backend", "penn", "the_upenn", "matrix", "special_blocks",
    )
    rows = [
        r for r in open(os.path.join(blocks, "furniture_spots.csv")).read().splitlines()
        if r.strip()
    ]
    for r in rows:
        assert len(r.split(",")) == 6, f"expected 6 fields (incl. furniture): {r!r}"
    classroom = [
        [c.strip() for c in r.split(",")]
        for r in rows
        if "Williams Hall" in r and "Classroom A" in r
    ]
    names = [c[5] for c in classroom]
    assert names.count("blackboard") == 1, f"Classroom A blackboard spot missing: {names}"
    assert names.count("student_desk") == 12, f"Classroom A desks wrong: {names}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py::test_furniture_spots_csv_carries_the_piece_type -v`
Expected: FAIL — the committed CSV rows have 5 fields, so `len(r.split(",")) == 6` fails.

- [ ] **Step 3: Emit the name column from the generator**

In `gen_furniture_matrix.py`, the spot loop currently reads (≈lines 354-364):

```python
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
```

Change the last two lines of the loop body to also emit the piece name (already available
via `piece_name`, used just above for `furniture_blocks.csv`):

```python
        arena = _majority_label(piece["cells"], arena_m, arena_t, W)
        name = piece_name(piece, names)
        spot_cells.append((x, y))
        spot_rows.append(f"{world}, {sector}, {arena}, {x}, {y}, {name}")
```

- [ ] **Step 4: Regenerate the artifact**

Run: `uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py`
Expected: prints `… interaction spots (one per piece) -> furniture_spots.csv`. Then confirm
**only** the spots CSV changed among the three generated files:

Run: `git -C godot-generative-agents status --short backend/penn/the_upenn/matrix`
Expected: only `furniture_spots.csv` is modified (`furniture_maze.csv` and
`furniture_blocks.csv` unchanged — the generator is idempotent and this change touches only
the spot rows). If either of the other two shows as modified, STOP and report — the change
leaked beyond its intent.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py::test_furniture_spots_csv_carries_the_piece_type -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/tools/geo/gen_furniture_matrix.py \
        godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv \
        godot-generative-agents/tests/test_furniture_spots.py
git commit -m "feat(geo): furniture_spots.csv carries the piece name per spot (#559)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Load the piece name into `WorldMap.furniture_spot_type`

**Files:**
- Modify: `godot-generative-agents/backend/world_map.py:106-114` (the `furniture_spots` loader)
- Test: `godot-generative-agents/tests/test_furniture_spots.py` (new test function)

**Interfaces:**
- Consumes: the 6-column `furniture_spots.csv` from Task 1.
- Produces: `WorldMap.furniture_spot_type: dict[tuple[int, int], str]` mapping a spot tile to
  its piece name. `furniture_spots` keeps its `dict[str, list[tuple[int, int]]]` shape. A row
  with only 5 fields adds no `furniture_spot_type` entry (`.get(tile)` is `None`). Task 3
  consumes `furniture_spot_type`.

- [ ] **Step 1: Write the failing test**

Add to `godot-generative-agents/tests/test_furniture_spots.py`:

```python
def test_worldmap_exposes_spot_furniture_type():
    # #559: the piece name loads into a parallel furniture_spot_type map keyed
    # by tile; furniture_spots keeps its (x, y) tile shape.
    wm = _world_map()
    assert hasattr(wm, "furniture_spot_type"), "WorldMap missing furniture_spot_type"
    classroom_spots = wm.furniture_spots.get(WILLIAMS_CLASSROOM_A)
    assert classroom_spots, "Classroom A has no spots"
    types = {wm.furniture_spot_type.get(t) for t in classroom_spots}
    assert "blackboard" in types, f"no blackboard spot in Classroom A: {types}"
    # Shape unchanged: spots are still plain (x, y) tiles.
    assert all(isinstance(t, tuple) and len(t) == 2 for t in classroom_spots)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py::test_worldmap_exposes_spot_furniture_type -v`
Expected: FAIL — `WorldMap` has no `furniture_spot_type` attribute yet.

- [ ] **Step 3: Load the 6th column**

In `backend/world_map.py`, the loader currently reads (≈lines 106-114):

```python
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

Replace it with a version that also fills the parallel type map, tolerating a legacy
5-field row:

```python
        self.furniture_spots: dict[str, list[tuple[int, int]]] = {}
        self.furniture_spot_type: dict[tuple[int, int], str] = {}
        spots_path = os.path.join(blocks, "furniture_spots.csv")
        if os.path.exists(spots_path):
            for row in open(spots_path).read().splitlines():
                if not row.strip():
                    continue
                fields = [c.strip() for c in row.split(",")]
                w, s, a, x, y = fields[:5]
                name = fields[5] if len(fields) > 5 else ""
                tile = (int(x), int(y))
                self.furniture_spots.setdefault(f"{w}:{s}:{a}", []).append(tile)
                if name:
                    self.furniture_spot_type[tile] = name
```

(The exact surrounding lines/comment above the block are unchanged; match on the
`w, s, a, x, y = (c.strip() ...)` line, which is the part being replaced.)

- [ ] **Step 4: Run the new test + the existing suite for this file**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py -v`
Expected: PASS — the new test passes and every pre-existing test in the file
(`test_furniture_spots_loaded_from_the_committed_artifact`, the routing tests, etc.) stays
green, because `furniture_spots` still holds `(x, y)` tiles.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/world_map.py \
        godot-generative-agents/tests/test_furniture_spots.py
git commit -m "feat(backend): WorldMap loads per-spot furniture type into furniture_spot_type (#559)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Bias `walk_path` toward the hinted furniture

**Files:**
- Modify: `godot-generative-agents/backend/penn/penn_world.py` — `_pin_building_meeting_points`
  `walk_path` (≈lines 103-144) and `_pin_meeting_rendezvous` `walk_path` (≈lines 200-212)
- Test: `godot-generative-agents/tests/test_furniture_spots.py` (new test function)

**Interfaces:**
- Consumes: `WorldMap.furniture_spot_type` from Task 2.
- Produces: `walk_path(from_tile, address, furniture=None)` on the patched world map — when
  `furniture` is set and ≥1 spot in the arena has that name, the k-nearest round-robin runs
  over only the matching spots; otherwise behavior is unchanged. Task 4 passes the hint in.

- [ ] **Step 1: Write the failing test**

Add to `godot-generative-agents/tests/test_furniture_spots.py`:

```python
def test_walk_path_furniture_hint_routes_to_the_named_piece():
    # #559: a furniture hint biases the spot pick to the matching piece.
    wm = _world_map()
    start = (100, 50)  # walkable outdoor point south of campus (as other tests use)
    assert not wm.is_blocked(start)
    classroom_spots = wm.furniture_spots[WILLIAMS_CLASSROOM_A]
    blackboard = [t for t in classroom_spots if wm.furniture_spot_type.get(t) == "blackboard"]
    assert len(blackboard) == 1, f"expected one blackboard spot: {blackboard}"

    # With the hint, the route ends on the blackboard spot.
    hinted = wm.walk_path(start, WILLIAMS_CLASSROOM_A, furniture="blackboard")
    assert hinted, "no path into Classroom A with a blackboard hint"
    assert hinted[-1] == blackboard[0], f"hint ignored: ended at {hinted[-1]}"

    # A hint naming furniture absent from the arena falls back to a normal spot
    # (one of the arena's spots), not stranded.
    absent = wm.walk_path(start, WILLIAMS_CLASSROOM_A, furniture="lectern")
    assert absent, "absent-furniture hint stranded the agent"
    assert absent[-1] in classroom_spots
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py::test_walk_path_furniture_hint_routes_to_the_named_piece -v`
Expected: FAIL — `walk_path()` currently takes no `furniture` keyword, so the call raises
`TypeError: walk_path() got an unexpected keyword argument 'furniture'`.

- [ ] **Step 3: Add the `furniture` bias to `_pin_building_meeting_points`**

In `penn_world.py`, `_pin_building_meeting_points`'s inner `walk_path` currently begins:

```python
    def walk_path(from_tile, address):
        # Furniture first (#537): when the arena has seat spots, walk to one
        # of the k nearest to the approach-offset point -- consumed
        # round-robin per address so co-arrivals spread across furniture
        # instead of stacking -- and only fall through to the centroid pick
        # (below) when every candidate is unreachable. Bare arenas
        # (Williams, grounds) have no spots and keep today's behavior.
        spots = getattr(world_map, "furniture_spots", {}).get(address)
        info = centre_of(address)
        if spots and info:
            cx, cy, _tiles = info
            dx, dy = from_tile[0] - cx, from_tile[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
            tx, ty = cx + dx / dist * offset, cy + dy / dist * offset
            near = sorted(spots, key=lambda t: (t[0] - tx) ** 2 + (t[1] - ty) ** 2)
            near = near[:4]
```

Change the signature to accept `furniture=None`, and narrow the candidate list before the
`sorted(...)` when the hint matches. Replace the block above with:

```python
    def walk_path(from_tile, address, furniture=None):
        # Furniture first (#537): when the arena has seat spots, walk to one
        # of the k nearest to the approach-offset point -- consumed
        # round-robin per address so co-arrivals spread across furniture
        # instead of stacking -- and only fall through to the centroid pick
        # (below) when every candidate is unreachable. Bare arenas
        # (Williams, grounds) have no spots and keep today's behavior.
        # A furniture hint (#559) biases the pick to spots serving that piece
        # (a teacher -> blackboard); no match -> the full spot set, as before.
        spots = getattr(world_map, "furniture_spots", {}).get(address)
        info = centre_of(address)
        if spots and info:
            if furniture:
                types = getattr(world_map, "furniture_spot_type", {})
                matching = [t for t in spots if types.get(t) == furniture]
                if matching:
                    spots = matching
            cx, cy, _tiles = info
            dx, dy = from_tile[0] - cx, from_tile[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
            tx, ty = cx + dx / dist * offset, cy + dy / dist * offset
            near = sorted(spots, key=lambda t: (t[0] - tx) ** 2 + (t[1] - ty) ** 2)
            near = near[:4]
```

Everything below `near = near[:4]` (the round-robin cursor, the `from_tile == target`
check, the `path_finder` call, and the centroid + `orig_walk_path` fallbacks) is
**unchanged** — spots are still plain `(x, y)` tiles.

- [ ] **Step 4: Forward `furniture` through `_pin_meeting_rendezvous`**

`_pin_meeting_rendezvous` wraps `walk_path` and is the outermost wrapper (so the call site
hits it first). Its inner `walk_path` currently reads:

```python
    def walk_path(from_tile, address):
        cluster = venues.get(address)
        if cluster:
            target = tuple(cluster[counts[address] % len(cluster)])
            counts[address] += 1
            if tuple(from_tile) == target:
                return []  # already standing on the rendezvous tile
            path = path_finder.path_finder(
                world_map.collision, tuple(from_tile), target, 1
            )
            if path and len(path) > 1:
                return [tuple(t) for t in path[1:]]
        return orig_walk_path(from_tile, address)
```

Change the signature to accept `furniture=None` and forward it to the underlying router
(a venue cluster ignores the hint; every other address falls through carrying it):

```python
    def walk_path(from_tile, address, furniture=None):
        cluster = venues.get(address)
        if cluster:
            target = tuple(cluster[counts[address] % len(cluster)])
            counts[address] += 1
            if tuple(from_tile) == target:
                return []  # already standing on the rendezvous tile
            path = path_finder.path_finder(
                world_map.collision, tuple(from_tile), target, 1
            )
            if path and len(path) > 1:
                return [tuple(t) for t in path[1:]]
        return orig_walk_path(from_tile, address, furniture=furniture)
```

- [ ] **Step 5: Run the new test + the file's suite**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py -v`
Expected: PASS — the new hint test passes and the existing routing tests
(`test_routing_prefers_a_spot_in_furnished_buildings`, `test_co_arrivals_spread_across_spots`,
`test_arenas_without_furniture_fall_back_to_centroid`) stay green (no hint → unchanged path).

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/backend/penn/penn_world.py \
        godot-generative-agents/tests/test_furniture_spots.py
git commit -m "feat(backend): walk_path biases to a hinted furniture piece (#559)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Thread the per-stop hint from the schedule + point Tanaka at the blackboard

**Files:**
- Modify: `godot-generative-agents/backend/build_world.py:71-97` (`_normalize_personas`)
- Modify: `godot-generative-agents/backend/cognition.py:104-111` (`ScheduleMockClient`, add
  a `furniture` property beside `emoji`/`steps`)
- Modify: `godot-generative-agents/backend/run_simulation.py:153-158` (pass the hint)
- Modify: `godot-generative-agents/backend/penn/world_data_upenn.yaml:220-222` (Tanaka's stop)
- Test: `godot-generative-agents/tests/test_cognition_wiring.py` (new test functions)

**Interfaces:**
- Consumes: `walk_path(..., furniture=...)` from Task 3.
- Produces: the normalized schedule dict carries `furniture` (default `None`);
  `ScheduleMockClient.furniture` returns the current stop's hint; `run_simulation` passes it
  into `walk_path`. End of the chain — nothing downstream consumes it.

- [ ] **Step 1: Write the failing tests**

Add to `godot-generative-agents/tests/test_cognition_wiring.py` (it already imports
`build_world`; add the `ScheduleMockClient` import at the top of the file:
`from backend.cognition import ScheduleMockClient`):

```python
def test_normalized_schedule_carries_the_furniture_hint():
    from backend.build_world import _normalize_personas

    personas = [
        {
            "name": "Teacher", "emoji": "🧮",
            "schedule": [
                {"place": "Room", "activity": "teaching", "furniture": "blackboard"},
                {"place": "Hall", "activity": "resting"},  # no hint
            ],
        }
    ]
    _normalize_personas(personas)
    stops = personas[0]["schedule"]
    assert stops[0]["furniture"] == "blackboard"
    assert stops[1]["furniture"] is None  # absent hint defaults to None


def test_schedule_mock_client_exposes_current_stop_furniture():
    sched = ScheduleMockClient(
        [
            {"place": "Room", "activity": "teaching", "emoji": "🧮",
             "steps": 5, "furniture": "blackboard"},
            {"place": "Hall", "activity": "resting", "emoji": "🧮", "steps": None},
        ]
    )
    assert sched.furniture == "blackboard"
    sched.advance()
    assert sched.furniture is None  # next stop has no hint
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_cognition_wiring.py::test_normalized_schedule_carries_the_furniture_hint godot-generative-agents/tests/test_cognition_wiring.py::test_schedule_mock_client_exposes_current_stop_furniture -v`
Expected: FAIL — `_normalize_personas` drops the unknown `furniture` key (so `stops[0]` has
no `"furniture"` → `KeyError`), and `ScheduleMockClient` has no `furniture` attribute.

- [ ] **Step 3: Carry `furniture` through `_normalize_personas`**

In `backend/build_world.py`, add a `furniture` key to **both** normalized-stop branches,
beside `commands`. The authored-schedule branch (≈lines 73-84) becomes:

```python
            spec["schedule"] = [
                {
                    "place": stop["place"],
                    "activity": stop["activity"],
                    "emoji": stop.get("emoji", spec["emoji"]),
                    "steps": stop.get("steps"),  # None => stay for the rest of the day
                    # Authored one-shot commands the mock brain replays at this
                    # stop, one per decision, before settling into `perform`
                    # (#300 -- e.g. "get ..." then "drink ..." at Houston Hall).
                    "commands": list(stop.get("commands") or []),
                    # Optional furniture the agent should occupy at this stop
                    # (#559 -- e.g. "blackboard" for a teacher). None => the
                    # router's default nearest-spot pick.
                    "furniture": stop.get("furniture"),
                }
                for stop in spec["schedule"]
            ]
```

And the implicit single-stop branch (≈lines 89-97) becomes:

```python
            spec["schedule"] = [
                {
                    "place": spec["destination"],
                    "activity": spec["activity"],
                    "emoji": spec["emoji"],
                    "steps": None,
                    "commands": [],
                    "furniture": None,
                }
            ]
```

- [ ] **Step 4: Add the `furniture` property to `ScheduleMockClient`**

In `backend/cognition.py`, add a property beside `emoji`/`steps` (after the `steps`
property, ≈line 111):

```python
    @property
    def furniture(self):
        """Furniture the agent should occupy at the current stop, or ``None``
        (#559). Read at travel time by run_simulation to bias walk_path."""
        return self._stop.get("furniture")
```

- [ ] **Step 5: Run the two unit tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_cognition_wiring.py::test_normalized_schedule_carries_the_furniture_hint godot-generative-agents/tests/test_cognition_wiring.py::test_schedule_mock_client_exposes_current_stop_furniture -v`
Expected: PASS.

- [ ] **Step 6: Pass the hint at the call site**

In `backend/run_simulation.py`, the travel branch currently reads (≈lines 153-158):

```python
                if command.startswith("travel"):
                    dest = char.location
                    address = getattr(dest, "tile_address", None)
                    st["path"] = (
                        world_map.walk_path(st["tile"], address) if address else []
                    )
```

Pass the current stop's hint (the `getattr` guard means a brain without a `furniture`
property — e.g. a real LLM client — yields `None`, today's behavior):

```python
                if command.startswith("travel"):
                    dest = char.location
                    address = getattr(dest, "tile_address", None)
                    st["path"] = (
                        world_map.walk_path(
                            st["tile"], address,
                            furniture=getattr(char.agent.schedule, "furniture", None),
                        )
                        if address
                        else []
                    )
```

- [ ] **Step 7: Point Tanaka's stop at the blackboard**

In `backend/penn/world_data_upenn.yaml`, Tanaka's Classroom A stop currently reads
(≈lines 220-222):

```yaml
  - place: Williams Hall — Classroom A
    activity: holding a problem session for her physics class
    emoji: 🧮
```

Add the hint:

```yaml
  - place: Williams Hall — Classroom A
    activity: holding a problem session for her physics class
    emoji: 🧮
    furniture: blackboard
```

- [ ] **Step 8: Verify the whole chain + no regressions**

Run: `uv run pytest godot-generative-agents/tests/test_cognition_wiring.py godot-generative-agents/tests/test_furniture_spots.py godot-generative-agents/tests/test_replay_contract.py -v`
Expected: PASS — the new schedule tests pass, the furniture-spot/routing tests stay green,
and `test_replay_contract` is unchanged and green (the hint never reaches the contract).

Then confirm formatting:
Run: `uv run black --check godot-generative-agents/backend/build_world.py godot-generative-agents/backend/cognition.py godot-generative-agents/backend/run_simulation.py`
Expected: `All done!` / would-be-left-unchanged.

- [ ] **Step 9: Commit**

```bash
git add godot-generative-agents/backend/build_world.py \
        godot-generative-agents/backend/cognition.py \
        godot-generative-agents/backend/run_simulation.py \
        godot-generative-agents/backend/penn/world_data_upenn.yaml \
        godot-generative-agents/tests/test_cognition_wiring.py
git commit -m "feat(backend): thread per-stop furniture hint into routing; Tanaka -> blackboard (#559)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- Persist furniture type per spot (spec §1) → Task 1. ✓
- `WorldMap.furniture_spot_type` parallel map, `furniture_spots` shape unchanged (spec §1) → Task 2. ✓
- `walk_path` furniture bias, both wrappers, fallback preserved (spec §3) → Task 3. ✓
- Optional per-stop hint: yaml + `_normalize_personas` + `ScheduleMockClient` (spec §2) → Task 4 Steps 3-4, 7. ✓
- Call site passes `getattr(..., "furniture", None)` (spec §4) → Task 4 Step 6. ✓
- Contract untouched, no `SCHEMA_VERSION` bump (spec §2 note) → Global Constraints + Task 4 Step 8 asserts `test_replay_contract` green; no `contract_models.py` in any task. ✓
- Tanaka → blackboard (acceptance 1) → Task 4 Step 7 + Task 3's routing test proves the mechanism. ✓
- No stranding / unhinted unchanged (acceptance 4) → Task 3 test (absent-furniture fallback) + `near[:4]`/fallbacks unchanged. ✓
- Regen leaves tiles unchanged (acceptance 3) → Task 1 Step 4 git-status check. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". Every code step shows the full before/after. ✓

**3. Type consistency:** `walk_path(from_tile, address, furniture=None)` is identical in Task 3 (both wrappers), Task 4's call site, and the Interfaces blocks. `furniture_spot_type: dict[tuple[int,int], str]` is defined in Task 2 and read in Task 3 (`types.get(t)`). `ScheduleMockClient.furniture` (Task 4 Step 4) matches its use in the call site (Task 4 Step 6) and its test (Task 4 Step 1). The CSV 6th field (Task 1) is read positionally as `fields[5]` in Task 2. ✓
