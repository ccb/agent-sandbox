# Tingen Sim Substrate + EventBus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic Godot foundation for the Tingen agent-sim vertical slice — a beat clock, an append-only event log, runtime agents with cheap fallback behavior, the Iron Cross cult cell data, and save/load — all headlessly testable with no LLM.

**Architecture:** Extend the existing autoload + data-driven-JSON pattern. `Clock` gains a *beat* cadence (the deliberation tick). A new `EventBus` autoload is the single append-only source of truth for everything that happens. A new `Agent` class (RefCounted) models a runtime NPC with position + a schedule-driven `tick_fallback` that runs while (later) its LLM deliberates; a new `Agents` autoload registry builds agents from `NpcDB` and ticks their fallback each beat. `npcs.json` is extended with `faction/role/intent` and the Iron Cross cult cell. `SaveManager` persists the new state. Everything stays seeded/deterministic; nondeterminism (the LLM) arrives in a later plan behind the sidecar contract.

**Tech Stack:** Godot 4.6, GDScript, autoload singletons, JSON data files, the existing headless `SceneTree` test runner (`tingen/tests/run_tests.gd`).

---

## Conventions

- **Project root for Godot:** the Godot project lives in `Tingen-Game/tingen/`. All `res://` paths are relative to that. Run all commands from `Tingen-Game/`.
- **Run the test suite:** `godot --headless --path tingen -s tests/run_tests.gd`
  (your Godot binary may be named `godot4` or be an absolute path to the app's binary; substitute as needed). Expected tail on success: `=== N passed, 0 failed ===` and exit code 0.
- **Test pattern:** the runner is a single `SceneTree` script. Each feature gets a `func _test_xxx()` that uses `_ok(cond, label)`, and a call to it added inside `_init()` just above the final `print(...)` line.

## File Structure

- **Create** `tingen/src/EventBus.gd` — append-only world event log (autoload `EventBus`). One job: record + query events.
- **Create** `tingen/src/Agent.gd` — `class_name Agent` (RefCounted). One job: one runtime agent's state + fallback movement + (de)serialization.
- **Create** `tingen/src/AgentRegistry.gd` — autoload `Agents`. One job: own the set of `Agent`s, build them from `NpcDB`, query/tick them.
- **Modify** `tingen/src/Clock.gd` — add a beat cadence (`beat_index`, `minutes_per_beat`, `beat_ticked`).
- **Modify** `tingen/data/npcs.json` — add `faction/role/intent` + the Iron Cross cult cell (`clerk_voss`, `dockhand_pell`; enrich `lamplighter_orin`, `fishwife_dalia`).
- **Modify** `tingen/project.godot` — register the `EventBus` and `Agents` autoloads.
- **Modify** `tingen/src/SaveManager.gd` — persist `EventBus` + `Agents`.
- **Modify** `tingen/tests/run_tests.gd` — add tests for every task.

---

## Task 1: Clock beats (the deliberation cadence)

**Files:**
- Modify: `tingen/src/Clock.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add this function (e.g. after `_test_clock_phases`):

```gdscript
func _test_clock_beats() -> void:
	print("[clock beats]")
	var Clk: Object = root.get_node("/root/Clock")
	Clk.minutes_per_beat = 15
	Clk.beat_index = 0
	Clk._beat_accum_minutes = 0
	var seen := {"n": 0}
	var cb := func(_bi: int, _d: int) -> void: seen["n"] += 1
	Clk.beat_ticked.connect(cb)
	Clk.advance_minutes(15)
	_ok(Clk.beat_index == 1, "15 minutes -> 1 beat")
	_ok(seen["n"] == 1, "beat_ticked emitted once")
	Clk.advance_minutes(30)
	_ok(Clk.beat_index == 3, "45 minutes total -> 3 beats")
	Clk.beat_ticked.disconnect(cb)
```

Register it: in `_init()`, add the call just above the final `print(...)` line:

```gdscript
	_test_clock_beats()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify the new test fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failures like `Invalid set index 'minutes_per_beat'` / `beat_index` not found (the members don't exist yet), suite exits non-zero.

- [ ] **Step 3: Implement beats in Clock.gd**

Add the signal near the other signals in `tingen/src/Clock.gd`:

```gdscript
signal beat_ticked(beat_index: int, day: int)
```

Add these members near `var paused: bool = false`:

```gdscript
var minutes_per_beat: int = 15
var beat_index: int = 0
var _beat_accum_minutes: int = 0
```

In `_advance_one_minute()`, at the very end of the function (after the phase-change block), add:

```gdscript
	_beat_accum_minutes += 1
	if _beat_accum_minutes >= minutes_per_beat:
		_beat_accum_minutes = 0
		beat_index += 1
		beat_ticked.emit(beat_index, day)
```

Extend `to_dict()` to include the beat fields:

```gdscript
func to_dict() -> Dictionary:
	return {
		"day": day,
		"minute_of_day": minute_of_day,
		"beat_index": beat_index,
		"minutes_per_beat": minutes_per_beat,
		"beat_accum_minutes": _beat_accum_minutes,
	}
```

Extend `from_dict()` to restore them (keep the existing `set_time` call):

```gdscript
func from_dict(d: Dictionary) -> void:
	set_time(int(d.get("day", 1)), int(d.get("minute_of_day", 480)))
	beat_index = int(d.get("beat_index", 0))
	minutes_per_beat = int(d.get("minutes_per_beat", 15))
	_beat_accum_minutes = int(d.get("beat_accum_minutes", 0))
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[clock beats]` shows three PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/Clock.gd tingen/tests/run_tests.gd
git commit -m "feat(clock): add beat cadence (beat_ticked) for agent deliberation"
```

---

## Task 2: EventBus autoload (append-only world event log)

**Files:**
- Create: `tingen/src/EventBus.gd`
- Modify: `tingen/project.godot`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_event_bus() -> void:
	print("[event bus]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var ev: Dictionary = EB.emit_event("test_action", {"actor": "voss"})
	_ok(ev["type"] == "test_action", "event records its type")
	_ok(int(ev["seq"]) == 1, "first event seq is 1")
	_ok(EB.events().size() == 1, "one event logged")
	EB.emit_event("other", {})
	_ok(EB.events("test_action").size() == 1, "filter by type returns only matches")
	_ok(EB.latest(1).size() == 1, "latest(1) returns one event")
```

Register it in `_init()` above the final `print(...)`:

```gdscript
	_test_event_bus()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failure resolving `/root/EventBus` (autoload doesn't exist yet) — `get_node` returns null and the test errors.

- [ ] **Step 3: Create EventBus.gd**

Create `tingen/src/EventBus.gd`:

```gdscript
extends Node
## Append-only world event log (autoload singleton `EventBus`).
##
## Every meaningful thing that happens in the sim — an agent's committed action, a
## player action, a pressure threshold crossing, a beat tick — is appended here as a
## plain Dictionary. This is the single source of truth the World-AI overseer (a later
## plan) reads, and the basis for deterministic replay and tests. Append-only with a
## rolling cap; never mutate past events.

signal event_logged(event: Dictionary)

const MAX_EVENTS: int = 2000

var _events: Array = []
var _seq: int = 0

## Append an event. `type` is a short tag (e.g. "agent_action", "player_sabotage").
## `data` is arbitrary JSON-safe detail. Returns the stored event dictionary.
func emit_event(type: String, data: Dictionary = {}) -> Dictionary:
	_seq += 1
	var ev: Dictionary = {
		"seq": _seq,
		"type": type,
		"data": data.duplicate(true),
		"day": Clock.day,
		"minute": Clock.minute_of_day,
		"beat": Clock.beat_index,
	}
	_events.append(ev)
	if _events.size() > MAX_EVENTS:
		_events = _events.slice(_events.size() - MAX_EVENTS)
	event_logged.emit(ev)
	return ev

## All events, or only those of a given type when `filter_type` is non-empty.
func events(filter_type: String = "") -> Array:
	if filter_type == "":
		return _events.duplicate(true)
	return _events.filter(func(e: Dictionary) -> bool: return e["type"] == filter_type)

## The most recent `n` events (oldest-first within the slice).
func latest(n: int = 10) -> Array:
	return _events.slice(maxi(0, _events.size() - n))

func clear() -> void:
	_events.clear()
	_seq = 0

func to_dict() -> Dictionary:
	return {"events": _events.duplicate(true), "seq": _seq}

func from_dict(d: Dictionary) -> void:
	_events = (d.get("events", []) as Array).duplicate(true)
	_seq = int(d.get("seq", 0))
```

Register the autoload in `tingen/project.godot` — add the `EventBus` line right after the `WorldManager` line in the `[autoload]` block:

```
WorldManager="*res://src/WorldManager.gd"
EventBus="*res://src/EventBus.gd"
EventManager="*res://src/EventManager.gd"
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[event bus]` shows five PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/EventBus.gd tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(eventbus): append-only world event log autoload"
```

---

## Task 3: Agent class (runtime agent + fallback movement)

**Files:**
- Create: `tingen/src/Agent.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_agent_fallback() -> void:
	print("[agent fallback]")
	var ND: Object = root.get_node("/root/NpcDB")
	var target: Vector2 = ND.waypoint_for("lamplighter_orin", "morning")
	var a: Agent = Agent.new("lamplighter_orin")
	a.position = Vector2.ZERO
	var before: float = a.distance_to(target)
	a.tick_fallback("morning", 100.0)
	var after: float = a.distance_to(target)
	_ok(after < before, "fallback step moves agent toward its waypoint")
	for _i in range(100):
		a.tick_fallback("morning", 100.0)
	_ok(a.position == target, "fallback converges onto the waypoint")
	a.remember("saw the player near the warehouse")
	_ok(a.short_memory.size() == 1, "remember() appends to short memory")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_agent_fallback()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: parse/identifier error — `Agent` class is not defined yet.

- [ ] **Step 3: Create Agent.gd**

Create `tingen/src/Agent.gd`:

```gdscript
class_name Agent
extends RefCounted
## One runtime NPC agent. Holds identity + intent + lightweight cognition state
## (short memory, current plan, current action) and a physical position. While the
## agent is not actively deliberating (the LLM arrives in a later plan), `tick_fallback`
## drives it toward its schedule waypoint so the world keeps moving and nothing stalls.

var id: String = ""
var display_name: String = ""
var faction: String = "civilian"
var role: String = ""
var intent: String = ""
var position: Vector2 = Vector2.ZERO
var current_action: Dictionary = {}
var short_memory: Array = []
var plan: Array = []

func _init(agent_id: String = "") -> void:
	id = agent_id

## Move one step (up to `speed` pixels) toward the schedule waypoint for `phase`.
## Snaps to the waypoint when within one step. No-op if there is no waypoint and the
## agent is still at the origin.
func tick_fallback(phase: String, speed: float) -> void:
	var target: Vector2 = NpcDB.waypoint_for(id, phase)
	if target == Vector2.ZERO and position == Vector2.ZERO:
		return
	var to_target: Vector2 = target - position
	var dist: float = to_target.length()
	if dist <= speed or dist == 0.0:
		position = target
	else:
		position += to_target / dist * speed

func distance_to(p: Vector2) -> float:
	return position.distance_to(p)

## Append a short memory line, keeping only the most recent `cap` entries.
func remember(entry: String, cap: int = 20) -> void:
	short_memory.append(entry)
	if short_memory.size() > cap:
		short_memory = short_memory.slice(short_memory.size() - cap)

func to_dict() -> Dictionary:
	return {
		"id": id,
		"display_name": display_name,
		"faction": faction,
		"role": role,
		"intent": intent,
		"position": [position.x, position.y],
		"current_action": current_action.duplicate(true),
		"short_memory": short_memory.duplicate(),
		"plan": plan.duplicate(true),
	}

func from_dict(d: Dictionary) -> void:
	id = String(d.get("id", id))
	display_name = String(d.get("display_name", display_name))
	faction = String(d.get("faction", faction))
	role = String(d.get("role", role))
	intent = String(d.get("intent", intent))
	var p: Variant = d.get("position", [0, 0])
	if typeof(p) == TYPE_ARRAY and (p as Array).size() >= 2:
		position = Vector2(float(p[0]), float(p[1]))
	current_action = (d.get("current_action", {}) as Dictionary).duplicate(true)
	short_memory = (d.get("short_memory", []) as Array).duplicate()
	plan = (d.get("plan", []) as Array).duplicate(true)
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[agent fallback]` shows three PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/Agent.gd tingen/tests/run_tests.gd
git commit -m "feat(agent): runtime Agent class with schedule fallback movement"
```

---

## Task 4: AgentRegistry autoload (`Agents`)

**Files:**
- Create: `tingen/src/AgentRegistry.gd`
- Modify: `tingen/project.godot`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_agent_registry() -> void:
	print("[agent registry]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	_ok(AG.get_agent("lamplighter_orin") != null, "registry builds a known agent")
	_ok(AG.all().size() >= 2, "registry holds at least the seeded npcs")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	var near: Array = AG.active(orin.position, 1.0)
	_ok(near.has(orin), "active() finds an agent at its own position")
	var far: Array = AG.active(orin.position + Vector2(99999, 0), 1.0)
	_ok(not far.has(orin), "active() excludes agents outside the radius")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_agent_registry()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failure resolving `/root/Agents` (autoload missing).

- [ ] **Step 3: Create AgentRegistry.gd**

Create `tingen/src/AgentRegistry.gd`:

```gdscript
extends Node
## Runtime agent registry (autoload singleton `Agents`). Builds an `Agent` for every
## entry in `NpcDB.defs`, reading optional `faction`/`role`/`intent` fields and seeding
## each agent's position from its current-phase waypoint. Provides spatial queries and a
## per-beat fallback tick. The LLM deliberation loop (a later plan) will sit on top of
## this; for now agents only run their schedule fallback.

var fallback_speed: float = 48.0

var _agents: Dictionary = {}  # id -> Agent

func _ready() -> void:
	rebuild()

## (Re)build all agents from NpcDB definitions. Safe to call again (e.g. in tests).
func rebuild() -> void:
	_agents.clear()
	for id in NpcDB.defs.keys():
		var def: Dictionary = NpcDB.defs[id]
		var a: Agent = Agent.new(id)
		a.display_name = String(def.get("name", id))
		a.faction = String(def.get("faction", "civilian"))
		a.role = String(def.get("role", ""))
		a.intent = String(def.get("intent", ""))
		a.position = NpcDB.waypoint_for(id, Clock.phase)
		_agents[id] = a

func get_agent(id: String) -> Agent:
	return _agents.get(id, null)

func all() -> Array:
	return _agents.values()

## Agents within `radius` of `center` (the "active" set that will deliberate via LLM).
func active(center: Vector2, radius: float) -> Array:
	var out: Array = []
	for a in _agents.values():
		if a.position.distance_to(center) <= radius:
			out.append(a)
	return out

## Advance every agent's fallback movement by one beat.
func tick_beat() -> void:
	for a in _agents.values():
		a.tick_fallback(Clock.phase, fallback_speed)

func to_dict() -> Dictionary:
	var d: Dictionary = {}
	for id in _agents.keys():
		d[id] = (_agents[id] as Agent).to_dict()
	return {"agents": d}

func from_dict(data: Dictionary) -> void:
	var d: Dictionary = data.get("agents", {})
	for id in d.keys():
		var a: Agent = _agents.get(id, null)
		if a == null:
			a = Agent.new(String(id))
		a.from_dict(d[id])
		_agents[id] = a
```

Register the autoload in `tingen/project.godot` — add the `Agents` line right after the `EventBus` line:

```
EventBus="*res://src/EventBus.gd"
Agents="*res://src/AgentRegistry.gd"
EventManager="*res://src/EventManager.gd"
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[agent registry]` shows four PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/AgentRegistry.gd tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(agents): AgentRegistry autoload with spatial queries + beat tick"
```

---

## Task 5: Seed the Iron Cross cult cell in npcs.json

**Files:**
- Modify: `tingen/data/npcs.json`
- Test: `tingen/tests/run_tests.gd`

Iron Cross Street occupies the polygon `[320,200, 560,200, 560,380, 320,380]` (from `districts.json`), so all positions below sit inside it.

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_cult_cell_seeded() -> void:
	print("[cult cell]")
	var ND: Object = root.get_node("/root/NpcDB")
	_ok(ND.get_def("clerk_voss").get("faction", "") == "cult", "voss is faction cult")
	_ok(ND.get_def("clerk_voss").get("role", "") == "leader", "voss is the leader")
	_ok(ND.get_def("dockhand_pell").get("role", "") == "victim", "pell is the victim")
	_ok(String(ND.get_def("lamplighter_orin").get("intent", "")) != "", "orin has an intent")
	_ok(String(ND.get_def("fishwife_dalia").get("role", "")) == "logistics", "dalia is logistics")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_cult_cell_seeded()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[cult cell]` FAILs (the fields/agents don't exist yet).

- [ ] **Step 3: Rewrite npcs.json with the cell**

Replace the entire contents of `tingen/data/npcs.json` with:

```json
{
	"clerk_voss": {
		"name": "Clerk Voss",
		"dialogue_id": "",
		"faction": "cult",
		"role": "leader",
		"intent": "Complete the warehouse summoning to escape mortality. Plan the ritual steps, direct the acolytes, recruit quietly, and keep the cell hidden from the Nighthawks and the player.",
		"tint": [0.6, 0.5, 0.7],
		"schedule": {
			"morning": [360, 240],
			"afternoon": [480, 300],
			"dusk": [440, 340],
			"night": [400, 360],
			"late-night": [420, 360]
		}
	},
	"fishwife_dalia": {
		"name": "Dalia the Fishwife",
		"dialogue_id": "",
		"faction": "cult",
		"role": "logistics",
		"intent": "Move ritual ingredients through the harbor to the warehouse, and run decoy errands that mislead anyone investigating the cell.",
		"tint": [0.5, 0.7, 0.65],
		"schedule": {
			"morning": [520, 220],
			"afternoon": [500, 260],
			"dusk": [460, 320],
			"night": [400, 360]
		}
	},
	"lamplighter_orin": {
		"name": "Orin the Lamplighter",
		"dialogue_id": "",
		"faction": "cult",
		"role": "scout_waverer",
		"intent": "Scout the district while lighting the lamps, reporting movements to Voss. Increasingly doubts what the cell is about to do, and can be turned by someone who reaches him.",
		"tint": [0.85, 0.7, 0.4],
		"schedule": {
			"early-morning": [340, 210],
			"morning": [400, 240],
			"afternoon": [540, 300],
			"dusk": [520, 360],
			"night": [360, 360],
			"late-night": [330, 360]
		}
	},
	"dockhand_pell": {
		"name": "Dockhand Pell",
		"dialogue_id": "",
		"faction": "civilian",
		"role": "victim",
		"intent": "Get through the workday and back home. Unaware that the cell has marked him as the intended sacrifice for the summoning.",
		"tint": [0.7, 0.65, 0.55],
		"schedule": {
			"morning": [340, 220],
			"afternoon": [520, 360],
			"dusk": [500, 380],
			"night": [360, 300]
		}
	}
}
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[cult cell]` shows five PASS lines; suite exits 0. (The earlier `[agent registry]` test now reports `all().size() >= 2` against four agents — still passes.)

- [ ] **Step 5: Commit**

```bash
git add tingen/data/npcs.json tingen/tests/run_tests.gd
git commit -m "feat(data): seed Iron Cross cult cell with faction/role/intent"
```

---

## Task 6: Persist EventBus + Agents through SaveManager

**Files:**
- Modify: `tingen/src/SaveManager.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_substrate_save_load() -> void:
	print("[substrate save/load]")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")
	var SM: Object = root.get_node("/root/SaveManager")
	AG.rebuild()
	EB.clear()
	EB.emit_event("seed_event", {"x": 1})
	AG.get_agent("clerk_voss").position = Vector2(123, 456)
	var tmp := "user://test_substrate.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	EB.clear()
	AG.get_agent("clerk_voss").position = Vector2.ZERO
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(EB.events("seed_event").size() == 1, "event log restored after load")
	_ok(AG.get_agent("clerk_voss").position == Vector2(123, 456), "agent position restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_substrate_save_load()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[substrate save/load]` FAILs at "event log restored" / "agent position restored" — the save payload doesn't include these systems yet, so load leaves them cleared/zeroed.

- [ ] **Step 3: Add the keys to SaveManager**

In `tingen/src/SaveManager.gd`, in `save_game()`, add two entries to the `data` dictionary (after the `"clues": ClueDB.to_dict(),` line):

```gdscript
		"clues": ClueDB.to_dict(),
		"event_bus": EventBus.to_dict(),
		"agents": Agents.to_dict(),
		"scene_path": gc.current_scene_path if gc else "",
```

In `load_game()`, add two restore calls in the "Restore data-only subsystems first" block (after the `WorldState.from_dict(...)` line):

```gdscript
	WorldState.from_dict(data.get("world_state", {}))
	EventBus.from_dict(data.get("event_bus", {}))
	Agents.from_dict(data.get("agents", {}))
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[substrate save/load]` shows four PASS lines; the full suite ends `=== N passed, 0 failed ===`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/SaveManager.gd tingen/tests/run_tests.gd
git commit -m "feat(save): persist EventBus + Agents in the save payload"
```

---

## Done criteria for this plan

- The full headless suite passes (`=== N passed, 0 failed ===`, exit 0) and includes: clock beats, event bus, agent fallback, agent registry, cult cell, substrate save/load.
- `EventBus` and `Agents` are registered autoloads; `Clock` emits `beat_ticked`.
- `npcs.json` defines the four-agent Iron Cross cult cell with `faction/role/intent`.
- Save/load round-trips the event log and agent state.

## What this plan deliberately does NOT do (next plans)

- No LLM, no Python sidecar, no real deliberation — agents only run schedule fallback. (Plan 3: sidecar contract + mock; Plan 4: agent runtime.)
- No overseer/critic. (Plan 5.)
- No player verbs, occult perception, sabotage, social influence, or combat. (Plan 6.)
- No on-screen agent rendering/sprites — this plan is headless/logic only; a scene-integration step comes with the player-verbs/UI plan.
- No inventory (separate, independent plan — `2026-06-08-inventory-system-design.md`).
```
