extends SceneTree
## Headless unit tests for scripts/restart_detect.gd (issue #578). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_restart_detect.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const RestartDetect := preload("res://scripts/restart_detect.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# A changed boot nonce is a restart even when the new feed's cursor climbed
	# PAST ours -- the case the cursor-rewind heuristic misses (#578).
	_check(
		RestartDetect.should_rejoin("boot-A", "boot-B", 5, 20),
		"changed boot nonce with an advanced cursor -> rejoin"
	)
	# Same nonce, cursor advanced normally: a healthy follower, no rejoin.
	_check(
		not RestartDetect.should_rejoin("boot-A", "boot-A", 5, 20),
		"same boot nonce, advancing cursor -> keep following"
	)
	# Older server omits boot_id (empty hs_boot): fall back to the cursor
	# rewind -- a lower handshake cursor still means restart.
	_check(
		RestartDetect.should_rejoin("boot-A", "", 10, 2),
		"no boot_id + rewound cursor -> rejoin (fallback)"
	)
	_check(
		not RestartDetect.should_rejoin("boot-A", "", 5, 20),
		"no boot_id + advanced cursor -> keep following (fallback)"
	)
	# First handshake of a session (empty prev_boot): record only, no rejoin
	# unless the cursor itself rewound.
	_check(
		not RestartDetect.should_rejoin("", "boot-A", -1, 0),
		"first handshake -> no rejoin"
	)

	if _failures == 0:
		print("test_restart_detect: all checks passed")
	quit(1 if _failures > 0 else 0)
