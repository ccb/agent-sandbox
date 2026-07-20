extends SceneTree
## Headless unit tests for scripts/run_state.gd (issue #678). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_run_state.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const RunState := preload("res://scripts/run_state.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# Armed but never ticked: a --start-paused boot, or a reset day (the #678
	# deadlock case) -- the whole day waits behind "▶ Start simulation".
	_check(
		RunState.from_status(true, 0) == "waiting",
		"paused at step 0 -> waiting (Start button armed)"
	)
	# Paused mid-day: the ordinary pause/resume toggle.
	_check(
		RunState.from_status(true, 42) == "paused",
		"paused mid-day -> paused (Resume button)"
	)
	# Not paused: the day is on, whatever the step says.
	_check(
		RunState.from_status(false, 0) == "running",
		"unpaused at step 0 -> running"
	)
	_check(
		RunState.from_status(false, 42) == "running",
		"unpaused mid-day -> running"
	)

	if _failures == 0:
		print("test_run_state: all checks passed")
	quit(1 if _failures > 0 else 0)
