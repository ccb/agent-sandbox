class_name Perception
extends RefCounted
## Builds the perception snapshot a sidecar needs to choose an action for one agent.
## A snapshot is a flat, JSON-safe Dictionary: who the agent is, what it wants, where it
## stands, who/what is near it, the recent event stream, and the world's coarse state.
## Pure read — never mutates anything.

const NEARBY_RADIUS: float = 160.0
const RECENT_EVENT_COUNT: int = 8

## Resolve an autoload singleton by name. Direct `Autoload.` references fail to compile
## in a class_name script under the headless -s harness (autoloads register after
## class_name scripts are parsed); the /root lookup is ordering-independent.
static func _al(autoload_name: String) -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("/root/" + autoload_name)

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
		"stage": _al("WorldManager").current_stage_id,
		"pressures": {
			"corruption": _al("WorldState").corruption,
			"cult_readiness": _al("WorldState").cult_readiness,
			"panic": _al("WorldState").panic,
			"attention": _al("WorldState").attention,
		},
		"phase": _al("Clock").phase,
		"beat": _al("Clock").beat_index,
	}

static func _nearby(agent: Agent) -> Array:
	var out: Array = []
	for other in _al("Agents").all():
		if other.id == agent.id:
			continue
		var d: float = agent.position.distance_to(other.position)
		if d <= NEARBY_RADIUS:
			out.append({"id": other.id, "role": other.role, "faction": other.faction, "distance": d})
	return out

static func _recent_events() -> Array:
	var out: Array = []
	for e in _al("EventBus").latest(RECENT_EVENT_COUNT):
		out.append({"type": e.get("type", ""), "data": e.get("data", {})})
	return out
