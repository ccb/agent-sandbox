# Spec: role/activity-aware furniture spot — per-stop furniture hint (#559)

**Date:** 2026-07-15
**Issue:** #559 (Penn routing: a teacher lands at a student desk, not the blackboard)
**Review track:** `godot-ga-main` (Penn routing under `godot-generative-agents/backend/` + geo tooling under `tools/geo/`)
**Follows:** #537 (furniture-spot routing), #538 (Williams subdivision). **Ties to:** #446 (action layer / per-object addressing).

## Context

In a #538 acceptance run, Professor Tanaka's "holding a problem session for her physics
class" stop correctly lands her *inside* Williams Hall's Classroom A, but she settles at
one of the 12 student desks rather than at the **blackboard** at the front, where a
teacher stands.

Root cause: #537's furniture-spot routing
(`backend/penn/penn_world.py` `_pin_building_meeting_points`) picks the k=4 nearest seat
spots to the approach point, round-robin per address, and is **role/activity-blind** — a
teacher teaching is routed exactly like a student choosing a seat. #537 deferred "which
specific piece" to a later layer.

Two facts from the current data make a clean, small fix possible:

1. `walk_path`'s only caller is `backend/run_simulation.py:157`, and at that point
   `char.agent.schedule` (a `ScheduleMockClient`) exposes the **current** stop — which
   during travel is the *destination* stop. So a per-stop hint can ride the agent's own
   schedule and reach the router, making it **agent-aware** (a teacher's stop carries the
   hint; a student's does not) rather than the agent-blind address-keyed compromise the
   issue worried about.
2. Williams Classroom A has exactly 1 `blackboard` + 12 `student_desk` pieces and 13
   spots (one spot per piece, per #537). The generator (`tools/geo/gen_furniture_matrix.py`)
   already computes each piece's name (`piece_name()`) when it derives the spot — but
   `furniture_spots.csv` stores only `world, sector, arena, x, y`, dropping the name.

## Goal

A schedule stop may name the furniture the agent should occupy
(`furniture: blackboard`). The router prefers a spot serving that furniture, so Tanaka's
teaching stop lands her at the blackboard. Every stop without a hint — and every other
agent — routes exactly as today. No agent is ever stranded.

## Design

### 1. Persist furniture type per spot (`furniture_spots.csv`)

`tools/geo/gen_furniture_matrix.py` writes a 6th column — the piece name it already has:

```
UPenn, Williams Hall, Classroom A, 18, 230, blackboard
UPenn, Williams Hall, Classroom A, 14, 234, student_desk
```

Regenerate the committed `backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv`
**via the script** (never hand-edit — the geo drift-gate compares committed artifacts to a
fresh regen). The regen is deterministic: the spot **tiles are unchanged**; only the
trailing `furniture` field is added to each row.

`WorldMap` (`backend/world_map.py`) loads the extra column into a **parallel map**
`self.furniture_spot_type: dict[tuple[int, int], str]` (spot tile → piece name; a spot
tile's `(x, y)` is unique across the map, so a flat tile-keyed dict is unambiguous).
`furniture_spots` keeps its existing `address → [(x, y)]` shape, so every current
consumer and test (`walk_path`, `tests/test_furniture_spots.py`'s
`path[-1] in furniture_spots[addr]` assertions) is unaffected. A row with only 5 fields
(legacy/fixture) simply adds no type entry — `furniture_spot_type.get(tile)` returns
`None`.

### 2. Optional per-stop `furniture` hint on the schedule

A schedule stop is `{place, activity, emoji?, steps?}`; add an optional `furniture?`:

- **`backend/penn/world_data_upenn.yaml`** (the live file `penn_world.WORLD_DATA` loads):
  Tanaka's Classroom A stop gains `furniture: blackboard`. No other stop changes.
- **`backend/build_world.py`** `_normalize_personas`: carry
  `"furniture": stop.get("furniture")` in **both** normalized-stop branches (the
  authored-stop branch and the implicit final-stop branch), defaulting to `None`.
- **`backend/contract_models.py`** `ScheduleStop`: add `furniture: str | None = None`.
- **`backend/cognition.py`** `ScheduleMockClient`: add a `furniture` `@property` returning
  `self._stop.get("furniture")`, beside the existing `emoji`/`steps` properties. During
  travel the current stop (`self._stop`) is the destination, so this reads the
  destination stop's hint.

### 3. Furniture-biased spot pick (`_pin_building_meeting_points`)

`walk_path` grows an optional keyword arg `furniture=None`:

```python
def walk_path(from_tile, address, furniture=None):
    spots = getattr(world_map, "furniture_spots", {}).get(address)
    info = centre_of(address)
    if spots and info:
        cx, cy, _tiles = info
        # approach-offset target point (unchanged)
        ...
        candidates = spots
        if furniture:
            types = getattr(world_map, "furniture_spot_type", {})
            matching = [t for t in spots if types.get(t) == furniture]
            if matching:
                candidates = matching        # bias to the named piece's spot(s)
        # k=4 nearest to the offset point, round-robin per address (unchanged),
        # now over `candidates` -- spots stay plain (x, y) tiles, so the sort,
        # cursor, from_tile check, and path_finder call below are untouched.
        ...
    # centroid fallback + orig_walk_path fallback: unchanged
```

- When `furniture` is set and ≥1 spot in the arena has that name, the k-nearest
  round-robin runs over **only the matching spots**. Williams Classroom A has one
  `blackboard` spot, so Tanaka routes there deterministically.
- When `furniture` is `None`, or no spot matches (the arena lacks that furniture), the
  candidate set is all spots — **today's exact behavior**.
- The centroid pick and the `orig_walk_path` nearest-tile fallback are unchanged, so an
  unreachable target still degrades gracefully; no agent is stranded.
- The round-robin cursor stays keyed by `address` (co-arriving students still spread).

`_pin_meeting_rendezvous` wraps `walk_path` too; its inner wrapper forwards the new
`furniture` kwarg to `orig_walk_path` so a hinted stop routed through it is not dropped.
(Classroom A is not a rendezvous venue, but forwarding keeps the wrapper chain correct.)

### 4. Call site (`run_simulation.py:157`)

```python
st["path"] = (
    world_map.walk_path(
        st["tile"], address,
        furniture=getattr(char.agent.schedule, "furniture", None),
    ) if address else []
)
```

The `getattr(..., None)` guard means a brain without a `furniture` property (e.g. a live
LLM client rather than `ScheduleMockClient`) yields `None` → today's behavior. No hard
dependency on the schedule type.

## Data flow

```
world_data_upenn.yaml (furniture: blackboard)
  -> build_world._normalize_personas  -> ScheduleStop.furniture
  -> ScheduleMockClient.furniture (current/destination stop)
  -> run_simulation.py:157  walk_path(tile, address, furniture=...)
  -> _pin_building_meeting_points: filter spots by name, k-nearest round-robin
  -> blackboard spot tile

gen_furniture_matrix.py -> furniture_spots.csv (+furniture col)
  -> WorldMap.furniture_spots[address] = [(x,y), ...]        (unchanged shape)
  -> WorldMap.furniture_spot_type[(x,y)] = name              (new parallel map)
```

## Testing

- **Generator** (`tools/geo/test_*` or the geo suite): after regen, every
  `furniture_spots.csv` row has 6 fields; Classroom A has a spot named `blackboard` and
  12 named `student_desk`; a regen leaves the `(x, y)` tiles byte-identical to the
  committed file (only the name column added) — a determinism/no-tile-drift assertion.
- **WorldMap** (`godot-generative-agents/tests/`): loading the 6-column CSV populates
  `furniture_spot_type[(x,y)]` with the piece name while `furniture_spots[address]` keeps
  its `[(x,y)]` shape (existing `test_furniture_spots.py` assertions stay green
  unchanged); a legacy 5-column row loads with no type entry (`.get(tile) is None`).
- **Routing** (backend unit test over `_pin_building_meeting_points`): with a small
  synthetic `furniture_spots` for one address containing a `blackboard` spot among
  `student_desk` spots — `walk_path(from, addr, furniture="blackboard")` returns a path
  ending on the blackboard spot; `furniture=None` reproduces the pre-change pick;
  `furniture="lectern"` (absent) falls back to the all-spots pick, not stranded.
- **Schedule**: `_normalize_personas` carries `furniture` (and defaults `None` when
  absent); `ScheduleStop` accepts and defaults it; `ScheduleMockClient.furniture` returns
  the current stop's value.
- **Regression**: existing Penn routing tests and the geo drift-gate (`tmj ⇄ matrix`)
  stay green.

## Scope / non-goals

- **In:** an optional `furniture` hint on schedule stops; the `furniture_spots.csv` type
  column + regen; the type-biased spot pick; Tanaka's one hint.
- **Out:** #446's `sit`/`use` verbs and per-object addressing (`"Blackboard 2"`); any
  change to how student desks are chosen; role/persona *inference* (the hint is authored,
  not derived from persona text); hints for any stop other than Tanaka's.

## Acceptance criteria

1. In a mock run, Tanaka's problem-session stop routes her onto the blackboard spot at
   the front of Classroom A, not a student desk.
2. All other agents' routing is unchanged; a baked mock replay differs only where Tanaka
   now stands.
3. `furniture_spots.csv` carries the `furniture` column with correct names; a regen
   changes no spot tile.
4. A stop with no `furniture` hint, and a hint naming furniture absent from the arena,
   both route exactly as today (no stranding).

## Files touched

- **Modify** `tools/geo/gen_furniture_matrix.py` (emit the `furniture` column)
- **Regenerate** `backend/penn/the_upenn/matrix/special_blocks/furniture_spots.csv`
- **Modify** `backend/world_map.py` (load the 6th column into a new `furniture_spot_type`
  map; `furniture_spots` shape unchanged)
- **Modify** `backend/penn/penn_world.py` (`walk_path` `furniture` bias in both wrappers)
- **Modify** `backend/run_simulation.py` (pass the hint at the call site)
- **Modify** `backend/build_world.py` (`_normalize_personas` carries `furniture`)
- **Modify** `backend/contract_models.py` (`ScheduleStop.furniture`)
- **Modify** `backend/cognition.py` (`ScheduleMockClient.furniture` property)
- **Modify** `backend/penn/world_data_upenn.yaml` (Tanaka's stop → `furniture: blackboard`)
- **Tests** for generator, WorldMap load, routing bias, schedule normalization
