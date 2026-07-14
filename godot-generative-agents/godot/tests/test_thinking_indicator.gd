extends SceneTree
## Headless unit tests for scripts/thinking_indicator.gd (issue #372). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_thinking_indicator.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const ThinkingIndicator := preload("res://scripts/thinking_indicator.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# --- should_show truth table (threshold 1500ms) ---
	_check(not ThinkingIndicator.should_show(false, "running", true, 9999, 1500),
		"not live -> never shows")
	_check(ThinkingIndicator.should_show(true, "running", true, 1600, 1500),
		"live + running + at head + stale -> shows")
	_check(not ThinkingIndicator.should_show(true, "running", true, 1000, 1500),
		"fresh frame (under threshold) -> no show")
	_check(not ThinkingIndicator.should_show(true, "running", false, 9999, 1500),
		"still easing (not at head) -> no show")
	_check(not ThinkingIndicator.should_show(true, "paused", true, 9999, 1500),
		"paused -> no show")
	_check(not ThinkingIndicator.should_show(true, "finished", true, 9999, 1500),
		"finished -> no show")
	_check(not ThinkingIndicator.should_show(true, "waiting", true, 9999, 1500),
		"waiting -> no show")

	# --- ellipsis cycles one dot per 400ms, wrapping after 3 dots ---
	_check(ThinkingIndicator.ellipsis(0) == "thinking", "0ms -> no dots")
	_check(ThinkingIndicator.ellipsis(400) == "thinking.", "400ms -> 1 dot")
	_check(ThinkingIndicator.ellipsis(800) == "thinking..", "800ms -> 2 dots")
	_check(ThinkingIndicator.ellipsis(1200) == "thinking...", "1200ms -> 3 dots")
	_check(ThinkingIndicator.ellipsis(1600) == "thinking", "1600ms -> wraps to 0 dots")

	if _failures == 0:
		print("test_thinking_indicator: all checks passed")
	quit(1 if _failures > 0 else 0)
