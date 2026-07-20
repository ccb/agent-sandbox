extends SceneTree
## Headless unit tests for scripts/action_tally.gd + scripts/actions_hud.gd
## (issue #700). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_action_tally.gd
## Exit 0 = all checks pass; 1 = at least one failed (run_smoke_test.sh runs
## this before the scene smoke).

const ActionTally := preload("res://scripts/action_tally.gd")
const ActionsHud := preload("res://scripts/actions_hud.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _ev(turn: int, actor: String, action: String) -> Dictionary:
	# One GameEvent.to_primitive()-shaped record (only the fields tally reads).
	return {"turn": turn, "actor": actor, "action": action, "summary": ""}


func _initialize() -> void:
	# A small day: go x3 @ t0, travel x2 @ t1-2, perform x1 @ t3, plus an
	# engine-internal sound @ t1 that must be dropped (filter parity with #699).
	var events := [
		_ev(0, "Diego", "go"), _ev(0, "Sofia", "go"), _ev(0, "Tanaka", "go"),
		_ev(1, "Diego", "travel"), _ev(1, "world", "sound"),
		_ev(2, "Sofia", "travel"),
		_ev(3, "Diego", "perform"),
	]

	# --- filter: trigger/sound never counted ---
	var full: Array = ActionTally.tally(events, 999, 10)
	var actions := full.map(func(r: Dictionary) -> String: return r["action"])
	_check(not ("sound" in actions), "engine-internal 'sound' is dropped")
	_check(full.size() == 3, "three distinct command verbs after filtering")

	# --- ranking: count desc, then action asc ---
	_check(full[0]["action"] == "go" and full[0]["count"] == 3, "most-taken verb ranks first")
	_check(full[1]["action"] == "travel" and full[1]["count"] == 2, "second by count")
	_check(full[2]["action"] == "perform" and full[2]["count"] == 1, "third by count")

	# --- tie-break: equal counts sort by the verb ascending, deterministically ---
	var tied := [_ev(0, "A", "zeta"), _ev(0, "B", "alpha")]
	var tied_rows: Array = ActionTally.tally(tied, 5, 10)
	_check(tied_rows[0]["action"] == "alpha" and tied_rows[1]["action"] == "zeta",
		"equal counts break ties by action verb ascending")

	# --- cursor: only events at or before up_to_step are counted ---
	var at0: Array = ActionTally.tally(events, 0, 10)
	_check(at0.size() == 1 and at0[0]["action"] == "go" and at0[0]["count"] == 3,
		"up_to_step 0 counts only turn-0 events")
	var at1: Array = ActionTally.tally(events, 1, 10)
	# t0: go x3; t1: travel x1 (the sound is filtered) -> go=3, travel=1.
	_check(at1.size() == 2 and at1[0]["action"] == "go" and at1[0]["count"] == 3,
		"up_to_step 1 adds turn-1 command events, still drops the sound")
	var travel_at1 := at1.filter(func(r: Dictionary) -> bool: return r["action"] == "travel")
	_check(travel_at1.size() == 1 and travel_at1[0]["count"] == 1, "travel=1 at step 1")

	# --- scrubbing backward LOWERS counts (never monotone) ---
	var at3: Array = ActionTally.tally(events, 3, 10)
	var travel_at3 := at3.filter(func(r: Dictionary) -> bool: return r["action"] == "travel")
	_check(travel_at3[0]["count"] == 2, "travel=2 at step 3")
	_check(travel_at1[0]["count"] < travel_at3[0]["count"],
		"scrubbing from step 3 back to step 1 lowers travel's count")

	# --- top_n clamp ---
	_check(ActionTally.tally(events, 999, 2).size() == 2, "top_n caps the row count")
	_check(ActionTally.tally(events, 999, 0).is_empty(), "top_n 0 -> no rows")

	# --- robustness (#638): malformed input is skipped, never crashes ---
	_check(ActionTally.tally([], 5, 10).is_empty(), "empty events -> no rows")
	var junk := [
		"not a dict", 42, null,
		{"turn": 0},                       # no action
		{"action": "go"},                  # no turn
		{"turn": "x", "action": "go"},     # non-numeric turn
		{"turn": 0, "action": ""},         # empty action
		{"turn": 0, "action": "eat"},      # the one valid record
	]
	var jr: Array = ActionTally.tally(junk, 5, 10)
	_check(jr.size() == 1 and jr[0]["action"] == "eat" and jr[0]["count"] == 1,
		"malformed records skipped; only the well-formed one counts")

	# --- actions_hud.gd panel rendering (added to the tree so _ready builds it) ---
	var hud := ActionsHud.new()
	get_root().add_child(hud)
	hud.set_rows([{"action": "go", "count": 3}, {"action": "travel", "count": 2}])
	_check(hud._rows_box.get_child_count() == 2, "set_rows renders one row per entry")
	# Re-render with a different set: old rows are replaced, not appended (no doubling).
	hud.set_rows([{"action": "eat", "count": 1}])
	_check(hud._rows_box.get_child_count() == 1, "set_rows rebuilds cleanly (no stale rows)")
	# Empty tally -> a single "no actions yet" caption, not a blank box.
	hud.set_rows([])
	_check(hud._rows_box.get_child_count() == 1, "empty rows -> one empty-state caption")
	hud.free()

	if _failures == 0:
		print("test_action_tally: all checks passed")
	quit(1 if _failures > 0 else 0)
