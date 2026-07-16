extends SceneTree
## N3 — CONTINUE IS A FIRST-CLASS RESUME (B-F1 / B-F2 / B-F5). The single-process half of the
## cross-session Continue proof: a nightly save -> a simulated FRESH BOOT (RunManager's session
## state forced back to its boot defaults + every world subsystem scrubbed through its own reset
## seam, so the load must do ALL the restoring work) -> the REAL BootController.continue_run().
## The true two-process case (fresh autoloads, a real process boundary) is tests/continue_probe.sh.
##
## Run:  godot --headless --path tingen -s tests/test_continue_resume.gd
## Also folded into the main suite (run_tests.gd `_test_continue_resume`) via the SAME run_all().
##
## The pins:
##   R1 [B-F2] the disk save carries the RUN SESSION: a run_manager block with the day, the live
##      flag, the checkpoint day, the ritual latch, and the run knowledge ledger.
##   R2 [B-F1] after a cold boot, the REAL Continue resumes a FIRST-CLASS run: run_active TRUE,
##      day correct, the in-memory checkpoint rebuilt, knowledge restored, pause eligible, codex
##      recording live, nightly checkpoints continuing, Ritual Night able to arm and fire.
##   R3 [B-F5] a full run-end INVALIDATES the save: has_save()/has_continue() go false and the
##      title's Continue button greys out — no ghost resume after a win/lose/final death.
##   R4 the meta payoff is LATCHED: end_run reached twice for one run pays/unlocks EXACTLY once.
##   R5 (rider) the pathway picker offers a way BACK — cancel returns to the title, no run started.
##   R6 (rider) the codex copy table authors pathway:hermit and ending:player_downed (no generic-
##      template fallback for facts every profile can reach).

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = await run_all()
	print("\n=== test_continue_resume: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd. Coroutine (mounts the
## real boot controller + awaits frames), so callers must `await run_all()`.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	var main: Node = await _r1_r2_r3_continue_cycle(c, root)
	_r4_payoff_latched(c, root)
	await _r5_picker_cancel(c, root, main)
	_r6_codex_copy_authored(c)
	# Teardown + leave a clean Hunter world for whatever runs next in the shared suite (the
	# test_death_save_load convention).
	if main != null and is_instance_valid(main):
		main.queue_free()
		await root.get_tree().process_frame
	root.get_node("/root/RunManager").start_run()
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

static func _find_button(node: Node, name_: String) -> Button:
	if node is Button and node.name == name_:
		return node
	for ch in node.get_children():
		var b := _find_button(ch, name_)
		if b != null:
			return b
	return null

# --- R1 + R2 + R3: the whole Continue cycle ------------------------------------------------------
static func _r1_r2_r3_continue_cycle(c: Dictionary, root: Node) -> Node:
	print("[R1/R2/R3: nightly save -> cold boot -> REAL Continue -> first-class resume -> run end invalidates the save]")
	var RM: Node = root.get_node("/root/RunManager")
	var SM: Node = root.get_node("/root/SaveManager")
	var CL: Node = root.get_node("/root/Clock")
	var M: Node = root.get_node("/root/Meters")
	var P: Node = root.get_node("/root/Progression")
	var EB: Node = root.get_node("/root/EventBus")
	RM.reset_meta()

	# --- the "first sitting": the REAL boot flow — New Run, learn a fact, rest to day 2 --------
	# (Main.tscn mounted FIRST so the nightly save records the live scene/player placement.)
	var main: Node = (load("res://scenes/Main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	main.start_new_run()
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	EB.emit_event("agent_downed", {"target": "bram_kell"})   # the REAL codex ear
	_check(c, (RM._run_knowledge as Dictionary).has("adversary:butcher_human"),
		"R1 setup: the live run learned adversary:butcher_human")
	var rest: Dictionary = RM.rest_until_morning()
	_check(c, bool(rest.get("ok", false)) and RM.current_day() == 2 and SM.has_save(),
		"R1 setup: rest -> day 2, nightly checkpoint mirrored to the disk save")

	# --- R1 [B-F2]: the save payload carries the run session -----------------------------------
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(String(SM.save_path)))
	var data: Dictionary = parsed if parsed is Dictionary else {}
	var blk: Variant = data.get("run_manager")
	_check(c, blk is Dictionary, "R1 [B-F2]: the save payload has a run_manager block")
	if blk is Dictionary:
		var b: Dictionary = blk
		_check(c, int(b.get("day", -1)) == 2, "R1 [B-F2]: block carries day 2")
		_check(c, bool(b.get("run_active", false)), "R1 [B-F2]: block carries run_active=true")
		_check(c, int(b.get("checkpoint_day", -1)) == 2, "R1 [B-F2]: block carries checkpoint_day 2")
		_check(c, not bool(b.get("ritual_night", true)), "R1 [B-F2]: block carries ritual_night=false")
		var kn: Variant = b.get("knowledge", [])
		_check(c, kn is Array and (kn as Array).has("adversary:butcher_human"),
			"R1 [B-F2]: block carries the run knowledge ledger")

	# --- the COLD BOOT: back to the title; force the session to boot defaults; scrub the world --
	# (As far as one process honestly can — the true fresh-autoload case is continue_probe.sh.)
	main.return_to_title()
	await root.get_tree().process_frame
	RM._run_active = false
	RM._current_day = 1
	RM._checkpoint = {}
	RM._checkpoint_day = 0
	RM._ritual_night = false
	RM._run_knowledge = {}
	CL.set_time(1, 480)
	M.reset()
	P.reset()
	root.get_node("/root/LeadSystem").reset()
	root.get_node("/root/Inventory").clear()
	# A fresh process has NO ending overlay mounted and an unpaused tree — but a pollute-y earlier
	# suite test may have left one latched (pause eligibility reads EndGame.has_overlay). Scrub it
	# through EndGame's own seams, part of the honest cold-boot simulation.
	var EG: Node = root.get_node_or_null("/root/EndGame")
	if EG != null:
		if EG.has_method("dismiss"):
			EG.dismiss()
		if EG.has_method("rearm"):
			EG.rearm()
	_check(c, not bool(RM.run_active()) and RM.current_day() == 1,
		"R2 setup: cold-boot state (run inactive, day 1) before Continue")

	# --- R2 [B-F1]: the REAL BootController Continue is a first-class resume --------------------
	_check(c, bool(main.is_at_title()) and bool(main.has_continue()),
		"R2: boot lands at the title with Continue offered")
	main.continue_run()
	for i in 8:
		await root.get_tree().process_frame
	_check(c, bool(RM.run_active()), "R2 [B-F1]: run_active TRUE after Continue")
	_check(c, RM.current_day() == 2, "R2 [B-F1]: day counter resumed at 2 (got %d)" % RM.current_day())
	_check(c, int(CL.day) == 2, "R2: Clock day 2 restored")
	_check(c, String(main.current_scene_path) == String(RM.LODGING_SCENE),
		"R2: resumed into the checkpoint's lodging scene")
	_check(c, String(P.pathway()) == "hunter" and int(P.sequence()) == 9,
		"R2: pathway/sequence resumed (hunter Seq 9)")
	_check(c, bool(RM.has_checkpoint()) and RM.checkpoint_day() == 2,
		"R2 [B-F1]: the in-memory checkpoint rebuilt from the save (day 2)")
	_check(c, (RM._run_knowledge as Dictionary).has("adversary:butcher_human"),
		"R2 [B-F2]: the run knowledge ledger survived the cold boot")
	var PM: Node = root.get_node_or_null("/root/PauseMenu")
	if PM != null:
		PM.open()
		_check(c, bool(PM.is_open()), "R2 [B-F1]: pause menu opens during the resumed run")
		PM.resume()
	else:
		_check(c, false, "R2: PauseMenu autoload present")
	# A death BETWEEN the resume and the next nightly checkpoint must restore to the REBUILT
	# checkpoint (the resumed morning) — the riskiest first-class-resume window: _restore() runs
	# against a checkpoint reconstructed from the disk payload, not one _snapshot() ever built.
	var doom_before := float(M.get_meter("doom"))
	M.adjust("doom", 7.0)
	RM.end_run("death")
	await root.get_tree().process_frame
	_check(c, bool(RM.run_active()) and RM.current_day() == 2
		and absf(float(M.get_meter("doom")) - doom_before) < 0.01,
		"R2 [B-F1]: a post-resume death restores to the REBUILT checkpoint (run live, day 2, meters back)")
	EB.emit_event("agent_downed", {"target": "sable_wren"})
	_check(c, (RM._run_knowledge as Dictionary).has("adversary:wren_human"),
		"R2 [B-F1]: codex recording LIVE after resume (fresh downed Beyonder recorded)")
	var rest2: Dictionary = RM.rest_until_morning()
	_check(c, bool(rest2.get("ok", false)) and RM.current_day() == 3 and RM.checkpoint_day() == 3,
		"R2 [B-F1]: nightly checkpoints CONTINUE on the resumed run (rest -> day 3 checkpoint)")
	M.set_meter("doom", 100.0)
	var RN: Node = root.get_node("/root/RitualNight")
	_check(c, bool(RM.ritual_night_reached()) and bool(RN.active()),
		"R2 [B-F1]: Ritual Night ARMS AND FIRES on the resumed run (Doom 100 -> staged climax)")

	# --- R3 [B-F5]: a full run-end invalidates the save — no ghost Continue ---------------------
	RM.end_run("lose")
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, not SM.has_save(), "R3 [B-F5]: the save slot is INVALIDATED on run end")
	_check(c, not bool(main.has_continue()), "R3 [B-F5]: has_continue() false after the run ends")
	var cont_btn := _find_button(main, "ContinueButton")
	_check(c, cont_btn != null and cont_btn.disabled,
		"R3 [B-F5]: the title Continue button greys out (no ghost resume)")
	return main

# --- R4: the meta payoff latches — exactly once per run ------------------------------------------
static func _r4_payoff_latched(c: Dictionary, root: Node) -> void:
	print("[R4: end_run reached twice for ONE run pays/unlocks the meta payoff exactly once]")
	var RM: Node = root.get_node("/root/RunManager")
	RM.reset_meta()
	RM.start_run()
	var cur0 := int(RM.meta_currency())
	RM.end_run("win", {"outcome": "descent_stopped"})
	var cur1 := int(RM.meta_currency())
	var unlocks1: Array = RM.meta_unlocked_pathways()
	_check(c, cur1 == cur0 + 1 and unlocks1 == ["hermit"],
		"R4: the first win pays 1 currency and unlocks hermit (the chain's first entry)")
	# The double path: a second end_run for the SAME run (e.g. a climax lose then an abandon quit).
	RM.end_run("win", {"outcome": "descent_stopped"})
	_check(c, int(RM.meta_currency()) == cur1,
		"R4: a second end_run pays NOTHING more (payoff latched)")
	_check(c, RM.meta_unlocked_pathways() == ["hermit"],
		"R4: a second end_run unlocks NOTHING more (no double chain-walk to death)")
	# A genuinely NEW run re-arms the latch — its own end pays again.
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	_check(c, int(RM.meta_currency()) == cur1 + 1 and RM.meta_unlocked_pathways() == ["hermit", "death"],
		"R4: the NEXT run's win pays again (latch re-armed by start_run)")

# --- R5 (rider): the pathway picker offers a way back --------------------------------------------
static func _r5_picker_cancel(c: Dictionary, root: Node, main: Node) -> void:
	print("[R5 rider: the New-Run pathway picker can be CANCELLED back to the title]")
	if main == null or not is_instance_valid(main):
		_check(c, false, "R5: boot controller still mounted")
		return
	var RM: Node = root.get_node("/root/RunManager")
	# R4 left hermit+death unlocked -> >1 pathway -> start_new_run presents the picker.
	main.return_to_title()
	await root.get_tree().process_frame
	main.start_new_run()
	await root.get_tree().process_frame
	_check(c, bool(main.pathway_picker_active()), "R5: the picker is up (multiple pathways unlocked)")
	var cancel_btn := _find_button(main, "CancelButton")
	_check(c, cancel_btn != null, "R5: the picker has a Cancel/Back button")
	if cancel_btn != null:
		cancel_btn.pressed.emit()
	elif main.has_method("cancel_pathway_picker"):
		main.cancel_pathway_picker()
	await root.get_tree().process_frame
	_check(c, not bool(main.pathway_picker_active()), "R5: cancel tears the picker down")
	_check(c, bool(main.is_at_title()), "R5: still at the title after cancel")
	_check(c, not bool(RM.run_active()), "R5: NO run was started by the cancelled pick")

# --- R6 (rider): the codex copy table has no reachable template-fallback gaps --------------------
static func _r6_codex_copy_authored(c: Dictionary) -> void:
	print("[R6 rider: codex copy authored for pathway:hermit and ending:player_downed]")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/scenario.json"))
	var codex: Dictionary = (parsed as Dictionary).get("codex", {}) if parsed is Dictionary else {}
	_check(c, codex.has("pathway:hermit"),
		"R6: pathway:hermit has an authored codex line (hunter/fool/death all do)")
	_check(c, codex.has("ending:player_downed"),
		"R6: ending:player_downed has an authored codex line (every profile can reach it)")
