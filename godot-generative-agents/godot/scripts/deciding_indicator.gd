extends RefCounted
## Pure per-agent decision-lifecycle state (issue #551), driven by the backend's
## `{kind:"deciding", agent, state:"begin"|"end", step, elapsed_ms?}` feed records.
## viewer.gd feeds it each record and reads is_deciding()/any_deciding() to drive
## per-agent "thinking" bubbles and the global badge fallback. No scene, no sim
## knowledge. Headless-tested (tests/test_deciding_indicator.gd). The authoritative
## per-agent signal #372 could only infer globally from a frame stall.

var _deciding := {}   # agent name -> true while mid-decision
var _seen := false    # has any `deciding` record arrived this run?


func apply(rec: Dictionary) -> void:
	var agent := String(rec.get("agent", ""))
	if agent == "":
		return  # malformed record: ignore
	_seen = true
	match String(rec.get("state", "")):
		"begin":
			_deciding[agent] = true
		"end":
			_deciding.erase(agent)


func is_deciding(agent: String) -> bool:
	return _deciding.get(agent, false)


func any_deciding() -> bool:
	return not _deciding.is_empty()


func seen_signal() -> bool:
	# True once a real `deciding` record has arrived -> the viewer prefers this
	# authoritative signal over #372's stall-inference for the global badge.
	return _seen


func clear() -> void:
	# Teardown / backend restart (#549): drop all in-flight state so a dropped
	# `end` across a reconnect can't strand a bubble, and reset _seen so the badge
	# falls back to stall-inference until the (possibly mock) new run signals.
	_deciding.clear()
	_seen = false
