extends SceneTree
## Headless unit tests for scripts/bubble_anchor.gd: the bottom-anchor invariant
## for the viewer's floating bubbles. Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_bubble_anchor.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const BubbleAnchor := preload("res://scripts/bubble_anchor.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	var w := 210.0
	var bottom := -100.0
	var short := BubbleAnchor.top_left(w, bottom, 40.0)
	var tall := BubbleAnchor.top_left(w, bottom, 90.0)

	# 1) The bottom edge (top.y + height) is invariant across content height.
	_check(is_equal_approx(short.y + 40.0, bottom), "short bubble bottom == bottom_y")
	_check(is_equal_approx(tall.y + 90.0, bottom), "tall bubble bottom == bottom_y")

	# 2) Taller text grows UPWARD (more-negative y = higher on screen).
	_check(tall.y < short.y, "taller text -> higher top")

	# 3) Horizontal centering is height-independent.
	_check(is_equal_approx(short.x, -w / 2.0), "short bubble x centered")
	_check(is_equal_approx(tall.x, -w / 2.0), "tall bubble x centered")

	# 4) Zero-height (empty label) rests its top exactly at bottom_y.
	_check(is_equal_approx(BubbleAnchor.top_left(w, bottom, 0.0).y, bottom),
		"empty bubble top == bottom_y")

	if _failures == 0:
		print("test_bubble_anchor: all checks passed")
	quit(1 if _failures > 0 else 0)
