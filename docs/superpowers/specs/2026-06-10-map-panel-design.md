# Map Panel — Real City Map + Markers + Live Player Tracker (Sub-project 1)

**Date:** 2026-06-10
**Status:** Approved design, ready for implementation plan
**Context:** This is **sub-project 1** of a staged "whole city walkable" effort. Sub-project 2 (the
walkable whole-city world: ground render, collision/traversal, follow camera, re-anchored streetscape
and agent beat-positions) is deferred to its own spec → plan → build cycle.

## Goal

Replace the `DistrictMap` panel's abstract district-rectangle rendering with the real
`tingen_map.png` city map, overlaid with live risk-tinted district regions, point markers for the key
sites (warehouse rite-site, cathedral, harbor, market, Iron Cross), and a **live player-position
tracker** — all on a map-anchored coordinate layer that leaves the current streetscape untouched.

## Current State

- **`tingen/src/DistrictMap.gd`** (modal, toggled with **M**): loads the 5 districts from
  `districts.json` and draws each as a flat polygon tinted green→red by live "risk"
  (`base_risk` blended with its citywide pressure). Hover → risk readout. **No map image, no player
  marker.** Risk math: `clampf(base + pressure*(1-base), 0, 1)` where `pressure = WorldState.get_pressure(risk_pressure)/100`.
- **`asset-gen/ref/tingen_map.png`** — 1000×706, a vintage-style whole-city street map (organic street
  grid, a river down the **east** side, parks, inset regional locator, legend + scale). It carries no
  LotM location labels; ours are overlaid. It lives **outside** the Godot `res://` tree.
- **`districts.json`** — 5 districts, each `{id, name, base_risk, risk_pressure, polygon}`. The
  `polygon` coords are an **abstract** layout (e.g. Harbor is placed *west*, conflicting with the map's
  *east* river) and were never traced from the reference map.
- **`AgentRuntime.player_position`** — already updated every frame by `LiveDistrict` (and set to
  `player_start` on spawn). This is the live source for the tracker.

## Design

### Coordinate spaces

Three spaces, two pure transforms:

1. **World space** — the streetscape coordinates the player and agents already live in (player starts
   at `(440,300)`, rite site at `(420,360)`).
2. **Map-image space** — `tingen_map.png` pixels, `MAP_SIZE = (1000, 706)`. This is the canonical
   anchor space: district `map_polygon`s and the player tracker are all expressed here.
3. **Canvas space** — the panel's Map control pixels (depends on runtime control size).

- `world_to_map(world_pos) → Vector2` — the Iron Cross streetscape occupies `STREETSCAPE_SOURCE`
  (a world-space rect); it maps linearly onto `IRON_CROSS_DEST` (a map-image-space rect = the Iron
  Cross region on the map). `world_to_map(p) = DEST.position + (p - SOURCE.position) / SOURCE.size * DEST.size`.
- `image_to_canvas(canvas_size, p) → Vector2` — **aspect-preserving** fit of map-image space into the
  canvas: uniform `scale = min(canvas.x/MAP_SIZE.x, canvas.y/MAP_SIZE.y)`, centered with an offset, so
  the map art is never distorted and every overlay stays aligned to it. `canvas_to_image` is its inverse
  (used for hover hit-testing).

Initial constants (concrete, **tuned live** once visible in-game via **M**):
- `MAP_SIZE = Vector2(1000, 706)`
- `STREETSCAPE_SOURCE = Rect2(120, 140, 660, 460)`  (world x∈[120,780], y∈[140,600])
- `IRON_CROSS_DEST = Rect2(430, 300, 170, 140)`  (map-image rect for the Iron Cross 铁十字街 region)
- `WAREHOUSE_WORLD = Vector2(420, 360)`  (the rite/降临 site; its map marker = `world_to_map(WAREHOUSE_WORLD)`)

### Components / file structure

- **NEW `tingen/src/MapProjection.gd`** (`class_name MapProjection`, `extends RefCounted`) — pure,
  static, node-free coordinate math: `world_to_map`, `image_to_canvas`, `canvas_to_image`, and the
  constants above. This is the headless-testable seam (mirrors the `EndGameResolver` pattern). No
  rendering, no scene-tree dependency.
- **NEW `tingen/assets/maps/tingen_map.png`** — copied from `asset-gen/ref/tingen_map.png` into the
  `res://` tree so Godot can import it as a texture (`+ .import`). The panel loads
  `res://assets/maps/tingen_map.png`.
- **MODIFY `tingen/data/districts.json`** — add a `"map_polygon": [x,y, x,y, …]` (map-image-space
  coords) to each of the 5 districts, *alongside* the existing `polygon`. The old `polygon` keeps
  driving the streetscape; `base_risk`/`risk_pressure` are untouched, so **risk values do not change**.
  Initial `map_polygon`s (quads, tuned live), placed against the map's real geography (river east):
  - `iron_cross`     → `[430,300, 600,300, 600,440, 430,440]`
  - `st_selena`      → `[610,150, 770,150, 770,300, 610,300]`  (cathedral, prominent NE)
  - `harbor`         → `[680,440, 860,440, 860,620, 680,620]`  (east riverfront — corrected from west)
  - `night_market`   → `[380,470, 560,470, 560,630, 380,630]`  (dense S-center)
  - `uptown`         → `[690,300, 850,300, 850,430, 690,430]`  (Backlund Bridge Quarter, E near the bridge)
- **MODIFY `tingen/src/DistrictMap.gd`** — render pipeline (back-to-front) in `_draw_map`:
  1. `draw_texture_rect` the map texture into the aspect-fit rect (letterboxed; dim backdrop behind).
  2. Each district `map_polygon`, transformed by `image_to_canvas`, filled with its **live risk tint**
     at low alpha (map reads through), brighter on hover; name label at the polygon centroid.
  3. **Point markers**: a small dot at each district centroid (its name already comes from step 2) and
     the warehouse marker (`world_to_map(WAREHOUSE_WORLD)`) as a dot + "Rite Site" label — the one keyed
     site with no district region of its own. (Warehouse ≈ Iron Cross centroid by design — the rite is in
     Iron Cross; label offsets tuned live to avoid overlap.)
  4. **Player tracker**: `image_to_canvas(world_to_map(AgentRuntime.player_position))` → a bright,
     pulsing dot drawn last (on top).
  - Hover/readout: convert the mouse via `canvas_to_image`, hit-test against `map_polygon`s, keep the
    existing risk readout string.
  - **Live refresh**: while `visible`, `_process` calls `queue_redraw()` so the tracker follows the
    player. (Modal panel; redraw cost is trivial and only while open.)
- **MODIFY `tingen/ui/DistrictMap.tscn`** — expected unchanged (drawing stays immediate-mode on the
  existing `$Center/Frame/VBox/Map` control); noted in case the Map control needs a min-size/expand tweak
  so the 1.416:1 map has room.
- **MODIFY `tingen/tests/run_tests.gd`** — new headless tests (see Testing).

### Testing (TDD)

Pure seams first (`MapProjection`), then data integrity:
- `world_to_map`: `STREETSCAPE_SOURCE` corners map to `IRON_CROSS_DEST` corners exactly; source center
  → dest center; `player_start (440,300)` and `WAREHOUSE_WORLD (420,360)` land inside `IRON_CROSS_DEST`.
- `image_to_canvas`: aspect-preserving (uniform scale); image origin maps to the fit offset; the
  `MAP_SIZE` corner stays within the canvas; `canvas_to_image(image_to_canvas(p)) ≈ p` (round-trip).
- Data integrity: every district in `districts.json` has a `map_polygon` with an even length ≥ 6, all
  vertices within `[0,1000]×[0,706]`; the 5 expected ids are present; `base_risk`/`risk_pressure` still
  parse (risk model unbroken).
- Rendering stays a thin view layer over these tested transforms/data — not unit-tested directly.

## Honest limitation (consequence of staging)

Until sub-project 2 makes the city walkable, the **player dot only moves within the Iron Cross region**
of the map — that is the only area currently walkable. The tracker is real; its range is one district
until the world expands.

## Out of scope (→ sub-project 2)

Walkable whole-city world, ground rendering at city scale, collision/traversal tracing, following/zoomed
camera, rebuilding the `LiveDistrict` streetscape, and re-anchoring agent beat-positions into map space.

## Design decisions & rejected alternatives

- **Isolated map-anchor layer (additive `map_polygon` + pure transforms), streetscape left as-is.**
  *Alts (rejected):* (a) fully unify world/agent coordinates into map space now — that is sub-project 2's
  job; pulling it forward bloats the slice and re-risks the streetscape for no panel-side benefit.
  (b) Display the existing abstract `polygon`s over the map image unchanged — they'd land on the wrong
  geography (Harbor over dry land, not the east river), defeating "locations built in regard to the map."
- **Pure `MapProjection` (`class_name`, RefCounted) owns the coordinate math; the panel is a thin view.**
  *Alts (rejected):* keep the math inside `DistrictMap.gd` — its `@onready` scene refs make it
  node-bound and awkward to test headlessly; the `EndGameResolver` precedent (pure seam under a thin
  shell) is the house pattern.
- **Aspect-preserving fit (letterbox), one transform shared by art + every overlay.**
  *Alts (rejected):* stretch-to-fill the control — distorts the map and silently misaligns markers when
  the panel's aspect ≠ 1.416:1.
- **Warehouse marker derived via `world_to_map(WAREHOUSE_WORLD)`; district markers at polygon centroids;
    no new landmark data file.** *Alts (rejected):* a separate `landmarks.json` — YAGNI for v1, since the
  warehouse is derivable (and stays automatically consistent with the player dot's coordinate system)
  and the four district focal points come free from their regions.
- **Copy `tingen_map.png` into `res://assets/maps/`.** *Alts (rejected):* reference it in
  `asset-gen/ref/` — outside the Godot project tree, so it cannot be imported/loaded as a texture.
- **Keep the live risk tint as a translucent overlay (the "Threat + navigation" choice).**
  *Alts (rejected):* drop risk for a clean nav map — loses the at-a-glance "where is the night going
  wrong" read the panel exists to provide.
