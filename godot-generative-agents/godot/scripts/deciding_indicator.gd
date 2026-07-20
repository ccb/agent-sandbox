extends RefCounted
## Pure per-agent decision-lifecycle state (issue #551), driven by the backend's
## `{kind:"deciding", agent, state:"begin"|"end", step, elapsed_ms?}` feed records.
## viewer.gd feeds it each record and reads is_deciding()/any_deciding() to drive
## per-agent "thinking" bubbles and (OR'd with #372's stall heuristic) the global
## badge. No scene, no sim knowledge. Headless-tested (tests/test_deciding_indicator.gd).

var _deciding := {}   # agent name -> true while mid-decision


func apply(rec: Dictionary) -> void:
	var agent := String(rec.get("agent", ""))
	if agent == "":
		return  # malformed record: ignore
	match String(rec.get("state", "")):
		"begin":
			_deciding[agent] = true
		"end":
			_deciding.erase(agent)


func is_deciding(agent: String) -> bool:
	return _deciding.get(agent, false)


func any_deciding() -> bool:
	return not _deciding.is_empty()


func clear() -> void:
	# Teardown / backend restart (#549): drop all in-flight state so a dropped
	# `end` across a reconnect can't strand a bubble.
	_deciding.clear()
