# Klein's Bedroom (IntroRoom) Tilemap Slice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `IntroRoom.tscn`'s placeholder flats with real art — a `wood_floor` TileMapLayer floor, the detective player sprite, the four interactables' real prop sprites, and Y-sorted furniture — while keeping every existing clue/door behavior intact.

**Architecture:** Retrofit the existing scene. Y-sort the IntroRoom **root** so the player, interactables, and furniture (all direct children) occlude each other by depth. The floor is a real `TileMapLayer` filled programmatically (`FloorTiler.gd`) from a one-tile `TileSet` built on the seamless `wood_floor` texture — no editor hand-painting. Per-instance art rides on exported `icon` properties (matching the codebase's existing `tint`/`clue_id` export pattern). A small reusable `Prop.tscn` carries feet-anchored furniture with optional solid footprints.

**Tech Stack:** Godot 4.6 (GDScript), `CharacterBody2D` top-down, `TileMapLayer`, headless `SceneTree` test runner.

**Conventions for this repo (override the skill defaults):**
- **No git commits without Mark's explicit OK.** Each task ends in a **Checkpoint** (show result, await go-ahead) instead of an automatic commit. The commit command is provided for when he approves.
- **No worktree** — work directly in `tingen/` (matches the project's established workflow; Godot `.godot/` cache + `uid://` refs make worktrees awkward here).
- **Godot binary:** `/Applications/Godot.app/Contents/MacOS/Godot` (referred to below as `$GODOT`). Set once per shell: `GODOT=/Applications/Godot.app/Contents/MacOS/Godot`.
- All paths below are relative to `/Users/markma/Desktop/Purm 2026/Tingen-Game/`.

**Verification model:** This is content authoring, so the gates are (1) a **headless wiring test** (`tests/test_intro_room.gd`, written test-first in Task 2 — instances the scene and asserts the art is wired), (2) the **existing logic suite stays green** (`tests/run_tests.gd` — proves clues/save/etc. weren't broken), and (3) a **manual playtest** at the end (occlusion, collision, examine→clue, door→City, and the HD-2D look). Classic unit tests don't fit visual occlusion; that's checked by eye + screenshot.

---

## File Structure

**Create:**
- `tingen/assets/tiles/wood_floor_0.png` + `tingen/assets/characters/player_detective.png` + `tingen/assets/props/{antigonus_notebook,revolver,cracked_mirror,door_wood,simple_bed,writing_desk,bookshelf,oil_lamp,candle,blood_pool}_0.png` + `tingen/assets/backgrounds/klein_bedroom.png` — copied art (Task 1).
- `tingen/assets/wood_floor_tileset.tres` — TileSet built on the wood tile (Task 3).
- `tingen/src/FloorTiler.gd` — fills a TileMapLayer rect at runtime (Task 3).
- `tingen/scenes/Prop.tscn` + `tingen/src/Prop.gd` — reusable feet-anchored furniture (Task 6).
- `tingen/tests/test_intro_room.gd` — headless wiring assertions (Task 2).

**Modify:**
- `tingen/project.godot` — default canvas texture filter → Nearest (Task 1).
- `tingen/src/Interactable.gd` — add `icon`/`icon_px` exports + feet-anchor (Task 5).
- `tingen/scenes/Player.tscn` — repoint `Sprite2D` to the detective, scale, feet-anchor, feet collider (Task 4). *(Shared with `City.tscn` — intended: the player looks the same everywhere.)*
- `tingen/scenes/IntroRoom.tscn` — root Y-sort; `Floor` → TileMapLayer; interactable `icon`s; furniture; backdrop (Tasks 3,5,6,7).

---

## Task 1: Import assets + Nearest filter

**Files:**
- Create: `tingen/assets/{tiles,characters,props,backgrounds}/…png` (copies)
- Modify: `tingen/project.godot` (add one rendering key)

- [ ] **Step 1: Copy the slice assets into the project**

```bash
cd "/Users/markma/Desktop/Purm 2026/Tingen-Game"
cp asset-gen/out/tiles/wood_floor_0.png                    tingen/assets/tiles/
cp asset-gen/out_image2/characters/player_detective.png    tingen/assets/characters/
cp asset-gen/out_image2/backgrounds/klein_bedroom.png      tingen/assets/backgrounds/
for p in antigonus_notebook revolver cracked_mirror door_wood simple_bed writing_desk bookshelf oil_lamp candle blood_pool; do
  cp "asset-gen/out/props/${p}_0.png" tingen/assets/props/
done
ls tingen/assets/tiles tingen/assets/characters tingen/assets/props tingen/assets/backgrounds
```
Expected: each target dir now lists its PNG(s); `props/` shows all 10.

- [ ] **Step 2: Set the project-wide canvas texture filter to Nearest**

Edit `tingen/project.godot`. If a `[rendering]` section exists, add the key under it; otherwise append the section at the end of the file:

```ini
[rendering]

textures/canvas_textures/default_texture_filter=0
```
(`0` = Nearest. Makes every 2D texture crisp by default — the HD-2D/pixel look — without per-node fiddling.)

- [ ] **Step 3: Trigger import + verify the project loads clean**

Run:
```bash
GODOT=/Applications/Godot.app/Contents/MacOS/Godot
"$GODOT" --headless --path tingen --import 2>&1 | tail -20
```
Expected: imports the new textures and exits without `ERROR`/`SCRIPT ERROR`. (`.import` sidecars now exist next to each PNG.)

- [ ] **Step 4: Checkpoint** — report "assets imported, Nearest filter on." Commit only on Mark's OK:
```bash
git add tingen/assets tingen/project.godot && git commit -m "chore(tingen): import bedroom slice art, default Nearest filter"
```

---

## Task 2: Failing wiring test (red)

**Files:**
- Create: `tingen/tests/test_intro_room.gd`

- [ ] **Step 1: Write the headless wiring test**

Create `tingen/tests/test_intro_room.gd`:

```gdscript
extends SceneTree
## Headless wiring check for the Klein's-bedroom slice. Instances IntroRoom and asserts the
## placeholder flats were replaced with real art (TileMapLayer floor, repointed player +
## interactable sprites, Y-sorted furniture). Logic (clues/door) is covered by run_tests.gd.
## Run:  <godot> --headless --path tingen -s tests/test_intro_room.gd

var _passed := 0
var _failed := 0

func _init() -> void:
	await process_frame
	var packed: PackedScene = load("res://scenes/IntroRoom.tscn")
	var room: Node = packed.instantiate()
	root.add_child(room)
	await process_frame
	await process_frame

	_ok(room.get("y_sort_enabled") == true, "IntroRoom root is Y-sorted")
	_ok(room.get_node_or_null("Floor") is TileMapLayer, "Floor is a TileMapLayer")

	var psprite: Sprite2D = room.get_node_or_null("Player/Sprite2D")
	_ok(psprite != null and psprite.texture != null
		and psprite.texture.resource_path.ends_with("player_detective.png"),
		"Player sprite -> player_detective.png")

	_check_icon(room, "Notebook", "antigonus_notebook_0.png")
	_check_icon(room, "Gun", "revolver_0.png")
	_check_icon(room, "Mirror", "cracked_mirror_0.png")
	_check_icon(room, "Door", "door_wood_0.png")

	_ok(room.get_node_or_null("Bed") != null, "Bed prop present")
	_ok(room.get_node_or_null("Desk") != null, "Desk prop present")
	_ok(room.get_node_or_null("Bookshelf") != null, "Bookshelf prop present")

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _check_icon(room: Node, node_name: String, expect_suffix: String) -> void:
	var spr: Sprite2D = room.get_node_or_null("%s/Sprite2D" % node_name)
	var ok := spr != null and spr.texture != null and spr.texture.resource_path.ends_with(expect_suffix)
	_ok(ok, "%s sprite -> %s" % [node_name, expect_suffix])

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
```

- [ ] **Step 2: Run it and confirm it FAILS**

Run:
```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | tail -15
```
Expected: several `FAIL` lines (Floor is still a `Polygon2D`, root not Y-sorted, player is `icon.svg`, interactables have no real texture, no furniture) and a non-zero exit. This is the target state we'll turn green task-by-task.

- [ ] **Step 3: Checkpoint** — report the red baseline (no commit needed yet; or fold into the next commit).

---

## Task 3: Floor TileMapLayer + Y-sorted root

**Files:**
- Create: `tingen/src/FloorTiler.gd`, `tingen/assets/wood_floor_tileset.tres`
- Modify: `tingen/scenes/IntroRoom.tscn`

- [ ] **Step 1: Write the floor-fill script**

Create `tingen/src/FloorTiler.gd`:

```gdscript
extends TileMapLayer
## Fills a rectangular floor region with one tile at runtime, so we get a real TileMapLayer
## floor without hand-painting tile data in the editor. The slice uses a single seamless wood
## tile; later hubs extend this to multiple sources / per-cell variety.

@export var cols: int = 9
@export var rows: int = 6
@export var source_id: int = 0
@export var atlas_coords: Vector2i = Vector2i.ZERO

func _ready() -> void:
	for y in rows:
		for x in cols:
			set_cell(Vector2i(x, y), source_id, atlas_coords)
```

- [ ] **Step 2: Build the TileSet resource**

Create `tingen/assets/wood_floor_tileset.tres` — a `TileSet` with `tile_size = 384` and one `TileSetAtlasSource` whose texture is `res://assets/tiles/wood_floor_0.png` with a single tile at atlas `(0,0)`. Minimal text form (regenerate the `uid` if Godot complains):

```ini
[gd_resource type="TileSet" load_steps=3 format=3 uid="uid://b1tngnwoodts01"]

[ext_resource type="Texture2D" path="res://assets/tiles/wood_floor_0.png" id="1"]

[sub_resource type="TileSetAtlasSource" id="atlas"]
texture = ExtResource("1")
texture_region_size = Vector2i(384, 384)
0:0/0 = 0

[resource]
tile_size = Vector2i(384, 384)
sources/0 = SubResource("atlas")
```

- [ ] **Step 3: Swap the Floor node and Y-sort the root in `IntroRoom.tscn`**

In `tingen/scenes/IntroRoom.tscn`:
- Add ext_resources for `res://assets/wood_floor_tileset.tres` (TileSet) and `res://src/FloorTiler.gd` (Script).
- On the root `[node name="IntroRoom" type="Node2D"]`, add: `y_sort_enabled = true`.
- **Replace** the `Floor` `Polygon2D` node with:
```ini
[node name="Floor" type="TileMapLayer" parent="."]
position = Vector2(0, 0)
scale = Vector2(0.34, 0.34)
y_sort_enabled = false
tile_set = ExtResource("<woodts>")
script = ExtResource("<floortiler>")
```
  (Floor stays non-Y-sorted at origin Y=0 so the whole floor renders behind everything with Y>0. `scale 0.34` shows ~130px tiles → a believable plank density across the 896×560 room; this is the spec's "tile cell size" open question — tune in Task 8 via the `cols/rows/scale` knobs.)
- Keep `Background` (dark fill) and `Bloodstain`; ensure `Bloodstain` is ordered **after** `Floor` so it reads on top of the planks (both sit at Y origin 0; child order breaks the tie).
- Leave `Walls` (StaticBody2D box), `Player`, the four interactables, and `Hint` as-is for now.

- [ ] **Step 4: Verify the floor + sort assertions go green**

Run:
```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | tail -15
```
Expected: `PASS  IntroRoom root is Y-sorted` and `PASS  Floor is a TileMapLayer` (player/interactable/furniture lines still FAIL).

- [ ] **Step 5: Checkpoint** — commit on OK:
```bash
git add tingen/src/FloorTiler.gd tingen/assets/wood_floor_tileset.tres tingen/scenes/IntroRoom.tscn && git commit -m "feat(tingen): wood TileMapLayer floor + Y-sorted IntroRoom root"
```

---

## Task 4: Repoint the player sprite

**Files:**
- Modify: `tingen/scenes/Player.tscn`

- [ ] **Step 1: Point the player Sprite2D at the detective art, feet-anchored**

In `tingen/scenes/Player.tscn`:
- Add an ext_resource: `res://assets/characters/player_detective.png`.
- On `[node name="Sprite2D" ...]` replace the `icon.svg` texture + cyan modulate + `scale = Vector2(0.16,0.16)` with:
  - `texture = ExtResource("<detective>")`
  - `modulate = Color(1, 1, 1, 1)`
  - `scale = Vector2(0.042, 0.042)`  *(≈64 px tall from the ~1536 px source; tune in Task 8)*
  - `offset = Vector2(0, -768)`  *(half the source height: drops the sprite's feet onto the node origin so Y-sort keys on the feet)*
- On `[node name="CollisionShape2D" ...]`, shrink the box to a feet footprint: change the `RectangleShape2D` `size` from `Vector2(20, 20)` to `Vector2(22, 12)` (kept at node origin = the feet).

- [ ] **Step 2: Verify the player assertion goes green**

Run:
```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | grep -E "player_detective|passed"
```
Expected: `PASS  Player sprite -> player_detective.png`.

- [ ] **Step 3: Checkpoint** — commit on OK:
```bash
git add tingen/scenes/Player.tscn && git commit -m "feat(tingen): real detective player sprite, feet-anchored"
```

---

## Task 5: Interactable real art (icon export) + wire the four

**Files:**
- Modify: `tingen/src/Interactable.gd`, `tingen/scenes/IntroRoom.tscn`

- [ ] **Step 1: Add `icon` support to `Interactable.gd`**

In `tingen/src/Interactable.gd`, add two exports after the existing `tint` line:

```gdscript
## Optional real art; when set it replaces the placeholder tint-square and is feet-anchored.
@export var icon: Texture2D
## Target on-screen height in pixels for the icon art.
@export var icon_px: float = 56.0
```

Replace the body of `_ready()`'s sprite setup (the single `_sprite.modulate = tint` line) with:

```gdscript
	if icon:
		_sprite.texture = icon
		_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		_sprite.modulate = Color.WHITE
		var h := float(icon.get_height())
		var s: float = icon_px / h if h > 0.0 else 1.0
		_sprite.scale = Vector2(s, s)
		_sprite.offset = Vector2(0, -h * 0.5)   # feet-anchor for Y-sort
	else:
		_sprite.modulate = tint
```

(Backward-compatible: interactables with no `icon`, e.g. in `City.tscn`, keep the tinted-placeholder behavior.)

- [ ] **Step 2: Set each interactable's `icon` in `IntroRoom.tscn`**

Add ext_resources for the four prop textures, then add an `icon = ExtResource(...)` line to each existing instance node (leave their `thought`/`clue_id`/`target_scene`/`tint`/`position` untouched):

| Node | line to add |
|---|---|
| `Notebook` | `icon = ExtResource("<antigonus_notebook>")` |
| `Gun` | `icon = ExtResource("<revolver>")` |
| `Mirror` | `icon = ExtResource("<cracked_mirror>")` |
| `Door` | `icon = ExtResource("<door_wood>")` and `icon_px = 96.0` (doors read taller) |

- [ ] **Step 3: Verify the four interactable assertions go green + logic suite stays green**

Run:
```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | grep -E "sprite ->|passed"
"$GODOT" --headless --path tingen -s tests/run_tests.gd 2>&1 | tail -3
```
Expected: the four `… sprite -> …` lines PASS; `run_tests.gd` still ends `=== N passed, 0 failed ===` (clues/door logic untouched).

- [ ] **Step 4: Checkpoint** — commit on OK:
```bash
git add tingen/src/Interactable.gd tingen/scenes/IntroRoom.tscn && git commit -m "feat(tingen): real prop art on IntroRoom interactables"
```

---

## Task 6: Reusable furniture props + populate the warm room

**Files:**
- Create: `tingen/src/Prop.gd`, `tingen/scenes/Prop.tscn`
- Modify: `tingen/scenes/IntroRoom.tscn`

- [ ] **Step 1: Write the Prop script**

Create `tingen/src/Prop.gd`:

```gdscript
extends StaticBody2D
## Reusable set-dressing prop: a feet-anchored sprite with an optional solid footprint.
## Placed as a direct child of a Y-sorted parent so the player occludes correctly by depth.

@export var icon: Texture2D
@export var icon_px: float = 96.0                 # target on-screen height in px
@export var solid: bool = true                    # blocks movement?
@export var footprint: Vector2 = Vector2(48, 18)  # collider size at the feet

@onready var _sprite: Sprite2D = $Sprite2D
@onready var _shape: CollisionShape2D = $CollisionShape2D

func _ready() -> void:
	if icon:
		_sprite.texture = icon
		_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		var h := float(icon.get_height())
		var s: float = icon_px / h if h > 0.0 else 1.0
		_sprite.scale = Vector2(s, s)
		_sprite.offset = Vector2(0, -h * 0.5)       # feet at node origin
	var rect := RectangleShape2D.new()
	rect.size = footprint
	_shape.shape = rect
	_shape.disabled = not solid
	if not solid:
		set_collision_layer_value(1, false)
```

- [ ] **Step 2: Build `Prop.tscn`**

Create `tingen/scenes/Prop.tscn`:

```ini
[gd_scene load_steps=2 format=3 uid="uid://b1tngnprop0001"]

[ext_resource type="Script" path="res://src/Prop.gd" id="1"]

[node name="Prop" type="StaticBody2D"]
script = ExtResource("1")

[node name="Sprite2D" type="Sprite2D" parent="."]

[node name="CollisionShape2D" type="CollisionShape2D" parent="."]
```

- [ ] **Step 3: Place furniture as direct children of the Y-sorted root**

In `tingen/scenes/IntroRoom.tscn`, add ext_resources for `res://scenes/Prop.tscn` and the five furniture textures, then add these instances **as direct children of the root** (siblings of `Player` — so they all sort together). Positions are inside the 0–896 × 0–560 room; tune in Task 8:

| Node name | texture | position | icon_px | solid | footprint |
|---|---|---|---|---|---|
| `Bed` | `simple_bed_0.png` | `Vector2(140, 180)` | 150 | true | `Vector2(120, 36)` |
| `Desk` | `writing_desk_0.png` | `Vector2(700, 200)` | 120 | true | `Vector2(96, 28)` |
| `Bookshelf` | `bookshelf_0.png` | `Vector2(450, 90)` | 150 | true | `Vector2(110, 24)` |
| `Lamp` | `oil_lamp_0.png` | `Vector2(700, 165)` | 70 | false | `Vector2(20, 8)` |
| `Candle` | `candle_0.png` | `Vector2(330, 250)` | 44 | false | `Vector2(12, 6)` |

Each instance node looks like:
```ini
[node name="Bed" parent="." instance=ExtResource("<prop>")]
position = Vector2(140, 180)
icon = ExtResource("<simple_bed>")
icon_px = 150.0
solid = true
footprint = Vector2(120, 36)
```

- [ ] **Step 4: Verify furniture assertions go green**

Run:
```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | tail -15
```
Expected: **all PASS**, `=== 10 passed, 0 failed ===` (or however many checks), exit 0.

- [ ] **Step 5: Checkpoint** — commit on OK:
```bash
git add tingen/src/Prop.gd tingen/scenes/Prop.tscn tingen/scenes/IntroRoom.tscn && git commit -m "feat(tingen): reusable Prop + furnish Klein's bedroom (Y-sorted)"
```

---

## Task 7: Establishing backdrop (intro card)

**Files:**
- Modify: `tingen/scenes/IntroRoom.tscn`

Use the painted `klein_bedroom` as establishing art (per the spec: establishing, not floor) — a brief "you wake up" card that fades to reveal the playable room.

- [ ] **Step 1: Add a fading intro card**

In `tingen/scenes/IntroRoom.tscn`, add a `CanvasLayer` named `IntroCard` (so it ignores world Y-sort/camera) containing a full-rect `TextureRect`:
- ext_resource: `res://assets/backgrounds/klein_bedroom.png`.
- `TextureRect`: `texture` = the painting, `expand_mode = 1` (Ignore Size) / `stretch_mode = 6` (Keep Aspect Covered), anchors full-rect (`anchor_right = 1.0`, `anchor_bottom = 1.0`).
- Attach a tiny inline fade via a 4-line script OR a `Tween` node. Minimal script on `IntroCard` (`CanvasLayer`):
```gdscript
extends CanvasLayer
func _ready() -> void:
	var tr := $TextureRect
	var t := create_tween()
	t.tween_interval(1.2)
	t.tween_property(tr, "modulate:a", 0.0, 1.0)
	t.tween_callback(queue_free)
```

- [ ] **Step 2: Verify it doesn't break load**

Run:
```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | tail -3
```
Expected: still `0 failed`, exit 0 (the card is cosmetic; instancing must stay clean).

- [ ] **Step 3: Checkpoint** — commit on OK:
```bash
git add tingen/scenes/IntroRoom.tscn && git commit -m "feat(tingen): klein_bedroom establishing intro card"
```

---

## Task 8: Playtest, tune, regression, screenshots

**Files:** none new — tuning passes over `IntroRoom.tscn`, `Player.tscn`, `FloorTiler.gd` knobs.

- [ ] **Step 1: Full regression — both suites green**

Run:
```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | tail -3
"$GODOT" --headless --path tingen -s tests/run_tests.gd 2>&1 | tail -3
```
Expected: both `=== N passed, 0 failed ===`, exit 0.

- [ ] **Step 2: Manual playtest** (launch the game)

Run:
```bash
"$GODOT" --path tingen
```
Walk the checklist (this is the real verification for the visual half):
- [ ] Intro card shows the painted bedroom, then fades to the playable room.
- [ ] Floor reads as continuous wood (no harsh seams / no tiny-crop noise). If wrong, tune `Floor.scale` and `FloorTiler.cols/rows`.
- [ ] Player is the detective, crisp (Nearest), grounded (feet on floor, ~2–3 plank-heights tall). Tune `Player/Sprite2D.scale` + `offset` if floating/oversized.
- [ ] **Occlusion both ways:** walking *above* the bed/desk/bookshelf draws the player *behind* it; walking *below* draws the player *in front*. If inverted/janky, adjust each prop's `position`/`offset` (feet line) — they must be direct children of the Y-sorted root.
- [ ] **Collision:** can't walk through walls, bed, desk, bookshelf; *can* pass the lamp/candle (non-solid). Tune `footprint`s.
- [ ] **Examine still works:** E on Notebook/Gun/Mirror surfaces the thought and collects the clue (open the notebook/Tab to confirm the clue landed).
- [ ] **Door still works:** E on the Door transitions to `City.tscn` with the "Find the Nighthawks" lead.
- [ ] HD-2D read: crisp anime player over the pixel floor/props looks intentional, not pasted. (If it reads wrong, that's the spec's reversible "pixelate sprites" escape hatch — a separate follow-up, not this slice.)

- [ ] **Step 3: Capture screenshots for Mark**

Use the in-game screenshot or macOS capture; save a couple of frames (wide room + a behind-the-bed occlusion shot) to `/tmp/` and share. These are the review artifact.

- [ ] **Step 4: Checkpoint** — present screenshots + the two green suites. Commit the tuning on OK:
```bash
git add tingen/scenes/IntroRoom.tscn tingen/scenes/Player.tscn tingen/src/FloorTiler.gd && git commit -m "polish(tingen): tune bedroom floor/sprite/collider scales"
```

---

## Self-Review

**Spec coverage (§7 build order → tasks):** copy assets + Nearest (T1) ✓; one-tile wood TileSet (T3) ✓; Floor Polygon2D → TileMapLayer + root Y-sort (T3) ✓; player repoint feet-anchored (T4) ✓; four interactables repointed, clue/`target_scene` intact (T5) ✓; furniture as Y-sorted props with footprints, Bloodstain kept (T6) ✓; occlusion verified (T8) ✓; `klein_bedroom` as establishing card not floor (T7) ✓; playtest + tune + clue/door check + screenshots (T8) ✓. §4 architecture: per-tile collision via `Walls` is retained from the existing `StaticBody2D` box (the slice keeps it; tile-collision `Walls` is an exterior-hub concern, noted in spec §9). **Deviation from spec §4/§7 wording:** the spec mentions a separate Y-sorted `Objects` layer; for this *retrofit* the player + interactables are already direct children of the root, so furniture is placed as their siblings and the **root** is Y-sorted instead — same depth result, and required for the player to sort against furniture (a separate child group would not cross-sort). Carry the dedicated `Objects` node into the fresh exterior hubs (City/Iron Cross) where everything is authored together.

**Placeholder scan:** no TBD/TODO; every code step has full code; tuning numbers are concrete defaults with an explicit "tune in Task 8" rationale (not placeholders).

**Type/name consistency:** `icon`/`icon_px`/`footprint`/`solid` identical across `Prop.gd`, `Interactable.gd`, and the `.tscn` instance tables; `FloorTiler` exports `cols/rows/source_id/atlas_coords` used consistently; test node names (`Floor`, `Player/Sprite2D`, `Notebook/Gun/Mirror/Door`, `Bed/Desk/Bookshelf`) match the scene edits in T3–T6; `$GODOT` defined once and reused.
