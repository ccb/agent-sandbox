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

	# 5) fit_to_text shrink-wraps the box. A free Label only auto-GROWS to fit new
	#    text, never shrinks on its own, so after a tall (expanded) bubble collapses
	#    to one line fit_to_text must snap .size back down -- otherwise the stylebox
	#    background keeps the expanded box (the click-to-collapse "shape" bug).
	var label := Label.new()
	label.add_theme_font_size_override("font_size", 18)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.custom_minimum_size = Vector2(w, 0.0)
	get_root().add_child(label)
	label.size = Vector2(w, 0.0)              # cap width so the text wraps like a bubble
	label.text = "x ".repeat(200)            # long -> many wrapped lines
	BubbleAnchor.fit_to_text(label)
	var tall_size := label.size.y            # box grew to fit the long text
	label.text = "short line"                # collapse to a single line
	var before_shrink := label.size.y        # grow-only: .size is still tall here
	BubbleAnchor.fit_to_text(label)
	var after_size := label.size.y           # the size the stylebox background draws at
	_check(before_shrink > label.get_minimum_size().y + 1.0,
		"a Label doesn't self-shrink (the grow-only gotcha fit_to_text fixes)")
	_check(after_size < tall_size, "fit_to_text shrinks .size after collapse")
	_check(is_equal_approx(after_size, label.get_minimum_size().y),
		"fit_to_text sets .size to the text's minimum height")
	label.free()

	# 6) width_for scales the box with the amount of text: min at/below the clip
	#    length, the cap at/above the full length, and monotonic in between.
	var min_w := 210.0
	var max_w := 380.0
	var start := 120
	var full := 350
	_check(is_equal_approx(BubbleAnchor.width_for(0, min_w, max_w, start, full), min_w),
		"empty text -> min width")
	_check(is_equal_approx(BubbleAnchor.width_for(start, min_w, max_w, start, full), min_w),
		"at the clip length -> still min width (no playback jitter)")
	_check(is_equal_approx(BubbleAnchor.width_for(full, min_w, max_w, start, full), max_w),
		"at the full length -> max width")
	_check(is_equal_approx(BubbleAnchor.width_for(1000, min_w, max_w, start, full), max_w),
		"beyond the full length -> capped at max width")
	var mid := BubbleAnchor.width_for((start + full) / 2, min_w, max_w, start, full)
	_check(mid > min_w and mid < max_w, "a mid-length line widens between min and max")
	_check(BubbleAnchor.width_for(200, min_w, max_w, start, full)
			< BubbleAnchor.width_for(300, min_w, max_w, start, full),
		"more characters -> wider box (monotonic)")

	if _failures == 0:
		print("test_bubble_anchor: all checks passed")
	quit(1 if _failures > 0 else 0)
