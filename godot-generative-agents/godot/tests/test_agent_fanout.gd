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

	# --- offset: a pair sits `spacing` apart, centred on the tile ---
	var p0 := AgentFanout.offset(0, 2, 32.0)
	var p1 := AgentFanout.offset(1, 2, 32.0)
	_check(p0 != p1, "count 2 -> two distinct offsets")
	_check(absf(p0.distance_to(p1) - 32.0) < 0.001, "pair is spacing apart")
	_check((p0 + p1).length() < 0.001, "pair is centred on the tile (offsets cancel)")

	# --- offset: N co-located agents ring with constant neighbour spacing ---
	var pts := []
	for k in range(3):
		pts.append(AgentFanout.offset(k, 3, 30.0))
	_check(pts[0] != pts[1] and pts[1] != pts[2] and pts[0] != pts[2],
		"count 3 -> three distinct offsets")
	_check(absf(pts[0].distance_to(pts[1]) - 30.0) < 0.001, "ring neighbours 0-1 spaced")
	_check(absf(pts[1].distance_to(pts[2]) - 30.0) < 0.001, "ring neighbours 1-2 spaced")
	_check(absf(pts[0].angle_to(pts[1]) - TAU / 3.0) < 0.001, "offsets evenly spaced")

	# --- offset is deterministic ---
	_check(AgentFanout.offset(1, 4, 32.0) == AgentFanout.offset(1, 4, 32.0),
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
