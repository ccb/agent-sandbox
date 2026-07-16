extends SceneTree
## N5 — DEATH **LIVE REACHABILITY**. Standalone headless harness; also folded into the main suite
## (run_tests.gd `_test_death_live`) via the SAME run_all() entry.
## Run: godot --headless --path tingen -s tests/test_death_live.gd
##
## The M30 lesson, applied to the THIRD pathway from day one: a green API-level test is NOT proof a
## player can get there. This harness proves the Death build is reachable + completable from the
## REAL live seams:
##
##  G1  pathway-pick in the live New-Run flow: start_run('death') applies the chosen pathway and it
##      SURVIVES the world build; a no-arg start_run defaults to Hunter; a LOCKED id falls back to
##      Hunter. The PICKER GATE: with only hermit unlocked (one win) the picker does NOT offer death;
##      after the SECOND win the mounted BootController (Main.tscn) New-Run flow presents the picker
##      with hunter+hermit+death and choose_pathway('death') starts a live Death run in the lodging.
##      The picker is id-literal-free (BootController builds buttons from available_pathways()), so
##      the third option appearing is pure data flow.
##  bug#3  LeadSystem.slot_run pathway-gates prey leads: a Death run slots BOTH death leads and
##      NEITHER hunter nor hermit prey lead; a Hunter run and a Hermit run slot no death lead; the
##      pathway-neutral butcher opener slots everywhere.
##  G2  the 9->8->7 Death ladder closes by TWO REAL kills through the live seams — agent_downed ->
##      ground drop -> LIVE walk-over gather (a mounted Player body + physics frames, never
##      take_near(...,999) — the B1 lesson) -> LIVE Interactable digest verb -> Seq 8 (grave_hands)
##      -> repeat with brother_cassian -> Seq 7 (wailing_host).

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = await run_all()
	print("\n=== test_death_live: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd. Coroutine (mounts the
## boot controller + awaits frames), so callers must `await run_all()`.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	await _g1_pathway_pick_reachable(c, root)
	_bug3_pathway_gated_leads(c, root)
	await _g2_two_kill_ladder(c, root)
	# Leave a clean Hunter world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/Progression").select_pathway("hunter")
	return c

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

## One lightweight WIN through the real meta seam.
static func _win_once(RM: Object) -> void:
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()

## TWO wins so the WIN_UNLOCK_CHAIN reaches death (win 1 -> hermit, win 2 -> death).
static func _unlock_death(RM: Object) -> void:
	RM.reset_meta()
	_win_once(RM)
	_win_once(RM)

## B1 (retro): harvest via the LIVE walk-over pickup seam — mount a real Player body at `pos` and let
## PlayerCombat's physics-frame proximity gather collect whatever gatherable lies there. G2 FAILS if
## the walk-over gather is unwired. Frees the body before returning.
static func _walk_over(root: Node, pos: Vector2, frames: int = 8) -> void:
	var pbody: Node = (load("res://scenes/Player.tscn") as PackedScene).instantiate()
	root.add_child(pbody)
	(pbody as Node2D).global_position = pos
	for _i in frames:
		await root.get_tree().physics_frame
	pbody.free()

# (G1) ------------------------------------------------------------------------------------------
static func _g1_pathway_pick_reachable(c: Dictionary, root: Node) -> void:
	print("[G1: start_run('death') threads through the REAL seam; the New-Run picker gates death on the SECOND win]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")

	# --- Part 1: the REAL start_run(pathway) applies the pick + survives the world build. ---
	_unlock_death(RM)
	RM.start_run("death")
	AG.rebuild()
	_check(c, P.pathway() == "death",
		"start_run('death') -> the run's live pathway IS Death after the world is built")
	_check(c, P.sequence() == 9, "…and the chosen-pathway run still begins at a fresh Seq 9")
	# A no-arg start_run is byte-identical to the shipped Hunter run (the default seam).
	RM.start_run()
	AG.rebuild()
	_check(c, P.pathway() == "hunter", "a no-arg start_run defaults to the shipped Hunter build")
	# A LOCKED death (only ONE win on the profile) falls back to Hunter through start_run.
	RM.reset_meta()
	_win_once(RM)
	RM.start_run("death")
	AG.rebuild()
	_check(c, P.pathway() == "hunter", "a LOCKED Death (one win: hermit only) falls back to Hunter through start_run")

	# --- Part 2: the BootController New-Run picker OFFERS death only once the second win lands. ---
	var main: Node = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)
	await root.get_tree().process_frame
	_check(c, main.is_in_group("game_controller"), "the boot controller mounted as the live game_controller")

	# ONE win: the picker presents (hunter+hermit) but does NOT offer death — the drip is visible live.
	_check(c, not P.available_pathways().has("death"),
		"after only one win, Death is NOT among the New-Run pathway options")
	main.start_new_run()
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, main.pathway_picker_active(),
		"with hermit unlocked the New-Run flow presents the picker")
	_check(c, not main.pathway_picker_options().has("death"),
		"…and the picker does NOT offer the still-locked Death build")
	main.choose_pathway("hunter")   # dismiss through the real button so the flow completes
	await root.get_tree().process_frame
	await root.get_tree().process_frame

	# The SECOND win: death joins the options; the picker offers all three; picking it goes live.
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()
	_check(c, main.is_at_title(), "the win returned the boot controller to the title (New Run reachable again)")
	_check(c, P.available_pathways().has("death"),
		"after the SECOND win, Death is among the New-Run pathway options")
	main.start_new_run()
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, main.pathway_picker_active(),
		"with three pathways unlocked the New-Run flow PRESENTS the pathway picker")
	_check(c, main.pathway_picker_options().has("death"),
		"…and the picker OFFERS the unlocked Death build")
	_check(c, main.pathway_picker_options().has("hunter") and main.pathway_picker_options().has("hermit"),
		"…alongside the Hunter and Hermit builds (all three options)")
	# Pick Death through the REAL button callback -> a live Death run in the lodging.
	main.choose_pathway("death")
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, P.pathway() == "death",
		"picking Death at the New-Run picker starts a LIVE Death run (the wire end-to-end)")
	_check(c, String(main.current_scene_path) == "res://scenes/IntroRoom.tscn",
		"…and wakes the player in the lodging on the Death run")
	main.queue_free()
	await root.get_tree().process_frame

# (bug#3) ---------------------------------------------------------------------------------------
static func _bug3_pathway_gated_leads(c: Dictionary, root: Node) -> void:
	print("[bug#3: slot_run pathway-gates prey leads — death prey only in a Death run, never elsewhere]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var LS: Object = root.get_node("/root/LeadSystem")
	_unlock_death(RM)

	# --- a DEATH run: BOTH death prey slot; hunter + hermit prey excluded; the neutral opener present. ---
	RM.start_run("death")
	AG.rebuild()
	_check(c, P.pathway() == "death", "a Death run is live")
	_check(c, not LS.get_lead("death_prey_auber").is_empty(),
		"a Death run slots death_prey_auber (the Seq-9 prey)")
	_check(c, not LS.get_lead("death_prey_cassian").is_empty(),
		"a Death run slots death_prey_cassian (the Seq-8 prey) — TWO same-pathway prey are reachable")
	_check(c, LS.get_lead("hunter_prey_kell_kin").is_empty(),
		"a Death run does NOT slot the off-pathway hunter prey lead")
	_check(c, LS.get_lead("hermit_prey_neil").is_empty(),
		"a Death run does NOT slot the off-pathway hermit prey lead")
	_check(c, not LS.get_lead("butcher_iron_cross").is_empty(),
		"the pathway-neutral butcher opener still slots in a Death run")

	# --- a HUNTER run and a HERMIT run: no death lead ever surfaces (its drop is dead weight). ---
	RM.start_run("hunter")
	AG.rebuild()
	_check(c, LS.get_lead("death_prey_auber").is_empty() and LS.get_lead("death_prey_cassian").is_empty(),
		"a Hunter run slots NO death prey lead")
	RM.start_run("hermit")
	AG.rebuild()
	_check(c, LS.get_lead("death_prey_auber").is_empty() and LS.get_lead("death_prey_cassian").is_empty(),
		"a Hermit run slots NO death prey lead")

# (G2) ------------------------------------------------------------------------------------------
static func _g2_two_kill_ladder(c: Dictionary, root: Node) -> void:
	print("[G2: the 9->8->7 Death ladder feedable by TWO REAL kills — down auber then cassian, harvest each via the LIVE walk-over, digest via the LIVE verb]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var DB: Object = root.get_node("/root/AbilityDB")
	var EB: Object = root.get_node("/root/EventBus")
	var RI: Object = root.get_node("/root/RoomItems")
	_unlock_death(RM)
	RM.start_run("death")
	AG.rebuild()
	_check(c, P.pathway() == "death" and P.sequence() == 9, "a live Death run begins Death · Seq 9")
	var proxy: Object = AG.ensure_player_proxy(Vector2(120, 60), "death_arena")

	# The LIVE digest station — the SAME Interactable verb (digest_advance flag) every pathway uses.
	var digest: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	digest.digest_advance = true
	root.add_child(digest)
	await root.get_tree().process_frame

	# ---- KILL 1: sister_auber (the Seq-9 prey) -> ground drop -> live harvest -> live digest -> 9->8 ----
	var auber: Object = AG.get_agent("sister_auber")
	_check(c, auber != null and String(auber.pathway) == "death",
		"sister_auber stands in the roster carrying pathway:death (the Seq-9 prey)")
	if auber != null:
		auber.room = "death_arena"
		auber.position = proxy.position
		auber.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "sister_auber"})
	_check(c, RI.count("death_arena", "death_characteristic") >= 1,
		"downing sister_auber DROPS a death_characteristic where she fell (a real kill -> a real drop)")
	# Harvest off the ground through the LIVE walk-over seam: the pickup REMOVES it from the world
	# (proving it came from the kill) and lands it in inventory — never a fabricated add_item.
	await _walk_over(root, proxy.position)
	_check(c, RI.count("death_arena", "death_characteristic") == 0,
		"the player HARVESTED auber's Characteristic off the ground via the LIVE walk-over seam (the drop is gone from the world)")
	_check(c, proxy.item_count("death_characteristic") == 1, "…and it is now in the player's hands")
	digest._use()   # the LIVE digest/advance verb (acting rite + advance), the SAME verb every pathway uses
	_check(c, P.sequence() == 8, "the LIVE digest verb advanced the Death ladder 9 -> 8 (Gravedigger)")
	_check(c, proxy.item_count("death_characteristic") == 0, "…consuming the harvested Characteristic")
	_check(c, DB.kit_for("player").has("grave_hands"), "…and unlocking grave_hands on the player kit")

	# ---- KILL 2: brother_cassian (the Seq-8 prey) -> ground drop -> live harvest -> live digest -> 8->7 ----
	var cassian: Object = AG.get_agent("brother_cassian")
	_check(c, cassian != null and String(cassian.pathway) == "death",
		"brother_cassian stands in the roster carrying pathway:death (the SECOND real prey)")
	_check(c, cassian != null and String(cassian.combat_form) == "cassian_human",
		"…in his two-phase human form cassian_human")
	if cassian != null:
		cassian.room = "death_arena"
		cassian.position = proxy.position
		cassian.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "brother_cassian"})
	_check(c, RI.count("death_arena", "death_characteristic") >= 1,
		"downing brother_cassian DROPS a SECOND death_characteristic (a REAL second kill — no injection)")
	await _walk_over(root, proxy.position)
	_check(c, RI.count("death_arena", "death_characteristic") == 0 and proxy.item_count("death_characteristic") == 1,
		"the player HARVESTED the second Characteristic off the ground via the LIVE walk-over seam")
	digest._use()   # the LIVE digest verb again — the ladder's second rung earned by a real kill
	_check(c, P.sequence() == 7,
		"the LIVE digest verb advanced the Death ladder 8 -> 7 via a SECOND real kill (the slice cap)")
	_check(c, DB.kit_for("player").has("wailing_host"), "…unlocking wailing_host at Seq 7 (Spirit Medium)")
	digest.free()
