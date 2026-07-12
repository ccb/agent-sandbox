extends SceneTree
## M20 live-loop bug harness (docs/handoff/OVERNIGHT_BACKLOG.md B1/B2/B6/B7). Run with:
##   godot --headless --path tingen -s tests/test_live_bugs.gd
##
## These pin the four bugs that made the LIVE game unplayable end-to-end but the green suite missed
## (no test instantiated the live City.tscn / the real player-input path). Watched RED before the
## fixes:
##   B1 — the legacy CitySummoning node self-lost every run ~80s after entering the city: it staged a
##        cult auto-resolve + overrode Clock pacing/DEMO_SPEED, and RunManager._on_summoning_climax
##        end_run('lose')'d off the legacy countdown, bypassing the M7 Ritual Night climax. FIX:
##        removed the node from City.tscn; guarded _on_summoning_climax to no-op unless a Ritual Night
##        owns the climax.
##   B2 — the core progression loop had no live caller: Progression.advance()/Madness sinks were only
##        reachable from tests. FIX: a digest/advance Interactable flag, an acting-deed flag (3/day
##        cap), and checkpoint_night's nightly Madness rest.
##   B6 — the on-screen objective never pointed at the opener. FIX: GMOpening sets WorldState.current_lead
##        to the butcher opener; the IntroRoom door override + legacy RUN_START_LEAD are retired.
##   B7 — constable_brom was a farmable free same-pathway advance + broke the opener. FIX: off-pathway
##        (no pathway/combat_form), plus a dialogue entry so the opener source is talkable.

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()

	await _b1_city_scene_has_no_summoning_node_and_keeps_pacing()
	_b1_summoning_climax_noops_without_ritual_night()
	await _b2_digest_advance_action_raises_sequence()
	_b2_checkpoint_night_lowers_madness()
	await _b2_acting_deed_relieves_and_caps_3_per_day()
	_b6_opener_objective_points_at_butcher()
	await _b7_constable_brom_is_off_pathway_and_talkable()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

# =========================================================================================== B1 ===
## Instantiating the LIVE City.tscn + letting the 2-frame-deferred bootstrap fire must NOT stage the
## legacy auto-loss: the CitySummoning node is gone, Clock pacing / Agents.fallback_speed are left at
## their run values (never the DEMO overrides), and advancing ~2 game-hours does not auto-end the run.
func _b1_city_scene_has_no_summoning_node_and_keeps_pacing() -> void:
	print("[B1: entering the city no longer stages the legacy auto-loss]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var CL: Object = root.get_node("/root/Clock")
	# Snapshot the pacing so a (RED) bootstrap override is detectable, and restore it after.
	var mpb_before: int = CL.minutes_per_beat
	var rspm_before: float = CL.real_seconds_per_game_minute
	var speed_before: float = AG.fallback_speed

	RM.start_run()
	_ok(RM.run_active(), "the run is active after start_run")

	var scene: Node = (load("res://scenes/City.tscn") as PackedScene).instantiate()
	root.add_child(scene)
	_ok(scene.get_node_or_null("CitySummoning") == null,
		"City.tscn no longer embeds the CitySummoning node")
	# Let the 2-frame-deferred bootstrap fire IF the node were still present (RED path).
	await process_frame
	await process_frame
	await process_frame
	_ok(CL.minutes_per_beat == mpb_before,
		"entering the city does NOT override Clock.minutes_per_beat to the DEMO value (%d)" % CL.minutes_per_beat)
	_ok(is_equal_approx(CL.real_seconds_per_game_minute, rspm_before),
		"entering the city does NOT override Clock.real_seconds_per_game_minute")
	_ok(is_equal_approx(AG.fallback_speed, speed_before),
		"entering the city does NOT override Agents.fallback_speed to DEMO_SPEED")

	# Advance ~2 game hours of beats and assert the run does NOT auto-end in a loss.
	var lost := {"n": 0}
	var cb := func(reason: String) -> void:
		if reason == "lose":
			lost["n"] = int(lost["n"]) + 1
	RM.run_ended.connect(cb)
	for beat in 10:
		CL.advance_minutes(15)   # ~2.5 game-hours over the loop
	RM.run_ended.disconnect(cb)
	_ok(int(lost["n"]) == 0 and RM.run_active(),
		"~2 game-hours in the city do NOT auto-end the run in a loss (run stays active)")

	scene.free()
	# Restore pacing (defensive — nothing should have touched it).
	CL.minutes_per_beat = mpb_before
	CL.real_seconds_per_game_minute = rspm_before
	AG.fallback_speed = speed_before
	CL.set_time(1, 480)

## The legacy SummoningPlan.summoning_climax must NOT self-end the run when no Ritual Night owns the
## climax — Doom/RitualNight own the loss now (M7/M11). RED before the guard: end_run('lose') fired.
func _b1_summoning_climax_noops_without_ritual_night() -> void:
	print("[B1: _on_summoning_climax no-ops without an active Ritual Night]")
	var RM: Object = root.get_node("/root/RunManager")
	var RN: Object = root.get_node("/root/RitualNight")
	RN.reset()
	RM.start_run()
	_ok(not RN.active() and not RN.resolved(), "no Ritual Night owns the climax (fresh run)")
	var ended := {"reason": ""}
	var cb := func(reason: String) -> void: ended["reason"] = reason
	RM.run_ended.connect(cb)
	# Drive the RunManager slot directly (avoid EndGame's pause side-effect from emitting the signal).
	RM._on_summoning_climax(100.0)
	RM.run_ended.disconnect(cb)
	_ok(RM.run_active() and String(ended["reason"]) == "",
		"the legacy climax at strength 100 is INERT: the run stays active, no end_run('lose')")

# =========================================================================================== B2 ===
## A live digest/advance action (the Interactable flag) raises the Sequence when the player holds a
## same-pathway Characteristic — the core RPG loop is reachable in play. RED: no live caller existed.
func _b2_digest_advance_action_raises_sequence() -> void:
	print("[B2: a live digest/advance action raises the Sequence]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	RM.start_run()
	AG.rebuild()
	var proxy: Object = AG.ensure_player_proxy(Vector2.ZERO, "city")
	proxy.add_item(P.characteristic_item(), 1)   # a harvested hunter_characteristic in hand
	P.mark_deed_done()                            # the acting ritual armed for this digest
	var seq_before: int = P.sequence()

	var node: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	node.digest_advance = true
	root.add_child(node)
	await process_frame
	node._use()
	node.free()

	_ok(P.sequence() == seq_before - 1,
		"the digest/advance action rose the Sequence one rung (%d -> %d)" % [seq_before, P.sequence()])
	_ok(proxy.item_count(P.characteristic_item()) == 0,
		"the digest consumed the same-pathway Characteristic")
	RM.start_run()   # scrub back for later cases
	AG.rebuild()

## The nightly safe-house checkpoint relieves Madness (-10, the §4 rest sink) — wired into
## checkpoint_night. RED: checkpoint_night never touched Madness.
func _b2_checkpoint_night_lowers_madness() -> void:
	print("[B2: checkpoint_night relieves Madness (nightly rest)]")
	var RM: Object = root.get_node("/root/RunManager")
	var M: Object = root.get_node("/root/Meters")
	RM.start_run()
	root.get_node("/root/Agents").rebuild()
	M.set_meter("doom", 30.0)   # keep Doom < 100 so this is a plain nightly checkpoint
	M.set_meter("madness", 40.0)
	RM.checkpoint_night()
	_ok(is_equal_approx(M.get_meter("madness"), 30.0),
		"checkpoint_night lowered Madness by the rest relief (40 -> %.0f)" % M.get_meter("madness"))
	RM.start_run()
	root.get_node("/root/Agents").rebuild()

## The daily acting-deed action relieves Madness (-5) and CAPS at 3/day — the other half of the
## Madness cycle, reachable live. RED: relieve_madness_deed had no caller and no cap existed.
func _b2_acting_deed_relieves_and_caps_3_per_day() -> void:
	print("[B2: the acting-deed action relieves Madness and caps at 3/day]")
	var RM: Object = root.get_node("/root/RunManager")
	var M: Object = root.get_node("/root/Meters")
	var CL: Object = root.get_node("/root/Clock")
	RM.start_run()
	CL.set_time(1, 480)
	M.set_meter("madness", 60.0)

	# Drive the live Interactable flag four times in one day.
	var node: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	node.acting_deed = true
	root.add_child(node)
	await process_frame
	node._use()   # M26 RETUNE #5: -3 each (was -5). 60 -> 57
	node._use()   # 57 -> 54
	node._use()   # 54 -> 51
	var after_three: float = M.get_meter("madness")
	node._use()   # capped — no change (3/day cap unchanged)
	var after_cap: float = M.get_meter("madness")
	node.free()

	_ok(is_equal_approx(after_three, 51.0),
		"three acting deeds relieved 3x3 Madness (60 -> %.0f) [M26 retune: -3/deed]" % after_three)
	_ok(is_equal_approx(after_cap, 51.0),
		"a fourth acting deed the SAME day is capped (stays %.0f)" % after_cap)

	# Rolling into the next day re-arms the cap.
	CL.set_time(2, 480)
	var r: Dictionary = M.try_relieve_madness_deed()
	_ok(bool(r.get("ok", false)) and is_equal_approx(M.get_meter("madness"), 48.0),
		"a new day re-arms the acting-deed cap (relief works again: 51 -> 48)")
	RM.start_run()
	root.get_node("/root/Agents").rebuild()

# =========================================================================================== B6 ===
## After start_run, the top-bar objective (WorldState.current_lead) NAMES the guaranteed butcher
## opener — matching the board's hot lead — not the stale cult-warehouse string. RED: it showed the
## legacy RUN_START_LEAD.
func _b6_opener_objective_points_at_butcher() -> void:
	print("[B6: the run-start objective points at the butcher opener]")
	var RM: Object = root.get_node("/root/RunManager")
	var LS: Object = root.get_node("/root/LeadSystem")
	var WS: Object = root.get_node("/root/WorldState")
	RM.start_run()
	var lead: Dictionary = LS.get_lead("butcher_iron_cross")
	_ok(not lead.is_empty(), "the guaranteed butcher lead is slotted on the board")
	var objective: String = String(WS.current_lead)
	_ok(objective.to_lower().find("iron cross") != -1,
		"the objective names the butcher opener's street (Iron Cross): '%s'" % objective)
	_ok(objective.find(String(lead.get("subject", ""))) != -1,
		"the objective text matches the board lead's own subject (data-sourced)")
	_ok(objective != WS.RUN_START_LEAD,
		"the objective is NOT the legacy cult-warehouse RUN_START_LEAD string")

# =========================================================================================== B7 ===
## constable_brom — the opener's source NPC — must be OFF-PATHWAY (downing him drops no free
## hunter_characteristic) and TALKABLE (a dialogue entry). RED: pathway:hunter + combat_form:
## butcher_human + no dialogue.
func _b7_constable_brom_is_off_pathway_and_talkable() -> void:
	print("[B7: constable_brom is off-pathway, safe to down, and talkable]")
	var DB: Object = root.get_node("/root/NpcDB")
	var def: Dictionary = DB.get_def("constable_brom")
	_ok(String(def.get("pathway", "")) == "",
		"constable_brom carries no pathway tag (off-pathway like the mundane roster)")
	_ok(String(def.get("combat_form", "")) != "butcher_human",
		"constable_brom's copy-paste butcher_human combat_form is gone")

	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var RI: Object = root.get_node("/root/RoomItems")
	var EB: Object = root.get_node("/root/EventBus")
	RM.start_run()
	AG.rebuild()
	var brom: Object = AG.get_agent("constable_brom")
	_ok(brom != null and String(brom.pathway) == "",
		"the live constable_brom agent is off-pathway")
	# Down him and confirm the harvest drop is NOT a hunter_characteristic (no free advance).
	brom.room = "city"
	brom.position = Vector2(1000, 1000)
	RI.clear()
	brom.downed = true
	EB.emit_event("agent_downed", {"actor": "player", "target": "constable_brom"})
	await process_frame
	_ok(RI.count("city", "hunter_characteristic") == 0,
		"downing constable_brom drops NO hunter_characteristic (no farmable free advance)")

	# Talkable: a dialogue tree exists.
	var dlg: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/dialogue.json"))
	_ok(dlg is Dictionary and (dlg as Dictionary).has("constable_brom"),
		"constable_brom has a dialogue.json entry (the opener source is talkable)")
	_ok(String(def.get("dialogue_id", "")) == "constable_brom",
		"constable_brom's npcs.json dialogue_id points at his dialogue tree")
	RI.clear()
	RM.start_run()
	AG.rebuild()
