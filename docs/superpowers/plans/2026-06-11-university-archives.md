# University Archives Vertical Slice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third playable flat-photo room — the Tingen University archive reading room — reusing the finished NighthawksHQ recipe (baked-photo background + invisible `Solids` colliders + `Interactable` hotspots), with the records clerk **Ledger Finch** as a talk-hotspot and three examine points that collect clues + surface thoughts, wired to/from the City hub. **No new GDScript.**

**Architecture:** Mirror `scenes/NighthawksHQ.tscn` verbatim. The room is a `Node2D` with a `RoomPhoto` `Sprite2D` (real PNG, `centered=false`, `scale=0.5833`), a `Solids` `StaticBody2D` of invisible collider boxes traced over the painted furniture, a `Player` instance (own camera disabled), a `RoomCam`, and five `Interactable`s: Finch (`dialogue_id="finch"` + real art), three invisible examine hotspots (each `clue_id` + `thought`), and a `Door` (`target_scene` → City). Per Mark's simulation steer, the room **surfaces, never commands**: it collects clues and emits thoughts but makes **no `set_lead`/`lead_on_use` call** anywhere — the Welch's-lodging thread lands as a *thought only*. Data lives in `data/dialogue.json` (+`finch` tree) and `data/clues.json` (+4 clues); the City→archive door is one optional `Interactable` in `City.tscn`.

**Tech Stack:** Godot 4.6.3, GDScript (existing `Interactable.gd`/`DialogueManager.gd`/`WorldState.gd`/`ClueDB.gd` — unchanged), JSON data, gpt-image-1 PNG art (already generated).

---

## Working context (read before Task 1)

- **Repo:** `/Users/markma/Desktop/Purm 2026/Tingen-Game` — this is the **Tingen-Game** git, NOT agent-sandbox. Work on `main` (the HQ slice committed directly to `main`; follow that precedent).
- **Godot binary:** `/Applications/Godot.app/Contents/MacOS/Godot`. Godot project root is `tingen/`.
- **Shell variables used throughout** (set these once per shell; paths contain a space so they must be quoted):
  ```bash
  GODOT="/Applications/Godot.app/Contents/MacOS/Godot"
  REPO="/Users/markma/Desktop/Purm 2026/Tingen-Game"
  TINGEN="$REPO/tingen"
  ```
- **Both art assets already exist and are production-ready — NO image generation needed:**
  - Background: `asset-gen/out_image2/backgrounds/library_archive.png` — **1536×1024**, identical dims to `hq_interior.png`, so RoomPhoto reuses `scale=0.5833` (→ 896×597 play box).
  - Finch figure: `asset-gen/out_image2/characters/archivist.png` — **1024×1536, already matted** (transparent alpha, corner pixels alpha 0), same hero pipeline + dims as `nighthawk_captain.png`. (This is a deliberate improvement over the spec's 384px `out/characters/archivist_0.png`: higher-res, already clean, visual parity with the Captain. No halo-cleaning required.)
- **Ownership safety — do NOT touch these animation-agent-owned files:** `src/AgentRegistry.gd`, `src/Agent.gd`, `src/EventBus.gd`, `src/Clock.gd`, `src/ItemDB.gd`, `src/ItemDef.gd`, `src/Inventory.gd`, `src/ActionSchema.gd`, `src/NpcDB.gd`, `scenes/Main.tscn`, `ui/HUD.tscn` + sub-scenes, `data/items.json`, `data/action_schema.json`, `tests/run_tests.gd`, `assets/characters/player_detective.png`, `asset-gen/generate_tingen_anim.py`. `data/dialogue.json` and `data/clues.json` are **NOT** on this list — they are safe to edit.
- **Commit gate (Mark's standing rule):** do **NOT** commit until Mark eyeballs the result and explicitly says go. All commits use **surgical explicit paths** (never `git add -A`/`git add .`). `docs/superpowers/` is gitignored/local-only and is **NEVER** committed (this plan + the spec stay local). Commits are batched in **Task 8**.
- **Asset hygiene:** generated art lives under `asset-gen/`; only the two finished PNGs get copied into `tingen/assets/`. The source PNGs under `asset-gen/` are not committed by this slice.

---

### Task 1: Stage + import the two existing PNG assets

**Files:**
- Create: `tingen/assets/backgrounds/university_archive.png` (copied)
- Create: `tingen/assets/characters/archive_clerk_finch.png` (copied)
- Create (by Godot): the two `*.png.import` sidecars

- [ ] **Step 1: Copy the background PNG into the project (renamed)**

```bash
cp "$REPO/asset-gen/out_image2/backgrounds/library_archive.png" \
   "$TINGEN/assets/backgrounds/university_archive.png"
```

- [ ] **Step 2: Copy the Finch figure PNG into the project (renamed)**

```bash
cp "$REPO/asset-gen/out_image2/characters/archivist.png" \
   "$TINGEN/assets/characters/archive_clerk_finch.png"
```

- [ ] **Step 3: Verify the copies landed with the right dimensions**

```bash
sips -g pixelWidth -g pixelHeight -g hasAlpha \
  "$TINGEN/assets/backgrounds/university_archive.png" \
  "$TINGEN/assets/characters/archive_clerk_finch.png"
```
Expected: background `1536×1024 hasAlpha:no`; Finch `1024×1536 hasAlpha:yes`.

- [ ] **Step 4: Import the new textures in Godot (headless) so `.import` sidecars generate**

```bash
"$GODOT" --headless --path "$TINGEN" --import
```
Expected: log lines mentioning `university_archive.png` and `archive_clerk_finch.png`; process exits 0. (If `--import` is not recognized on this build, use `"$GODOT" --headless --path "$TINGEN" --editor --quit-after 200` instead — opening the editor reimports.)

- [ ] **Step 5: Confirm the `.import` sidecars now exist**

```bash
ls "$TINGEN/assets/backgrounds/university_archive.png.import" \
   "$TINGEN/assets/characters/archive_clerk_finch.png.import"
```
Expected: both paths listed (no "No such file").

- [ ] **Step 6 (deferred to Task 6 — brightness tuning):** The source prompt for this background was "candlelight, dim and dusty," so it may read too dark in-engine. Do **not** pre-tune now — judge it on the real Godot render in Task 6, where the exact brightness recipe (and the regen fallback) lives.

> No commit yet (commit gate — Task 8).

---

### Task 2: Failing wiring test (red)

**Files:**
- Create: `tingen/tests/test_university_archive.gd`

- [ ] **Step 1: Write the headless wiring test**

This mirrors `tests/test_nighthawks_hq.gd` exactly, retargeted to the archive. Write the full file:

```gdscript
extends SceneTree
## Headless wiring check for the University Archive slice (flat-image + colliders build).
## Mirrors test_nighthawks_hq.gd: asserts the baked room photo as a Sprite2D background,
## furniture/wall colliders on a Solids StaticBody2D, the player + room camera, Finch (talk),
## the three examine hotspots (each with its clue_id), the door (transition), and the data
## edits (finch dialogue tree + four clues) plus the City -> UniversityArchive door.
## Run:  <godot> --headless --path tingen -s tests/test_university_archive.gd

var _passed := 0
var _failed := 0

func _init() -> void:
	await process_frame
	var packed: PackedScene = load("res://scenes/UniversityArchive.tscn")
	if packed == null:
		_ok(false, "UniversityArchive.tscn loads")
		_finish()
		return
	var room: Node = packed.instantiate()
	root.add_child(room)
	await process_frame
	await process_frame

	# Real room art as the flat background sprite.
	var photo: Sprite2D = room.get_node_or_null("RoomPhoto")
	_ok(photo != null and photo.texture != null
		and photo.texture.resource_path.ends_with("university_archive.png"),
		"RoomPhoto -> university_archive.png")

	# Furniture + wall colliders live on one Solids StaticBody2D.
	var solids: Node = room.get_node_or_null("Solids")
	_ok(solids is StaticBody2D, "Solids is a StaticBody2D")
	var shape_count := 0
	if solids:
		for c in solids.get_children():
			if c is CollisionShape2D and c.shape != null:
				shape_count += 1
	_ok(shape_count >= 8, "Solids has >=8 collision shapes (got %d)" % shape_count)

	# Player wiring (asset owned elsewhere; just verify the sprite path).
	var psprite: Sprite2D = room.get_node_or_null("Player/Sprite2D")
	_ok(psprite != null and psprite.texture != null
		and psprite.texture.resource_path.ends_with("klein_down.png"),
		"Player sprite -> klein_down.png")

	_ok(room.get_node_or_null("RoomCam") is Camera2D, "RoomCam is a Camera2D")

	# Finch: lightweight talking-NPC interactable (dialogue_id + real art, not icon.svg).
	var finch: Node = room.get_node_or_null("Finch")
	_ok(finch != null and finch.get("dialogue_id") == "finch",
		"Finch.dialogue_id == finch")
	var finch_spr: Sprite2D = room.get_node_or_null("Finch/Sprite2D")
	_ok(finch_spr != null and finch_spr.texture != null
		and finch_spr.texture.resource_path.ends_with("archive_clerk_finch.png"),
		"Finch sprite -> archive_clerk_finch.png")

	# Three examine hotspots, each carrying its clue_id.
	_check_examine(room, "CardCatalog", "archive_antigonus")
	_check_examine(room, "RestrictedShelf", "restricted_volume_missing")
	_check_examine(room, "ReadingDeskNotes", "contamination_chain")

	# Door is an invisible hotspot back to the City (no sprite of its own).
	var door: Node = room.get_node_or_null("Door")
	_ok(door != null and door.get("icon") == null,
		"Door is an invisible hotspot (no icon)")
	_ok(door != null and door.get("target_scene") == "res://scenes/City.tscn",
		"Door -> City.tscn")

	# Simulation framing: the room must NOT overwrite the player's lead. No interactable
	# in the room sets lead_on_use (the Welch thread is a thought, not an objective).
	var leads := 0
	for n in room.get_children():
		if n.get("lead_on_use") != null and String(n.get("lead_on_use")) != "":
			leads += 1
	_ok(leads == 0, "no Interactable sets a lead (surface, never command)")

	# Data edits: finch dialogue tree + four clues.
	_check_json_has_key("res://data/dialogue.json", "finch", "dialogue.json has 'finch' tree")
	for cid in ["archive_antigonus", "restricted_volume_missing", "contamination_chain", "finch_cover"]:
		_check_clue_exists(cid)

	# City hub wiring: a door interactable targets the archive.
	_check_city_archive_door()

	_finish()

func _finish() -> void:
	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _check_examine(room: Node, node_name: String, clue_id: String) -> void:
	var n: Node = room.get_node_or_null(node_name)
	_ok(n != null and String(n.get("clue_id")) == clue_id,
		"%s.clue_id == %s" % [node_name, clue_id])

func _check_json_has_key(path: String, key: String, label: String) -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_ok(typeof(parsed) == TYPE_DICTIONARY and parsed.has(key), label)

func _check_clue_exists(clue_id: String) -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/clues.json"))
	var found := false
	if typeof(parsed) == TYPE_ARRAY:
		for c in parsed:
			if typeof(c) == TYPE_DICTIONARY and String(c.get("id", "")) == clue_id:
				found = true
				break
	_ok(found, "clues.json has '%s'" % clue_id)

func _check_city_archive_door() -> void:
	var packed: PackedScene = load("res://scenes/City.tscn")
	if packed == null:
		_ok(false, "City.tscn loads")
		return
	var city: Node = packed.instantiate()
	var found := false
	for c in city.get_children():
		if c.get("target_scene") == "res://scenes/UniversityArchive.tscn":
			found = true
			break
	city.free()
	_ok(found, "City has a door -> UniversityArchive.tscn")

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
```

- [ ] **Step 2: Run the test and confirm it fails (red)**

```bash
"$GODOT" --headless --path "$TINGEN" -s tests/test_university_archive.gd
```
Expected: FAIL — the very first assert prints `FAIL  UniversityArchive.tscn loads` (the scene does not exist yet) and the run ends `=== 0 passed, 1 failed ===`, exit code 1.

> No commit yet (commit gate — Task 8).

---

### Task 3: Data edits — `finch` dialogue tree + four clues

**Files:**
- Modify: `tingen/data/dialogue.json` (append `"finch"` tree)
- Modify: `tingen/data/clues.json` (append 4 clue objects)

The dialogue effect schema (from `DialogueManager._apply_effect`) supports `{"type":"collect","clue":...}`, `{"type":"lead","text":...}`, `{"type":"thought","text":...}`. The `finch` tree uses **only `collect`** — no `lead` (simulation framing).

- [ ] **Step 1: Append the `finch` tree to `dialogue.json`**

The file is one JSON object whose last tree is `"orin_waverer"`. Use this exact `Edit` — anchor on the end of orin_waverer's `turned` node and the two closing braces, and insert `finch` before the final brace:

old_string:
```json
				{ "label": "Stay quiet and wait for my signal.", "goto": "end" }
			]
		}
	}
}
```
new_string:
```json
				{ "label": "Stay quiet and wait for my signal.", "goto": "end" }
			]
		}
	},
	"finch": {
		"start": "root",
		"nodes": {
			"root": {
				"speaker": "Ledger Finch",
				"text": "(He looks up sharply, ink-stained fingers going still on a ledger.) Oh — the records desk is closed for cataloguing just now. Mostly. Was there something you needed? Please, be quick about it.",
				"options": [
					{ "label": "Anything on Antigonus?", "goto": "antigonus" },
					{ "label": "What happened to the restricted volume?", "goto": "volume" },
					{ "label": "(Leave)", "goto": "end" }
				]
			},
			"antigonus": {
				"speaker": "Ledger Finch",
				"text": "Antigonus...? (He stiffens.) That name belongs to the restricted collection. I really couldn't say. The catalogue is over there if you must — but the section is sealed. Please don't make trouble for me.",
				"options": [
					{ "label": "Back", "goto": "root" }
				]
			},
			"volume": {
				"speaker": "Ledger Finch",
				"text": "The restricted volume? It's out — out for rebinding. At the bindery. Routine, entirely routine. (He answers a shade too fast, eyes flicking to the gap on the shelf.) It will be back any day now. Any day.",
				"effects": [ { "type": "collect", "clue": "finch_cover" } ],
				"options": [
					{ "label": "Back", "goto": "root" },
					{ "label": "Understood.", "goto": "end" }
				]
			}
		}
	}
}
```

- [ ] **Step 2: Append the four clues to `clues.json`**

The file is a JSON array whose last element is `captain_briefing`. Use this exact `Edit` — anchor on the end of the `captain_briefing` object and the array close:

old_string:
```json
		"type": "testimony",
		"importance": "pivotal",
		"location": "nighthawk_hq",
		"topics": ["the_nighthawks", "antigonus_notebook"],
		"linked_entities": ["nighthawk_captain"]
	}
]
```
new_string:
```json
		"type": "testimony",
		"importance": "pivotal",
		"location": "nighthawk_hq",
		"topics": ["the_nighthawks", "antigonus_notebook"],
		"linked_entities": ["nighthawk_captain"]
	},
	{
		"id": "archive_antigonus",
		"name": "Antigonus in the Catalogue",
		"description": "The card catalogue confirms Antigonus was real — a long-dead devotee whose key volume has a call number but no book on the shelf.",
		"type": "occult",
		"importance": "supporting",
		"location": "university_archive",
		"topics": ["antigonus_notebook", "the_university"],
		"linked_entities": ["antigonus"]
	},
	{
		"id": "restricted_volume_missing",
		"name": "The Missing Volume",
		"description": "The restricted shelf has one empty slot, its dust-shadow still fresh. Someone removed Antigonus' volume only recently.",
		"type": "physical",
		"importance": "supporting",
		"location": "university_archive",
		"topics": ["antigonus_notebook", "the_theft"],
		"linked_entities": ["ledger_finch"]
	},
	{
		"id": "contamination_chain",
		"name": "The Chain of Owners",
		"description": "Abandoned marginalia traces the notebook through Welch and his circle — each reader driven mad, then dead. The list ends at Welch's lodging.",
		"type": "testimony",
		"importance": "pivotal",
		"location": "university_archive",
		"topics": ["antigonus_notebook", "the_contamination"],
		"linked_entities": ["welch"]
	},
	{
		"id": "finch_cover",
		"name": "The Clerk's Excuse",
		"description": "The records clerk insists the restricted volume is 'out for rebinding' — a shade too quickly. He is covering for its disappearance.",
		"type": "testimony",
		"importance": "supporting",
		"location": "university_archive",
		"topics": ["the_theft"],
		"linked_entities": ["ledger_finch"]
	}
]
```

- [ ] **Step 3: Verify both JSON files still parse and contain the new keys/ids**

```bash
python3 -c "
import json
d = json.load(open('$TINGEN/data/dialogue.json'))
assert 'finch' in d, 'finch tree missing'
assert d['finch']['nodes']['volume']['effects'][0] == {'type':'collect','clue':'finch_cover'}, 'volume effect wrong'
c = json.load(open('$TINGEN/data/clues.json'))
ids = {x['id'] for x in c}
for cid in ['archive_antigonus','restricted_volume_missing','contamination_chain','finch_cover']:
    assert cid in ids, cid + ' missing'
print('OK: dialogue + clues parse; finch tree and 4 clues present')
"
```
Expected: `OK: dialogue + clues parse; finch tree and 4 clues present`.

> No commit yet (commit gate — Task 8). The full headless test (Task 2) still fails because the scene does not exist yet — the data asserts only run after the scene loads.

---

### Task 4: Build `UniversityArchive.tscn` (complete scene)

**Files:**
- Create: `tingen/scenes/UniversityArchive.tscn`

This is a hand-written `.tscn` mirroring `NighthawksHQ.tscn`. Write the whole file at once (incremental hand-editing of a `.tscn` risks malformed intermediate `load_steps`). Collider + interactable coordinates are **sensible starting estimates** in the 896×597 play box; Task 6 tunes them against the rendered photo.

- [ ] **Step 1: Write the scene file**

```
[gd_scene load_steps=13 format=3 uid="uid://b1tngnuniv0001"]

[ext_resource type="PackedScene" path="res://scenes/Player.tscn" id="player"]
[ext_resource type="Texture2D" path="res://assets/backgrounds/university_archive.png" id="arc_bg"]
[ext_resource type="PackedScene" path="res://scenes/Interactable.tscn" id="interactable"]
[ext_resource type="Texture2D" path="res://assets/characters/archive_clerk_finch.png" id="finch_art"]

[sub_resource type="RectangleShape2D" id="wall_h"]
size = Vector2(896, 48)

[sub_resource type="RectangleShape2D" id="wall_v"]
size = Vector2(54, 597)

[sub_resource type="RectangleShape2D" id="s_shelf_top"]
size = Vector2(360, 46)

[sub_resource type="RectangleShape2D" id="s_shelf_side"]
size = Vector2(46, 340)

[sub_resource type="RectangleShape2D" id="s_table"]
size = Vector2(180, 110)

[sub_resource type="RectangleShape2D" id="s_catalog"]
size = Vector2(150, 92)

[sub_resource type="RectangleShape2D" id="s_desk"]
size = Vector2(130, 92)

[sub_resource type="RectangleShape2D" id="s_feet"]
size = Vector2(44, 30)

[node name="UniversityArchive" type="Node2D"]
y_sort_enabled = false

[node name="Background" type="Polygon2D" parent="."]
color = Color(0.07, 0.05, 0.04, 1)
polygon = PackedVector2Array(-200, -200, 1100, -200, 1100, 800, -200, 800)

[node name="RoomPhoto" type="Sprite2D" parent="."]
centered = false
texture = ExtResource("arc_bg")
scale = Vector2(0.5833, 0.5833)

[node name="Solids" type="StaticBody2D" parent="."]

[node name="WTop" type="CollisionShape2D" parent="Solids"]
position = Vector2(448, 24)
shape = SubResource("wall_h")

[node name="WBottom" type="CollisionShape2D" parent="Solids"]
position = Vector2(448, 573)
shape = SubResource("wall_h")

[node name="WLeft" type="CollisionShape2D" parent="Solids"]
position = Vector2(27, 298)
shape = SubResource("wall_v")

[node name="WRight" type="CollisionShape2D" parent="Solids"]
position = Vector2(869, 298)
shape = SubResource("wall_v")

[node name="FShelfTopL" type="CollisionShape2D" parent="Solids"]
position = Vector2(250, 72)
shape = SubResource("s_shelf_top")

[node name="FShelfTopR" type="CollisionShape2D" parent="Solids"]
position = Vector2(646, 72)
shape = SubResource("s_shelf_top")

[node name="FShelfL" type="CollisionShape2D" parent="Solids"]
position = Vector2(74, 298)
shape = SubResource("s_shelf_side")

[node name="FShelfR" type="CollisionShape2D" parent="Solids"]
position = Vector2(822, 298)
shape = SubResource("s_shelf_side")

[node name="FTableL" type="CollisionShape2D" parent="Solids"]
position = Vector2(330, 300)
shape = SubResource("s_table")

[node name="FTableR" type="CollisionShape2D" parent="Solids"]
position = Vector2(580, 300)
shape = SubResource("s_table")

[node name="FCatalog" type="CollisionShape2D" parent="Solids"]
position = Vector2(150, 470)
shape = SubResource("s_catalog")

[node name="FDesk" type="CollisionShape2D" parent="Solids"]
position = Vector2(700, 455)
shape = SubResource("s_desk")

[node name="FFeet" type="CollisionShape2D" parent="Solids"]
position = Vector2(700, 420)
shape = SubResource("s_feet")

[node name="Player" parent="." instance=ExtResource("player")]
position = Vector2(448, 500)

[node name="Sprite2D" parent="Player" index="0"]
scale = Vector2(0.073, 0.073)

[node name="Camera2D" parent="Player" index="2"]
enabled = false

[node name="RoomCam" type="Camera2D" parent="."]
position = Vector2(448, 298)
zoom = Vector2(1.2, 1.2)

[node name="Finch" parent="." instance=ExtResource("interactable")]
position = Vector2(700, 415)
prompt_text = "Speak to the records clerk"
icon = ExtResource("finch_art")
icon_px = 90.0
dialogue_id = "finch"

[node name="CardCatalog" parent="." instance=ExtResource("interactable")]
position = Vector2(150, 408)
thought = "卡片目录里确有其人——安提哥努斯，一位早已作古的信徒。索书号还在，架上却没有那本书。 (The card catalogue does list him — Antigonus, a devotee long dead. The call number remains; the book is gone from the shelf.)"
prompt_text = "Read the card catalogue"
tint = Color(0.7, 0.72, 0.78, 0)
clue_id = "archive_antigonus"

[node name="RestrictedShelf" parent="." instance=ExtResource("interactable")]
position = Vector2(790, 180)
thought = "禁阅架上空了一格，尘影边缘还很新。有人刚把安提哥努斯的卷册取走，就在我前头。 (One slot on the restricted shelf sits empty, its dust-shadow still sharp. Someone lifted Antigonus' volume only just ahead of me.)"
prompt_text = "Examine the restricted shelf"
tint = Color(0.7, 0.72, 0.78, 0)
clue_id = "restricted_volume_missing"

[node name="ReadingDeskNotes" parent="." instance=ExtResource("interactable")]
position = Vector2(330, 370)
thought = "废弃的旁注，一行接一行：读过这本笔记的人——韦尔奇和他的同伴——一个个发疯，然后死去。名单的尽头，是韦尔奇的寓所。 (Abandoned marginalia, line after line: every reader of this notebook — Welch and his circle — driven mad, then dead. The list ends at Welch's lodging.)"
prompt_text = "Read the abandoned notes"
tint = Color(0.7, 0.72, 0.78, 0)
clue_id = "contamination_chain"

[node name="Door" parent="." instance=ExtResource("interactable")]
position = Vector2(448, 540)
prompt_text = "Leave — back to the quad"
tint = Color(0.7, 0.72, 0.78, 0)
target_scene = "res://scenes/City.tscn"

[node name="Hint" type="Label" parent="."]
offset_left = 300.0
offset_top = 24.0
offset_right = 600.0
offset_bottom = 44.0
horizontal_alignment = 1
text = "WASD / Arrows to move   .   E to interact"
```

- [ ] **Step 2: Run the headless test — scene-side asserts should now pass**

```bash
"$GODOT" --headless --path "$TINGEN" -s tests/test_university_archive.gd
```
Expected (Task 3's data asserts already pass; only the City door remains): every assert PASSES **except** the last one — `FAIL  City has a door -> UniversityArchive.tscn` — because the City door isn't wired yet. Tally: `=== 18 passed, 1 failed ===`, exit 1. (If `RoomPhoto`/`Finch` sprite asserts fail with a load error, the Task 1 import didn't take — re-run Task 1 Step 4.)

> No commit yet (commit gate — Task 8).

---

### Task 5: Wire the City → University Archive door

**Files:**
- Modify: `tingen/scenes/City.tscn` (add one `UniversityDoor` `Interactable`)

The City stub currently holds: `Player (600,400)`, `Nighthawk (820,320)`, `HQDoor (300,500)`, `Orin (400,240)`, `Dalia (820,220)`. Place `UniversityDoor` at `(600, 600)` — straight down from spawn, ≥200px clear of every existing node. It is a visible warm-amber square (the City is a stub with placeholder art) and, per the simulation framing, sets **no `lead_on_use`** — it's there to enter or ignore.

- [ ] **Step 1: Add the door node**

Use this exact `Edit` — anchor on the existing `Dalia` node at the end of `City.tscn` and append after it:

old_string:
```
[node name="Dalia" parent="." instance=ExtResource("npc")]
position = Vector2(820, 220)
npc_id = "fishwife_dalia"
```
new_string:
```
[node name="Dalia" parent="." instance=ExtResource("npc")]
position = Vector2(820, 220)
npc_id = "fishwife_dalia"

[node name="UniversityDoor" parent="." instance=ExtResource("interactable")]
position = Vector2(600, 600)
prompt_text = "Enter the University archive"
tint = Color(0.72, 0.6, 0.42, 1)
target_scene = "res://scenes/UniversityArchive.tscn"
```

- [ ] **Step 2: Run the headless test — fully green**

```bash
"$GODOT" --headless --path "$TINGEN" -s tests/test_university_archive.gd
```
Expected: all asserts PASS — `=== 19 passed, 0 failed ===`, exit 0.

- [ ] **Step 3: Regression — the HQ test still passes (shared files `City.tscn`/`dialogue.json`/`clues.json` were edited)**

```bash
"$GODOT" --headless --path "$TINGEN" -s tests/test_nighthawks_hq.gd
```
Expected: the HQ run still ends `0 failed`, exit 0 (our edits are purely additive).

> No commit yet (commit gate — Task 8).

---

### Task 6: Tune colliders + Finch placement against the rendered photo

The headless test proves wiring, not visual alignment. Use two **temporary** harnesses (deleted in Task 7) to align the invisible colliders and the interactables to the actual painted furniture, and to judge the background's brightness on the real render.

**Files:**
- Create (temp): `tingen/tests/_overlay_archive.gd`
- Create (temp): `tingen/tests/_shot_archive.gd`
- Modify (tuning): `tingen/scenes/UniversityArchive.tscn` (collider + interactable positions), and possibly `tingen/assets/backgrounds/university_archive.png` (brightness)

- [ ] **Step 1: Judge background brightness on the real render**

Open the room in the editor and look at it:
```bash
"$GODOT" --path "$TINGEN" --editor scenes/UniversityArchive.tscn
```
If the room is too dark to read the furniture (the "dim and dusty" risk), brighten in post (then re-import). Run this only if needed:
```bash
python3 -c "
from PIL import Image, ImageEnhance
p = '$TINGEN/assets/backgrounds/university_archive.png'
im = Image.open(p).convert('RGB')
im = ImageEnhance.Brightness(im).enhance(1.22)
im = ImageEnhance.Contrast(im).enhance(1.05)
im.save(p)
print('brightened', p)
"
"$GODOT" --headless --path "$TINGEN" --import
```
**Regen fallback (Mark's call — costs API budget):** if the background is structurally wrong (not an enclosed top-down room, wrong perspective, people in it — the same failure the HQ background hit before its regen), it must be regenerated via Mark's pipeline. The improved prompt to drop into the `library_archive` entry of `asset-gen/generate_tingen_image2.py` (mirroring the enclosed-room/evenly-lit HQ prompt, warm palette):
> "a grand university archive reading room inside a stately building, the rectangular room is fully enclosed and bordered along all four outer edges by tall dark mahogany bookshelves packed with leather books seen from directly above, a warm worn red-and-gold patterned carpet over a polished wood floor filling the center, a sensible reading-room layout: two long central reading tables with chairs and green-shaded brass banker's lamps, a tall wooden card-catalogue cabinet against one wall, an archivist's writing desk with a ledger in one corner, a wall shelf with one visible empty gap, arched windows with warm evening light between the shelves, a few brass lamps and candles, sophisticated antique scholarly and aesthetically pleasing, a warm palette of mahogany brown, aged gold, deep-green lampshades and parchment cream, clearly and evenly lit with a soft warm amber glow so the whole room is bright enough to read everything, sparse tidy and orderly not cluttered, NO cold blue or silver tint, NO marble, NO clutter, NO people"

Then `python3 generate_tingen_image2.py --category backgrounds --treatment topdown` (regenerates topdown backgrounds; Mark scopes/eyeballs), re-copy + re-import via Task 1. **`generate_tingen_image2.py` is Mark's pipeline — do not edit/run it without his go-ahead.**

- [ ] **Step 2: Write the collider-overlay harness**

```gdscript
extends SceneTree
## TEMP: render each Solids collider as a translucent box over the room photo so
## furniture alignment can be eyeballed. Saves a PNG. Delete before finishing.
## Run:  <godot> --path tingen -s tests/_overlay_archive.gd

func _init() -> void:
	await process_frame
	var room: Node2D = load("res://scenes/UniversityArchive.tscn").instantiate()
	root.add_child(room)
	await process_frame
	var solids: Node = room.get_node("Solids")
	for c in solids.get_children():
		if c is CollisionShape2D and c.shape is RectangleShape2D:
			var box := ColorRect.new()
			var sz: Vector2 = (c.shape as RectangleShape2D).size
			box.size = sz
			box.position = c.position - sz * 0.5
			box.color = Color(1, 0, 0, 0.32)
			room.add_child(box)
	var cam: Camera2D = room.get_node("RoomCam")
	cam.make_current()
	await process_frame
	await process_frame
	var img := get_root().get_texture().get_image()
	img.save_png("res://_overlay_archive.png")
	print("wrote res://_overlay_archive.png")
	quit(0)
```

```bash
"$GODOT" --path "$TINGEN" -s tests/_overlay_archive.gd
open "$TINGEN/_overlay_archive.png"
```
Inspect: each red box should sit over its painted furniture (wall bookshelves, the two reading tables, the card-catalogue cabinet, Finch's desk). Adjust the `position`/`size` of the corresponding `CollisionShape2D`/`SubResource` in `UniversityArchive.tscn` and re-run until aligned. Keep `shape_count >= 8`.

- [ ] **Step 3: Write the screenshot harness (full room + Finch close-up)**

```gdscript
extends SceneTree
## TEMP: capture the room (RoomCam) and a Finch close-up to verify figure scale,
## feet-anchoring (no floating art), and that the player reaches the talk zone.
## Delete before finishing.  Run:  <godot> --path tingen -s tests/_shot_archive.gd

func _init() -> void:
	await process_frame
	var room: Node2D = load("res://scenes/UniversityArchive.tscn").instantiate()
	root.add_child(room)
	await process_frame
	await process_frame
	# Full room.
	(room.get_node("RoomCam") as Camera2D).make_current()
	await process_frame
	await process_frame
	get_root().get_texture().get_image().save_png("res://_shot_archive_room.png")
	# Finch close-up: a temporary camera centered on Finch.
	var finch: Node2D = room.get_node("Finch")
	var cu := Camera2D.new()
	cu.zoom = Vector2(3.0, 3.0)
	finch.add_child(cu)
	cu.make_current()
	await process_frame
	await process_frame
	get_root().get_texture().get_image().save_png("res://_shot_archive_finch.png")
	print("wrote _shot_archive_room.png + _shot_archive_finch.png")
	quit(0)
```

```bash
"$GODOT" --path "$TINGEN" -s tests/_shot_archive.gd
open "$TINGEN/_shot_archive_room.png" "$TINGEN/_shot_archive_finch.png"
```
Verify: Finch stands at his desk at a believable scale (≈ Captain's on-screen size; tune `icon_px` on the `Finch` node if needed — Captain uses `90.0`), feet on the floor (not floating), and the player spawn sits in open floor near the exit. Re-position `Finch`, the examine hotspots, `Door`, and `Player` in `UniversityArchive.tscn` as needed; re-run.

- [ ] **Step 4: Re-confirm the headless test after tuning**

```bash
"$GODOT" --headless --path "$TINGEN" -s tests/test_university_archive.gd
```
Expected: still `=== 19 passed, 0 failed ===`.

> No commit yet (commit gate — Task 8).

---

### Task 7: Playtest harness (proximity + effects), then cleanup

**Files:**
- Create (temp): `tingen/tests/_playtest_archive.gd`
- Delete (temp): `tingen/tests/_overlay_archive.gd`, `tingen/tests/_shot_archive.gd`, `tingen/tests/_playtest_archive.gd`, any `_overlay_archive.png`/`_shot_archive_*.png`, and any orphaned `*.uid` for the temp scripts

- [ ] **Step 1: Write the playtest harness**

This teleports the player onto each hotspot and asserts proximity detection + the right effect fires. It uses the velocity-zero + `force_update_transform()` + extra-physics-frame + `get_overlapping_bodies()` recipe proven on the HQ slice (avoids the teleport/physics-monitoring timing artifact). Autoloads are reached via `root.get_node("/root/...")`.

```gdscript
extends SceneTree
## TEMP playtest: proximity + effects for the archive hotspots. Delete before finishing.
## Run:  <godot> --path tingen -s tests/_playtest_archive.gd

var _passed := 0
var _failed := 0

func _init() -> void:
	await process_frame
	var ClueDB = root.get_node("/root/ClueDB")
	var DM = root.get_node("/root/DialogueManager")
	var WS = root.get_node("/root/WorldState")

	var room: Node2D = load("res://scenes/UniversityArchive.tscn").instantiate()
	root.add_child(room)
	await process_frame
	await process_frame
	var player: Node2D = room.get_node("Player")

	# Capture thoughts emitted by examines.
	var thoughts: Array = []
	WS.thought_requested.connect(func(t): thoughts.append(t))

	# --- examines: proximity + clue collect + thought ---
	for pair in [["CardCatalog", "archive_antigonus"],
				 ["RestrictedShelf", "restricted_volume_missing"],
				 ["ReadingDeskNotes", "contamination_chain"]]:
		var it: Node2D = room.get_node(pair[0])
		await _walk_to(player, it)
		_ok(it._player_near, "%s: player within reach" % pair[0])
		var before: int = thoughts.size()
		it._use()
		await process_frame
		_ok(ClueDB.is_collected(pair[1]), "%s: collected %s" % [pair[0], pair[1]])
		_ok(thoughts.size() > before, "%s: surfaced a thought" % pair[0])

	# --- Finch: talk opens the finch tree; the 'volume' branch collects finch_cover ---
	var finch: Node2D = room.get_node("Finch")
	await _walk_to(player, finch)
	_ok(finch._player_near, "Finch: player within reach")
	finch._use()
	await process_frame
	_ok(DM.active and DM._active_npc == "finch", "Finch: opened the 'finch' dialogue")
	# Drive root -> 'volume' (option index 1) which carries collect:finch_cover.
	DM.choose("root", 1)
	await process_frame
	_ok(ClueDB.is_collected("finch_cover"), "Finch: 'volume' branch collected finch_cover")
	DM.active = false

	# --- Door: requests the City transition (no lead overwrite) ---
	var door: Node2D = room.get_node("Door")
	var lead_before = WS.current_lead
	var got := {"scene": ""}
	WS.transition_requested.connect(func(scene, _lead): got.scene = scene)
	await _walk_to(player, door)
	_ok(door._player_near, "Door: player within reach")
	door._use()
	await process_frame
	_ok(got.scene == "res://scenes/City.tscn", "Door: requested City transition")
	_ok(WS.current_lead == lead_before, "Door: did NOT overwrite the player's lead")

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _walk_to(player: Node2D, target: Node2D) -> void:
	player.global_position = target.global_position
	player.velocity = Vector2.ZERO
	player.force_update_transform()
	await physics_frame
	await physics_frame
	await physics_frame
	await process_frame

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
```

- [ ] **Step 2: Run the playtest**

```bash
"$GODOT" --path "$TINGEN" -s tests/_playtest_archive.gd
```
Expected: `=== 15 passed, 0 failed ===`, exit 0 (3 examines × {within reach, collected clue, surfaced thought} = 9, + Finch {within reach, opened tree, collected finch_cover} = 3, + Door {within reach, requested City transition, did not overwrite lead} = 3). Treat any `FAIL` as a real bug — a missed proximity means the interactable sits outside the player's reach; nudge its position in `UniversityArchive.tscn` toward walkable floor and re-run.

- [ ] **Step 3: Delete all temporary harnesses + artifacts**

```bash
rm -f "$TINGEN/tests/_overlay_archive.gd" \
      "$TINGEN/tests/_shot_archive.gd" \
      "$TINGEN/tests/_playtest_archive.gd"
rm -f "$TINGEN/tests/_overlay_archive.gd.uid" \
      "$TINGEN/tests/_shot_archive.gd.uid" \
      "$TINGEN/tests/_playtest_archive.gd.uid"
rm -f "$TINGEN/_overlay_archive.png" \
      "$TINGEN/_shot_archive_room.png" \
      "$TINGEN/_shot_archive_finch.png"
```

- [ ] **Step 4: Final verification — only the permanent wiring test remains and is green**

```bash
ls "$TINGEN/tests/" | grep -i archive
"$GODOT" --headless --path "$TINGEN" -s tests/test_university_archive.gd
```
Expected: `ls` shows **only** `test_university_archive.gd` (+ its `.uid`) — no `_overlay`/`_shot`/`_playtest`. Test ends `=== 19 passed, 0 failed ===`, exit 0.

- [ ] **Step 5: Confirm working tree is clean of temp files**

```bash
cd "$REPO" && git status --short
```
Expected: the only changed/untracked entries are the slice's real files (scene, test, two JSON, City.tscn, the two PNGs + `.import`) — no `_overlay`/`_shot`/`_playtest` artifacts. (`docs/superpowers/` may also appear but is gitignored.)

> No commit yet — present to Mark for eyeball first (commit gate).

---

### Task 8: Commit on Mark's explicit OK (three surgical groups)

**Do not run this task until Mark has eyeballed the room and said go.** Commit on `main`, in the Tingen-Game repo, with **explicit paths only** (never `git add -A`). Mirror the HQ slice's three logical commits. `docs/superpowers/` is gitignored and must never appear in a commit.

- [ ] **Step 1: Review exactly what will be staged**

```bash
cd "$REPO" && git status --short && echo "---" && git diff --stat
```
Confirm only these paths are involved:
`tingen/assets/backgrounds/university_archive.png` (+`.import`), `tingen/assets/characters/archive_clerk_finch.png` (+`.import`), `tingen/data/dialogue.json`, `tingen/data/clues.json`, `tingen/scenes/UniversityArchive.tscn` (+`.uid` if Godot made one), `tingen/scenes/City.tscn`, `tingen/tests/test_university_archive.gd` (+`.uid`).

- [ ] **Step 2: Commit group A — the two art assets**

```bash
cd "$REPO"
git add tingen/assets/backgrounds/university_archive.png \
        tingen/assets/backgrounds/university_archive.png.import \
        tingen/assets/characters/archive_clerk_finch.png \
        tingen/assets/characters/archive_clerk_finch.png.import
git commit -m "$(cat <<'EOF'
feat(archive): add University archive background + Ledger Finch art

Reading-room backdrop and the records-clerk figure (both from the existing
gpt-image-1 pipeline outputs), copied in as finished PNGs.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Commit group B — the data (dialogue tree + clues)**

```bash
cd "$REPO"
git add tingen/data/dialogue.json tingen/data/clues.json
git commit -m "$(cat <<'EOF'
feat(archive): add finch dialogue tree + four archive clues

Placeholder 'finch' tree (LLM-driven later); the 'volume' branch collects
finch_cover. Four clues: archive_antigonus, restricted_volume_missing,
contamination_chain (the Welch chain), finch_cover. No lead is set — the
room surfaces clues/thoughts, it does not command a next objective.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Commit group C — the scene, wiring test, and City door**

```bash
cd "$REPO"
git add tingen/scenes/UniversityArchive.tscn tingen/scenes/City.tscn \
        tingen/tests/test_university_archive.gd
# include the .uid sidecars if Godot generated them:
git add tingen/scenes/UniversityArchive.tscn.uid 2>/dev/null || true
git add tingen/tests/test_university_archive.gd.uid 2>/dev/null || true
git commit -m "$(cat <<'EOF'
feat(archive): build top-down archive room, wire City door + wiring test

Flat-photo reading room mirroring NighthawksHQ: Solids colliders over the
furniture, Ledger Finch as a talk-hotspot, three examine hotspots (card
catalogue, restricted shelf, abandoned reading-desk notes), and an exit
door back to the City. One optional UniversityDoor added to City.tscn.
Headless wiring test asserts the whole chain.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Verify the commits and a clean tree**

```bash
cd "$REPO" && git log --oneline -3 && echo "---" && git status --short
```
Expected: the three `feat(archive): ...` commits on top; `git status` shows no leftover staged slice files (untracked `docs/superpowers/` is fine — gitignored).

> Pushing to origin is a separate step — only on Mark's explicit request (and if the HTTP/2 sideband error recurs, push with the one-shot override `git -c http.version=HTTP/1.1 -c http.postBuffer=524288000 push origin <sha>:refs/heads/main`, which does not modify stored git config).

---

## Deferred / future (out of scope for this slice)

- **Welch's lodging** scene — the contamination chain's thought-only "could-do" target; a later slice.
- Finch becomes LLM-driven (the static `"finch"` tree is a stand-in); add Finch + Welch + Antigonus to `npcs.json` for the sim layer.
- Precise City return-spawn; real City street art (the City is still a stub).
