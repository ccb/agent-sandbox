extends SceneTree
## Headless unit tests for scripts/day_plan_model.gd (issue #251). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_day_plan_model.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this before the scene smoke
## and also greps for the success sentinel (Godot can exit 0 on a parse error).

const DayPlanModel := preload("res://scripts/day_plan_model.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _frame(name: String, act: String) -> Dictionary:
	return {name: {"x": 0, "y": 0, "act": act, "e": "🙂", "chat": null}}


func _initialize() -> void:
	# --- transit_place ---
	_check(DayPlanModel.transit_place(
		"walking to Van Pelt — Kamin Gallery @ UPenn:Van Pelt Library:Kamin Gallery")
		== "Van Pelt — Kamin Gallery", "transit_place extracts the schedule place name")
	_check(DayPlanModel.transit_place("studying @ UPenn:X:y") == "",
		"transit_place empty for a non-walking act")

	# --- axis_len ---
	var sched_a := [{"place": "A", "activity": "x", "emoji": "🙂", "steps": 100},
		{"place": "B", "activity": "y", "emoji": "🙂", "steps": null}]
	var sched_b := [{"place": "C", "activity": "z", "emoji": "🙂", "steps": 300},
		{"place": "D", "activity": "w", "emoji": "🙂", "steps": 250}]
	_check(DayPlanModel.axis_len(400, [sched_a, sched_b]) == 550,
		"axis_len takes the larger of frames and explicit-step sums")
	_check(DayPlanModel.axis_len(800, [sched_a, sched_b]) == 800,
		"axis_len keeps frames when longer")

	# --- planned_segments ---
	var segs: Array = DayPlanModel.planned_segments(sched_a, 400)
	_check(segs.size() == 2, "one segment per stop")
	_check(int(segs[0]["start"]) == 0 and int(segs[0]["len"]) == 100,
		"explicit stop sized by its steps")
	_check(int(segs[1]["start"]) == 100 and int(segs[1]["len"]) == 300,
		"null-steps stop absorbs the remaining axis")
	var two_nulls := [{"place": "A", "activity": "x", "emoji": "🙂", "steps": null},
		{"place": "B", "activity": "y", "emoji": "🙂", "steps": null}]
	var segs2: Array = DayPlanModel.planned_segments(two_nulls, 401)
	_check(int(segs2[0]["len"]) == 200 and int(segs2[1]["len"]) == 201,
		"two nulls split the remainder; the last absorbs the leftover")
	_check(DayPlanModel.planned_segments([], 400).is_empty(),
		"empty schedule -> no segments")

	# --- actual_slots: transit / at (room-level!) / other ---
	var name := "Ada"
	var frames := [
		_frame(name, "walking to Van Pelt — Kamin Gallery @ UPenn:Van Pelt Library:Kamin Gallery"),
		_frame(name, "wandering exhibits @ UPenn:Van Pelt Library:Kamin Gallery"),
		_frame(name, "eating lunch @ UPenn:Houston Hall:lobby"),
	]
	var slots: Array = DayPlanModel.actual_slots(frames, name)
	_check(slots.size() == 3, "one slot per frame")
	_check(String(slots[0]["kind"]) == "transit"
		and String(slots[0]["place"]) == "Van Pelt — Kamin Gallery",
		"walking frame is transit toward the schedule place")
	_check(String(slots[1]["kind"]) == "at"
		and String(slots[1]["place"]) == "Van Pelt — Kamin Gallery",
		"perform at the learned address resolves to the ROOM-LEVEL place")
	_check(String(slots[2]["kind"]) == "other"
		and String(slots[2]["place"]) == "Houston Hall",
		"perform at an unlearned address is other, labeled by building")
	_check(DayPlanModel.actual_slots([], name).is_empty(), "no frames -> no slots")

	if _failures == 0:
		print("test_day_plan_model: all checks passed")
	quit(1 if _failures > 0 else 0)
