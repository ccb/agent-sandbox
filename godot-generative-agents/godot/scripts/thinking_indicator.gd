extends RefCounted
## Pure decision logic for the live "thinking" cue (issue #372): whether the
## indicator should show, and its label text this frame. No scene, no sim
## knowledge -- viewer.gd feeds it live state and thinking_badge.gd renders the
## result. Global, not per-agent (stall inference can't attribute to one agent;
## per-agent bubbles are #551). Headless-tested (tests/test_thinking_indicator.gd).

const DOT_PERIOD_MS := 400  # one dot added every this many ms
const MAX_DOTS := 3


static func should_show(is_live: bool, run_state: String, playhead_at_head: bool,
		ms_since_last_frame: int, threshold_ms: int) -> bool:
	# True only when a live, RUNNING backend has caught the head (nothing left to
	# ease toward) and no new frame has landed for longer than threshold_ms.
	# Any other state -- not live, paused/finished/stopped/waiting, still easing
	# through buffered frames, or a frame arrived recently -- returns false.
	return (
		is_live
		and run_state == "running"
		and playhead_at_head
		and ms_since_last_frame > threshold_ms
	)


static func ellipsis(now_ms: int) -> String:
	# "thinking" -> "thinking." -> ".." -> "..." -> wrap, one dot per DOT_PERIOD_MS.
	var dots := int(now_ms / DOT_PERIOD_MS) % (MAX_DOTS + 1)
	return "thinking" + ".".repeat(dots)
