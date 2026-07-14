# One Interaction Spot per Furniture Piece — Typed Placement (#537 refinement)

**Issue:** #537 (PR #544 iteration) · **Branch:** `feat/furniture-spots-537` ·
**Review track:** godot-ga-main.

**Refines** `2026-07-13-furniture-spots-artifact.md`: that shipped one spot per
walkable floor tile *beside* furniture (a ring per piece). The PR owner's
visual pass asked for **one interaction spot per piece**, placed by furniture
type — you stand *on* seats, *in front of* boards/sinks/shelves.

## Goal

Exactly one seat/interaction spot per furniture piece, placed by a two-bucket
rule, and make sofas walkable so their on-top spot is reachable. Spot count
drops from ~3,634 (per-cell ring) to ~one per piece (~500).

## Product rules (from the PR owner), simplified for now

- **Walk-on** (cushion, armchair, chair, stool, sofa, desk-with-chair): the
  spot is a tile **on** the piece — its walkable seat/cushion/chair tile.
- **Front** (blackboard, sink, bookshelf, table, and every other type): the
  spot is the floor tile **in front of** the piece (nearest walkable floor).

Two design realities force the simplification (both confirmed in the data):
pieces are contiguity-merged blobs typed by their anchor tile's name (so a
"blackboard" piece can include merged neighbours — precise "front-centre of
*the blackboard*" is not computable per blob); and the catalog carries **no
orientation metadata** (so "front" must be derived from geometry). The
two-bucket rule reproduces the on-top-vs-in-front intent without either.

## Current state (verified)

- `gen_furniture_matrix.py` already emits per-piece `furniture_blocks.csv`
  (id, world, sector, arena, name via `_majority_label` / `piece_name`) and
  the committed `furniture_spots.csv` (`world, sector, arena, x, y`), and
  computes spots via `spots(furn, collision, arena_m, structural, W, H)` —
  the per-cell rule this refactor replaces. `pieces(tmj, excluded)` returns
  each piece's `cells`/`anchor_gid`/`gids`. `structural_cells` masks
  wall/window/door cells. WorldMap loads `furniture_spots.csv` unchanged.
- **Sofa is solid.** `walkable_furniture.json` (chairs, cushions, stools,
  armchairs — the walk-on allowlist `block_furniture` leaves un-sealed) does
  NOT contain sofa's 6 gids `{1191,1192,1193,1223,1224,1225}`; its 114 tiles
  are all collision `1`. `block_furniture.solid_cells` is **seal-only** (it
  never un-seals — `validate_tmj:588-599` documents this), so adding sofa to
  the allowlist and re-running does nothing to already-sealed cells.
- `validate_tmj.check_furniture_solidity` is one-directional: it flags
  furniture that should be solid but isn't, and *skips* allowlisted gids —
  so an allowlisted-and-walkable sofa passes.
  `check_walkable_allowlist_fresh` only warns on allowlist gids no longer
  painted — sofa's are painted (114 cells), so it stays fresh.

## Design

### 1. Make sofa walkable (collision change)

- Add sofa's 6 gids to `walkable_furniture.json`'s `walkable_gids` (with
  labels, matching the file's format).
- **Surgically un-seal** sofa in `collision_maze.csv`: for every cell whose
  `*_furniture`-layer base gid is a sofa gid, set collision to `"0"` (114
  cells). This is provably equal to the canonical furniture-free-baseline
  regen the seal-only pipeline would need — the only allowlist delta is sofa,
  so a full regen would un-seal exactly those 114 cells and nothing else.
- The pathfinder now walks onto/through sofas (the "(walkthrough)" intent).
- Gates: `validate_tmj` stays green (furniture-solidity skips allowlisted
  sofa; allowlist-fresh sees sofa painted); the stepper↔simulate byte-identity
  test stays green (both sides read the new collision); full suite green.

### 2. One spot per piece — two-bucket placement (generator)

Replace the per-cell `spots(...)` with a per-piece function operating over
`pieces(...)`. For each piece:

- `name = piece_name(piece, names)`; `centroid = mean(cells)`;
  `arena_id = majority(arena_m over cells)`, `arena/sector labels` as
  `furniture_blocks` computes them.
- **Walk-on** iff `name` contains any of
  `{"cushion", "armchair", "chair", "stool", "sofa", "desk"}` (case-folded;
  covers the variants — `cushion_red`, `armchair_orange`, `student_desk`,
  `chair_wood`, …). Its spot = the piece cell that is walkable (`collision ==
  "0"`) and non-structural, nearest the centroid (row-major tiebreak). "desk"
  captures the desk-with-chair sprites whose walkable tile is the chair.
- **Front** (not walk-on, or walk-on with no walkable tile): spot = a floor
  cell (`furn == "0"`, walkable, non-structural, `arena_m == arena_id`)
  4-adjacent to any piece cell, nearest the centroid (row-major tiebreak) —
  the front for a wall-mounted piece.
- A piece with no qualifying spot in either bucket is skipped (its arena
  still routes via centroid if it holds other furniture).
- Emit **one row per piece** to `furniture_spots.csv` (schema unchanged:
  `world, sector, arena, x, y`), row-major over pieces. The `--debug-overlay`
  draws the same one-per-piece list (parity by construction, as before).

### 3. WorldMap, docs, overlay

- `WorldMap` is unchanged — it loads the smaller `furniture_spots.csv`; the
  routing (`_pin_building_meeting_points`) consumes one-per-piece transparently.
- `backend/README.md` / `tools/geo/README.md`: note the one-spot-per-piece
  model and sofa walkability.
- Regenerate the overlay for the PR owner's eyeball.

### 4. Out of scope

- Precise front-**centre** (needs orientation data) and a full per-type table
  (fragile on merged blobs) — deferred; two-bucket approximates for now.
- Per-piece spot identity in the artifact (piece id/name column) — WorldMap's
  5-field parser stays; #446 can re-derive.
- Williams' unsealed *walls* in collision (#538) — untouched.
- Making other walk-through furniture (beds?) walkable — only sofa, per the
  PR owner.

## Verification

- **Generator unit tests** (`test_furniture_matrix.py`): synthetic pieces —
  a walk-on piece (a walkable tile) → spot on that tile; a front piece (solid,
  walkable floor in front) → the front floor tile; nearest-centroid tiebreak;
  a piece whose only floor is cross-arena/structural → skipped; a walk-on
  name with no walkable tile → falls to front. Exactly one spot per piece.
- **Sofa** (`test_furniture_matrix.py` or a geo check): after the allowlist +
  un-seal, sofa's 114 cells are collision `0`; `validate_tmj` reports no
  furniture-solidity error.
- **Backend** (`tests/test_furniture_spots.py`): furnished arenas still have
  spots (≥1 per piece); every spot walkable; Williams keeps spots; the
  byte-identity `test_stepper_matches_simulate_prefix` green.
- **Real-map**: spot count ≈ piece count (~500, was 3,634); every spot is
  walkable and non-structural.
- `uv run pytest godot-generative-agents/tests/ -q`,
  `godot-generative-agents/tools/geo/test_furniture_matrix.py`, and
  `validate_tmj.py` all green; `uv run black .` clean.
- **User visual pass**: regenerate `--debug-overlay`; in Tiled, one point per
  piece — on cushions/chairs/sofas, in front of blackboards/sinks/bookshelves.
