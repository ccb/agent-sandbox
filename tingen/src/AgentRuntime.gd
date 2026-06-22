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
