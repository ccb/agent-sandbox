extends SceneTree
## Headless unit tests for scripts/live_clip_span.gd (issue #548). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_live_clip_span.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const LiveClipSpan := preload("res://scripts/live_clip_span.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _span_eq(got: Dictionary, from: int, to: int) -> bool:
	return not got.is_empty() and int(got["from"]) == from and int(got["to"]) == to


func _initialize() -> void:
	# --- too little history -> {} ---
	_check(LiveClipSpan.span_last_n(0, 60).is_empty(), "head 0 (1 frame) -> {}")
	# --- exactly min_n frames (head 1) -> whole run ---
	_check(_span_eq(LiveClipSpan.span_last_n(1, 60), 0, 1), "head 1, N 60 -> {0,1}")
	# --- exact N well inside history ---
	_check(_span_eq(LiveClipSpan.span_last_n(100, 60), 41, 100), "head 100, N 60 -> {41,100}")
	# --- N exceeds history -> whole run so far ---
	_check(_span_eq(LiveClipSpan.span_last_n(10, 60), 0, 10), "head 10, N 60 -> {0,10}")
	# --- n below min_n -> {} ---
	_check(LiveClipSpan.span_last_n(100, 1).is_empty(), "N 1 (< min_n) -> {}")
	# --- n at the min_n boundary ---
	_check(_span_eq(LiveClipSpan.span_last_n(100, 2), 99, 100), "head 100, N 2 -> {99,100}")
	# --- custom min_n honored ---
	_check(LiveClipSpan.span_last_n(3, 60, 5).is_empty(), "head 3, min_n 5 -> {} (too little)")
	_check(_span_eq(LiveClipSpan.span_last_n(4, 60, 5), 0, 4), "head 4, min_n 5 -> {0,4}")

	# --- invariant sweep: to == head, 0 <= from <= to, over many heads/Ns ---
	var ok := true
	for head in range(1, 200, 7):
		for n in [2, 5, 60, 500]:
			var s := LiveClipSpan.span_last_n(head, n)
			if s.is_empty():
				continue
			if int(s["to"]) != head or int(s["from"]) < 0 or int(s["from"]) > int(s["to"]):
				ok = false
	_check(ok, "invariant: to==head and 0<=from<=to across sweep")

	if _failures == 0:
		print("test_live_clip_span: all checks passed")
	quit(1 if _failures > 0 else 0)
