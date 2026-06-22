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
