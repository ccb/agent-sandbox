# Transplant the hand-designed Van Pelt Library interior onto godot-ga-main

**Date:** 2026-06-29
**Branch:** `feat/furnish-van-pelt` (off `godot-ga-main`); PR targets `godot-ga-main`.
**Status:** design approved, ready for implementation plan.

## Goal

Bring the **meticulously hand-designed** Van Pelt Library interior — 25 named rooms
with their walls and furniture, built on the abandoned branch `feat/map-asset-creation`
(tip `f5219ce`) — onto the current `godot-ga-main`, wired into its door-gated interior
system so every room is an individually addressable, navigable arena
(`UPenn:Van Pelt Library:<room>`).

We **preserve** the design (transplant the actual painted tiles + room rectangles); we
do **not** regenerate it procedurally. The old branch's *generator code*
(`westwing.py`/`eastwing.py`/`furnish_library.py`/`wall_contour.py`/`build_arenas.py`)
is **not** ported — only its output is kept, as a frozen asset.

## Why transplant (not regenerate)

The decisive measurement: the old branch's designed interior and godot-ga-main's carved
Van Pelt interior occupy essentially the **same cells**.

- godot-ga-main carved interior (arena `1030`): 4,659 cells.
- old-branch designed floors: 4,638 cells; **overlap with carved: 4,628** (99.8%).
- only 10 designed cells fall outside the carved footprint (a sliver at the throat
  seam, cols 66–67); only 31 carved cells are uncovered (bare floor).

So the design drops onto godot-ga-main's footprint almost exactly. Regenerating
procedurally (the earlier plan) would discard the hand-tuned walls and furniture for no
benefit. Transplanting keeps them and is *simpler* engine-side.

## Background (current architecture)

- `add_entrances.py` (PR #240) carved every OSM footprint into a walkable interior with
  a 1-tile perimeter wall and exactly one BFS-enforced door, tagging the interior as one
  arena (`INTERIOR_ARENA_BASE 1000 + sector_id`; Van Pelt sector 30 → lobby `1030`).
  **It is the authoritative matrix builder: every run rebuilds `arena_blocks`,
  re-stamps `arena_maze`, and re-hollows `collision_maze` from scratch** (main, lines
  ~559–584). So the per-room subdivision MUST live inside `add_entrances.py` — a
  subdivision written by any other tool would be silently clobbered on its next run.
- `furnish_building.py` paints a *procedural* cutaway into the picture for Williams Hall.
  **It is not used for Van Pelt and is left unchanged.**
- `entrance_floor` (a `.tmj` tile layer) holds godot-ga-main's plain Van Pelt cutaway:
  it covers 100% of the carved interior (4,659 cells) plus the perimeter wall + door.
- Tilesets are **identical** between the old branch and godot-ga-main (same `firstgid`s),
  so the old branch's tile GIDs are valid as-is on the current map.

The old branch's interior lives in six tile layers — `westwing_floors`,
`eastwing_floors`, `westwing_walls`, `eastwing_walls`, `westwing_furniture`,
`eastwing_furniture` (floors 4,638 / walls 501 / furniture 1,537 cells) — and a named
`arenas` object layer with the 25 room rectangles. The old `buildings`-layer brick
perimeter (417 cells) is **superseded** by godot-ga-main's `entrance_floor` cutaway and
is dropped. Of the 501 wall cells, only 9 touch the perimeter; the rest are interior
partitions — the room dividers, with 1-tile gaps as doorways.

## Architecture

A frozen interior asset feeds two consumers, split by the existing tool boundary:
the **picture** is transplanted by a new tool; the **matrix subdivision** is integrated
into `add_entrances.py` (the matrix authority). `furnish_building.py` is untouched.

### 1. Interior asset — `tools/geo/van_pelt_interior.json`

The user's design, extracted **once** from `f5219ce`:

- the six interior tile layers as cell→GID data (sparse: `{cell_index: gid}` per layer);
- the 25 named room rectangles from the `arenas` object layer (`name` + tile-rect
  `[x0,y0,x1,y1]` inclusive);
- the partition-wall cell set (the union of `westwing_walls` + `eastwing_walls` cells),
  used to derive interior collision.

Committed to the repo so the transplant is reproducible and reviewable without the
abandoned branch. Both consumers below read this one file.

### 2. Picture transplant — `tools/geo/furnish_van_pelt.py`

Grafts the detailed interior onto `upenn_core_urban.tmj`, **idempotently** (strips its
own layers before re-applying; backs up the `.tmj` first). The matrix is NOT touched
here.

- Insert the six interior layers in canonical interior z-order (floors < walls <
  furniture), above `entrance_floor`. These live in their own layers (like Williams'
  `williams_*`), so `add_entrances.py` — which strips only `entrance_*` layers — leaves
  them intact across its runs.
- `entrance_floor` stays as the base cutaway (floor + perimeter + door); the detailed
  floors render above it. No `entrance_floor` cells are removed.
- Clip the 10 throat-seam cells (cols 66–67) that fall outside the carved footprint.
- **Cardinal rule:** never place part of a multi-tile sprite — verify 0 partial sprites.

### 3. Matrix subdivision — inside `add_entrances.py` (opt-in)

`add_entrances.py` already recovers each footprint, carves the perimeter + one door, and
hollows the interior. Add an **opt-in room subdivision** keyed by sector name (Van Pelt
opts in; Williams and every other building do not, so they are unchanged):

- Read the room rectangles + partition-wall cells from `van_pelt_interior.json`.
- After hollowing Van Pelt's interior, set the partition-wall cells to `collision==1`
  in `collision_maze` (the building perimeter + chosen door are carved as today; the
  designed doorway gaps in the partitions stay `0`).
- Stamp each room's *walkable* interior cells (collision `0`, inside the room's rect,
  inside the carved interior) in `arena_maze` with a per-room id, in fixed asset order
  (later rooms win the rare walkable-overlap cell — ~30 cells, mostly shared walls that
  are collision anyway). Emit one `arena_blocks` row per room
  (`<id>, UPenn, Van Pelt Library, <name>`).
- The 25 rects cover ~3,578 of the 4,659 interior cells; the remaining ~1,081 cells are
  circulation not inside any named room. **Keep the lobby arena (`1030`) for those
  leftover cells** (addressable as `UPenn:Van Pelt Library:lobby`). So Van Pelt's arena
  rows = grounds + lobby + 25 rooms.
- **Arena id scheme:** `ROOM_ARENA_BASE (10000) + sector_id*100 + room_index` → Van Pelt
  `13000`–`13024`. Avoids the packed lobby range (`1000`–`1036`) and the grounds ids
  (= sector ids, where the old branch's `34`–`58` collided).
- Because this runs *inside* the authoritative rebuild, re-running `add_entrances.py`
  reproduces the subdivision identically (idempotent) instead of clobbering it.

Also exclude Van Pelt from the plain-cutaway `picture_jobs` (as Williams already is) —
its picture is the transplanted detail, not a generated cutaway.

**Entrance reconciliation (resolved during implementation):**
`add_entrances.py` carved Van Pelt's one door on the far-east wall (col 155, rows
56–58); the design's `Entrance` room is bottom-center (cols 95–136). During
implementation, inspect how the designed doorways chain to the carved door and pick the
cleaner option — either force Van Pelt's door at the designed `Entrance` (as Williams'
door is special-cased), or keep the east door and ensure a path into the interior — and
flag the choice in the plan for review. Hard requirement: every one of the 25 room
arenas must be BFS-reachable from the single building entrance.

### Data flow

```
f5219ce layers + arenas ──(one-time extract)──► tools/geo/van_pelt_interior.json
                                                       │            │
                          furnish_van_pelt.py ◄────────┘            └────────► add_entrances.py (Van Pelt opt-in)
                               └─► upenn_core_urban.tmj                              ├─► collision_maze (partition walls)
                                   (6 interior layers above entrance_floor)          ├─► arena_maze (25 room ids)
                                                                                     └─► arena_blocks (25 rows)
```

## Rooms

All 25 are preserved as designed (names already match the real floor plan), each
becoming an arena `13000`–`13024`:

`113`, `114`, `116`, `117`, `118`, `119`, `120`, `121`, `122`, `123`, `124`, `125`,
`126`, `127`, `West Wing Books`, `Lounge`, `Hallway`, `Kamin Gallery`, `Circulation`,
`Microtext Collection`, `Staff Area`, `Research Data and Digital Scholarship Exchange`,
`Moelis Family Grand Reading Room`, `Study Booths`, `Entrance`.

(The earlier 5-room procedural proposal is **superseded** by this full design.)

## Testing

- **Picture:** 0 partial sprites; every transplanted cell inside the carved footprint;
  interior layers in canonical z-order; `furnish_building.py` output for Williams
  byte-identical (untouched).
- **Matrix:** after `add_entrances.py`, the 25 Van Pelt arenas are present in
  `arena_blocks.csv` with non-clashing ids; `collision_maze` partition walls match the
  asset's wall cells; **every room arena BFS-reachable from the building entrance**
  (mirror `path_finder.py`).
- **Idempotency:** running `furnish_van_pelt.py` twice yields an identical `.tmj`;
  running `add_entrances.py` twice yields identical matrix CSVs (the subdivision
  reproduces, not duplicates).
- **No regression:** `add_entrances.py` leaves Williams and every other (non-opted-in)
  building's matrix byte-identical; `furnish_building.py` for Williams byte-identical.

## Out of scope (YAGNI)

- Porting the old generator code (`westwing.py`/`eastwing.py`/`furnish_library.py`/
  `wall_contour.py`/`build_arenas.py`); we keep only their frozen output.
- Generalizing `furnish_building.py` or adding library room kinds (the regeneration plan
  — no longer needed).
- The old `buildings`-layer brick perimeter (superseded by `entrance_floor`).
- Upper floors of Van Pelt; only the carved ground-floor interior is transplanted.

## Risks / notes

- **Connectivity is the main risk.** The designed doorways (wall gaps) must chain every
  room to the single building entrance once walls become collision. The BFS test gates
  this; unreachable rooms get a doorway added (or the entrance relocated) during
  implementation.
- **entrance_floor reconciliation:** must clear exactly the plain interior floor that the
  detailed floors replace, without disturbing the perimeter/door or neighbouring
  buildings' `entrance_floor` cells.
- The asset freezes GIDs; valid only while tileset `firstgid`s stay identical (they are
  today). If a tileset is renumbered later, the asset must be re-extracted.
