# To-Scale Walkable City World — Design Spec

**Date:** 2026-06-15
**Sub-project:** 2 (follows the Map Panel sub-project)
**Branch:** `feature/city-world`
**Status:** Approved design, pending spec review

---

## 1. Problem

The map panel (`tingen_map.png`, 1000×706 px) shows a full vintage city — dense street
grid, a river/harbor down the east side, five districts, and landmarks (cathedral,
bridge, the Iron Cross Street / 铁十字街 rite site). But the **playable Godot world**
(`LiveDistrict.gd`) is a small procedural patch (~660×460 world units of ground, two
crossing roads, one warehouse block) that occupies the footprint of *only the Iron Cross
district*. The other four districts have no walkable geometry.

Worse, the two spaces are authored independently with **no shared transform**:

- District **world** `polygon`s live in arbitrary world units.
- District **map** `map_polygon`s live in map-image pixels.
- `MapProjection.world_to_map()` only remaps a hardcoded streetscape rect
  (`STREETSCAPE_SOURCE = Rect2(120,140,660,460)`) onto the Iron Cross destination rect
  (`IRON_CROSS_DEST = Rect2(430,300,170,140)`).

So the player's blip on the map is only meaningful inside Iron Cross, and the world the
player walks does not resemble the map at all.

**Goal:** Rebuild the playable Godot world so it is *true to the map* — same scale,
dimensions, locations — for the whole city, with full collision and navmesh-driven NPC
pathfinding.

## 2. Core idea: one global transform

Make the **map-image space the single canonical authoring space** and connect it to world
space with one uniform linear transform:

```
CITY_SCALE = 3.5
map_to_world(p) = p * CITY_SCALE
world_to_map(w) = w / CITY_SCALE
```

- The map is 1000×706 px → the world becomes **(0,0) → (3500, 2471)** world units.
- `CITY_SCALE = 3.5` keeps the *current* feel: Iron Cross today is ~170×140 map px of
  destination; at ×3.5 a district reads at a human walking scale (player speed 120 u/s →
  ~29 s to cross the full 3500-unit city, a believable district-to-district walk).
- Because the transform is global and uniform, **the map blip is accurate everywhere**,
  not just Iron Cross. `DistrictMap.gd` keeps calling
  `MapProjection.image_to_canvas(world_to_map(player_position))` unchanged and it Just
  Works city-wide.

This replaces the Iron-Cross-only remap. `STREETSCAPE_SOURCE` and `IRON_CROSS_DEST` are
removed; `image_to_canvas` / `canvas_to_image` (the aspect-fit letterbox used by the map
panel) are **untouched**.

## 3. Architecture & components

```
data/city_layout.json   (NEW)  ── map-pixel space authoring data
        │
        ▼
src/CityLayout.gd       (NEW)  ── pure RefCounted loader; parses JSON,
        │                          applies ×CITY_SCALE, returns world-space features
        ▼
src/LiveDistrict.gd  (REWRITE) ── consumes CityLayout; builds, per feature:
        │                            • Polygon2D     (visual fill)
        │                            • StaticBody2D + CollisionPolygon2D (solid)
        │                          + city-edge boundary collider
        │                          + NavigationRegion2D (streets = walkable)
        │                          + Sprite2D map underlay (toggle)
        │                          + bounded Camera2D
        ▼
src/MapProjection.gd (MODIFY)  ── global map_to_world / world_to_map
src/NPC.gd           (MODIFY)  ── NavigationAgent2D pathing
data/npcs.json       (MODIFY)  ── waypoints rescaled into new world space
```

### 3.1 Data — `data/city_layout.json` (new)

Authored in **map-pixel space** (so it can be traced directly against `tingen_map.png`):

- `city_outline`: `[x,y, x,y, …]` — the main map body polygon, **excluding the marginal
  insets/legend** (top-left cartouche, bottom-left regional inset, bottom-right legend +
  scale bar). Used for camera/world bounds and as the navmesh outer boundary.
- `water[]`: array of polygons for the river + harbor down the east side. Solid (blocks
  the player) and a navmesh hole.
- `blocks[]`: array of **many small building-mass polygons** — the blocks *between* the
  streets. These are true buildings, not placeholder mega-blocks. Solid + navmesh holes.
- `landmarks[]`: array of `{ "pos": [x,y], "label": "…" }` — rite site (降临 at Iron
  Cross), cathedral, bridge, market. Drives labels and re-anchors gameplay points.

Streets are **not** stored; they are the implicit walkable negative space between blocks
and water, inside `city_outline`.

`data/districts.json` is **kept as-is**; its `map_polygon` continues to drive district
tints, labels, and risk. (Its world-space `polygon` becomes vestigial for rendering but
is left in place to avoid churn; nothing in the new builder reads it.)

### 3.2 Loader — `src/CityLayout.gd` (new)

`class_name CityLayout extends RefCounted`, pure + static, mirroring `MapProjection` /
`EndGameResolver`. Responsibilities:

- Load + parse `data/city_layout.json` (with a static method that accepts an
  already-parsed `Dictionary` for headless testing — no file I/O in the seam).
- Convert each feature's flat `[x,y,…]` arrays into `PackedVector2Array`.
- Apply `MapProjection.map_to_world()` so callers receive **world-space** geometry.
- Expose typed getters: `outline()`, `water()`, `blocks()`, `landmarks()`.

This is the headless-testable seam; `LiveDistrict` is the thin Node that wires the result
into the scene tree.

### 3.3 World builder — `src/LiveDistrict.gd` (rewrite)

Replace the hand-built `_build_streetscape()` with a data-driven build:

1. **Map underlay** — `Sprite2D` of `tingen_map.png`, positioned/scaled to cover exactly
   `(0,0)→(3500,2471)`, z-index behind everything. Visibility bound to a
   `show_map_underlay` flag (default **ON**, for tracing fidelity; flipped OFF later).
2. **Ground base** — a `Polygon2D` filling `city_outline` (world space) as the street/base
   color.
3. **District tints** — for each district, a translucent `Polygon2D` over its
   `map_polygon` (×3.5), same as today but city-wide.
4. **Water** — per `water[]` polygon: visual `Polygon2D` (water color) + `StaticBody2D` +
   `CollisionPolygon2D`.
5. **Blocks** — per `blocks[]` polygon: visual `Polygon2D` (building color) + `StaticBody2D`
   + `CollisionPolygon2D`.
6. **City-edge boundary** — a collider ringing `city_outline` so the player cannot walk off
   the map into the void.
7. **Landmark labels** — a `Label` at each landmark `pos` (×3.5).
8. **Navmesh** — see §3.4.
9. **Camera bounds** — set the player `Camera2D` `limit_left/top/right/bottom` to the city
   rect.

Player collides with all of the above via `move_and_slide` (already in `Player.gd`).

### 3.4 Navmesh — `NavigationRegion2D` (in scope)

- A `NavigationRegion2D` with a `NavigationPolygon` whose **outer outline = `city_outline`**
  and whose **holes = every block polygon + every water polygon** (all world space).
- Result: the streets (negative space) are the single connected walkable region.
- Bake headlessly (`NavigationPolygon` outline/hole API + `make_polygons_from_outlines`,
  or `NavigationServer2D` region baking), then assert baked area > 0.
- `NPC.gd` switches from straight-line steering to a `NavigationAgent2D`: it still receives
  the *same* goals from `AmbientSidecar` (cultists → 降临 warehouse; others → schedule
  waypoints), but now paths **around** buildings via
  `NavigationServer2D.map_get_path()` instead of walking through walls.

### 3.5 Re-anchoring gameplay points

Everything currently authored in the old ad-hoc world space is re-expressed through the
transform so it lands in the right *map* location:

- `player_start` — placed on a street near Iron Cross (was `(440,300)`).
- Warehouse / 降临 rite site — old `(420,360)` ≈ map `(507,367)` → new world ≈ `(1775,1285)`;
  but authoritatively it becomes a **landmark** in `city_layout.json` at the Iron Cross
  warehouse, transformed ×3.5.
- Sabotage point — re-anchored relative to the warehouse landmark.
- `data/npcs.json` waypoints — rescaled into the new world space (old coords were
  x∈[220,680], y∈[180,400]).

### 3.6 Camera

`Player.tscn` Camera2D gains `limit_left=0, limit_top=0, limit_right=3500,
limit_bottom=2471` (the city rect) so the view never shows past the city edge. Zoom/
smoothing unchanged.

## 4. Testing strategy (headless TDD)

All via the dependency-free `tests/run_tests.gd` runner. New/changed tests:

**MapProjection**
- `map_to_world` / `world_to_map` round-trip identity.
- Iron Cross `map_polygon` `[430,300,600,300,600,440,430,440]` → world rect
  `[1505,1050,2100,1050,2100,1540,1505,1540]` (595×490).
- Map corners `(0,0)` and `(1000,706)` → `(0,0)` and `(3500,2471)`.
- (Replace the old streetscape-remap assertions.)

**CityLayout**
- Loads a sample dict; returns world-space polygons (every vertex inside the
  `(0,0)→(3500,2471)` rect).
- Transform correctness: a known map-space vertex comes back ×3.5.

**Data integrity**
- `city_layout.json` parses; all block/water/outline vertices are within map bounds
  `(0,0)→(1000,706)`; arrays are even-length coordinate lists; ≥ 20 blocks present (a
  floor that proves "many small buildings," not a handful of mega-blocks).

**Navmesh**
- Baked navigation polygon area > 0.
- `NavigationServer2D.map_get_path()` between two street points on opposite sides of a
  known block returns a path that **bends** (more than 2 points / longer than the straight
  line) and does **not** cross the block — proves routing around obstacles.
- An NPC given a cross-street goal reaches it (path is non-empty and ends within
  `arrive_radius`).

**LiveDistrict (headless instantiation)**
- Scene instantiates headless; produces the expected number of block + water colliders
  (matches the data counts).
- `show_map_underlay` toggles the underlay `Sprite2D.visible`.
- Player is bounded: a body started inside and pushed toward the edge stays within the city
  rect (or the boundary collider exists with correct extents).

**Regression**
- All existing map-panel tests (DistrictMap, MapProjection panel-side) stay green.
- Smoke: `--headless --path tingen --quit-after 180` boots without errors.

Baseline before changes: **488 passed, 0 failed** (worktree, on 385cdd3).

## 5. Scope

**In:**
- Five districts rendered to scale across the full city.
- Water (river/harbor) + many small building blocks, each with visual + collision.
- Full player collision.
- Navmesh + NPC pathfinding around obstacles.
- Bounded camera.
- City-wide accurate map tracker.
- Map underlay with a toggle.

**Out:**
- Entering / interiors of buildings.
- New city-wide NPC content or schedules beyond rescaling existing ones.
- Any gameplay / risk / pressure-system changes.

## 6. Fidelity approach

First pass is **structured, not pixel-perfect**: lay out district-organized building
blocks, the east river/harbor, and the named landmarks in roughly correct map positions,
then **refine live against the underlay** (which is why the underlay defaults ON). Tests
assert *structure* (counts, bounds, transform correctness, routing behavior) — never exact
pixel coordinates — so live tuning never breaks the suite.

## 7. Build order

1. **Global transform** — `MapProjection` `CITY_SCALE` + `map_to_world` / `world_to_map`;
   update its tests; remove streetscape/Iron-Cross remap. (Tracker goes city-wide.)
2. **Layout loader + first-pass data** — `CityLayout.gd` + `city_layout.json` (traced
   against the underlay), with loader + data-integrity tests.
3. **World builder** — rewrite `LiveDistrict` to build visuals + collision from the loader,
   add the city-edge boundary, the map underlay + toggle, and camera bounds.
4. **Navmesh + NPC pathfinding** — `NavigationRegion2D` baked from outline−blocks−water;
   switch `NPC.gd` to `NavigationAgent2D`; re-anchor waypoints.
5. **Verify & tune** — run suite + smoke, tune block geometry live against the underlay,
   log decisions.

Each step ends green before the next begins.

## 8. Risks & mitigations

- **Navmesh baking API differences across Godot versions** → isolate baking behind a small
  helper; assert on area > 0 and on `map_get_path` behavior rather than on internal poly
  structure.
- **Tracing fidelity is tedious** → accept a structured first pass; refine live with the
  underlay ON; never gate the suite on pixel coordinates.
- **Performance with many small colliders** → blocks are static bodies (cheap); if needed,
  merge adjacent blocks per district. Re-evaluate only if the smoke run regresses.
- **NPC navmesh edge cases** (goal inside a building, agent stuck) → snap goals to the
  nearest navmesh point; keep `arrive_radius` tolerant.
- **Underlay/vector drift after underlay is hidden** → vectors are the source of truth for
  collision/nav; the underlay is only a tracing aid, so hiding it changes nothing
  functional.

## 9. Design decisions (for DESIGN_DECISIONS.md)

### Implementation notes — to-scale city world

- **Single global uniform transform (`CITY_SCALE = 3.5`), map-image space canonical.**
  *Alts (rejected):* (a) per-district piecewise remaps — keeps independent authoring, but
  the tracker stays locally-correct-only and seams appear at district borders; (b) author
  the world in world units and derive the map — inverts today's canonical source (the map
  art) and makes the panel the derived artifact, more churn. The uniform transform makes
  the existing `world_to_map` tracker correct city-wide for free.

- **`CITY_SCALE = 3.5` (match today's feel).**
  *Alts (rejected):* 1.0 (map px = world units) feels cramped — a district would be ~170
  units, crossed in ~1.4 s; larger (e.g. 7×) makes the city a long boring walk. 3.5 keeps
  the current Iron Cross district size and a ~29 s full-city traversal.

- **Data-driven `city_layout.json` + pure `CityLayout` loader.**
  *Alts (rejected):* hardcode geometry in `LiveDistrict` (current approach) — not
  headless-testable, mixes data with scene wiring; a Godot `TileMap` — overkill for
  polygonal building masses and harder to derive a navmesh from.

- **Many small building-mass blocks (true buildings).**
  *Alts (rejected):* a few large placeholder blocks — faster to author but reads as
  abstract zones, not a city, and produces a coarse navmesh with unrealistic detours.
  (User explicitly requested true small blocks.)

- **Navmesh in this run, NPCs via `NavigationAgent2D`.**
  *Alts (rejected):* defer navmesh and keep straight-line steering — NPCs would walk
  through the new buildings, immediately visibly broken. (User explicitly approved building
  the navmesh now.)

- **Map underlay default ON, with a toggle; hidden later.**
  *Alts (rejected):* no underlay — tracing blind against a separate window is error-prone;
  underlay permanently on — defeats the goal of a self-contained vector world. Default ON
  for tracing, flip OFF once geometry is faithful (per user: "do the underlay approach
  first, then hide it").

- **Full collision (water + every block) + city-edge boundary.**
  *Alts (rejected):* visual-only / no collision — player walks through buildings and off
  the map; collision on blocks only — player escapes off the city edge into the void.
