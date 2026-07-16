extends SceneTree
## P1 (experiential wave) — RUN PACE: the ~60-minute run budget (direction v2 §13) made an
## EXPLICIT RunManager constant applied at run start — never a scene side-effect (the old
## CitySummoning._bootstrap pace override has been DEAD/unmounted since M20, so live runs
## silently played at Clock's 1.0 s/game-min default: ~24 real-min/day, ~2.3x over budget).
## Standalone: godot --headless --path tingen -s tests/test_run_pace.gd
## Also folded into the main suite (run_tests.gd `_test_run_pace`) via the SAME run_all() entry.
##
## The pins:
##  (a) RunManager exposes RUN_SECONDS_PER_GAME_MINUTE and start_run() applies it to the Clock
##  (b) the pace lands the idle Doom-100 budget inside the ~60-minute design target (arithmetic
##      derived from MeterDrivers' own passive-fill constants, not hardcoded twice)
##  (c) the pace is a RUN CONSTANT: re-applied on a day-1 wipe, a checkpoint restore, and a
##      disk load (Continue), so no stale/older snapshot can drag a run back to the slow pace

func _init() -> void:
	await process_frame
	await process_frame
	# Never touch the player's REAL persistent profile (see tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_run_pace: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_start_run_applies_explicit_pace(c, root)
	_b_pace_meets_the_60_minute_budget(c, root)
	_c_pace_survives_wipe_restore_and_load(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

# (a) --------------------------------------------------------------------------------------------
static func _a_start_run_applies_explicit_pace(c: Dictionary, root: Node) -> void:
	print("[run pace (a): start_run applies the EXPLICIT RunManager pace constant to the Clock]")
	var RM: Object = root.get_node("/root/RunManager")
	var CL: Object = root.get_node("/root/Clock")
	var pace: Variant = RM.get("RUN_SECONDS_PER_GAME_MINUTE")
	_check(c, pace != null, "RunManager exposes RUN_SECONDS_PER_GAME_MINUTE (the explicit run-pace constant)")
	if pace == null:
		return
	# Dirty the pace to the old slow default, then start a run — the run must own its pace.
	CL.real_seconds_per_game_minute = 1.0
	RM.start_run()
	_check(c, is_equal_approx(CL.real_seconds_per_game_minute, float(pace)),
		"start_run() sets Clock.real_seconds_per_game_minute to the run constant (%.3f)" % float(pace))
	_check(c, float(pace) < 0.5, "the run pace is FASTER than the old 1.0 default (was ~2.3x over budget)")

# (b) --------------------------------------------------------------------------------------------
## The budget arithmetic, derived from MeterDrivers' own passive Doom-fill constants so the pin
## tracks retunes instead of hardcoding a second copy of the numbers:
##   passive fill/day = DOOM_PER_HOUR*24 + DOOM_PER_PHASE*6      (~17.4 Doom/day today)
##   idle Doom-100    = 100 / fill_per_day days  (~5.75 days)    (~8280 game-minutes)
##   real budget      = game-minutes * RUN_SECONDS_PER_GAME_MINUTE   (~58 real minutes at 0.42)
static func _b_pace_meets_the_60_minute_budget(c: Dictionary, root: Node) -> void:
	print("[run pace (b): the pace lands the idle Doom-100 run inside the ~60-minute design target]")
	var RM: Object = root.get_node("/root/RunManager")
	var MD: GDScript = load("res://src/MeterDrivers.gd") as GDScript
	var pace: Variant = RM.get("RUN_SECONDS_PER_GAME_MINUTE")
	if pace == null:
		_check(c, false, "RUN_SECONDS_PER_GAME_MINUTE missing — cannot compute the budget")
		return
	var fill_per_day: float = float(MD.DOOM_PER_HOUR) * 24.0 + float(MD.DOOM_PER_PHASE) * 6.0
	var idle_game_minutes: float = (100.0 / fill_per_day) * 1440.0
	var real_minutes: float = idle_game_minutes * float(pace) / 60.0
	_check(c, real_minutes >= 50.0 and real_minutes <= 70.0,
		"idle Doom-100 budget is ~60 real minutes (measured %.1f min: %.0f game-min at %.2f s/min)"
		% [real_minutes, idle_game_minutes, float(pace)])

# (c) --------------------------------------------------------------------------------------------
static func _c_pace_survives_wipe_restore_and_load(c: Dictionary, root: Node) -> void:
	print("[run pace (c): the pace is a RUN CONSTANT — re-applied on wipe, checkpoint restore, and disk load]")
	var RM: Object = root.get_node("/root/RunManager")
	var CL: Object = root.get_node("/root/Clock")
	var SM: Object = root.get_node("/root/SaveManager")
	var pace: Variant = RM.get("RUN_SECONDS_PER_GAME_MINUTE")
	if pace == null:
		_check(c, false, "RUN_SECONDS_PER_GAME_MINUTE missing — cannot pin the reapply seams")
		return
	var run_pace := float(pace)
	# Day-1 wipe (lost_control with no checkpoint yet -> _restart_fresh). N2 (A1) rerouted the
	# pre-checkpoint DEATH to a full run loss (no wipe, no live clock to pace), so the rampage
	# expiry is now the only day-1 same-run wipe — the pace pin moves with it.
	RM.start_run()
	CL.real_seconds_per_game_minute = 1.0
	RM.end_run("lost_control")
	_check(c, is_equal_approx(CL.real_seconds_per_game_minute, run_pace),
		"a day-1 wipe (lost_control, no checkpoint) re-applies the run pace")
	# Checkpoint restore (death after a nightly checkpoint -> _restore).
	RM.start_run()
	RM.checkpoint_night()
	CL.real_seconds_per_game_minute = 1.0
	RM.end_run("death")
	_check(c, is_equal_approx(CL.real_seconds_per_game_minute, run_pace),
		"a checkpoint restore (death after a nightly checkpoint) re-applies the run pace")
	# Disk load (the Continue path goes through SaveManager, never through start_run).
	var tmp: String = preload("res://src/TestSandbox.gd").path("save_pace_test.json")
	RM.start_run()
	SM.save_game(tmp)
	CL.real_seconds_per_game_minute = 1.0
	SM.load_game(tmp)
	_check(c, is_equal_approx(CL.real_seconds_per_game_minute, run_pace),
		"a disk load (Continue) re-applies the run pace")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
