extends Node
## Event system (autoload singleton `EventManager`) — GDD §9 emergent beats.
##
## On every WorldManager strategic refresh, scores the event library against the
## current world state and (weighted-randomly) fires one eligible event. Each event
## carries effects (pressure nudges, lead changes, stage hints) and a notify channel
## the HUD toast layer listens on.
##
## Selection follows the extensibility plan: score = weight × state_match, where an
## event with unmet hard conditions scores 0. Cooldowns stop the same beat repeating
## back-to-back. The RNG is seeded from WorldManager so a reloaded save replays the
## same draws.

signal event_fired(event: Dictionary)

const EVENTS_PATH: String = "res://data/events.json"

var library: Array = []
var _cooldowns: Dictionary = {}      # event id -> refresh_count it is eligible again
var _rng := RandomNumberGenerator.new()

func _ready() -> void:
	_load()
	_rng.seed = WorldManager.seed_value ^ 0x5eed
	WorldManager.refreshed.connect(_on_refreshed)

func _load() -> void:
	if not FileAccess.file_exists(EVENTS_PATH):
		push_error("EventManager: missing %s" % EVENTS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(EVENTS_PATH))
	if typeof(parsed) != TYPE_ARRAY:
		push_error("EventManager: %s is not a JSON array" % EVENTS_PATH)
		return
	library = parsed

func _on_refreshed(refresh_count: int) -> void:
	var ev := _pick(refresh_count)
	if ev.is_empty():
		return
	_cooldowns[String(ev["id"])] = refresh_count + int(ev.get("cooldown", 0))
	for e in ev.get("effects", []):
		_apply_effect(e)
	event_fired.emit(ev)

## Weighted pick over eligible events. score = weight × state_match (0..1). Events
## with unmet conditions or on cooldown are excluded.
func _pick(refresh_count: int) -> Dictionary:
	var scored: Array = []
	var total: float = 0.0
	for ev in library:
		var id := String(ev["id"])
		if int(_cooldowns.get(id, 0)) > refresh_count:
			continue
		if not _conditions_met(ev.get("conditions", [])):
			continue
		var score: float = float(ev.get("weight", 1.0)) * _state_match(ev)
		if score <= 0.0:
			continue
		scored.append({"ev": ev, "score": score})
		total += score
	if total <= 0.0:
		return {}
	var roll: float = _rng.randf() * total
	for s in scored:
		roll -= float(s["score"])
		if roll <= 0.0:
			return s["ev"]
	return scored[-1]["ev"]

## Soft fit 0..1 — events that match the current stage/pressure mood weigh heavier.
## Kept simple: any "prefer_*" hints scale the score; absence means neutral 1.0.
func _state_match(ev: Dictionary) -> float:
	var m: float = 1.0
	var prefer_stage := String(ev.get("prefer_stage", ""))
	if prefer_stage != "" and prefer_stage != WorldManager.current_stage_id:
		m *= 0.5
	return m

func _conditions_met(conditions: Array) -> bool:
	for c in conditions:
		if not _condition_met(c):
			return false
	return true

func _condition_met(c: Dictionary) -> bool:
	match String(c.get("type", "")):
		"pressure_gte":
			return WorldState.get_pressure(StringName(c.get("target", ""))) >= float(c.get("value", 0))
		"pressure_lte":
			return WorldState.get_pressure(StringName(c.get("target", ""))) <= float(c.get("value", 0))
		"stage_in":
			return WorldManager.current_stage_id in (c.get("value", []) as Array)
		"clue_count_gte":
			return ClueDB.collected_count() >= int(c.get("value", 0))
		_:
			return true

func _apply_effect(e: Dictionary) -> void:
	match String(e.get("type", "")):
		"pressure":
			WorldState.adjust(StringName(e.get("target", "")), float(e.get("delta", 0.0)))
		"lead":
			WorldState.set_lead(String(e.get("text", "")))
		"collect":
			ClueDB.collect(String(e.get("clue", "")))
		"stage_hint", "notify":
			pass  # surfaced via event_fired payload to the toast layer
