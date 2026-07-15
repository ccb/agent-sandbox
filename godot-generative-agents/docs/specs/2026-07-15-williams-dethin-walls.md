# Spec: Williams Hall — de-thin the double walls (issue #572)

**Track:** godot-ga-main (geo). Builds on #571 (#552); companion to #538.
**Date:** 2026-07-15

## Problem

Williams Hall's interior renders with **parallel double walls** — 2-cell-thick wall
runs where the repo's other furnished buildings are 1-thick. Measured on the
committed `williams_walls` layer: **84** 2×2 windows are fully solid (wall+window),
**40** are fully `wall_brick`. Concretely doubled: the south perimeter (rows 256
*and* 257), the right perimeter (cols 66–67), the lower-left perimeter (cols
12–13), and interior room borders. The doubling is baked into the authored art —
it came from the original `furnish_building` generator (which painted room-divider
borders *and* the footprint perimeter) and #538's relayer faithfully carried it onto
`williams_walls`. Unlike `furnish_houston`/`furnish_irvine`/`furnish_college_hall`
(which each de-thin with a "drop a wall until no 2×2 has 4" pass + a test),
`furnish_williams` has no such pass — it's a relayer over authored art, not a
partition generator.

## Why not just run the sibling 2×2 rule

Prototyped. The blind 2×2 rule on Williams' *hand-tuned, irregular* walls produces a
**ragged** result: stray inner-row bumps, a silhouette that shifts a column, and
1-cell holes punched mid-run. The sibling buildings avoid this only because they
de-thin *clean generated rectangles* before the art is hand-tuned. A clean result on
Williams needs aesthetic judgment, which belongs to the map owner.

## Approach (decided): one-time authored-art cleanup, human-in-the-loop

`williams_walls` is effectively authored input (per #571 it self-seeds through
`furnish_williams.compute_relayer`, so whatever is committed round-trips unchanged).
The owner edits it in Tiled; the tooling re-derives everything downstream.

**Collision safety (key insight):** the building's exterior seal is produced by
`add_entrances`' footprint-based perimeter carve — *independent* of the
`williams_walls` tiles (`add_entrances` seals the interior subset of the wall cells;
the main carve loop seals the perimeter from the matrix footprint). So thinning wall
*tiles* is a visual change with benign collision effects: a dropped cell in a 2-thick
run simply becomes walkable interior. The invariants to preserve are therefore:
- keep **≥1 wall line** per run (never erase a whole wall),
- keep all **window** cells (46),
- keep the **door gap** at cols 43–44 open,
- keep the **outer silhouette** (erase the inner line, not the outer edge).

**Owner also resized the arenas.** In the same Tiled pass the owner adjusted the
`williams_arenas` object layer to match the de-thinned room boundaries. This is
supported *because of* #571: `furnish_williams._arena_objects` now reads the arenas
from the tmj layer (the constant is fallback-only), so the resized rooms are the
source of truth and reproduce. It means the **arena matrices** (`arena_maze`,
`arena_blocks`) change too, and the `grouped_sections` view still resolves to the
five rooms (Lobby\* dropped, `Classroom B 1/2` merged).

**Format normalization (discovered).** Tiled writes the arenas objectgroup in a
slightly different whitespace style than `furnish_williams._object_layer_block` (e.g.
`}, ` with a trailing space; the objects array closed inline as `}]`). So a raw Tiled
save is *not* byte-identical to what `furnish_williams` would re-emit, which would
break #571's round-trip test. Resolution: `furnish_williams` is the **canonical
writer** of `williams_walls` + `williams_arenas`; run it once after the Tiled edit to
normalize the format, and commit *that*. Verified: the normalized tmj is
formatting-only vs the Tiled save (all `williams_*` tile data identical, arenas
identical by name+geometry) and it **self-reproduces byte-identically**, so the
round-trip test stays green.

## Workflow

1. **Guide (tooling).** Generate an annotated map of the current `williams_walls`:
   each cell marked keep-wall / suggested-erase / window, plus a per-region list of
   suggested erase coordinates that favors keeping the outer silhouette. The suggested
   set is a *starting point* — the owner refines for clean, continuous 1-thick lines.
   Artifact: `godot-generative-agents/tools/geo/out/williams_dethin_guide.txt` (+ a PNG
   for visual reference). This is a work aid, not committed product. *(Done.)*
2. **Edit (owner, in Tiled).** Erase the redundant inner line on `williams_walls`
   (honoring the four invariants above) and resize `williams_arenas` to match. Save.
   *(Done — verified: 340→263 wall cells, all-wall 2×2 40→0, windows + door gap
   preserved, only `williams_walls`/`williams_arenas` changed.)*
3. **Normalize + re-derive + test (tooling).**
   - **Normalize:** run `furnish_williams` on the edited tmj to re-emit
     `williams_walls`/`williams_arenas` in the canonical splice format; commit that
     tmj (Tiled-pretty, format-preserving). Verify it is formatting-only vs the Tiled
     save (tile data + arena geometry unchanged).
   - **Re-derive matrices:** run the matrix chain (`add_entrances` → `block_grass` →
     `block_furniture` → `gen_furniture_matrix`) on a *copy*; commit only the
     regenerated **matrix CSVs** (`collision_maze`, `arena_maze`, `arena_blocks`,
     `furniture_maze`, `furniture_blocks`, `furniture_spots`). **Never commit the
     minified tmj** those scripts write.
   - **Reproducibility:** confirm #571's round-trip test stays green on the committed
     (normalized) tmj — `furnish_williams` reproduces it byte-identically and the
     matrix chain reproduces the CSVs.
   - **New regression test:** assert **no 2×2 window in `williams_walls` is fully
     `wall_brick`** (mirroring the sibling buildings' tests).
   - **Tidy the constant:** update `WILLIAMS_ARENA_OBJECTS` to match the new committed
     arenas. It is fallback-only (no effect on committed output, since the layer is
     read), but a stale constant would seed the wrong rooms on a fresh bake.

## Deliverables (this issue's tooling)

- The committed tmj: the owner's edit, normalized through `furnish_williams` (cleaned
  `williams_walls` + resized `williams_arenas`).
- Regenerated matrix CSVs reflecting the cleaned walls + resized rooms (collision +
  arena + furniture).
- New test: `williams_walls` has zero all-`wall_brick` 2×2 windows. If a sibling
  furnisher already exposes a 2×2-check helper, reuse it rather than duplicating.
- `WILLIAMS_ARENA_OBJECTS` updated to match the new committed arenas (fallback-only,
  no effect on committed output).
- `furnish_williams`'s relayer/splice logic is otherwise unchanged — it already
  self-seeds the authored walls + reads the authored arenas (#571).

## Out of scope

- An algorithmic thinning pass in `furnish_williams` (rejected above — ragged on
  hand-art; the owner edits instead).
- Any other building; furniture or arena changes; the door position (#552 fixed it).
- Regenerating the tmj format (the owner's Tiled save is the source of the pretty tmj;
  the derivation scripts minify and must not have their tmj output committed).

## Verification

- New no-2×2 test passes; #571 round-trip test still green; full `pytest
  tools/geo/` green; `black` clean.
- `validate_tmj` 0 errors (catches an accidentally-unsealed perimeter / stray tile).
- Headless smoke test loads Williams; the building is still enclosed (agents can only
  exit via the 43–44 door) and all 5 rooms remain reachable — check the regenerated
  `arena_maze`/`collision_maze` the same way #538's `test_williams_arenas` does.
- Visual: walls render 1-thick in the viewer, windows intact, no gaps in wall lines.
- The committed (normalized) tmj self-reproduces: re-running `furnish_williams` on it
  leaves it byte-identical.
- `git status` shows changes only to the normalized tmj + the six matrix CSVs + the
  new test + the `WILLIAMS_ARENA_OBJECTS` constant — no unrelated files, no minified
  tmj (the committed tmj stays Tiled-pretty).

## Risks

- **Owner edit breaks the seal / leaves a hole (mitigated):** the guide marks ≥1-line
  minimums and the door gap; collision's exterior seal is footprint-based and
  independent; `validate_tmj` + the reachability check catch a bad edit before merge.
- **Ragged result (mitigated):** the guide's suggested erase set favors the outer
  silhouette; the owner refines for continuity.
- **Accidental minified-tmj commit (mitigated):** re-derive matrices on a copy; commit
  only CSVs; the verification step greps for a minified committed tmj.

## Dependency

Branches off #571 (`feat/williams-repro-552`) — same file/tests, and relies on #571's
authored-input model + round-trip test. Rebase onto `godot-ga-main` if #571 merges
first.
