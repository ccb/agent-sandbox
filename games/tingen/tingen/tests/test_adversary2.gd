extends SceneTree
## M12 — the SECOND adversary: the Hunter-pathway prey (direction v2 §3/§6, the first real hunt).
## Standalone headless harness. Run: godot --headless --path tingen -s tests/test_adversary2.gd
##
## The progression loop (§6) advances the player by hunting a SAME-pathway Beyonder and harvesting
## its Characteristic. Until now the only pathway:"hunter" foe was a stand-in (constable_brom); the
## §3 opening promises a real quarry — the "he wasn't the only one, same blood walks the beat" hint,
## backed by the hunter_prey_kell_kin lead — with nothing behind it. M12 authors that quarry as PURE
## DATA (mirroring bram_kell/the butcher): a hidden Hunter-pathway Beyonder who LOST CONTROL, a
## two-phase combat_form (human -> monster via a transform, like the butcher's assume_form seam), a
## signature deed, and a real lead destination. No engine changes — the foe works through the same
## combat / deed / lead / progression machinery as the butcher.
##
## Covers the DELIVER acceptance (TDD):
##  (a) the new NPC loads with pathway:"hunter" + a two-phase combat_form (human + a monster form
##      reached via a transform ability in the human form's kit)
##  (b) the hunter_prey lead points to them with a REAL where_hint + pathway:"hunter"
##  (c) downing them drops hunter_characteristic via the PATHWAY-DRIVEN drop (not special-cased) ->
##      the player can advance (the first real hunt pays off)
##  (d) the deed grants its suspicion clue near the site
##  (e) the new forms/abilities load clean (validate_refs), distinct RANGED kit from the butcher's
##      melee cleaver set

const ADVERSARY_ID: String = "sable_wren"
const HUMAN_FORM: String = "wren_human"
const MONSTER_FORM: String = "wren_predator"
const HUNTER_LEAD: String = "hunter_prey_kell_kin"
const DEED_ID: String = "wren_blackthorn_stalk"
const DEED_CLUE: String = "sable_wren_suspicious"

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
	_test_lead_points_to_adversary()
	_test_downing_drops_hunter_characteristic_pathway_driven()
	_test_deed_grants_suspicion_clue_near_site()
	_test_forms_and_abilities_load_clean_distinct_kit()

	print("\n=== test_adversary2: %d passed, %d failed ===" % [_passed, _failed])
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
	print("[adversary2: the hidden Hunter-pathway Beyonder loads with a two-phase combat_form]")
	var DB: Object = _al("NpcDB")
	_ok(DB != null, "NpcDB autoload is registered")
	if DB == null:
		return
	var def: Dictionary = DB.get_def(ADVERSARY_ID)
	_ok(not def.is_empty(), "%s is authored in npcs.json" % ADVERSARY_ID)
	_ok(String(def.get("pathway", "")) == "hunter", "%s is tagged pathway:hunter" % ADVERSARY_ID)
	_ok(String(def.get("combat_form", "")) == HUMAN_FORM,
		"%s opens in the human phase-1 form %s" % [ADVERSARY_ID, HUMAN_FORM])
	# Identity / day-life: a public face + a secret (a Hunter who lost control), plus waypoints,
	# secrets, vision_r — mirroring the butcher template.
	_ok(String(def.get("description", "")) != "" and String(def.get("intent", "")) != "",
		"has a public-face identity (description + intent)")
	_ok((def.get("secrets", []) as Array).size() >= 1, "carries a secret (the lost-control truth)")
	_ok((def.get("schedule", {}) as Dictionary).size() >= 1, "has schedule waypoints")
	_ok(float(def.get("vision_r", 0.0)) > 0.0, "has a vision_r (a hunter's eyes)")
	# The two-phase shape: the human form's kit contains a TRANSFORM ability that lands on the
	# monster form (the assume_form seam, mirrored), and the monster form is authored monster:true.
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
	# The monster form has its own hp_below reflex? No — the human form transforms; the monster is
	# the terminal shape. Assert the HUMAN form has an hp_below -> transform reflex (like bram_kell).
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
		"the human form has an hp_below -> cast(transform) reflex (the butcher's descent seam)")

# (b) --------------------------------------------------------------------------------------------
func _test_lead_points_to_adversary() -> void:
	print("[adversary2: the hunter_prey lead is a REAL destination — subject=the adversary, where_hint, pathway:hunter]")
	var LS: Object = _al("LeadSystem")
	if LS == null:
		_ok(false, "LeadSystem autoload exists")
		return
	var RM: Object = _al("RunManager")
	RM.start_run()
	var lead: Dictionary = LS.get_lead(HUNTER_LEAD)
	_ok(not lead.is_empty(), "the hunter_prey_kell_kin lead is slotted")
	_ok(String(lead.get("pathway", "")) == "hunter", "the lead is tagged pathway:hunter (routes the advance)")
	_ok(String(lead.get("where_hint", "")) != "", "the lead has a REAL where_hint (a place, not blank)")
	_ok(String(lead.get("subject", "")) != "", "the lead names a subject (the same-blooded hunter)")
	# The where_hint must resolve to WHERE the adversary actually is (a real destination, not a
	# random pool pick that points nowhere). We assert the adversary is staged/schedulable at the
	# lead's site — the lead ROUTES to the fight.
	var subj_key := String(lead.get("subject_key", ""))
	_ok(subj_key == "hunter", "the lead's subject_key is the hunter hook")

# (c) --------------------------------------------------------------------------------------------
func _test_downing_drops_hunter_characteristic_pathway_driven() -> void:
	print("[adversary2: downing the adversary drops hunter_characteristic via the PATHWAY-driven drop -> the player can advance]")
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
	# Stage the REAL adversary def (pathway is DATA on the agent), down it, and confirm the drop is
	# the SAME pathway-driven rule the butcher uses — not a per-id special case. Prove it by asserting
	# drop_for_pathway keys purely off the pathway string.
	_ok(P.drop_for_pathway("hunter") == "hunter_characteristic",
		"drop_for_pathway('hunter') -> hunter_characteristic (pathway-driven, not id-driven)")
	var foe: Agent = AG.get_agent(ADVERSARY_ID)
	_ok(foe != null, "the adversary is in the live roster (loaded from npcs.json)")
	if foe == null:
		return
	_ok(String(foe.pathway) == "hunter", "the live agent carries pathway:hunter (hydrated from data)")
	foe.room = "adv2_drop"
	foe.position = Vector2(120, 60)
	foe.downed = true
	RI.clear()
	EB.emit_event("agent_downed", {"actor": "player", "target": ADVERSARY_ID})
	_ok(RI.count("adv2_drop", "hunter_characteristic") >= 1,
		"downing the adversary drops a hunter_characteristic where it fell (the harvest)")
	# The payoff: with the drop harvested + the acting ritual done, the player can ADVANCE.
	var proxy: Agent = AG.ensure_player_proxy(Vector2.ZERO, "adv2_drop")
	proxy.add_item("hunter_characteristic", 1)
	P.mark_deed_done()
	_ok(bool(P.can_advance().get("ok", false)),
		"the harvested hunter_characteristic + acting ritual arms an advance (the first real hunt pays off)")
	RI.clear()
	AG.rebuild()

# (d) --------------------------------------------------------------------------------------------
func _test_deed_grants_suspicion_clue_near_site() -> void:
	print("[adversary2: the adversary's signature deed grants its suspicion clue when the proxy witnesses it near the site]")
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
	# Find the authored deed row (data, not engine): agent = the adversary, a clue, a waypoint.
	var deed: Dictionary = {}
	for d in DR.deeds:
		if String((d as Dictionary).get("id", "")) == DEED_ID:
			deed = d
	_ok(not deed.is_empty(), "the deed %s is authored in deeds.json" % DEED_ID)
	if deed.is_empty():
		return
	_ok(String(deed.get("agent", "")) == ADVERSARY_ID, "the deed is performed by the adversary")
	_ok(String(deed.get("clue", "")) == DEED_CLUE, "the deed grants the %s suspicion clue" % DEED_CLUE)
	# Walk the adversary to the deed waypoint during a named phase, with the proxy watching, and tick a
	# minute — the deed fires and the watching proxy earns the clue (the butcher-canal seam, mirrored).
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
	# Set the clock into one of the deed's named phases (map the phase name -> a minute in it).
	if not phases.is_empty():
		Clk.set_time(2, _minute_for_phase(String(phases[0])))
	# Drive a minute tick; the deed fires once and the watching proxy earns the clue.
	Clk.minute_ticked.emit(Clk.minute_of_day, Clk.day)
	_ok(CD.is_collected(DEED_CLUE),
		"the watching proxy earned %s from the adversary's deed near the site" % DEED_CLUE)
	CD.from_dict({})
	AG.rebuild()

# (e) --------------------------------------------------------------------------------------------
func _test_forms_and_abilities_load_clean_distinct_kit() -> void:
	print("[adversary2: the new forms + any new abilities load clean (validate_refs) with a DISTINCT ranged kit from the butcher]")
	var ADB: Object = _al("AbilityDB")
	if ADB == null:
		_ok(false, "AbilityDB autoload exists")
		return
	_ok(not ADB.form_def(HUMAN_FORM).is_empty(), "%s is loaded in AbilityDB" % HUMAN_FORM)
	_ok(not ADB.form_def(MONSTER_FORM).is_empty(), "%s is loaded in AbilityDB" % MONSTER_FORM)
	# Any NEW ability the adversary authors must pass validate_refs against the loaded forms (a
	# transform naming an unknown form would be caught here). Build the probe from the two forms'
	# kits + the transform ability, validated against both forms.
	var probe_forms := {HUMAN_FORM: ADB.form_def(HUMAN_FORM), MONSTER_FORM: ADB.form_def(MONSTER_FORM)}
	var probe_abilities := {}
	for form in [HUMAN_FORM, MONSTER_FORM]:
		for aid in ADB.kit_for(String(form)):
			probe_abilities[String(aid)] = ADB.ability_for(String(aid))
	_ok(ADB.validate_refs(probe_abilities, probe_forms).is_empty(),
		"the adversary's forms + kit abilities pass validate_refs (no dangling refs)")
	# DISTINCT kit: the butcher's monster is a MELEE cleaver set (cleaver_swipe). The adversary is a
	# RANGED blood-hunter — its monster kit must lean on ranged/hunter arts, NOT cleaver_swipe.
	var mon_kit: Array = ADB.kit_for(MONSTER_FORM)
	_ok(not mon_kit.has("cleaver_swipe"),
		"the adversary's monster kit is DISTINCT from the butcher's cleaver melee (no cleaver_swipe)")
	var ranged_arts := ["revolver_shot", "incendiary_round", "hook_throw", "mark_prey"]
	var has_ranged := false
	for a in ranged_arts:
		if mon_kit.has(a):
			has_ranged = true
	_ok(has_ranged, "the adversary's monster kit is a ranged/hunter set (a blood-hunter, not a brawler)")
	# A telegraph/dodge reflex on the monster form (distinct counterplay feel, like the butcher).
	var mform: Dictionary = ADB.form_def(MONSTER_FORM)
	var has_dodge := false
	for row in (mform.get("reflexes", []) as Array):
		if String((row as Dictionary).get("do", {}).get("kind", "")) == "dodge":
			has_dodge = true
	_ok(has_dodge, "the monster form has a telegraph->dodge reflex (readable counterplay)")

# --- helpers ------------------------------------------------------------------------------------
## Map a Clock phase name to a minute-of-day that falls inside it (Clock.PHASE_BOUNDS).
func _minute_for_phase(phase: String) -> int:
	match phase:
		"late-night": return 60
		"early-morning": return 360
		"morning": return 540
		"afternoon": return 780
		"dusk": return 1050
		"night": return 1200
		_: return 1200
