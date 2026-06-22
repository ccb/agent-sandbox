# Plan A — Live agent-driven scene + ticking countdown

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the agent-sim brain visibly drive the on-screen cast in real time — one rendered NPC per registry `Agent`, each following its beat-driven position — feed the real player position into the runtime, and turn the summoning countdown into a live doomsday clock that fires a manifestation climax at zero.

**Architecture:** The headless brain (`AgentRuntime`/`Agents`/`SummoningPlan`) already runs on `Clock.beat_ticked`. Today the rendered `NPC.gd` nodes ignore it and re-read `NpcDB` schedules themselves, and `AgentRuntime.player_position` is a hardcoded stand-in. This plan (1) adds an agent-bound mode to `NPC.gd` so a node follows `Agents.get_agent(npc_id).position`, (2) adds a data-driven `LiveDistrict` scene that spawns one NPC per agent and pushes the player's position into `AgentRuntime` each frame, and (3) makes `SummoningPlan` decrement its countdown on each beat and emit a `summoning_climax(strength)` signal the scene turns into a `CombatEncounter`.

**Tech Stack:** Godot 4.6, GDScript; autoload singletons; headless `SceneTree` test runner (`tingen/tests/run_tests.gd`).

**Key facts the implementer must know:**
- `SummoningPlan.gd` is an autoload **Node** script (NOT `class_name`), so it may reference other autoloads (`Clock`, `EventBus`) by bare name in `_ready`/methods. `Agent.gd`, `Critic.gd`, `ActionCommit.gd`, `Perception.gd` are `class_name` scripts and must use the `_al()` `/root` lookup — but you are not editing those here.
- `NPC.gd` (`res://src/NPC.gd`) is a plain scene script (`extends CharacterBody2D`), only ever instantiated at runtime, so bare autoload references (`Agents`, `Clock`, `NpcDB`, `DialogueManager`) are fine and already used.
- `CombatEncounter` is a `class_name` (RefCounted); `CombatEncounter.new(strength)` works in a scene script. Its `auto_resolve()` returns `{win, rounds, player_hp_left}`.
- `Agents.all()` returns the live `Agent` objects; each `Agent` has `.id` and `.position` (a `Vector2` the beat loop moves).
- The test runner is `extends SceneTree`; it can `instantiate()` a scene, `root.add_child(it)`, `await process_frame`, assert, then `queue_free()`. `_process` runs under it; do NOT rely on `_physics_process`.

---

## Task A1: SummoningPlan ticks the countdown and fires the climax

**Files:**
- Modify: `tingen/src/SummoningPlan.gd`
- Test: `tingen/tests/run_tests.gd` (add `_test_summoning_countdown_and_climax`, register it)

- [ ] **Step 1: Write the failing test**

Add to `tingen/tests/run_tests.gd` and register it in `_init()` after `_test_summoning_plan()`:

```gdscript
func _test_summoning_countdown_and_climax() -> void:
	print("[summoning countdown]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	SP.reset()
	SP.countdown_beats = 3
	var fired: Array = []
	var cb := func(strength: float): fired.append(strength)
	SP.summoning_climax.connect(cb)
	EB.clear()
	SP.tick_countdown()
	_ok(SP.countdown_beats == 2, "tick decrements 3 -> 2")
	_ok(fired.is_empty(), "no climax before zero")
	SP.tick_countdown()
	SP.tick_countdown()
	_ok(SP.countdown_beats == 0, "reaches zero")
	_ok(fired.size() == 1, "climax fires exactly once")
	_ok(is_equal_approx(fired[0], SP.manifestation_strength()), "climax strength == manifestation_strength()")
	_ok(SP.climax_fired, "climax_fired latched true")
	var saw := false
	for e in EB.events("summoning_climax"):
		saw = true
	_ok(saw, "summoning_climax event logged")
	SP.tick_countdown()
	_ok(fired.size() == 1, "does not re-fire after climax")
	SP.summoning_climax.disconnect(cb)
	SP.reset()
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: FAIL — `summoning_climax` signal / `tick_countdown` / `climax_fired` do not exist yet (parse error or failing asserts).

- [ ] **Step 3: Implement the countdown + climax on SummoningPlan**

In `tingen/src/SummoningPlan.gd`, add the two signals and the `climax_fired` flag near the top (after the doc comment / consts, before `var countdown_beats`):

```gdscript
signal countdown_changed(beats_left: int)
signal summoning_climax(strength: float)

var climax_fired: bool = false
```

Add a `_ready` that subscribes to the clock (place it right after the `var _initial_total` line):

```gdscript
func _ready() -> void:
	Clock.beat_ticked.connect(_on_beat)

func _on_beat(_beat_index: int, _day: int) -> void:
	tick_countdown()

## Advance the doomsday clock by one beat. At zero, fire the climax exactly once.
func tick_countdown() -> void:
	if climax_fired:
		return
	if countdown_beats > 0:
		countdown_beats -= 1
		countdown_changed.emit(countdown_beats)
	if countdown_beats <= 0:
		climax_fired = true
		var strength := manifestation_strength()
		summoning_climax.emit(strength)
		EventBus.emit_event("summoning_climax", {"strength": strength})
```

Update `reset()` to clear the latch (add `climax_fired = false` as its first line):

```gdscript
func reset() -> void:
	climax_fired = false
	countdown_beats = 40
	impede_score = 0.0
	ingredients = {"ritual_salt": 3, "consecrated_chalk": 2, "candle": 3}
	_initial_total = _total_ingredients()
```

Persist the latch in `to_dict()` (add `"climax_fired": climax_fired,`) and restore it in `from_dict()` (add `climax_fired = bool(d.get("climax_fired", false))`).

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: PASS — all prior tests still green plus the new `[summoning countdown]` block. Confirm the summary line ends `=== N passed, 0 failed, K skipped ===`.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/SummoningPlan.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(summoning): tick countdown on each beat, fire manifestation climax at zero

SummoningPlan now decrements countdown_beats on Clock.beat_ticked and emits
summoning_climax(strength) + a summoning_climax EventBus event once at zero.
Lifts the passive-countdown slice boundary from the previous build.
EOF
```

---

## Task A2: NPC node binds to its Agent and follows the beat-driven position

**Files:**
- Modify: `tingen/src/NPC.gd`
- Test: `tingen/tests/run_tests.gd` (add `_test_npc_binds_to_agent`, register it)

- [ ] **Step 1: Write the failing test**

The follow behaviour is steered in `_physics_process`, which the headless runner does not tick. Make the *target selection* a pure method so it is unit-testable. Add this test and register it after `_test_summoning_countdown_and_climax`:

```gdscript
func _test_npc_binds_to_agent() -> void:
	print("[npc bind]")
	var Ag: Object = root.get_node("/root/Agents")
	Ag.rebuild()
	var agent = Ag.all()[0]
	agent.position = Vector2(777, 333)
	var npc = preload("res://scenes/NPC.tscn").instantiate()
	npc.npc_id = agent.id
	root.add_child(npc)
	await process_frame
	_ok(npc.is_bound(), "node bound to a registry agent")
	_ok(npc.steer_goal() == Vector2(777, 333), "bound node steers toward its agent's position")
	# Unknown id falls back to schedule mode (not bound).
	var loose = preload("res://scenes/NPC.tscn").instantiate()
	loose.npc_id = "no_such_agent"
	root.add_child(loose)
	await process_frame
	_ok(not loose.is_bound(), "unknown id is not bound (schedule fallback)")
	npc.queue_free()
	loose.queue_free()
	await process_frame
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: FAIL — `is_bound()` / `steer_goal()` do not exist.

- [ ] **Step 3: Implement agent binding on NPC.gd**

In `tingen/src/NPC.gd`, add a bound-agent field next to the other `var`s:

```gdscript
var _agent = null   # bound Agent (from the registry) or null = schedule fallback
```

At the end of `_ready()` (after the `area.body_exited.connect(...)` line), bind to the registry agent if one exists:

```gdscript
	_agent = Agents.get_agent(npc_id)
```

Add the two query methods (anywhere after `_ready`):

```gdscript
## True when this node is the rendered body of a live registry Agent.
func is_bound() -> bool:
	return _agent != null

## Where the node should walk this frame: its Agent's beat-driven position when bound,
## otherwise its scheduled waypoint.
func steer_goal() -> Vector2:
	return _agent.position if _agent != null else _target
```

Rewrite `_physics_process` to steer toward `steer_goal()`:

```gdscript
func _physics_process(_delta: float) -> void:
	if DialogueManager.active:
		velocity = Vector2.ZERO
		return
	var to_target := steer_goal() - global_position
	if to_target.length() <= arrive_radius:
		velocity = Vector2.ZERO
	else:
		velocity = to_target.normalized() * move_speed
		move_and_slide()
```

Leave `_retarget` and the `Clock.phase_changed` connection in place — they keep schedule mode working for any scene (e.g. `City.tscn`) that places an NPC whose id is not in the registry.

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: PASS, including `[npc bind]`.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/NPC.gd tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(npc): bind rendered NPC to its registry Agent and follow its beat position

A node whose npc_id matches a registry Agent now steers toward Agent.position
(moved by the beat loop) instead of re-reading the schedule itself; unknown ids
keep the schedule fallback so City.tscn still works.
EOF
```

---

## Task A3: LiveDistrict scene — spawn agents, feed player position, present the climax

**Files:**
- Create: `tingen/src/LiveDistrict.gd`
- Create: `tingen/scenes/LiveDistrict.tscn`
- Modify: `tingen/scenes/Main.tscn` (World hosts LiveDistrict instead of IntroRoom)
- Test: `tingen/tests/run_tests.gd` (add `_test_live_district_wiring`, register it)

- [ ] **Step 1: Write the failing test**

Add and register after `_test_npc_binds_to_agent`:

```gdscript
func _test_live_district_wiring() -> void:
	print("[live district]")
	var Ag: Object = root.get_node("/root/Agents")
	var AR: Object = root.get_node("/root/AgentRuntime")
	Ag.rebuild()
	var scene = preload("res://scenes/LiveDistrict.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var npc_count := 0
	for c in scene.get_children():
		if c.is_in_group("npc"):
			npc_count += 1
	_ok(npc_count == Ag.all().size(), "spawns one NPC per registry agent")
	_ok(AR.player_position == scene.player_start, "runtime player_position fed from the live player")
	scene.queue_free()
	await process_frame
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: FAIL — `res://scenes/LiveDistrict.tscn` does not exist.

- [ ] **Step 3: Create the LiveDistrict script**

Create `tingen/src/LiveDistrict.gd`:

```gdscript
extends Node2D
## The live district. The agent-sim brain visibly drives the cast here: one rendered NPC
## per registry Agent (data-driven, not hand-placed), each bound by id so it follows its
## Agent's beat-driven position. Pushes the real player's position into AgentRuntime every
## frame so "active agents near the player" tracks what is on screen, and presents the
## summoning climax when SummoningPlan's countdown hits zero.

const NPC_SCENE: PackedScene = preload("res://scenes/NPC.tscn")
const PLAYER_SCENE: PackedScene = preload("res://scenes/Player.tscn")

@export var player_start: Vector2 = Vector2(440, 300)

var _player: Node2D = null

func _ready() -> void:
	_spawn_player()
	_spawn_agents()
	if not SummoningPlan.summoning_climax.is_connected(_on_climax):
		SummoningPlan.summoning_climax.connect(_on_climax)

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

func _process(_delta: float) -> void:
	if is_instance_valid(_player):
		AgentRuntime.player_position = _player.global_position

## Headless-real climax: resolve the fight deterministically and surface the result. The
## animated, interactive fight is a later polish; the resolution math is real now.
func _on_climax(strength: float) -> void:
	var fight := CombatEncounter.new(strength)
	var result: Dictionary = fight.auto_resolve()
	var verdict := "You hold the line." if result["win"] else "The descent takes you."
	WorldState.thought_requested.emit("The summoning breaks over Tingen. %s (%d HP left, %d rounds)" % [
		verdict, int(result["player_hp_left"]), int(result["rounds"])])
	EventBus.emit_event("combat_resolved", result)
```

- [ ] **Step 4: Create the LiveDistrict scene**

Create `tingen/scenes/LiveDistrict.tscn` (mirrors `City.tscn`'s ground/tint but spawns the cast from the registry; no hand-placed NPCs):

```
[gd_scene load_steps=3 format=3 uid="uid://b1tngnlive0001"]

[ext_resource type="Script" path="res://src/LiveDistrict.gd" id="1"]
[ext_resource type="Script" path="res://src/DayNightTint.gd" id="2"]

[node name="LiveDistrict" type="Node2D"]
script = ExtResource("1")

[node name="DayNight" type="CanvasModulate" parent="."]
script = ExtResource("2")

[node name="Ground" type="Polygon2D" parent="."]
color = Color(0.12, 0.13, 0.17, 1)
polygon = PackedVector2Array(-200, -200, 1400, -200, 1400, 1000, -200, 1000)

[node name="Cobbles" type="Polygon2D" parent="."]
color = Color(0.18, 0.18, 0.22, 1)
polygon = PackedVector2Array(120, 120, 1080, 120, 1080, 680, 120, 680)

[node name="Title" type="Label" parent="."]
offset_left = 320.0
offset_top = 150.0
offset_right = 880.0
offset_bottom = 174.0
horizontal_alignment = 1
text = "Tingen - Iron Cross Street  [live district]"
```

- [ ] **Step 5: Point Main.tscn's World at LiveDistrict**

Edit `tingen/scenes/Main.tscn`. Replace the IntroRoom ext_resource + instance with LiveDistrict so the live agent sim is what the player sees on run. The file becomes:

```
[gd_scene load_steps=4 format=3 uid="uid://b1tngnmain0001"]

[ext_resource type="Script" path="res://src/GameController.gd" id="1"]
[ext_resource type="PackedScene" path="res://scenes/LiveDistrict.tscn" id="2"]
[ext_resource type="PackedScene" path="res://ui/HUD.tscn" id="3"]

[node name="Main" type="Node2D"]
script = ExtResource("1")

[node name="World" type="Node2D" parent="."]

[node name="LiveDistrict" parent="World" instance=ExtResource("2")]

[node name="UI" type="CanvasLayer" parent="."]

[node name="HUD" parent="UI" instance=ExtResource("3")]
```

- [ ] **Step 6: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: PASS, including `[live district]`. Summary ends `0 failed`.

- [ ] **Step 7: Smoke-run the project headlessly (no crash on load)**

Run: `godot --headless --path tingen --quit-after 120`
Expected: boots, prints the sidecar/agent logs, advances beats, and quits cleanly with no script errors. (A few `Camera2D`/audio warnings under `--headless` are acceptable; script *errors* are not.)

- [ ] **Step 8: Commit**

```bash
git add tingen/src/LiveDistrict.gd tingen/scenes/LiveDistrict.tscn tingen/scenes/Main.tscn tingen/tests/run_tests.gd
git commit -F - <<'EOF'
feat(scene): live district drives the cast from the agent registry

LiveDistrict spawns one NPC per registry Agent, feeds the real player position
into AgentRuntime each frame, and resolves the summoning climax via
CombatEncounter when the countdown hits zero. Main.tscn now opens here.
EOF
```

---

## Done when

- `SummoningPlan` decrements on each beat and fires a single `summoning_climax` + EventBus event at zero (covered by `_test_summoning_countdown_and_climax`).
- A rendered NPC bound to a registry agent steers toward that agent's position; unknown ids fall back to schedules (`_test_npc_binds_to_agent`).
- `LiveDistrict` spawns one NPC per agent and feeds `AgentRuntime.player_position` (`_test_live_district_wiring`), and the project boots into it headlessly with no script errors.
- Full suite green (`0 failed`).
