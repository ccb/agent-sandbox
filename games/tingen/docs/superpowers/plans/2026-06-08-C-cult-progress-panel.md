# Plan C — Cult progress panel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A toggleable panel (key **C**) showing the player how close the cult is to summoning the descending god — a closeness bar (from the countdown), the ritual stock they've gathered and how far the player's interference has set them back — alongside recent **publicly-known** events and the player's own collected leads/clues. The hidden manifestation strength is never shown as a raw number; the player reads the threat through these proxies.

**Architecture:** `SummoningPlan` gains pure read-out helpers (`closeness_ratio()`, `interference_band()`, `ingredients_ratio()`, plus a `START_COUNTDOWN` const). A `CultProgressPanel` Panel in the HUD renders them, filters `EventBus.latest()` to a public whitelist (the cult's secret `agent_action` moves are excluded), and lists `ClueDB`/`WorldState` intel. `HUD.gd` toggles it on the new `toggle_cult` input action.

**Tech Stack:** Godot 4.6, GDScript. Depends on Plan A (live countdown). Independent of B/D/E/F.

**Key facts:**
- `SummoningPlan.gd` is an autoload Node; it already has `ingredients` (Dictionary), `impede_score`, `countdown_beats`, private `_total_ingredients()`/`_initial_total`. `closeness_ratio` etc. are added as same-class methods (no `_al` needed).
- `ClueDB` API: `collected_count() -> int`, `collected_clues() -> Array` (each a clue dict with `name`/`type`/`importance`), signal `clue_collected`.
- `EventBus.latest(n)` returns recent events `{seq,type,data,day,minute,beat}`; `EventBus.events(type)` filters.
- Input actions in `project.godot` are `InputEventKey` objects keyed by `physical_keycode`. Letter **C** = `67`.
- HUD toggle pattern: `HUD.gd._unhandled_input` already handles `toggle_board`/`toggle_map`; the panel exposes `toggle()` like `DistrictMap`.

---

## Task C1: SummoningPlan read-out helpers

**Files:**
- Modify: `tingen/src/SummoningPlan.gd`
- Test: `tingen/tests/run_tests.gd` (add `_test_summoning_progress_readouts`, register after `_test_summoning_countdown_and_climax`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_summoning_progress_readouts() -> void:
	print("[summoning progress]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	SP.reset()
	_ok(is_equal_approx(SP.closeness_ratio(), 0.0), "fresh plan = 0 closeness")
	SP.countdown_beats = SP.START_COUNTDOWN / 2
	_ok(is_equal_approx(SP.closeness_ratio(), 0.5), "halfway countdown = 0.5 closeness")
	SP.countdown_beats = 0
	_ok(is_equal_approx(SP.closeness_ratio(), 1.0), "zero countdown = full closeness")
	_ok(is_equal_approx(SP.ingredients_ratio(), 1.0), "fresh stock = full ratio")
	_ok(SP.interference_band() == "none", "no impede = none band")
	SP.add_impede(40.0)
	_ok(SP.interference_band() == "heavy", "large impede = heavy band")
	SP.reset()
```

- [ ] **Step 2: Run to verify it fails** — helpers / const missing. FAIL.

- [ ] **Step 3: Implement**

In `tingen/src/SummoningPlan.gd`, add a const next to the others:

```gdscript
const START_COUNTDOWN: int = 40
```

Replace the literal `40` in the `var countdown_beats: int = 40` declaration and in `reset()` with `START_COUNTDOWN`:

```gdscript
var countdown_beats: int = START_COUNTDOWN
```
```gdscript
	countdown_beats = START_COUNTDOWN
```

Add the read-out helpers (after `manifestation_strength()`):

```gdscript
## How close the cult is to the summoning, 0 (just begun) .. 1 (imminent). Setbacks that
## push countdown_beats back above START_COUNTDOWN clamp the bar back toward 0 — the player
## sees their interference rewind the clock.
func closeness_ratio() -> float:
	return clampf(1.0 - float(countdown_beats) / float(START_COUNTDOWN), 0.0, 1.0)

## Fraction of the starting ritual stock the cell still holds, 0 .. 1.
func ingredients_ratio() -> float:
	return clampf(float(_total_ingredients()) / float(maxi(1, _initial_total)), 0.0, 1.0)

## Qualitative band for the hidden impede score — shown as words, never a raw number.
func interference_band() -> String:
	if impede_score <= 0.0:
		return "none"
	elif impede_score < 15.0:
		return "minor"
	elif impede_score < 35.0:
		return "significant"
	return "heavy"
```

- [ ] **Step 4: Run to verify it passes** — PASS incl. `[summoning progress]`.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/SummoningPlan.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(summoning): closeness/ingredients/interference read-outs for the cult panel

Adds START_COUNTDOWN const + closeness_ratio(), ingredients_ratio() and a
qualitative interference_band() so the cult progress panel can show the threat
without exposing the hidden strength as a number.
EOF
```

---

## Task C2: CultProgressPanel + toggle (key C)

**Files:**
- Create: `tingen/src/CultProgressPanel.gd`
- Create: `tingen/ui/CultProgressPanel.tscn`
- Modify: `tingen/project.godot` (add `toggle_cult` = C)
- Modify: `tingen/ui/HUD.tscn` (instance the panel)
- Modify: `tingen/src/HUD.gd` (toggle on `toggle_cult`)
- Test: `tingen/tests/run_tests.gd` (add `_test_cult_progress_panel`, register after `_test_summoning_progress_readouts`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_cult_progress_panel() -> void:
	print("[cult panel]")
	var SP: Object = root.get_node("/root/SummoningPlan"); SP.reset()
	var EB: Object = root.get_node("/root/EventBus"); EB.clear()
	var panel = preload("res://ui/CultProgressPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "panel hidden by default")
	SP.countdown_beats = SP.START_COUNTDOWN / 2
	panel.toggle()
	await process_frame
	_ok(panel.visible, "panel toggles visible")
	_ok(is_equal_approx(panel.get_node("Margin/Body/Closeness/Bar").value, 50.0), "closeness bar at 50%")
	EB.emit_event("agent_action", {"actor": "clerk_voss", "verb": "perform_ritual_step"})
	EB.emit_event("player_sabotage", {"actor": "player", "item": "candle"})
	var joined := ""
	for line in panel.public_event_lines():
		joined += String(line) + "\n"
	_ok("player sabotage" in joined, "public player event is listed")
	_ok(not ("perform_ritual_step" in joined), "secret agent_action is excluded")
	panel.queue_free()
	await process_frame
	SP.reset(); EB.clear()
```

- [ ] **Step 2: Run to verify it fails** — scene does not exist. FAIL.

- [ ] **Step 3: Create the panel script**

Create `tingen/src/CultProgressPanel.gd`:

```gdscript
extends Panel
## Cult progress panel (toggle: C). Shows how close the cult is to summoning the descending
## god (外神) — a closeness bar from the countdown, the ritual stock they hold, and the
## qualitative dent the player's interference has made — plus recent publicly-known events
## and the player's own collected leads/clues. The hidden manifestation strength is never a
## raw number here; the player reads the threat through these proxies.

## EventBus types the public / the player would plausibly know. The cult's own agent_action
## moves are secret and deliberately excluded.
const PUBLIC_TYPES: Array = [
	"player_sabotage", "player_social", "player_occult",
	"event", "world_pressure", "summoning_climax", "combat_resolved",
]
const RECENT: int = 10

@onready var _closeness: ProgressBar = $Margin/Body/Closeness/Bar
@onready var _summary: Label = $Margin/Body/Summary
@onready var _ingredients: Label = $Margin/Body/Ingredients
@onready var _events: VBoxContainer = $Margin/Body/Events/List
@onready var _intel: VBoxContainer = $Margin/Body/Intel/List

func _ready() -> void:
	visible = false
	EventBus.event_logged.connect(func(_e): if visible: refresh())
	WorldState.state_changed.connect(func(): if visible: refresh())

func toggle() -> void:
	visible = not visible
	if visible:
		refresh()

func refresh() -> void:
	_closeness.value = SummoningPlan.closeness_ratio() * 100.0
	_summary.text = _summary_line()
	_ingredients.text = _ingredients_line()
	_fill(_events, public_event_lines())
	_fill(_intel, intel_lines())

func _summary_line() -> String:
	var pct := int(round(SummoningPlan.closeness_ratio() * 100.0))
	return "Summoning readiness: %d%%   ·   your interference: %s" % [pct, SummoningPlan.interference_band()]

func _ingredients_line() -> String:
	var parts: PackedStringArray = []
	for k in SummoningPlan.ingredients.keys():
		parts.append("%s ×%d" % [String(k).replace("_", " "), int(SummoningPlan.ingredients[k])])
	if parts.is_empty():
		return "Ritual stock: stripped bare."
	return "Ritual stock: " + ", ".join(parts)

func public_event_lines() -> Array:
	var out: Array = []
	for e in EventBus.latest(RECENT):
		if String(e.get("type", "")) in PUBLIC_TYPES:
			out.append("• " + _format_event(e))
	if out.is_empty():
		out.append("• Nothing of public note yet.")
	return out

func _format_event(e: Dictionary) -> String:
	var t := String(e.get("type", "")).replace("_", " ")
	var who := String((e.get("data", {}) as Dictionary).get("actor", ""))
	return "%s — %s" % [t, who] if who != "" else t

func intel_lines() -> Array:
	var out: Array = ["Lead: " + WorldState.current_lead, "Clues collected: %d" % ClueDB.collected_count()]
	for clue in ClueDB.collected_clues():
		if String(clue.get("importance", "")) == "pivotal":
			out.append("  ★ " + String(clue.get("name", "?")))
	return out

func _fill(box: VBoxContainer, lines: Array) -> void:
	for c in box.get_children():
		c.queue_free()
	for line in lines:
		var l := Label.new()
		l.text = String(line)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		box.add_child(l)

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		visible = false
		get_viewport().set_input_as_handled()
```

- [ ] **Step 4: Create the panel scene**

Create `tingen/ui/CultProgressPanel.tscn`:

```
[gd_scene load_steps=2 format=3 uid="uid://b1tngncult0001"]

[ext_resource type="Script" path="res://src/CultProgressPanel.gd" id="1"]

[node name="CultProgressPanel" type="Panel"]
anchor_left = 0.5
anchor_top = 0.5
anchor_right = 0.5
anchor_bottom = 0.5
offset_left = -300.0
offset_top = -240.0
offset_right = 300.0
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
theme_override_constants/separation = 8

[node name="Title" type="Label" parent="Margin/Body"]
text = "The Descent — Cult Progress"
horizontal_alignment = 1
theme_override_font_sizes/font_size = 18

[node name="Summary" type="Label" parent="Margin/Body"]
text = ""
horizontal_alignment = 1

[node name="Closeness" type="HBoxContainer" parent="Margin/Body"]
theme_override_constants/separation = 8

[node name="Label" type="Label" parent="Margin/Body/Closeness"]
custom_minimum_size = Vector2(90, 0)
text = "Closeness"

[node name="Bar" type="ProgressBar" parent="Margin/Body/Closeness"]
custom_minimum_size = Vector2(0, 16)
modulate = Color(0.8, 0.4, 0.45, 1)
size_flags_horizontal = 3
max_value = 100.0
value = 0.0
show_percentage = false

[node name="Ingredients" type="Label" parent="Margin/Body"]
text = ""
autowrap_mode = 2

[node name="Sep1" type="HSeparator" parent="Margin/Body"]

[node name="EventsLabel" type="Label" parent="Margin/Body"]
text = "Publicly known"
theme_override_colors/font_color = Color(0.85, 0.8, 0.6, 1)

[node name="Events" type="ScrollContainer" parent="Margin/Body"]
custom_minimum_size = Vector2(0, 120)
size_flags_vertical = 3

[node name="List" type="VBoxContainer" parent="Margin/Body/Events"]
custom_minimum_size = Vector2(540, 0)
theme_override_constants/separation = 2

[node name="Sep2" type="HSeparator" parent="Margin/Body"]

[node name="IntelLabel" type="Label" parent="Margin/Body"]
text = "What you know"
theme_override_colors/font_color = Color(0.6, 0.78, 0.85, 1)

[node name="Intel" type="ScrollContainer" parent="Margin/Body"]
custom_minimum_size = Vector2(0, 100)

[node name="List" type="VBoxContainer" parent="Margin/Body/Intel"]
custom_minimum_size = Vector2(540, 0)
theme_override_constants/separation = 2

[node name="Hint" type="Label" parent="Margin/Body"]
text = "C or Esc to close"
horizontal_alignment = 1
theme_override_colors/font_color = Color(0.55, 0.55, 0.6, 1)
```

- [ ] **Step 5: Add the `toggle_cult` input action**

In `tingen/project.godot`, inside the `[input]` section (after `toggle_console={...}`), add (physical keycode 67 = C):

```
toggle_cult={
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":67,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]
}
```

- [ ] **Step 6: Instance in HUD + wire the toggle**

In `tingen/ui/HUD.tscn`: bump `load_steps` by 1, add `[ext_resource type="PackedScene" path="res://ui/CultProgressPanel.tscn" id="7"]`, and append:

```
[node name="CultProgress" parent="." instance=ExtResource("7")]
visible = false
```

In `tingen/src/HUD.gd`: add the ref `@onready var _cult: Control = $CultProgress` and, in `_unhandled_input`, add a branch:

```gdscript
	elif event.is_action_pressed("toggle_cult"):
		_cult.toggle()
		get_viewport().set_input_as_handled()
```

- [ ] **Step 7: Run to verify it passes** — `godot --headless --path tingen -s tests/run_tests.gd` → PASS incl. `[cult panel]`.

- [ ] **Step 8: Smoke-run** — `godot --headless --path tingen --quit-after 60` → no script errors.

- [ ] **Step 9: Commit**

```bash
git add tingen/src/CultProgressPanel.gd tingen/ui/CultProgressPanel.tscn tingen/project.godot tingen/ui/HUD.tscn tingen/src/HUD.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(ui): cult progress panel (C) — closeness, stock, public events, your intel

Toggleable panel showing summoning closeness (from the countdown), ritual stock,
qualitative interference, recent publicly-known events (cult agent_action moves
excluded) and the player's collected leads/clues.
EOF
```

---

## Done when

- `SummoningPlan.closeness_ratio/ingredients_ratio/interference_band` behave (`_test_summoning_progress_readouts`).
- The panel toggles, the closeness bar tracks the countdown, and the public-event filter excludes secret `agent_action` while showing player events (`_test_cult_progress_panel`).
- Pressing **C** opens/closes it in-game; full suite green; boots clean.
