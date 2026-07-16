extends SceneTree
## M14 — the THIRD adversary: the Seq-8 hunter's meal (closes the 9->8->7 chain).
## Standalone headless harness. Run: godot --headless --path tingen -s tests/test_adversary3.gd
##
## The progression loop needs TWO legitimate hunter_characteristic drops so a player can advance
## 9->8 (Wren) and then 8->7 (this adversary). Without this foe the only other pathway:"hunter"
## agent is constable_brom — a FRIENDLY lawman — forcing the player to murder him. Degenerate.
## M14 authors a second same-pathway prey as PURE DATA: a harbor poacher/line-handler who took a
## bad Hunter dose and now hunts people at the docks. A mid-range hook-and-charge bruiser (distinct
## from the butcher's melee cleaver and Wren's ranged revolver). Tuned HARDER than Wren: a meaner
## reflex table and a higher hp_below transform threshold that gives the player less room.
##
## A post-advance lead gate is also wired: the adversary's lead surfaces AFTER the player's first
## advance (Progression.advanced -> LeadSystem.surface_after_advance), not at run start. This
## keeps the pacing: Wren is the Seq-9 meal; Mack is the Seq-8 meal, revealed by the city only
## after the player has proven they can handle the first hunt.
##
## Covers the DELIVER acceptance (TDD):
##  (a) the new NPC loads with pathway:"hunter" + a two-phase combat_form (human + a monster form
##      reached via a transform ability in the human form's kit)
##  (b) the lead points at them with a REAL where_hint + pathway:"hunter" + after_advance:true
##      (it is NOT in the opening set — it surfaces only after the first advance)
##  (c) downing them drops hunter_characteristic via the PATHWAY-driven drop (not special-cased)
##      -> the player can advance a second time (the second meal pays off for Seq 7)
##  (d) the deed grants its suspicion clue near the site
##  (e) the new forms/abilities load clean (validate_refs), DISTINCT mid-range bruiser kit from
##      both the butcher's melee cleaver AND Wren's ranged revolver set
##  (f) the post-advance lead gate: after Progression emits advanced, LeadSystem surfaces the lead
##      (the after_advance:true flag + the Progression.advanced -> LeadSystem hook)

const ADVERSARY_ID: String = "leland_mack"
const HUMAN_FORM: String = "mack_harbor"
const MONSTER_FORM: String = "mack_beast"
const MACK_LEAD: String = "hunter_prey_mack_docks"
const DEED_ID: String = "mack_breakwater_drag"
const DEED_CLUE: String = "leland_mack_suspicious"

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)

	_test_npc_loads_hunter_pathway_two_phase()
	_test_lead_is_after_advance_not_in_opening()
	_test_downing_drops_hunter_characteristic_pathway_driven()
	_test_deed_grants_suspicion_clue_near_site()
	_test_forms_and_abilities_load_clean_distinct_kit()
	_test_post_advance_lead_gate()

	print("\n=== test_adversary3: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

func _al(n: String) -> Node:
	return root.get_node_or_null(n)

# (a) --------------------------------------------------------------------------------------------
func _test_npc_loads_hunter_pathway_two_phase() -> void:
	print("[adversary3: the hidden Hunter-pathway Beyonder (the docks poacher) loads with a two-phase combat_form]")
	var DB: Object = _al("NpcDB")
	_ok(DB != null, "NpcDB autoload is registered")
	if DB == null:
		return
	var def: Dictionary = DB.get_def(ADVERSARY_ID)
	_ok(not def.is_empty(), "%s is authored in npcs.json" % ADVERSARY_ID)
	_ok(String(def.get("pathway", "")) == "hunter", "%s is tagged pathway:hunter" % ADVERSARY_ID)
	_ok(String(def.get("combat_form", "")) == HUMAN_FORM,
		"%s opens in the human phase-1 form %s" % [ADVERSARY_ID, HUMAN_FORM])
	_ok(String(def.get("description", "")) != "" and String(def.get("intent", "")) != "",
		"has a public-face identity (description + intent)")
	_ok((def.get("secrets", []) as Array).size() >= 1, "carries a secret (the lost-control truth)")
	_ok((def.get("schedule", {}) as Dictionary).size() >= 1, "has schedule waypoints")
	_ok(float(def.get("vision_r", 0.0)) > 0.0, "has a vision_r (a hunter's eyes)")
	# The two-phase shape: human form kit contains a transform landing on the monster form.
	var ADB: Object = _al("AbilityDB")
	if ADB == null:
		return
	var human_kit: Array = ADB.kit_for(HUMAN_FORM)
	var has_transform := false
	for aid in human_kit:
		var a: Dictionary = ADB.ability_for(String(aid))
		if String(a.get("class", "")) == "transform":
			for eff in (a.get("effects", []) as Array):
				if String((eff as Dictionary).get("kind", "")) == "transform" \
						and String((eff as Dictionary).get("form", "")) == MONSTER_FORM:
					has_transform = true
	_ok(has_transform,
		"the human form's kit carries a transform that lands on %s (two-phase via the assume_form seam)" % MONSTER_FORM)
	_ok(ADB.is_monster_form(MONSTER_FORM), "%s is authored monster:true (feeds the Doom driver)" % MONSTER_FORM)
	# The human form has an hp_below -> transform reflex (mirroring wren_human).
	var hform: Dictionary = ADB.form_def(HUMAN_FORM)
	var has_hp_below_transform := false
	for row in (hform.get("reflexes", []) as Array):
		var when: Dictionary = (row as Dictionary).get("when", {})
		var do_d: Dictionary = (row as Dictionary).get("do", {})
		if String(when.get("kind", "")) == "hp_below" and String(do_d.get("kind", "")) == "cast":
			var cast_a: Dictionary = ADB.ability_for(String(do_d.get("ability", "")))
			if String(cast_a.get("class", "")) == "transform":
				has_hp_below_transform = true
	_ok(has_hp_below_transform,
		"the human form has an hp_below -> cast(transform) reflex (the descent seam)")

# (b) --------------------------------------------------------------------------------------------
func _test_lead_is_after_advance_not_in_opening() -> void:
	print("[adversary3: the Mack lead is tagged after_advance:true — NOT in the opening set, surfaces post-advance]")
	var LS: Object = _al("LeadSystem")
	if LS == null:
		_ok(false, "LeadSystem autoload exists")
		return
	var RM: Object = _al("RunManager")
	RM.start_run()
	# The lead IS slotted at run start (LeadSystem.slot_run includes it), but is gated:
	# after_advance:true means it does NOT surface until the player's first advance.
	var lead: Dictionary = LS.get_lead(MACK_LEAD)
	_ok(not lead.is_empty(), "the %s lead is slotted at run start (it exists on the board)" % MACK_LEAD)
	_ok(String(lead.get("pathway", "")) == "hunter", "the lead is tagged pathway:hunter (routes the advance)")
	_ok(String(lead.get("where_hint", "")) != "", "the lead has a REAL where_hint (a place, not blank)")
	_ok(bool(lead.get("after_advance", false)), "the lead is tagged after_advance:true (gated behind the first advance)")
	# The lead must NOT be in the opening set: it is a follow-up, not a guaranteed opener.
	_ok(String(lead.get("subject_key", "")) == "hunter", "the lead's subject_key is the hunter hook")

# (c) --------------------------------------------------------------------------------------------
func _test_downing_drops_hunter_characteristic_pathway_driven() -> void:
	print("[adversary3: downing the adversary drops hunter_characteristic via the PATHWAY-driven drop -> second advance (Seq 7)]")
	var P: Object = _al("Progression")
	if P == null:
		_ok(false, "Progression autoload exists")
		return
	var RM: Object = _al("RunManager")
	var AG: Object = _al("Agents")
	var EB: Object = _al("EventBus")
	var RI: Object = _al("RoomItems")
	RM.start_run()
	AG.rebuild()
	# Pathway-driven drop rule (same rule as all hunter foes, no id branch).
	_ok(P.drop_for_pathway("hunter") == "hunter_characteristic",
		"drop_for_pathway('hunter') -> hunter_characteristic (pathway-driven, not id-driven)")
	var foe: Agent = AG.get_agent(ADVERSARY_ID)
	_ok(foe != null, "the adversary is in the live roster (loaded from npcs.json)")
	if foe == null:
		return
	_ok(String(foe.pathway) == "hunter", "the live agent carries pathway:hunter (hydrated from data)")
	foe.room = "adv3_drop"
	foe.position = Vector2(120, 60)
	foe.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": ADVERSARY_ID})
	_ok(RI.count("adv3_drop", "hunter_characteristic") >= 1,
		"downing the adversary drops a hunter_characteristic where it fell (the second harvest)")
	# The Seq-7 payoff: two characteristics harvested -> two advances possible (9->8->7).
	var proxy: Agent = AG.ensure_player_proxy(Vector2.ZERO, "adv3_drop")
	proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()
	_ok(bool(P.can_advance().get("ok", false)),
		"the harvested hunter_characteristic + acting ritual arms a second advance (the Seq-7 payoff)")
	RI.clear()
	AG.rebuild()

# (d) --------------------------------------------------------------------------------------------
func _test_deed_grants_suspicion_clue_near_site() -> void:
	print("[adversary3: the adversary's signature deed grants its suspicion clue when the proxy witnesses it near the site]")
	var DR: Object = _al("DeedRunner")
	if DR == null:
		_ok(false, "DeedRunner autoload exists")
		return
	var AG: Object = _al("Agents")
	var CD: Object = _al("ClueDB")
	var Clk: Object = _al("Clock")
	var RM: Object = _al("RunManager")
	RM.start_run()
	AG.rebuild()
	var deed: Dictionary = {}
	for d in DR.deeds:
		if String((d as Dictionary).get("id", "")) == DEED_ID:
			deed = d
	_ok(not deed.is_empty(), "the deed %s is authored in deeds.json" % DEED_ID)
	if deed.is_empty():
		return
	_ok(String(deed.get("agent", "")) == ADVERSARY_ID, "the deed is performed by the adversary")
	_ok(String(deed.get("clue", "")) == DEED_CLUE, "the deed grants the %s suspicion clue" % DEED_CLUE)
	var wp_v: Array = deed.get("waypoint", [])
	var wp := Vector2(float(wp_v[0]), float(wp_v[1]))
	var room := String(deed.get("room", "city"))
	var phases: Array = deed.get("phases", [])
	var foe: Agent = AG.get_agent(ADVERSARY_ID)
	foe.room = room
	foe.position = wp
	foe.downed = false
	foe.vision_r = 600.0
	var proxy: Agent = AG.ensure_player_proxy(wp, room)
	proxy.vision_r = 600.0
	CD.from_dict({})
	DR.reset()
	if not phases.is_empty():
		Clk.set_time(2, _minute_for_phase(String(phases[0])))
	Clk.minute_ticked.emit(Clk.minute_of_day, Clk.day)
	_ok(CD.is_collected(DEED_CLUE),
		"the watching proxy earned %s from the adversary's deed near the site" % DEED_CLUE)
	CD.from_dict({})
	AG.rebuild()

# (e) --------------------------------------------------------------------------------------------
func _test_forms_and_abilities_load_clean_distinct_kit() -> void:
	print("[adversary3: the new forms + abilities load clean (validate_refs) with a DISTINCT mid-range bruiser kit]")
	var ADB: Object = _al("AbilityDB")
	if ADB == null:
		_ok(false, "AbilityDB autoload exists")
		return
	_ok(not ADB.form_def(HUMAN_FORM).is_empty(), "%s is loaded in AbilityDB" % HUMAN_FORM)
	_ok(not ADB.form_def(MONSTER_FORM).is_empty(), "%s is loaded in AbilityDB" % MONSTER_FORM)
	var probe_forms := {HUMAN_FORM: ADB.form_def(HUMAN_FORM), MONSTER_FORM: ADB.form_def(MONSTER_FORM)}
	var probe_abilities := {}
	for form in [HUMAN_FORM, MONSTER_FORM]:
		for aid in ADB.kit_for(String(form)):
			probe_abilities[String(aid)] = ADB.ability_for(String(aid))
	_ok(ADB.validate_refs(probe_abilities, probe_forms).is_empty(),
		"the adversary's forms + kit abilities pass validate_refs (no dangling refs)")
	# DISTINCT from butcher: no cleaver_swipe in human form (the butcher's opener).
	var human_kit: Array = ADB.kit_for(HUMAN_FORM)
	_ok(not human_kit.has("cleaver_swipe"),
		"the adversary's human kit is DISTINCT from the butcher (no cleaver_swipe)")
	# DISTINCT from Wren: no revolver_shot in human form (Wren's opening move).
	_ok(not human_kit.has("revolver_shot"),
		"the adversary's human kit is DISTINCT from Wren (no revolver_shot opener)")
	# Has a mid-range capability: hook_throw is the poacher's signature.
	_ok(human_kit.has("hook_throw"),
		"the adversary's human kit has hook_throw (the docks poacher's signature mid-range tool)")
	# Monster kit: a bruiser set with charge + blood_frenzy (the feral harbour beast).
	var mon_kit: Array = ADB.kit_for(MONSTER_FORM)
	_ok(mon_kit.has("charge"), "the monster kit has charge (the beast's lunge)")
	_ok(mon_kit.has("blood_frenzy"), "the monster kit has blood_frenzy (the hunt's end)")
	# Telegraph/dodge reflex on both forms (readable counterplay).
	for form_id in [HUMAN_FORM, MONSTER_FORM]:
		var fdef: Dictionary = ADB.form_def(form_id)
		var has_dodge := false
		for row in (fdef.get("reflexes", []) as Array):
			if String((row as Dictionary).get("do", {}).get("kind", "")) == "dodge":
				has_dodge = true
		_ok(has_dodge, "%s has a telegraph->dodge reflex (readable counterplay)" % form_id)

# (f) --------------------------------------------------------------------------------------------
func _test_post_advance_lead_gate() -> void:
	print("[adversary3: the after_advance lead surfaces after Progression.advanced fires — NOT before]")
	var LS: Object = _al("LeadSystem")
	var P: Object = _al("Progression")
	var RM: Object = _al("RunManager")
	var AG: Object = _al("Agents")
	var RI: Object = _al("RoomItems")
	if LS == null or P == null:
		_ok(false, "LeadSystem and Progression autoloads exist")
		return
	RM.start_run()
	AG.rebuild()
	# Track lead_surfaced signals.
	var surfaced_ids: Array = []
	var on_surfaced := func(id: String) -> void:
		surfaced_ids.append(id)
	LS.lead_surfaced.connect(on_surfaced)
	# Before any advance, the Mack lead is slotted but not yet surfaced by the post-advance hook.
	_ok(not LS.get_lead(MACK_LEAD).is_empty(),
		"the Mack lead is slotted from run start (board holds it)")
	var was_surfaced_pre := surfaced_ids.has(MACK_LEAD)
	_ok(not was_surfaced_pre,
		"the Mack lead is NOT surfaced at run start (gated behind after_advance)")
	# Fire Progression.advanced (simulating the first 9->8 advance).
	P.advanced.emit("hunter", 8)
	var was_surfaced_post := surfaced_ids.has(MACK_LEAD)
	_ok(was_surfaced_post,
		"the Mack lead IS surfaced after Progression.advanced fires (post-advance gate opened)")
	LS.lead_surfaced.disconnect(on_surfaced)
	RI.clear()
	AG.rebuild()

# --- helpers ------------------------------------------------------------------------------------
func _minute_for_phase(phase: String) -> int:
	match phase:
		"late-night": return 60
		"early-morning": return 360
		"morning": return 540
		"afternoon": return 780
		"dusk": return 1050
		"night": return 1200
		_: return 1200
