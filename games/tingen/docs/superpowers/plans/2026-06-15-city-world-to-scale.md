# To-Scale Walkable City World — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the playable Godot world so it is true to `tingen_map.png` — same scale, dimensions, and locations across the whole city — with full collision and navmesh-driven NPC pathfinding.

**Architecture:** Make map-image space the single canonical authoring space, linked to world space by one global uniform transform (`CITY_SCALE = 3.5`). Author the city (outline, water, building blocks, landmarks) in map pixels in `data/city_layout.json`; a pure `CityLayout` loader transforms it to world space; a rewritten `LiveDistrict` builds visuals + collision + a baked `NavigationRegion2D` from it; NPCs path around buildings via `NavigationAgent2D`. All gameplay anchor points (rite site, sabotage point, NPC waypoints) are re-expressed through the transform so the existing map tracker becomes accurate city-wide for free.

**Tech Stack:** Godot 4.6.3 / GDScript. Dependency-free headless `SceneTree` test runner (`tingen/tests/run_tests.gd`). Modern navmesh API (`NavigationMeshSourceGeometryData2D` + `NavigationServer2D.bake_from_source_geometry_data`) — no deprecated calls (pristine output required).

---

## Conventions for every task

**Godot binary (not on PATH):** `/Applications/Godot.app/Contents/MacOS/Godot`

**Run the full suite** (the runner has no single-test filter — run all, then read the new PASS/FAIL lines):
```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && /Applications/Godot.app/Contents/MacOS/Godot --headless --path tingen -s tests/run_tests.gd 2>&1 | tail -8
```
Green tail: `=== N passed, 0 failed, 0 skipped ===` and exit 0.

**Class-cache refresh** (REQUIRED once after introducing a new `class_name` script — otherwise the headless `-s` runner reports `Parse Error: Identifier "X" not declared`):
```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && timeout 150 /Applications/Godot.app/Contents/MacOS/Godot --headless --editor --quit --path tingen 2>&1 | tail -3
```

**Smoke run** (boots the real game loop headless):
```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && /Applications/Godot.app/Contents/MacOS/Godot --headless --path tingen --quit-after 180 2>&1 | tail -15
```

**Baseline before any change: `488 passed, 0 failed, 0 skipped`.**

**Notes on GDScript / this repo:**
- A `class_name X extends RefCounted` script is a *global class* — its statics are reachable from any other script at parse time (e.g. `MapProjection.map_to_world(...)`). This is **not** the autoload restriction; only `Autoload.` references break under the `-s` harness.
- `const` initializers **cannot** call static functions; use `static var` to compute a value from another global class's static method.
- Removing or renaming a `const` referenced elsewhere is a **parse error**, which prevents the *whole* suite from running. When a task removes a symbol, it must update every reader in the **same** task. The "RED" for such a change is the parse/identifier error; "GREEN" is the suite running clean again.
- Staging: stage only the files named in each commit step **by name**. Never `git add -A`/`git add .`. Never stage the untracked `*.uid` editor-import artifacts.
- Commit messages via heredoc (`cat <<'EOF'`) so apostrophes don't break the shell; end with the `Co-Authored-By` trailer.

---

## File Structure

**New files:**
- `tingen/data/city_layout.json` — map-pixel-space authoring data: `city_outline`, `water[]`, `blocks[]`, `landmarks[]`.
- `tingen/src/CityLayout.gd` — `class_name CityLayout extends RefCounted`. Pure loader: parses the JSON, applies `MapProjection.map_to_world`, returns world-space geometry. Also hosts the static `build_nav_polygon` helper.

**Modified files:**
- `tingen/src/MapProjection.gd` — replace the Iron-Cross-only remap with the global `CITY_SCALE` transform.
- `tingen/src/DistrictMap.gd` — line 105 rite-marker now derives from `MapProjection.WAREHOUSE_MAP` directly.
- `tingen/src/ActionCommit.gd` — `SITES` becomes a `static var` anchored to `map_to_world(WAREHOUSE_MAP)`.
- `tingen/src/AmbientSidecar.gd` — `WAREHOUSE` becomes a `static var` anchored the same way.
- `tingen/data/npcs.json` — schedule waypoints rescaled into the new world space.
- `tingen/src/LiveDistrict.gd` — full rewrite: data-driven visuals + collision + spawns + underlay + camera bounds + city-edge walls + navmesh.
- `tingen/src/NPC.gd` — `NavigationAgent2D` pathfinding (preserving `steer_goal()` / `is_bound()`).
- `tingen/scenes/NPC.tscn` — add a `NavigationAgent2D` child.
- `tingen/tests/run_tests.gd` — rewrite the map-projection test; extend the live-district test; add CityLayout / navmesh / underlay / camera / consistency tests; update the action-commit site reference.

**Kept as-is:** `tingen/data/districts.json` (its `map_polygon` still drives tints/labels/risk), `tingen/scenes/Player.tscn` (camera limits set at runtime), `tingen/scenes/LiveDistrict.tscn`.

---

## Canonical values (single source of truth — reuse, do not re-derive ad hoc)

| Thing | Map-pixel space | World space (×3.5) |
|---|---|---|
| `CITY_SCALE` | — | `3.5` |
| Map / world extent | `(0,0)–(1000,706)` | `(0,0)–(3500,2471)` |
| Warehouse / 降临 rite site (`WAREHOUSE_MAP`) | `(515, 372)` | `(1802.5, 1302.0)` |
| Iron Cross `map_polygon` top-left | `(430, 300)` | `(1505, 1050)` |
| `player_start` | `(470, 360)` | `(1645, 1260)` |
| `SABOTAGE_POINT` | `(505, 372)` | `(1767.5, 1302.0)` |
| `city_outline` | `[120,120, 900,120, 900,640, 120,640]` | `[420,420, 3150,420, 3150,2240, 420,2240]` |
| Camera limits / boundary | — | `left=0, top=0, right=3500, bottom=2471` |

---

## Task 1: MapProjection global transform

Replace the Iron-Cross-only `world_to_map` remap with a global uniform `CITY_SCALE` transform. Because removing `STREETSCAPE_SOURCE` / `IRON_CROSS_DEST` / `WAREHOUSE_WORLD` is a parse-breaking change, the test rewrite, the production rewrite, and the one downstream reader (`DistrictMap.gd:105`) all land in this task.

**Files:**
- Modify: `tingen/src/MapProjection.gd`
- Modify: `tingen/src/DistrictMap.gd:105`
- Test: `tingen/tests/run_tests.gd` (rewrite `_test_map_projection_world_to_map`, lines 1936–1953)

- [ ] **Step 1: Rewrite the test to assert the new transform**

Replace the entire `_test_map_projection_world_to_map` function (currently lines 1936–1953) with:

```gdscript
func _test_map_projection_world_to_map() -> void:
	print("[map projection global transform]")
	# Constants match the canonical map-image space (tingen_map.png is 1000x706).
	_ok(MapProjection.MAP_SIZE == Vector2(1000.0, 706.0), "MAP_SIZE is the tingen_map.png pixel size")
	_ok(MapProjection.CITY_SCALE == 3.5, "CITY_SCALE is 3.5")
	# Map corners map onto the world rect (0,0)..(3500,2471).
	_ok(MapProjection.map_to_world(Vector2.ZERO).is_equal_approx(Vector2.ZERO),
		"map origin -> world origin")
	_ok(MapProjection.map_to_world(MapProjection.MAP_SIZE).is_equal_approx(Vector2(3500.0, 2471.0)),
		"map far corner -> world far corner (3500,2471)")
	# Round-trip identity: world_to_map is the exact inverse of map_to_world.
	var p := Vector2(1234.0, 567.0)
	_ok(MapProjection.map_to_world(MapProjection.world_to_map(p)).is_equal_approx(p),
		"map_to_world(world_to_map(p)) == p")
	# The Iron Cross map_polygon top-left lands at the documented world rect corner.
	_ok(MapProjection.map_to_world(Vector2(430.0, 300.0)).is_equal_approx(Vector2(1505.0, 1050.0)),
		"Iron Cross map (430,300) -> world (1505,1050)")
	# The rite site anchor: WAREHOUSE_MAP sits inside the Iron Cross map_polygon and transforms cleanly.
	var ic := Rect2(430.0, 300.0, 170.0, 140.0)  # iron_cross map_polygon bounds
	_ok(ic.has_point(MapProjection.WAREHOUSE_MAP), "WAREHOUSE_MAP lands inside the Iron Cross region")
	_ok(MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP).is_equal_approx(Vector2(1802.5, 1302.0)),
		"WAREHOUSE_MAP -> world (1802.5,1302.0)")
```

- [ ] **Step 2: Run the suite — expect RED (identifier not declared)**

Run the full suite (command above). Expected: a parse/identifier error such as `Identifier "CITY_SCALE" not declared in the current scope` / `Invalid call ... map_to_world`, and a non-zero exit. The suite cannot run until MapProjection defines the new API. (If it *does* run, the test fails on the new assertions — also RED.)

- [ ] **Step 3: Rewrite MapProjection.gd**

Replace the whole file with:

```gdscript
class_name MapProjection
extends RefCounted
## Pure, static, node-free coordinate math. Three spaces:
##   • World space     — the streetscape coords the player/agents live in.
##   • Map-image space — tingen_map.png pixels (MAP_SIZE). The single canonical authoring space:
##     city_layout.json, district map_polygons, and the player tracker are all expressed here.
##   • Canvas space    — the map panel's Map control pixels (runtime-sized).
## ONE global uniform transform links world and map space (CITY_SCALE), so the map tracker is
## accurate everywhere, not just inside one district. image_to_canvas / canvas_to_image are the
## panel's aspect-fit letterbox and are independent of CITY_SCALE.

const MAP_SIZE := Vector2(1000.0, 706.0)
## World units per map pixel. The map (1000x706) becomes a (0,0)..(3500,2471) world. 3.5 keeps the
## established district feel: a full-city walk is ~29 s at the player's 120 u/s.
const CITY_SCALE := 3.5
## The 降临 / rite site in the canonical map-image space (inside the iron_cross map_polygon
## [430,300,600,440]). Its world position = map_to_world(WAREHOUSE_MAP); its map marker is itself.
const WAREHOUSE_MAP := Vector2(515.0, 372.0)

## Map-image space -> world space.
static func map_to_world(map_pos: Vector2) -> Vector2:
	return map_pos * CITY_SCALE

## World space -> map-image space (exact inverse of map_to_world).
static func world_to_map(world_pos: Vector2) -> Vector2:
	return world_pos / CITY_SCALE

## Map-image -> canvas: aspect-preserving (letterbox) fit of MAP_SIZE into canvas_size.
## Uniform scale, centered; never distorts the art, so every overlay stays aligned to it.
static func image_to_canvas(canvas_size: Vector2, p: Vector2) -> Vector2:
	var scale: float = minf(canvas_size.x / MAP_SIZE.x, canvas_size.y / MAP_SIZE.y)
	var offset: Vector2 = (canvas_size - MAP_SIZE * scale) * 0.5
	return offset + p * scale

## Canvas -> map-image: the exact inverse of image_to_canvas (for hover hit-testing).
## A zero/negative-size canvas (e.g. before first layout) has no valid inverse; pass the
## point through unchanged rather than dividing by zero into inf/nan.
static func canvas_to_image(canvas_size: Vector2, p: Vector2) -> Vector2:
	var scale: float = minf(canvas_size.x / MAP_SIZE.x, canvas_size.y / MAP_SIZE.y)
	if scale <= 0.0:
		return p
	var offset: Vector2 = (canvas_size - MAP_SIZE * scale) * 0.5
	return (p - offset) / scale
```

- [ ] **Step 4: Fix the one downstream reader (DistrictMap.gd:105)**

The rite marker was derived as `world_to_map(WAREHOUSE_WORLD)`; now `WAREHOUSE_MAP` is already map-space. Edit `tingen/src/DistrictMap.gd` line 105:

```gdscript
	# 3b) The warehouse rite-site marker, in canonical map space (same space as the district dots).
	var rite: Vector2 = MapProjection.image_to_canvas(size, MapProjection.WAREHOUSE_MAP)
```

(The player tracker on line 110, `world_to_map(AgentRuntime.player_position)`, stays correct — it now divides by 3.5 and is accurate city-wide.)

- [ ] **Step 5: Run the suite — expect GREEN**

Run the full suite. Expected: `=== 490 passed, 0 failed, 0 skipped ===`, exit 0. (The harness counts each `_ok` assertion, not each test function. Baseline 488 + 2: the rewritten `_test_map_projection_world_to_map` has 8 assertions, up from the old 6.)

- [ ] **Step 6: Commit**

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && git add tingen/src/MapProjection.gd tingen/src/DistrictMap.gd tingen/tests/run_tests.gd && git commit -F - <<'EOF'
refactor: replace Iron-Cross remap with global CITY_SCALE transform

MapProjection now maps the whole map onto a (0,0)-(3500,2471) world via one
uniform CITY_SCALE=3.5. WAREHOUSE_MAP anchors the rite site in canonical map
space. The map tracker is now accurate city-wide, not just inside Iron Cross.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
```

---

## Task 2: Re-anchor simulation coordinates

Move the gameplay anchors (rite site, NPC waypoints) into the new world space, with a guard test proving the three sources agree. `const` can't call statics, so `SITES` / `WAREHOUSE` become `static var`s.

**Files:**
- Modify: `tingen/src/ActionCommit.gd:11-13`
- Modify: `tingen/src/AmbientSidecar.gd:16`
- Modify: `tingen/data/npcs.json`
- Test: `tingen/tests/run_tests.gd` (add `_test_coordinate_anchors_consistent`; update `_test_action_commit`)

- [ ] **Step 1: Write the failing consistency-guard test**

Add this new function after `_test_action_commit` (after line 575):

```gdscript
func _test_coordinate_anchors_consistent() -> void:
	print("[coordinate anchors]")
	var site_world: Vector2 = MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP)
	_ok(site_world.is_equal_approx(Vector2(1802.5, 1302.0)), "rite site resolves to world (1802.5,1302.0)")
	_ok((ActionCommit.SITES["iron_cross_warehouse"] as Vector2).is_equal_approx(site_world),
		"ActionCommit.SITES rite == map_to_world(WAREHOUSE_MAP)")
	_ok(AmbientSidecar.WAREHOUSE.is_equal_approx(site_world),
		"AmbientSidecar.WAREHOUSE == map_to_world(WAREHOUSE_MAP)")
```

Register it in `_init()` immediately after the `_test_action_commit()` call (line 48):

```gdscript
	_test_action_commit()
	_test_coordinate_anchors_consistent()
```

- [ ] **Step 2: Run the suite — expect RED**

Run the full suite. Expected: the two new `_ok` lines comparing against `site_world` FAIL — `ActionCommit.SITES` is still `Vector2(420,360)` and `AmbientSidecar.WAREHOUSE` is still `Vector2(420,360)`, neither equals `(1802.5,1302.0)`. Summary shows `... 2 failed`, exit 1.

- [ ] **Step 3: Anchor ActionCommit.SITES to the transform**

In `tingen/src/ActionCommit.gd`, replace the `SITES` const (lines 9–13):

```gdscript
## Named ritual/world sites in world coordinates, anchored to the canonical map via MapProjection
## so they stay true to the map. const can't call a static fn, so this is a static var.
static var SITES: Dictionary = {
	"iron_cross_warehouse": MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP),
}
```

- [ ] **Step 4: Anchor AmbientSidecar.WAREHOUSE to the transform**

In `tingen/src/AmbientSidecar.gd`, replace line 16:

```gdscript
## Mirrors ActionCommit.SITES.iron_cross_warehouse — the descending god's rite pulls the faithful in.
## static var (not const) so it can be computed from MapProjection's transform.
static var WAREHOUSE: Vector2 = MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP)
```

- [ ] **Step 5: Update `_test_action_commit` to reference the site symbolically**

In `_test_action_commit`, replace the two hardcoded `Vector2(420, 360)` references (lines 559 and 563) so the test follows the anchor instead of a stale literal:

```gdscript
	voss.position = Vector2.ZERO
	var site: Vector2 = ActionCommit.SITES["iron_cross_warehouse"]
	var before: float = voss.position.distance_to(site)
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)
	_ok(out.has("moved_to"), "move_to reports a new position")
	_ok(voss.position.distance_to(site) < before, "agent moved toward the site")
```

- [ ] **Step 6: Rescale npcs.json waypoints into the new world space**

Each old waypoint is mapped old-world → map (via the *old* streetscape remap, `map = 430+(x-120)·170/660, 300+(y-140)·140/460`) → world (×3.5), i.e. `new = (1505 + (x-120)·0.901515, 1050 + (y-140)·1.065217)`, rounded to integers. This keeps the cast clustered correctly around the Iron Cross rite site (~`(1802,1302)`). Replace the `schedule` blocks in `tingen/data/npcs.json`:

```json
		"schedule": {
			"morning": [1793, 1327],
			"afternoon": [1830, 1220],
			"dusk": [1793, 1263],
			"night": [1757, 1284],
			"late-night": [1775, 1284]
		}
```
(clerk_voss) …

```json
		"schedule": {
			"morning": [2010, 1167],
			"afternoon": [1848, 1178],
			"dusk": [1812, 1242],
			"night": [1757, 1284]
		}
```
(fishwife_dalia) …

```json
		"schedule": {
			"early-morning": [1703, 1125],
			"morning": [1595, 1220],
			"afternoon": [1884, 1220],
			"dusk": [1866, 1284],
			"night": [1721, 1284],
			"late-night": [1694, 1284]
		}
```
(lamplighter_orin) …

```json
		"schedule": {
			"morning": [1866, 1093],
			"afternoon": [1866, 1284],
			"dusk": [1848, 1306],
			"night": [1721, 1220]
		}
```
(dockhand_pell). Leave every other field (`name`, `dialogue_id`, `faction`, `role`, `intent`, `tint`) untouched.

- [ ] **Step 7: Run the suite — expect GREEN**

Run the full suite. Expected: `=== 493 passed, 0 failed, 0 skipped ===` (490 + the 3 new assertions in `_test_coordinate_anchors_consistent`), exit 0. `_test_ambient_sidecar` stays green because it reads waypoints symbolically via `NpcDB.waypoint_for`; `_test_ambient_sidecar_performs_rite` stays green because it positions the cultist *at* `AmbientSidecar.WAREHOUSE`.

- [ ] **Step 8: Commit**

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && git add tingen/src/ActionCommit.gd tingen/src/AmbientSidecar.gd tingen/data/npcs.json tingen/tests/run_tests.gd && git commit -F - <<'EOF'
refactor: re-anchor rite site and NPC waypoints to the new world scale

ActionCommit.SITES and AmbientSidecar.WAREHOUSE are now derived from
MapProjection.map_to_world(WAREHOUSE_MAP); npcs.json schedules are rescaled
into the (0,0)-(3500,2471) world. A guard test asserts all three anchors agree.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
```

---

## Task 3: CityLayout loader, nav-polygon helper, and city data

A new global class that parses `city_layout.json`, transforms it to world space, and bakes a `NavigationPolygon`. Pure/static, mirroring `MapProjection`. **Introduces a new `class_name`, so a class-cache refresh is required.**

**Files:**
- Create: `tingen/src/CityLayout.gd`
- Create: `tingen/data/city_layout.json`
- Test: `tingen/tests/run_tests.gd` (add `_test_city_layout`, `_test_city_layout_data`, `_test_navmesh_routing`)

- [ ] **Step 1: Author the city data — `tingen/data/city_layout.json`**

Map-pixel space (traceable against `tingen_map.png`). 27 small building blocks grouped by district, the east river + harbor basin as water, the city outline, and five landmarks. All vertices within `(0,0)–(1000,706)`.

```json
{
	"city_outline": [120, 120, 900, 120, 900, 640, 120, 640],
	"water": [
		[858, 150, 895, 150, 895, 470, 858, 470],
		[770, 460, 895, 460, 895, 635, 770, 635]
	],
	"blocks": [
		[438, 306, 498, 306, 498, 346, 438, 346],
		[512, 306, 590, 306, 590, 346, 512, 346],
		[438, 392, 498, 392, 498, 434, 438, 434],
		[536, 392, 590, 392, 590, 434, 536, 434],
		[616, 158, 676, 158, 676, 210, 616, 210],
		[704, 158, 764, 158, 764, 210, 704, 210],
		[616, 236, 676, 236, 676, 292, 616, 292],
		[704, 236, 764, 236, 764, 292, 704, 292],
		[696, 306, 760, 306, 760, 358, 696, 358],
		[780, 306, 844, 306, 844, 358, 780, 358],
		[696, 372, 760, 372, 760, 424, 696, 424],
		[780, 372, 844, 372, 844, 424, 780, 424],
		[386, 478, 436, 478, 436, 522, 386, 522],
		[450, 478, 500, 478, 500, 522, 450, 522],
		[504, 478, 554, 478, 554, 522, 504, 522],
		[386, 540, 436, 540, 436, 584, 386, 584],
		[450, 540, 500, 540, 500, 584, 450, 584],
		[504, 540, 554, 540, 554, 584, 504, 584],
		[686, 448, 740, 448, 740, 494, 686, 494],
		[686, 508, 740, 508, 740, 554, 686, 554],
		[686, 568, 740, 568, 740, 614, 686, 614],
		[206, 308, 262, 308, 262, 354, 206, 354],
		[276, 308, 332, 308, 332, 354, 276, 354],
		[346, 308, 402, 308, 402, 354, 346, 354],
		[206, 372, 262, 372, 262, 418, 206, 418],
		[276, 372, 332, 372, 332, 418, 276, 418],
		[346, 372, 402, 372, 402, 418, 346, 418]
	],
	"landmarks": [
		{ "pos": [515, 372], "label": "Warehouse" },
		{ "pos": [690, 205], "label": "St. Selena Cathedral" },
		{ "pos": [835, 150], "label": "Backlund Bridge" },
		{ "pos": [470, 550], "label": "Night Market" },
		{ "pos": [800, 545], "label": "The Harbor" }
	]
}
```

- [ ] **Step 2: Create the loader — `tingen/src/CityLayout.gd`**

```gdscript
class_name CityLayout
extends RefCounted
## Pure, node-free loader for the canonical city authoring data (data/city_layout.json).
## Parses the map-pixel-space JSON, applies MapProjection.map_to_world so callers receive
## WORLD-space geometry, and exposes typed getters. This is the headless-testable seam under the
## thin LiveDistrict view (mirrors MapProjection / EndGameResolver). Also hosts the navmesh bake
## helper so the outline-minus-obstacles math lives next to the data that feeds it.

const LAYOUT_PATH := "res://data/city_layout.json"

var _outline: PackedVector2Array
var _water: Array          # Array[PackedVector2Array]
var _blocks: Array         # Array[PackedVector2Array]
var _landmarks: Array      # Array[Dictionary] { pos: Vector2 (world), label: String }

## Load + parse the default data file. Returns a populated CityLayout (empty on missing/bad file).
static func load_default() -> CityLayout:
	if not FileAccess.file_exists(LAYOUT_PATH):
		push_warning("CityLayout: missing %s" % LAYOUT_PATH)
		return CityLayout.new()
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT_PATH))
	return from_dict(parsed if typeof(parsed) == TYPE_DICTIONARY else {})

## Build from an already-parsed Dictionary (no file I/O) — the seam headless tests drive directly.
static func from_dict(data: Dictionary) -> CityLayout:
	var c := CityLayout.new()
	c._outline = _to_world_poly(data.get("city_outline", []))
	for w in data.get("water", []):
		c._water.append(_to_world_poly(w))
	for b in data.get("blocks", []):
		c._blocks.append(_to_world_poly(b))
	for lm in data.get("landmarks", []):
		var p: Array = (lm as Dictionary).get("pos", [0, 0])
		c._landmarks.append({
			"pos": MapProjection.map_to_world(Vector2(float(p[0]), float(p[1]))),
			"label": String((lm as Dictionary).get("label", "")),
		})
	return c

func outline() -> PackedVector2Array: return _outline
func water() -> Array: return _water
func blocks() -> Array: return _blocks
func landmarks() -> Array: return _landmarks

## Flat [x,y,x,y,...] map-pixel array -> world-space PackedVector2Array.
static func _to_world_poly(raw: Array) -> PackedVector2Array:
	var pts := PackedVector2Array()
	for i in range(0, raw.size() - 1, 2):
		pts.append(MapProjection.map_to_world(Vector2(float(raw[i]), float(raw[i + 1]))))
	return pts

## Bake a NavigationPolygon whose walkable area is `outline_world` minus every polygon in
## `holes_world` (blocks + water). Modern source-geometry API — NO deprecated
## make_polygons_from_outlines, so output stays warning-free. agent_radius 0 keeps the narrow
## alleys between blocks walkable. Pure: returns the resource; the caller owns map registration.
static func build_nav_polygon(outline_world: PackedVector2Array, holes_world: Array) -> NavigationPolygon:
	var nav := NavigationPolygon.new()
	nav.agent_radius = 0.0
	var src := NavigationMeshSourceGeometryData2D.new()
	src.add_traversable_outline(outline_world)
	for h in holes_world:
		src.add_obstruction_outline(h as PackedVector2Array)
	NavigationServer2D.bake_from_source_geometry_data(nav, src)
	return nav
```

- [ ] **Step 3: Write the failing tests**

Add these three functions after `_test_coordinate_anchors_consistent`:

```gdscript
func _test_city_layout() -> void:
	print("[city layout loader]")
	var sample := {
		"city_outline": [0, 0, 100, 0, 100, 100, 0, 100],
		"water": [[80, 0, 100, 0, 100, 50, 80, 50]],
		"blocks": [[10, 10, 30, 10, 30, 30, 10, 30], [40, 40, 60, 40, 60, 60, 40, 60]],
		"landmarks": [{ "pos": [50, 50], "label": "Test Site" }],
	}
	var layout := CityLayout.from_dict(sample)
	_ok(layout.outline().size() == 4, "outline parsed to 4 vertices")
	_ok(layout.water().size() == 1, "one water polygon parsed")
	_ok(layout.blocks().size() == 2, "two block polygons parsed")
	# Transform correctness: a known map vertex comes back x3.5 in world space.
	_ok(layout.outline()[1].is_equal_approx(Vector2(350.0, 0.0)), "map (100,0) -> world (350,0)")
	_ok((layout.landmarks()[0]["pos"] as Vector2).is_equal_approx(Vector2(175.0, 175.0)),
		"landmark map (50,50) -> world (175,175)")
	_ok(String(layout.landmarks()[0]["label"]) == "Test Site", "landmark label preserved")

func _test_city_layout_data() -> void:
	print("[city layout data integrity]")
	var path := "res://data/city_layout.json"
	_ok(FileAccess.file_exists(path), "city_layout.json exists")
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_ok(typeof(data) == TYPE_DICTIONARY, "city_layout.json parses to a Dictionary")
	var d: Dictionary = data
	_ok((d.get("blocks", []) as Array).size() >= 20, "at least 20 building blocks (a real city, not mega-blocks)")
	# Every coordinate list is even-length and inside the map bounds (0,0)-(1000,706).
	var all_polys: Array = []
	all_polys.append(d.get("city_outline", []))
	for w in d.get("water", []): all_polys.append(w)
	for b in d.get("blocks", []): all_polys.append(b)
	var clean := true
	for poly in all_polys:
		if (poly as Array).size() % 2 != 0 or (poly as Array).size() < 6:
			clean = false
		for i in range((poly as Array).size()):
			var v := float(poly[i])
			var bound := 1000.0 if i % 2 == 0 else 706.0
			if v < 0.0 or v > bound:
				clean = false
	_ok(clean, "all outline/water/block vertices are even-length and within map bounds")

func _test_navmesh_routing() -> void:
	print("[navmesh routing]")
	# A 400x400 walkable square with a 120x120 block dead center.
	var outline := PackedVector2Array([Vector2(0, 0), Vector2(400, 0), Vector2(400, 400), Vector2(0, 400)])
	var hole := PackedVector2Array([Vector2(140, 140), Vector2(260, 140), Vector2(260, 260), Vector2(140, 260)])
	var nav := CityLayout.build_nav_polygon(outline, [hole])
	_ok(nav.get_polygon_count() > 0, "baked navigation polygon has polygons")
	# Stand up a standalone nav map, attach a region, and query a path that must pass the block.
	var map := NavigationServer2D.map_create()
	NavigationServer2D.map_set_active(map, true)
	# Align the map's cell size with the NavigationPolygon bake default (1.0) so the region's
	# polygons register cleanly. If a path is unexpectedly empty, this is the first knob to check.
	NavigationServer2D.map_set_cell_size(map, 1.0)
	var region := NavigationServer2D.region_create()
	NavigationServer2D.region_set_map(region, map)
	NavigationServer2D.region_set_navigation_polygon(region, nav)
	NavigationServer2D.map_force_update(map)
	var path := NavigationServer2D.map_get_path(map, Vector2(20, 200), Vector2(380, 200), true)
	_ok(path.size() >= 2, "a path exists across the square")
	_ok(path.size() >= 3, "the path bends around the central block (has an intermediate waypoint)")
	var inside_block := false
	for p in path:
		if p.x > 140.0 and p.x < 260.0 and p.y > 140.0 and p.y < 260.0:
			inside_block = true
	_ok(not inside_block, "no path point lies inside the block")
	NavigationServer2D.free_rid(region)
	NavigationServer2D.free_rid(map)
```

Register all three in `_init()` after `_test_coordinate_anchors_consistent()`:

```gdscript
	_test_coordinate_anchors_consistent()
	_test_city_layout()
	_test_city_layout_data()
	_test_navmesh_routing()
```

- [ ] **Step 4: Run the suite — expect RED (CityLayout not declared)**

Run the full suite. Expected: `Parse Error: Identifier "CityLayout" not declared in the current scope` (the class isn't cached yet), non-zero exit.

- [ ] **Step 5: Refresh the class cache**

Run the class-cache refresh command (above). Expected tail: a clean editor import/quit with no parse errors for `CityLayout.gd`.

- [ ] **Step 6: Run the suite — expect GREEN**

Run the full suite. Expected: `=== 507 passed, 0 failed, 0 skipped ===` (493 + 14 new assertions across the three new tests: 6 in `_test_city_layout`, 4 in `_test_city_layout_data`, 4 in `_test_navmesh_routing`), exit 0.

> If `_test_navmesh_routing` reports `a path exists` failing (empty path), the navmesh cell-size alignment is the cause — see the inline comment in the test. This is the plan's #1 known risk; the fix is local to the helper/test.

- [ ] **Step 7: Commit**

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && git add tingen/src/CityLayout.gd tingen/data/city_layout.json tingen/tests/run_tests.gd && git commit -F - <<'EOF'
feat: add CityLayout loader + navmesh helper + city_layout.json

Canonical map-pixel city authoring (outline, water, 27 building blocks,
landmarks) plus a pure loader that transforms it to world space and bakes a
NavigationPolygon (streets = outline minus blocks/water) via the modern API.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
```

---

## Task 4: LiveDistrict rewrite — data-driven visuals + collision + re-anchored spawns

Replace the hand-built Iron-Cross patch with a city built from `CityLayout`: ground, district tints, water + blocks (each visual + solid collider), the warehouse set-dressing, landmark labels, and the re-anchored player / agent / sabotage spawns. The underlay, camera, boundary, and navmesh are layered on in Tasks 5–6, so `_ready()` here only wires the visuals + collision + cast.

**Files:**
- Modify (full rewrite): `tingen/src/LiveDistrict.gd`
- Test: `tingen/tests/run_tests.gd` (extend `_test_live_district_wiring`, lines 1131–1155)

- [ ] **Step 1: Extend the wiring test for the city build**

Replace the body of `_test_live_district_wiring` (lines 1131–1155) with:

```gdscript
func _test_live_district_wiring() -> void:
	print("[live district]")
	var Ag: Object = root.get_node("/root/Agents")
	var AR: Object = root.get_node("/root/AgentRuntime")
	Ag.rebuild()
	var scene = load("res://scenes/LiveDistrict.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var npc_count := 0
	for c in scene.get_children():
		if c.is_in_group("npc"):
			npc_count += 1
	_ok(npc_count == Ag.all().size(), "spawns one NPC per registry agent")
	_ok(AR.player_position == scene.player_start, "runtime player_position fed from the live player")
	_ok(scene.player_start.is_equal_approx(Vector2(1645, 1260)), "player starts on a street near the rite site")
	# The city is built data-driven from CityLayout: every block and water body is realized.
	var layout := CityLayout.load_default()
	_ok(scene.city_block_count() == layout.blocks().size() and scene.city_block_count() >= 20,
		"one solid collider per building block (>= 20)")
	_ok(scene.city_water_count() == layout.water().size(), "one solid collider per water body")
	var street: Node = scene.get_node_or_null("Streetscape")
	_ok(street != null, "live district builds a streetscape")
	_ok(scene.has_warehouse_marker(), "streetscape marks the warehouse (rite site)")
	_ok(scene.has_method("has_sabotage_point") and scene.has_sabotage_point(),
		"streetscape places a sabotage interactable at the rite site")
	scene.queue_free()
	await process_frame
```

- [ ] **Step 2: Run the suite — expect RED**

Run the full suite. Expected: failures in `[live district]` — `scene.city_block_count()` is an unknown method on the old LiveDistrict (runtime error / FAIL), and `player_start` is still `(440,300)`. Non-zero exit.

- [ ] **Step 3: Rewrite `tingen/src/LiveDistrict.gd`**

```gdscript
extends Node2D
## The live, to-scale district. Built data-driven from CityLayout, which transforms the canonical
## map-pixel authoring (data/city_layout.json) into world space via MapProjection: the whole city
## — five districts, the east river/harbor, and many small building blocks — is laid out true to
## tingen_map.png. Each block and water body gets a visual Polygon2D plus a StaticBody2D /
## CollisionPolygon2D so the player and agents collide with the city. One rendered NPC per registry
## Agent is spawned at its (rescaled) position and follows its beat-driven goal. The warehouse
## (降临 / the cult's rite site) is open maroon set-dressing the cast converges on; the player can
## spoil the gathered cache there. The map underlay, camera bounds, city-edge walls, and the baked
## navmesh are layered on in LiveDistrict's later build steps.

const NPC_SCENE: PackedScene = preload("res://scenes/NPC.tscn")
const PLAYER_SCENE: PackedScene = preload("res://scenes/Player.tscn")
const INTERACTABLE_SCENE: PackedScene = preload("res://scenes/Interactable.tscn")
const DISTRICTS_PATH: String = "res://data/districts.json"

## Player spawn: a street just south of the Iron Cross blocks (map (470,360) x3.5). On the walkable
## negative space between buildings, a short walk from the warehouse rite site.
@export var player_start: Vector2 = Vector2(1645, 1260)

## The sabotage point at the warehouse door (map (505,372) x3.5): ~35u from the rite site, inside
## ActionCommit.RITE_RADIUS so the player can spoil the gathered cache by hand.
const SABOTAGE_POINT: Vector2 = Vector2(1767.5, 1302.0)
## The warehouse building footprint in world space (map rect (485,350)-(545,394) x3.5). Visual
## set-dressing only (no collider) so cultists gather in its open courtyard and the player reaches
## the sabotage point.
const WAREHOUSE_RECT: Rect2 = Rect2(1697.5, 1225.0, 210.0, 154.0)

# Per-district translucent ground tints by id; districts not listed fall back to GROUND_DISTRICT.
const DISTRICT_TINTS: Dictionary = {
	"iron_cross": Color(0.205, 0.205, 0.255),
	"harbor": Color(0.105, 0.185, 0.245),
	"st_selena": Color(0.235, 0.225, 0.265),
	"night_market": Color(0.245, 0.200, 0.170),
	"uptown": Color(0.215, 0.225, 0.255),
}
const GROUND_BASE: Color = Color(0.110, 0.120, 0.150)        # the streets/paving filling city_outline
const GROUND_DISTRICT: Color = Color(0.180, 0.180, 0.220)
const WATER_FILL: Color = Color(0.085, 0.150, 0.205)
const WATER_EDGE: Color = Color(0.400, 0.560, 0.610, 0.70)
const BUILDING_FILL: Color = Color(0.150, 0.155, 0.190)
const BUILDING_EDGE: Color = Color(0.310, 0.320, 0.380)
const WAREHOUSE_FILL: Color = Color(0.235, 0.130, 0.130)
const WAREHOUSE_EDGE: Color = Color(0.520, 0.225, 0.215)

var _player: Node2D = null

func _ready() -> void:
	_build_city()
	_spawn_player()
	_spawn_agents()
	_spawn_rite_sabotage_point()

# --- Set construction -------------------------------------------------------------------
## Build the city under one "Streetscape" node (added first so the cast renders on top). The fills,
## district tints, water, and building blocks are all data-driven from CityLayout; the warehouse is
## authored maroon set-dressing at the rite site.
func _build_city() -> void:
	var s := Node2D.new()
	s.name = "Streetscape"
	add_child(s)

	var layout := CityLayout.load_default()

	# 1) Ground base filling the city outline (the streets/negative space read as paving).
	var ground := Polygon2D.new()
	ground.polygon = layout.outline()
	ground.color = GROUND_BASE
	s.add_child(ground)

	# 2) District tints, from the same map_polygon data the panel & risk model read.
	for d in _load_districts():
		var poly := _district_world_poly(d)
		if poly.size() < 3:
			continue
		var pg := Polygon2D.new()
		pg.polygon = poly
		var tint: Color = DISTRICT_TINTS.get(String(d.get("id", "")), GROUND_DISTRICT)
		tint.a = 0.45
		pg.color = tint
		s.add_child(pg)

	# 3) Water (river + harbor): visual fill + edge + a solid body so the player can't enter it.
	for w in layout.water():
		_fill(s, w, WATER_FILL)
		_outline(s, w, WATER_EDGE, 2.0)
		_solid(s, w, "city_water")

	# 4) Building blocks: visual fill + edge + a solid body each.
	for b in layout.blocks():
		_fill(s, b, BUILDING_FILL)
		_outline(s, b, BUILDING_EDGE, 1.5)
		_solid(s, b, "city_block")

	# 5) The warehouse — maroon, named, no collider (open rite courtyard).
	var wh_poly := _rect_poly(WAREHOUSE_RECT)
	_fill(s, wh_poly, WAREHOUSE_FILL)
	_outline(s, wh_poly, WAREHOUSE_EDGE, 2.0)

	# 6) Landmark labels (rite site, cathedral, bridge, market, harbor) at their world positions.
	for lm in layout.landmarks():
		_place_label(s, (lm["pos"] as Vector2) + Vector2(-30, -22), String(lm["label"]),
			Color(0.86, 0.84, 0.92), 13)

func _fill(parent: Node2D, poly: PackedVector2Array, color: Color) -> void:
	var p := Polygon2D.new()
	p.polygon = poly
	p.color = color
	parent.add_child(p)

func _outline(parent: Node2D, poly: PackedVector2Array, color: Color, w: float) -> void:
	var l := Line2D.new()
	var pts := poly
	pts.append(poly[0])   # close the loop
	l.points = pts
	l.width = w
	l.default_color = color
	parent.add_child(l)

## A static collider for a closed polygon, tagged with `group` so tests can count blocks/water.
func _solid(parent: Node2D, poly: PackedVector2Array, group: String) -> void:
	var body := StaticBody2D.new()
	body.add_to_group(group)
	var col := CollisionPolygon2D.new()
	col.polygon = poly
	body.add_child(col)
	parent.add_child(body)

func _rect_poly(r: Rect2) -> PackedVector2Array:
	return PackedVector2Array([r.position, Vector2(r.end.x, r.position.y), r.end,
		Vector2(r.position.x, r.end.y)])

func _place_label(parent: Node2D, pos: Vector2, text: String, color: Color, size: int) -> void:
	var l := Label.new()
	l.position = pos
	l.text = text
	l.modulate = color
	l.add_theme_font_size_override("font_size", size)
	parent.add_child(l)

func _load_districts() -> Array:
	if not FileAccess.file_exists(DISTRICTS_PATH):
		return []
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(DISTRICTS_PATH))
	return parsed if typeof(parsed) == TYPE_ARRAY else []

## A district's outline in world space, from its canonical map_polygon (x CITY_SCALE).
func _district_world_poly(d: Dictionary) -> PackedVector2Array:
	var pts := PackedVector2Array()
	var raw: Array = d.get("map_polygon", [])
	for i in range(0, raw.size() - 1, 2):
		pts.append(MapProjection.map_to_world(Vector2(float(raw[i]), float(raw[i + 1]))))
	return pts

# --- Test/debug seams -------------------------------------------------------------------
## Number of solid building-block colliders realized from the layout data.
func city_block_count() -> int:
	return _count_in_group("city_block")

## Number of solid water-body colliders realized from the layout data.
func city_water_count() -> int:
	return _count_in_group("city_water")

func _count_in_group(group: String) -> int:
	var s: Node = get_node_or_null("Streetscape")
	if s == null:
		return 0
	var n := 0
	for c in s.get_children():
		if c.is_in_group(group):
			n += 1
	return n

## True once the streetscape has labeled the warehouse rite site.
func has_warehouse_marker() -> bool:
	var s: Node = get_node_or_null("Streetscape")
	if s == null:
		return false
	for c in s.get_children():
		if c is Label and (c as Label).text == "Warehouse":
			return true
	return false

## True once the rite-cache sabotage interactable has been placed.
func has_sabotage_point() -> bool:
	for c in get_children():
		if c.is_in_group("interactable") and bool(c.get("sabotage_cache")):
			return true
	return false

# --- Cast -------------------------------------------------------------------------------
func _spawn_player() -> void:
	_player = PLAYER_SCENE.instantiate()
	add_child(_player)
	_player.global_position = player_start
	AgentRuntime.player_position = player_start

func _spawn_agents() -> void:
	for a in Agents.all():
		var npc: Node2D = NPC_SCENE.instantiate()
		npc.npc_id = a.id
		add_child(npc)
		npc.global_position = a.position

## The player's hands-on counter to the summoning: a sabotage point at the warehouse door. Walk up,
## press E, and one gathered ingredient is scattered (PlayerActions.sabotage_any) — setting the rite
## back. The cult re-gathers, so it is a tug-of-war, not a kill switch.
func _spawn_rite_sabotage_point() -> void:
	var node: Node2D = INTERACTABLE_SCENE.instantiate()
	node.sabotage_cache = true
	node.prompt_text = "Spoil the rite cache"
	node.tint = WAREHOUSE_EDGE
	add_child(node)
	node.global_position = SABOTAGE_POINT

func _process(_delta: float) -> void:
	if is_instance_valid(_player):
		AgentRuntime.player_position = _player.global_position
```

- [ ] **Step 4: Run the suite — expect GREEN**

Run the full suite. Expected: `=== 509 passed, 0 failed, 0 skipped ===`, exit 0. (507 + 2: `_test_live_district_wiring` grew from 6 to 8 assertions.)

- [ ] **Step 5: Commit**

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && git add tingen/src/LiveDistrict.gd tingen/tests/run_tests.gd && git commit -F - <<'EOF'
feat: rebuild LiveDistrict to scale from CityLayout (visuals + collision)

The whole city is now built data-driven from CityLayout: ground, district
tints, the river/harbor and every building block (each a solid collider), the
warehouse rite site, and re-anchored player/agent/sabotage spawns.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
```

---

## Task 5: Map underlay, camera bounds, and city-edge boundary

Add the tracing underlay (default ON), bound the camera to the city rect, and ring the world with four `WorldBoundaryShape2D` walls so the player can't walk off the map. Layered onto LiveDistrict via additions to `_ready()` plus new methods.

**Files:**
- Modify: `tingen/src/LiveDistrict.gd`
- Test: `tingen/tests/run_tests.gd` (add `_test_live_district_underlay_camera_bounds`)

- [ ] **Step 1: Write the failing test**

Add after `_test_live_district_wiring`:

```gdscript
func _test_live_district_underlay_camera_bounds() -> void:
	print("[live district underlay/camera/bounds]")
	root.get_node("/root/Agents").rebuild()
	var scene = load("res://scenes/LiveDistrict.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	# Underlay: a map Sprite2D, visible by default (for tracing), toggleable.
	_ok(scene.underlay_visible(), "map underlay is ON by default (for tracing fidelity)")
	scene.set_underlay_visible(false)
	_ok(not scene.underlay_visible(), "underlay can be toggled off")
	scene.set_underlay_visible(true)
	# Camera bounds: the player's Camera2D is limited to the (0,0)-(3500,2471) city rect.
	_ok(scene.has_camera_bounds(), "player camera is bounded to the city rect")
	# City-edge boundary: four world-boundary walls keep the player on the map.
	_ok(scene.boundary_wall_count() == 4, "four city-edge boundary walls exist")
	scene.queue_free()
	await process_frame
```

Register it in `_init()` right after `_test_live_district_wiring()` (line 70):

```gdscript
	await _test_live_district_wiring()
	await _test_live_district_underlay_camera_bounds()
```

- [ ] **Step 2: Run the suite — expect RED**

Run the full suite. Expected: `[live district underlay/camera/bounds]` fails — `underlay_visible` / `has_camera_bounds` / `boundary_wall_count` are unknown methods. Non-zero exit.

- [ ] **Step 3: Add the underlay export + the new build calls**

In `tingen/src/LiveDistrict.gd`, add the map texture const next to the other `preload`s:

```gdscript
const MAP_TEXTURE: Texture2D = preload("res://assets/maps/tingen_map.png")
```

Add the export beside `player_start`:

```gdscript
## The map art drawn behind the vector city, scaled to cover (0,0)-(3500,2471). ON by default so
## geometry can be traced against it; flipped OFF (a later user-triggered step) once faithful.
@export var show_map_underlay: bool = true
```

Replace `_ready()` with:

```gdscript
func _ready() -> void:
	_build_underlay()
	_build_city()
	_build_boundary()
	_spawn_player()
	_apply_camera_bounds()
	_spawn_agents()
	_spawn_rite_sabotage_point()
```

- [ ] **Step 4: Add the underlay, boundary, and camera methods**

Add these methods to `tingen/src/LiveDistrict.gd` (e.g. after `_build_city`):

```gdscript
## The map art underlay: a Sprite2D covering exactly (0,0)-(3500,2471), behind everything. A
## tracing aid only — the vectors are the source of truth for collision/nav — so its visibility is
## a free toggle that changes nothing functional.
func _build_underlay() -> void:
	var spr := Sprite2D.new()
	spr.name = "MapUnderlay"
	spr.texture = MAP_TEXTURE
	spr.centered = false
	spr.position = Vector2.ZERO
	spr.scale = Vector2(MapProjection.CITY_SCALE, MapProjection.CITY_SCALE)
	spr.z_index = -100
	spr.visible = show_map_underlay
	add_child(spr)

## Four infinite WorldBoundaryShape2D walls at the world rect edges, so the player can't walk off
## the map. Each normal points inward (toward the playable side); distance = normal . edge-point.
func _build_boundary() -> void:
	var w: float = MapProjection.MAP_SIZE.x * MapProjection.CITY_SCALE   # 3500
	var h: float = MapProjection.MAP_SIZE.y * MapProjection.CITY_SCALE   # 2471
	_wall(Vector2(1, 0), 0.0)     # left   (x = 0)
	_wall(Vector2(-1, 0), -w)     # right  (x = 3500)
	_wall(Vector2(0, 1), 0.0)     # top    (y = 0)
	_wall(Vector2(0, -1), -h)     # bottom (y = 2471)

func _wall(normal: Vector2, distance: float) -> void:
	var body := StaticBody2D.new()
	body.add_to_group("city_boundary")
	var col := CollisionShape2D.new()
	var shape := WorldBoundaryShape2D.new()
	shape.normal = normal
	shape.distance = distance
	col.shape = shape
	body.add_child(col)
	add_child(body)

## Bound the player's camera to the (0,0)-(3500,2471) city rect so the view never shows the void.
func _apply_camera_bounds() -> void:
	if _player == null:
		return
	var cam := _player.get_node_or_null("Camera2D") as Camera2D
	if cam == null:
		return
	cam.limit_left = 0
	cam.limit_top = 0
	cam.limit_right = int(MapProjection.MAP_SIZE.x * MapProjection.CITY_SCALE)   # 3500
	cam.limit_bottom = int(MapProjection.MAP_SIZE.y * MapProjection.CITY_SCALE)  # 2471
```

- [ ] **Step 5: Add the test seams**

Add to the test/debug seams section:

```gdscript
## True when the map underlay sprite is currently shown.
func underlay_visible() -> bool:
	var spr := get_node_or_null("MapUnderlay") as Sprite2D
	return spr != null and spr.visible

## Toggle the tracing underlay on/off (the vectors stay the source of truth either way).
func set_underlay_visible(v: bool) -> void:
	var spr := get_node_or_null("MapUnderlay") as Sprite2D
	if spr != null:
		spr.visible = v

## True when the player's camera has been limited to the full city rect.
func has_camera_bounds() -> bool:
	if _player == null:
		return false
	var cam := _player.get_node_or_null("Camera2D") as Camera2D
	return cam != null and cam.limit_right == int(MapProjection.MAP_SIZE.x * MapProjection.CITY_SCALE) \
		and cam.limit_bottom == int(MapProjection.MAP_SIZE.y * MapProjection.CITY_SCALE)

## Number of city-edge boundary walls.
func boundary_wall_count() -> int:
	var n := 0
	for c in get_children():
		if c.is_in_group("city_boundary"):
			n += 1
	return n
```

- [ ] **Step 6: Run the suite — expect GREEN**

Run the full suite. Expected: `=== 513 passed, 0 failed, 0 skipped ===` (509 + 4 new assertions in `_test_live_district_underlay_camera_bounds`), exit 0.

- [ ] **Step 7: Commit**

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && git add tingen/src/LiveDistrict.gd tingen/tests/run_tests.gd && git commit -F - <<'EOF'
feat: add map underlay, bounded camera, and city-edge walls

A toggleable tingen_map.png underlay (ON by default for tracing) sits behind the
vector city; the player camera is limited to the (0,0)-(3500,2471) rect; four
WorldBoundaryShape2D walls keep the player on the map.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
```

---

## Task 6: Bake the city navmesh region

Stand up a `NavigationRegion2D` in LiveDistrict whose walkable area is the city outline minus every building block and water body, baked from the same `CityLayout` data that draws the set and the colliders. The region attaches to the scene's default 2D navigation map; Task 7's NPC `NavigationAgent2D` nodes path on it.

**Files:**
- Modify: `tingen/src/LiveDistrict.gd`
- Test: `tingen/tests/run_tests.gd` (add `_test_live_district_navmesh`)

- [ ] **Step 1: Write the failing test**

Add after `_test_live_district_underlay_camera_bounds`:

```gdscript
func _test_live_district_navmesh() -> void:
	print("[live district navmesh]")
	root.get_node("/root/Agents").rebuild()
	var scene = load("res://scenes/LiveDistrict.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	# The region bakes from CityLayout (outline minus blocks/water) and has real polygons.
	_ok(scene.nav_region_baked() > 0, "city navmesh region baked with polygons")
	# It is attached to a live navigation map (the scene's default 2D map), shared with agents.
	_ok(scene.nav_map_rid().is_valid(), "city nav region is on a valid navigation map")
	scene.queue_free()
	await process_frame
```

Register it in `_init()` right after `_test_live_district_underlay_camera_bounds()` (the call added in Task 5):

```gdscript
	await _test_live_district_underlay_camera_bounds()
	await _test_live_district_navmesh()
```

- [ ] **Step 2: Run the suite — expect RED**

Run the full suite. Expected: `[live district navmesh]` fails — `nav_region_baked` / `nav_map_rid` are unknown methods. Non-zero exit.

- [ ] **Step 3: Add the navmesh region member + build call**

In `tingen/src/LiveDistrict.gd`, add the region handle beside `_player`:

```gdscript
var _nav_region: NavigationRegion2D = null
```

Replace `_ready()` (the Task 5 version) with one that bakes the navmesh after the city geometry exists and before the cast spawns (so agents find a populated map):

```gdscript
func _ready() -> void:
	_build_underlay()
	_build_city()
	_build_boundary()
	_build_navmesh()
	_spawn_player()
	_apply_camera_bounds()
	_spawn_agents()
	_spawn_rite_sabotage_point()
```

- [ ] **Step 4: Add the navmesh build method**

Add this method to `tingen/src/LiveDistrict.gd` (e.g. after `_build_city`):

```gdscript
## Bake the walkable navmesh from the SAME data the set is drawn from: the city outline is the
## traversable area, every building block and water body is punched out as an obstruction. The
## resulting NavigationRegion2D registers with the scene's default 2D nav map, which NPC
## NavigationAgent2D nodes (Task 7) share automatically.
func _build_navmesh() -> void:
	var layout := CityLayout.load_default()
	var holes: Array = []
	holes.append_array(layout.blocks())
	holes.append_array(layout.water())
	var nav := CityLayout.build_nav_polygon(layout.outline(), holes)
	# Align the scene's default 2D nav-map cell size with the NavigationPolygon bake default (1.0)
	# so the region registers without a cell-size-mismatch warning — the #1 navmesh pitfall.
	NavigationServer2D.map_set_cell_size(get_world_2d().navigation_map, 1.0)
	var region := NavigationRegion2D.new()
	region.name = "CityNav"
	region.navigation_polygon = nav
	add_child(region)
	_nav_region = region
```

- [ ] **Step 5: Add the test seams**

Add to the test/debug seams section:

```gdscript
## Number of baked polygons in the city navmesh (0 if the region is missing or failed to bake).
func nav_region_baked() -> int:
	if _nav_region == null or _nav_region.navigation_polygon == null:
		return 0
	return _nav_region.navigation_polygon.get_polygon_count()

## The navigation map RID the city region — and every NPC NavigationAgent2D — share.
func nav_map_rid() -> RID:
	return _nav_region.get_navigation_map() if _nav_region != null else RID()
```

- [ ] **Step 6: Run the suite — expect GREEN**

Run the full suite. Expected: `=== 515 passed, 0 failed, 0 skipped ===` (513 + 2 new assertions in `_test_live_district_navmesh`), exit 0. Output must stay pristine — if a "navigation map synchronization error … cell size" warning prints, the `map_set_cell_size` line is the knob; confirm `navigation/2d/default_cell_size` in `project.godot` is 1.0.

- [ ] **Step 7: Commit**

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && git add tingen/src/LiveDistrict.gd tingen/tests/run_tests.gd && git commit -F - <<'EOF'
feat: bake a city navmesh region from CityLayout

LiveDistrict bakes a NavigationRegion2D whose walkable area is the city outline
minus every building block and water body, attached to the scene's default 2D
nav map (cell size aligned to the 1.0 bake default). NPC pathfinding wires onto
it in the next task.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
```

---

## Task 7: NPC pathfinding via NavigationAgent2D

Give each NPC a `NavigationAgent2D` and route its movement around the city's building blocks/water on the baked navmesh, with a straight-line fallback when no usable path exists (an NPC outside the live district, or before the map has synced). The Agent-binding seams `steer_goal()` / `is_bound()` are preserved untouched, so the registry-driven cast still follows its beat-driven goals — only the *path* to the goal changes.

**Files:**
- Modify: `tingen/scenes/NPC.tscn` (add a `NavigationAgent2D` child)
- Modify: `tingen/src/NPC.gd` (path on the navmesh in `_physics_process`; keep `steer_goal()`/`is_bound()`)
- Test: `tingen/tests/run_tests.gd` (add `_test_npc_navmesh_pathfinding`)

- [ ] **Step 1: Write the failing integration test**

Add after `_test_live_district_navmesh`:

```gdscript
func _test_npc_navmesh_pathfinding() -> void:
	print("[npc navmesh pathfinding]")
	root.get_node("/root/Agents").rebuild()
	var scene = load("res://scenes/LiveDistrict.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	# Each spawned NPC carries a NavigationAgent2D bound to the shared city nav map.
	var npc: Node = null
	for c in scene.get_children():
		if c.is_in_group("npc"):
			npc = c
			break
	_ok(npc != null, "at least one NPC spawned in the live district")
	var agent = npc.get_node_or_null("NavigationAgent2D") if npc != null else null
	_ok(agent != null, "the NPC scene carries a NavigationAgent2D")
	_ok(agent != null and agent.get_navigation_map() == scene.nav_map_rid(),
		"the NPC agent shares the city navigation map")
	# The shared map routes between two open street points (proves NPCs can path around blocks).
	NavigationServer2D.map_force_update(scene.nav_map_rid())
	var from_w := MapProjection.map_to_world(Vector2(470, 360))   # open street by the player start
	var to_w := MapProjection.map_to_world(Vector2(515, 372))     # the warehouse rite door
	var path := NavigationServer2D.map_get_path(scene.nav_map_rid(), from_w, to_w, true)
	_ok(path.size() >= 2, "the city nav map returns a path between two street points")
	scene.queue_free()
	await process_frame
```

Register it in `_init()` right after `_test_live_district_navmesh()` (the call added in Task 6):

```gdscript
	await _test_live_district_navmesh()
	await _test_npc_navmesh_pathfinding()
```

- [ ] **Step 2: Run the suite — expect RED**

Run the full suite. Expected: `[npc navmesh pathfinding]` fails — `npc.get_node_or_null("NavigationAgent2D")` is `null` (the scene has no agent yet), so `the NPC scene carries a NavigationAgent2D` (and the map-equality assertion) FAIL. Non-zero exit.

- [ ] **Step 3: Add the NavigationAgent2D to `tingen/scenes/NPC.tscn`**

Append this node (a child of the root `NPC`) after the `TalkArea`/`Prompt` block (the last lines of the file). `path_desired_distance` / `target_desired_distance` match the script's `arrive_radius` (8.0); avoidance stays off (NPCs collide via their physics body, not RVO):

```
[node name="NavigationAgent2D" type="NavigationAgent2D" parent="."]
path_desired_distance = 8.0
target_desired_distance = 8.0
avoidance_enabled = false
```

- [ ] **Step 4: Route movement through the navmesh in `tingen/src/NPC.gd`**

Add the agent handle next to the other `@onready` vars (after `_prompt`, line 15):

```gdscript
@onready var _nav: NavigationAgent2D = $NavigationAgent2D
```

Replace `_physics_process` (lines 62–71) with:

```gdscript
func _physics_process(_delta: float) -> void:
	if DialogueManager.active:
		velocity = Vector2.ZERO
		return
	var goal := steer_goal()
	if global_position.distance_to(goal) <= arrive_radius:
		velocity = Vector2.ZERO
		return
	# Path around the city's buildings/water on the baked navmesh. Fall back to straight-line
	# steering when there is no usable path — an NPC instantiated outside the live district (e.g.
	# the bind unit-test), or before the nav map has synced — so isolated behavior still holds.
	_nav.target_position = goal
	var steer_point := goal
	if not _nav.is_navigation_finished() and _nav.is_target_reachable():
		steer_point = _nav.get_next_path_position()
	velocity = (steer_point - global_position).normalized() * move_speed
	move_and_slide()
```

Leave `is_bound()` (line 44) and `steer_goal()` (line 49) exactly as they are — the binding contract is unchanged; only the pathing between `global_position` and the goal is new.

- [ ] **Step 5: Run the suite — expect GREEN**

Run the full suite. Expected: `=== 519 passed, 0 failed, 0 skipped ===` (515 + 4 new assertions in `_test_npc_navmesh_pathfinding`), exit 0. `_test_npc_binds_to_agent` stays green: it spawns the NPC from `NPC.tscn` (so `$NavigationAgent2D` resolves), and `steer_goal()` still returns the bound agent's logical position (node movement does not change it). Output must stay pristine — no "NavigationAgent2D is not within a navigation map" warnings (avoidance is off and the agent sits on the scene's default 2D map).

- [ ] **Step 6: Commit**

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && git add tingen/scenes/NPC.tscn tingen/src/NPC.gd tingen/tests/run_tests.gd && git commit -F - <<'EOF'
feat: NPCs path around the city on the baked navmesh

Each NPC gets a NavigationAgent2D and steers along the city navmesh toward its
beat-driven goal, with a straight-line fallback when no path exists. The Agent
binding seams (steer_goal/is_bound) are untouched, so the registry still drives
who goes where; only the route changes.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
```

---

## Task 8: Verify, tune against the underlay, log decisions, review

No new behavior — this task proves the whole world works, refines the traced geometry against the map underlay (which stays ON; hiding it is a separate, later, user-triggered change — per the user: "do the underlay approach first, then hide it"), records the design decisions, and gets a final review.

**Files:**
- Modify (tuning only): `tingen/data/city_layout.json`
- Modify: `DESIGN_DECISIONS.md`

- [ ] **Step 1: Full suite — expect GREEN**

Run the full suite:

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && /Applications/Godot.app/Contents/MacOS/Godot --headless --path tingen -s tests/run_tests.gd
```

Expected tail: `=== 519 passed, 0 failed, 0 skipped ===`, exit 0, no warnings/errors in the output above the summary.

- [ ] **Step 2: Smoke run — boots clean**

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && /Applications/Godot.app/Contents/MacOS/Godot --headless --path tingen --quit-after 180
```

Expected: the game boots, the live district loads (NPCs spawn, navmesh bakes), and it quits after 180 frames with no script errors, no `NavigationServer` warnings, and no "missing node"/parse errors. (`--quit-after` counts frames, not seconds.)

- [ ] **Step 3: Tune the block geometry against the underlay (iterative, visual)**

Launch the project windowed (NOT headless) so the `tingen_map.png` underlay shows behind the vector city:

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && /Applications/Godot.app/Contents/MacOS/Godot --path tingen
```

Walk the player around and compare the vector blocks/water/outline (drawn from `data/city_layout.json`) to the map art beneath them. Where a block clearly misaligns, edit its `[x,y,…]` map-pixel coordinates in `data/city_layout.json` (map-pixel space, 0–1000 × 0–706 — the same space the JSON is authored in) and relaunch to re-check. After each edit, re-run the suite (Step 1) so `_test_city_layout_data` still passes (even-length, in-bounds, ≥20 blocks) and nothing regresses.

Acceptance bar (per spec §6 fidelity + §8 risk): a **structured first pass** that reads unmistakably as the mapped city — districts, the east river/harbor, and the Iron Cross core in the right places at the right relative sizes. Pixel-perfect tracing is explicitly *not* required here; the vectors are the source of truth and can be refined later. Leave `show_map_underlay = true` (default ON) — do not hide the underlay in this task.

> If launching windowed is not available in the execution environment, skip the live trace and accept the authored first-pass geometry; the data-integrity test already guarantees it is well-formed and in-bounds. Note this in the task's completion summary so the user can do the visual pass.

- [ ] **Step 4: Record the design decisions**

Append a new section to the **end** of `DESIGN_DECISIONS.md` (after the existing `### Implementation notes — map panel …` section, the last one in the file). Use this exact text (it mirrors spec §9, in the project's required `**bold choice**` + `*Alts (rejected):*` format):

```markdown

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

- **Modern source-geometry navmesh bake (`add_traversable_outline` / `add_obstruction_outline` + `bake_from_source_geometry_data`), nav-map cell size pinned to the 1.0 bake default.**
  *Alts (rejected):* the deprecated `make_polygons_from_outlines` — emits warnings and is
  slated for removal; leaving cell sizes unpinned — risks a silent "cell size mismatch"
  that drops the region from the map and yields empty paths (the build's #1 navmesh risk).
```

- [ ] **Step 5: Commit the decisions + any tuning**

```bash
cd "/Users/markma/.config/superpowers/worktrees/Tingen-Game/city-world" && git add DESIGN_DECISIONS.md tingen/data/city_layout.json && git commit -F - <<'EOF'
docs: log to-scale city-world design decisions

Records the eight key choices (global CITY_SCALE transform, data-driven
CityLayout, small building blocks, in-run navmesh, default-ON underlay, full
collision + edge boundary, modern bake API) and their rejected alternatives,
plus any block-geometry tuning made against the underlay.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
```

> If Step 3 made no edits to `city_layout.json`, drop it from the `git add` and commit `DESIGN_DECISIONS.md` alone.

- [ ] **Step 6: Final code review**

Dispatch a final review over the whole branch (all eight tasks) — use the `superpowers:code-reviewer` agent (or `superpowers:requesting-code-review`). Brief it with: the goal (rebuild the playable Godot world true to `tingen_map.png` at `CITY_SCALE = 3.5`, with full collision and navmesh-driven NPC pathfinding), the spec path (`docs/superpowers/specs/2026-06-15-city-world-to-scale-design.md`), and the commit range for this branch. Address any blocking findings before finishing the branch.

- [ ] **Step 7: Finish the branch**

Use **superpowers:finishing-a-development-branch** to wrap up (merge/PR per the user's choice, clean up the worktree).

---

## Self-review (run against the spec before execution)

**Spec coverage — every spec section maps to a task:**

| Spec section | Task(s) |
|---|---|
| §2 one global transform (`CITY_SCALE = 3.5`) | Task 1 |
| §3.1 `data/city_layout.json` | Task 3 |
| §3.2 `CityLayout` loader | Task 3 |
| §3.3 `LiveDistrict` rewrite (visuals + collision) | Task 4 |
| §3.4 navmesh `NavigationRegion2D` + `NavigationAgent2D` | Task 6 (region) + Task 7 (NPC) |
| §3.5 re-anchoring (rite site, sabotage, npcs.json waypoints, player_start) | Task 2 (sim coords + npcs.json) + Task 4 (player/sabotage spawns) |
| §3.6 camera bounds | Task 5 |
| §4 testing (MapProjection, CityLayout, data integrity, navmesh, LiveDistrict, regression, smoke) | Tasks 1–7 (per-task tests) + Task 8 (smoke) |
| §5 scope (no interiors, no new content/risk changes) | respected throughout |
| §6 fidelity (structured first pass, refine live) | Task 8 Step 3 |
| §7 build order | Tasks 1→8 follow it |
| §8 risks (navmesh API/cell size, tracing, collision) | Task 3/6 (cell size pinned), Task 8 (trace), Task 4/5 (collision + edge) |
| §9 design decisions | Task 8 Step 4 |
| map underlay + toggle (§3.x / testing §199–202) | Task 5 |
| city-wide accurate tracker | free from Task 1 (DistrictMap already calls `world_to_map`) |

**Placeholder scan:** no `TODO`/`TBD`/"as appropriate"/"similar to" or empty steps — every code/data step shows the actual content. (The only literal "placeholder" is inside a *rejected*-alternative description in Task 8.)

**Type consistency (names match across tasks):** `MapProjection.{CITY_SCALE, MAP_SIZE, WAREHOUSE_MAP, map_to_world, world_to_map, image_to_canvas, canvas_to_image}` defined in Task 1, used verbatim in Tasks 2–7. `CityLayout.{load_default, from_dict, outline, water, blocks, landmarks, _to_world_poly, build_nav_polygon}` defined in Task 3, used verbatim in Tasks 4 & 6. `LiveDistrict` seams (`city_block_count`, `city_water_count`, `has_warehouse_marker`, `has_sabotage_point`, `underlay_visible`, `set_underlay_visible`, `has_camera_bounds`, `boundary_wall_count`, `nav_region_baked`, `nav_map_rid`) are each defined in the task that first asserts them. `NPC.{steer_goal, is_bound}` preserved unchanged in Task 7. Assertion-count math (488 → 490 → 493 → 507 → 509 → 513 → 515 → 519) verified against actual `_ok` counts.

**One deliberate coverage call:** spec §4 lists a *behavioral* "player pushed toward the edge stays in bounds" test; Task 5 instead asserts the **four `WorldBoundaryShape2D` walls exist at the correct edges** (structural). The walls are infinite half-planes a physics body cannot cross, so the structural assertion is a deterministic proxy that avoids flaky headless physics-step simulation. Flagged here so a reviewer can upgrade it to a push test if desired.

---
