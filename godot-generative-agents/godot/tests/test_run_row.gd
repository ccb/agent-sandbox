extends SceneTree
## Headless unit tests for scripts/run_row.gd (issue #716). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_run_row.gd

const RunRow := preload("res://scripts/run_row.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	var row := {
		"id": "run-2-live", "status": "running", "model": "claude-haiku-4-5",
		"created": "2026-07-22T12:34:56+00:00", "cost": 0.0123, "steps": 42,
	}
	var s := RunRow.label(row)
	_check(s.begins_with("run-2-live · running · claude-haiku-4-5 · 2026-07-22 12:34"),
		"label leads with id/status/model + short time")
	_check(s.contains("$0.0123") and s.ends_with("42 steps"),
		"label carries cost + steps")

	# A mock-brain run has model == null -> "mock".
	var mockrow := {"id": "r1", "status": "finished", "model": null,
		"created": "2026-07-22T09:00:00+00:00", "cost": 0.0, "steps": 5}
	_check(RunRow.label(mockrow).contains(" · mock · "), "null model renders as 'mock'")

	# An odd/short created string passes through rather than crashing.
	var weird := {"id": "r2", "status": "x", "model": "m", "created": "soon", "cost": 12.5, "steps": 1}
	var w := RunRow.label(weird)
	_check(w.contains(" · soon · "), "unparseable created passes through")
	_check(w.contains("$12.50"), "cost >= $10 uses two decimals")

	if _failures == 0:
		print("test_run_row: all checks passed")
	quit(1 if _failures > 0 else 0)
