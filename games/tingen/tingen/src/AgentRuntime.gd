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
	var handled: Dictionary = {}   # agent_id -> true once acted/decided this beat

	# 1) Overseer directives first — the director's authority overrides agent proposals.
	for a in Agents.all():
		if not a.deliberates:
			continue   # the player proxy is mirrored, never driven by the runtime
		var directive: Dictionary = Overseer.take_directive(a.id)
		if not directive.is_empty():
			_apply_directive(a, directive)
			handled[a.id] = true

	# 2) Active agents deliberate (those not already handled by a directive) — but only the beat's
	# COHORT re-decides (orchestrator/GM design §4.1). The stagger factor comes from the brain
	# (SidecarClient.stagger_k: 1 for deterministic brains, so mock/ambient behavior is unchanged;
	# 2 for the LLM), because decision monoculture is an LLM property: identical-context concurrent
	# calls converge on the modal action. Off-cohort agents CONTINUE their committed action, so the
	# world never freezes and later cohorts decide against the earlier cohort's committed effects.
	var k: int = 1
	if SidecarBridge.client != null:
		k = maxi(1, int(SidecarBridge.client.stagger_k()))
	var to_deliberate: Array = []
	for a in _active_agents():
		if handled.has(a.id):
			continue
		if in_cohort(a.id, Clock.beat_index, k):
			to_deliberate.append(a)
		else:
			_continue_action(a)
			handled[a.id] = true
	if not to_deliberate.is_empty():
		var snaps: Array = []
		for a in to_deliberate:
			var snap: Dictionary = Perception.build_snapshot(a, player_position)
			# One-shot `just_*` transition markers (P1): consumed off the agent HERE, so each
			# marker reaches exactly one deliberation snapshot and then is gone.
			var just: Array = a.take_transition_markers()
			if not just.is_empty():
				snap["just_happened"] = just
			snaps.append(snap)
		var proposals: Array = SidecarBridge.propose(snaps)
		for i in to_deliberate.size():
			var proposal: Variant = proposals[i] if i < proposals.size() else null
			_resolve_proposal(to_deliberate[i], proposal)
			handled[to_deliberate[i].id] = true

	# 3) Everyone else keeps to their schedule so nothing stalls (but never the player proxy).
	for a in Agents.all():
		if a.deliberates and not handled.has(a.id):
			a.tick_fallback(Clock.phase, Agents.fallback_speed)

## True when this agent re-decides on this beat under stagger factor k. Deterministic and
## replay-safe. NOTE: Godot's String.hash() is djb2 (h = h*33 + c) and 33 ≡ 1 (mod 2^n), so
## hash(id) % k would collapse to the id's character sum — md5 mixes honestly (same reasoning as
## ActionCommit._formation_offset).
func in_cohort(agent_id: String, beat: int, k: int) -> bool:
	if k <= 1:
		return true
	var h: int = ("0x" + agent_id.md5_text().substr(0, 8)).hex_to_int()
	return posmod(h, k) == posmod(beat, k)

## Verbs an off-cohort agent may re-commit unchanged between deliberations: extended activities
## whose repetition IS the activity. One-shot verbs (gather/talk/attack/adopt…) must never fire
## from a stale decision, so an off-cohort agent holding one falls back to its schedule instead.
const CONTINUOUS_VERBS: Array = ["move_to", "perform_ritual_step", "idle", "hide"]

## Off-cohort beat: keep the agent's committed activity going without a fresh decision. The action
## already passed schema+Critic when first committed; continuation is engine mechanics, not a new
## choice, so it re-commits directly (still logged, so the .md play log stays faithful).
## A TASK-BEARER holding a one-shot verb HOLDS position instead of schedule-falling-back: its
## schedule is its day job, and drifting toward it mid-mission wastes beats walking the wrong way
## (live playtest finding). Gated on the agent's own task DATA, never an identity.
func _continue_action(agent: Agent) -> void:
	# A downed agent is never animated by continuation: the Critic's "downed can only idle" gate
	# reviews fresh proposals, and re-committing a pre-downing action here would bypass it (a body
	# on the ground walking to the altar, or worse, still advancing the rite).
	if agent.downed:
		return
	# A combat-intent holder (engage/protect) HOLDS between deliberations: its published intent
	# persists as state and the M2 executor acts it out at frame rate — a schedule fallback here
	# would walk the body away from the very fight it just committed to. NOT in CONTINUOUS_VERBS:
	# intents aren't re-committed (re-stamping set_at_beat would forge a fresh decision).
	# `disengage` deliberately falls through — the agent is leaving, so normal continuation applies.
	var intent_mode := String(agent.combat_intent.get("mode", ""))
	if intent_mode == "engage" or intent_mode == "protect":
		return
	var act: Dictionary = agent.current_action
	if not act.is_empty() and String(act.get("verb", "")) in CONTINUOUS_VERBS:
		_commit_and_log(agent, act, "agent_action")
	elif agent.task.is_empty():
		agent.tick_fallback(Clock.phase, Agents.fallback_speed)
	# else: hold — the next deliberation beat re-decides from where the task left off

func _active_agents() -> Array:
	var out: Array = []
	for a in Agents.all():
		if not a.deliberates:
			continue   # the player proxy is perceivable + attackable, but never deliberates
		if always_active.has(a.id) or a.position.distance_to(player_position) <= active_radius:
			out.append(a)
	return out

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
	# `intent` + `room` are engine-side metadata for the log + later tooling; they do NOT feed the LLM
	# prompt — that is built separately in the sidecar (brain.py).
	EventBus.emit_event(event_type, {
		"actor": agent.id, "intent": agent.intent, "room": agent.room,
		"verb": String(action.get("verb", "")), "args": action.get("args", {}), "outcome": outcome,
	})
	_track_failure(agent, action, outcome)

## --- P5 (lab pull-in): the repeat-failure FREEZE GUARD -----------------------------------------
## Consecutive IDENTICAL gate-failed commits (same ActionCommit.failure_key) are counted per
## agent; the STUCK_THRESHOLDth one forces idle/replan, writes an informed-failure memory row
## (generalizing gather_item's contention fact — the next deliberation KNOWS why to change
## course), and emits `agent_stuck` so the GM sees stuck NPCs. Any success — or a DIFFERENT
## failure — resets the streak, so normal play never trips it.
const STUCK_THRESHOLD: int = 3
var _fail_streaks: Dictionary = {}   # agent_id -> {"key": String, "count": int}

func _track_failure(agent: Agent, action: Dictionary, outcome: Dictionary) -> void:
	var key := ActionCommit.failure_key(action, outcome)
	if key == "":
		_fail_streaks.erase(agent.id)
		return
	var s: Dictionary = _fail_streaks.get(agent.id, {"key": "", "count": 0})
	s["count"] = (int(s["count"]) + 1) if String(s["key"]) == key else 1
	s["key"] = key
	if int(s["count"]) < STUCK_THRESHOLD:
		_fail_streaks[agent.id] = s
		return
	_fail_streaks.erase(agent.id)   # reset after firing — a fresh streak must re-earn the guard
	var verb := String(action.get("verb", ""))
	var what := verb
	var args: Dictionary = action.get("args", {}) if action.get("args") is Dictionary else {}
	for k in ["target", "item_id", "agent", "step", "to"]:
		if args.has(k):
			what = "%s %s" % [verb, String(args[k])]
			break
	# Force the replan: a stale blocked action must not keep re-committing on off-cohort beats.
	agent.current_action = {"actor": agent.id, "verb": "idle", "args": {}}
	# PINNED (8.0): the informed failure must survive to the next deliberation, whatever else lands.
	agent.remember_scored("tried to %s three times and it did not work — that path is blocked; I must try something else" % what, 8.0)
	EventBus.emit_event("agent_stuck", {"agent": agent.id, "verb": verb, "key": key, "failures": STUCK_THRESHOLD})
