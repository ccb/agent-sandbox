# Agent Runtime + Beat Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop: on each beat, build a perception snapshot for every active agent, ask the sidecar for a proposed action, validate it against the schema, commit the approved verb to the world deterministically, and log it to the `EventBus`. Agents that aren't active run their schedule fallback so the world never stalls.

**Architecture:** Three units. `Perception` (static) turns one `Agent` + world state into a JSON-safe snapshot dict. `ActionCommit` (static) applies one validated verb to the agent/world and returns a deterministic outcome. `AgentRuntime` (autoload) drives one beat: pick active agents (near the player or flagged), `Perception → SidecarBridge.propose → ActionSchema.validate → ActionCommit.commit → EventBus`, and fallback-tick everyone else. No agent mutates the world except through `ActionCommit`.

**Tech Stack:** Godot 4.6, GDScript, autoloads + `class_name` static libs, headless `SceneTree` test runner.

**Depends on:** Plan 1 (`Clock.beat_ticked`, `Agent`, `Agents` registry, `EventBus`), Plan 3 (`SidecarBridge`, `MockSidecar`, `ActionSchema`).

**Source spec:** `docs/superpowers/specs/2026-06-08-tingen-agent-sim-vertical-slice-design.md` §B, §4.

---

## Conventions

- **Godot project root:** `Tingen-Game/tingen/`. Run from `Tingen-Game/`.
- **Run the suite:** `godot --headless --path tingen -s tests/run_tests.gd`. Success tail: `=== N passed, 0 failed ===`, exit 0.
- **Test pattern:** one `SceneTree` script; each feature gets `func _test_xxx()` using `_ok(cond, label)`, called in `_init()` above the final `print(...)`.

## File Structure

- **Create** `tingen/src/Perception.gd` — `class_name Perception`. One job: build an agent's perception snapshot.
- **Create** `tingen/src/ActionCommit.gd` — `class_name ActionCommit`. One job: deterministically apply one validated verb.
- **Create** `tingen/src/AgentRuntime.gd` — autoload `AgentRuntime`. One job: run a beat end-to-end.
- **Modify** `tingen/project.godot` — register `AgentRuntime` (after `SidecarBridge`).
- **Modify** `tingen/tests/run_tests.gd` — add tests.

---

## Task 1: Perception snapshot builder

**Files:**
- Create: `tingen/src/Perception.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_perception_snapshot() -> void:
	print("[perception]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	EB.clear()
	EB.emit_event("test_seed", {"x": 1})
	var voss: Agent = AG.get_agent("clerk_voss")
	var snap: Dictionary = Perception.build_snapshot(voss, voss.position)
	_ok(snap.get("agent_id", "") == "clerk_voss", "snapshot carries agent_id")
	_ok(snap.has("intent"), "snapshot includes intent")
	_ok(snap.has("position"), "snapshot includes position")
	_ok(snap.has("nearby"), "snapshot includes nearby agents")
	_ok(snap.has("recent_events"), "snapshot includes recent events")
	_ok(snap.has("stage"), "snapshot includes world stage")
	_ok(snap.has("pressures"), "snapshot includes pressures")
	# Another agent placed at voss's position should show up as nearby.
	var pell: Agent = AG.get_agent("dockhand_pell")
	pell.position = voss.position
	var snap2: Dictionary = Perception.build_snapshot(voss, voss.position)
	var nearby_ids: Array = []
	for n in snap2["nearby"]:
		nearby_ids.append(n["id"])
	_ok(nearby_ids.has("dockhand_pell"), "co-located agent appears in nearby")
	_ok(not nearby_ids.has("clerk_voss"), "agent does not list itself as nearby")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_perception_snapshot()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: parse/identifier error — `Perception` not defined.

- [ ] **Step 3: Create Perception.gd**

Create `tingen/src/Perception.gd`:

```gdscript
class_name Perception
extends RefCounted
## Builds the perception snapshot a sidecar needs to choose an action for one agent.
## A snapshot is a flat, JSON-safe Dictionary: who the agent is, what it wants, where it
## stands, who/what is near it, the recent event stream, and the world's coarse state.
## Pure read — never mutates anything.

const NEARBY_RADIUS: float = 160.0
const RECENT_EVENT_COUNT: int = 8

static func build_snapshot(agent: Agent, _player_center: Vector2) -> Dictionary:
	return {
		"agent_id": agent.id,
		"display_name": agent.display_name,
		"faction": agent.faction,
		"role": agent.role,
		"intent": agent.intent,
		"position": [agent.position.x, agent.position.y],
		"short_memory": agent.short_memory.duplicate(),
		"current_action": agent.current_action.duplicate(true),
		"nearby": _nearby(agent),
		"recent_events": _recent_events(),
		"stage": WorldManager.current_stage_id,
		"pressures": {
			"corruption": WorldState.corruption,
			"cult_readiness": WorldState.cult_readiness,
			"panic": WorldState.panic,
			"attention": WorldState.attention,
		},
		"phase": Clock.phase,
		"beat": Clock.beat_index,
	}

static func _nearby(agent: Agent) -> Array:
	var out: Array = []
	for other in Agents.all():
		if other.id == agent.id:
			continue
		var d: float = agent.position.distance_to(other.position)
		if d <= NEARBY_RADIUS:
			out.append({"id": other.id, "role": other.role, "faction": other.faction, "distance": d})
	return out

static func _recent_events() -> Array:
	var out: Array = []
	for e in EventBus.latest(RECENT_EVENT_COUNT):
		out.append({"type": e.get("type", ""), "data": e.get("data", {})})
	return out
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[perception]` shows nine PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/Perception.gd tingen/tests/run_tests.gd
git commit -m "feat(agents): Perception snapshot builder"
```

---

## Task 2: ActionCommit (apply one validated verb)

**Files:**
- Create: `tingen/src/ActionCommit.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_action_commit() -> void:
	print("[action commit]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.position = Vector2.ZERO
	var before: float = voss.position.distance_to(Vector2(420, 360))
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)
	_ok(out.has("moved_to"), "move_to reports a new position")
	_ok(voss.position.distance_to(Vector2(420, 360)) < before, "agent moved toward the site")
	_ok(voss.current_action.get("verb", "") == "move_to", "current_action is recorded")
	# talk_to records memory, no movement.
	var pos_before: Vector2 = voss.position
	ActionCommit.commit({"actor": "clerk_voss", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "ritual"}}, voss)
	_ok(voss.position == pos_before, "talk_to does not move the agent")
	_ok(voss.short_memory.size() >= 1, "talk_to records a memory")
	# move_to with an unresolved target is a safe no-op.
	var out2: Dictionary = ActionCommit.commit({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "nowhere_xyz"}}, voss)
	_ok(out2.has("noop"), "unresolved move target is a no-op")
	# coordinate-string target resolves.
	ActionCommit.commit({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "100,100"}}, voss)
	_ok(true, "coordinate target does not error")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_action_commit()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: parse/identifier error — `ActionCommit` not defined.

- [ ] **Step 3: Create ActionCommit.gd**

Create `tingen/src/ActionCommit.gd`:

```gdscript
class_name ActionCommit
extends RefCounted
## Deterministically applies ONE already-validated action to its agent and the world.
## Returns a small outcome Dictionary describing what happened (logged to the EventBus by
## the runtime). This is the only place agents change world state. For the slice, verbs
## that belong to later systems (combat, ritual countdown, sabotage economy) are recorded
## as memory + outcome here and given their full effects in their own plans.

## Named ritual/world sites in scene coordinates. Inside the iron_cross polygon
## [320,200, 560,380] from districts.json.
const SITES: Dictionary = {
	"iron_cross_warehouse": Vector2(420, 360),
}

## One beat's worth of movement, matching the registry fallback step.
static func _step() -> float:
	return Agents.fallback_speed

static func commit(action: Dictionary, agent: Agent) -> Dictionary:
	agent.current_action = action.duplicate(true)
	var verb := String(action.get("verb", ""))
	var args: Dictionary = action.get("args", {})
	match verb:
		"move_to":
			return _move_to(agent, String(args.get("target", "")))
		"talk_to":
			agent.remember("talked to %s about %s" % [args.get("agent", ""), args.get("topic", "")])
			return {"talked_to": String(args.get("agent", ""))}
		"gather_item":
			agent.remember("gathered %s" % args.get("item_id", ""))
			return {"gathered": String(args.get("item_id", ""))}
		"perform_ritual_step":
			agent.remember("performed ritual step: %s" % args.get("step", ""))
			return {"ritual_step": String(args.get("step", ""))}
		"recruit":
			agent.remember("approached %s to recruit" % args.get("agent", ""))
			return {"recruited": String(args.get("agent", ""))}
		"report":
			agent.remember("reported to %s: %s" % [args.get("to", ""), args.get("info", "")])
			return {"reported_to": String(args.get("to", ""))}
		"hide":
			agent.remember("went to ground")
			return {"hid": true}
		"flee":
			return _flee(agent, String(args.get("from", "")))
		"attack":
			agent.remember("attacked %s" % args.get("target", ""))
			return {"attacked": String(args.get("target", ""))}
		"idle":
			return {"idle": true}
		_:
			return {"noop": "unhandled verb '%s'" % verb}

static func _move_to(agent: Agent, target: String) -> Dictionary:
	var resolved := _resolve_target(target)
	if not resolved["found"]:
		return {"noop": "unresolved target '%s'" % target}
	var dest: Vector2 = resolved["pos"]
	var to_dest: Vector2 = dest - agent.position
	var dist: float = to_dest.length()
	var step := _step()
	if dist <= step or dist == 0.0:
		agent.position = dest
	else:
		agent.position += to_dest / dist * step
	agent.remember("moved toward %s" % target)
	return {"moved_to": [agent.position.x, agent.position.y]}

static func _flee(agent: Agent, from: String) -> Dictionary:
	var resolved := _resolve_target(from)
	if resolved["found"]:
		var away: Vector2 = agent.position - (resolved["pos"] as Vector2)
		if away.length() > 0.0:
			agent.position += away / away.length() * _step()
	agent.remember("fled from %s" % from)
	return {"fled_from": from}

## Resolve a target string to a position. Order: another agent's id, a named site, an
## "x,y" coordinate. Returns { found: bool, pos: Vector2 }.
static func _resolve_target(target: String) -> Dictionary:
	var other: Agent = Agents.get_agent(target)
	if other != null:
		return {"found": true, "pos": other.position}
	if SITES.has(target):
		return {"found": true, "pos": SITES[target]}
	if "," in target:
		var parts := target.split(",")
		if parts.size() >= 2 and parts[0].is_valid_float() and parts[1].is_valid_float():
			return {"found": true, "pos": Vector2(float(parts[0]), float(parts[1]))}
	return {"found": false, "pos": Vector2.ZERO}
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[action commit]` shows seven PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/ActionCommit.gd tingen/tests/run_tests.gd
git commit -m "feat(agents): ActionCommit — deterministic verb application"
```

---

## Task 3: AgentRuntime (run one beat end-to-end)

**Files:**
- Create: `tingen/src/AgentRuntime.gd`
- Modify: `tingen/project.godot`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_agent_runtime_beat() -> void:
	print("[agent runtime]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var ART: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	EB.clear()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.position = Vector2(400, 300)
	ART.player_position = Vector2(400, 300)
	ART.active_radius = 50.0   # only voss is active

	# Mock proposes a valid move for voss.
	var mock := MockSidecar.new()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	SB.set_client(mock)

	var before: Vector2 = voss.position
	ART.run_beat()
	_ok(voss.position != before, "active agent acted on its proposal")
	_ok(EB.events("agent_action").size() == 1, "one agent_action logged")
	_ok(EB.events("agent_action")[0]["data"]["actor"] == "clerk_voss", "logged actor is voss")

	# Invalid proposal -> rejected -> fallback.
	EB.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "teleport", "args": {}})
	ART.run_beat()
	_ok(EB.events("action_rejected").size() == 1, "invalid action is rejected, not committed")
	_ok(EB.events("agent_action").size() == 0, "no agent_action for the rejected proposal")

	# Idle proposal -> no movement.
	EB.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "idle", "args": {}})
	var pos_idle: Vector2 = voss.position
	ART.run_beat()
	_ok(voss.position == pos_idle, "idle proposal leaves the agent in place")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_agent_runtime_beat()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failure resolving `/root/AgentRuntime` (autoload missing).

- [ ] **Step 3: Create AgentRuntime.gd + register autoload**

Create `tingen/src/AgentRuntime.gd`:

```gdscript
extends Node
## Drives one deliberation beat (autoload `AgentRuntime`). On each `Clock.beat_ticked` it:
##   1. selects ACTIVE agents (near the player or explicitly flagged),
##   2. builds a perception snapshot for each and asks the SidecarBridge for proposals,
##   3. validates each proposal against ActionSchema,
##   4. commits the approved verb via ActionCommit and logs it to the EventBus,
##   5. runs schedule fallback for every INACTIVE agent so the world keeps moving.
## A rejected proposal falls the agent back to its schedule (the critic plan refines this
## into the approve/reroll/veto/amend verdict set). The overseer plan inserts its review
## between steps 3 and 4.

@export var auto_run: bool = true
var player_position: Vector2 = Vector2(440, 300)
var active_radius: float = 240.0
var always_active: Dictionary = {}   # agent_id -> true

func _ready() -> void:
	Clock.beat_ticked.connect(_on_beat)

func _on_beat(_beat_index: int, _day: int) -> void:
	if auto_run:
		run_beat()

func run_beat() -> void:
	var active: Array = _active_agents()
	var active_ids: Dictionary = {}
	for a in active:
		active_ids[a.id] = true

	if not active.is_empty():
		var snaps: Array = []
		for a in active:
			snaps.append(Perception.build_snapshot(a, player_position))
		var proposals: Array = SidecarBridge.propose(snaps)
		for i in active.size():
			var proposal: Variant = proposals[i] if i < proposals.size() else null
			_resolve_proposal(active[i], proposal)

	# Inactive agents keep to their schedule so nothing stalls.
	for a in Agents.all():
		if not active_ids.has(a.id):
			a.tick_fallback(Clock.phase, Agents.fallback_speed)

func _active_agents() -> Array:
	var out: Array = []
	for a in Agents.all():
		if always_active.has(a.id) or a.position.distance_to(player_position) <= active_radius:
			out.append(a)
	return out

func _resolve_proposal(agent: Agent, proposal: Variant) -> void:
	if typeof(proposal) != TYPE_DICTIONARY:
		agent.tick_fallback(Clock.phase, Agents.fallback_speed)
		return
	var action: Dictionary = proposal
	var verdict: Dictionary = ActionSchema.validate(action)
	if not verdict["ok"]:
		EventBus.emit_event("action_rejected", {
			"actor": agent.id, "verb": String(action.get("verb", "")), "reason": verdict["reason"],
		})
		agent.tick_fallback(Clock.phase, Agents.fallback_speed)
		return
	var outcome: Dictionary = ActionCommit.commit(action, agent)
	EventBus.emit_event("agent_action", {
		"actor": agent.id, "verb": String(action["verb"]), "args": action.get("args", {}), "outcome": outcome,
	})
```

Register the autoload in `tingen/project.godot` — add the `AgentRuntime` line after `SidecarBridge`:

```
SidecarBridge="*res://src/SidecarBridge.gd"
AgentRuntime="*res://src/AgentRuntime.gd"
EventManager="*res://src/EventManager.gd"
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[agent runtime]` shows seven PASS lines; full suite ends `=== N passed, 0 failed ===`, exit 0.

> Note: `AgentRuntime` auto-runs on real beats. The headless test runner advances no real time by default, so `_on_beat` won't fire during tests unless a test calls `Clock.advance_minutes`. If a *different* test advances the clock far enough to cross a beat while a live `MockSidecar` is set, harmless `agent_action`/`action_rejected` events may be logged. Tests that count events `EB.clear()` first (as above), so this does not cause flakiness. If you prefer total isolation, set `AgentRuntime.auto_run = false` at the top of any test that advances the clock.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/AgentRuntime.gd tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(agents): AgentRuntime beat loop (perceive -> propose -> commit)"
```

---

## Done criteria for this plan

- Full headless suite passes and includes: perception, action commit, agent runtime.
- `AgentRuntime` runs a complete beat: active agents perceive → propose → validate → commit → log; inactive agents fallback.
- Invalid proposals are rejected (logged `action_rejected`) and never mutate the world; the agent falls back.
- `idle` is a true no-op; `move_to` resolves agent ids, named sites, and `x,y` coordinates.

## What this plan deliberately does NOT do (later plans)

- No overseer/critic verdicts beyond schema legality — Plan 5 inserts coherence/interestingness review and directives between propose and commit.
- No full verb economics — `gather_item`, `perform_ritual_step`, `attack` record memory/outcome but their world effects (cult supply, ritual countdown, combat) land in Plans 5/6.
- No live LLM — the runtime calls `SidecarBridge`, which serves `MockSidecar`. The real `HttpSidecar` is post-slice.
- No on-screen agent sprites — headless logic only; scene integration ships with the player-verbs/UI plan.
