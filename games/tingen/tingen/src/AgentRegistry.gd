extends Node
## Live registry of every Agent in the district (autoload singleton `Agents`).
##
## Builds one Agent per NpcDB definition at startup (and on demand via `rebuild`),
## owns their lifetime, and answers spatial queries the rest of the sim needs:
## `get_agent`/`all` for lookup, `active` for "who is near here" (the cheap stand-in
## for the LLM's attention budget), and `tick_beat` to step every agent's fallback
## movement once per clock beat. Round-trips through to_dict()/from_dict() so a save
## restores each agent's runtime state on top of the freshly-built cast.

var fallback_speed: float = 48.0
var _agents: Dictionary = {}  # id -> Agent

func _ready() -> void:
	rebuild()

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

func active(center: Vector2, radius: float) -> Array:
	var out: Array = []
	for a in _agents.values():
		if a.position.distance_to(center) <= radius:
			out.append(a)
	return out

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
