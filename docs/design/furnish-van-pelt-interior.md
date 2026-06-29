# Furnish Van Pelt Library via the door-gated interior system

**Date:** 2026-06-29
**Branch:** `feat/furnish-van-pelt` (off `godot-ga-main`); PR targets `godot-ga-main`.
**Status:** design approved, ready for implementation plan.

## Goal

Give Van Pelt Library a furnished, navigable library interior on `godot-ga-main`,
using the campus's *current* door-gated interior system — the same machinery that
furnished Williams Hall. Van Pelt's rooms become individually addressable arenas
(e.g. `UPenn:Van Pelt Library:Moelis Family Grand Reading Room`).

This re-implements, on the current architecture, what an abandoned branch
(`feat/map-asset-creation`, tip `f5219ce`) did with a now-defunct pipeline. We carry
over only that branch's *content* (the library theme and room names), not its code.

## Background / why this shape

`godot-ga-main` reworked building interiors into a unified door-gated system and
diverged hard from the old branch:

- `add_entrances.py` (PR #240) hollows each OSM building footprint into a walkable
  interior, keeps a 1-tile perimeter wall, opens exactly one door gap (BFS over the
  collision grid enforces "enter through the door"), and tags the interior as one
  arena, id `INTERIOR_ARENA_BASE (1000) + sector_id`.
- `furnish_building.py` paints a furnished cutaway into the **picture** (the `.tmj`)
  only; it *reads* the sim matrix to find a footprint but never writes it. It
  currently hardcodes Williams Hall's room plan and knows the room kinds
  `classroom` / `office` / `restroom` plus a central `atrium`.
- The old branch's `buildings`-layer brick perimeter and its
  `westwing/eastwing/furnish_library/wall_contour/build_arenas` pipeline assume a map
  structure that no longer exists (the `buildings` layer on `godot-ga-main` is empty;
  footprints live in `entrance_floor`). That code is **dropped**, not ported.

Van Pelt already exists on `godot-ga-main`: sector 30, carved enterable by
`add_entrances.py` with one lobby arena `1030`, footprint at cols 17–157 / rows 17–68.
Its carved interior (arena `1030`, 4,659 floor cells) is an H-shaped hall: a west
block (cols 19–67, rows 19–56) and an east block (cols 89–155, rows 27–66), joined by
an open central band (rows 34–49) through a throat at cols 68–88. The single entrance
door is a 3-wide gap on the **east** wall (col 155, rows 56–58).

## Architecture

A single **per-building room plan** is the source of truth, consumed by both tools so
the painted walls (picture) and the collision walls + arenas (matrix) are always the
same rectangles.

### 1. Shared room plan

A per-sector plan record: a list of rooms, each `{name, kind, rect (x0,y0,x1,y1
inclusive), door (side, width)}`, plus optional atrium dressing (reception, seating,
plants) and a `subdivide` flag (default `False`) that opts the building's matrix into
per-room arena subdivision (see §3). Lives in one place and is keyed by sector name.
Williams' existing plan is migrated into this structure unchanged (`subdivide` omitted
→ `False`); Van Pelt's is added with `subdivide: True`.

Each room's `door (side, width)` names the wall (`top`/`bottom`/`left`/`right`) carved
open onto its neighbour in the circulation chain below — e.g. Study Booths' door is on
its `top` wall into Weigle Commons. The picture painter and the matrix subdivider read
the same `door` field, so the visual gap and the collision gap coincide.

Decision: keep the plan in `furnish_building.py` as `PLANS = {sector_name: plan}`, and
have `add_entrances.py` import it. `furnish_building.py` is the natural home (it already
holds Williams' `ROOMS`); `add_entrances.py` already imports `furnish_building` helpers,
so the dependency direction is unchanged.

### 2. `furnish_building.py` — picture (generalized)

- Replace the module-level Williams constants (`ROOMS`, `SEATING_CLUSTERS`,
  `RECEPTION`, `ATRIUM_PLANTS`, `SOUTH_DOOR_X`) with a `PLANS[sector]` lookup selected
  by the existing `--sector` flag.
- **Williams output must stay byte-identical** after the refactor (regression guard).
- Add three library room kinds to `furnish_room`:
  - `reading_room` — long reading tables down the centre + bookshelves along the top
    wall; rugs/plants as space allows.
  - `stacks` — parallel rows of bookshelves with aisles.
  - `study` — individual study desks/booths in a grid.
  Reuse existing furniture constants (`BOOKSHELF`, `DESK`, `TEACHER_DESK`, `RUG`,
  `SOFA`, `SIDE_TABLE`, `PLANT`, …); pull any missing library tile from the existing
  `furniture_catalog.json` (extend the catalog, don't hand-build GIDs).
- The all-or-nothing `stamp()` guarantee already enforces the **cardinal rule** (no
  multi-tile sprite is ever placed partially). Verify 0 partial sprites after a run.

### 3. `add_entrances.py` — matrix (per-room subdivision, opt-in)

- After carving a building's lobby as today, if the building's plan sets
  `subdivide: True` (Van Pelt does; Williams does **not**), subdivide its interior:
  - paint interior collision walls (`collision==1`) on each room's borders, matching
    the picture's room rects;
  - open one door gap per room (collision `0`) onto the adjacent circulation space,
    sized to the plan's door width;
  - assign each room a new arena id and stamp its cells in `arena_maze.csv`;
  - add `arena_blocks.csv` rows `<id>, UPenn, Van Pelt Library, <room name>`.
- **Arena id scheme:** room arenas use `ROOM_ARENA_BASE (2000) + sector_id*10 +
  room_index`. Van Pelt (sector 30) → `2300`–`2304`. This avoids the densely packed
  lobby range `1000`–`1036` and allows up to 10 rooms per building.
- Buildings without a room plan, or whose plan does not opt in, keep today's single
  lobby arena — so Williams and every other building are **unchanged**.
- Idempotency is preserved: the room subdivision recomputes from the original footprint
  + plan each run, exactly as the lobby carve already does.

### Data flow

```
sector_blocks.csv ─┐
                   ├─► add_entrances.py ─► collision_maze, arena_maze, arena_blocks   (matrix: walls, doors, room arenas)
PLANS[sector] ─────┤                                                                   ▲ same rects
                   └─► furnish_building.py --sector "Van Pelt Library" ─► .tmj picture  (floor, walls, furniture)
```

## The Van Pelt room plan

Five rooms, fitted to the real interior (verified against arena `1030`), in the real
floor plan's west→east order. Regions are interior-cell extents (cols × rows,
inclusive); exact wall lines reuse the building perimeter where a room abuts it.

| Arena | Name | Kind | Region (cols × rows) | Notes |
|---|---|---|---|---|
| `2300` | Weigle Information Commons | `reading_room` | 19–67 × 19–49 | west block, main hall |
| `2301` | Study Booths | `study` | 19–67 × 50–56 | west block, south strip |
| `2302` | Kamin Gallery | `stacks` | 68–88 × 34–49 | central connector (throat) bridging the wings |
| `2303` | East Commons / Circulation | `reading_room` | 89–129 × 27–66 | east block, west slice |
| `2304` | Moelis Family Grand Reading Room | `reading_room` | 130–155 × 27–66 | easternmost slice; holds the east entrance door |

**Circulation (every room BFS-reachable from the entrance):**
east door → Moelis → East Commons → Kamin Gallery → Weigle Commons → Study Booths.
Each room opens onto its neighbour along that chain; no dead ends.

A handful of single-cell slivers at block edges (col 68 west; the row-56 notch) are
absorbed into the adjacent room so no interior cell is left unassigned.

## Testing

- **Williams regression:** `furnish_building.py --sector "Williams Hall"` produces a
  byte-identical `.tmj` to pre-refactor; `add_entrances.py` produces byte-identical
  matrix CSVs for Williams and every non-opted-in building.
- **Van Pelt picture:** furnishes with **0 partial sprites** and **0 overlaps** (the
  `stamp()` invariant), every placed object inside the footprint.
- **Van Pelt matrix:** the 5 room arenas appear in `arena_blocks.csv`; every room
  arena is reachable from the entrance door by BFS over `collision_maze.csv` (assert
  connectivity, mirroring `path_finder.py`).
- **Idempotency:** running each tool twice yields identical output.

## Out of scope (YAGNI)

- Resurrecting the old branch's `westwing.py` / `eastwing.py` / `furnish_library.py` /
  `wall_contour.py` / `build_arenas.py`, its `buildings`-layer perimeter, or its
  expanded footprint.
- A distinct `gallery` room kind with display cases (Kamin Gallery uses `stacks` for
  now). Can be added later if desired.
- Upper floors of Van Pelt; only the carved ground-floor interior is furnished.
- Relocating the entrance door (it stays where `add_entrances.py` placed it).

## Risks / notes

- The entrance lands in Moelis's east wall, so agents enter through the grand reading
  room — consistent with the real building's east staircase entrance near Moelis.
- Interior walls added to the matrix must line up cell-for-cell with the picture's
  room walls; the shared plan is what guarantees this, so both consumers must read the
  same rects with the same inclusive-rectangle convention.
