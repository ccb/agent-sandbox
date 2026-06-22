# Tingen Map System, Walkable Districts & Navigation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder city stub with a **map system + player-location tracker** (faithful to `asset-gen/ref/tingen_map.png`), **five walkable, prop-furnished district hubs**, and **navigable connections** between them (walkable edge-doors + click-to-travel map), reusing the existing `WorldState.transition_requested → GameController._swap_world` backbone and the approved tilemap-hub design.

**Architecture:** Each district is a Godot `Node2D` hub (`y_sort_enabled`) with a `TileMapLayer` floor (`FloorTiler.gd`), a `StaticBody2D` wall/footprint border, a Y-sorted layer of `Prop`/`Interactable`/`NPC`/`Player`, and a `DayNightTint` modulate — the pattern proven by the IntroRoom slice. A new data file `data/hubs.json` is the single source of truth for each hub's scene path, spawn point, floor tile, neighbour edge-doors, and map hotspot. A new `WorldMap` overlay (owned by us, mounted at runtime by `GameController`, **not** the animation agent's `DistrictMap`) renders the real Tingen map art with a location marker and warps the player on click.

**Tech Stack:** Godot 4.6.3 (GDScript), `CharacterBody2D` top-down, `TileMapLayer` + per-region collision, `CanvasLayer` UI, JSON data. macOS; Godot binary `/Applications/Godot.app/Contents/MacOS/Godot`.

---

## 0. Context the implementer must know (read before starting)

- **Existing navigation backbone (reuse, do not reinvent):**
  - `src/WorldState.gd` → `signal transition_requested(scene_path: String, lead: String)`.
  - `src/GameController.gd` → connects it in `_ready()`; `_on_transition_requested()` calls `_swap_world()`, which frees the current `$World` child and instances the new scene. It already tracks `current_scene_path` and exposes `get_player()` / `player_position()`. **This script is editable (not owned by the animation agent).**
  - `scenes/Interactable.gd` `_use()`: when `target_scene != ""` it emits `WorldState.transition_requested.emit(target_scene, lead_on_use)`. **Edge-doors are just `Interactable` instances with `target_scene` set — zero new code.** (Proven: IntroRoom's Door → `City.tscn`.)
- **Entry shells (both instance `GameController` + `ui/HUD.tscn`):** `scenes/Main.tscn` (project main, loads `LiveDistrict`) and `scenes/IntroMain.tscn` (loads `IntroRoom`). Player flow: IntroMain → IntroRoom → (Door) → `City.tscn`.
- **Reusable pieces:**
  - `scenes/Prop.tscn` + `src/Prop.gd`: `StaticBody2D` set-dressing. Exports `icon: Texture2D`, `icon_px: float` (target on-screen height), `solid: bool`, `footprint: Vector2` (feet collider). Feet-anchored (sprite offset `-h*0.5`), Nearest filter. Use for all district furniture/scenery.
  - `scenes/Player.tscn`: `CharacterBody2D` (group `player`), sprite `klein_down` (scale `0.069`, offset `(0,-470)`), body collider `22×12`, **`Camera2D` with zoom `(2,2)` and smoothing enabled (default ON)** — hubs keep the follow camera (IntroRoom is the exception that disabled it for a fixed `RoomCam`).
  - `scenes/NPC.tscn` + `src/NPC.gd`: `CharacterBody2D` (group `npc`) driven by `npc_id`, with `TalkArea` (radius 56) + prompt. Placed by `npc_id` + `position` (see `City.tscn`'s Orin/Dalia). **NPC sprite art is governed by `NPC.gd`/`NpcDB.gd` (animation agent's domain) — we only place instances; do not repoint NPC textures.**
  - `src/FloorTiler.gd`: `TileMapLayer` subclass; fills `cols×rows` cells with `(source_id, atlas_coords)` at `_ready()`. Needs a `tile_set` assigned.
  - `src/DayNightTint.gd`: existing `CanvasModulate` script; every hub gets one `DayNight` node.
- **Stale-import gotcha (must handle when copying art in):** Godot renders `.godot/imported/<name>-<hash>.ctex`, not the source PNG. After copying any new PNG into `tingen/assets/`, force a reimport: `rm -f tingen/.godot/imported/<name>.png-*` then `Godot --headless --path tingen --import`.
- **GUI playtest launch (proven to stick):** `open -n -a "/Applications/Godot.app" --args --path "<abs tingen path>" res://scenes/<Scene>.tscn`. A background `Bash` launch of the Godot binary exits immediately — do not use it for GUI runs.

### Ownership boundary — files the parallel animation agent owns (DO NOT EDIT)
`AgentRegistry.gd`, `Agent.gd`, `EventBus.gd`, `Clock.gd`, `ItemDB.gd`, `ItemDef.gd`, `Inventory.gd`, `ActionSchema.gd`, `NpcDB.gd`, **`Main.tscn`**, **`ui/HUD.tscn` + all its sub-scenes (incl. `ui/DistrictMap.tscn`)**, `data/items.json`, `action_schema.json`, `tests/run_tests.gd`, `player_detective.png`, `generate_tingen_anim.py` + its `anim/` outputs. Every task below routes around these.

---

## 1. Design decisions (resolved) + flagged for Mark

**Resolved (reasonable defaults, driven by Mark's request + the approved spec + ownership constraints):**

| # | Fork | Decision | Why |
|---|---|---|---|
| D1 | Multi-scene hubs vs. one big `LiveDistrict` polygon-map | **Multi-scene hubs** (`City.tscn`=Iron Cross + 4 new). | Mark said "the **scenes**" and "connection between **them**"; the spec mandates one hub per district; IntroRoom→City already works this way. `LiveDistrict`/`Main.tscn` is the animation agent's agent-sim demo — left untouched. |
| D2 | Map = passive risk overlay vs. interactive travel + tracker | **One map, upgraded in place:** the existing `DistrictMap` is repointed to the real `tingen_map.png` art, with a location marker + click-to-warp (risk tint preserved). | Mark: *"I want only one map, and it should be the ref image as map"* + "player location tracker" + "navigatable". |
| D3 | Navigation: doors / warp / both | **Both.** Walkable edge-doors (immersive, zero new code) + map warp (fast travel) from the one map. | "navigatable" + map emphasis. Same backbone serves both. |
| D4 | Map art style | **Cleaned copy of `ref/tingen_map.png`** as `assets/ui/tingen_map.png`. | "follows the tingen map closely"; the vintage survey look fits the Loen/Backlund era. |
| D5 | Where the map UI lives | **Upgrade the existing `DistrictMap`** (`ui/DistrictMap.gd` + `.tscn`) in place, on the existing **M** key — no second overlay, no new key. | Mark wants exactly one map. The map is a world/navigation concern; folding it into the one map avoids a redundant overlay. **Crosses the animation-agent ownership line — see F1.** |
| D6 | Scope | **One plan, phased:** map+nav system → reusable hub recipe + Iron Cross → stamp the other 4 → integration playtest. | Delivers all 5 connected (as asked) while proving the pattern on a vertical slice first. |
| D7 | Data source of truth | **New `data/hubs.json`** keyed by district id; `districts.json` is left as-is. | `districts.json` is read by two animation-agent scripts (`DistrictMap.gd`, `LiveDistrict.gd`); keeping hub/travel data separate avoids any coupling. |

**Flagged for Mark (decided 2026-06-10; one item still needs his go-ahead):**

- **F1 — ⚠ The one map lives in the animation agent's `DistrictMap` (ownership crossing — NEEDS GO-AHEAD).** Mark's *"one map = ref image"* decision means upgrading `ui/DistrictMap.gd` + `ui/DistrictMap.tscn`, which are on the animation agent's side (HUD sub-scene). The upgrade is **non-destructive** — it keeps the risk-tint feature and *adds* the art backdrop + location marker + click-to-warp — but it edits their files. **Get Mark's explicit OK (or a quick coordinate with the animation agent) before starting Task 6.** No other animation-agent-owned file is touched.
- **F2 — (resolved by D5)** No new input action and no `GameController` mount are needed: the upgraded `DistrictMap` stays on **M** and reaches the player/current scene through the existing `game_controller` group. `project.godot` and `GameController.gd` are left untouched. *(Net owned-file footprint shrank to just `DistrictMap`.)*
- **F3 — (decided: "Map + Iron Cross first")** Execution lands **Phase 0–2 (Tasks 1–9)** and **stops at a checkpoint** for Mark's demo/OK; districts 2–5 + integration (Tasks 10–13) are the **follow-up batch**.

---

## 2. File structure

**Create:**
- `tingen/data/hubs.json` — hub registry: per district `{id, name, scene, player_start, floor_tile, map_rect, map_marker, exits[]}`.
- `tingen/assets/district_tileset.tres` — one `TileSetAtlasSource` per district floor tile.
- `tingen/scenes/Harbor.tscn`, `StSelena.tscn`, `NightMarket.tscn`, `BridgeQuarter.tscn` — the 4 new hubs *(follow-up batch)*.
- `tingen/tools/validate_hubs.gd` — headless validator (our own; **not** `tests/run_tests.gd`).
- `tingen/assets/tiles/*` (6 copied PNGs), `tingen/assets/props/*` (copied + generated PNGs), `tingen/assets/ui/tingen_map.png`, `tingen/assets/ui/map_marker.png`, optional `tingen/assets/backgrounds/*` (district cards).

**Modify — editable / not owned:**
- `tingen/scenes/City.tscn` — rebuild the Iron Cross stub into a full hub.

**Modify — ⚠ animation-agent-owned (only after Mark's F1 go-ahead):**
- `tingen/ui/DistrictMap.gd` + `tingen/ui/DistrictMap.tscn` — upgrade the one map: draw `tingen_map.png` as the backdrop, add a location marker + click-to-warp, keep the risk tint. No other HUD sub-scene is touched.

**Untouched-but-referenced:** `Prop.tscn/gd`, `Player.tscn`, `NPC.tscn`, `Interactable.tscn/gd`, `FloorTiler.gd`, `DayNightTint.gd`, `WorldState.gd`, `GameController.gd`, `project.godot`, `IntroRoom.tscn`.

---

## 3. Asset manifest ("the assets you would need")

Legend: **✓ have** = exists in `asset-gen/out*`, copy into `tingen/assets/…` (Nearest import) · **GEN** = generate with `asset-gen/generate_tingen_assets.py` (or best-match substitute) · **ART** = process from a reference.

### 3a. Floor tiles → `tingen/assets/tiles/` (all ✓ have, in `out/tiles/`)
| District | Tile | Status |
|---|---|---|
| Iron Cross | `cobblestone_wet_0.png` | ✓ have |
| The Harbor | `warehouse_concrete_0.png` (docks) | ✓ have |
| St. Selena | `archive_carpet_0.png` (nave) / `cobblestone_wet` (plaza) | ✓ have |
| Night Market | `brick_alley_0.png` | ✓ have |
| Bridge Quarter | `cobblestone_wet_0.png` (fine paving) + `dead_grass_0.png` (riverbank) | ✓ have |
| (rite/undercroft) | `ritual_stone_0.png` | ✓ have |
| (interiors) | `wood_floor_0.png` | ✓ already imported |

### 3b. Props → `tingen/assets/props/`
| Need | Asset | Status |
|---|---|---|
| Harbor | `barrel_0`, `wooden_crate_0` | ✓ have |
| Cathedral | `archive_shelf_0` (as pew/shelf), `candle_0`, `oil_lamp_0` | ✓ have |
| Iron Cross / exits | `oil_lamp_0` (street lamp), `door_wood_0`, `door_iron_0` | ✓ have |
| Clue props (any district) | `case_file_0`, `evidence_photo_0`, `ledger_book_0`, `pocket_watch_0`, `talisman_paper_0`, `occult_dagger_0` | ✓ have |
| **Market stall / awning** | `market_stall` | **GEN** |
| **Cathedral altar / statue / pew bench** | `church_altar`, `saint_statue`, `wooden_pew` | **GEN** |
| **Bridge span / stone balustrade** | `stone_bridge`, `balustrade` | **GEN** |
| **Harbor dock / fishing net / moored boat** | `dock_planks`, `fishing_net`, `rowboat` | **GEN** |
| **Hanging lantern (market/bridge)** | `street_lantern` | **GEN** (or reuse `oil_lamp_0`) |

> If the GEN props slip, every district is still walkable + furnished with the ✓-have props; signature props are polish. Each district task notes its minimum viable prop set (all ✓-have) vs. nice-to-have (GEN).

### 3c. Characters / NPCs (place by `npc_id` only — art is the animation agent's)
| Role | Best `npc_id` art (`out/characters`) | Status |
|---|---|---|
| Klein (player) | `klein_down/up/left/right` | ✓ imported |
| Nighthawk | `nighthawk_captain_0` | ✓ have |
| Harbor folk | `npc_dockworker_0`, `witness_widow_0` (Dalia) | ✓ have |
| Cathedral | `priest_0`, `archivist_0` | ✓ have |
| Bridge Quarter | `lady_genteel_0`, `npc_constable_0` | ✓ have |
| Iron Cross | `npc_laborer_0` (Orin lamplighter, best-match), `informant_0` | ✓ have (best-match) |
| Crowd filler | `npc_civilian_man/woman_0`, `npc_street_urchin_0`, `npc_drunkard_0` | ✓ have |

### 3d. UI / map
| Need | Asset | Status |
|---|---|---|
| Map backdrop | `assets/ui/tingen_map.png` ← processed `ref/tingen_map.png` (1000×706; crop border/legend optional) | **ART** (trivial copy/crop) |
| Location marker | `assets/ui/map_marker.png` ← `out/ui/map_marker_0.png` | ✓ have |

### 3e. Establishing backgrounds (optional district cards) → `tingen/assets/backgrounds/`
`iron_cross_street_day/_bloodmoon`, `cathedral_plaza`, `university_quad`, `oldtown_street`, `backlund_skyline`, `warehouse_interior`, `library_archive`, `ritual_chamber`, `raphael_cemetery` — ✓ have in `out_image2/backgrounds`. **Harbor & Night-Market dedicated cards: GEN** (or reuse `oldtown_street`).

---

## 4. District ↔ map layout (follow `tingen_map.png`, image space 1000×706)

Derived from the reference geography (river wraps **S+E**; park/lake **W**; 延根大学 campus mid-right; dense grid core; outlying blocks across the E river). Coordinates are starting values; **tuned empirically in Task 13**.

| id | name | map_marker (cx,cy) | map_rect (x,y,w,h) | floor_tile | neighbours (edge-doors) |
|---|---|---|---|---|---|
| `iron_cross` | Iron Cross Street | (470, 300) | (360, 220, 230, 170) | cobblestone_wet | st_selena (N), night_market (S), harbor (SW) |
| `st_selena` | St. Selena Cathedral | (640, 230) | (560, 150, 200, 160) | archive_carpet | iron_cross (S), uptown (SE) |
| `night_market` | Night Market | (560, 470) | (450, 390, 220, 160) | brick_alley | iron_cross (N), harbor (W), uptown (E) |
| `harbor` | The Harbor | (300, 520) | (180, 440, 240, 160) | warehouse_concrete | iron_cross (NE), night_market (E) |
| `uptown` | Backlund Bridge Quarter | (760, 430) | (680, 350, 200, 170) | cobblestone_wet | night_market (W), st_selena (NW) |

Graph is fully connected; the map warp also reaches any hub directly.

---

## 5. Phase plan (overview)

- **Phase 0 — Asset prep** (Tasks 1–3): copy tiles/props/map art in + Nearest reimport; build `district_tileset.tres`; generate signature props (best-effort).
- **Phase 1 — Map + navigation system** (Tasks 4–7): `hubs.json`; **upgrade the one `DistrictMap`** to ref-image art + marker + click-to-warp *(after F1 go-ahead)*; headless validator.
- **Phase 2 — Hub recipe + Iron Cross** (Tasks 8–9): the reusable construction recipe, applied to rebuild `City.tscn`.
- **▶ CHECKPOINT** *(Mark's scope call: "Map + Iron Cross first")*: after **Task 9**, demo the map + the Iron Cross hub, get Mark's go-ahead, then run the follow-up batch.
- **Phase 3 — Stamp the 4 districts** (Tasks 10–12) *(follow-up)*: Harbor, St. Selena, Night Market + Bridge Quarter.
- **Phase 4 — Integrate, tune, screenshot** (Task 13) *(follow-up)*.

Each task ends in a verification step. Because verification here is **mostly manual playtest + screenshots**, automated gates are: (a) `Godot --headless --import` returns clean, (b) `tools/validate_hubs.gd` passes, (c) the existing `Godot --headless` test run is unaffected. Manual gates are explicit launch + screenshot steps.

---

## 6. Tasks

### Task 1: Copy floor tiles, props, and map art into the project (Nearest reimport)

**Files:**
- Create: `tingen/assets/tiles/{cobblestone_wet,brick_alley,warehouse_concrete,archive_carpet,ritual_stone,dead_grass}_0.png`
- Create: `tingen/assets/props/{barrel,wooden_crate,archive_shelf,door_iron}_0.png`
- Create: `tingen/assets/ui/tingen_map.png`, `tingen/assets/ui/map_marker.png`

- [ ] **Step 1: Copy the finished PNGs in** (assets stay generated outside `tingen/`; only finished PNGs ship)

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game"
for t in cobblestone_wet brick_alley warehouse_concrete archive_carpet ritual_stone dead_grass; do
  cp "asset-gen/out/tiles/${t}_0.png" "tingen/assets/tiles/${t}_0.png"; done
for p in barrel wooden_crate archive_shelf door_iron; do
  cp "asset-gen/out/props/${p}_0.png" "tingen/assets/props/${p}_0.png"; done
cp "asset-gen/out/ui/map_marker_0.png" "tingen/assets/ui/map_marker.png"
cp "asset-gen/ref/tingen_map.png" "tingen/assets/ui/tingen_map.png"   # ART: optional crop of border/legend later
```

- [ ] **Step 2: Force-reimport (defeat the stale `.ctex` cache)**

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen"
rm -f .godot/imported/cobblestone_wet_0.png-* .godot/imported/brick_alley_0.png-* \
      .godot/imported/warehouse_concrete_0.png-* .godot/imported/archive_carpet_0.png-* \
      .godot/imported/ritual_stone_0.png-* .godot/imported/dead_grass_0.png-* \
      .godot/imported/barrel_0.png-* .godot/imported/wooden_crate_0.png-* \
      .godot/imported/archive_shelf_0.png-* .godot/imported/door_iron_0.png-* \
      .godot/imported/tingen_map.png-* .godot/imported/map_marker.png-*
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . --import 2>&1 | tail -20
```

Expected: import completes with no `ERROR`; `.import` sidecars appear next to each new PNG.

- [ ] **Step 3: Set Nearest filter on the new images.** For each new `*.png.import`, ensure `compress/mode` default and set `flags/filter=false` is **not** what we want — instead set the import filter to Nearest. Easiest reliable path: open the editor once (`open -n -a "/Applications/Godot.app" --args --path "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen"`), select the new textures in the FileSystem dock, set Import → Filter = **Nearest**, Reimport. (The slice's existing tiles/props already use Nearest; match them.)

Verify: `grep -L "filter=0\|Nearest" tingen/assets/tiles/*.import` — investigate any file that still shows linear filtering. (Tiles especially must be Nearest to avoid seam bleed.)

- [ ] **Step 4: Commit** (only if Mark has OK'd committing; otherwise leave staged note)

```bash
git add tingen/assets/tiles tingen/assets/props tingen/assets/ui
git commit -m "assets: import district floor tiles, props, and map art (Nearest)"
```

---

### Task 2: Build the multi-source district TileSet

**Files:**
- Create: `tingen/assets/district_tileset.tres`

The existing `assets/wood_floor_tileset.tres` wraps one full-room `klein_floor` tile. District floors need several seamless tiles as separate atlas **sources** (one `source_id` per district), so `FloorTiler.source_id` can pick the right floor per hub.

- [ ] **Step 1: Read a tile's native size** (sets `texture_region_size`/`tile_size`)

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/asset-gen"
/Users/markma/miniconda3/bin/python3 -c "from PIL import Image; print(Image.open('out/tiles/cobblestone_wet_0.png').size)"
```

Use the printed `(W,H)` as `texture_region_size`/`tile_size` below (spec expects ~384²; use the actual value).

- [ ] **Step 2: Author `district_tileset.tres`** (one atlas source per tile; `source_id` order is the contract `hubs.json` floor ids map to)

```ini
[gd_resource type="TileSet" format=3]

[ext_resource type="Texture2D" path="res://assets/tiles/cobblestone_wet_0.png" id="t0"]
[ext_resource type="Texture2D" path="res://assets/tiles/warehouse_concrete_0.png" id="t1"]
[ext_resource type="Texture2D" path="res://assets/tiles/archive_carpet_0.png" id="t2"]
[ext_resource type="Texture2D" path="res://assets/tiles/brick_alley_0.png" id="t3"]
[ext_resource type="Texture2D" path="res://assets/tiles/dead_grass_0.png" id="t4"]
[ext_resource type="Texture2D" path="res://assets/tiles/ritual_stone_0.png" id="t5"]

[sub_resource type="TileSetAtlasSource" id="a0"]
texture = ExtResource("t0")
texture_region_size = Vector2i(384, 384)
0:0/0 = 0
[sub_resource type="TileSetAtlasSource" id="a1"]
texture = ExtResource("t1")
texture_region_size = Vector2i(384, 384)
0:0/0 = 0
[sub_resource type="TileSetAtlasSource" id="a2"]
texture = ExtResource("t2")
texture_region_size = Vector2i(384, 384)
0:0/0 = 0
[sub_resource type="TileSetAtlasSource" id="a3"]
texture = ExtResource("t3")
texture_region_size = Vector2i(384, 384)
0:0/0 = 0
[sub_resource type="TileSetAtlasSource" id="a4"]
texture = ExtResource("t4")
texture_region_size = Vector2i(384, 384)
0:0/0 = 0
[sub_resource type="TileSetAtlasSource" id="a5"]
texture = ExtResource("t5")
texture_region_size = Vector2i(384, 384)
0:0/0 = 0

[resource]
tile_size = Vector2i(384, 384)
sources/0 = SubResource("a0")
sources/1 = SubResource("a1")
sources/2 = SubResource("a2")
sources/3 = SubResource("a3")
sources/4 = SubResource("a4")
sources/5 = SubResource("a5")
```

**Floor-tile → `source_id` contract** (used by `hubs.json` `floor_tile` and `FloorTiler.source_id`): `cobblestone_wet=0`, `warehouse_concrete=1`, `archive_carpet=2`, `brick_alley=3`, `dead_grass=4`, `ritual_stone=5`.

- [ ] **Step 3: Verify it loads headless**

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen"
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . --import 2>&1 | grep -i "district_tileset\|ERROR" || echo "tileset imported clean"
```

Expected: no error referencing `district_tileset.tres`.

- [ ] **Step 4: Commit** (if OK'd): `git add tingen/assets/district_tileset.tres && git commit -m "assets: multi-source district floor TileSet"`

---

### Task 3: Generate signature district props (best-effort, non-blocking)

**Files:** Create `tingen/assets/props/{market_stall,wooden_pew,church_altar,stone_bridge,fishing_net,rowboat,dock_planks}_0.png`

- [ ] **Step 1: Add prompts to the generator.** In `asset-gen/generate_tingen_assets.py`, add the props above to the props list following the existing entry format (match `STYLE_GUIDE.md` palette + the existing prop style). Do **not** change unrelated entries.
- [ ] **Step 2: Generate** (API keys load at runtime from `/Users/markma/Desktop/Yumina/.env`; print only booleans/lengths, never values):

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/asset-gen"
/Users/markma/miniconda3/bin/python3 generate_tingen_assets.py --category props --only market_stall,wooden_pew,church_altar,stone_bridge,fishing_net,rowboat,dock_planks
```
(If the generator lacks `--only`, generate the props category and keep just the new files.)

- [ ] **Step 3: Copy in + Nearest reimport** the new props (same pattern as Task 1, Steps 1–3).
- [ ] **Step 4: Commit** (if OK'd).

> **Status handling:** This task is **non-blocking**. If generation is over budget or low quality, mark each district's signature props as "deferred" and proceed with the ✓-have minimum sets. Report `DONE_WITH_CONCERNS` listing which props were skipped.

---

### Task 4: `data/hubs.json` — the hub & travel registry

**Files:** Create `tingen/data/hubs.json`

- [ ] **Step 1: Author the registry.** `player_start` and `exits[].at` are in hub-scene coordinates (the hub's playable area is ~`(120,120)`–`(1080,680)`, matching `City.tscn`); `map_rect`/`map_marker` are in `tingen_map.png` image space (1000×706, from §4). `exits[].at` are starting positions tuned in each hub task.

```json
[
  {
    "id": "iron_cross", "name": "Iron Cross Street",
    "scene": "res://scenes/City.tscn", "player_start": [600, 400], "floor_tile": "cobblestone_wet",
    "map_marker": [470, 300], "map_rect": [360, 220, 230, 170],
    "exits": [
      {"to": "st_selena",    "scene": "res://scenes/StSelena.tscn",     "at": [600, 150], "prompt": "North to St. Selena Cathedral"},
      {"to": "night_market", "scene": "res://scenes/NightMarket.tscn",  "at": [600, 650], "prompt": "South to the Night Market"},
      {"to": "harbor",       "scene": "res://scenes/Harbor.tscn",       "at": [160, 600], "prompt": "Down to the Harbor"}
    ]
  },
  {
    "id": "st_selena", "name": "St. Selena Cathedral",
    "scene": "res://scenes/StSelena.tscn", "player_start": [600, 600], "floor_tile": "archive_carpet",
    "map_marker": [640, 230], "map_rect": [560, 150, 200, 160],
    "exits": [
      {"to": "iron_cross", "scene": "res://scenes/City.tscn",          "at": [600, 650], "prompt": "Out to Iron Cross Street"},
      {"to": "uptown",     "scene": "res://scenes/BridgeQuarter.tscn", "at": [950, 500], "prompt": "East to the Bridge Quarter"}
    ]
  },
  {
    "id": "night_market", "name": "Night Market",
    "scene": "res://scenes/NightMarket.tscn", "player_start": [600, 200], "floor_tile": "brick_alley",
    "map_marker": [560, 470], "map_rect": [450, 390, 220, 160],
    "exits": [
      {"to": "iron_cross", "scene": "res://scenes/City.tscn",          "at": [600, 150], "prompt": "North to Iron Cross Street"},
      {"to": "harbor",     "scene": "res://scenes/Harbor.tscn",        "at": [160, 400], "prompt": "West to the Harbor"},
      {"to": "uptown",     "scene": "res://scenes/BridgeQuarter.tscn", "at": [950, 400], "prompt": "East to the Bridge Quarter"}
    ]
  },
  {
    "id": "harbor", "name": "The Harbor",
    "scene": "res://scenes/Harbor.tscn", "player_start": [600, 400], "floor_tile": "warehouse_concrete",
    "map_marker": [300, 520], "map_rect": [180, 440, 240, 160],
    "exits": [
      {"to": "iron_cross",   "scene": "res://scenes/City.tscn",         "at": [1000, 200], "prompt": "Up to Iron Cross Street"},
      {"to": "night_market", "scene": "res://scenes/NightMarket.tscn",  "at": [1000, 400], "prompt": "East to the Night Market"}
    ]
  },
  {
    "id": "uptown", "name": "Backlund Bridge Quarter",
    "scene": "res://scenes/BridgeQuarter.tscn", "player_start": [600, 400], "floor_tile": "cobblestone_wet",
    "map_marker": [760, 430], "map_rect": [680, 350, 200, 170],
    "exits": [
      {"to": "night_market", "scene": "res://scenes/NightMarket.tscn", "at": [200, 400], "prompt": "West to the Night Market"},
      {"to": "st_selena",    "scene": "res://scenes/StSelena.tscn",    "at": [200, 500], "prompt": "North to St. Selena Cathedral"}
    ]
  }
]
```

- [ ] **Step 2: Validate JSON parses**

```bash
/Users/markma/miniconda3/bin/python3 -c "import json; d=json.load(open('/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen/data/hubs.json')); print('hubs:', [h['id'] for h in d])"
```

Expected: `hubs: ['iron_cross', 'st_selena', 'night_market', 'harbor', 'uptown']`.

- [ ] **Step 3: Commit** (if OK'd).

---

### Task 5: `tools/validate_hubs.gd` — headless integrity check

**Files:** Create `tingen/tools/validate_hubs.gd`

This is our automated gate (separate from the animation agent's `tests/run_tests.gd`). It asserts every hub `scene` resolves, every `floor_tile` is a known source id, and every `exit.to`/`exit.scene` is consistent.

- [ ] **Step 1: Write the validator**

```gdscript
extends SceneTree
## Headless check: `Godot --headless --path tingen -s res://tools/validate_hubs.gd`
## Exits 0 if hubs.json is internally consistent and all referenced scenes load, else 1.

const HUBS := "res://data/hubs.json"
const FLOOR_IDS := {
    "cobblestone_wet": 0, "warehouse_concrete": 1, "archive_carpet": 2,
    "brick_alley": 3, "dead_grass": 4, "ritual_stone": 5,
}

func _init() -> void:
    var fails: Array[String] = []
    var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(HUBS))
    if typeof(raw) != TYPE_ARRAY:
        push_error("hubs.json did not parse to an array"); quit(1); return
    var ids := {}
    for h in raw:
        ids[h.get("id", "?")] = h
    for h in raw:
        var id: String = h.get("id", "?")
        if not FLOOR_IDS.has(h.get("floor_tile", "")):
            fails.append("%s: unknown floor_tile %s" % [id, h.get("floor_tile")])
        var scene: String = h.get("scene", "")
        if not ResourceLoader.exists(scene):
            fails.append("%s: scene missing %s" % [id, scene])
        for e in h.get("exits", []):
            if not ids.has(e.get("to", "")):
                fails.append("%s: exit -> unknown hub %s" % [id, e.get("to")])
            if e.get("scene", "") != ids.get(e.get("to", {}), {}).get("scene", ""):
                fails.append("%s: exit scene mismatch for %s" % [id, e.get("to")])
    if fails.is_empty():
        print("validate_hubs: OK (%d hubs)" % raw.size()); quit(0)
    else:
        for f in fails: push_error(f)
        quit(1)
```

- [ ] **Step 2: Run it** (after Task 4; will report missing hub scenes until Tasks 9–12 land — that's expected and tells you what's left)

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen"
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . -s res://tools/validate_hubs.gd; echo "exit=$?"
```

Expected now: lists `scene missing res://scenes/{Harbor,StSelena,NightMarket,BridgeQuarter}.tscn` (City exists) and `exit=1`. After Task 12 it prints `validate_hubs: OK (5 hubs)` and `exit=0`.

- [ ] **Step 3: Commit** (if OK'd).

---

### Task 6: ⚠ Upgrade the one `DistrictMap` to the ref-image map (art + marker + click-to-warp)

**Files (animation-agent-owned — start ONLY after Mark's F1 go-ahead):**
- Modify: `tingen/ui/DistrictMap.gd`
- Modify: `tingen/ui/DistrictMap.tscn`

> This is *the* map (M key). The upgrade is **non-destructive**: keep the existing risk-tint / hover / readout and *add* the real `tingen_map.png` backdrop, a player-location marker, and click-to-warp. **Read the current `DistrictMap.gd` and `.tscn` first and apply these changes surgically — do not wholesale-replace**, in case the animation agent has edited them. The existing nodes are `_canvas = $Center/Frame/VBox/Map` (a `Control`) and `_readout = $Center/Frame/VBox/Readout`; the existing helpers `_risk_for(d)`, `_load()`, `toggle()`, `_hover_index` are reused.

- [ ] **Step 0: Confirm the F1 go-ahead.** Verify Mark OK'd editing `DistrictMap` (or coordinated with the animation agent). If not, STOP and report `BLOCKED`.

- [ ] **Step 1: Load hub data + map art.** Add near the top of `DistrictMap.gd`:

```gdscript
const HUBS_PATH := "res://data/hubs.json"
const MAP_ART := preload("res://assets/ui/tingen_map.png")
const MAP_MARKER := preload("res://assets/ui/map_marker.png")
const MAP_IMG_SIZE := Vector2(1000, 706)   # tingen_map.png native size; hubs.json coords live in this space
var hubs: Array = []
```

Extend `_load()` so it also parses `hubs.json` into `hubs` (same `FileAccess.get_file_as_string` + `JSON.parse_string` + `TYPE_ARRAY` guard already used for `districts`).

- [ ] **Step 2: Add lookup helpers** (append to the script):

```gdscript
func _district_by_id(id: String) -> Dictionary:
    for d in districts:
        if String(d.get("id", "")) == id:
            return d
    return {}

func _hub_index_at(pos: Vector2, s: Vector2) -> int:
    for i in hubs.size():
        var r: Array = hubs[i].get("map_rect", [0, 0, 0, 0])
        if Rect2(Vector2(r[0], r[1]) * s, Vector2(r[2], r[3]) * s).has_point(pos):
            return i
    return -1

func _current_scene() -> String:
    var gcs := get_tree().get_nodes_in_group("game_controller")   # GameController adds itself in _ready()
    return String(gcs[0].current_scene_path) if gcs.size() > 0 else ""

func _hub_by_scene(scene: String) -> Dictionary:
    for h in hubs:
        if String(h.get("scene", "")) == scene:
            return h
    return {}
```

- [ ] **Step 3: Replace `_draw_map()`** — real art backdrop + risk-tinted hub hotspots over `map_rect` + names + a feet-anchored location marker:

```gdscript
func _draw_map() -> void:
    var s: Vector2 = _canvas.size / MAP_IMG_SIZE                       # image-space -> canvas-space
    _canvas.draw_texture_rect(MAP_ART, Rect2(Vector2.ZERO, _canvas.size), false)
    for i in hubs.size():
        var h: Dictionary = hubs[i]
        var r: Array = h.get("map_rect", [0, 0, 0, 0])
        var rect := Rect2(Vector2(r[0], r[1]) * s, Vector2(r[2], r[3]) * s)
        var d := _district_by_id(String(h.get("id", "")))
        var risk: float = _risk_for(d) if not d.is_empty() else 0.0
        var fill := LOW_RISK.lerp(HIGH_RISK, risk)
        fill.a = 0.32 if i == _hover_index else 0.16                   # tint shows risk; brighter on hover
        _canvas.draw_rect(rect, fill, true)
        _canvas.draw_rect(rect, Color(0.95, 0.92, 0.85, 0.55), false, 1.5)
        _canvas.draw_string(ThemeDB.fallback_font, rect.position + Vector2(6, 16),
            String(h.get("name", h.get("id", "?"))), HORIZONTAL_ALIGNMENT_LEFT, rect.size.x, 12)
    var cur := _hub_by_scene(_current_scene())                        # player-location marker
    if not cur.is_empty():
        var m: Array = cur.get("map_marker", [0, 0])
        var mp := Vector2(m[0], m[1]) * s
        _canvas.draw_texture(MAP_MARKER, mp - Vector2(MAP_MARKER.get_width() * 0.5, MAP_MARKER.get_height()))
```

(The old `_poly_of`/`_centroid` polygon rendering is superseded; you may delete `_poly_of`/`_centroid` if nothing else uses them, or leave them unused.)

- [ ] **Step 4: Replace `_on_map_input()`** — hover + **click-to-warp** in `map_rect` space:

```gdscript
func _on_map_input(event: InputEvent) -> void:
    var s: Vector2 = _canvas.size / MAP_IMG_SIZE
    if event is InputEventMouseMotion:
        var prev := _hover_index
        _hover_index = _hub_index_at(event.position, s)
        if _hover_index != prev:
            _update_readout()
            _canvas.queue_redraw()
    elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
        var i := _hub_index_at(event.position, s)
        if i >= 0:
            var scene := String(hubs[i].get("scene", ""))
            if scene != "":
                visible = false
                WorldState.transition_requested.emit(scene, "")      # same backbone as edge-doors
```

Update `_update_readout()` to read the hovered **hub** (`hubs[_hover_index]`) and its risk via `_district_by_id(hubs[_hover_index].id)` — keep the existing `"%s — risk %d%% (%s)"` format.

- [ ] **Step 5: Marker tracks per-open.** `toggle()` already `queue_redraw()`s when shown, so `_draw_map()` recomputes `_current_scene()` and repositions the marker every time the map opens — sufficient for a location tracker. (The map also redraws on `WorldState.state_changed`.)

- [ ] **Step 6: Size the Map canvas to the art** in `ui/DistrictMap.tscn`. Read the file; set `$Center/Frame/VBox/Map` `custom_minimum_size` to the art's aspect (e.g., `Vector2(760, 537)` ≈ 1000×706 × 0.76) so the texture + hotspots have room. Leave `Frame`, `Readout`, and every other HUD node untouched.

- [ ] **Step 7: Reimport + manual smoke (the M map).**

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen" && /Applications/Godot.app/Contents/MacOS/Godot --headless --path . --import >/dev/null 2>&1
open -n -a "/Applications/Godot.app" --args --path "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen" res://scenes/IntroMain.tscn
```

In game: bedroom → Door → `City.tscn`. Press **M**: the **Tingen map art** fills the panel; Iron Cross is tinted (by risk) + labeled with the **location marker** on it; hovering a district updates the readout; clicking Iron Cross reloads City (other districts warp once their hubs exist, Tasks 9–12). There is exactly **one** map, on **M**.

- [ ] **Step 8: Regression — headless tests unaffected** (do not edit `tests/run_tests.gd`):

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen"
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . -s res://tests/run_tests.gd 2>&1 | tail -15
```

Expected: same pass/fail profile as before (no new failures from `DistrictMap`).

- [ ] **Step 9: Commit** (if OK'd): `git add tingen/ui/DistrictMap.gd tingen/ui/DistrictMap.tscn && git commit -m "feat: upgrade DistrictMap to the ref-image map (art backdrop + location marker + click-to-warp)"`

---

### Task 7: Wire `WorldMap` into `GameController` + add `toggle_travel` input

**Files:**
- Modify: `tingen/src/GameController.gd`
- Modify: `tingen/project.godot` (`[input]`, additive)

- [ ] **Step 1: Add the input action.** Append to `project.godot` `[input]` (mirror the existing `toggle_map` block; **G** = physical_keycode 71):

```ini
toggle_travel={
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":71,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]
}
```

- [ ] **Step 2: Mount the overlay in `GameController._ready()`** and add a current-district helper + input handler. Add to `src/GameController.gd`:

```gdscript
const WORLD_MAP_SCENE: PackedScene = preload("res://ui/WorldMap.tscn")
var _world_map: CanvasLayer = null
```

In `_ready()` (after the existing body):

```gdscript
    _world_map = WORLD_MAP_SCENE.instantiate()
    add_child(_world_map)                       # persists across _swap_world (sibling of $World)
```

Add an input handler + helper:

```gdscript
func _unhandled_input(event: InputEvent) -> void:
    if event.is_action_pressed("toggle_travel") and _world_map:
        _world_map.toggle(current_scene_path)
        get_viewport().set_input_as_handled()

## Current district id from hubs.json, or "" when not in a mapped hub.
func current_district_id() -> String:
    var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/hubs.json"))
    if typeof(raw) == TYPE_ARRAY:
        for h in raw:
            if String(h.get("scene", "")) == current_scene_path:
                return String(h.get("id", ""))
    return ""
```

- [ ] **Step 3: Manual smoke — map opens & warps.** Reimport, then launch IntroMain and verify the travel map:

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen" && /Applications/Godot.app/Contents/MacOS/Godot --headless --path . --import >/dev/null 2>&1
open -n -a "/Applications/Godot.app" --args --path "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen" res://scenes/IntroMain.tscn
```

In game: walk Klein through the Door → `City.tscn`. Press **G** → the Tingen map appears with a marker over Iron Cross. Click the Night Market hotspot region → world swaps to `NightMarket.tscn` (will exist after Task 11; until then click Iron Cross's own region to confirm it reloads). Press **G** again → closes. Confirm **M** still opens the *other* (risk) map unaffected.

- [ ] **Step 4: Regression — headless test run unaffected** (do not edit `tests/run_tests.gd`; just confirm green):

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen"
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . -s res://tests/run_tests.gd 2>&1 | tail -15
```

Expected: same pass/fail profile as before this task (no new failures attributable to `GameController`).

- [ ] **Step 5: Commit** (if OK'd): `git add tingen/src/GameController.gd tingen/project.godot && git commit -m "feat: travel map overlay + toggle_travel (G), mounted by GameController"`

---

### Task 8: The Hub Construction Recipe (reference for Tasks 9–12)

This is the canonical recipe each district task applies with its own parameters. **No file is created by this task** — it documents the node structure and the exact `.tscn` skeleton so districts are consistent. (Implementers of Tasks 9–12 receive this text plus their district's parameter block.)

A hub `.tscn` is a `Node2D` with `y_sort_enabled = true` and these children:

```ini
[gd_scene load_steps=? format=3]

[ext_resource type="PackedScene" path="res://scenes/Player.tscn" id="player"]
[ext_resource type="PackedScene" path="res://scenes/Interactable.tscn" id="interactable"]
[ext_resource type="PackedScene" path="res://scenes/NPC.tscn" id="npc"]
[ext_resource type="PackedScene" path="res://scenes/Prop.tscn" id="prop"]
[ext_resource type="Script"      path="res://src/DayNightTint.gd" id="tint"]
[ext_resource type="Script"      path="res://src/FloorTiler.gd"   id="floor"]
[ext_resource type="TileSet"     path="res://assets/district_tileset.tres" id="tileset"]
# + a Texture2D ext_resource per Prop icon used below
# + RectangleShape2D sub_resources for the wall border + furniture footprints

[node name="<HubName>" type="Node2D"]
y_sort_enabled = true

[node name="DayNight" type="CanvasModulate" parent="."]
script = ExtResource("tint")

# Floor: FloorTiler fills cols×rows of the district's tile. cell≈384 ⇒ ~3×2 covers ~1100×760.
[node name="Floor" type="TileMapLayer" parent="."]
y_sort_enabled = false
tile_set = ExtResource("tileset")
script = ExtResource("floor")
cols = 3
rows = 2
source_id = <FLOOR SOURCE ID from §Task2 contract>
# position/scale the layer so cells cover the playable area (tune in playtest)

# Walls + irregular footprints: a StaticBody2D border (matches IntroRoom's "Solids")
[node name="Solids" type="StaticBody2D" parent="."]
[node name="WTop"    type="CollisionShape2D" parent="Solids"]   # position + RectangleShape2D
[node name="WBottom" type="CollisionShape2D" parent="Solids"]
[node name="WLeft"   type="CollisionShape2D" parent="Solids"]
[node name="WRight"  type="CollisionShape2D" parent="Solids"]

# Player (keeps its follow Camera2D enabled — do NOT disable it as IntroRoom did)
[node name="Player" parent="." instance=ExtResource("player")]
position = Vector2(<player_start from hubs.json>)

# Props: Prop.tscn instances, each a direct child so Y-sort occludes by feet.
[node name="<PropName>" parent="." instance=ExtResource("prop")]
position = Vector2(x, y)
icon = ExtResource("<prop texture>")
icon_px = <height px>
footprint = Vector2(<w>, <h>)
solid = true

# NPCs: by npc_id only (art handled elsewhere)
[node name="<NpcName>" parent="." instance=ExtResource("npc")]
position = Vector2(x, y)
npc_id = "<id>"

# Interactables: clue/dialogue points AND edge-doors (target_scene = neighbour hub)
[node name="ExitTo<Neighbour>" parent="." instance=ExtResource("interactable")]
position = Vector2(<exit.at>)
prompt_text = "<exit.prompt>"
tint = Color(0.7, 0.6, 0.45, 0)          # invisible E-zone at the painted edge
target_scene = "<neighbour scene>"
```

**Recipe rules:**
1. Root `y_sort_enabled = true`; `Floor` layer `y_sort_enabled = false` and drawn under everything.
2. Wall border insets the playable area to ~`(120,120)`–`(1080,680)` (like `City.tscn`); add extra `StaticBody2D` colliders for large scenery the player must walk around.
3. Each `Prop` is feet-anchored automatically (`Prop.gd`); give big scenery a `footprint` so the player rounds it; set `solid=false` for floor decals (rugs, blood pools, dock planks).
4. Player keeps its `Camera2D` (follow). Tune `zoom` per hub at playtest if `(2,2)` is too tight.
5. Edge-doors are `Interactable` instances with `target_scene` = the neighbour's scene and `position` = the `exit.at` from `hubs.json`; invisible tint (alpha 0), placed at the map-appropriate edge.
6. One clue or dialogue `Interactable` per district keeps each hub a real investigation beat (reuse `clue_id`/`dialogue_id`).

**Verification of the recipe itself:** none (documentation task). Tasks 9–12 verify by playtest.

---

### Task 9: Rebuild `City.tscn` into the Iron Cross hub (reference district)

**Files:** Modify `tingen/scenes/City.tscn`

Apply the Task 8 recipe. Iron Cross is the crossroads heart: cobblestone, tenements, street lamps, the Nighthawk contact, Orin the lamplighter, and the warehouse rite-site nod. Preserve the existing **Nighthawk** (`dialogue_id="nighthawk"`), **Orin** (`lamplighter_orin`), **Dalia** (`fishwife_dalia`) wiring.

**Parameters:**
- Floor: `cobblestone_wet` → `source_id = 0`.
- `player_start = (600, 400)`.
- Props (✓-have): `oil_lamp_0` street lamps at `(300,300),(700,300),(500,520)` (`icon_px≈90`, small `footprint`); `barrel_0` at `(220,360)`; `wooden_crate_0` at `(260,380)`; `archive_shelf_0` (shopfront) at `(820,260)`; `blood_pool_0` decal at `(520,360)` (`solid=false`).
- NPCs (keep): Nighthawk `Interactable dialogue_id="nighthawk"` at `(820,320)`; Orin `npc_id="lamplighter_orin"` at `(400,240)`; Dalia `npc_id="fishwife_dalia"` at `(820,220)`.
- One clue point: `Interactable clue_id="iron_cross_handbill"` (add to `data/clues.json` if missing — see Step 2) at `(480,260)`, `prompt_text="Read the handbill"`, `thought="A Nighthawk recruiting bill — fresh ink."`.
- Edge-doors (from `hubs.json`): `ExitToStSelena` → `StSelena.tscn` at `(600,150)`; `ExitToNightMarket` → `NightMarket.tscn` at `(600,650)`; `ExitToHarbor` → `Harbor.tscn` at `(160,600)`.

- [ ] **Step 1: Rewrite `City.tscn`** per the recipe with the parameters above (replace the two `Polygon2D`s + Title stub; keep `DayNight`). Wall border insets `(120,120)`–`(1080,680)`: `WTop (600,120)` size `(960,16)`, `WBottom (600,680)` size `(960,16)`, `WLeft (120,400)` size `(16,560)`, `WRight (1080,400)` size `(16,560)`.
- [ ] **Step 2: Ensure referenced ids exist.** Check `data/clues.json` has `iron_cross_handbill`; if not, add a minimal entry matching the file's schema. (`grep -n iron_cross_handbill tingen/data/clues.json`.) Confirm `dialogue.json` still has `nighthawk`.
- [ ] **Step 3: Headless load**

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen"
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . --import 2>&1 | grep -i "City.tscn\|ERROR" || echo "City imports clean"
```

- [ ] **Step 4: Playtest** (launch `IntroMain`, go through the Door to City — or launch `City.tscn` directly inside a shell by temporarily running `IntroMain` and warping):

```bash
open -n -a "/Applications/Godot.app" --args --path "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen" res://scenes/IntroMain.tscn
```

Verify: cobblestone floor renders (Nearest, no seams); Klein walks the crossroads and is **occluded correctly** by lamps/shelf when above them, in front when below; collides with walls + props; **E** talks to the Nighthawk and reads the handbill (clue fires); **G** opens the map with the marker on Iron Cross. Walking onto each edge-door zone shows its prompt; **E** transitions (targets exist after Tasks 10–12 — until then verify the prompt appears and the transition attempt is logged).

- [ ] **Step 5: Screenshot** for review (`mcp__computer-use__screenshot` or system capture) → save under `asset-gen/out_image2/` (outside `tingen/`).
- [ ] **Step 6: Commit** (if OK'd): `git add tingen/scenes/City.tscn tingen/data/clues.json && git commit -m "feat: Iron Cross walkable hub (cobbles, props, NPCs, edge-doors)"`

---

### Task 10: `Harbor.tscn`

**Files:** Create `tingen/scenes/Harbor.tscn`

Apply the Task 8 recipe. Wet concrete docks on the river; crates, barrels, nets, a moored boat; dockworkers.

**Parameters:**
- Floor: `warehouse_concrete` → `source_id = 1`. `player_start = (600,400)`.
- Props: minimum (✓-have) `barrel_0` ×3 at `(240,300),(300,300),(270,340)`; `wooden_crate_0` ×3 at `(800,300),(860,300),(830,260)`; `oil_lamp_0` quay lamps at `(200,250),(1000,250)`. Nice-to-have (GEN): `dock_planks_0` decal strip along the south (`solid=false`), `fishing_net_0` at `(360,520)`, `rowboat_0` at `(900,560)`.
- Water edge: a non-walkable south band — extend the wall border so the bottom ~120px reads as water (collider across the south at `y≈600`).
- NPCs: `npc_dockworker_0` at `(420,300)`; Dalia `npc_id="fishwife_dalia"` at `(700,420)` (the fishwife belongs at the harbor).
- Clue/dialogue point: `Interactable clue_id="harbor_manifest"` (add to clues.json) at `(520,300)`, `prompt_text="Inspect the cargo manifest"`.
- Edge-doors: `ExitToIronCross` → `City.tscn` at `(1000,200)`; `ExitToNightMarket` → `NightMarket.tscn` at `(1000,400)`.

- [ ] **Step 1: Author `Harbor.tscn`** per recipe + parameters.
- [ ] **Step 2: Headless load** (`grep -i "Harbor.tscn\|ERROR"`).
- [ ] **Step 3: Playtest** via map-warp from Iron Cross (press G → click Harbor) **or** the Iron Cross→Harbor edge-door: floor renders; collide with crates/barrels and the water edge; **E** on the manifest fires the clue; both edge-doors return correctly; marker sits on the Harbor when G is pressed here.
- [ ] **Step 4: Screenshot** → `asset-gen/out_image2/`.
- [ ] **Step 5: Commit** (if OK'd).

---

### Task 11: `StSelena.tscn` + `NightMarket.tscn`

**Files:** Create `tingen/scenes/StSelena.tscn`, `tingen/scenes/NightMarket.tscn`

Two hubs, same recipe.

**St. Selena Cathedral parameters:**
- Floor: `archive_carpet` → `source_id = 2`. `player_start = (600,600)` (enter from the south doors).
- Props: ✓-have `archive_shelf_0` as pew rows at `(360,300),(360,380),(840,300),(840,380)`; `candle_0` ×4 flanking the altar at `(540,200),(660,200),(540,240),(660,240)`; `oil_lamp_0` at `(300,260),(900,260)`. GEN nice-to-have: `church_altar_0` at `(600,180)`, `wooden_pew_0` rows, `saint_statue_0` at `(480,180)`/`(720,180)`.
- NPC: `priest_0` at `(600,260)`; `archivist_0` at `(840,440)`.
- Clue/dialogue: `Interactable clue_id="selena_reliquary"` at `(600,300)`, `prompt_text="Examine the reliquary"`.
- Edge-doors: `ExitToIronCross` → `City.tscn` at `(600,650)`; `ExitToBridgeQuarter` → `BridgeQuarter.tscn` at `(950,500)`.

**Night Market parameters:**
- Floor: `brick_alley` → `source_id = 3`. `player_start = (600,200)` (enter from the north).
- Props: ✓-have `wooden_crate_0`/`barrel_0` as stall bases clustered at `(280,300),(320,300),(760,300),(800,300),(280,460),(760,460)`; `oil_lamp_0` hanging lamps at `(400,260),(600,260),(800,260)`. GEN nice-to-have: `market_stall_0` ×4 at the crate clusters; `street_lantern_0` strung overhead.
- NPCs: `npc_civilian_woman_0` (vendor) at `(360,320)`; `npc_drunkard_0` at `(820,480)`; `npc_street_urchin_0` at `(500,420)`.
- Clue/dialogue: `Interactable dialogue_id="market_vendor"` if present in `dialogue.json`, else `clue_id="market_whisper"` at `(600,360)`, `prompt_text="Listen to the market talk"`.
- Edge-doors: `ExitToIronCross` → `City.tscn` at `(600,150)`; `ExitToHarbor` → `Harbor.tscn` at `(160,400)`; `ExitToBridgeQuarter` → `BridgeQuarter.tscn` at `(1000,400)`.

- [ ] **Step 1: Author both scenes** per recipe + parameters. Add any new `clue_id`s to `data/clues.json`; only use a `dialogue_id` that exists in `data/dialogue.json` (else use a `clue_id`).
- [ ] **Step 2: Headless load** both (`grep -i "StSelena.tscn\|NightMarket.tscn\|ERROR"`).
- [ ] **Step 3: Playtest** each via map-warp + the reciprocal edge-doors (Iron Cross↔St. Selena, Iron Cross↔Night Market): floors render; props occlude/collide; clue/dialogue fires; doors land in the right hub; marker tracks.
- [ ] **Step 4: Screenshots** → `asset-gen/out_image2/`.
- [ ] **Step 5: Commit** (if OK'd).

---

### Task 12: `BridgeQuarter.tscn`

**Files:** Create `tingen/scenes/BridgeQuarter.tscn`

Apply the recipe. Backlund Bridge Quarter: fine cobbles by the river, a stone bridge, gas lamps, genteel residents, a constable.

**Parameters:**
- Floor: `cobblestone_wet` → `source_id = 0`; a `dead_grass` (`source_id = 4`) riverbank strip (second small `FloorTiler` along the south, or a `dead_grass` decal `Prop`). `player_start = (600,400)`.
- Props: ✓-have `oil_lamp_0` gas lamps at `(300,300),(600,300),(900,300)`; `barrel_0`/`wooden_crate_0` dockside at `(240,520),(280,520)`. GEN nice-to-have: `stone_bridge_0` spanning the south river at `(600,560)` (large, `solid=false` walkway with balustrade colliders), `balustrade_0` rails.
- River edge: south band non-walkable except the bridge mouth (wall colliders with a gap at the bridge).
- NPCs: `lady_genteel_0` at `(520,300)`; `npc_constable_0` at `(760,360)`.
- Clue/dialogue: `Interactable clue_id="bridge_letter"` at `(600,340)`, `prompt_text="Read the dropped letter"`.
- Edge-doors: `ExitToNightMarket` → `NightMarket.tscn` at `(200,400)`; `ExitToStSelena` → `StSelena.tscn` at `(200,500)`.

- [ ] **Step 1: Author `BridgeQuarter.tscn`** per recipe + parameters; add `bridge_letter` to `data/clues.json`.
- [ ] **Step 2: Headless load** (`grep -i "BridgeQuarter.tscn\|ERROR"`).
- [ ] **Step 3: Run the validator — now all 5 resolve**

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen"
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . -s res://tools/validate_hubs.gd; echo "exit=$?"
```

Expected: `validate_hubs: OK (5 hubs)` and `exit=0`.

- [ ] **Step 4: Playtest** via map-warp + edge-doors; **Step 5: Screenshot**; **Step 6: Commit** (if OK'd).

---

### Task 13: Integration playtest, tuning, and review screenshots

**Files:** tune `tingen/data/hubs.json` (`map_rect`/`map_marker`/`exit.at`), per-hub `Floor` cols/rows + camera `zoom`, prop coords.

- [ ] **Step 1: Full traversal loop.** Launch `IntroMain`, leave the bedroom, then visit all five districts using **only walkable edge-doors** (IronCross→StSelena→Uptown→NightMarket→Harbor→IronCross). Confirm each transition lands the player at the intended `exit.at`/`player_start` and the destination floor/props render.
- [ ] **Step 2: Map fidelity pass.** Press **G** in each district. Confirm (a) the marker sits over the correct district on the real map art, and (b) clicking each hotspot warps to the right hub. Nudge `map_rect`/`map_marker` in `hubs.json` until hotspots sit on the painted districts and markers land on the right features (this is the "follows the tingen map closely" acceptance).
- [ ] **Step 3: Camera & scale tune.** If `(2,2)` zoom feels too tight for roaming, set a per-hub `Camera2D.zoom` (e.g., `(1.4,1.4)`); confirm walls keep the camera from showing void (add `Camera2D` limits if needed). Confirm prop `icon_px` reads ~2–3 floor-cells tall (HD-2D grounding) and Nearest filtering holds (no blur, no tile seams).
- [ ] **Step 4: Regression.** Re-run the headless test suite and the hub validator; both green / `OK`.

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game/tingen"
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . -s res://tests/run_tests.gd 2>&1 | tail -8
/Applications/Godot.app/Contents/MacOS/Godot --headless --path . -s res://tools/validate_hubs.gd; echo "exit=$?"
```

- [ ] **Step 5: Capture review screenshots** of all five districts + the open map with marker → `asset-gen/out_image2/` (outside `tingen/`). Summarize for Mark: does the HD-2D seam hold, or pixelate later? Are two maps (M risk / G travel) acceptable, or schedule the merge (F1)?
- [ ] **Step 6: Final commit** (if OK'd): `git add tingen/data/hubs.json tingen/scenes/*.tscn && git commit -m "tune: map hotspots, hub cameras, props after integration playtest"`

---

## 7. Verification summary (what "done" means)

- **Automated:** `Godot --headless --path tingen --import` clean; `tools/validate_hubs.gd` → `OK (5 hubs)`; existing `tests/run_tests.gd` unchanged.
- **Manual:** From the bedroom you can roam into all five districts via edge-doors **and** the **G** travel map; the map art is `tingen_map.png` with a location marker that tracks the current district; each hub has a tiled floor, Y-sorted furniture you walk around, NPCs, and at least one working clue/dialogue beat; **M** (animation agent's risk map) still works untouched.
- **Boundary honored:** no edits to any animation-agent-owned file; `docs/superpowers/` stays local/gitignored; no commits without Mark's explicit OK; generated art stays outside `tingen/` (only finished PNGs copied in).

## 8. Self-review notes

- **Spec coverage:** map system ✓ (Tasks 6–7), player location tracker ✓ (`WorldMap._mark_current`), build-out districts with props ✓ (Tasks 9–12), asset list ✓ (§3), navigable connections ✓ (edge-doors in every hub + warp), "follows tingen map closely" ✓ (real art backdrop + §4 placement + Task 13 fidelity pass).
- **Type consistency:** floor-tile→source-id contract (Task 2) is reused verbatim by `hubs.json` `floor_tile` and `Floor.source_id`; `WorldMap` reads `map_rect`/`map_marker`/`scene` exactly as written in `hubs.json`; `current_scene_path` (existing) is the join key for the marker.
- **Risks/placeholders:** tile pixel size is read at build time (Task 2 Step 1), not assumed; GEN props are explicitly non-blocking with ✓-have fallbacks; map hotspot coords are starting values explicitly tuned in Task 13; NPC art deliberately left to the animation agent.
