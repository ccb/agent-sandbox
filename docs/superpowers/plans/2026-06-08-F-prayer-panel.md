# Plan F — Prayer panel (UI)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A toggleable panel (key **P**) where the player picks a god from the focused pantheon, writes a prayer in their own words, offers it, and reads the god's adjudicated answer — **Granted (应允)**, **Cryptic (神秘应答)**, **Ignored (无应)**, **Punished (惩罚)** — styled by outcome, with current per-god standing shown on each god's button.

**Architecture:** A `PrayerPanel` Panel renders the pantheon as a column of buttons (from `GodDB.all()`), a multi-line prayer entry, an "Offer Prayer" button, and a BBCode response area. Submitting routes to `PrayerService.pray(god_id, text)` (Plan E) and renders the returned outcome dict with an outcome-keyed colour. `HUD.gd` toggles it on `toggle_prayer`. Follows the established panel pattern (`toggle()`, hidden by default, `_unhandled_input` closes on Esc) and exposes pure seams (`god_button_count()`, `selected_god()`, `last_outcome()`, `submit_prayer()`) so it is testable headlessly.

**Tech Stack:** Godot 4.6, GDScript. **Depends on Plan E** (`GodDB`, `PrayerService`, `MockSidecar.adjudicate_prayer`). Shares only the HUD with B/C/D.

**Key facts (verified):**
- `GodDB.all()` → Array of god defs each with `id`, `name`, `name_zh`, `domain`, `blurb`, … (sorted by id). `GodDB.ids()` → sorted ids.
- `PrayerService.pray(god_id, text)` → `{ ok, god, outcome, outcome_zh, severity, message, struck_down }` (or `{ ok:false, reason }`). `PrayerService.get_standing(god_id)` → float.
- Panel pattern: a `Panel` script with `func toggle()`, `visible = false` in `_ready()`, and `_unhandled_input` consuming `ui_cancel`. `HUD.gd._unhandled_input` adds a branch per panel; `HUD.tscn` instances each panel `visible = false`.
- HUD ext-resource ids so far: 1 script, 2 board, 3 dialogue, 4 toasts, 5 map; Plan B uses 6 (CharacterCard), C uses 7 (CultProgressPanel), D uses 8 (RitualPanel). **This panel uses id `9`.**
- Input action letter **P** = physical keycode `80`.

---

## Task F1: PrayerPanel (key P) wired to PrayerService

**Files:**
- Create: `tingen/src/PrayerPanel.gd`
- Create: `tingen/ui/PrayerPanel.tscn`
- Modify: `tingen/project.godot` (add `toggle_prayer` = P)
- Modify: `tingen/ui/HUD.tscn` (instance the panel)
- Modify: `tingen/src/HUD.gd` (toggle on `toggle_prayer`)
- Test: `tingen/tests/run_tests.gd` (add `_test_prayer_panel`, register after `_test_prayer_parity_with_sidecar`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_prayer_panel() -> void:
	print("[prayer panel]")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var PS: Object = root.get_node("/root/PrayerService")
	SB.set_client(MockSidecar.new())   # deterministic adjudication
	PS.reset()
	var panel = preload("res://ui/PrayerPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "panel hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "panel toggles visible")
	_ok(panel.god_button_count() == 4, "one button per god in the pantheon")
	# A respectful, domain-aligned prayer is granted and rendered.
	var g: Dictionary = panel.submit_prayer("goddess_of_night", "i humbly beseech your mercy this night, please protect me")
	_ok(g["outcome"] == "granted", "panel routes a granted prayer")
	_ok(panel.last_outcome() == "granted", "panel records the rendered outcome")
	# An insulting prayer is punished.
	panel.submit_prayer("eternal_blazing_sun", "obey me, you worthless weak sun, kneel")
	_ok(panel.last_outcome() == "punished", "panel renders a punishment")
	# Selecting a god updates the selection seam.
	panel.toggle()  # hide
	await process_frame
	_ok(not panel.visible, "panel toggles back hidden")
	panel.queue_free()
	await process_frame
```

Register after `_test_prayer_parity_with_sidecar()`:

```gdscript
	_test_prayer_parity_with_sidecar()
	_test_prayer_panel()
```

- [ ] **Step 2: Run to verify it fails** — scene does not exist. FAIL.

- [ ] **Step 3: Create `tingen/src/PrayerPanel.gd`**

```gdscript
extends Panel
## Prayer panel (toggle: P). Pick a god from the focused Tingen pantheon, offer a prayer in
## your own words, and read the god's adjudicated answer — Granted (应允), Cryptic (神秘应答),
## Ignored (无应) or Punished (惩罚) — coloured by outcome. Wires to PrayerService.pray()
## (Plan E); each god button shows current standing.

const OUTCOME_COLORS: Dictionary = {
	"granted": Color(0.55, 0.85, 0.55),
	"cryptic": Color(0.72, 0.5, 0.9),
	"ignored": Color(0.6, 0.6, 0.65),
	"punished": Color(0.9, 0.4, 0.4),
}

@onready var _gods_box: VBoxContainer = $Margin/Body/Cols/Left/Gods
@onready var _prayer_edit: TextEdit = $Margin/Body/Cols/Right/PrayerEdit
@onready var _pray_btn: Button = $Margin/Body/Cols/Right/PrayButton
@onready var _selected_label: Label = $Margin/Body/Cols/Right/SelectedGod
@onready var _response: RichTextLabel = $Margin/Body/Cols/Right/Response

var _selected: String = ""
var _god_buttons: int = 0
var _last_outcome: String = ""

func _ready() -> void:
	visible = false
	_pray_btn.pressed.connect(_on_pray)
	_build_gods()

func toggle() -> void:
	visible = not visible
	if visible:
		_build_gods()
		_refresh_selected()

func god_button_count() -> int:
	return _god_buttons

func selected_god() -> String:
	return _selected

func last_outcome() -> String:
	return _last_outcome

## Headless-testable entry: select a god, offer a prayer, render the response. Returns the
## PrayerService outcome dict.
func submit_prayer(god_id: String, text: String) -> Dictionary:
	_selected = god_id
	var res: Dictionary = PrayerService.pray(god_id, text)
	_render_response(res)
	return res

func _build_gods() -> void:
	for c in _gods_box.get_children():
		c.queue_free()
	_god_buttons = 0
	for god in GodDB.all():
		var id := String(god["id"])
		var standing := PrayerService.get_standing(id)
		var btn := Button.new()
		btn.text = "%s (%s)   ·   standing %+d" % [
			String(god.get("name", "?")), String(god.get("name_zh", "")), int(round(standing))]
		btn.tooltip_text = String(god.get("blurb", ""))
		btn.toggle_mode = true
		btn.button_pressed = (id == _selected)
		btn.pressed.connect(func() -> void: _select(id))
		_gods_box.add_child(btn)
		_god_buttons += 1
	if _selected == "" and _god_buttons > 0:
		_select(String(GodDB.ids()[0]))

func _select(id: String) -> void:
	_selected = id
	_refresh_selected()

func _refresh_selected() -> void:
	if _selected == "":
		_selected_label.text = "Choose a god to petition."
		return
	var god: Dictionary = GodDB.get_def(_selected)
	_selected_label.text = "%s · %s\n%s" % [
		String(god.get("name", "?")), String(god.get("name_zh", "")), String(god.get("blurb", ""))]

func _on_pray() -> void:
	if _selected == "":
		return
	submit_prayer(_selected, _prayer_edit.text)

func _render_response(res: Dictionary) -> void:
	if not bool(res.get("ok", false)):
		_last_outcome = ""
		_response.text = "[i]%s[/i]" % String(res.get("reason", "The prayer falters."))
		return
	_last_outcome = String(res.get("outcome", ""))
	var color: Color = OUTCOME_COLORS.get(_last_outcome, Color.WHITE)
	var header := "%s (%s)" % [_last_outcome.capitalize(), String(res.get("outcome_zh", ""))]
	_response.text = "[color=#%s][b]%s[/b][/color]\n%s" % [
		color.to_html(false), header, String(res.get("message", ""))]
	_build_gods()   # standing may have changed -> refresh the buttons

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		visible = false
		get_viewport().set_input_as_handled()
```

- [ ] **Step 4: Create `tingen/ui/PrayerPanel.tscn`**

```
[gd_scene load_steps=2 format=3 uid="uid://b1tngnprayer01"]

[ext_resource type="Script" path="res://src/PrayerPanel.gd" id="1"]

[node name="PrayerPanel" type="Panel"]
anchor_left = 0.5
anchor_top = 0.5
anchor_right = 0.5
anchor_bottom = 0.5
offset_left = -340.0
offset_top = -240.0
offset_right = 340.0
offset_bottom = 240.0
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
theme_override_constants/separation = 10

[node name="Title" type="Label" parent="Margin/Body"]
text = "Prayer (祈祷)"
horizontal_alignment = 1
theme_override_font_sizes/font_size = 18

[node name="Cols" type="HBoxContainer" parent="Margin/Body"]
size_flags_vertical = 3
theme_override_constants/separation = 14

[node name="Left" type="VBoxContainer" parent="Margin/Body/Cols"]
custom_minimum_size = Vector2(300, 0)
theme_override_constants/separation = 6

[node name="GodsLabel" type="Label" parent="Margin/Body/Cols/Left"]
text = "The Pantheon"
theme_override_colors/font_color = Color(0.6, 0.78, 0.85, 1)

[node name="Gods" type="VBoxContainer" parent="Margin/Body/Cols/Left"]
theme_override_constants/separation = 6

[node name="Right" type="VBoxContainer" parent="Margin/Body/Cols"]
size_flags_horizontal = 3
theme_override_constants/separation = 8

[node name="SelectedGod" type="Label" parent="Margin/Body/Cols/Right"]
autowrap_mode = 2
text = "Choose a god to petition."
theme_override_colors/font_color = Color(0.82, 0.82, 0.86, 1)

[node name="PrayerEdit" type="TextEdit" parent="Margin/Body/Cols/Right"]
custom_minimum_size = Vector2(0, 120)
placeholder_text = "Speak your prayer in your own words..."
wrap_mode = 1

[node name="PrayButton" type="Button" parent="Margin/Body/Cols/Right"]
text = "Offer Prayer"

[node name="Response" type="RichTextLabel" parent="Margin/Body/Cols/Right"]
custom_minimum_size = Vector2(0, 140)
size_flags_vertical = 3
bbcode_enabled = true
fit_content = true

[node name="Hint" type="Label" parent="Margin/Body"]
text = "P or Esc to close"
horizontal_alignment = 1
theme_override_colors/font_color = Color(0.55, 0.55, 0.6, 1)
```

- [ ] **Step 5: Add the `toggle_prayer` input action**

In `tingen/project.godot`, inside `[input]`, add (physical keycode 80 = P):

```
toggle_prayer={
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":80,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]
}
```

- [ ] **Step 6: Instance in HUD + wire the toggle**

In `tingen/ui/HUD.tscn`: bump `load_steps` by 1, add the ext_resource (use id `9` per the HUD id map above):

```
[ext_resource type="PackedScene" path="res://ui/PrayerPanel.tscn" id="9"]
```

and append an instance node:

```
[node name="PrayerPanel" parent="." instance=ExtResource("9")]
visible = false
```

In `tingen/src/HUD.gd`: add `@onready var _prayer: Control = $PrayerPanel` (next to the other panel `@onready`s) and a branch in `_unhandled_input`:

```gdscript
	elif event.is_action_pressed("toggle_prayer"):
		_prayer.toggle()
		get_viewport().set_input_as_handled()
```

- [ ] **Step 7: Run to verify it passes** — `godot --headless --path tingen -s tests/run_tests.gd` → PASS incl. `[prayer panel]`.

- [ ] **Step 8: Smoke-run** — `godot --headless --path tingen --quit-after 60` → no script errors; HUD instances the panel clean.

- [ ] **Step 9: Commit**

```bash
git add tingen/src/PrayerPanel.gd tingen/ui/PrayerPanel.tscn tingen/project.godot tingen/ui/HUD.tscn tingen/src/HUD.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(ui): prayer panel (P) — petition a god, read its answer

PrayerPanel lists the focused pantheon (with per-god standing), takes a free-text
prayer, routes it through PrayerService.pray(), and renders the adjudicated outcome
(granted/cryptic/ignored/punished) coloured by category. Toggle with P.
EOF
```

---

## Done when

- Pressing **P** opens/closes the panel; it lists one button per god with current standing (`_test_prayer_panel`).
- Submitting a prayer routes through `PrayerService` and renders the outcome with its category colour + 中文 label; `last_outcome()` reflects the rendered verdict.
- Full suite green; boots clean.
