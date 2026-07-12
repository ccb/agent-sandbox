extends SceneTree
## M7 — Ritual Night climax harness. Runs headless (no display): stage the crypt encounter
## state in the RitualNight controller and STEP it; assert every climax outcome resolves to an
## ending (win/lose) with NO softlock, plus the trigger/relocate/avatar/backlash spine and the
## determinism guard.
##
## Run: godot --headless --path tingen -s tests/test_ritual_night.gd

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()

	_test_trigger_doom_or_assault()
	_test_early_assault_while_tipped_relocates_once()
	_test_two_door_defender_counts()
	_test_fuse_runs_out_loses()
	_test_interrupt_interactable_wins()
	_test_kill_celebrant_wins()
	_test_avatar_half_lands_and_kill_wins()
	_test_no_softlock_every_outcome_ends_once()
	_test_determinism_fixed_seed()

	print("\n=== ritual_night: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

func _rn() -> Object:
	return root.get_node_or_null("/root/RitualNight")

func _rm() -> Object:
	return root.get_node("/root/RunManager")

func _fresh() -> Object:
	var rm := _rm()
	rm.start_run()
	root.get_node("/root/Agents").rebuild()
	var rn := _rn()
	rn.reset()
	return rn

# (a) Doom 100 OR force-assault STARTS Ritual Night.
func _test_trigger_doom_or_assault() -> void:
	print("[trigger: Doom 100 OR force-assault starts Ritual Night]")
	var M: Object = root.get_node("/root/Meters")
	var rn := _fresh()
	_ok(rn != null, "RitualNight autoload is registered")
	if rn == null:
		return
	_ok(not rn.active(), "a fresh run has no Ritual Night underway")
	# Doom 100 path.
	M.set_meter("doom", 100.0)
	_ok(rn.active(), "Doom 100 starts Ritual Night")
	# Force-assault path (a fresh run, Doom low).
	rn = _fresh()
	M.set_meter("doom", 20.0)
	rn.force_assault(true, 4242)
	_ok(rn.active(), "a force-assault starts Ritual Night even at low Doom")

# (a) early assault while TIPPED relocates the site ONCE.
func _test_early_assault_while_tipped_relocates_once() -> void:
	print("[trigger: early assault while tipped RELOCATES the site once]")
	var rn := _fresh()
	rn.set_tipped(true)
	var before: String = rn.site_room()
	rn.force_assault(true, 4242)
	var after: String = rn.site_room()
	_ok(after != before, "a tipped early assault relocates the ritual site once")
	_ok(rn.relocated(), "the relocation is latched")
	# A SECOND assault (already active) does not relocate again.
	var after2_room: String = rn.site_room()
	rn.force_assault(true, 4242)
	_ok(rn.site_room() == after2_room, "the site relocates at most once")
	# An UN-tipped early assault does not relocate.
	rn = _fresh()
	rn.set_tipped(false)
	var b2: String = rn.site_room()
	rn.force_assault(true, 4242)
	_ok(rn.site_room() == b2 and not rn.relocated(), "an un-tipped assault does not relocate")

# (b-entry) two portals into the crypt: guarded front vs quiet side, different defender counts.
func _test_two_door_defender_counts() -> void:
	print("[entry: two doors — guarded front has more defenders than the quiet side]")
	var rn := _fresh()
	rn.force_assault(false, 4242)   # front door
	var front := int(rn.defender_count())
	rn = _fresh()
	rn.force_assault(false, 4242, "side")   # quiet side
	var side := int(rn.defender_count())
	_ok(front > side, "the guarded front door fields more defenders than the quiet side (%d > %d)" % [front, side])
	_ok(side >= 1, "the quiet side still has at least one defender")

# (b-fuse) the fuse counts down; reaching 0 un-interrupted -> end_run('lose') + a lose result.
func _test_fuse_runs_out_loses() -> void:
	print("[fuse: reaching 0 un-interrupted -> end_run('lose') + a lose result]")
	var rn := _fresh()
	rn.force_assault(false, 4242)
	var start_fuse := int(rn.fuse_remaining())
	_ok(start_fuse > 0, "the fuse starts above zero (%d)" % start_fuse)
	rn.tick_fuse(1)
	_ok(int(rn.fuse_remaining()) == start_fuse - 1, "the fuse counts down one beat per tick")
	var ended := {"reason": ""}
	var cb := func(reason: String) -> void: ended["reason"] = reason
	_rm().run_ended.connect(cb)
	# Run the fuse to zero WITHOUT lowering it past the avatar threshold interruption.
	rn.tick_fuse(9999)
	_rm().run_ended.disconnect(cb)
	_ok(int(rn.fuse_remaining()) == 0, "the fuse reaches zero")
	_ok(ended["reason"] == "lose", "an un-interrupted fuse ends the run 'lose'")
	_ok(String(rn.result().get("outcome", "")) == "descent_complete", "a lose result records descent_complete")
	_ok(rn.resolved(), "the climax is resolved (an ending was reached)")

# (c) using the interrupt interactable BEFORE the fuse -> interrupt -> backlash wave -> WIN.
func _test_interrupt_interactable_wins() -> void:
	print("[interrupt: break-the-altar interactable -> backlash wave -> clear it -> win]")
	var rn := _fresh()
	rn.force_assault(false, 4242)
	var ended := {"reason": ""}
	var cb := func(reason: String) -> void: ended["reason"] = reason
	_rm().run_ended.connect(cb)
	# The altar interactable flips the SummoningPlan interrupt flag.
	rn.use_interrupt_interactable()
	_ok(rn.interrupted(), "the altar interactable interrupts the rite")
	_ok(rn.backlash_active(), "the interrupt spawns the backlash wave")
	# The surviving celebrants LOSE CONTROL -> assume_form into monsters (canon §⑦).
	var backlashers: Array = rn.backlash_monsters()
	_ok(backlashers.size() >= 1, "at least one celebrant assumes a monster form in the backlash")
	var any_monster := false
	var DB: Object = root.get_node("/root/AbilityDB")
	for id in backlashers:
		var a: Agent = root.get_node("/root/Agents").get_agent(id)
		if a != null and DB.is_monster_form(a.combat_form):
			any_monster = true
	_ok(any_monster, "a backlash celebrant wears a monster combat_form (assume_form)")
	_ok(ended["reason"] == "", "clearing is not yet done — the run has not ended mid-wave")
	# Survive/clear the wave -> WIN.
	rn.clear_backlash_wave()
	_rm().run_ended.disconnect(cb)
	_ok(ended["reason"] == "win", "surviving/clearing the backlash wins the run")
	_ok(String(rn.result().get("outcome", "")) == "descent_stopped", "the win result records descent_stopped")

# (c) killing the celebrant BEFORE the fuse also interrupts -> backlash -> WIN.
func _test_kill_celebrant_wins() -> void:
	print("[interrupt: kill the celebrant -> backlash wave -> clear it -> win]")
	var rn := _fresh()
	rn.force_assault(false, 4242)
	var ended := {"reason": ""}
	var cb := func(reason: String) -> void: ended["reason"] = reason
	_rm().run_ended.connect(cb)
	var celebrant: Agent = root.get_node("/root/Agents").get_agent(rn.celebrant_id())
	_ok(celebrant != null, "the celebrant exists as an agent")
	if celebrant != null:
		celebrant.take_damage(celebrant.hp + 10.0)   # down them
		rn.notify_agent_downed(celebrant.id)
	_ok(rn.interrupted() and rn.backlash_active(), "downing the celebrant interrupts + spawns the backlash")
	rn.clear_backlash_wave()
	_rm().run_ended.disconnect(cb)
	_ok(ended["reason"] == "win", "clearing the backlash after a celebrant kill wins")

# (d) the avatar HALF-LANDS past the low-fuse threshold; killing it -> win.
func _test_avatar_half_lands_and_kill_wins() -> void:
	print("[avatar: half-lands past the low-fuse threshold; killing it wins]")
	var rn := _fresh()
	rn.force_assault(false, 4242)
	_ok(not rn.avatar_present(), "no avatar before the low-fuse threshold")
	# Tick the fuse down PAST the low threshold (but not to zero).
	rn.tick_fuse(rn.fuse_remaining() - rn.avatar_threshold() + 1)
	_ok(rn.avatar_present(), "crossing the low-fuse threshold half-lands the avatar")
	var avatar: Agent = root.get_node("/root/Agents").get_agent(rn.avatar_id())
	var DB: Object = root.get_node("/root/AbilityDB")
	_ok(avatar != null and DB.is_monster_form(avatar.combat_form), "the avatar wears the descended_avatar monster form")
	# The avatar can assume a truer shape at low HP (two-stage descent, like bram_kell) — assert its form def.
	_ok(_has_low_hp_assume_form("descended_avatar"), "descended_avatar has an hp_below -> assume_form reflex (two-stage descent)")
	var ended := {"reason": ""}
	var cb := func(reason: String) -> void: ended["reason"] = reason
	_rm().run_ended.connect(cb)
	if avatar != null:
		avatar.take_damage(avatar.hp + 10.0)
		rn.notify_agent_downed(avatar.id)
	_rm().run_ended.disconnect(cb)
	_ok(ended["reason"] == "win", "killing the half-landed avatar wins the run")
	_ok(String(rn.result().get("outcome", "")) == "avatar_slain", "the win result records avatar_slain")

func _has_low_hp_assume_form(form: String) -> bool:
	var DB: Object = root.get_node("/root/AbilityDB")
	var fdef: Dictionary = DB.form_def(form)
	for r in (fdef.get("reflexes", []) as Array):
		if typeof(r) != TYPE_DICTIONARY:
			continue
		var when_v: Variant = (r as Dictionary).get("when", {})
		var do_v: Variant = (r as Dictionary).get("do", {})
		if when_v is Dictionary and do_v is Dictionary \
				and String((when_v as Dictionary).get("kind", "")) == "hp_below" \
				and String((do_v as Dictionary).get("kind", "")) == "cast":
			var aid := String((do_v as Dictionary).get("ability", ""))
			var adef: Dictionary = DB.ability_for(aid)
			if String(adef.get("class", "")) == "transform":
				return true
	return false

# (e) NO SOFTLOCK: every outcome calls end_run exactly once and returns toward Title (meta bumps).
func _test_no_softlock_every_outcome_ends_once() -> void:
	print("[no softlock: every climax outcome calls end_run exactly once + bumps meta toward Title]")
	var EG: Object = root.get_node("/root/EndGame")
	# EndGame must have been re-armed (start_run -> rearm) so the terminal player-death latch does
	# not swallow the climax screen; the resolver already latched it, so the ending screen fires.
	for path in ["lose", "interrupt", "avatar"]:
		var rn := _fresh()
		var runs_before := int(_rm().meta_runs_played())
		rn.force_assault(false, 4242)
		var count := {"n": 0, "reason": ""}
		var cb := func(reason: String) -> void:
			count["n"] = int(count["n"]) + 1
			count["reason"] = reason
		_rm().run_ended.connect(cb)
		# The SCREEN half of GAP-2.11: every climax outcome must raise an ending screen, not just end
		# the run. Capture EndGame.ending_reached so "reaches a screen" is asserted directly, not just
		# inferred from end_run. (Headless: show_ritual_result still emits the signal + builds no display.)
		var screen := {"n": 0, "outcome": ""}
		var scb := func(outcome: String, _res: Dictionary) -> void:
			screen["n"] = int(screen["n"]) + 1
			screen["outcome"] = outcome
		EG.ending_reached.connect(scb)
		match path:
			"lose":
				rn.tick_fuse(9999)
			"interrupt":
				rn.use_interrupt_interactable()
				rn.clear_backlash_wave()
			"avatar":
				rn.tick_fuse(rn.fuse_remaining() - rn.avatar_threshold() + 1)
				var av: Agent = root.get_node("/root/Agents").get_agent(rn.avatar_id())
				if av != null:
					av.take_damage(av.hp + 10.0)
					rn.notify_agent_downed(av.id)
		# A redundant late tick / double interrupt must NOT fire a second ending (idempotent).
		rn.tick_fuse(9999)
		rn.use_interrupt_interactable()
		_rm().run_ended.disconnect(cb)
		EG.ending_reached.disconnect(scb)
		_ok(int(count["n"]) == 1, "[%s] end_run fires EXACTLY once (no softlock, no double-end)" % path)
		_ok(count["reason"] == "win" or count["reason"] == "lose", "[%s] the ending is a win or lose" % path)
		# GAP-2.11 (the SCREEN half): the ending SCREEN was raised exactly once, with the climax
		# outcome — every outcome reaches a screen, no softlock, no duplicate overlay.
		_ok(int(screen["n"]) == 1, "[%s] the ending SCREEN is raised exactly once (GAP-2.11)" % path)
		var expected_outcome := "descent_complete" if path == "lose" else ("avatar_slain" if path == "avatar" else "descent_stopped")
		_ok(String(screen["outcome"]) == expected_outcome, "[%s] the screen shows the climax outcome '%s'" % [path, expected_outcome])
		_ok(not _rm().run_active(), "[%s] the run is ended (title handoff is next)" % path)
		# Return-to-Title bookkeeping: end_run itself does NOT count a run (win/lose is a bare pass);
		# the count advances when the player starts the NEXT run from the title. Assert that seam
		# concretely — a post-ending start_run bumps meta by EXACTLY one (not the trivially-true >=).
		var after_end := int(_rm().meta_runs_played())
		_ok(after_end == runs_before, "[%s] the ending itself does not double-count the run" % path)
		_rm().start_run()   # the title's "New Run" after the climax
		var after_restart := int(_rm().meta_runs_played())
		_ok(after_restart == runs_before + 1, "[%s] the next run from title bumps meta by exactly one" % path)

# (f) determinism: the climax setup for a fixed run-seed is identical.
func _test_determinism_fixed_seed() -> void:
	print("[determinism: a fixed run-seed yields an identical climax setup]")
	var a := _setup_signature(4242, true)
	var b := _setup_signature(4242, true)
	_ok(a == b, "the same seed yields the same which-door/relocation/defender setup")
	var c := _setup_signature(9999, true)
	_ok(a != c, "a different seed yields a different setup (the seed actually drives it)")

func _setup_signature(seed_val: int, tipped: bool) -> String:
	var rn := _fresh()
	rn.set_tipped(tipped)
	rn.force_assault(true, seed_val)
	return "%s|%d|%s" % [rn.site_room(), rn.defender_count(), str(rn.relocated())]
