extends SceneTree
## Headless unit tests for scripts/deciding_indicator.gd (issue #551). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_deciding_indicator.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const DecidingState := preload("res://scripts/deciding_indicator.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _rec(agent: String, state: String) -> Dictionary:
	return {"kind": "deciding", "agent": agent, "state": state, "step": 0}


func _initialize() -> void:
	var s = DecidingState.new()
	_check(not s.seen_signal(), "no signal seen before any record")
	_check(not s.any_deciding(), "nobody deciding initially")

	s.apply(_rec("Maya", "begin"))
	_check(s.is_deciding("Maya"), "begin -> agent is deciding")
	_check(s.any_deciding(), "begin -> any_deciding true")
	_check(s.seen_signal(), "a record arrived -> signal seen")
	_check(not s.is_deciding("Diego"), "other agent unaffected")

	s.apply(_rec("Maya", "end"))
	_check(not s.is_deciding("Maya"), "end -> agent no longer deciding")
	_check(not s.any_deciding(), "end -> any_deciding false")

	# Unmatched end (no prior begin) is safely ignored, no error.
	s.apply(_rec("Ghost", "end"))
	_check(not s.is_deciding("Ghost"), "unmatched end -> not deciding")

	# A record missing the agent is ignored.
	s.apply({"kind": "deciding", "state": "begin"})
	_check(not s.any_deciding(), "agent-less record ignored")

	# clear() drops all state (teardown / backend restart).
	s.apply(_rec("Sofia", "begin"))
	s.clear()
	_check(not s.any_deciding(), "clear -> nobody deciding")
	_check(not s.seen_signal(), "clear -> signal reset (new run may be mock)")

	if _failures == 0:
		print("test_deciding_indicator: all checks passed")
	quit(1 if _failures > 0 else 0)
