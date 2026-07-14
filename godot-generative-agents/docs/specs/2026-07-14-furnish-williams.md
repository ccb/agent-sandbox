# Furnish Williams Hall — subdivide the shell into room arenas (#538)

**Issue:** #538 · **Branch:** `feat/furnish-williams-538` off `godot-ga-main` ·
**Track:** godot-ga-main (tools/geo + backend/penn matrices + world_data + tests).

## Goal

Williams Hall is the only scheduled Penn venue with no interior subdivision: its
whole interior is one ~1244-tile `lobby` arena (1032), so Professor Tanaka's
problem session drops her on bare floor. Give Williams real rooms in the matrix,
route Tanaka into a classroom, and fix the two data bugs found during #537/#544
prep — all without a from-scratch furnish, because the rooms are **already
painted**.

## Current state (verified)

- **The rooms already exist as art.** `furnish_building.py` (Williams' furnisher)
  draws `williams_floor` (floor + `wall_brick` partitions + windows shell) and
  `williams_furniture` (blackboards, desks, seating). `furnish_building.ROOMS`
  defines five rooms — Classroom A/B/C, Office, Restroom — around an open central
  atrium dressed with seating clusters. The **picture** has rooms; the **matrix**
  does not.
- **Williams is excluded from subdivision.** In `add_entrances.py` Williams is
  processed in the main carve loop (footprint from `williams_floor`, interior
  hollowed, single south door at `WILLIAMS_DOOR_X = (40,41)`), assigned lobby
  arena `1032`, but it is **not** in `ROOM_SUBDIVIDE` and has no `load_*_plan`, and
  its picture is skipped (`name != WILLIAMS`) because `furnish_building` owns it.
  It is the only subdivide-candidate building with neither a `williams_walls` nor a
  `williams_arenas` layer.
- **Bug 1 — walk-through walls (from #538 comment).** The interior `wall_brick`
  partitions are painted on `williams_floor`, left collision `0`; `block_furniture`
  only seals `*_furniture` layers, so nothing seals wall-category tiles on a floor
  layer. A* treats them as walkable and #544 seat-spots land on them (33 cells).
- **Bug 2 — stray windows (from #538 comment).** `williams_furniture` carries 46
  window-category tiles (painted there so `block_furniture` sealed them absent a
  walls layer). #537's generator already excludes them from `furniture_maze`, but
  they belong on a walls layer.
- **Addressing.** A room's address is `{world}:{sector}:{arena}` verbatim
  (`world_map.py:79-80`), e.g. `UPenn:Williams Hall:Classroom A`. No schedule uses
  a room-level address yet — all are `:lobby`/`:grounds`. `DECIDE_MAX_ENUM = 20`,
  currently 17/20.
- **The arena outline is authored.** The `williams_arenas` object layer was drawn
  and hand-tweaked in Tiled to fit the painted rooms (preview
  `tools/geo/out/upenn_williams_arenas_preview.tmj`). Eight objects: `Classroom A`,
  `Classroom B 1`+`Classroom B 2` (the L-shaped room, split), `Office`, `Restroom`,
  `Classroom C`, and `Lobby 1`+`Lobby 2` (the central general-seating area).

## Design

### 1. `tools/geo/furnish_williams.py` (new) — arena layer + wall relayer + wall-cell provider

A small module mirroring the dual role the other `furnish_*` modules play (author
the picture bits AND provide the cell sets `add_entrances` consumes), but Williams'
floor/furniture already exist so it does **not** repaint them. It provides:

- **`read_sections(tmj)`** — `name → (c0,r0,c1,r1)` inclusive tile rects from the
  `williams_arenas` object layer (round px/16), same idiom as
  `furnish_college_hall.read_sections`.
- **`grouped_sections(tmj)`** — merges numbered sub-boxes into one bounding rect per
  group via the Irvine `_group` idiom (`Classroom B 1`+`B 2` → `Classroom B`),
  **excluding** any group whose base name is `Lobby` (those cells stay lobby 1032 —
  the general-seating area; excluded like College Hall excludes `rug` objects).
  Verified: the `Classroom B` bbox merge over-claims exactly **1** walkable cell
  (negligible); `Lobby` is never merged because it is excluded.
- **`williams_wall_cells(tmj)`** — the set `{(x,y)}` of cells on the
  `williams_walls` layer (below). This is the **authoritative wall geometry** (the
  tiles `furnish_building` actually painted), so collision matches the picture by
  construction — arena rects only *label* rooms, they do not invent walls.
- **`relayer_walls(tmj)`** — creates the `williams_walls` tile layer (inserted above
  `williams_floor`, below `williams_furniture`) and moves onto it: every `wall_brick`
  cell from `williams_floor` and every window-category cell from `williams_furniture`.
  Idempotent (strips `williams_walls` and re-derives from the two source layers).
  Renders pixel-identical (walls/windows were already opaque above the floor).
- A `--dry-run` main that reports rects, group merges, and relayer counts.

The `williams_arenas` object layer itself is transplanted from the hand-tweaked
preview into the committed tmj as a **surgical insert** (see §4).

### 2. `add_entrances.py` — wire Williams into subdivision

- Add `WILLIAMS` to `ROOM_SUBDIVIDE`.
- Add a `load_williams_plan(tmj, W, H, interior)` branch returning
  `(rooms, wall_cells)`: `rooms = [{"name": nm, "rect": rect} for nm, rect in
  furnish_williams.grouped_sections(tmj).items()]` and `wall_cells =
  furnish_williams.williams_wall_cells(tmj)`. Matches the other loaders exactly.
- `subdivide_rooms` (unchanged) then seals `(wall_cells & interior) - door_cells`
  in collision, assigns each room a `ROOM_ARENA_BASE + 32*100 + idx` arena over its
  walkable cells, and its `_punch_doorway` safety net guarantees every room stays
  reachable. Cells in no room rect (the two Lobby regions + circulation) remain
  lobby 1032. Williams' existing `name == WILLIAMS` special-cases (door, skip
  picture) are untouched — subdivision composes on top.

### 3. `world_data_upenn.yaml` — surface one classroom, re-route Tanaka

- Add a `Williams Hall — Classroom A` location (`UPenn:Williams Hall:Classroom A`)
  after the `Williams Hall` entry, mirroring the Houston room entries (18/20 enum).
- Re-point Professor Tanaka's **solo** problem-session stop from `place: Williams
  Hall` to `place: Williams Hall — Classroom A` so routing targets the classroom
  (Classroom A has the decorated blackboard — fits a physics demo session).
- **No meeting change:** the only Tanaka↔Sofia meeting (`Before the guest lecture
  at Irvine`) is at Irvine Auditorium; Sofia never visits Williams. The Williams
  stop has no meeting.

### 4. Regenerate matrices + commit the tmj surgically

Run order (documented in the PR): the relayer + arena layer land in the tmj, then
`add_entrances.py` regenerates `collision_maze`/`arena_maze`/`arena_blocks`, then
`block_furniture.py` (windows no longer on the furniture layer → not sealed as
furniture; interior walls sealed via subdivision), then **`gen_furniture_matrix.py`**
re-derives `furniture_maze`/`furniture_blocks` (Williams furniture re-attributes
from `lobby` to the room arenas; the 33 spurious wall-spots vanish now that the
partitions are sealed). `furniture_spots` (derived in `world_map` at load) follows
automatically.

The tmj changes — two new layers (`williams_walls`, `williams_arenas`) — go in as
**surgical inserts** into the Tiled-pretty committed tmj (never a minified regen),
per the geo hazard rules (back up first; scripts write minified). `validate_tmj`
drift gate must stay green (baseline updated for the two new layers if needed).

### 5. Out of scope

- Repainting/adding furniture (the art exists) — only relayering walls/windows.
- Redrawing the arena boxes (authored + user-tweaked already).
- Any other building, the viewer, `_pin_meeting_rendezvous`, or new verbs (#446).
- Surfacing more than one room as schedulable (enum budget).

## Verification

- **Geo unit tests** (`tools/geo/`): a new `test_furnish_williams.py` — `read_sections`
  returns the 8 objects; `grouped_sections` merges `Classroom B 1/2` and drops
  `Lobby*`; `relayer_walls` moves all `wall_brick`+windows and is idempotent
  (byte-identical re-run); `williams_wall_cells` == the painted wall set.
- **Arena reachability** (`test_williams_arenas.py`, modeled on
  `test_houston_arenas.py`): all 5 room arenas present in `arena_blocks`; each
  reachable from the south door via BFS on collision; lobby 1032 still present
  (the atrium); partition walls sealed (`collision == 1`); no window tiles remain
  on `williams_furniture`.
- **Backend** (`godot-generative-agents/tests/`): `UPenn:Williams Hall:Classroom A`
  resolves to a non-empty tile set with seat spots; Tanaka's routed settle tile is
  in Classroom A; `test_stepper_matches_simulate_prefix` and scripted-meeting tests
  stay green; decide-enum count == 18, pinned.
- **Full suites** + `validate_tmj` drift gate + `uv run black .` + headless smoke.
- **User visual pass:** open the committed tmj in Tiled → the five rooms are their
  own arenas with sealed walls; then a run — Tanaka settles in Classroom A at the
  blackboard, agents can no longer walk through Williams' interior walls.
