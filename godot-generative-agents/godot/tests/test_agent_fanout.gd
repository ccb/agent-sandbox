extends SceneTree
## Headless unit tests for scripts/agent_fanout.gd (issue #560). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_agent_fanout.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const AgentFanout := preload("res://scripts/agent_fanout.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# --- offset: a lone (or empty) tile is never moved ---
	_check(AgentFanout.offset(0, 1, 16.0) == Vector2.ZERO, "count 1 -> no offset")
	_check(AgentFanout.offset(0, 0, 16.0) == Vector2.ZERO, "count 0 -> no offset")

	# --- offset: N co-located agents fan into a ring within the cap radius ---
	var cap := 16.0 * 0.36
	var pts := []
	for k in range(3):
		pts.append(AgentFanout.offset(k, 3, 16.0))
	_check(pts[0] != pts[1] and pts[1] != pts[2] and pts[0] != pts[2],
		"count 3 -> three distinct offsets")
	for k in range(3):
		_check(pts[k].length() <= cap + 0.001, "offset %d within cap radius" % k)
	_check(absf(pts[0].angle_to(pts[1]) - TAU / 3.0) < 0.001, "offsets evenly spaced")

	# --- offset is deterministic ---
	_check(AgentFanout.offset(1, 4, 16.0) == AgentFanout.offset(1, 4, 16.0),
		"offset deterministic")

	# --- groups: bucket co-located names (sorted); split distinct tiles ---
	var g: Dictionary = AgentFanout.groups({
		"Bob": Vector2i(3, 3), "Ada": Vector2i(3, 3), "Cy": Vector2i(9, 1),
	})
	_check(g[Vector2i(3, 3)] == ["Ada", "Bob"], "co-located names bucketed + sorted")
	_check(g[Vector2i(9, 1)] == ["Cy"], "distinct tile separate")

	if _failures == 0:
		print("test_agent_fanout: all checks passed")
	quit(1 if _failures > 0 else 0)
