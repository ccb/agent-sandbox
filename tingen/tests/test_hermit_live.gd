extends SceneTree
## M30 — HERMIT **LIVE REACHABILITY**. Standalone headless harness; also folded into the main suite
## (run_tests.gd `_test_hermit_live`) via the SAME run_all() entry.
## Run: godot --headless --path tingen -s tests/test_hermit_live.gd
##
## M28 built the whole Hermit layer and it is green in unit tests, but a LIVE player could never
## select Hermit and could never finish its Seq ladder. This harness proves the three fixes are
## reachable from the REAL live seams (a green API-level test is NOT proof a player can get there):
##
##  G1  pathway-pick in the live New-Run flow: start_run(pathway) applies the chosen pathway and it
##      SURVIVES Progression.reset() (the reset used to hard-set hunter); and the BootController
##      New-Run flow presents a picker offering Hermit ONLY once the meta unlock is present, and
##      picking it starts a live Hermit run. Driven through RunManager.start_run + the mounted
##      BootController (Main.tscn) — NOT Progression.select_pathway() in isolation.
##  G2  the 9->8->7 ladder is feedable by TWO real kills: down old_neil (Seq-9) then ledger_finch
##      (Seq-8), each dropping a hermit_characteristic HARVESTED off the ground, each digested through
##      the SAME live Interactable digest verb the Hunter uses — the second Characteristic comes from
##      a REAL second kill, never proxy.add_item() of a literal.
##  bug#3  LeadSystem.slot_run pathway-gates prey leads: a hermit_prey_* lead never surfaces in a
##      Hunter run (its drop is dead weight to a Hunter) and vice-versa; pathway-neutral leads always
##      slot. This also proves >=2 same-pathway prey (neil + finch) are reachable in a Hermit run.

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = await run_all()
	print("\n=== test_hermit_live: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
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

## Drive the first-win meta unlock (end_run('win', descent_stopped)) so Hermit is a selectable pathway.
static func _unlock_hermit(RM: Object) -> void:
	RM.reset_meta()
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()

## B1 (retro): harvest via the LIVE walk-over pickup seam — mount a real Player body at `pos` and let
## PlayerCombat's physics-frame proximity gather collect whatever gatherable lies there (a naked
## RoomItems.take_near(...,999) call here is exactly how this harness used to MASK the missing live
## seam — G2 now FAILS if the walk-over gather is unwired). Frees the body before returning.
static func _walk_over(root: Node, pos: Vector2, frames: int = 8) -> void:
	var pbody: Node = (load("res://scenes/Player.tscn") as PackedScene).instantiate()
	root.add_child(pbody)
	(pbody as Node2D).global_position = pos
	for _i in frames:
		await root.get_tree().physics_frame
	pbody.free()

# (G1) ------------------------------------------------------------------------------------------
static func _g1_pathway_pick_reachable(c: Dictionary, root: Node) -> void:
	print("[G1: the chosen pathway threads through the REAL start_run + survives reset; the New-Run flow gates the picker on the unlock]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")

	# --- Part 1: the REAL start_run(pathway) applies the pick, and reset() no longer clobbers it. ---
	_unlock_hermit(RM)
	RM.start_run("hermit")
	AG.rebuild()
	_check(c, P.pathway() == "hermit",
		"start_run('hermit') -> the run's live pathway IS Hermit after the world is built (reset did NOT clobber it)")
	_check(c, P.sequence() == 9, "…and the chosen-pathway run still begins at a fresh Seq 9")
	# A no-arg start_run is byte-identical to the shipped Hunter run (the default seam).
	RM.start_run()
	AG.rebuild()
	_check(c, P.pathway() == "hunter", "a no-arg start_run defaults to the shipped Hunter build")
	# A LOCKED/unknown chosen pathway falls back to Hunter (the meta gate holds through start_run).
	RM.start_run("no_such_pathway")
	AG.rebuild()
	_check(c, P.pathway() == "hunter", "a locked/unknown chosen pathway falls back to Hunter through start_run")

	# --- Part 2: the BootController New-Run flow presents the picker only when >1 pathway is unlocked. ---
	var main: Node = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)
	await root.get_tree().process_frame
	_check(c, main.is_in_group("game_controller"), "the boot controller mounted as the live game_controller")

	# WITHOUT the unlock: only Hunter is available, so New Run starts it DIRECTLY (no needless picker).
	RM.reset_meta()
	_check(c, not P.available_pathways().has("hermit"),
		"a fresh profile: Hermit is NOT among the New-Run pathway options")
	main.start_new_run()
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, not main.pathway_picker_active(),
		"with one pathway unlocked the New-Run flow starts it directly (no picker)")
	_check(c, P.pathway() == "hunter", "…the sole-pathway New Run runs Hunter")
	_check(c, String(main.current_scene_path) == "res://scenes/IntroRoom.tscn",
		"…and wakes the player in the lodging")

	# Unlock Hermit -> a win returns to the title -> New Run now PRESENTS the picker.
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()
	_check(c, main.is_at_title(), "the win returned the boot controller to the title (New Run reachable again)")
	_check(c, P.available_pathways().has("hermit"),
		"after the first win, Hermit is among the New-Run pathway options")
	main.start_new_run()
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, main.pathway_picker_active(),
		"with >1 pathway unlocked the New-Run flow PRESENTS a pathway picker")
	_check(c, main.pathway_picker_options().has("hermit"),
		"…and the picker OFFERS the unlocked Hermit build")
	_check(c, main.pathway_picker_options().has("hunter"),
		"…alongside the always-available Hunter build")
	# Pick Hermit through the REAL button callback -> a live Hermit run in the lodging.
	main.choose_pathway("hermit")
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, P.pathway() == "hermit",
		"picking Hermit at the New-Run picker starts a LIVE Hermit run (the wire end-to-end)")
	_check(c, String(main.current_scene_path) == "res://scenes/IntroRoom.tscn",
		"…and wakes the player in the lodging on the Hermit run")
	main.queue_free()
	await root.get_tree().process_frame

# (bug#3) ---------------------------------------------------------------------------------------
static func _bug3_pathway_gated_leads(c: Dictionary, root: Node) -> void:
	print("[bug#3: slot_run pathway-gates prey leads — hermit prey never in a Hunter run, hunter prey never in a Hermit run]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var LS: Object = root.get_node("/root/LeadSystem")
	_unlock_hermit(RM)

	# --- a HUNTER run: hermit prey excluded; hunter prey + pathway-neutral leads present. ---
	RM.start_run("hunter")
	AG.rebuild()
	_check(c, P.pathway() == "hunter", "a Hunter run is live")
	_check(c, LS.get_lead("hermit_prey_neil").is_empty(),
		"a Hunter run does NOT slot hermit_prey_neil (the off-pathway drop is dead weight)")
	_check(c, LS.get_lead("hermit_prey_finch").is_empty(),
		"a Hunter run does NOT slot hermit_prey_finch")
	_check(c, not LS.get_lead("hunter_prey_kell_kin").is_empty(),
		"a Hunter run DOES slot the same-pathway hunter prey lead")
	_check(c, not LS.get_lead("butcher_iron_cross").is_empty(),
		"the pathway-neutral butcher opener always slots")

	# --- a HERMIT run: hunter prey excluded; BOTH hermit prey (neil + finch) + neutral present. ---
	RM.start_run("hermit")
	AG.rebuild()
	_check(c, P.pathway() == "hermit", "a Hermit run is live")
	_check(c, not LS.get_lead("hermit_prey_neil").is_empty(),
		"a Hermit run slots hermit_prey_neil (the Seq-9 prey)")
	_check(c, not LS.get_lead("hermit_prey_finch").is_empty(),
		"a Hermit run slots hermit_prey_finch (the Seq-8 prey) — TWO same-pathway prey are reachable")
	_check(c, LS.get_lead("hunter_prey_kell_kin").is_empty(),
		"a Hermit run does NOT slot the off-pathway hunter prey lead")
	_check(c, LS.get_lead("hunter_prey_mack_docks").is_empty(),
		"a Hermit run does NOT slot the off-pathway hunter Seq-8 prey lead")
	_check(c, not LS.get_lead("butcher_iron_cross").is_empty(),
		"the pathway-neutral butcher opener still slots in a Hermit run")

# (G2) ------------------------------------------------------------------------------------------
static func _g2_two_kill_ladder(c: Dictionary, root: Node) -> void:
	print("[G2: the 9->8->7 ladder feedable by TWO REAL kills — down old_neil then ledger_finch, harvest each, digest via the LIVE verb]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var DB: Object = root.get_node("/root/AbilityDB")
	var EB: Object = root.get_node("/root/EventBus")
	var RI: Object = root.get_node("/root/RoomItems")
	_unlock_hermit(RM)
	RM.start_run("hermit")
	AG.rebuild()
	_check(c, P.pathway() == "hermit" and P.sequence() == 9, "a live Hermit run begins Hermit · Seq 9")
	var proxy: Object = AG.ensure_player_proxy(Vector2(120, 60), "hermit_arena")

	# The LIVE digest station — the SAME Interactable verb (digest_advance flag) the Hunter uses.
	var digest: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	digest.digest_advance = true
	root.add_child(digest)
	await root.get_tree().process_frame

	# ---- KILL 1: old_neil (the Seq-9 prey) -> ground drop -> harvest -> live digest -> advance 9->8 ----
	var neil: Object = AG.get_agent("old_neil")
	_check(c, neil != null and String(neil.pathway) == "hermit",
		"old_neil stands in the roster carrying pathway:hermit (the Seq-9 prey)")
	if neil != null:
		neil.room = "hermit_arena"
		neil.position = proxy.position
		neil.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "old_neil"})
	_check(c, RI.count("hermit_arena", "hermit_characteristic") >= 1,
		"downing old_neil DROPS a hermit_characteristic where he fell (a real kill -> a real drop)")
	# Harvest off the ground through the LIVE walk-over seam: the pickup REMOVES it from the world
	# (proving it came from the kill) and lands it in inventory — never a fabricated add_item.
	await _walk_over(root, proxy.position)
	_check(c, RI.count("hermit_arena", "hermit_characteristic") == 0,
		"the player HARVESTED old_neil's Characteristic off the ground via the LIVE walk-over seam (the drop is gone from the world)")
	_check(c, proxy.item_count("hermit_characteristic") == 1, "…and it is now in the player's hands")
	digest._use()   # the LIVE digest/advance verb (acting rite + advance), the SAME verb the Hunter uses
	_check(c, P.sequence() == 8, "the LIVE digest verb advanced the Hermit ladder 9 -> 8")
	_check(c, proxy.item_count("hermit_characteristic") == 0, "…consuming the harvested Characteristic")
	_check(c, DB.kit_for("player").has("astral_chains"), "…and unlocking astral_chains on the player kit")

	# ---- KILL 2: ledger_finch (the Seq-8 prey) -> ground drop -> harvest -> live digest -> advance 8->7 ----
	var finch: Object = AG.get_agent("ledger_finch")
	_check(c, finch != null and String(finch.pathway) == "hermit",
		"ledger_finch stands in the roster carrying pathway:hermit (the SECOND real prey)")
	_check(c, finch != null and String(finch.combat_form) == "finch_human",
		"…in her two-phase human form finch_human")
	# finch is a REAL two-phase adversary with her OWN kit (mirrors old_neil): finch_human -> finch_descend
	# -> finch_monster, and the monster fights ink/word arts DISTINCT from neil_monster and every Hunter monster.
	var f_human_kit: Array = DB.kit_for("finch_human")
	var f_has_transform := false
	for aid in f_human_kit:
		var a: Dictionary = DB.ability_for(String(aid))
		if String(a.get("class", "")) == "transform":
			for eff in (a.get("effects", []) as Array):
				if String((eff as Dictionary).get("form", "")) == "finch_monster":
					f_has_transform = true
	_check(c, f_has_transform, "finch_human carries a transform that lands on finch_monster (the descent seam)")
	_check(c, DB.is_monster_form("finch_monster") and DB.is_hidden_beyonder_form("finch_human"),
		"finch_monster is monster:true and finch_human is a hidden Beyonder (the two-phase shape)")
	var f_mon_kit: Array = DB.kit_for("finch_monster")
	_check(c, not f_mon_kit.has("cleaver_swipe") and not f_mon_kit.has("revolver_shot") and not f_mon_kit.has("incendiary_round")
			and not f_mon_kit.has("collapsing_star") and not f_mon_kit.has("star_brand") and not f_mon_kit.has("astral_chains"),
		"finch_monster's kit is DISTINCT from every Hunter monster AND from neil_monster: %s" % str(f_mon_kit))
	if finch != null:
		finch.room = "hermit_arena"
		finch.position = proxy.position
		finch.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "ledger_finch"})
	_check(c, RI.count("hermit_arena", "hermit_characteristic") >= 1,
		"downing ledger_finch DROPS a SECOND hermit_characteristic (a REAL second kill — no injection)")
	await _walk_over(root, proxy.position)
	_check(c, RI.count("hermit_arena", "hermit_characteristic") == 0 and proxy.item_count("hermit_characteristic") == 1,
		"the player HARVESTED the second Characteristic off the ground via the LIVE walk-over seam")
	digest._use()   # the LIVE digest verb again — the ladder's second rung earned by a real kill
	_check(c, P.sequence() == 7,
		"the LIVE digest verb advanced the Hermit ladder 8 -> 7 via a SECOND real kill (the slice cap)")
	_check(c, DB.kit_for("player").has("collapsing_star"), "…unlocking collapsing_star at Seq 7")
	digest.free()
