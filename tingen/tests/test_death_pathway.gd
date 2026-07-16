extends SceneTree
## N5 — the DEATH package: the THIRD playable pathway + the sister_auber/brother_cassian adversaries
## (canon: Death 死神 pathway, low-Seq Corpse Collector 收尸人 line — Seq 9 Corpse Collector ->
## Seq 8 Gravedigger 掘墓人 -> Seq 7 Spirit Medium 通灵者). Standalone headless harness.
## Run: godot --headless --path tingen -s tests/test_death_pathway.gd
## Also folded into the main suite (run_tests.gd `_test_death_pathway`) via the SAME run_all() entry.
##
## The Death build mirrors the Hermit package byte-for-byte in SHAPE (M28): selecting it gives a
## DISTINCT censer/grave base kit (not the revolver, not the star/ritual kit), routed through the
## SAME per-form kit seam (AbilityDB.kit_for + _player_base_kits) and the pathway-agnostic
## Progression spine — no NPC/id branch anywhere. sister_auber is its Seq-9 prey and brother_cassian
## the Seq-8 meal: both hidden Death-pathway Beyonders with two-phase combat forms, distinct kits,
## leads that route to them, and signature deeds. Death reuses SPIRITUALITY (M31) — no new pool.
##
## Covers the N5 acceptance (TDD):
##  (a) selecting Death gives the Death base kit (censer_ember/grave_ring/grave_stillness);
##      the Hunter kit is unchanged and the Hermit kit is not the Death kit
##  (b) the Death advance loop: down sister_auber -> death_characteristic drop (drop_for_pathway) ->
##      acting rite (death_act_rite) -> advance Seq 9->8->7 via TWO real kills (auber then cassian),
##      the Death ladder arts (grave_hands, wailing_host) unlock on the player's kit
##  (c) BOTH prey are real two-phase adversaries (pathway:death, human->monster transform, kits
##      distinct from every Hunter AND Hermit art, validate_refs clean, deeds granting clues)
##  (e) the WIN-UNLOCK CHAIN: one win -> hermit only (the roguelite drip); TWO wins -> death
##      unlocked + selectable + kit live; a loss grants nothing; a third win walks off the chain end

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_death_pathway: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_unlock_death(root.get_node("/root/RunManager"))   # two wins, so the pathway is selectable for (a)/(b)
	_a_pathway_base_kit_differs(c, root)
	_b_death_advance_loop(c, root)
	_c_two_phase_adversaries(c, root)
	_e_win_chain_unlocks_death(c, root)
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

## One lightweight WIN through the real meta seam (end_run('win', descent_stopped) + reload).
static func _win_once(RM: Object) -> void:
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()

## Drive TWO wins so the WIN_UNLOCK_CHAIN reaches death (win 1 -> hermit, win 2 -> death).
static func _unlock_death(RM: Object) -> void:
	RM.reset_meta()
	_win_once(RM)
	_win_once(RM)

# (a) --------------------------------------------------------------------------------------------
static func _a_pathway_base_kit_differs(c: Dictionary, root: Node) -> void:
	print("[death (a): selecting the Death pathway gives the Death base kit; Hunter/Hermit kits unchanged]")
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
	_check(c, not hunter_kit.has("censer_ember"),
		"the Hunter kit does NOT carry a Death art (censer_ember absent)")
	# Selecting Death swaps the BASE kit through the same seam (Progression.pathway -> kit_for('player')).
	_check(c, P.select_pathway("death") == "death", "the Death pathway is selectable (unlocked by two wins)")
	var death_kit: Array = DB.kit_for("player")
	_check(c, death_kit.has("censer_ember") and death_kit.has("grave_ring") and death_kit.has("grave_stillness"),
		"the Death base kit is the censer/grave kit (censer_ember + grave_ring + grave_stillness): %s" % str(death_kit))
	_check(c, not death_kit.has("revolver_shot") and not death_kit.has("paper_charm"),
		"the Death kit is DISTINCT from the Hunter kit — no revolver_shot, no paper_charm")
	_check(c, not death_kit.has("star_brand") and not death_kit.has("ward_circle") and not death_kit.has("astral_sight"),
		"the Death kit is DISTINCT from the Hermit kit — no star_brand/ward_circle/astral_sight")
	# censer_ember LEADS the kit row, so the kit-aware primary resolves to it (the star_brand precedent).
	_check(c, death_kit.size() > 0 and String(death_kit[0]) == "censer_ember",
		"censer_ember leads the Death kit row (the kit-aware primary picks it first)")
	_check(c, hunter_kit != death_kit, "the Hunter and Death base kits DIFFER (a real third build)")

# (b) --------------------------------------------------------------------------------------------
static func _b_death_advance_loop(c: Dictionary, root: Node) -> void:
	print("[death (b): down sister_auber -> death_characteristic drop -> acting rite -> advance 9->8->7, ladder arts unlock]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var M: Object = root.get_node("/root/Meters")
	var DB: Object = root.get_node("/root/AbilityDB")
	var EB: Object = root.get_node("/root/EventBus")
	var RI: Object = root.get_node("/root/RoomItems")
	RM.start_run("death")
	AG.rebuild()
	P.select_pathway("death")
	_check(c, P.pathway() == "death" and P.sequence() == 9, "a Death run starts Death · Seq 9 (Corpse Collector)")
	# The pathway-agnostic spine keys the fuel item + drop off the pathway string, no id branch.
	_check(c, P.characteristic_item() == "death_characteristic",
		"the Death advance fuel is death_characteristic (pathway-agnostic characteristic_item)")
	_check(c, P.drop_for_pathway("death") == "death_characteristic",
		"drop_for_pathway('death') -> death_characteristic (pathway-driven, not id-driven)")
	_check(c, P.acting_deed_id() == "death_act_rite",
		"the Death acting ritual is the death_act_rite deed (pathway-dependent)")
	_check(c, bool(P.perform_acting_deed().get("ok", false)),
		"the corpse-collector's office performs cleanly through DeedRunner (the digestion step)")
	# Down sister_auber (the real def, pathway is DATA) -> the pathway-driven drop lands death_characteristic.
	var foe: Object = AG.get_agent("sister_auber")
	_check(c, foe != null and String(foe.pathway) == "death",
		"sister_auber is in the live roster carrying pathway:death (hydrated from data)")
	if foe == null:
		return
	foe.room = "death_drop"
	foe.position = Vector2(120, 60)
	foe.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "sister_auber"})
	_check(c, RI.count("death_drop", "death_characteristic") >= 1,
		"downing sister_auber drops a death_characteristic where she fell (the harvest)")
	# Harvest her drop OFF THE GROUND (take_near removes it from the world — a REAL harvest of a
	# real kill, not a fabricated add_item) + acting rite -> advance 9 -> 8, Madness spikes, Seq-8 art unlocks.
	var proxy: Object = AG.ensure_player_proxy(Vector2(120, 60), "death_drop")
	var taken1: String = RI.take_near("death_drop", "death_characteristic", proxy.position, 999.0)
	if taken1 != "":
		proxy.add_item(taken1, 1)
	_check(c, proxy.item_count("death_characteristic") == 1,
		"the player HARVESTED sister_auber's Characteristic off the ground (a real kill, not an injection)")
	P.mark_deed_done()
	M.set_meter("madness", 0.0)
	var res: Dictionary = P.advance()
	_check(c, bool(res.get("ok", false)) and P.sequence() == 8, "a full advance raises the Death rank 9 -> 8 (Gravedigger)")
	_check(c, proxy.item_count("death_characteristic") == 0, "the advance consumes the death_characteristic")
	_check(c, absf(M.get_meter("madness") - 35.0) < 0.01, "the advance spikes Madness ~35 (digest)")
	_check(c, P.granted_arts().has("grave_hands") and DB.kit_for("player").has("grave_hands"),
		"Seq 8 grows the Death kit with grave_hands (reaching the player's usable arts)")
	# 8 -> 7: EARN the SECOND Characteristic from a REAL second kill — brother_cassian, the Seq-8 Death
	# prey (the ledger_finch precedent). Down him, harvest his ground drop, digest, advance.
	var cassian: Object = AG.get_agent("brother_cassian")
	_check(c, cassian != null and String(cassian.pathway) == "death" and String(cassian.combat_form) == "cassian_human",
		"brother_cassian is the SECOND Death prey (pathway:death, two-phase cassian_human)")
	if cassian != null:
		cassian.room = "death_drop"
		cassian.position = proxy.position
		cassian.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": "brother_cassian"})
	_check(c, RI.count("death_drop", "death_characteristic") >= 1,
		"downing brother_cassian drops the SECOND death_characteristic (a real second kill)")
	var taken2: String = RI.take_near("death_drop", "death_characteristic", proxy.position, 999.0)
	if taken2 != "":
		proxy.add_item(taken2, 1)
	P.mark_deed_done()
	P.advance()
	_check(c, P.sequence() == 7 and DB.kit_for("player").has("wailing_host"),
		"Seq 7 (Spirit Medium) grows the Death kit with wailing_host (earned via a SECOND real kill)")
	# A fresh run resets the Death climb (no cross-run inheritance, §8).
	RM.start_run()
	AG.rebuild()
	_check(c, P.sequence() == 9 and P.granted_arts().is_empty(),
		"a new run resets the rank + wipes the granted arts (no cross-run inheritance)")

# (c) --------------------------------------------------------------------------------------------
static func _c_two_phase_adversaries(c: Dictionary, root: Node) -> void:
	print("[death (c): BOTH prey are real two-phase Death adversaries — forms, transforms, distinct kits, leads, deeds]")
	var DBn: Object = root.get_node("/root/NpcDB")
	var ADB: Object = root.get_node("/root/AbilityDB")
	var LS: Object = root.get_node("/root/LeadSystem")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")

	# The two-phase shape, checked for BOTH prey through the same data-driven probes (no id branch —
	# the harness only iterates authored strings).
	var shapes := [
		{"npc": "sister_auber", "human": "auber_human", "monster": "auber_monster", "descend": "auber_descend"},
		{"npc": "brother_cassian", "human": "cassian_human", "monster": "cassian_monster", "descend": "cassian_descend"},
	]
	for row_v in shapes:
		var row: Dictionary = row_v
		var npc := String(row["npc"])
		var human := String(row["human"])
		var monster := String(row["monster"])
		var def: Dictionary = DBn.get_def(npc)
		_check(c, String(def.get("pathway", "")) == "death", "%s is tagged pathway:death" % npc)
		_check(c, String(def.get("combat_form", "")) == human, "%s opens in the human form %s" % [npc, human])
		# The human form carries a transform landing on the monster; the monster is monster:true.
		var human_kit: Array = ADB.kit_for(human)
		var has_transform := false
		for aid in human_kit:
			var a: Dictionary = ADB.ability_for(String(aid))
			if String(a.get("class", "")) == "transform":
				for eff in (a.get("effects", []) as Array):
					if String((eff as Dictionary).get("form", "")) == monster:
						has_transform = true
		_check(c, has_transform, "%s's kit carries a transform that lands on %s (the descent seam)" % [human, monster])
		_check(c, ADB.is_monster_form(monster), "%s is authored monster:true (feeds the Doom driver)" % monster)
		_check(c, ADB.is_hidden_beyonder_form(human), "%s is a hidden Beyonder (hidden_beyonder:true, the human phase)" % human)
		# The human form has an hp_below -> cast(transform) reflex (the shared descent seam).
		var hform: Dictionary = ADB.form_def(human)
		var has_hp_below := false
		for rrow in (hform.get("reflexes", []) as Array):
			if String((rrow as Dictionary).get("when", {}).get("kind", "")) == "hp_below" \
					and String((rrow as Dictionary).get("do", {}).get("kind", "")) == "cast":
				var ca: Dictionary = ADB.ability_for(String((rrow as Dictionary).get("do", {}).get("ability", "")))
				if String(ca.get("class", "")) == "transform":
					has_hp_below = true
		_check(c, has_hp_below, "%s has an hp_below -> cast(transform) reflex" % human)
		# The monster kit is DISTINCT from every Hunter monster AND both Hermit monsters.
		var mon_kit: Array = ADB.kit_for(monster)
		var hunter_arts := ["cleaver_swipe", "revolver_shot", "incendiary_round", "hook_throw", "charge", "blood_frenzy"]
		var hermit_arts := ["star_brand", "collapsing_star", "astral_chains", "ward_circle", "ink_flood", "redacted_word", "finch_recite"]
		var clean := true
		for art in hunter_arts + hermit_arts:
			if mon_kit.has(art):
				clean = false
		_check(c, clean,
			"%s's kit is DISTINCT from every Hunter AND Hermit art: %s" % [monster, str(mon_kit)])
		# The new forms + kit abilities load clean (validate_refs) — no dangling refs.
		var probe_forms := {human: ADB.form_def(human), monster: ADB.form_def(monster)}
		var probe_ab := {}
		for form in [human, monster]:
			for aid in ADB.kit_for(String(form)):
				probe_ab[String(aid)] = ADB.ability_for(String(aid))
		_check(c, ADB.validate_refs(probe_ab, probe_forms).is_empty(),
			"%s's forms + kit abilities pass validate_refs (no dangling refs)" % npc)
	# The two Death monsters fight DIFFERENT kits (the finch-vs-neil precedent: no re-skins).
	var auber_kit: Array = ADB.kit_for("auber_monster")
	var cassian_kit: Array = ADB.kit_for("cassian_monster")
	var shared := false
	for aid in auber_kit:
		if cassian_kit.has(aid):
			shared = true
	_check(c, not auber_kit.is_empty() and not cassian_kit.is_empty() and not shared,
		"auber_monster and cassian_monster share NO art (the two Death prey are distinct hunts)")
	_check(c, auber_kit.has("wailing_host") and cassian_kit.has("choir_of_the_dead"),
		"the monsters fight the Death grave/spirit arts (wailing_host / choir_of_the_dead)")

	# The leads route to them: pathway:death, real where_hints, the Seq-8 lead gated after_advance.
	RM.start_run("death")   # prey leads are pathway-gated — the death leads slot in a Death run
	AG.rebuild()
	var lead_a: Dictionary = LS.get_lead("death_prey_auber")
	_check(c, not lead_a.is_empty(), "the death_prey_auber lead is slotted in a Death run")
	_check(c, String(lead_a.get("pathway", "")) == "death", "the auber lead is tagged pathway:death (routes the advance)")
	_check(c, String(lead_a.get("where_hint", "")) != "" and String(lead_a.get("subject", "")) != "",
		"the auber lead has a real where_hint + names Sister Auber as the subject")
	_check(c, String(lead_a.get("subject_key", "")) == "death", "the auber lead's subject_key is the death hook")

	# The signature deeds grant their suspicion clues via the vision-gated Stimulus drive, one prey
	# at a time (the neil_star_rite pattern: stage agent+proxy at the waypoint, night, minute tick).
	_deed_grants_clue(c, root, "auber_grave_office", "sister_auber", "sister_auber_suspicious")
	_deed_grants_clue(c, root, "cassian_crypt_requiem", "brother_cassian", "brother_cassian_suspicious")

## Stage `agent_id` + the player proxy at the deed's waypoint at NIGHT and prove the watching proxy
## earns the suspicion clue through the vision-gated Stimulus channel (the neil_star_rite pattern).
static func _deed_grants_clue(c: Dictionary, root: Node, deed_id: String, agent_id: String, clue_id: String) -> void:
	var DR: Object = root.get_node("/root/DeedRunner")
	var AG: Object = root.get_node("/root/Agents")
	var CD: Object = root.get_node("/root/ClueDB")
	var Clk: Object = root.get_node("/root/Clock")
	var deed: Dictionary = {}
	for d in DR.deeds:
		if String((d as Dictionary).get("id", "")) == deed_id:
			deed = d
	_check(c, not deed.is_empty() and String(deed.get("agent", "")) == agent_id
		and String(deed.get("clue", "")) == clue_id,
		"the %s deed is authored (agent %s, grants %s)" % [deed_id, agent_id, clue_id])
	if deed.is_empty():
		return
	var wp_v: Array = deed.get("waypoint", [])
	var wp := Vector2(float(wp_v[0]), float(wp_v[1]))
	var room := String(deed.get("room", "city"))
	var foe: Object = AG.get_agent(agent_id)
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
	_check(c, CD.is_collected(clue_id),
		"the watching proxy earned %s from the deed near the site" % clue_id)
	CD.from_dict({})
	AG.rebuild()

# (e) --------------------------------------------------------------------------------------------
static func _e_win_chain_unlocks_death(c: Dictionary, root: Node) -> void:
	print("[death (e): the WIN chain — win 1 unlocks hermit ONLY (the drip); win 2 unlocks death; losses/extra wins grant nothing]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var DB: Object = root.get_node("/root/AbilityDB")
	RM.reset_meta()
	_check(c, not RM.meta_unlocked_pathways().has("death"), "a fresh profile has the Death pathway LOCKED")
	_check(c, P.select_pathway("death") == "hunter", "picking a locked Death falls back to Hunter")
	# A LOSS unlocks nothing.
	RM.start_run()
	RM.end_run("lose", {"outcome": "descent_complete"})
	_check(c, RM.meta_unlocked_pathways().is_empty(), "a LOSING run unlocks nothing")
	# WIN #1 -> hermit only. Death stays locked — the roguelite drip (ONE unlock per win).
	_win_once(RM)
	_check(c, RM.meta_unlocked_pathways().has("hermit"), "win #1 unlocks the Hermit pathway (byte-identical to the pinned first-win behavior)")
	_check(c, not RM.meta_unlocked_pathways().has("death"),
		"win #1 does NOT unlock Death — one unlock per win (the drip)")
	# A loss BETWEEN wins grants nothing.
	RM.start_run()
	RM.end_run("lose", {"outcome": "descent_complete"})
	_check(c, not RM.meta_unlocked_pathways().has("death"), "a loss between wins does not advance the chain")
	# WIN #2 -> death. Selectable + the kit is live.
	_win_once(RM)
	_check(c, RM.meta_unlocked_pathways().has("death"), "win #2 unlocks the Death pathway (the chain's next entry)")
	_check(c, P.available_pathways().has("death"), "after the second win, Death is available at the pick")
	RM.start_run()
	AG.rebuild()
	_check(c, P.select_pathway("death") == "death" and P.pathway() == "death",
		"the pick HONORS the unlock — the run's live pathway is Death")
	_check(c, DB.kit_for("player").has("censer_ember"),
		"the next run PLAYS the Death build (its base kit is the censer/grave kit)")
	# WIN #3 walks off the chain end and grants NOTHING new.
	var owned_before: int = RM.meta_unlocked_pathways().size()
	_win_once(RM)
	_check(c, RM.meta_unlocked_pathways().size() == owned_before,
		"a third win walks off the chain end and unlocks nothing more")
	_check(c, (RM.meta_last_payoff().get("new_unlocks", []) as Array).is_empty(),
		"…and the third win's payoff reports no new unlock (new_unlocks empty)")
	P.select_pathway("hunter")
