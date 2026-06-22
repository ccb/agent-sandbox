# Plan D — Ritual & occult-tool panel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A toggleable panel (key **R**) that specifies, for every occult practice, its **usage** (what it does) and **requirements/costs** — the player's own occult tools (the actionable ones, with a Use button gated on availability) and a read-only reference card for the cult's summoning rite (its ingredient recipe and ritual steps).

**Architecture:** `OccultToolManager` gains a UI-facing `tool_views()` accessor that flattens each tool's name/description/required-item/cost/uses-left/can-use into a plain dict (the manager's `_tools` are private today). A one-line `description` is added to each tool in `occult_tools.json`. A new `data/rituals.json` describes the summoning rite as a recipe + steps. A `RitualPanel` Panel renders both sections; `HUD.gd` toggles it on `toggle_rituals`.

**Tech Stack:** Godot 4.6, GDScript. Independent of B/C/E/F (only shares the HUD).

**Key facts:**
- `OccultToolManager` (autoload Node) holds `_tools: id -> OccultTool`. `OccultTool` has `def` (its JSON), `compute_cost() -> {fatigue, attention, items}`, `can_use() -> bool`, `uses_left: int` (-1 = unlimited). `OccultToolManager.use(id)` pays costs + surfaces leads.
- `occult_tools.json` fields today: `name`, `item_id`, `fatigue_cost`, `attention_cost`, `ingredient_cost`, `uses_per_run`, optional `produces`. Unknown fields (like a new `description`) are ignored by the loader.
- `Inventory` (autoload) exposes `count_of(id)`, `has(id, n)`, `items()`.
- A panel may load JSON directly (`DistrictMap` does: `FileAccess.get_file_as_string` + `JSON.parse_string`).
- Input action letter **R** = physical keycode `82`.

---

## Task D1: occult_tools descriptions + OccultToolManager.tool_views()

**Files:**
- Modify: `tingen/data/occult_tools.json` (add a `description` to each tool)
- Modify: `tingen/src/OccultToolManager.gd` (add `tool_views()`)
- Test: `tingen/tests/run_tests.gd` (add `_test_occult_tool_views`, register after `_test_occult_other_tools`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_occult_tool_views() -> void:
	print("[occult tool views]")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var views: Array = OTM.tool_views()
	_ok(views.size() == 4, "four occult tools surfaced")
	var div: Variant = null
	for v in views:
		if v["id"] == "divination":
			div = v
	_ok(div != null, "divination present")
	_ok(String(div["name"]) == "Divination", "name surfaced")
	_ok(String(div["description"]) != "", "description surfaced")
	_ok(is_equal_approx(float(div["cost"]["fatigue"]), 8.0), "fatigue cost surfaced")
	_ok((div["cost"]["items"] as Dictionary).has("candle"), "ingredient cost surfaced")
	_ok(div.has("can_use") and div.has("uses_left"), "availability fields surfaced")
```

- [ ] **Step 2: Run to verify it fails** — `tool_views` missing. FAIL.

- [ ] **Step 3: Add descriptions to occult_tools.json**

Add a `"description"` line to each tool object in `tingen/data/occult_tools.json` (insert as the first field after the opening brace of each; keep valid JSON — commas matter):

- `divination`: `"description": "Cast the lots and read the omens — points you toward where the corruption is gathering.",`
- `residue_sight`: `"description": "See the spiritual residue clinging to a place or object; recent presences linger there.",`
- `dream_fragments`: `"description": "Sift a sleeper's dream for fragments of what they witnessed.",`
- `gray_fog`: `"description": "Reconstruct a scene out of the Gray Fog — vivid, but it draws the Fog's attention to you.",`

- [ ] **Step 4: Add `tool_views()` to OccultToolManager**

In `tingen/src/OccultToolManager.gd`, add (after `use()`):

```gdscript
## UI-facing snapshot of every tool: name, usage text, what it requires and costs, how many
## uses remain and whether it can be used right now. Sorted by name for a stable panel.
func tool_views() -> Array:
	var out: Array = []
	for id in _tools.keys():
		var t: OccultTool = _tools[id]
		out.append({
			"id": id,
			"name": String(t.def.get("name", id)),
			"description": String(t.def.get("description", "")),
			"requires_item": String(t.def.get("item_id", "")),
			"cost": t.compute_cost(),
			"produces": (t.def.get("produces", {}) as Dictionary).duplicate(true),
			"uses_left": t.uses_left,
			"can_use": t.can_use(),
		})
	out.sort_custom(func(a, b): return String(a["name"]) < String(b["name"]))
	return out
```

- [ ] **Step 5: Run to verify it passes** — PASS incl. `[occult tool views]`.

- [ ] **Step 6: Commit**

```bash
git add tingen/data/occult_tools.json tingen/src/OccultToolManager.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(occult): tool_views() accessor + per-tool descriptions for the ritual panel

OccultToolManager.tool_views() flattens each tool's name/usage/required-item/
cost/uses/can-use for the UI; occult_tools.json gains a one-line description per
tool.
EOF
```

---

## Task D2: rituals.json + RitualPanel (key R)

**Files:**
- Create: `tingen/data/rituals.json`
- Create: `tingen/src/RitualPanel.gd`
- Create: `tingen/ui/RitualPanel.tscn`
- Modify: `tingen/project.godot` (add `toggle_rituals` = R)
- Modify: `tingen/ui/HUD.tscn` (instance the panel)
- Modify: `tingen/src/HUD.gd` (toggle on `toggle_rituals`)
- Test: `tingen/tests/run_tests.gd` (add `_test_ritual_panel`, register after `_test_occult_tool_views`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_ritual_panel() -> void:
	print("[ritual panel]")
	var panel = preload("res://ui/RitualPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "panel hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "panel toggles visible")
	_ok(panel.tool_row_count() == 4, "renders one row per occult tool")
	_ok(panel.rite_step_count() >= 3, "summoning rite lists its steps")
	panel.queue_free()
	await process_frame
```

- [ ] **Step 2: Run to verify it fails** — scene does not exist. FAIL.

- [ ] **Step 3: Create rituals.json**

Create `tingen/data/rituals.json`:

```json
{
	"summoning_descent": {
		"name": "The Descent",
		"actor": "cult",
		"description": "The Iron Cross cell's rite to call the descending god (外神) into Tingen. Each ingredient binds another thread of the gate; the final step demands the marked sacrifice.",
		"ingredients": { "ritual_salt": 3, "consecrated_chalk": 2, "candle": 3 },
		"steps": [
			"Inscribe the consecrated circle in chalk.",
			"Set and light the three candles at its points.",
			"Lay the salt wards and speak the descending name.",
			"Offer the marked sacrifice to open the gate."
		]
	}
}
```

- [ ] **Step 4: Create the RitualPanel script**

Create `tingen/src/RitualPanel.gd`:

```gdscript
extends Panel
## Rituals & occult practices panel (toggle: R). Two sections:
##   1. Your occult practices — every player tool with its usage, requirements and costs, and
##      a Use button enabled only when it can be used right now (OccultToolManager.tool_views).
##   2. The Descent — a read-only reference for the cult's summoning rite (recipe + steps),
##      loaded from data/rituals.json.

const RITUALS_PATH: String = "res://data/rituals.json"

@onready var _tools_box: VBoxContainer = $Margin/Body/Scroll/List/Tools
@onready var _rite_box: VBoxContainer = $Margin/Body/Scroll/List/Rite

var _rituals: Dictionary = {}
var _tool_rows: int = 0
var _rite_steps: int = 0

func _ready() -> void:
	visible = false
	_load_rituals()
	Inventory.item_added.connect(func(_i, _c): if visible: refresh())
	Inventory.item_removed.connect(func(_i, _c): if visible: refresh())

func _load_rituals() -> void:
	if not FileAccess.file_exists(RITUALS_PATH):
		push_error("RitualPanel: missing %s" % RITUALS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(RITUALS_PATH))
	if typeof(parsed) == TYPE_DICTIONARY:
		_rituals = parsed

func toggle() -> void:
	visible = not visible
	if visible:
		refresh()

func tool_row_count() -> int:
	return _tool_rows

func rite_step_count() -> int:
	return _rite_steps

func refresh() -> void:
	_build_tools()
	_build_rite()

func _build_tools() -> void:
	for c in _tools_box.get_children():
		c.queue_free()
	_tool_rows = 0
	for v in OccultToolManager.tool_views():
		_tools_box.add_child(_tool_row(v))
		_tool_rows += 1

func _tool_row(v: Dictionary) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	_label(box, String(v["name"]), Color(0.7, 0.45, 0.85), 16)
	_label(box, String(v["description"]), Color(0.82, 0.82, 0.86))
	var req := "Requires: %s" % _humanize(String(v["requires_item"]))
	var ing: Dictionary = (v["cost"] as Dictionary)["items"]
	for k in ing.keys():
		req += ", %s ×%d" % [_humanize(String(k)), int(ing[k])]
	_label(box, req, Color(0.7, 0.7, 0.75))
	var cost: Dictionary = v["cost"]
	var uses := "unlimited" if int(v["uses_left"]) < 0 else "%d left" % int(v["uses_left"])
	_label(box, "Cost: fatigue +%d, attention +%d   ·   uses: %s" % [
		int(cost["fatigue"]), int(cost["attention"]), uses], Color(0.7, 0.7, 0.75))
	var use_btn := Button.new()
	use_btn.text = "Use"
	use_btn.disabled = not bool(v["can_use"])
	var id := String(v["id"])
	use_btn.pressed.connect(func(): _on_use(id))
	box.add_child(use_btn)
	box.add_child(HSeparator.new())
	return box

func _on_use(id: String) -> void:
	var res: Dictionary = OccultToolManager.use(id)
	WorldState.thought_requested.emit(String(res.get("text", "Nothing comes.")))
	refresh()

func _build_rite() -> void:
	for c in _rite_box.get_children():
		c.queue_free()
	_rite_steps = 0
	var rite: Dictionary = _rituals.get("summoning_descent", {})
	if rite.is_empty():
		return
	_label(_rite_box, String(rite.get("name", "The Descent")), Color(0.85, 0.45, 0.45), 16)
	_label(_rite_box, String(rite.get("description", "")), Color(0.82, 0.82, 0.86))
	var ing: Dictionary = rite.get("ingredients", {})
	var recipe := "Requires: "
	var parts: PackedStringArray = []
	for k in ing.keys():
		parts.append("%s ×%d" % [_humanize(String(k)), int(ing[k])])
	_label(_rite_box, recipe + ", ".join(parts), Color(0.7, 0.7, 0.75))
	_label(_rite_box, "Steps:", Color(0.85, 0.8, 0.6))
	var i := 1
	for step in rite.get("steps", []):
		_label(_rite_box, "  %d. %s" % [i, String(step)], Color(0.82, 0.82, 0.86))
		i += 1
		_rite_steps += 1

func _label(box: VBoxContainer, text: String, color: Color, font_size: int = 0) -> void:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", color)
	if font_size > 0:
		l.add_theme_font_size_override("font_size", font_size)
	box.add_child(l)

func _humanize(id: String) -> String:
	return id.replace("_", " ") if id != "" else "—"

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		visible = false
		get_viewport().set_input_as_handled()
```

- [ ] **Step 5: Create the RitualPanel scene**

Create `tingen/ui/RitualPanel.tscn`:

```
[gd_scene load_steps=2 format=3 uid="uid://b1tngnritual01"]

[ext_resource type="Script" path="res://src/RitualPanel.gd" id="1"]

[node name="RitualPanel" type="Panel"]
anchor_left = 0.5
anchor_top = 0.5
anchor_right = 0.5
anchor_bottom = 0.5
offset_left = -320.0
offset_top = -250.0
offset_right = 320.0
offset_bottom = 250.0
grow_horizontal = 2
grow_vertical = 2
script = ExtResource("1")

[node name="Margin" type="MarginContainer" parent="."]
anchor_right = 1.0
anchor_bottom = 1.0
theme_override_constants/margin_left = 20
theme_override_constants/margin_top = 16
theme_override_constants/margin_right = 20
theme_override_constants/margin_bottom = 16

[node name="Body" type="VBoxContainer" parent="Margin"]
theme_override_constants/separation = 8

[node name="Title" type="Label" parent="Margin/Body"]
text = "Rituals & Occult Practices"
horizontal_alignment = 1
theme_override_font_sizes/font_size = 18

[node name="Scroll" type="ScrollContainer" parent="Margin/Body"]
custom_minimum_size = Vector2(0, 400)
size_flags_vertical = 3

[node name="List" type="VBoxContainer" parent="Margin/Body/Scroll"]
custom_minimum_size = Vector2(596, 0)
theme_override_constants/separation = 8

[node name="ToolsLabel" type="Label" parent="Margin/Body/Scroll/List"]
text = "Your occult practices"
theme_override_colors/font_color = Color(0.6, 0.78, 0.85, 1)

[node name="Tools" type="VBoxContainer" parent="Margin/Body/Scroll/List"]
theme_override_constants/separation = 6

[node name="Gap" type="HSeparator" parent="Margin/Body/Scroll/List"]

[node name="RiteLabel" type="Label" parent="Margin/Body/Scroll/List"]
text = "What the cult is assembling"
theme_override_colors/font_color = Color(0.85, 0.45, 0.45, 1)

[node name="Rite" type="VBoxContainer" parent="Margin/Body/Scroll/List"]
theme_override_constants/separation = 2

[node name="Hint" type="Label" parent="Margin/Body"]
text = "R or Esc to close"
horizontal_alignment = 1
theme_override_colors/font_color = Color(0.55, 0.55, 0.6, 1)
```

- [ ] **Step 6: Add the `toggle_rituals` input action**

In `tingen/project.godot`, inside `[input]`, add (physical keycode 82 = R):

```
toggle_rituals={
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":82,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]
}
```

- [ ] **Step 7: Instance in HUD + wire the toggle**

In `tingen/ui/HUD.tscn`: bump `load_steps`, add `[ext_resource type="PackedScene" path="res://ui/RitualPanel.tscn" id="8"]`, and append:

```
[node name="RitualPanel" parent="." instance=ExtResource("8")]
visible = false
```

In `tingen/src/HUD.gd`: add `@onready var _rituals: Control = $RitualPanel` and a branch in `_unhandled_input`:

```gdscript
	elif event.is_action_pressed("toggle_rituals"):
		_rituals.toggle()
		get_viewport().set_input_as_handled()
```

- [ ] **Step 8: Run to verify it passes** — `godot --headless --path tingen -s tests/run_tests.gd` → PASS incl. `[ritual panel]`.

- [ ] **Step 9: Smoke-run** — `godot --headless --path tingen --quit-after 60` → no script errors.

- [ ] **Step 10: Commit**

```bash
git add tingen/data/rituals.json tingen/src/RitualPanel.gd tingen/ui/RitualPanel.tscn tingen/project.godot tingen/ui/HUD.tscn tingen/src/HUD.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(ui): rituals & occult-practices panel (R)

RitualPanel lists each player occult tool with usage, requirements, costs and a
Use button gated on availability, plus a read-only reference for the cult's
summoning rite (recipe + steps) from data/rituals.json.
EOF
```

---

## Done when

- `OccultToolManager.tool_views()` surfaces name/usage/requirements/cost/uses/can-use per tool (`_test_occult_tool_views`).
- The panel renders one row per tool and lists the summoning rite's steps (`_test_ritual_panel`); pressing **R** opens/closes it.
- Full suite green; boots clean.
