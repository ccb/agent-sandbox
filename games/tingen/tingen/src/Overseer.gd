extends Node
## World-AI overseer / director (autoload `Overseer`). Sits above the simulation: it
## reads the EventBus, holds a one-shot directive queue that can re-task or coordinate
## agents, and enforces the invariant that the cult is never exposed/caught without the
## player's involvement. The Critic consults `allows_exposure()`; the AgentRuntime applies
## directives at the top of each beat. Deterministic — no LLM here (the real director's
## LLM reasoning, when added, produces directives through `issue_directive`).

var player_involved: bool = false

## GM/Director loss-of-control threshold (combat plan §M4): when the city's corruption reaches
## this, the Director judges the change no longer resistible and DIRECTS any still-untransformed
## transform-capable agent to cast its transform — transformation as the GM's move through the
## existing directive seam, never an automatic engine reveal rule (§0).
const CORRUPTION_TRANSFORM_THRESHOLD: float = 85.0

var _directives: Dictionary = {}   # agent_id -> action dict
## Corruption-transform latch: agent_id -> true once directed. The crossing fires ONCE per agent
## — even if the cast later fails, the Director does not nag. Persisted (a reload past the
## threshold must not re-issue) and cleared by reset().
var _corruption_transformed: Dictionary = {}

func _ready() -> void:
	EventBus.event_logged.connect(_on_event)

func reset() -> void:
	_directives.clear()
	_corruption_transformed.clear()
	player_involved = false

func _on_event(ev: Dictionary) -> void:
	# The player being "involved" gates exposure (no caught-by-chance). Any event the
	# player authored — typed `player_*` or carrying actor "player" — counts.
	var type := String(ev.get("type", ""))
	var data: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	var actor := String(data.get("actor", ""))
	if type.begins_with("player_") or actor == "player":
		player_involved = true
	# Corruption movement is the Director's cue (combat plan §M4): whenever the tracked
	# corruption pressure changes at/above the threshold, sweep the cast for loss-of-control
	# transforms. The per-agent latch makes repeat sweeps free.
	if type == "world_var_changed" and String(data.get("var", "")) == "corruption":
		check_corruption_transforms(Agents.all(), float(data.get("to", 0.0)))

## The corruption loss-of-control pass (combat plan §M4). For each agent whose worn combat_form
## still carries an art that would transform it into something ELSE (not yet transformed) and
## whose latch has not fired: issue a one-shot `cast_ability` directive (schema-legal; commits
## through ActionCommit, which enters combat and routes the cast to the executor). Deterministic,
## no LLM. Returns the ids directed THIS call ([] below the threshold) so tests/logging can see
## exactly what the Director did.
func check_corruption_transforms(agents: Array, corruption: float) -> Array:
	if corruption < CORRUPTION_TRANSFORM_THRESHOLD:
		return []
	var directed: Array = []
	for a_v in agents:
		var a: Agent = a_v
		if a == null or a.downed or a.combat_form == "" or _corruption_transformed.has(a.id):
			continue
		var art := _transform_art_for(a)
		if art == "":
			continue
		issue_directive(a.id, {"verb": "cast_ability", "args": {"ability": art}})
		_corruption_transformed[a.id] = true
		directed.append(a.id)
	return directed

## The first kit art that would transform this agent into a form it is NOT already wearing — ""
## when its kit can't, or when it already wears its transform's target (i.e. "already
## transformed": the bieber kit's own assume_form points back at bieber_monster, so a turned
## monster is never re-directed).
func _transform_art_for(a: Agent) -> String:
	for art_v in (AbilityDB.kit_for(a.combat_form) as Array):
		var art := String(art_v)
		var def: Dictionary = AbilityDB.ability_for(art)
		if String(def.get("class", "")) != "transform":
			continue
		for eff_v in (def.get("effects", []) as Array):
			var eff: Dictionary = eff_v if eff_v is Dictionary else {}
			var form := String(eff.get("form", ""))
			if String(eff.get("kind", "")) == "transform" and form != "" and form != a.combat_form:
				return art
	return ""

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
	return {"player_involved": player_involved, "directives": _directives.duplicate(true),
		"corruption_transformed": _corruption_transformed.duplicate(true)}

func from_dict(d: Dictionary) -> void:
	player_involved = bool(d.get("player_involved", false))
	_directives = (d.get("directives", {}) as Dictionary).duplicate(true)
	_corruption_transformed = (d.get("corruption_transformed", {}) as Dictionary).duplicate(true)
