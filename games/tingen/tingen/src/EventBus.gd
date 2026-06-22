extends Node
## Append-only world event log (autoload singleton `EventBus`).
##
## A single chronological record of everything that happens in the simulation:
## agent actions, world-manager beats, player verbs. Each event is a self-describing
## dictionary stamped with a monotonic sequence number and the clock time it occurred.
## Later plans (the LLM overseer/critic) read this log to reason about the story; for
## now it is the deterministic backbone other systems append to and query.
##
## The log is capped (MAX_EVENTS) so a long run can't grow unbounded; it round-trips
## through to_dict()/from_dict() so the SaveManager can persist it.

signal event_logged(event: Dictionary)

const MAX_EVENTS: int = 2000

var _events: Array = []
var _seq: int = 0

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

func events(filter_type: String = "") -> Array:
	if filter_type == "":
		return _events.duplicate(true)
	var matches: Array = _events.filter(func(e: Dictionary) -> bool: return e["type"] == filter_type)
	return matches.map(func(e: Dictionary) -> Dictionary: return e.duplicate(true))

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
