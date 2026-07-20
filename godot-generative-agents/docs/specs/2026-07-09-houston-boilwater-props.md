# Houston Hall Boil-Water Props: Sprites + game_object Tier (#466)

**Issue:** #466 · **Branch:** `feat/houston-objects-466` off `godot-ga-main`
(independent of PR #465 — no shared files) · **Review track:** godot-ga-main
(tools/geo + matrix + map data only).

## Goal

The boil-water props exist today only as engine Items (PR #465). Make three of
them — **sink, stove, pot** — (1) visible in the Godot viewer inside Houston
Hall and (2) addressable at the object tier, so
`UPenn:Houston Hall:lobby:{sink,stove,pot}` resolve to routable tiles. This is
the matrix half of #300, following the Fisher pipeline from PR #402 exactly.

Cups deliberately get **no sprite or address**: they are portable items, not
fixtures.

## Current state (verified)

- Houston Hall is sector **14**, carved and fully furnished: layers
  `houston_floor/walls/rugs/furniture` and the `houston_arenas` objectgroup
  exist in the committed `godot-generative-agents/godot/maps/upenn_core_urban.tmj`.
  The `lobby` arena is id **1014**.
- `game_object_maze.csv` has no Houston cells; `game_object_blocks.csv` has no
  Houston rows (Fisher only, ids 134000–134018).
- `tools/geo/add_game_objects.py` hardcodes `OBJECT_LAYER = "fisher_objects"`
  (line 32); id scheme is `100000 + sector*1000 + idx` → Houston ids **114000+**.
- The committed tmj is **Tiled-pretty**; the furnish scripts serialize
  **minified** (`json.dump(..., separators=(",", ":"))`) — so a script-driven
  tmj rewrite would reformat ~15k lines. Map edits must therefore be surgical.
- Candidate tiles in `tools/geo/furniture_catalog.json`: sink (bath sheet,
  col 6 row 1, 1×2, `verified: true`), stove (franuka, col 8 row 24, 3×2,
  `verified: false`), pot (franuka, col 24 row 14, 1×1, `verified: false`).

## Design

### 1. Verify the tiles visually first

Crop the relevant regions of `interior_bath.png` / `interior_franuka.png` and
visually confirm the stove and pot candidates actually read as a stove and a
pot. If one doesn't, pick an alternative from the wired tilesets and use it
instead. Flip the chosen entries to `verified: true` in
`furniture_catalog.json` and record the final GIDs in the implementation plan.

### 2. Surgical tmj edit (the only map-file change)

One commit-worthy diff to `upenn_core_urban.tmj`, made by string-level edits
that preserve the Tiled-pretty formatting everywhere else (a `.bak` copy is
taken first, per the backup_tmj convention):

- **Sprites:** write the prop GIDs into the existing `houston_furniture`
  layer's `data` line — in-place integer swaps at computed indices, no JSON
  reserialization of the file. Placement: a kitchen corner of the lobby
  (arena 1014), sprites wall-adjacent, with open walkable floor in front, not
  blocking any doorway. The pot sits on/beside the stove.
- **Objects:** insert a new `houston_objects` objectgroup containing exactly
  three named rectangles — `sink`, `stove`, `pot` — each rect covering the
  walkable **use-tile(s)** on the floor in front of (not on) its sprite,
  matching the `fisher_objects` convention. Bump the top-level `nextlayerid`
  and `nextobjectid` so the file stays valid for Tiled.

### 3. Generalize `add_game_objects.py`

Replace the hardcoded `OBJECT_LAYER = "fisher_objects"` with a scan of **all**
objectgroup layers whose names end in `_objects`, so one idempotent invocation
covers Fisher + Houston (and future buildings). Hard constraint: after the
generalized run, the existing Fisher rows in `game_object_blocks.csv` and
Fisher cells in `game_object_maze.csv` are **byte-identical** (id stability —
`idx` enumerates per building/layer, and PR #402 pinned byte-for-byte matrix
reproduction).

### 4. Regenerate the script-owned CSVs

In pipeline order (these files are script output; regen diffs are expected):

1. `block_furniture.py` — seals the new prop sprite tiles into
   `collision_maze.csv` (additive; the allowlist is untouched, props are solid).
2. `add_game_objects.py` (generalized) — paints `game_object_maze.csv` cells,
   appends the three Houston rows (`114000+, "UPenn", "Houston Hall", "lobby",
   name`) to `game_object_blocks.csv`, and re-opens each use-tile in
   `collision_maze.csv`.
3. `validate_tmj.py` — all checks green, including the four object checks
   (orphans both directions, use-tiles walkable, single-arena containment,
   BFS reachability).

### 5. Address-resolution test

A new pytest pins that `WorldMap` (`backend/world_map.py`) resolves all three
4-tier addresses: `UPenn:Houston Hall:lobby:sink|stove|pot` each map to at
least one tile in `address_tiles`, and each such tile is walkable
(collision 0) — i.e. the address is routable. Lives with the existing
matrix-consistency tests (same home as `test_add_game_objects.py`'s suite),
plus a case covering the multi-layer scan itself (a synthetic second
`*_objects` layer alongside a `fisher_objects`-style one).

## Non-goals

- No routing change for Sofia's dinner stop (her stop's YAML lives on PR #465;
  pointing it at `UPenn:Houston Hall:lobby:sink` is a small follow-up after
  both PRs merge).
- No cup sprites/addresses, no other buildings, no viewer code, no backend
  Python behavior changes (`WorldMap` picks up the new CSV rows through its
  existing loader).
- No committed replay artifact (the bake stays git-ignored, regenerated per
  checkout).

## Acceptance (from #466)

1. `validate_tmj.py` fully green; `./godot-generative-agents/run_smoke_test.sh`
   exits 0; collision changes are exactly the deliberate seal/re-open deltas.
2. The three 4-tier addresses resolve to routable tiles (pinned by the new test).
3. A locally baked replay (`LLM_PROVIDER=mock … generate_penn_replay.py`)
   shows the props in Houston Hall — manual eyeball, artifact not committed.
