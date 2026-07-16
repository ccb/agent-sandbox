extends SceneTree
## P1 (experiential wave) — REST UNTIL MORNING: the lodging bed's dead-time skip. There was NO way
## to skip dead time in a run; the bed becomes an Interactable verb (mirroring the digest/acting
## spots) that routes through RunManager.rest_until_morning():
##   * advances the Clock to the NEXT morning phase (08:00, the run's canonical day start)
##   * triggers the existing nightly safe-house checkpoint EXACTLY ONCE per rest (the fast-forward
##     crossing nightfall must not double-snapshot on top of the verb's own morning checkpoint)
##   * applies the existing rest Madness relief (checkpoint_night's Cogitation, -10)
##   * refuses CLEANLY during Ritual Night and while the player is in combat (no clock movement,
##     no checkpoint, a typed refusal reason)
## Standalone: godot --headless --path tingen -s tests/test_rest_verb.gd
## Also folded into the main suite (run_tests.gd `_test_rest_verb`) via the SAME run_all() entry.

func _init() -> void:
	await process_frame
	await process_frame
	# Never touch the player's REAL persistent profile (see tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_rest_verb: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_clock_jumps_to_next_morning(c, root)
	_b_exactly_one_checkpoint_per_rest(c, root)
	_c_rest_madness_relief(c, root)
	_d_refuses_during_ritual_night(c, root)
	_e_refuses_in_combat(c, root)
	_f_bed_interactable_wired_in_lodging(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

# (a) --------------------------------------------------------------------------------------------
static func _a_clock_jumps_to_next_morning(c: Dictionary, root: Node) -> void:
	print("[rest verb (a): resting advances the Clock to the NEXT morning phase (08:00)]")
	var RM: Object = root.get_node("/root/RunManager")
	var CL: Object = root.get_node("/root/Clock")
	_check(c, RM.has_method("rest_until_morning"), "RunManager exposes rest_until_morning()")
	if not RM.has_method("rest_until_morning"):
		return
	# No run -> a clean typed refusal.
	if RM.run_active():
		RM.end_run("lose")
	var r0: Dictionary = RM.rest_until_morning()
	_check(c, not bool(r0.get("ok", true)) and String(r0.get("reason", "")) == "no_run",
		"with no run active the verb refuses cleanly (reason 'no_run')")
	# Day-1 morning -> next morning is day 2 08:00 (a full day; resting is never a no-op).
	RM.start_run()
	var r1: Dictionary = RM.rest_until_morning()
	_check(c, bool(r1.get("ok", false)), "resting at day-1 08:00 succeeds")
	_check(c, CL.day == 2 and CL.minute_of_day == 480 and CL.phase == "morning",
		"day-1 08:00 -> day 2 08:00 morning (got day %d %s '%s')" % [CL.day, CL.hhmm(), CL.phase])
	# Mid-afternoon -> the following morning (crosses dusk/night/late-night/midnight).
	CL.set_time(2, 900)   # 15:00
	RM.rest_until_morning()
	_check(c, CL.day == 3 and CL.minute_of_day == 480 and CL.phase == "morning",
		"day-2 15:00 -> day 3 08:00 morning (got day %d %s '%s')" % [CL.day, CL.hhmm(), CL.phase])
	# Post-midnight late-night -> the SAME day's morning (already past the day roll).
	CL.set_time(4, 120)   # 02:00
	RM.rest_until_morning()
	_check(c, CL.day == 4 and CL.minute_of_day == 480 and CL.phase == "morning",
		"day-4 02:00 -> day 4 08:00 morning (got day %d %s '%s')" % [CL.day, CL.hhmm(), CL.phase])
	RM.end_run("lose")

# (b) --------------------------------------------------------------------------------------------
## The critical once-only pin: with a live game controller reporting the player IN the lodging (the
## live New-Run situation), the rest fast-forward crosses nightfall — the nightly auto-checkpoint
## (Clock.phase_changed -> checkpoint_night) must NOT fire on top of the verb's own single morning
## checkpoint. Exactly ONE checkpoint_saved per rest.
static func _b_exactly_one_checkpoint_per_rest(c: Dictionary, root: Node) -> void:
	print("[rest verb (b): exactly ONE nightly checkpoint per rest, even crossing nightfall in the lodging]")
	var RM: Object = root.get_node("/root/RunManager")
	var CL: Object = root.get_node("/root/Clock")
	if not RM.has_method("rest_until_morning"):
		_check(c, false, "RunManager.rest_until_morning missing — cannot pin the checkpoint count")
		return
	# Mount a stand-in game controller that reports the lodging as the live scene, so the nightly
	# auto-checkpoint gate (_player_in_lodging) is OPEN exactly like live play.
	var src := GDScript.new()
	src.source_code = "extends Node\nvar current_scene_path := \"res://scenes/IntroRoom.tscn\"\nfunc player_position() -> Vector2:\n\treturn Vector2(415, 470)\nfunc world_scene() -> Node:\n\treturn null\nfunc current_room() -> String:\n\treturn \"klein_bedroom\"\n"
	src.reload()
	var gc: Node = src.new()
	gc.add_to_group("game_controller")
	root.add_child(gc)

	RM.start_run()
	var saves := {"n": 0}
	var cb := func(_day: int) -> void:
		saves["n"] = int(saves["n"]) + 1
	RM.checkpoint_saved.connect(cb)
	CL.set_time(1, 720)   # midday — the fast-forward will cross nightfall (19:00) tonight
	var r: Dictionary = RM.rest_until_morning()
	RM.checkpoint_saved.disconnect(cb)
	_check(c, bool(r.get("ok", false)), "resting from midday succeeds")
	_check(c, int(saves["n"]) == 1,
		"exactly ONE checkpoint_saved fired for the rest (got %d)" % int(saves["n"]))
	_check(c, RM.has_checkpoint() and RM.checkpoint_day() == 2,
		"the checkpoint is the MORNING landing (day 2, got day %d)" % RM.checkpoint_day())
	# The suppression is rest-scoped: after the rest, the normal once-per-day rule governs again —
	# day 2 is already checkpointed (the rest's morning snapshot), so day-2 nightfall must NOT
	# re-snapshot; day-3 nightfall (a new day, no rest) fires the auto-checkpoint exactly once.
	var saves2 := {"n": 0}
	var cb2 := func(_day: int) -> void:
		saves2["n"] = int(saves2["n"]) + 1
	RM.checkpoint_saved.connect(cb2)
	CL.advance_minutes(700)   # 08:00 + 700min -> 19:40, past day-2 nightfall
	var same_day_saves: int = int(saves2["n"])
	CL.advance_minutes(1440)  # -> 19:40 day 3, past day-3 nightfall
	RM.checkpoint_saved.disconnect(cb2)
	_check(c, same_day_saves == 0,
		"day-2 nightfall does NOT re-snapshot (the rest already took day 2's checkpoint; got %d)" % same_day_saves)
	_check(c, int(saves2["n"]) == 1 and RM.checkpoint_day() == 3,
		"day-3 nightfall auto-checkpoints ONCE again after the rest (got %d, day %d)"
		% [int(saves2["n"]), RM.checkpoint_day()])
	RM.end_run("lose")
	gc.queue_free()

# (c) --------------------------------------------------------------------------------------------
static func _c_rest_madness_relief(c: Dictionary, root: Node) -> void:
	print("[rest verb (c): resting applies the existing nightly Madness rest relief]")
	var RM: Object = root.get_node("/root/RunManager")
	var M: Object = root.get_node("/root/Meters")
	if not RM.has_method("rest_until_morning"):
		_check(c, false, "RunManager.rest_until_morning missing — cannot pin the relief")
		return
	RM.start_run()
	M.set_meter("madness", 40.0)
	RM.rest_until_morning()
	var relief: float = float(M.get("MADNESS_REST_RELIEF"))
	_check(c, is_equal_approx(M.get_meter("madness"), 40.0 - relief),
		"resting relieves Madness by the nightly rest amount (40 -> %.0f, relief %.0f)"
		% [M.get_meter("madness"), relief])
	RM.end_run("lose")

# (d) --------------------------------------------------------------------------------------------
static func _d_refuses_during_ritual_night(c: Dictionary, root: Node) -> void:
	print("[rest verb (d): resting refuses cleanly during Ritual Night — no clock move, no checkpoint]")
	var RM: Object = root.get_node("/root/RunManager")
	var CL: Object = root.get_node("/root/Clock")
	var M: Object = root.get_node("/root/Meters")
	if not RM.has_method("rest_until_morning"):
		_check(c, false, "RunManager.rest_until_morning missing — cannot pin the refusal")
		return
	RM.start_run()
	M.set_meter("doom", 100.0)   # Doom tops out -> the Ritual Night latch lights
	_check(c, RM.ritual_night_reached(), "Doom 100 latched Ritual Night (test precondition)")
	var day_before: int = CL.day
	var minute_before: int = CL.minute_of_day
	var saves := {"n": 0}
	var cb := func(_day: int) -> void:
		saves["n"] = int(saves["n"]) + 1
	RM.checkpoint_saved.connect(cb)
	var r: Dictionary = RM.rest_until_morning()
	RM.checkpoint_saved.disconnect(cb)
	_check(c, not bool(r.get("ok", true)) and String(r.get("reason", "")) == "ritual_night",
		"the verb refuses with reason 'ritual_night'")
	_check(c, CL.day == day_before and CL.minute_of_day == minute_before,
		"a refused rest moves NO time")
	_check(c, int(saves["n"]) == 0, "a refused rest takes NO checkpoint")
	RM.end_run("lose")

# (e) --------------------------------------------------------------------------------------------
static func _e_refuses_in_combat(c: Dictionary, root: Node) -> void:
	print("[rest verb (e): resting refuses cleanly while the player is in combat]")
	var RM: Object = root.get_node("/root/RunManager")
	var CL: Object = root.get_node("/root/Clock")
	var AG: Object = root.get_node("/root/Agents")
	if not RM.has_method("rest_until_morning"):
		_check(c, false, "RunManager.rest_until_morning missing — cannot pin the refusal")
		return
	RM.start_run()
	var proxy: Object = AG.ensure_player_proxy(Vector2(415, 470), "klein_bedroom")
	proxy.in_combat = true
	var day_before: int = CL.day
	var minute_before: int = CL.minute_of_day
	var r: Dictionary = RM.rest_until_morning()
	_check(c, not bool(r.get("ok", true)) and String(r.get("reason", "")) == "in_combat",
		"the verb refuses with reason 'in_combat'")
	_check(c, CL.day == day_before and CL.minute_of_day == minute_before,
		"a refused rest moves NO time")
	proxy.in_combat = false
	var r2: Dictionary = RM.rest_until_morning()
	_check(c, bool(r2.get("ok", false)), "once combat ends the same rest succeeds")
	RM.end_run("lose")

# (f) --------------------------------------------------------------------------------------------
## Live reachability: the LODGING scene actually carries the bed RestSpot wired to the verb — a
## green RunManager seam with no scene caller would be the classic unreachable-feature trap.
static func _f_bed_interactable_wired_in_lodging(c: Dictionary, root: Node) -> void:
	print("[rest verb (f): the lodging bed carries a RestSpot Interactable wired to rest_until_morning]")
	var scene: Node = (load("res://scenes/IntroRoom.tscn") as PackedScene).instantiate()
	var rest: Node = scene.find_child("RestSpot", true, false)
	_check(c, rest != null, "IntroRoom (the lodging) has a RestSpot node")
	if rest != null:
		_check(c, bool(rest.get("rest_until_morning")),
			"the RestSpot carries the rest_until_morning Interactable flag")
		_check(c, String(rest.get("prompt_text")) != "" and String(rest.get("prompt_text")).to_lower().contains("rest"),
			"the RestSpot prompt names the verb ('%s')" % String(rest.get("prompt_text")))
	scene.free()
