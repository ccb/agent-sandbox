extends RefCounted
## Pure pacing logic for the live interpolation buffer (issue #372): given how
## many ticks are buffered ahead of the playhead (`lead`), return the clock-speed
## multiplier that keeps live playback smooth and near-real-time across irregular
## tick arrivals. No scene, no sim knowledge -- viewer.gd feeds it live state and
## applies the result to its `_t` clock. Headless-tested (tests/test_live_pacer.gd).


static func factor(lead: float, target := 2.0, catchup_max := 3.0) -> float:
	# lead <= 0       : starved (playhead at the head, nothing to ease toward) -> hold.
	# 0 < lead < target: buffer draining -> ease to a stop (ramp 0 -> 1x across the interval).
	# lead >= target  : healthy or backlog -> 1x, then +1x per extra buffered tick, capped.
	if lead <= 0.0:
		return 0.0
	if lead < target:
		return lead / target
	return minf(1.0 + (lead - target), catchup_max)
