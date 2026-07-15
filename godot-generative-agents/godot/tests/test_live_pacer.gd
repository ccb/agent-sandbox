extends SceneTree
## Headless unit tests for scripts/live_pacer.gd (issue #372). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_live_pacer.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const LivePacer := preload("res://scripts/live_pacer.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _approx(a: float, b: float) -> bool:
	return absf(a - b) < 0.0001


func _initialize() -> void:
	# --- factor() curve, defaults target=2.0 catchup_max=3.0 ---
	_check(_approx(LivePacer.factor(0.0), 0.0), "lead 0 -> hold (0x)")
	_check(_approx(LivePacer.factor(1.0), 0.5), "lead 1 -> 0.5x (draining)")
	_check(_approx(LivePacer.factor(1.5), 0.75), "lead 1.5 -> 0.75x")
	_check(_approx(LivePacer.factor(2.0), 1.0), "lead 2 (target) -> 1x")
	_check(_approx(LivePacer.factor(3.0), 2.0), "lead 3 -> 2x (catch-up)")
	_check(_approx(LivePacer.factor(4.0), 3.0), "lead 4 -> 3x (cap reached)")
	_check(_approx(LivePacer.factor(5.0), 3.0), "lead 5 -> 3x (capped)")

	# --- negative lead holds ---
	_check(_approx(LivePacer.factor(-1.0), 0.0), "negative lead -> hold (0x)")

	# --- continuity at the knee: both branches yield 1.0 at lead == target ---
	_check(_approx(LivePacer.factor(2.0), 1.0), "knee is continuous at 1x")

	# --- monotonic non-decreasing across a sweep ---
	var prev := -1.0
	var mono := true
	for i in range(0, 61):  # lead 0.0 .. 6.0 step 0.1
		var f := LivePacer.factor(float(i) * 0.1)
		if f < prev - 0.0001:
			mono = false
		prev = f
	_check(mono, "factor is monotonic non-decreasing over lead 0..6")

	# --- custom args honored (target=4, max=2), distinct from defaults ---
	_check(_approx(LivePacer.factor(10.0, 4.0, 2.0), 2.0), "custom cap: factor(10,4,2) == 2.0")
	_check(_approx(LivePacer.factor(2.0, 4.0, 2.0), 0.5), "custom target: factor(2,4,2) == 0.5")

	if _failures == 0:
		print("test_live_pacer: all checks passed")
	quit(1 if _failures > 0 else 0)
