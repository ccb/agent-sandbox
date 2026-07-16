extends SceneTree
## M28 — the HERMIT package: the SECOND playable pathway + the old_neil adversary (direction v2 §6).
## Standalone headless harness. Run: godot --headless --path tingen -s tests/test_hermit_pathway.gd
## Also folded into the main suite (run_tests.gd `_test_hermit_pathway`) via the SAME run_all() entry.
##
## The Hermit is a REAL second build: selecting it gives a DISTINCT star/ritual base kit (not the
## Hunter revolver kit), routed through the SAME per-form kit seam (AbilityDB.kit_for) + the pathway-
## agnostic Progression spine — no NPC/id branch. old_neil is its Seq-9 prey: a hidden Hermit-pathway
## Beyonder who lost control to the Hidden Sage, a two-phase combat_form (neil_human -> neil_monster),
## a distinct kit, a lead that routes to him, and a signature deed. The advance loop closes exactly like
## the Hunter's (down the same-pathway prey -> hermit_characteristic drop -> acting rite -> advance).
##
## Covers the DELIVER acceptance (TDD):
##  (a) selecting the Hermit pathway gives the Hermit base kit (not the Hunter kit); Hunter still Hunter
##  (b) the Hermit advance loop: down old_neil -> hermit_characteristic drop (drop_for_pathway) ->
##      acting deed -> advance Seq 9->8->7, the Hermit ladder arts unlock on the player's kit
##  (c) old_neil is a real two-phase adversary (pathway:hermit, human->monster transform, distinct kit,
##      a lead routing to him, a deed granting a clue)
##  (e) a first WIN unlocks hermit + the next run can pick+play it (Fool stays a future stub)

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_hermit_pathway: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_unlock_hermit(root)   # the first-win unlock, so the pathway is selectable for (a)/(b)
	_a_pathway_base_kit_differs(c, root)
	_b_hermit_advance_loop(c, root)
	_c_old_neil_two_phase_adversary(c, root)
	_e_first_win_unlocks_hermit(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
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

## Drive the lightweight first-win meta unlock (end_run('win', descent_stopped)) so hermit is a
## selectable pathway. Mirrors the M27 unlock seam; no full RitualNight climax needed.
static func _unlock_hermit(root: Node) -> void:
	var RM: Object = root.get_node("/root/RunManager")
	RM.reset_meta()
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()

# (a) --------------------------------------------------------------------------------------------
static func _a_pathway_base_kit_differs(c: Dictionary, root: Node) -> void:
	print("[hermit (a): selecting the Hermit pathway gives the Hermit base kit; Hunter still gives the Hunter kit]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var DB: Object = root.get_node("/root/AbilityDB")
	RM.start_run()
	AG.rebuild()
	# Hunter (the slice default) keeps its EXACT revolver kit — the DEFAULT base is unchanged.
	P.select_pathway("hunter")
	var hunter_kit: Array = DB.kit_for("player")
	_check(c, hunter_kit.has("revolver_shot") and hunter_kit.has("pistol_whip"),
		"Hunter base kit is the revolver kit (revolver_shot + pistol_whip): %s" % str(hunter_kit))
	_check(c, not hunter_kit.has("star_brand"),
		"the Hunter kit does NOT carry a Hermit art (star_brand absent)")
	# Selecting Hermit swaps the BASE kit through the same seam (Progression.pathway -> kit_for('player')).
	_check(c, P.select_pathway("hermit") == "hermit", "the Hermit pathway is selectable (unlocked)")
	var hermit_kit: Array = DB.kit_for("player")
	_check(c, hermit_kit.has("star_brand") and hermit_kit.has("ward_circle") and hermit_kit.has("astral_sight"),
		"the Hermit base kit is the star/ritual kit (star_brand + ward_circle + astral_sight): %s" % str(hermit_kit))
	_check(c, not hermit_kit.has("revolver_shot") and not hermit_kit.has("paper_charm"),
		"the Hermit kit is DISTINCT — no revolver_shot, no paper_charm (not the Hunter kit)")
	# The two kits actually differ (the whole point of a second build).
	_check(c, hunter_kit != hermit_kit, "the Hunter and Hermit base kits DIFFER (a real second build)")

# (b) --------------------------------------------------------------------------------------------
static func _b_hermit_advance_loop(c: Dictionary, root: Node) -> void:
	print("[hermit (b): down old_neil -> hermit_characteristic drop -> acting rite -> advance 9->8->7, ladder arts unlock]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var M: Object = root.get_node("/root/Meters")
	var DB: Object = root.get_node("/root/AbilityDB")
	var EB: Object = root.get_node("/root/EventBus")
	var RI: Object = root.get_node("/root/RoomItems")
	RM.start_run("hermit")
	AG.rebuild()
	P.select_pathway("hermit")
	_check(c, P.pathway() == "hermit" and P.sequence() == 9, "a Hermit run starts Hermit · Seq 9")
	# The pathway-agnostic spine keys the fuel item + drop off the pathway string, no id branch.
	_check(c, P.characteristic_item() == "hermit_characteristic",
		"the Hermit's advance fuel is hermit_characteristic (pathway-agnostic characteristic_item)")
	_check(c, P.drop_for_pathway("hermit") == "hermit_characteristic",
		"drop_for_pathway('hermit') -> hermit_characteristic (pathway-driven, not id-driven)")
	_check(c, P.acting_deed_id() == "hermit_act_rite",
		"the Hermit's acting ritual is the hermit_act_rite deed (pathway-dependent)")
	_check(c, bool(P.perform_acting_deed().get("ok", false)),
		"the Hermit acting rite performs cleanly through DeedRunner (the digestion step)")
	# Down old_neil (the real def, pathway is DATA) -> the pathway-driven drop lands hermit_characteristic.
	var foe: Object = AG.get_agent("old_neil")
	_check(c, foe != null and String(foe.pathway) == "hermit",
		"old_neil is in the live roster carrying pathway:hermit (hydrated from data)")
	if foe == null:
		return
	foe.room = "hermit_drop"
	foe.position = Vector2(120, 60)
	foe.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "old_neil"})
	_check(c, RI.count("hermit_drop", "hermit_characteristic") >= 1,
		"downing old_neil drops a hermit_characteristic where he fell (the harvest)")
	# Harvest old_neil's drop OFF THE GROUND (take_near removes it from the world — a REAL harvest of a
	# real kill, not a fabricated add_item) + acting rite -> advance 9 -> 8, Madness spikes, Seq-8 art unlocks.
	var proxy: Object = AG.ensure_player_proxy(Vector2(120, 60), "hermit_drop")
	var taken1: String = RI.take_near("hermit_drop", "hermit_characteristic", proxy.position, 999.0)
	if taken1 != "":
		proxy.add_item(taken1, 1)
	_check(c, proxy.item_count("hermit_characteristic") == 1,
		"the player HARVESTED old_neil's Characteristic off the ground (a real kill, not an injection)")
	P.mark_deed_done()
	M.set_meter("madness", 0.0)
	var res: Dictionary = P.advance()
	_check(c, bool(res.get("ok", false)) and P.sequence() == 8, "a full advance raises the Hermit rank 9 -> 8")
	_check(c, proxy.item_count("hermit_characteristic") == 0, "the advance consumes the hermit_characteristic")
	_check(c, absf(M.get_meter("madness") - 35.0) < 0.01, "the advance spikes Madness ~35 (digest)")
	_check(c, P.granted_arts().has("astral_chains") and DB.kit_for("player").has("astral_chains"),
		"Seq 8 grows the Hermit kit with astral_chains (reaching the player's usable arts)")
	# 8 -> 7: EARN the SECOND Characteristic from a REAL second kill — ledger_finch, the Seq-8 Hermit prey
	# (M30, replacing the old proxy.add_item injection). Down her, harvest her ground drop, digest, advance.
	var finch: Object = AG.get_agent("ledger_finch")
	_check(c, finch != null and String(finch.pathway) == "hermit" and String(finch.combat_form) == "finch_human",
		"ledger_finch is the SECOND Hermit prey (pathway:hermit, two-phase finch_human)")
	if finch != null:
		finch.room = "hermit_drop"
		finch.position = proxy.position
		finch.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "ledger_finch"})
	_check(c, RI.count("hermit_drop", "hermit_characteristic") >= 1,
		"downing ledger_finch drops the SECOND hermit_characteristic (a real second kill)")
	var taken2: String = RI.take_near("hermit_drop", "hermit_characteristic", proxy.position, 999.0)
	if taken2 != "":
		proxy.add_item(taken2, 1)
	P.mark_deed_done()
	P.advance()
	_check(c, P.sequence() == 7 and DB.kit_for("player").has("collapsing_star"),
		"Seq 7 grows the Hermit kit with collapsing_star (earned via a SECOND real kill, not injection)")
	# A fresh run resets the Hermit climb (no cross-run inheritance, §8).
	RM.start_run()
	AG.rebuild()
	_check(c, P.sequence() == 9 and P.granted_arts().is_empty(),
		"a new run resets the rank + wipes the granted arts (no cross-run inheritance)")

# (c) --------------------------------------------------------------------------------------------
static func _c_old_neil_two_phase_adversary(c: Dictionary, root: Node) -> void:
	print("[hermit (c): old_neil is a real two-phase Hermit adversary — forms, transform, distinct kit, lead, deed]")
	var DBn: Object = root.get_node("/root/NpcDB")
	var ADB: Object = root.get_node("/root/AbilityDB")
	var LS: Object = root.get_node("/root/LeadSystem")
	var DR: Object = root.get_node("/root/DeedRunner")
	var AG: Object = root.get_node("/root/Agents")
	var CD: Object = root.get_node("/root/ClueDB")
	var Clk: Object = root.get_node("/root/Clock")
	var RM: Object = root.get_node("/root/RunManager")
	# The NPC def: a hidden Hermit-pathway Beyonder opening in the human phase-1 form.
	var def: Dictionary = DBn.get_def("old_neil")
	_check(c, String(def.get("pathway", "")) == "hermit", "old_neil is tagged pathway:hermit")
	_check(c, String(def.get("combat_form", "")) == "neil_human", "old_neil opens in the human form neil_human")
	# The two-phase shape: neil_human carries a transform landing on neil_monster; the monster is monster:true.
	var human_kit: Array = ADB.kit_for("neil_human")
	var has_transform := false
	for aid in human_kit:
		var a: Dictionary = ADB.ability_for(String(aid))
		if String(a.get("class", "")) == "transform":
			for eff in (a.get("effects", []) as Array):
				if String((eff as Dictionary).get("form", "")) == "neil_monster":
					has_transform = true
	_check(c, has_transform, "neil_human's kit carries a transform that lands on neil_monster (the descent seam)")
	_check(c, ADB.is_monster_form("neil_monster"), "neil_monster is authored monster:true (feeds the Doom driver)")
	_check(c, ADB.is_hidden_beyonder_form("neil_human"), "neil_human is a hidden Beyonder (hidden_beyonder:true, the human phase)")
	# The human form has an hp_below -> cast(transform) reflex (the butcher/Wren descent seam).
	var hform: Dictionary = ADB.form_def("neil_human")
	var has_hp_below := false
	for row in (hform.get("reflexes", []) as Array):
		if String((row as Dictionary).get("when", {}).get("kind", "")) == "hp_below" \
				and String((row as Dictionary).get("do", {}).get("kind", "")) == "cast":
			var ca: Dictionary = ADB.ability_for(String((row as Dictionary).get("do", {}).get("ability", "")))
			if String(ca.get("class", "")) == "transform":
				has_hp_below = true
	_check(c, has_hp_below, "neil_human has an hp_below -> cast(transform) reflex")
	# A DISTINCT kit from every Hunter monster: no cleaver, no revolver — a Hermit star/ritual set.
	var mon_kit: Array = ADB.kit_for("neil_monster")
	_check(c, not mon_kit.has("cleaver_swipe") and not mon_kit.has("revolver_shot") and not mon_kit.has("incendiary_round"),
		"neil_monster's kit is DISTINCT from every Hunter monster (no cleaver/revolver/incendiary): %s" % str(mon_kit))
	var has_hermit_art := mon_kit.has("collapsing_star") or mon_kit.has("star_brand") or mon_kit.has("astral_chains")
	_check(c, has_hermit_art, "neil_monster fights with the Hermit star/ritual arts (a caster, not a brawler)")
	# The new forms + kit abilities load clean (validate_refs) — no dangling refs.
	var probe_forms := {"neil_human": ADB.form_def("neil_human"), "neil_monster": ADB.form_def("neil_monster")}
	var probe_ab := {}
	for form in ["neil_human", "neil_monster"]:
		for aid in ADB.kit_for(String(form)):
			probe_ab[String(aid)] = ADB.ability_for(String(aid))
	_check(c, ADB.validate_refs(probe_ab, probe_forms).is_empty(),
		"neil's forms + kit abilities pass validate_refs (no dangling refs)")
	# The lead routes to him: subject = old_neil, pathway:hermit, a real where_hint.
	RM.start_run("hermit")   # M30: prey leads are pathway-gated now — the neil lead slots in a Hermit run
	AG.rebuild()
	var lead: Dictionary = LS.get_lead("hermit_prey_neil")
	_check(c, not lead.is_empty(), "the hermit_prey_neil lead is slotted")
	_check(c, String(lead.get("pathway", "")) == "hermit", "the lead is tagged pathway:hermit (routes the advance)")
	_check(c, String(lead.get("where_hint", "")) != "" and String(lead.get("subject", "")) != "",
		"the lead has a real where_hint + names Old Neil as the subject")
	_check(c, String(lead.get("subject_key", "")) == "hermit", "the lead's subject_key is the hermit hook")
	# The signature deed grants its suspicion clue when the proxy witnesses it near the site.
	var deed: Dictionary = {}
	for d in DR.deeds:
		if String((d as Dictionary).get("id", "")) == "neil_star_rite":
			deed = d
	_check(c, not deed.is_empty() and String(deed.get("agent", "")) == "old_neil"
		and String(deed.get("clue", "")) == "old_neil_suspicious",
		"the neil_star_rite deed is authored (agent old_neil, grants old_neil_suspicious)")
	if deed.is_empty():
		return
	var wp_v: Array = deed.get("waypoint", [])
	var wp := Vector2(float(wp_v[0]), float(wp_v[1]))
	var room := String(deed.get("room", "city"))
	var foe: Object = AG.get_agent("old_neil")
	foe.room = room
	foe.position = wp
	foe.downed = false
	foe.vision_r = 600.0
	var proxy: Object = AG.ensure_player_proxy(wp, room)
	proxy.vision_r = 600.0
	CD.from_dict({})
	DR.reset()
	Clk.set_time(2, 1200)   # night phase
	Clk.minute_ticked.emit(Clk.minute_of_day, Clk.day)
	_check(c, CD.is_collected("old_neil_suspicious"),
		"the watching proxy earned old_neil_suspicious from the deed near the site")
	CD.from_dict({})
	AG.rebuild()

# (e) --------------------------------------------------------------------------------------------
static func _e_first_win_unlocks_hermit(c: Dictionary, root: Node) -> void:
	print("[hermit (e): a first WIN unlocks hermit + the next run can pick+play it; a loss does not]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var DB: Object = root.get_node("/root/AbilityDB")
	RM.reset_meta()
	_check(c, not RM.meta_unlocked_pathways().has("hermit"), "a fresh profile has the Hermit pathway LOCKED")
	_check(c, not P.available_pathways().has("hermit") and P.available_pathways().has("hunter"),
		"the pick reads the meta: Hunter available, Hermit locked")
	_check(c, P.select_pathway("hermit") == "hunter", "picking a locked Hermit falls back to Hunter")
	# A LOSS unlocks nothing.
	RM.start_run()
	RM.end_run("lose", {"outcome": "descent_complete"})
	_check(c, not RM.meta_unlocked_pathways().has("hermit"), "a LOSING run does not unlock Hermit")
	# The first WIN unlocks Hermit; it persists to the meta slot.
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()
	_check(c, RM.meta_unlocked_pathways().has("hermit"), "the first WIN unlocks the Hermit pathway")
	_check(c, not RM.meta_unlocked_pathways().has("fool"), "Fool stays a future stub (not unlocked by the first win)")
	# The next run can PICK and PLAY it (the pick honors the unlock + the kit is the Hermit build).
	RM.start_run()
	AG.rebuild()
	_check(c, P.available_pathways().has("hermit"), "after the win, Hermit is available at the pick")
	_check(c, P.select_pathway("hermit") == "hermit" and P.pathway() == "hermit",
		"the pick HONORS the unlock — the run's live pathway is Hermit")
	_check(c, DB.kit_for("player").has("star_brand"),
		"the next run PLAYS the Hermit build (its base kit is the star/ritual kit)")
	P.select_pathway("hunter")
