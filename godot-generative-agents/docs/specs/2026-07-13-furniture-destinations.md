# Furniture-Aware Destinations — furniture_maze + Seat Spots + Routing Preference (#537)

**Issue:** #537 · **Branch:** `feat/furniture-spots-537` off `godot-ga-main` ·
**Review track:** godot-ga-main (tools/geo + backend + tests — all ride this
branch per the branch rules).

## Goal

Agents walk to the right buildings but settle at the **centroid-offset tile**
of the arena — Sofia beside the Houston bathroom doors, Tanaka mid-floor.
Make in-building destinations **furniture-aware**: give the sim first-class
knowledge of where furniture is *and what it is* (a `furniture_maze` +
`furniture_blocks` pair mirroring the game-object convention), derive per-
arena **seat spots** (walkable tiles at furniture), and have the building
routing prefer them — with a Tiled-openable **debug overlay** so placements
can be eyeballed before any agent walks to one.

## Current state (verified)

- **Furniture lives geo-side only.** The tmj's `*_furniture` layers
  (houston_furniture, westwing/eastwing_furniture, college_hall, meyerson,
  irvine, fisher, alumni, cohen, williams) carry per-cell GIDs;
  `tools/geo/furniture_catalog.json` maps tile names → GIDs with category
  (`floor|wall|window|door|furniture|prop|tree`), footprint, and room tags.
  The sim sees none of it: `tools/geo/block_furniture.py:97-114` seals
  furniture cells to `1` in `collision_maze.csv` — byte-identical to walls —
  **except** GIDs in `tools/geo/walkable_furniture.json` (single-tile seats:
  chairs, cushions, stools), which stay walkable and are indistinguishable
  from floor.
- **The backend loads** (`backend/world_map.py:38-50`): collision, sector,
  arena, game_object, spawning mazes + the special_blocks id→label tables.
  `game_object_maze/blocks` is the per-cell-id + id-table convention this
  spec mirrors, but it holds only hand-authored interactables (Fisher's
  bookshelves/chairs, Houston's #465 sink/stove/pot).
- **The routing patch** (`backend/penn/penn_world.py:68-121`,
  `_pin_building_meeting_points`): per address, centroid of walkable arena
  tiles → a point `offset` (5.0) tiles toward the approach → nearest
  walkable tile → path; falls back to the original nearest-tile routing when
  unreachable. Meeting venues use `_pin_meeting_rendezvous` (155-189, tight
  round-robin cluster at the centre) — **untouched by this spec**: scripted
  meetings' co-location windows depend on it.
- **Viewer sprite anchor: verified correct** (`viewer.gd:1167-1170` centres
  sprites on the tile; no off-by-half). #537's sprite-anchor checkbox
  closes as "no bug" — Diego's "on a wall" look was his frozen mid-path
  spot from the (now fixed, #536/#539) parser freeze.
- **Hazards honored:** geo scripts that rewrite the committed tmj write it
  minified (repo tracks Tiled-pretty) — this feature only READS the tmj and
  writes new artifacts, so no backup/minify concern. The CI geo job runs
  the suite + `validate_tmj.py` drift gate.

## Design

### 1. `tools/geo/gen_furniture_matrix.py` (new) — the identity join

Reads the committed tmj (read-only), `furniture_catalog.json`,
`arena_maze.csv`, and `collision_maze.csv`; emits:

- **`backend/penn/the_upenn/matrix/maze/furniture_maze.csv`** — per-cell
  furniture instance id, `0` elsewhere (same flat format as the other
  mazes).
- **`backend/penn/the_upenn/matrix/special_blocks/furniture_blocks.csv`** —
  `id, world, sector, arena, name` rows (the game_object_blocks format).
  One id per **contiguous piece** (4-connected nonzero cells within one
  `*_furniture` layer share an id — multi-tile furniture is placed as a
  block of *different* atlas GIDs, so same-GID grouping would shatter one
  desk into six instances). `name` comes from the catalog's GID→name
  reverse lookup on the piece's top-left (anchor) cell; an anchor GID
  missing from the catalog gets `tile-<gid>` (emitted, not dropped — the
  overlay makes such gaps visible). Two distinct pieces placed touching
  merge into one instance — harmless for spot derivation, visible in the
  overlay if the label matters later. `sector`/
  `arena` from `arena_maze` majority over the piece's cells (`grounds`
  pieces keep the building sector with arena `grounds`).
- Both artifacts are committed (like every other matrix) and reproducible;
  the script is idempotent and never touches the tmj.

### 2. Seat spots — derived in `penn_world` at build time

No third artifact: `build_penn_world` derives, once per build,
`spots[arena_address] = ordered list of walkable tiles at furniture` from
`furniture_maze` + `collision_maze` + `arena_maze`:

- a walkable cell 4-adjacent to a furniture cell (stand AT the desk/table),
  **plus** walkable furniture cells themselves (the walkable_furniture.json
  seats — collision `0` with a furniture id).
- Ordered deterministically (row-major), attributed to the arena of the
  walkable cell itself.

The overlay generator (§4) recomputes the same rule for display — ~10 lines
duplicated by design, so tools/geo never imports backend.

### 3. Routing preference in `_pin_building_meeting_points`

When the target address has seat spots, replace the "nearest walkable tile
to the offset point" pick with: the **k nearest spots** to the offset point
(k = 4) consumed **round-robin per address** (the `_rendezvous_clusters`
counter idiom) so co-arriving agents spread across furniture instead of
stacking; unreachable spot → try the next → centroid pick → original
nearest-tile fallback. Addresses with no spots (Williams' bare shell, all
outdoor `grounds`) keep today's behavior exactly. `_pin_meeting_rendezvous`
and `walk_path`'s signature are untouched.

Determinism note: destinations change for furnished, non-meeting stops —
the baked replay regenerates (it's a git-ignored artifact) and the
stepper/simulate byte-identity pin holds because both sides share
`build_penn_world`. Scripted meetings are unaffected (rendezvous pinning
owns meeting venues).

### 4. `tools/geo/out/upenn_furniture_debug.tmj` — the verification overlay

`gen_furniture_matrix.py --debug-overlay` writes a **separate, git-ignored**
tmj (same tilesets/map geometry) whose layers are the base map plus a
`furniture_debug` **object layer**: one labeled rectangle per furniture
instance (`<name> — <sector>: <arena>`, color-coded per building) and one
point object per derived seat spot. Open in Tiled, toggle the layer, and
eyeball: right piece, right building/arena, sensible spot tiles. This is
the user-facing check that placements are correct; catalog gaps show up as
`tile-<gid>` labels.

### 5. Out of scope

- `sit`/`use` verbs, per-object addressing for schedules ("Reading Chair
  2") — #446's action layer consumes `furniture_blocks` later.
- Furnishing Williams Hall (#538) — its empty spot list is the correct
  behavior here.
- Any change to `_pin_meeting_rendezvous`, `walkable_furniture.json`, the
  committed tmj, `collision_maze`, or the viewer.
- DECIDE_MAX_ENUM / room-location additions (unchanged 17/20).

## Verification

- **Geo unit tests** (`tools/geo/` suite): generator on a small synthetic
  tmj fixture → expected maze cells + blocks rows (contiguous grouping,
  catalog names, `tile-<gid>` fallback, arena attribution); idempotent
  re-run byte-identical; on the real map: every nonzero `furniture_maze`
  cell sits on a `*_furniture` layer cell, and the drift gate
  (`validate_tmj.py`) still passes.
- **Backend tests** (`godot-generative-agents/tests/`): on the real map —
  every derived spot is walkable and at-furniture; furnished arenas
  (Houston lobby, Van Pelt rooms) have non-empty spots; Williams has none;
  a routed agent's destination for a furnished stop IS a spot (walk the
  stepper and assert the settle tile); Williams routing byte-identical to
  today; `test_stepper_matches_simulate_prefix` stays green; scripted-
  meeting tests stay green.
- **Full suites** (`uv run pytest godot-generative-agents/tests/ -q` and
  `uv run pytest godot-generative-agents/tools/geo -q` if separate) +
  `uv run black .`.
- **User visual pass:** regenerate the overlay, open
  `tools/geo/out/upenn_furniture_debug.tmj` in Tiled, confirm labels/spots;
  then a live/baked run — Sofia settles at Houston furniture, Tanaka's
  Williams behavior unchanged.
