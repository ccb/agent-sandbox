# World-AI Overseer + Critic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the director above the simulation. A `Critic` reviews every proposed action on legality (possible now), coherence (fits the agent), and interestingness, returning approve / amend / veto. An `Overseer` consumes the event stream, tracks whether the player is involved, issues directives that re-task or coordinate agents, and enforces the invariant that **the cult is never exposed/caught without the player**. Both hook into the beat loop between proposal and commit — deterministically, with no LLM.

**Architecture:** `Critic` (static lib) is pure: `(action, agent) -> verdict`. `Overseer` (autoload) holds mutable director state: a one-shot directive queue keyed by agent, a `player_involved` flag updated from the `EventBus`, and the exposure guard the critic consults. `AgentRuntime.run_beat` is upgraded to: apply overseer directives first (director authority), then for active agents run `propose → schema → critic → commit`, then fallback the rest. Vetoes fall the agent back to its schedule.

**Tech Stack:** Godot 4.6, GDScript, autoload + `class_name` static lib, headless `SceneTree` test runner.

**Depends on:** Plans 1, 3, 4 (`EventBus`, `Agent`/`Agents`, `ActionSchema`, `AgentRuntime`, `ActionCommit`, `Perception`).

**Source spec:** `docs/superpowers/specs/2026-06-08-tingen-agent-sim-vertical-slice-design.md` §C, §4, §6 (success criteria 2 & 3, tests 2–4).

---

## Conventions

- **Godot project root:** `Tingen-Game/tingen/`. Run from `Tingen-Game/`.
- **Run the suite:** `godot --headless --path tingen -s tests/run_tests.gd`. Success tail: `=== N passed, 0 failed ===`, exit 0.
- **Test pattern:** one `SceneTree` script; each feature gets `func _test_xxx()` using `_ok(cond, label)`, called in `_init()` above the final `print(...)`.

## File Structure

- **Create** `tingen/src/Overseer.gd` — autoload `Overseer`. One job: director state (directives, player-involvement, exposure guard, coordinate).
- **Create** `tingen/src/Critic.gd` — `class_name Critic`. One job: verdict on one proposed action.
- **Modify** `tingen/src/AgentRuntime.gd` — insert directive + critic review into `run_beat`.
- **Modify** `tingen/project.godot` — register `Overseer`.
- **Modify** `tingen/tests/run_tests.gd` — add tests.

---

## Task 1: Overseer autoload (director state)

**Files:**
- Create: `tingen/src/Overseer.gd`
- Modify: `tingen/project.godot`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_overseer_state() -> void:
	print("[overseer]")
	var OV: Object = root.get_node("/root/Overseer")
	var EB: Object = root.get_node("/root/EventBus")
	OV.reset()
	# Directives: one-shot, keyed by agent.
	OV.issue_directive("clerk_voss", {"actor": "clerk_voss", "verb": "hide", "args": {}})
	_ok(OV.has_directive("clerk_voss"), "directive queued")
	var d: Dictionary = OV.take_directive("clerk_voss")
	_ok(d.get("verb", "") == "hide", "directive returned")
	_ok(not OV.has_directive("clerk_voss"), "directive is one-shot")
	_ok(OV.take_directive("nobody").is_empty(), "no directive returns empty dict")
	# Coordinate: issue the same directive to several agents.
	OV.coordinate(["fishwife_dalia", "lamplighter_orin"], {"verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	_ok(OV.has_directive("fishwife_dalia"), "coordinate queues for agent 1")
	_ok(OV.has_directive("lamplighter_orin"), "coordinate queues for agent 2")
	_ok(OV.take_directive("fishwife_dalia").get("actor", "") == "fishwife_dalia", "coordinate sets actor per agent")
	# Player involvement is initially false, flips on a player_ event.
	OV.reset()
	_ok(OV.allows_exposure() == false, "exposure disallowed until player is involved")
	EB.emit_event("player_sabotage", {"actor": "player", "item": "ritual_salt"})
	_ok(OV.allows_exposure() == true, "a player_ event marks the player involved")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_overseer_state()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failure resolving `/root/Overseer` (autoload missing).

- [ ] **Step 3: Create Overseer.gd + register autoload**

Create `tingen/src/Overseer.gd`:

```gdscript
extends Node
## World-AI overseer / director (autoload `Overseer`). Sits above the simulation: it
## reads the EventBus, holds a one-shot directive queue that can re-task or coordinate
## agents, and enforces the invariant that the cult is never exposed/caught without the
## player's involvement. The Critic consults `allows_exposure()`; the AgentRuntime applies
## directives at the top of each beat. Deterministic — no LLM here (the real director's
## LLM reasoning, when added, produces directives through `issue_directive`).

var player_involved: bool = false

var _directives: Dictionary = {}   # agent_id -> action dict

func _ready() -> void:
	EventBus.event_logged.connect(_on_event)

func reset() -> void:
	_directives.clear()
	player_involved = false

func _on_event(ev: Dictionary) -> void:
	# The player being "involved" gates exposure (no caught-by-chance). Any event the
	# player authored — typed `player_*` or carrying actor "player" — counts.
	var type := String(ev.get("type", ""))
	var actor := String((ev.get("data", {}) as Dictionary).get("actor", ""))
	if type.begins_with("player_") or actor == "player":
		player_involved = true

## Queue a one-shot directive for an agent. `action` should be a full action dict; the
## actor is forced to `agent_id`.
func issue_directive(agent_id: String, action: Dictionary) -> void:
	var a: Dictionary = action.duplicate(true)
	a["actor"] = agent_id
	_directives[agent_id] = a

## Coordinate a group beat: issue one action template to several agents at once.
func coordinate(agent_ids: Array, action_template: Dictionary) -> void:
	for id in agent_ids:
		issue_directive(String(id), action_template)

func has_directive(agent_id: String) -> bool:
	return _directives.has(agent_id)

## Pop and return a directive (one-shot). Returns {} when none.
func take_directive(agent_id: String) -> Dictionary:
	if not _directives.has(agent_id):
		return {}
	var d: Dictionary = _directives[agent_id]
	_directives.erase(agent_id)
	return d

## The no-chance-exposure invariant: exposing/catching the cell is only allowed once the
## player has gotten involved.
func allows_exposure() -> bool:
	return player_involved

func to_dict() -> Dictionary:
	return {"player_involved": player_involved, "directives": _directives.duplicate(true)}

func from_dict(d: Dictionary) -> void:
	player_involved = bool(d.get("player_involved", false))
	_directives = (d.get("directives", {}) as Dictionary).duplicate(true)
```

Register the autoload in `tingen/project.godot` — add `Overseer` after `AgentRuntime`:

```
AgentRuntime="*res://src/AgentRuntime.gd"
Overseer="*res://src/Overseer.gd"
EventManager="*res://src/EventManager.gd"
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[overseer]` shows ten PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/Overseer.gd tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(overseer): director state — directives, coordinate, exposure guard"
```

---

## Task 2: Critic (verdict on a proposed action)

**Files:**
- Create: `tingen/src/Critic.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_critic_verdicts() -> void:
	print("[critic]")
	var AG: Object = root.get_node("/root/Agents")
	var OV: Object = root.get_node("/root/Overseer")
	AG.rebuild()
	OV.reset()
	var voss: Agent = AG.get_agent("clerk_voss")        # cult / leader
	var pell: Agent = AG.get_agent("dockhand_pell")     # civilian / victim
	var orin: Agent = AG.get_agent("lamplighter_orin")  # cult / scout_waverer

	# Coherent cult ritual step: approved.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, voss)["verdict"] == "approve",
		"cult leader may perform a ritual step")
	# Victim performing a ritual step: incoherent -> veto.
	_ok(Critic.review({"actor": "dockhand_pell", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, pell)["verdict"] == "veto",
		"the victim cannot perform a ritual step")
	# A turned waverer (faction no longer cult) performing a ritual step -> veto.
	orin.faction = "ally"
	_ok(Critic.review({"actor": "lamplighter_orin", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, orin)["verdict"] == "veto",
		"a turned waverer would not perform a ritual step")
	# Exposing report without player involvement -> veto; with involvement -> approve.
	var expose := {"actor": "clerk_voss", "verb": "report", "args": {"to": "nighthawks", "info": "the cult meets at the warehouse"}}
	_ok(Critic.review(expose, voss)["verdict"] == "veto", "no caught-by-chance: exposing report vetoed")
	OV.player_involved = true
	_ok(Critic.review(expose, voss)["verdict"] == "approve", "exposing report allowed once player is involved")
	# Ordinary move is always fine.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)["verdict"] == "approve",
		"ordinary move approved")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_critic_verdicts()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: parse/identifier error — `Critic` not defined.

- [ ] **Step 3: Create Critic.gd**

Create `tingen/src/Critic.gd`:

```gdscript
class_name Critic
extends RefCounted
## The "catch & kill" guardrail. Given a schema-valid proposed action and its agent,
## returns a verdict on three axes:
##   - legality (state): is the verb possible for this agent right now?
##   - coherence: does it fit the agent's identity / faction / role?
##   - interestingness: does it advance or complicate the thread (vs. dead repetition)?
## Verdict ∈ { approve, amend, veto }. `amend` returns a corrected `action`. The runtime
## turns veto (and, for the slice, reroll-equivalents) into a schedule fallback.
## Deterministic and pure — the eventual LLM critic produces the same verdict shape.

static func _verdict(v: String, reason: String = "", action: Dictionary = {}) -> Dictionary:
	return {"verdict": v, "reason": reason, "action": action}

static func review(action: Dictionary, agent: Agent) -> Dictionary:
	var verb := String(action.get("verb", ""))
	var args: Dictionary = action.get("args", {})

	# --- Coherence / state legality by role + faction ---
	var is_cultist := agent.faction == "cult"

	if verb == "perform_ritual_step":
		if not is_cultist:
			return _verdict("veto", "%s is not a cultist and cannot perform a ritual step" % agent.id)
	if verb == "recruit":
		if not is_cultist:
			return _verdict("veto", "%s is not a cultist and cannot recruit" % agent.id)
	if agent.role == "victim" and verb in ["perform_ritual_step", "recruit", "attack"]:
		return _verdict("veto", "the intended victim would not act as a cultist")

	# --- No-chance-exposure invariant ---
	if verb == "report" and _is_exposing(args) and not Overseer.allows_exposure():
		return _verdict("veto", "the cell cannot be exposed without the player's involvement")

	# --- Interestingness: kill an agent re-issuing the identical action it just did. ---
	if not agent.current_action.is_empty() \
			and String(agent.current_action.get("verb", "")) == verb \
			and agent.current_action.get("args", {}) == args \
			and verb in ["hide", "idle"]:
		return _verdict("veto", "repeating a passive action is dramatically inert")

	return _verdict("approve")

## A report "exposes" the cell when it informs the law (e.g. the Nighthawks) or names the
## cult to an outside party.
static func _is_exposing(args: Dictionary) -> bool:
	var to := String(args.get("to", "")).to_lower()
	var info := String(args.get("info", "")).to_lower()
	if to in ["nighthawks", "police", "church", "authorities"]:
		return true
	return "cult" in info or "ritual" in info or "summon" in info
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[critic]` shows seven PASS lines; suite exits 0.

> The critic test mutates `orin.faction` and `OV.player_involved`. If a later test depends on a fresh registry/overseer, it already calls `AG.rebuild()` / `OV.reset()` at its top, so this leaves no cross-test residue.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/Critic.gd tingen/tests/run_tests.gd
git commit -m "feat(critic): verdict on legality, coherence, interestingness"
```

---

## Task 3: Wire overseer + critic into the beat loop

**Files:**
- Modify: `tingen/src/AgentRuntime.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_runtime_with_overseer() -> void:
	print("[runtime + overseer]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var OV: Object = root.get_node("/root/Overseer")
	var ART: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	OV.reset()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.position = Vector2(400, 300)
	ART.player_position = Vector2(400, 300)
	ART.active_radius = 50.0

	# 1) Critic veto: turned waverer proposing a ritual step -> vetoed -> no commit.
	var orin: Agent = AG.get_agent("lamplighter_orin")
	orin.faction = "ally"
	orin.position = Vector2(400, 300)   # make orin active too
	var mock := MockSidecar.new()
	mock.set_action("lamplighter_orin", {"actor": "lamplighter_orin", "verb": "perform_ritual_step", "args": {"step": "x"}})
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "idle", "args": {}})
	SB.set_client(mock)
	EB.clear()
	ART.run_beat()
	_ok(EB.events("action_vetoed").size() >= 1, "incoherent action is vetoed")
	var ritual_actions := EB.events("agent_action").filter(func(e): return e["data"]["verb"] == "perform_ritual_step")
	_ok(ritual_actions.size() == 0, "vetoed ritual step is never committed")

	# 2) Overseer directive overrides the agent's own proposal.
	AG.rebuild(); OV.reset()
	var voss2: Agent = AG.get_agent("clerk_voss")
	voss2.position = Vector2(800, 800)              # far from player -> not active
	ART.player_position = Vector2(0, 0)
	ART.active_radius = 10.0
	var before: Vector2 = voss2.position
	OV.issue_directive("clerk_voss", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	EB.clear()
	ART.run_beat()
	_ok(EB.events("overseer_directive").size() == 1, "directive committed even for an inactive agent")
	_ok(voss2.position != before, "directed agent moved per the directive")

	# 3) End-to-end exposure invariant: exposing report blocked, then allowed.
	AG.rebuild(); OV.reset()
	var voss3: Agent = AG.get_agent("clerk_voss")
	voss3.position = Vector2(0, 0)
	ART.player_position = Vector2(0, 0)
	ART.active_radius = 50.0
	mock.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "report", "args": {"to": "nighthawks", "info": "the cult meets at the warehouse"}})
	# make only voss active: move others away
	for a in AG.all():
		if a.id != "clerk_voss":
			a.position = Vector2(9000, 9000)
	EB.clear()
	ART.run_beat()
	_ok(EB.events("action_vetoed").size() == 1, "exposing report vetoed without player involvement")
	# Player gets involved, then the same report is allowed.
	EB.emit_event("player_investigate", {"actor": "player"})
	EB.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "report", "args": {"to": "nighthawks", "info": "the cult meets at the warehouse"}})
	ART.run_beat()
	_ok(EB.events("agent_action").size() == 1, "report committed once the player is involved")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_runtime_with_overseer()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[runtime + overseer]` FAILs — `run_beat` doesn't apply directives or run the critic yet (no `overseer_directive`/`action_vetoed` events).

- [ ] **Step 3: Upgrade AgentRuntime.run_beat**

In `tingen/src/AgentRuntime.gd`, replace the entire `run_beat()` function and the `_resolve_proposal()` function with the versions below, and add the new `_apply_directive()` function. (Keep `_ready`, `_on_beat`, and `_active_agents` as they are.)

```gdscript
func run_beat() -> void:
	var handled: Dictionary = {}   # agent_id -> true once acted/decided this beat

	# 1) Overseer directives first — the director's authority overrides agent proposals.
	for a in Agents.all():
		var directive: Dictionary = Overseer.take_directive(a.id)
		if not directive.is_empty():
			_apply_directive(a, directive)
			handled[a.id] = true

	# 2) Active agents deliberate (those not already handled by a directive).
	var to_deliberate: Array = []
	for a in _active_agents():
		if not handled.has(a.id):
			to_deliberate.append(a)
	if not to_deliberate.is_empty():
		var snaps: Array = []
		for a in to_deliberate:
			snaps.append(Perception.build_snapshot(a, player_position))
		var proposals: Array = SidecarBridge.propose(snaps)
		for i in to_deliberate.size():
			var proposal: Variant = proposals[i] if i < proposals.size() else null
			_resolve_proposal(to_deliberate[i], proposal)
			handled[to_deliberate[i].id] = true

	# 3) Everyone else keeps to their schedule so nothing stalls.
	for a in Agents.all():
		if not handled.has(a.id):
			a.tick_fallback(Clock.phase, Agents.fallback_speed)

func _resolve_proposal(agent: Agent, proposal: Variant) -> void:
	if typeof(proposal) != TYPE_DICTIONARY:
		agent.tick_fallback(Clock.phase, Agents.fallback_speed)
		return
	var action: Dictionary = proposal
	# Legality (schema).
	var schema: Dictionary = ActionSchema.validate(action)
	if not schema["ok"]:
		EventBus.emit_event("action_rejected", {
			"actor": agent.id, "verb": String(action.get("verb", "")), "reason": schema["reason"],
		})
		agent.tick_fallback(Clock.phase, Agents.fallback_speed)
		return
	# Critic: legality(state) + coherence + interestingness.
	var review: Dictionary = Critic.review(action, agent)
	match String(review["verdict"]):
		"approve":
			_commit_and_log(agent, action, "agent_action")
		"amend":
			_commit_and_log(agent, review["action"], "agent_action_amended")
		_:  # veto (and any reroll-equivalent): fall back to schedule
			EventBus.emit_event("action_vetoed", {
				"actor": agent.id, "verb": String(action.get("verb", "")), "reason": review["reason"],
			})
			agent.tick_fallback(Clock.phase, Agents.fallback_speed)

func _apply_directive(agent: Agent, directive: Dictionary) -> void:
	# Directives come from the overseer (trusted) but must still be legal verbs.
	var schema: Dictionary = ActionSchema.validate(directive)
	if not schema["ok"]:
		EventBus.emit_event("directive_rejected", {
			"actor": agent.id, "verb": String(directive.get("verb", "")), "reason": schema["reason"],
		})
		agent.tick_fallback(Clock.phase, Agents.fallback_speed)
		return
	_commit_and_log(agent, directive, "overseer_directive")

func _commit_and_log(agent: Agent, action: Dictionary, event_type: String) -> void:
	var outcome: Dictionary = ActionCommit.commit(action, agent)
	EventBus.emit_event(event_type, {
		"actor": agent.id, "verb": String(action.get("verb", "")), "args": action.get("args", {}), "outcome": outcome,
	})
```

> This supersedes the simpler `_resolve_proposal` from the agent-runtime plan; the `action_rejected` behavior for schema-invalid proposals is preserved, and `agent_action` logging is unchanged for approved actions, so the earlier `[agent runtime]` test still passes.

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[runtime + overseer]` shows six PASS lines; the earlier `[agent runtime]` test still passes; full suite ends `=== N passed, 0 failed ===`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/AgentRuntime.gd tingen/tests/run_tests.gd
git commit -m "feat(runtime): apply overseer directives + critic verdicts in the beat loop"
```

---

## Done criteria for this plan

- Full headless suite passes and includes: overseer state, critic verdicts, runtime + overseer integration.
- The critic vetoes incoherent/illegal actions (victim or turned-waverer ritual step; non-cultist recruit) and approves coherent ones.
- The no-chance-exposure invariant holds: an exposing `report` is vetoed until a `player_*` event flips `Overseer.player_involved`.
- The overseer can re-task a single agent and coordinate several via directives, overriding their own proposals.

## What this plan deliberately does NOT do (later plans)

- No LLM-driven directives/critique — directives are issued programmatically; verdicts are deterministic rules. The real director's LLM reasoning, when added, produces the same directive/verdict shapes through these same entry points.
- No `reroll` round-trip — for the synchronous slice, non-approve verdicts fall back; true reroll (re-ask the sidecar) is post-slice.
- No impede score, sabotage economy, or combat — Plan 6. (Overseer is saved via its own `to_dict/from_dict`; add the `overseer` key to `SaveManager` in Plan 6 alongside impede, or now if convenient.)
