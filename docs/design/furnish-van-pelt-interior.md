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

A frozen interior asset + one new applier tool. Existing furnishing tools are untouched.

### 1. Interior asset — `tools/geo/van_pelt_interior.json`

The user's design, extracted **once** from `f5219ce`:

- the six interior tile layers as cell→GID data (sparse, keyed by cell index);
- the 25 named room rectangles from the `arenas` object layer (`name` + tile-rect).

Committed to the repo so the transplant is reproducible and reviewable without the
abandoned branch.

### 2. Applier — `tools/geo/furnish_van_pelt.py`

Applies the asset to the current map + matrix, **idempotently** (strips its own
additions and restores the lobby baseline before re-applying; calls `backup_tmj` first).

**Picture (`upenn_core_urban.tmj`):**
- Insert the six interior layers in canonical interior z-order (floors < walls <
  furniture), above `entrance_floor`.
- Clear `entrance_floor`'s plain interior floor where the detailed floors replace it;
  keep its perimeter wall + door tiles.
- Clip the 10 throat-seam cells (cols 66–67) that fall outside the carved footprint.
- **Cardinal rule:** never place part of a multi-tile sprite — verify 0 partial sprites
  after applying.

**Matrix (`the_upenn/matrix`):**
- Replace Van Pelt's single lobby arena (`1030`) with the 25 room arenas: stamp each
  room's cells in `arena_maze.csv`; add `arena_blocks.csv` rows
  `<id>, UPenn, Van Pelt Library, <name>`.
- **Arena id scheme:** `ROOM_ARENA_BASE (10000) + sector_id*100 + room_index` → Van Pelt
  `13000`–`13024`. Avoids the packed lobby range (`1000`–`1036`) and the grounds ids
  (= sector ids, where the old branch's `34`–`58` collided).
- Set interior partition walls (the transplanted wall cells) to `collision==1` in
  `collision_maze.csv`, leaving the designed doorway gaps open. The building's existing
  perimeter wall + door stay as `add_entrances.py` left them.

**Entrance reconciliation (resolved during implementation):**
godot-ga-main carved Van Pelt's one door on the far-east wall (col 155, rows 56–58); the
design's `Entrance` room is bottom-center (cols 95–136). During implementation, inspect
how the designed doorways chain to the carved door and pick the cleaner option — either
relocate the carved door to the designed `Entrance`, or keep the east door and ensure a
path into the interior — and flag the choice in the plan for review. Hard requirement:
every one of the 25 room arenas must be BFS-reachable from the single building entrance.

### Data flow

```
f5219ce layers + arenas ──(one-time extract)──► tools/geo/van_pelt_interior.json
                                                          │
                              furnish_van_pelt.py ◄────────┘
                                   ├─► upenn_core_urban.tmj   (6 interior layers; entrance_floor reconciled)
                                   └─► arena_maze / arena_blocks / collision_maze   (25 arenas; partition collision)
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
- **Matrix:** the 25 Van Pelt arenas present in `arena_blocks.csv` with non-clashing
  ids; `collision_maze` partition walls match the painted walls; **every room arena
  BFS-reachable from the building entrance** (mirror `path_finder.py`).
- **Idempotency:** running `furnish_van_pelt.py` twice yields identical map + matrix.
- **No regression:** Williams and all other buildings' picture + matrix unchanged.

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
