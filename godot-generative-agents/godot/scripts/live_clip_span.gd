extends RefCounted
## Pure "last N steps" span arithmetic for live-mode clip export (issue #548).
## No rendering, no HTTP -- headless-testable (tests/test_live_clip_span.gd).


static func span_last_n(head: int, n: int, min_n := 2) -> Dictionary:
	# The clip covers [from, to] over ELAPSED history, ending at the live head:
	#   to   = head
	#   from = max(0, head - n + 1)   (N frames, clamped to the start of history)
	# Returns {} (too little history / n below min) when n < min_n or head < min_n - 1.
	if n < min_n or head < min_n - 1:
		return {}
	var to := head
	var from := maxi(0, head - n + 1)
	return {"from": from, "to": to}
