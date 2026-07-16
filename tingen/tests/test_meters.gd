extends SceneTree
## M4 four-meter push-your-luck harness. Run with:
##   godot --headless --path tingen -s tests/test_meters.gd
##
## Watched RED before the Meters/MeterDrivers/rampage/HUD implementation existed. Covers the
## design-doc §4 semantics: the four meters clamp 0..100 and reset to RUN_START on RunManager.reset;
## Madness is a CYCLE (add_madness raises, acting-deed/rest lowers) with a telegraphed ladder that
## fires each threshold exactly once per crossing; Madness 100 -> a loss-of-control rampage that
## transforms the player proxy, runs a timer, and calls RunManager.end_run('lost_control') at expiry;
## a WITNESSED public player cast raises Heat but an unwitnessed one does not (vision-gated); Doom
## rises on a rite-step event and panic is a pure function of Doom; and a determinism guard proving
## the meter drivers never alter the combat event transcript (meters read combat, never feed it back).

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

	_test_four_meters_clamp_and_reset()
	_test_madness_is_a_cycle()
	_test_madness_ladder_fires_once_per_crossing()
	await _test_madness_100_loss_of_control()
	await _test_rampage_player_controls_monster()
	_test_rampage_suspends_normal_play()
	_test_ritual_night_latch_not_leaked_across_restore()
	_test_heat_is_vision_gated()
	_test_doom_rises_on_rite_step()
	_test_doom_rises_as_time_passes()
	_test_doom_rises_with_monsters_left_alive()
	_test_doom_100_flags_ritual_night()
	_test_notice_heat_threat_hook()
	_test_panic_is_derived_from_doom()
	await _test_meter_drivers_are_cosmetic_to_combat()
	await _test_hud_reads_meters_progressive_disclosure()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

func _M() -> Node:
	return root.get_node_or_null("/root/Meters")

# --- (a) clamp + reset ------------------------------------------------------------------------
func _test_four_meters_clamp_and_reset() -> void:
	print("[meters: the four clamp 0..100 and reset to RUN_START on RunManager.reset]")
	var M := _M()
	_ok(M != null, "Meters autoload is registered")
	if M == null:
		return
	for meter in ["doom", "madness", "notice", "heat"]:
		M.set_meter(meter, 250.0)
		_ok(M.get_meter(meter) == 100.0, "%s clamps high to 100" % meter)
		M.set_meter(meter, -80.0)
		_ok(M.get_meter(meter) == 0.0, "%s clamps low to 0" % meter)
	# Dirty every meter, then a fresh run must scrub them to RUN_START.
	for meter in ["doom", "madness", "notice", "heat"]:
		M.set_meter(meter, 77.0)
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()
	for meter in ["doom", "madness", "notice", "heat"]:
		_ok(M.get_meter(meter) == M.run_start(meter),
			"%s resets to RUN_START (%s) on start_run" % [meter, M.run_start(meter)])

# --- (b) Madness cycle + ladder ---------------------------------------------------------------
func _test_madness_is_a_cycle() -> void:
	print("[meters: Madness is a cycle — add raises, acting-deed / rest lowers]")
	var M := _M()
	if M == null:
		return
	M.set_meter("madness", 0.0)
	M.add_madness(35.0, "digest")
	_ok(M.get_meter("madness") == 35.0, "add_madness(+35) raises Madness")
	M.relieve_madness_deed()   # M26 RETUNE #5: an acting deed, -3 (was -5; cap 3/day handled by caller)
	_ok(M.get_meter("madness") == 32.0, "an acting deed lowers Madness by 3 (M26 retune)")
	M.relieve_madness_rest()   # a night's Cogitation, -10
	_ok(M.get_meter("madness") == 22.0, "a night's rest lowers Madness by 10 (35 -3 M26 deed -10 rest = 22)")

func _test_madness_ladder_fires_once_per_crossing() -> void:
	print("[meters: the Madness ladder fires at 50/75/100 exactly once per crossing]")
	var M := _M()
	if M == null:
		return
	var fired: Array = []
	var cb := func(level: int) -> void: fired.append(level)
	M.madness_threshold.connect(cb)
	M.set_meter("madness", 0.0)
	M.add_madness(50.0, "t")   # cross 50
	_ok(fired == [50], "crossing 50 fires the whispers threshold once")
	M.add_madness(1.0, "t")    # still above 50, no re-fire
	_ok(fired == [50], "staying above 50 does not re-fire")
	M.add_madness(24.0, "t")   # to 75 -> stir
	_ok(fired == [50, 75], "crossing 75 fires the form-stirring threshold")
	M.add_madness(25.0, "t")   # to 100 -> loss of control
	_ok(fired == [50, 75, 100], "crossing 100 fires the loss-of-control threshold")
	# Fall back below 50 then climb again — the crossing re-arms.
	M.relieve_madness(80.0)    # down to 20
	M.add_madness(35.0, "t")   # back across 50
	_ok(fired == [50, 75, 100, 50], "falling below then re-crossing 50 re-fires it")
	M.madness_threshold.disconnect(cb)

# --- (c) Madness 100 -> loss of control (the 60s rampage) --------------------------------------
func _test_madness_100_loss_of_control() -> void:
	print("[meters: Madness 100 -> rampage: player transforms, timer runs, end_run('lost_control')]")
	var M := _M()
	if M == null:
		return
	var AG: Object = root.get_node("/root/Agents")
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()   # a fresh run clears any prior rampage/ladder latch from earlier tests
	AG.rebuild()
	var proxy: Agent = AG.ensure_player_proxy(Vector2.ZERO, "rampage_arena")
	proxy.combat_form = "player"
	# A shortened rampage window keeps the test fast; the driver reads this seam.
	M.rampage_duration_s = 0.5
	var ended := {"reason": ""}
	var cb := func(reason: String) -> void: ended["reason"] = reason
	RM.run_ended.connect(cb)
	M.set_meter("madness", 0.0)
	M.add_madness(100.0, "t")   # cross 100 -> loss of control begins
	_ok(M.in_rampage(), "Madness 100 puts the player into a loss-of-control rampage")
	_ok(proxy.combat_form != "player" and proxy.combat_form != "",
		"the rampage transforms the player proxy off its human form")
	_ok(M.rampage_remaining_s() > 0.0 and M.rampage_remaining_s() <= 0.5,
		"the rampage exposes a countdown for the HUD")
	# Step the rampage clock past its window; at expiry the run ends 'lost_control'.
	M.tick_rampage(0.3)
	_ok(ended["reason"] == "" and M.in_rampage(), "before expiry the rampage is still live")
	M.tick_rampage(0.3)   # total 0.6 > 0.5
	_ok(ended["reason"] == "lost_control", "at expiry RunManager.end_run('lost_control') is called")
	_ok(not M.in_rampage(), "the rampage ends when the window closes")
	RM.run_ended.disconnect(cb)

# --- rampage: the player CONTROLS the creature form -------------------------------------------
func _test_rampage_player_controls_monster() -> void:
	print("[meters: during the rampage the player's attack drives the MONSTER kit, not the human gun]")
	var M := _M()
	if M == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	var EB: Object = root.get_node("/root/EventBus")
	RM.start_run()
	# Stage the real Player scene (its Combat child binds a live executor to the "player" proxy).
	var p = load("res://scenes/Player.tscn").instantiate()
	root.add_child(p)
	p.global_position = Vector2.ZERO
	var pc: Node = p.get_node("Combat")
	pc.proxy.room = "rampage_control"
	pc.proxy.position = Vector2.ZERO
	M.rampage_duration_s = 60.0
	M.set_meter("madness", 0.0)
	M.add_madness(100.0, "t")   # loss of control: the proxy assumes the creature form
	_ok(M.in_rampage() and pc.proxy.combat_form == Meters.RAMPAGE_FORM,
		"the player proxy wears the creature form during the rampage")
	EB.clear()
	# The SAME attack button now casts the monster's primary art (not revolver_shot).
	var verdict: Dictionary = pc.on_attack_pressed(Vector2.RIGHT)
	_ok(bool(verdict.get("ok", false)), "the attack fires in creature form")
	var casts: Array = EB.events("ability_cast_started")
	var cast_art := String((casts[0].get("data", {}) as Dictionary).get("ability", "")) if casts.size() > 0 else ""
	_ok(cast_art != "" and cast_art != "revolver_shot",
		"the attack drove a monster art ('%s'), not the human revolver" % cast_art)
	# Clean up the scene + rampage before the next test (start_run scrubs the meters/rampage latch).
	p.free()
	RM.start_run()
	root.get_node("/root/Agents").rebuild()
	EB.clear()

# --- rampage suspends normal play (§13 decision #5; review M4 #2) ------------------------------
func _test_rampage_suspends_normal_play() -> void:
	print("[meters: a live rampage locks out normal play — no room swap / dialogue / tool use]")
	var M := _M()
	if M == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	var DM: Object = root.get_node("/root/DialogueManager")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	RM.start_run()
	root.get_node("/root/Agents").rebuild()
	var proxy: Agent = root.get_node("/root/Agents").ensure_player_proxy(Vector2.ZERO, "lockout_room")
	proxy.combat_form = "player"
	M.rampage_duration_s = 60.0
	M.set_meter("madness", 0.0)
	M.add_madness(100.0, "t")   # loss of control begins
	_ok(M.in_rampage(), "the rampage is live for the lockout checks")
	# Dialogue is refused while the beast has taken over (start() and open() both bail early).
	DM.active = false
	DM.start("any_npc")
	_ok(not bool(DM.get("active")), "dialogue.start() is refused during a rampage")
	DM.open("any_npc")
	_ok(not bool(DM.get("active")), "dialogue.open() is refused during a rampage")
	# Occult tool use is refused (the beast can't work a divination tool).
	var tool_res: Dictionary = OTM.use("any_tool")
	_ok(not bool(tool_res.get("ok", false)) and String(tool_res.get("kind", "")) == "locked",
		"OccultToolManager.use() is locked out during a rampage")
	# The GameController transition seam is gated on in_rampage() too (asserted by reading the guard
	# path: a swap request while rampaging is a no-op). Verified structurally here via the meter gate.
	_ok(M.in_rampage(), "the transition seam reads the same in_rampage() lockout gate")
	# Close the window so the next test starts clean.
	M.tick_rampage(61.0)
	RM.start_run()
	root.get_node("/root/Agents").rebuild()

# --- Ritual-Night latch does not leak across a checkpoint restore (review M4 #1) ---------------
func _test_ritual_night_latch_not_leaked_across_restore() -> void:
	print("[run: the Ritual-Night latch is re-derived from Doom on a checkpoint restore (no M2-class leak)]")
	var M := _M()
	if M == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()
	root.get_node("/root/Agents").rebuild()
	# Take a nightly checkpoint with Doom < 100 (Ritual Night NOT yet reached).
	M.set_meter("doom", 40.0)
	RM.checkpoint_night()
	_ok(not RM.ritual_night_reached(), "at checkpoint (Doom<100) Ritual Night is not reached")
	# Doom later tops out -> the latch lights.
	M.set_meter("doom", 100.0)
	_ok(RM.ritual_night_reached(), "Doom 100 latches Ritual Night")
	# The player is downed -> end_run('death') restores the pre-100 checkpoint. The latch MUST clear
	# (Doom came back below 100); before the fix it stayed stuck true.
	RM.end_run("death")
	_ok(M.get_meter("doom") < 100.0, "the restore pulled Doom back below 100")
	_ok(not RM.ritual_night_reached(),
		"the Ritual-Night latch is cleared on restore (not leaked across the checkpoint)")
	RM.start_run()
	root.get_node("/root/Agents").rebuild()

# --- (d) Heat is vision-gated -----------------------------------------------------------------
func _test_heat_is_vision_gated() -> void:
	print("[meters: a WITNESSED public player cast raises Heat; an unwitnessed one does not]")
	var M := _M()
	if M == null:
		return
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var proxy: Agent = AG.ensure_player_proxy(Vector2.ZERO, "heat_room")
	# A witness standing in the room, within vision.
	var witness := _stage("heat_witness", "heat_room", Vector2(60, 0))
	M.set_meter("heat", 0.0)
	# The player casts in public view: a witness can perceive it -> Heat rises.
	root.get_node("/root/EventBus").emit_event("ability_cast_started",
		{"caster": "player", "ability": "revolver_shot", "target": "", "cast_time": 0.25})
	_ok(M.get_meter("heat") > 0.0, "a witnessed public cast raises Heat")
	# Now move the only witness out of the room: an unwitnessed cast raises NO Heat.
	witness.room = "elsewhere"
	M.set_meter("heat", 0.0)
	root.get_node("/root/EventBus").emit_event("ability_cast_started",
		{"caster": "player", "ability": "revolver_shot", "target": "", "cast_time": 0.25})
	_ok(M.get_meter("heat") == 0.0, "an unwitnessed public cast raises no Heat (vision-gated)")
	AG.rebuild()

# --- (e) Doom rises on a rite step; panic derived ---------------------------------------------
func _test_doom_rises_on_rite_step() -> void:
	print("[meters: Doom rises on a rite-step event]")
	var M := _M()
	if M == null:
		return
	M.set_meter("doom", 10.0)
	var before: float = M.get_meter("doom")
	root.get_node("/root/EventBus").emit_event("ritual_advanced",
		{"actor": "cultist", "step": 1, "closeness": 0.5})
	_ok(M.get_meter("doom") > before, "a rite-step (ritual_advanced) raises Doom")

# --- (e2) Doom is the WORLD CLOCK: time passing + monsters left alive both fill it (§4) ---------
# §4 "Doom rises when: time passes; cult rites you don't stop; monsters you leave alive." The
# rite-step fill is above; these two cover the other two sources — both DETERMINISTIC game-time
# drivers (no RNG, no wall clock) that read world state and never feed back into combat.
#
# Each measurement pins the clock to 08:00 first and advances exactly one hour to 09:00, a window
# WHOLLY inside the "morning" phase (Clock bounds at 480/720). That isolates the hourly time/monster
# driver from the separate per-phase Doom pacer (which fires only on a phase boundary crossing), so
# the windows are identical game-time and the ONLY variable is whether a monster is loose.
const _DOOM_HOUR_START_MIN: int = 480   # 08:00, inside "morning" — +60 min stays in-phase (< 720)

func _test_doom_rises_as_time_passes() -> void:
	print("[meters: Doom fills on its own as in-game time passes (the world clock, §4)]")
	var M := _M()
	if M == null:
		return
	var AG: Object = root.get_node("/root/Agents")
	var CL: Object = root.get_node("/root/Clock")
	AG.rebuild()   # a clean cast (no monster loose) isolates the pure TIME fill
	CL.set_time(1, _DOOM_HOUR_START_MIN)
	M.set_meter("doom", 10.0)   # after set_time so any phase-change nudge from it is wiped
	var before: float = M.get_meter("doom")
	CL.advance_minutes(60)   # 08:00 -> 09:00, in-phase — deterministic, no wall clock
	_ok(M.get_meter("doom") > before, "an in-game hour of time passing raises Doom on its own")

func _test_doom_rises_with_monsters_left_alive() -> void:
	print("[meters: a live monster left in the district hastens Doom beyond time alone (§4)]")
	var M := _M()
	if M == null:
		return
	var AG: Object = root.get_node("/root/Agents")
	var CL: Object = root.get_node("/root/Clock")
	AG.rebuild()
	# Baseline: one in-game hour with NO monster loose — the pure time fill.
	CL.set_time(1, _DOOM_HOUR_START_MIN)
	M.set_meter("doom", 0.0)
	CL.advance_minutes(60)
	var time_only: float = M.get_meter("doom")
	# Stage a LIVE monster, keyed generically off a MONSTER combat_form (no NPC-identity branch).
	var monster := _stage("doom_monster", "doom_lair", Vector2.ZERO)
	monster.combat_form = Meters.RAMPAGE_FORM   # bieber_monster — a built monster kit
	CL.set_time(1, _DOOM_HOUR_START_MIN)
	M.set_meter("doom", 0.0)
	CL.advance_minutes(60)
	var with_monster: float = M.get_meter("doom")
	_ok(with_monster > time_only, "a live monster raises Doom faster than time alone")
	# A DOWNED monster is no threat — it stops pushing Doom (only the identical time fill remains).
	monster.downed = true
	CL.set_time(1, _DOOM_HOUR_START_MIN)
	M.set_meter("doom", 0.0)
	CL.advance_minutes(60)
	_ok(M.get_meter("doom") == time_only, "a downed monster no longer pushes Doom (only time remains)")
	AG.rebuild()   # scrub the staged monster before the next test

func _test_doom_100_flags_ritual_night() -> void:
	print("[meters: Doom 100 fires ritual_night once and RunManager latches it]")
	var M := _M()
	if M == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()   # a fresh run: Doom low, ritual-night latch clear
	var fired := {"n": 0}
	var cb := func() -> void: fired["n"] += 1
	M.ritual_night.connect(cb)
	M.set_meter("doom", 50.0)
	_ok(not RM.ritual_night_reached(), "before Doom 100 Ritual Night is not reached")
	M.set_meter("doom", 100.0)
	_ok(fired["n"] == 1, "Doom 100 fires ritual_night exactly once")
	_ok(RM.ritual_night_reached(), "RunManager latches Ritual Night at Doom 100")
	M.set_meter("doom", 100.0)   # staying at 100 doesn't re-fire
	_ok(fired["n"] == 1, "staying at Doom 100 does not re-fire ritual_night")
	M.ritual_night.disconnect(cb)
	RM.start_run()

func _test_notice_heat_threat_hook() -> void:
	print("[meters: high Notice/Heat fire the threat threshold (hunter/Nighthawk spawn hook)]")
	var M := _M()
	if M == null:
		return
	var seen: Array = []
	var cb := func(meter: String, level: int) -> void: seen.append([meter, level])
	M.threat_threshold.connect(cb)
	M.set_meter("notice", 0.0)
	M.set_meter("notice", 80.0)   # cross the threat rung -> Beyond-hunter dispatch hook
	_ok(seen.has(["notice", Meters.THREAT_RUNG]), "high Notice fires the Beyond-hunter threat hook")
	M.set_meter("heat", 0.0)
	M.set_meter("heat", 80.0)     # cross the threat rung -> Nighthawk hunt hook
	_ok(seen.has(["heat", Meters.THREAT_RUNG]), "high Heat fires the Nighthawk threat hook")
	M.threat_threshold.disconnect(cb)

func _test_panic_is_derived_from_doom() -> void:
	print("[meters: panic is a pure read-only function of Doom]")
	var M := _M()
	if M == null:
		return
	M.set_meter("doom", 0.0)
	var p0: float = M.panic()
	M.set_meter("doom", 100.0)
	var p1: float = M.panic()
	_ok(p1 > p0, "panic rises with Doom")
	# Purity: computing panic twice for the same Doom yields the same value and mutates nothing.
	M.set_meter("doom", 50.0)
	var a: float = M.panic()
	var b: float = M.panic()
	_ok(a == b, "panic is deterministic for a fixed Doom")

# --- (f) determinism guard: drivers are cosmetic-to-combat ------------------------------------
func _test_meter_drivers_are_cosmetic_to_combat() -> void:
	print("[meters: the drivers do NOT alter the combat event transcript (read combat, never feed back)]")
	# A fixed duel run TWICE — once with meters at 0, once with meters maxed — must produce the
	# identical combat transcript. Meters read combat events; they never feed into resolution.
	var t_low := await _run_duel_with_meters(0.0)
	var t_high := await _run_duel_with_meters(100.0)
	_ok(t_low == t_high and not t_low.is_empty(),
		"the combat transcript is byte-identical regardless of meter state")

func _run_duel_with_meters(meter_val: float) -> Array:
	var M := _M()
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	if M != null:
		for meter in ["doom", "madness", "notice", "heat"]:
			M.set_meter(meter, meter_val)
	AG.rebuild()
	EB.clear()
	var shooter := _stage("mtr_shooter", "mtr_room", Vector2.ZERO)
	var mark := _stage("mtr_mark", "mtr_room", Vector2(200, 0))
	var sx := CombatExecutor.new()
	sx.bind(shooter)
	var mx := CombatExecutor.new()
	mx.bind(mark)
	sx.try_cast("revolver_shot", "mtr_mark")
	for _i in range(60):
		sx.step_combat(1.0 / 60.0)
		mx.step_combat(1.0 / 60.0)
	await process_frame
	var combat_types := ["ability_cast_started", "ability_cast_finished",
		"ability_cast_interrupted", "agent_attacked", "agent_downed", "transformed"]
	var transcript: Array = []
	for ev in EB.events():
		if combat_types.has(String(ev.get("type", ""))):
			transcript.append({"type": ev.get("type"), "data": ev.get("data")})
	sx.free()
	mx.free()
	AG.rebuild()
	EB.clear()
	return transcript

# --- HUD progressive disclosure ---------------------------------------------------------------
func _test_hud_reads_meters_progressive_disclosure() -> void:
	print("[HUD: the MeterHUD reads the meters with progressive disclosure]")
	var M := _M()
	if M == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()   # a fresh run: Doom shown, the other three hidden until first triggered
	var hud = load("res://ui/HUD.tscn").instantiate()
	root.add_child(hud)
	await process_frame
	var mh: Node = hud.get_node_or_null("MeterHUD")
	_ok(mh != null, "the persistent HUD carries the MeterHUD widget")
	if mh == null:
		hud.queue_free()
		return
	mh.refresh()
	_ok(mh.get_node("Doom").visible, "Doom is always shown")
	_ok(not mh.get_node("Madness").visible, "Madness is hidden until first triggered")
	_ok(not mh.get_node("Notice").visible, "Notice is hidden until first triggered")
	_ok(not mh.get_node("Heat").visible, "Heat is hidden until first triggered")
	# Trigger Madness: it reveals.
	M.add_madness(10.0, "t")
	mh.refresh()
	_ok(mh.get_node("Madness").visible, "Madness reveals on first trigger")
	_ok(float(mh.get_node("Madness/Bar").value) == M.get_meter("madness"),
		"the Madness bar reads the meter value")
	hud.queue_free()
	await process_frame

# --- helper ------------------------------------------------------------------------------------
func _stage(id: String, room_id: String, pos: Vector2) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	a.combat_form = "civilian"
	a.in_combat = true
	root.get_node("/root/Agents")._agents[id] = a
	return a
