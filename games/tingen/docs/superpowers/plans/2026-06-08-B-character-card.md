# Plan B — NPC click → character card

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Click an NPC to bring up a character card showing that agent's live **thought**, **current goal** (its long-horizon `intent`), and **recent actions** (its `short_memory`), refreshing while open as the beat loop advances.

**Architecture:** Adds an `Agent.thought` field (set from the action a sidecar/critic produces, else synthesized deterministically from the agent's current action) plus an `Agent.describe_thought()` accessor. `ActionCommit` stores each action's `thought` (or clears it) when it commits. A `CharacterCard` Panel in the HUD opens on a new `WorldState.inspect_requested(agent_id)` signal, which `NPC.gd` emits when its `TalkArea` is left-clicked.

**Tech Stack:** Godot 4.6, GDScript. Depends on Plan A (NPCs are registry-bound).

**Key facts:**
- `Agent.gd` is `class_name Agent extends RefCounted`; `ActionCommit.gd` is `class_name` (uses `_al()` for autoloads). The edits here are plain field/string work — no new autoload lookups needed.
- `NPC.gd`, `CharacterCard.gd`, `WorldState.gd` are scene/autoload scripts that may use bare autoload references.
- `WorldState.gd` already documents itself as "a lightweight signal bus so any scene can surface info without holding direct references to the HUD" — `inspect_requested` belongs there alongside `thought_requested`/`transition_requested`. (*Alt rejected:* a brand-new UIEvents autoload — the project already has 19 and WorldState is the documented bus.)
- `Area2D.input_event` fires `(viewport, event, shape_idx)`; `TalkArea` already exists on `NPC.tscn` with a 56px shape and `input_pickable` defaults true.

---

## Task B1: Agent.thought field + describe_thought()

**Files:**
- Modify: `tingen/src/Agent.gd`
- Test: `tingen/tests/run_tests.gd` (add `_test_agent_thought`, register after `_test_agent_registry`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_agent_thought() -> void:
	print("[agent thought]")
	var a := Agent.new("voss")
	a.intent = "Complete the warehouse summoning."
	_ok(a.describe_thought().length() > 0, "idle agent has a synthesized thought")
	a.current_action = {"verb": "move_to", "args": {"target": "warehouse"}}
	_ok("warehouse" in a.describe_thought(), "thought reflects the current move target")
	a.thought = "I sense I am being watched."
	_ok(a.describe_thought() == "I sense I am being watched.", "explicit thought overrides synthesis")
	var b := Agent.new()
	b.from_dict(a.to_dict())
	_ok(b.thought == a.thought, "thought round-trips through save")
```

- [ ] **Step 2: Run to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: FAIL — `thought` / `describe_thought` missing.

- [ ] **Step 3: Implement**

In `tingen/src/Agent.gd`, add the field after `var plan: Array = []`:

```gdscript
var thought: String = ""   # latest read-out: set by sidecar/critic, else synthesized
```

Add the accessor (after `remember`):

```gdscript
## The agent's moment-to-moment read-out for the character card. Returns an explicit
## thought when one was set (by a sidecar/critic), otherwise synthesizes one from the
## current action. Distinct from `intent`, which is the long-horizon goal.
func describe_thought() -> String:
	if thought != "":
		return thought
	var verb := String(current_action.get("verb", ""))
	var args: Dictionary = current_action.get("args", {})
	match verb:
		"move_to": return "Making my way to %s." % args.get("target", "somewhere")
		"talk_to": return "I should have words with %s." % args.get("agent", "them")
		"gather_item": return "I still need the %s." % args.get("item_id", "supplies")
		"perform_ritual_step": return "The rite must go on: %s." % args.get("step", "the next step")
		"recruit": return "Could %s be brought into the fold?" % args.get("agent", "them")
		"report": return "Voss will want to hear of this."
		"hide": return "Best I am not seen just now."
		"flee": return "I have to get clear of %s." % args.get("from", "here")
		"attack": return "No choice left but to strike."
		_: return "Keeping to my own business... for now."
```

Add `"thought": thought,` to the `to_dict()` Dictionary, and `thought = String(d.get("thought", thought))` in `from_dict()`.

- [ ] **Step 4: Run to verify it passes** — `godot --headless --path tingen -s tests/run_tests.gd` → PASS incl. `[agent thought]`.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/Agent.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(agent): add thought field + describe_thought() for the character card

thought holds an explicit read-out (sidecar/critic) when present, else
describe_thought() synthesizes one from the agent's current action. Distinct
from intent (the long-horizon goal). Round-trips through save.
EOF
```

---

## Task B2: ActionCommit stores the action's thought

**Files:**
- Modify: `tingen/src/ActionCommit.gd`
- Test: `tingen/tests/run_tests.gd` (add `_test_commit_sets_thought`, register after `_test_action_commit`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_commit_sets_thought() -> void:
	print("[commit thought]")
	var a := Agent.new("voss")
	ActionCommit.commit({"actor": "voss", "verb": "idle", "args": {}, "thought": "All proceeds as foreseen."}, a)
	_ok(a.describe_thought() == "All proceeds as foreseen.", "commit stores the action's thought")
	ActionCommit.commit({"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, a)
	_ok(a.thought == "", "an action without a thought clears the stored one")
	_ok(a.describe_thought().length() > 0, "describe_thought() falls back to synthesis")
```

- [ ] **Step 2: Run to verify it fails** — `describe_thought()` returns the synthesized line, not the stored thought. FAIL.

- [ ] **Step 3: Implement**

In `tingen/src/ActionCommit.gd`, in `commit()`, right after `agent.current_action = action.duplicate(true)`:

```gdscript
	agent.thought = String(action.get("thought", ""))
```

- [ ] **Step 4: Run to verify it passes** — PASS incl. `[commit thought]`.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/ActionCommit.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(commit): store the committed action's thought on its agent

ActionCommit now copies action.thought onto agent.thought (clearing it when
absent) so the character card shows the latest read-out, sidecar-provided or
synthesized.
EOF
```

---

## Task B3: WorldState.inspect_requested + NPC click

**Files:**
- Modify: `tingen/src/WorldState.gd` (add signal)
- Modify: `tingen/src/NPC.gd` (emit on TalkArea click)
- Test: `tingen/tests/run_tests.gd` (add `_test_inspect_signal`, register after `_test_npc_binds_to_agent`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_inspect_signal() -> void:
	print("[inspect signal]")
	var WS: Object = root.get_node("/root/WorldState")
	var got: Array = []
	var cb := func(id: String): got.append(id)
	WS.inspect_requested.connect(cb)
	WS.inspect_requested.emit("clerk_voss")
	_ok(got == ["clerk_voss"], "inspect_requested carries the agent id")
	WS.inspect_requested.disconnect(cb)
```

- [ ] **Step 2: Run to verify it fails** — signal `inspect_requested` does not exist. FAIL.

- [ ] **Step 3: Implement**

In `tingen/src/WorldState.gd`, add next to the other signals:

```gdscript
signal inspect_requested(agent_id: String)
```

In `tingen/src/NPC.gd`, connect the click in `_ready()` (after the existing `area.body_exited.connect(...)`):

```gdscript
	area.input_pickable = true
	area.input_event.connect(_on_talk_area_input)
```

Add the handler:

```gdscript
func _on_talk_area_input(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		if Agents.get_agent(npc_id) != null:
			WorldState.inspect_requested.emit(npc_id)
```

- [ ] **Step 4: Run to verify it passes** — PASS incl. `[inspect signal]`.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/WorldState.gd tingen/src/NPC.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(npc): emit WorldState.inspect_requested when a bound NPC is clicked

Left-clicking an NPC whose id maps to a registry agent fires the new
inspect_requested(agent_id) signal on the WorldState UI bus; the character card
listens for it.
EOF
```

---

## Task B4: CharacterCard panel

**Files:**
- Create: `tingen/src/CharacterCard.gd`
- Create: `tingen/ui/CharacterCard.tscn`
- Modify: `tingen/ui/HUD.tscn` (instance the card)
- Test: `tingen/tests/run_tests.gd` (add `_test_character_card_opens`, register after `_test_inspect_signal`)

- [ ] **Step 1: Write the failing test**

```gdscript
func _test_character_card_opens() -> void:
	print("[character card]")
	var Ag: Object = root.get_node("/root/Agents"); Ag.rebuild()
	var WS: Object = root.get_node("/root/WorldState")
	var id: String = Ag.all()[0].id
	var card = preload("res://ui/CharacterCard.tscn").instantiate()
	root.add_child(card)
	await process_frame
	_ok(not card.visible, "card hidden by default")
	WS.inspect_requested.emit(id)
	await process_frame
	_ok(card.visible, "card opens on inspect_requested")
	_ok(card.shows_agent(id), "card is showing the inspected agent")
	card.queue_free()
	await process_frame
```

- [ ] **Step 2: Run to verify it fails** — scene does not exist. FAIL.

- [ ] **Step 3: Create the CharacterCard script**

Create `tingen/src/CharacterCard.gd`:

```gdscript
extends Panel
## Inspect card for one Agent (GDD §15). Opened by clicking an NPC
## (WorldState.inspect_requested). Shows the agent's live thought, current goal (its
## long-horizon intent) and recent actions, refreshing while open as beats advance.

@onready var _name: Label = $Margin/Body/Name
@onready var _sub: Label = $Margin/Body/Sub
@onready var _thought: Label = $Margin/Body/Thought
@onready var _goal: Label = $Margin/Body/Goal
@onready var _actions: VBoxContainer = $Margin/Body/Actions

var _agent_id: String = ""

func _ready() -> void:
	visible = false
	WorldState.inspect_requested.connect(_open)
	EventBus.event_logged.connect(func(_e): if visible: _refresh())

func shows_agent(id: String) -> bool:
	return visible and _agent_id == id

func _open(agent_id: String) -> void:
	_agent_id = agent_id
	visible = true
	_refresh()

func close() -> void:
	visible = false

func _refresh() -> void:
	var a = Agents.get_agent(_agent_id)
	if a == null:
		visible = false
		return
	_name.text = a.display_name
	_sub.text = "%s · %s" % [String(a.faction).capitalize(), String(a.role).capitalize()]
	_thought.text = "“%s”" % a.describe_thought()
	_goal.text = a.intent
	for c in _actions.get_children():
		c.queue_free()
	var recent: Array = a.short_memory.slice(maxi(0, a.short_memory.size() - 5))
	if recent.is_empty():
		_add_action("(nothing yet)")
	else:
		for entry in recent:
			_add_action("• " + String(entry))

func _add_action(text: String) -> void:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", Color(0.78, 0.78, 0.82))
	_actions.add_child(l)

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		close()
		get_viewport().set_input_as_handled()
```

- [ ] **Step 4: Create the CharacterCard scene**

Create `tingen/ui/CharacterCard.tscn`:

```
[gd_scene load_steps=2 format=3 uid="uid://b1tngncard0001"]

[ext_resource type="Script" path="res://src/CharacterCard.gd" id="1"]

[node name="CharacterCard" type="Panel"]
anchor_top = 0.5
anchor_bottom = 0.5
offset_left = 16.0
offset_top = -180.0
offset_right = 356.0
offset_bottom = 200.0
grow_vertical = 2
script = ExtResource("1")

[node name="Margin" type="MarginContainer" parent="."]
anchor_right = 1.0
anchor_bottom = 1.0
theme_override_constants/margin_left = 16
theme_override_constants/margin_top = 14
theme_override_constants/margin_right = 16
theme_override_constants/margin_bottom = 14

[node name="Body" type="VBoxContainer" parent="Margin"]
theme_override_constants/separation = 8

[node name="Name" type="Label" parent="Margin/Body"]
text = "Name"
theme_override_font_sizes/font_size = 20

[node name="Sub" type="Label" parent="Margin/Body"]
text = "Faction · Role"
theme_override_colors/font_color = Color(0.7, 0.7, 0.78, 1)

[node name="Sep1" type="HSeparator" parent="Margin/Body"]

[node name="ThoughtLabel" type="Label" parent="Margin/Body"]
text = "Thinking"
theme_override_colors/font_color = Color(0.6, 0.78, 0.85, 1)

[node name="Thought" type="Label" parent="Margin/Body"]
text = ""
autowrap_mode = 2

[node name="GoalLabel" type="Label" parent="Margin/Body"]
text = "Current goal"
theme_override_colors/font_color = Color(0.85, 0.8, 0.6, 1)

[node name="Goal" type="Label" parent="Margin/Body"]
text = ""
autowrap_mode = 2

[node name="ActionsLabel" type="Label" parent="Margin/Body"]
text = "Recent actions"
theme_override_colors/font_color = Color(0.7, 0.7, 0.78, 1)

[node name="Actions" type="VBoxContainer" parent="Margin/Body"]
theme_override_constants/separation = 2

[node name="Hint" type="Label" parent="Margin/Body"]
text = "Esc to close"
theme_override_colors/font_color = Color(0.55, 0.55, 0.6, 1)
horizontal_alignment = 1
```

Note: the script's `@onready` paths address `Name`, `Sub`, `Thought`, `Goal`, `Actions` directly under `Margin/Body` — the extra label nodes (`ThoughtLabel`, `GoalLabel`, `ActionsLabel`, `Hint`, `Sep1`) are static captions and are not referenced by the script.

- [ ] **Step 5: Instance the card in the HUD**

Edit `tingen/ui/HUD.tscn`: bump `load_steps` by 1, add the ext_resource, and add the instance child. Add to the `[ext_resource]` block:

```
[ext_resource type="PackedScene" path="res://ui/CharacterCard.tscn" id="6"]
```

Add at the end of the file (sibling of the other HUD children):

```
[node name="CharacterCard" parent="." instance=ExtResource("6")]
visible = false
```

- [ ] **Step 6: Run to verify it passes** — `godot --headless --path tingen -s tests/run_tests.gd` → PASS incl. `[character card]`.

- [ ] **Step 7: Smoke-run** — `godot --headless --path tingen --quit-after 60` boots with no script errors.

- [ ] **Step 8: Commit**

```bash
git add tingen/src/CharacterCard.gd tingen/ui/CharacterCard.tscn tingen/ui/HUD.tscn tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(ui): character card — click an NPC to read its thought, goal, recent actions

CharacterCard opens on WorldState.inspect_requested, shows the agent's live
thought (describe_thought), current goal (intent) and last actions
(short_memory), and refreshes on each EventBus event while open. Instanced in
the HUD.
EOF
```

---

## Done when

- `Agent.thought` + `describe_thought()` exist and round-trip (`_test_agent_thought`); `ActionCommit` stores the action's thought (`_test_commit_sets_thought`).
- Clicking a bound NPC emits `WorldState.inspect_requested` (`_test_inspect_signal`) and opens the `CharacterCard` showing that agent (`_test_character_card_opens`).
- Full suite green; project boots with no script errors.
