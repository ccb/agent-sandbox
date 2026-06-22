# Klein's Bedroom (IntroRoom) — Y-Sorted Depth Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the already-built `IntroRoom.tscn` from a **flat painted backdrop** (no per-furniture depth) to a **Y-sorted depth build**: swap the furnished `klein_room.png` photo for the empty `klein_floor.png`, place the bespoke `klein_*` furniture as Y-sorted props so the player walks *behind* furniture above her and *in front of* furniture below her, restore the rug + blood-pool floor decals, and make the three remaining invisible interactables read as real objects — while keeping every clue/door behavior and the existing wall/furniture collision intact.

**Architecture:** Keep the existing scene's bones. The root `IntroRoom` Node2D becomes `y_sort_enabled = true` so every direct child (furniture props, the player, interactables) depth-sorts by its feet. The floor and the two floor-decals (rug, blood) are pinned *behind* the sorted objects with negative `z_index` (z_index is the coarse layer; Y-sort is the within-layer tiebreaker). Furniture rides the **existing `Prop.tscn`** (feet-anchored sprite via `Prop.gd`) placed at each piece's front-bottom edge, with `solid = false` so collision keeps coming from the already-authored `Solids` StaticBody2D boxes (visual and collision align because both derive from the same painted layout). Interactables ride the **existing `Interactable.gd` `icon` export** (already feet-anchors art). No new scripts, no engine-file edits, no animation-agent files touched.

**Tech Stack:** Godot 4.6.3 (GDScript), `Node2D` Y-sort, `Sprite2D` feet-anchoring, `CharacterBody2D` top-down, headless `SceneTree` test runner.

---

## Context — why this plan exists (read before starting)

The 2026-06-08 spec (`docs/superpowers/specs/2026-06-08-tilemap-hub-design.md` §7) called for a generic `wood_floor` **TileMapLayer** slice with `player_detective` + `simple_bed`/`writing_desk` props. **That slice was built (Slice Tasks T1–T8, all complete) and then deliberately superseded.** Mark replaced it with a **bespoke painted "Klein" set**:

- `IntroRoom.tscn` now renders the furnished **`klein_room.png`** as a flat `RoomPhoto` Sprite2D (scale 0.5833), with **13 hand-placed colliders** on a `Solids` StaticBody2D (4 walls + 9 furniture footprints), a fixed `RoomCam` (zoom 1.2), a vignette, and an `IntroCard` (the `klein_bedroom.png` card). The player is the bespoke 4-direction **`klein_down.png`** chibi (not `player_detective`).
- Sitting **unused** in `assets/`: an empty-room **`klein_floor.png`** (896×597, exactly the in-game room rectangle at 1:1) plus a full standalone **`klein_*` furniture set** (bed, desk, chair, bookshelf, nightstand, wardrobe, dresser, chest, rug, vanity, cabinet, lamp, picture). You only generate an empty floor + standalone furniture if you intend to place the furniture as separate depth-sorted objects.

Mark chose the **Y-sorted depth upgrade** direction (2026-06-10). This plan realizes the spec's §7.6–7.7 intent ("Y-sorted props… the player passes behind the bed/desk when above, in front when below") **with the bespoke art** — which the flat backdrop cannot deliver because its furniture is baked into one photo.

**Why the floor swap is clean:** `klein_floor.png` is 896×597 native; the current `RoomPhoto` shows `klein_room.png` (1535×1024) at scale 0.5833 ≈ 895×597 — the *same* room rectangle. So swapping the texture and setting scale 1.0 keeps every wall, collider, and interactable coordinate valid. The rug + blood were painted *into* `klein_room.png`, so they must be re-added as decals on the empty floor.

---

## Conventions for this repo (override the skill defaults)

- **No git commits without Mark's explicit OK.** Each task ends in a **Checkpoint** (show result, await go-ahead). The commit command is provided for when he approves. Stage **explicit paths only** — never `git add -A` (a parallel animation agent has many uncommitted files in this tree).
- **No worktree** — work directly in `tingen/` (the project's established workflow; Godot `.godot/` cache + `uid://` refs make worktrees awkward here).
- **Godot binary:** `/Applications/Godot.app/Contents/MacOS/Godot` (referred to below as `$GODOT`). Set once per shell: `GODOT=/Applications/Godot.app/Contents/MacOS/Godot`. A `--headless` run is a separate process and will **not** disturb Mark's open editor (do not kill his editor).
- **Do not touch animation-agent-owned files:** `Main.tscn`, `ui/HUD.tscn` + sub-scenes (incl. `DistrictMap.*`), `LiveDistrict.*`, `AgentRegistry.gd`, `Agent.gd`, `EventBus.gd`, `Clock.gd`, `Item*.gd`, `NpcDB.gd`, `data/items.json`, `tests/run_tests.gd` content (read-only here), `generate_tingen_*.py`. This plan touches **only** `scenes/IntroRoom.tscn` and `tests/test_intro_room.gd`.
- **Do not touch `Player.tscn`** — the player sprite (`klein_down`, feet-anchored) is already verified in-game (task #16). The root Y-sort alone makes it depth-sort.
- All paths below are relative to `/Users/markma/Desktop/Purm 2026/Tingen-Game/`.

**Verification model:** This is visual authoring, so the heavy gate is the **manual playtest** in Task 6 (occlusion both ways, collision, clues fire, door→City). A cheap **headless wiring test** (`tests/test_intro_room.gd`, rewritten test-first in Task 1) guards the structure: root Y-sorted, `Floor`→`klein_floor`, the 9 furniture props present + non-solid, decals present, interactable icons + clue/door wiring intact. The **existing logic suite** (`tests/run_tests.gd`) must stay green to prove clue/save logic wasn't disturbed.

---

## File Structure

**Modify:**
- `tingen/scenes/IntroRoom.tscn` — root `y_sort_enabled`; `RoomPhoto`(`klein_room`)→`Floor`(`klein_floor`); add `Rug` + `BloodPool` decals; add 9 Y-sorted furniture `Prop` instances; repoint `Notebook`/`Mirror`/`Door` icons. (Tasks 2–5)
- `tingen/tests/test_intro_room.gd` — rewrite assertions for the Y-sorted depth design. (Task 1)

**Reuse unchanged (already present — read to confirm, do not edit):**
- `tingen/scenes/Prop.tscn` + `tingen/src/Prop.gd` — feet-anchored prop; honors `icon`/`icon_px`/`solid`/`footprint`. With `solid=false` it draws + Y-sorts but skips collision.
- `tingen/src/Interactable.gd` — already exports `icon`/`icon_px` and feet-anchors art when `icon` is set (ignoring `tint`).
- `tingen/scenes/Solids` (inside `IntroRoom.tscn`) — keep all 13 colliders; the 9 furniture boxes stay the collision source.

**No new scripts. No asset copying** — every `klein_*`, `blood_pool_0`, `antigonus_notebook_0`, `cracked_mirror_0`, `door_wood_0` PNG is already imported (`.import` sidecars present).

---

## Reference — measured asset dimensions (px)

| Asset | native W×H | role |
|---|---|---|
| `tiles/klein_floor.png` | 896×597 | empty room floor+walls+window → the new `Floor` (scale 1.0) |
| `characters/klein_down.png` | 941×1040 | player (already wired; unchanged) |
| `props/klein_bed.png` | 450×575 | furniture |
| `props/klein_desk.png` | 453×400 | furniture |
| `props/klein_chair.png` | 172×330 | furniture |
| `props/klein_bookshelf.png` | 195×472 | furniture |
| `props/klein_nightstand.png` | 252×241 | furniture (used twice) |
| `props/klein_wardrobe.png` | 265×415 | furniture |
| `props/klein_dresser.png` | 169×222 | furniture |
| `props/klein_chest.png` | 355×241 | furniture |
| `props/klein_rug.png` | 492×299 | floor decal |
| `props/blood_pool_0.png` | 248×275 | floor decal (horror beat) |
| `props/antigonus_notebook_0.png` | 384×384 | Notebook interactable icon |
| `props/cracked_mirror_0.png` | 384×384 | Mirror interactable icon |
| `props/door_wood_0.png` | 384×384 | Door interactable icon |

## Reference — furniture layout (derived from existing `Solids` colliders)

Each furniture `Prop` is placed at the **front-bottom (feet)** of its existing collider so the feet-anchored sprite covers the furniture and Y-sorts on its front edge. `feet = (collider.x, collider.y + collider_height/2)`. `icon_px` (on-screen sprite height) is sized so the sprite's *width* ≈ the collider's width: `icon_px = collider_W × nativeH / nativeW`.

| Prop node | klein icon | existing collider (size @ pos) | Prop position (feet) | icon_px |
|---|---|---|---|---|
| `Bed` | `klein_bed` | 204×265 @ (390,167) | **(390, 300)** | **260** |
| `Desk` | `klein_desk` | 155×70 @ (78,150) | **(78, 185)** | **137** |
| `Chair` | `klein_chair` | 80×67 @ (100,212) | **(100, 246)** | **154** |
| `Bookshelf` | `klein_bookshelf` | 83×105 @ (216,82) | **(216, 135)** | **200** |
| `Nightstand1` | `klein_nightstand` | 105×70 @ (352,130) | **(352, 165)** | **100** |
| `Nightstand2` | `klein_nightstand` | 95×85 @ (515,351) | **(515, 394)** | **91** |
| `Wardrobe` | `klein_wardrobe` | 174×114 @ (685,85) | **(685, 142)** | **272** |
| `Dresser` | `klein_dresser` | 126×134 @ (833,195) | **(833, 262)** | **166** |
| `Chest` | `klein_chest` | 110×75 @ (670,336) | **(670, 374)** | **75** |

All positions/`icon_px` are **starting values — tune in Task 6's playtest.** They land furniture on its painted spot; the eye does the final placement.

## Reference — z-order layers (root is Y-sorted)

| z_index | nodes | result |
|---|---|---|
| **-20** | `Background` (dark Polygon2D) | farthest back |
| **-10** | `Floor` (`klein_floor` Sprite2D) | the floor |
| **-5** | `Rug`, `BloodPool` (flat decals) | on the floor, under everything else |
| **0** | 9 furniture `Prop`s, `Player`, `Gun`, `Door` | **Y-sorted among themselves** (depth) |
| **1** | `Notebook`, `Mirror` | small items reading *on top of* their furniture |
| **100** | `Hint` label | instructional UI, always legible |

(`RoomCam` is a camera — no draw order. `Vignette` + `IntroCard` are `CanvasLayer`s — always on top, immune to Y-sort.)

---

## Task 1: Rewrite the wiring test for the Y-sorted design (red baseline)

**Files:**
- Modify: `tingen/tests/test_intro_room.gd`

TDD: assert the *final* design first, watch it go red, then turn it green task-by-task in Tasks 2–5.

- [ ] **Step 1: Replace `tests/test_intro_room.gd` with the new assertions**

Overwrite the file with:

```gdscript
extends SceneTree
## Headless wiring check for the Klein's-bedroom Y-sorted depth build. Instances IntroRoom
## and asserts: the empty klein_floor is the Floor sprite, the root is Y-sorted, the rug +
## blood decals are present, the 9 bespoke klein furniture props are placed as non-solid
## (collision stays on the Solids StaticBody2D), the player + interactable art is wired, and
## the clue/door logic is intact. Visual occlusion itself is checked by eye in the playtest.
## Run:  <godot> --headless --path tingen -s tests/test_intro_room.gd

var _passed := 0
var _failed := 0

const FURNITURE := {
	"Bed": "klein_bed.png", "Desk": "klein_desk.png", "Chair": "klein_chair.png",
	"Bookshelf": "klein_bookshelf.png", "Nightstand1": "klein_nightstand.png",
	"Nightstand2": "klein_nightstand.png", "Wardrobe": "klein_wardrobe.png",
	"Dresser": "klein_dresser.png", "Chest": "klein_chest.png",
}

func _init() -> void:
	await process_frame
	var packed: PackedScene = load("res://scenes/IntroRoom.tscn")
	var room: Node = packed.instantiate()
	root.add_child(room)
	await process_frame
	await process_frame

	# Root Y-sort drives all depth.
	_ok(room.get("y_sort_enabled") == true, "IntroRoom root is Y-sorted")

	# Empty room floor (furniture/blood/rug removed) is a flat Sprite2D, not the furnished photo.
	var floor: Sprite2D = room.get_node_or_null("Floor")
	_ok(floor != null and floor.texture != null
		and floor.texture.resource_path.ends_with("klein_floor.png"),
		"Floor -> klein_floor.png")

	# Floor decals restore what was painted into klein_room.png.
	_check_sprite(room, "Rug", "klein_rug.png")
	_check_sprite(room, "BloodPool", "blood_pool_0.png")

	# Collision stays on the hand-authored Solids boxes (walls + furniture).
	var solids: Node = room.get_node_or_null("Solids")
	_ok(solids is StaticBody2D, "Solids is a StaticBody2D")
	var shape_count := 0
	if solids:
		for c in solids.get_children():
			if c is CollisionShape2D and c.shape != null:
				shape_count += 1
	_ok(shape_count >= 10, "Solids has >=10 collision shapes (got %d)" % shape_count)

	# The 9 bespoke furniture props: present, art wired, and non-solid (Solids owns collision).
	for node_name in FURNITURE:
		var p: Node = room.get_node_or_null(node_name)
		var tex: Texture2D = p.get("icon") if p != null else null
		_ok(p != null and tex != null and tex.resource_path.ends_with(FURNITURE[node_name]),
			"%s prop -> %s" % [node_name, FURNITURE[node_name]])
		_ok(p != null and p.get("solid") == false,
			"%s is non-solid (collision via Solids)" % node_name)

	# Player art (bespoke 4-way Klein; asset owned elsewhere — just verify wiring).
	var psprite: Sprite2D = room.get_node_or_null("Player/Sprite2D")
	_ok(psprite != null and psprite.texture != null
		and psprite.texture.resource_path.ends_with("klein_down.png"),
		"Player sprite -> klein_down.png")
	_ok(room.get_node_or_null("RoomCam") is Camera2D, "RoomCam is a Camera2D")

	# Interactables: real art on all four.
	_check_icon(room, "Notebook", "antigonus_notebook_0.png")
	_check_icon(room, "Gun", "revolver_0.png")
	_check_icon(room, "Mirror", "cracked_mirror_0.png")
	_check_icon(room, "Door", "door_wood_0.png")

	# Interactable logic intact: clue ids + door target unchanged by the art upgrade.
	_check_clue(room, "Notebook", "antigonus_notebook")
	_check_clue(room, "Gun", "spent_revolver")
	_check_clue(room, "Mirror", "wrong_reflection")
	var door: Node = room.get_node_or_null("Door")
	_ok(door != null and door.get("target_scene") == "res://scenes/City.tscn",
		"Door -> City.tscn")

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _check_sprite(room: Node, node_name: String, expect_suffix: String) -> void:
	var s: Sprite2D = room.get_node_or_null(node_name)
	_ok(s != null and s.texture != null and s.texture.resource_path.ends_with(expect_suffix),
		"%s -> %s" % [node_name, expect_suffix])

func _check_icon(room: Node, node_name: String, expect_suffix: String) -> void:
	var spr: Sprite2D = room.get_node_or_null("%s/Sprite2D" % node_name)
	var ok := spr != null and spr.texture != null and spr.texture.resource_path.ends_with(expect_suffix)
	_ok(ok, "%s sprite -> %s" % [node_name, expect_suffix])

func _check_clue(room: Node, node_name: String, expect_clue: String) -> void:
	var n: Node = room.get_node_or_null(node_name)
	_ok(n != null and n.get("clue_id") == expect_clue,
		"%s clue_id == %s" % [node_name, expect_clue])

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
```

- [ ] **Step 2: Run it and confirm it FAILS (red baseline)**

```bash
GODOT=/Applications/Godot.app/Contents/MacOS/Godot
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | tail -30
```
Expected: many `FAIL` lines and a non-zero exit — `IntroRoom root is Y-sorted` (root is currently `y_sort_enabled=false`), `Floor -> klein_floor.png` (node is still `RoomPhoto`/`klein_room`), `Rug`/`BloodPool` (absent), all 9 furniture props (absent), `Notebook`/`Mirror`/`Door` icons (unset). The `Gun sprite`, the three `clue_id` lines, `Solids`, `RoomCam`, and `Door -> City.tscn` should already PASS. This red list is the work for Tasks 2–5.

- [ ] **Step 3: Checkpoint** — report the red baseline (no commit yet; fold into Task 5's commit).

---

## Task 2: Swap the floor + Y-sort the root

**Files:**
- Modify: `tingen/scenes/IntroRoom.tscn`

- [ ] **Step 1: Add the `klein_floor` ext_resource; drop the now-unused `klein_room`**

In `tingen/scenes/IntroRoom.tscn`, in the `ext_resource` block near the top:
- **Add:** `[ext_resource type="Texture2D" path="res://assets/tiles/klein_floor.png" id="klein_floor"]`
- **Remove:** the line `[ext_resource type="Texture2D" path="res://assets/backgrounds/klein_room.png" id="klein_room"]` (no longer referenced after this task — the PNG stays on disk).

- [ ] **Step 2: Y-sort the root and push the dark background fully behind**

- On the root node, change `y_sort_enabled = false` → `y_sort_enabled = true`:
```ini
[node name="IntroRoom" type="Node2D"]
y_sort_enabled = true
```
- On the `Background` Polygon2D node, add `z_index = -20` (keeps the dark fill behind the floor under Y-sort):
```ini
[node name="Background" type="Polygon2D" parent="."]
z_index = -20
color = Color(0.08, 0.07, 0.06, 1)
polygon = PackedVector2Array(-200, -200, 1100, -200, 1100, 800, -200, 800)
```

- [ ] **Step 3: Replace `RoomPhoto` (furnished photo) with `Floor` (empty room, 1:1)**

Replace the whole `RoomPhoto` node block:
```ini
[node name="RoomPhoto" type="Sprite2D" parent="."]
centered = false
texture = ExtResource("klein_room")
scale = Vector2(0.5833, 0.5833)
```
with:
```ini
[node name="Floor" type="Sprite2D" parent="."]
z_index = -10
centered = false
texture = ExtResource("klein_floor")
```
(`klein_floor` is 896×597 = the room rectangle at 1:1, so no `scale` line is needed. `z_index = -10` keeps it under the Y-sorted objects.)

- [ ] **Step 4: Let Godot recompute `load_steps` + verify the floor assertions go green**

The header `load_steps` count is now stale. Either open the scene once in Mark's editor and save, **or** bump the number safely by hand (a too-high `load_steps` is harmless; too-low only warns) — set the header to `load_steps=34`. Then:
```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | grep -E "Y-sorted|Floor ->|passed"
```
Expected: `PASS  IntroRoom root is Y-sorted` and `PASS  Floor -> klein_floor.png` (furniture/decal/interactable lines still FAIL).

- [ ] **Step 5: Checkpoint** — report 2 lines flipped green. Commit on OK:
```bash
git add tingen/scenes/IntroRoom.tscn && git commit -m "feat(tingen): empty klein_floor + Y-sorted IntroRoom root"
```

---

## Task 3: Restore the rug + blood-pool floor decals

**Files:**
- Modify: `tingen/scenes/IntroRoom.tscn`

The rug and blood were painted into `klein_room.png`; on the empty floor they return as flat decals — plain `Sprite2D`s (not feet-anchored, not solid) pinned just above the floor with `z_index = -5`.

- [ ] **Step 1: Add the two decal ext_resources**

Add to the ext_resource block:
```ini
[ext_resource type="Texture2D" path="res://assets/props/klein_rug.png" id="klein_rug"]
[ext_resource type="Texture2D" path="res://assets/props/blood_pool_0.png" id="blood_pool"]
```

- [ ] **Step 2: Add the `Rug` and `BloodPool` nodes (right after the `Floor` node)**

```ini
[node name="Rug" type="Sprite2D" parent="."]
z_index = -5
position = Vector2(400, 330)
scale = Vector2(0.73, 0.73)
texture = ExtResource("klein_rug")

[node name="BloodPool" type="Sprite2D" parent="."]
z_index = -5
position = Vector2(120, 360)
scale = Vector2(0.32, 0.32)
texture = ExtResource("blood_pool")
```
(`Rug` ≈ 359×218 under/south of the bed; `BloodPool` ≈ 79×88 under the `Gun` at (110,360). Both centered; tune in Task 6.)

- [ ] **Step 3: Verify the decal assertions go green**

```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | grep -E "Rug ->|BloodPool ->|passed"
```
Expected: `PASS  Rug -> klein_rug.png` and `PASS  BloodPool -> blood_pool_0.png`.

- [ ] **Step 4: Checkpoint** — commit on OK:
```bash
git add tingen/scenes/IntroRoom.tscn && git commit -m "feat(tingen): restore rug + blood-pool floor decals on empty floor"
```

---

## Task 4: Place the 9 Y-sorted furniture props

**Files:**
- Modify: `tingen/scenes/IntroRoom.tscn`

Furniture rides the existing `Prop.tscn` with `solid = false` (visual + Y-sort only; the `Solids` boxes keep collision). Each `Prop` sits at its piece's feet (see the layout table).

- [ ] **Step 1: Add the `Prop` scene + 8 furniture-texture ext_resources**

Add to the ext_resource block (`klein_nightstand` is shared by both nightstands):
```ini
[ext_resource type="PackedScene" path="res://scenes/Prop.tscn" id="prop"]
[ext_resource type="Texture2D" path="res://assets/props/klein_bed.png" id="klein_bed"]
[ext_resource type="Texture2D" path="res://assets/props/klein_desk.png" id="klein_desk"]
[ext_resource type="Texture2D" path="res://assets/props/klein_chair.png" id="klein_chair"]
[ext_resource type="Texture2D" path="res://assets/props/klein_bookshelf.png" id="klein_bookshelf"]
[ext_resource type="Texture2D" path="res://assets/props/klein_nightstand.png" id="klein_nightstand"]
[ext_resource type="Texture2D" path="res://assets/props/klein_wardrobe.png" id="klein_wardrobe"]
[ext_resource type="Texture2D" path="res://assets/props/klein_dresser.png" id="klein_dresser"]
[ext_resource type="Texture2D" path="res://assets/props/klein_chest.png" id="klein_chest"]
```

- [ ] **Step 2: Add the 9 furniture `Prop` instances (as direct children of the root, before `Player`)**

```ini
[node name="Bed" parent="." instance=ExtResource("prop")]
position = Vector2(390, 300)
icon = ExtResource("klein_bed")
icon_px = 260.0
solid = false

[node name="Desk" parent="." instance=ExtResource("prop")]
position = Vector2(78, 185)
icon = ExtResource("klein_desk")
icon_px = 137.0
solid = false

[node name="Chair" parent="." instance=ExtResource("prop")]
position = Vector2(100, 246)
icon = ExtResource("klein_chair")
icon_px = 154.0
solid = false

[node name="Bookshelf" parent="." instance=ExtResource("prop")]
position = Vector2(216, 135)
icon = ExtResource("klein_bookshelf")
icon_px = 200.0
solid = false

[node name="Nightstand1" parent="." instance=ExtResource("prop")]
position = Vector2(352, 165)
icon = ExtResource("klein_nightstand")
icon_px = 100.0
solid = false

[node name="Nightstand2" parent="." instance=ExtResource("prop")]
position = Vector2(515, 394)
icon = ExtResource("klein_nightstand")
icon_px = 91.0
solid = false

[node name="Wardrobe" parent="." instance=ExtResource("prop")]
position = Vector2(685, 142)
icon = ExtResource("klein_wardrobe")
icon_px = 272.0
solid = false

[node name="Dresser" parent="." instance=ExtResource("prop")]
position = Vector2(833, 262)
icon = ExtResource("klein_dresser")
icon_px = 166.0
solid = false

[node name="Chest" parent="." instance=ExtResource("prop")]
position = Vector2(670, 374)
icon = ExtResource("klein_chest")
icon_px = 75.0
solid = false
```

- [ ] **Step 3: Verify all furniture assertions go green**

```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | grep -E "prop ->|non-solid|passed"
```
Expected: all nine `… prop -> klein_*.png` and nine `… is non-solid` lines PASS.

- [ ] **Step 4: Checkpoint** — commit on OK:
```bash
git add tingen/scenes/IntroRoom.tscn && git commit -m "feat(tingen): place 9 Y-sorted bespoke klein furniture props"
```

---

## Task 5: Repoint the three remaining interactables to real art

**Files:**
- Modify: `tingen/scenes/IntroRoom.tscn`

`Gun` already shows `revolver_0.png`. Make `Notebook`, `Mirror`, and `Door` read as real objects (Interactable.gd feet-anchors `icon` and ignores `tint` once `icon` is set). Notebook + Mirror sit on furniture, so `z_index = 1` keeps them above their piece; the Door is floor-standing and sorts naturally.

- [ ] **Step 1: Add the three interactable-icon ext_resources**

```ini
[ext_resource type="Texture2D" path="res://assets/props/antigonus_notebook_0.png" id="antigonus_notebook"]
[ext_resource type="Texture2D" path="res://assets/props/cracked_mirror_0.png" id="cracked_mirror"]
[ext_resource type="Texture2D" path="res://assets/props/door_wood_0.png" id="door_wood"]
```

- [ ] **Step 2: Edit the three interactable nodes (keep every `thought`/`clue_id`/`target_scene`/`lead_on_use`)**

Replace the `Notebook` block with (on the desk, front edge; small):
```ini
[node name="Notebook" parent="." instance=ExtResource("interactable")]
z_index = 1
position = Vector2(118, 182)
thought = "这东西不对劲。 (This notebook is wrong. The symbols crawl when I look away.)"
prompt_text = "Examine notebook"
icon = ExtResource("antigonus_notebook")
icon_px = 34.0
clue_id = "antigonus_notebook"
```

Replace the `Mirror` block with (on the dresser, right wall):
```ini
[node name="Mirror" parent="." instance=ExtResource("interactable")]
z_index = 1
position = Vector2(836, 250)
thought = "这不是我。 (That is not my face in the glass.)"
prompt_text = "Look in the mirror"
icon = ExtResource("cracked_mirror")
icon_px = 64.0
clue_id = "wrong_reflection"
```

Replace the `Door` block with (against the right wall; the empty floor has no painted door, so the prop makes the exit legible):
```ini
[node name="Door" parent="." instance=ExtResource("interactable")]
position = Vector2(852, 430)
prompt_text = "Open the door"
icon = ExtResource("door_wood")
icon_px = 120.0
target_scene = "res://scenes/City.tscn"
lead_on_use = "线索：寻找值夜者 (Find the Nighthawks)."
```
(Leave the `Gun` node untouched.)

- [ ] **Step 3: Full wiring test green + logic suite still green**

```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | tail -6
"$GODOT" --headless --path tingen -s tests/run_tests.gd 2>&1 | tail -3
```
Expected: `test_intro_room.gd` ends `=== N passed, 0 failed ===`, exit 0. `run_tests.gd` still ends `=== N passed, 0 failed ===` (clue/save logic untouched).

- [ ] **Step 4: Checkpoint** — commit on OK:
```bash
git add tingen/scenes/IntroRoom.tscn tingen/tests/test_intro_room.gd && git commit -m "feat(tingen): real art on Notebook/Mirror/Door + Y-sort wiring test"
```

---

## Task 6: Manual playtest, tune occlusion/collision, screenshots

**Files:** none new — tuning passes over `IntroRoom.tscn` (prop `position`/`icon_px`/`z_index`, decal `position`/`scale`).

This is the real gate for the visual half — the headless test can't see depth.

- [ ] **Step 1: Full regression — both suites green**
```bash
"$GODOT" --headless --path tingen -s tests/test_intro_room.gd 2>&1 | tail -3
"$GODOT" --headless --path tingen -s tests/run_tests.gd 2>&1 | tail -3
```
Expected: both `=== N passed, 0 failed ===`, exit 0.

- [ ] **Step 2: Launch and walk the checklist** (use Mark's already-open editor's Play, or `"$GODOT" --path tingen`; the intro boots through `IntroMain.tscn` → `IntroRoom`)
  - [ ] Intro card (`klein_bedroom`) shows, then fades to the playable room (`IntroCard.gd`, unchanged).
  - [ ] Floor reads as the warm empty room; the **rug** sits under/around the bed and the **blood pool** under the revolver — both *below* furniture and the player (never drawn on top of them).
  - [ ] **Occlusion both ways:** walking *above* the bed / desk / bookshelf / wardrobe / dresser draws the player *behind* it; walking *below* draws the player *in front*. If a piece sorts wrong, nudge its `Prop.position.y` (the feet line) — lower Y sorts it further back. Props must stay direct children of the Y-sorted root.
  - [ ] **Collision unchanged:** can't walk through walls or any furniture (the `Solids` boxes still bite); the prop sprite visually covers its collider. If a sprite floats off its collider, nudge `Prop.position` to re-seat the feet.
  - [ ] **Clue items read right:** the notebook sits on the desk, the cracked mirror on the dresser, both visible. If either hides *behind* its furniture, its `z_index = 1` should already fix it — if it instead floats oddly over the player, drop the `z_index` line and nudge `position.y` down to the furniture's front edge.
  - [ ] **Examine still fires:** E on Notebook / Gun / Mirror surfaces the thought and collects the clue (open the board / Tab to confirm the clue landed).
  - [ ] **Door still works:** the `door_wood` reads as a door on the right wall; E transitions to `City.tscn` with the "Find the Nighthawks" lead.
  - [ ] `Hint` label is legible (if Y-sort buries it under the bed head, add `z_index = 100` to the `Hint` node).
  - [ ] HD-2D read: the crisp Klein chibi over the painted floor/props looks intentional, not pasted.

- [ ] **Step 3: Capture screenshots for Mark**

Save a couple of frames to `/tmp/` (a wide room shot + a behind-the-furniture occlusion shot showing the player partly hidden by the bed or wardrobe). These are the review artifact.

- [ ] **Step 4: Checkpoint** — present screenshots + both green suites. Commit the tuning on OK:
```bash
git add tingen/scenes/IntroRoom.tscn && git commit -m "polish(tingen): tune IntroRoom furniture occlusion/placement"
```

---

## Appendix — optional decor (not core; place only if Mark wants more dressing)

These bespoke assets exist but aren't in the canonical 9-piece layout. Add as extra **non-solid** `Prop`s (or `klein_vanity` as a *solid* swap) only if the room reads sparse after Task 6 — keep them out of the core to avoid clutter (YAGNI):

| Asset | native | suggested use |
|---|---|---|
| `props/klein_vanity.png` | 302×514 | a mirror-vanity that could *replace* `Dresser` and host the Mirror clue (built-in mirror) |
| `props/klein_cabinet.png` | 241×270 | extra storage against a free wall stretch |
| `props/klein_lamp.png` | 101×225 | a standing lamp for a warm pool of light (non-solid) |
| `props/klein_picture.png` | 113×133 | a wall picture (give it a low `z_index` so it stays behind the player) |
| `props/candle_0.png`, `props/oil_lamp_0.png` | 384×384 | flickering candle/lamp ambiance on the nightstands (non-solid) |

---

## Self-Review

**Spec coverage (§7.6–7.7 intent → tasks):** Y-sorted furniture props with collider footprints (T3/T4) ✓; the player passes behind/in front of furniture by depth (root Y-sort T2 + feet-anchored props T4, verified T6) ✓; the bloodstain kept as the horror overlay beat — restored as a `BloodPool` decal since the empty floor drops the painted-in version (T3) ✓; `klein_bedroom` retained as the establishing card, not the floor (unchanged) ✓; playtest + tune + clue/door check + screenshots (T6) ✓. **Reconciliation with reality:** the spec's generic `wood_floor` TileMapLayer + `player_detective` are intentionally *not* used — superseded by Mark's bespoke `klein_floor` + `klein_*` + `klein_down` set (documented in Context); the floor is a flat 1:1 `Sprite2D`, not a TileMapLayer, because `klein_floor.png` is a single room-sized painting, not a seamless tile.

**Placeholder scan:** no TBD/TODO; every `.tscn` edit shows the exact node block; every number (positions, `icon_px`, scales, z-layers) is a concrete value derived in the reference tables, each tagged "tune in Task 6" rather than left open.

**Type/name consistency:** node names in `test_intro_room.gd` (`Floor`, `Rug`, `BloodPool`, the 9 `FURNITURE` keys, `Player/Sprite2D`, `Notebook`/`Gun`/`Mirror`/`Door`, `RoomCam`, `Solids`) match the scene edits in T2–T5 exactly; `icon`/`icon_px`/`solid` are the real `Prop.gd`/`Interactable.gd` export names (confirmed by reading both scripts); ext_resource ids are referenced consistently (`klein_floor`, `prop`, the eight `klein_*` furniture ids, `klein_rug`, `blood_pool`, `antigonus_notebook`, `cracked_mirror`, `door_wood`); `$GODOT` defined once and reused. Furniture feet-positions and `icon_px` are each computed from the existing `Solids` collider that stays the collision source, so visual and collision align by construction.

**Risk notes:** (1) Y-sort vs `z_index` — decals/floor use negative `z_index` as a coarse back-layer with Y-sort as the within-layer tiebreaker (standard Godot 4 ordering); the 9 props + player share `z_index 0` so they cross-sort. (2) Small-item-on-furniture sorting (Notebook/Mirror) is the one fragile spot — handled with `z_index = 1` and an explicit playtest fallback. (3) Collision is *not* re-authored (the verified `Solids` boxes stay), minimizing regression surface; the only logic-adjacent change is adding `icon` lines to interactables, guarded by `run_tests.gd` staying green.
