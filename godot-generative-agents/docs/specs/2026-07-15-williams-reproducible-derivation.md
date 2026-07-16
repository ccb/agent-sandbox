# Spec: Williams Hall — reproducible derivation (issue #552)

**Track:** godot-ga-main (geo). Companion to #538 / #553.
**Date:** 2026-07-15

## Problem

Issue #552 was filed (during #538) as a small "the door constant drifted" fix:
`add_entrances.WILLIAMS_DOOR_X` is `(43, 44)` (the real south gap, corrected in
#538) but `furnish_building.SOUTH_DOOR_X` is still the stale `(40, 41)`. The issue
asked to either re-run `furnish_building` with the corrected constant, or at least
unify the two so they can't drift.

Investigating it surfaced a bigger, better goal (confirmed with the issue owner):
**make the Williams pipeline reproducible** — running the scripts should regenerate
what is checked in, so the map is not a hand-tended artifact no tool can rebuild.

## What was measured (all on copies; nothing in the tree was touched)

1. **Re-running `furnish_building.py` today is destructive and wrong.** It
   `strip_previous`-es *every* `williams_*` layer and only re-inserts
   `williams_floor` + `williams_furniture` — so it **deletes** the `williams_walls`
   and `williams_arenas` layers #538 added. It also `json.dump`s the whole `.tmj`
   *minified* (the committed map is Tiled-pretty), and it carves the south gap at
   the stale `(40, 41)` instead of `(43, 44)`.

2. **The committed Williams art is not `furnish_building` output at all.** Diffing
   the committed `williams_floor`/`williams_furniture` against what the current
   generator produces: **1424** floor cells differ (committed = 1445 painted cells
   of a uniform floor gid 621; generator = 473 cells of a *different* floor gid with
   walls baked in) and **256** furniture cells differ. #538 changed the layer model
   (walls relayered off the floor onto `williams_walls`; floor unified to gid 621)
   and the furniture is hand-tuned. The art is **authored**, not generated.

3. **The *derivation* is already byte-for-byte reproducible.** On a copy of the
   committed inputs:
   - `furnish_williams.py` reproduces the Williams tmj layers **whole-file
     byte-identical** (`williams_walls` 0 differing cells, `williams_arenas`
     identical, layer ids preserved — thanks to #553's format-preserving splice).
   - The matrix chain `add_entrances` → `block_grass` → `block_furniture` →
     `gen_furniture_matrix` reproduces **every** matrix CSV byte-identically.

So reproducibility already *holds* for Williams. It is simply **undocumented,
untested, and flanked by two footguns.**

## Model (the definition of "reproducible" we build to — Option 1)

The repo has migrated to an **authored-art + script-derivation** model: 10 of the
11 `furnish_*` scripts read an authored `*_arenas`/`*_objects` object layer; only
the legacy `furnish_building.py` paints everything from code. Williams now follows
the house pattern.

- **Authored inputs** (edited in Tiled, checked in, never regenerated):
  `williams_floor`, `williams_furniture`, `williams_arenas`.
- **Derived artifacts** (regenerated deterministically from those inputs, must be
  byte-identical): the `williams_walls` tmj layer, and the Williams cells of
  `collision_maze` / `arena_maze` / `arena_blocks` / `furniture_maze` /
  `furniture_blocks` / `furniture_spots`.

"Reproducible" = *from the committed authored inputs, re-running the derivation
regenerates the derived artifacts byte-identically.* Regenerating the **art** is
explicitly a non-goal (it is hand-made).

## Design

Five changes, ordered from most to least behavioral.

### 1. Make `williams_arenas` a true authored input (the one behavior change)

`furnish_williams.apply_to_file` currently strips `williams_arenas` and re-inserts
it from the Python constant `WILLIAMS_ARENA_OBJECTS` (reusing only the existing
ids). Byte-identity holds today *only because that constant happens to match the
Tiled tweaks*; editing the arenas in Tiled and re-running would silently revert
them. Under the authored-input model the tmj object layer is the source of truth.

- When a `williams_arenas` object layer **exists** in the tmj, re-emit it from the
  layer's own objects (source of truth), not from `WILLIAMS_ARENA_OBJECTS`.
- Keep `WILLIAMS_ARENA_OBJECTS` only as a **seed-if-absent** fallback for a fresh
  bake that has no arenas layer yet (document it as such).
- This is symmetric with `williams_walls`, which already self-seeds from the
  existing layer (line ~98–99). **Byte-output is unchanged today** (existing ==
  constant), so the round-trip test still passes.

### 2. Single-source the south door at cols 43–44

`furnish_building.SOUTH_DOOR_X` and `add_entrances.WILLIAMS_DOOR_X` must not be able
to disagree. `add_entrances` already `import furnish_building as fb`, so make
`furnish_building` own the canonical value and have `add_entrances` reference it
(`WILLIAMS_DOOR_X = fb.SOUTH_DOOR_X`), with `SOUTH_DOOR_X` corrected to `(43, 44)`.
This is safe: the door constant only affects `furnish_building`'s (now-guarded)
repaint path and window-skipping, so correcting it changes no committed bytes.

### 3. Guard `furnish_building`'s Williams re-run (hard refuse)

`furnish_building.py` is Williams-specific (`ROOMS` = Williams' rooms) and
superseded. Its CLI must **refuse** to repaint Williams with a message pointing at
`furnish_williams.py`, so it can never clobber the authored layers or minify the
map. The module stays importable — `furnish_williams` and `add_entrances` depend on
its `WALL` / `WINDOW` / `FLOOR` palette constants and splice helpers, so only the
`main()` write path is gated, not the library. No `--force-legacy` escape hatch (it
would only ever re-enable the destructive path).

### 4. Document authored-vs-derived + fix the run order

In `tools/geo/README.md`:
- Add `furnish_williams.py` to the Williams run order (it is currently absent),
  placed **before** `add_entrances.py` (which reads `williams_walls`/`arenas`).
- State plainly which `williams_*` layers are authored inputs vs derived artifacts.
- Note the `add_entrances`/`gen_furniture_matrix` tmj-minify caveat and that it does
  **not** touch the Williams layers (only the matrices + other buildings'
  `entrance_floor`), so Williams reproducibility is unaffected by it.
- Mark `furnish_building.py` as the legacy generator, retained as a palette/splice
  library, not to be run for Williams.

### 5. Round-trip regression test

Add a test (under `tools/geo/`, alongside `test_furnish_williams.py`) that locks in
what was measured, so it can't silently regress:
- Copy the committed `.tmj`, run `furnish_williams` on it, assert the resulting
  `williams_walls` data and `williams_arenas` objects are **byte-identical** to the
  committed layers (and ids preserved).
- Copy the committed matrix dir + tmj, run the matrix chain (`add_entrances` →
  `block_grass` → `block_furniture` → `gen_furniture_matrix`) pointed at the copies,
  assert the six Williams-touching matrix CSVs are byte-identical to the committed
  ones.
- Keep it hermetic and fast: operate on temp copies, never the tree; if the full
  matrix chain is too slow for CI, scope the assertion to the Williams sector cells.

## Out of scope

- Regenerating the Williams **art** (floor/furniture) from code — it is authored.
- Making `add_entrances`/`gen_furniture_matrix` write the tmj format-preservingly
  (a cross-building concern affecting every `entrance_floor` building — separate
  issue if wanted). Williams' tmj is untouched by those scripts, so this does not
  block #552.
- The furniture-alignment cosmetics from the original #552 text (reception desk ~3
  tiles off) — the art is authored; nudge it in Tiled if desired, out of scope here.
- Any other building.

## Verification

- New round-trip test passes.
- `validate_tmj` 0 errors; existing `pytest tools/geo/` green; `black` clean.
- Manual: `furnish_building.py` (no args) exits non-zero with the refusal message;
  `furnish_building.py` still imports cleanly (constants/helpers intact).
- Headless smoke test still loads Williams.
- `git diff` on the tree after running the documented pipeline shows **no** change
  to `williams_*` layers or the Williams matrix cells.

## Risks

- **Silent constant/layer divergence (mitigated):** change #1 makes the tmj layer
  authoritative so Tiled edits win; the constant is fallback-only.
- **Guard breaks an unknown caller (low):** `furnish_building` is Williams-only and
  absent from any automated pipeline except the README's manual steps; the library
  import path is untouched.
- **Test flakiness on the slow matrix chain (mitigated):** operate on temp copies,
  scope to Williams cells if needed.
