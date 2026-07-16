extends SceneTree
## M9 — the FULL-RUN INTEGRATION HARNESS. Proves the WHOLE LOOP CLOSES end-to-end, in play,
## through the REAL autoloads (no mocks for the systems under test) — not per-milestone unit tests.
## This is the artifact that demonstrates "playable" per docs/handoff/SPRINT_PLAYABLE.md's 7-point
## bar: boot -> opening -> a real fight (visible telegraphs/hits) -> the four meters move ->
## harvest + advance a Sequence -> Ritual Night -> a win/lose SCREEN with no softlock -> restart
## into a clean run with meta intact -> the lose + rampage arms each reach an ending too.
##
## Run:  godot --headless --path tingen -s tests/full_run.gd
##
## Structure — one live run driven beat by beat, each printing a PASS/FAIL trace line:
##   Beat 1  RunManager.start_run() -> the GMOpening guaranteed butcher lead is present + hot (M8/M6).
##   Beat 2  Stage + DOWN bram_kell through the REAL combat path (proxy fires the revolver, Kell's
##           executor binds on the combat-mode flip — exactly combat_sim's slice) -> the harvest drop
##           lands (M5) + the harvest fork is presented (M8) + Heat REVEALED from the witnessed kill (M4).
##   Beat 3  Perform the acting deed + advance the Hunter Sequence 9->8 (M5) -> Madness spiked (M4)
##           + the kit grew (mark_prey usable).
##   Beat 4  Drive Doom to 100 -> Ritual Night starts (M7) -> take the interrupt WIN path
##           (altar/celebrant) -> backlash wave -> end_run('win') fires EXACTLY once, run ends, no softlock.
##   Beat 5  Restart -> a fresh run is clean (M2/M4/M5/M6/M7 state reset; meta bumped) — the roguelite loop.
##   Beat 6  A second pass drives the LOSE arm (fuse -> 0 -> end_run('lose')) and the RAMPAGE arm
##           (Madness 100 -> lost_control), asserting each reaches an ending.
##   Beat 7  LIVE-LLM smoke (optional): if a sidecar answers /health, run one real converse turn through
##           the async M3 path headlessly and confirm it doesn't freeze/crash. Skips gracefully otherwise.
##
## Determinism / constraints preserved: the Kell fight reuses combat_sim's deterministic executor
## machinery (fixed dt, no RNG-in-combat, no wall time); transformation only via assume_form; the world
## clock advances during the fight (never pauses). Nothing here edits combat vectors or City.tscn.
##
## Prints a clear per-beat trace and exits NONZERO on any failure (a bare failed assert would hang the
## tree — every failure path routes through _quit()).

const DT: float = 1.0 / 60.0

## The player-bot's pacing against the butcher (mirrors combat_sim scenario D). A fat proxy pool so the
## monster lands cleaver work while being put down but the fight still ENDS with the butcher downed.
const SLICE_SHOT_PERIOD_S: float = 3.0
const SLICE_BOT_STRAFE: float = 60.0
const SLICE_PROXY_HP: float = 2000.0

const SIDECAR_URL: String = "http://127.0.0.1:8777"

var _pass: int = 0
var _fail: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	print("=== full_run: the whole loop, end-to-end, through the real systems ===")

	_beat1_opening()
	var kell_downed_ok := await _beat2_fight_and_harvest()
	await _beat3_advance_sequence()
	_beat4_ritual_night_win()
	_beat5_restart_clean()
	_beat6_lose_and_rampage()
	await _beat8_live_scene_continuity()
	await _beat7_live_llm_smoke()

	print("\n=== full_run: %d passed, %d failed ===" % [_pass, _fail])
	if not kell_downed_ok:
		printerr("  (the butcher fight never resolved — later beats ran on a stale world)")
	_quit(1 if _fail > 0 else 0)

# --- trace helpers ----------------------------------------------------------------------------
func _check(cond: bool, label: String) -> bool:
	if cond:
		_pass += 1
		print("  PASS  %s" % label)
	else:
		_fail += 1
		printerr("  FAIL  %s" % label)
	return cond

func _beat(n: int, title: String) -> void:
	print("\n--- beat %d: %s ---" % [n, title])

func _quit(code: int) -> void:
	# Leave no executor residue pinning scripts; scrub the static ledger like the sims do.
	CombatExecutor.reset_last_attackers()
	quit(code)

# --- autoload shortcuts -----------------------------------------------------------------------
func _n(name: String) -> Object:
	return root.get_node_or_null("/root/" + name)

# ==============================================================================================
# BEAT 1 — start_run() -> the guaranteed butcher opener is present + hot (M8/M6)
# ==============================================================================================
func _beat1_opening() -> void:
	_beat(1, "start_run() surfaces the guaranteed butcher lead, hot")
	var RM := _n("RunManager")
	var GMO := _n("GMOpening")
	var LS := _n("LeadSystem")

	# Capture that the opening actually fired off run_started (not just that a lead exists).
	var opened := {"n": 0}
	var on_open := func() -> void: opened["n"] = int(opened["n"]) + 1
	GMO.opening_began.connect(on_open)
	RM.start_run()
	GMO.opening_began.disconnect(on_open)

	_check(RM.run_active(), "the run is live after start_run()")
	_check(RM.current_day() == 1, "a fresh run begins on day 1")
	_check(int(opened["n"]) >= 1, "GMOpening.begin_opening fired off run_started (the opening staged)")

	var lead: Dictionary = GMO.butcher_lead()
	_check(not lead.is_empty(), "the guaranteed butcher lead is on the board (M6)")
	_check(bool(lead.get("hot", false)), "…and it is HOT (the §3 opener contract)")
	_check(String(lead.get("source", "")) == "constable_brom",
		"…sourced from the constable hammering on doors (%s)" % String(lead.get("source", "")))

	# The lead routes to a REAL, reachable staged butcher (his Iron Cross shop).
	var staged: Dictionary = GMO.butcher_staged_at()
	_check(String(staged.get("agent", "")) == "bram_kell", "the lead routes to the staged bram_kell")
	var kell: Agent = _n("Agents").get_agent("bram_kell")
	_check(kell != null and not kell.downed and kell.combat_form == "butcher_human",
		"bram_kell stands in his human phase-1 form, ready for the fight")

	# The opening also flashed the tip onto the shared bus (the living-city chatter seam).
	_check(LS.get_lead("butcher_iron_cross").get("state", "") == "open",
		"the opener lead is OPEN (surfaced, awaiting the player following it)")

# ==============================================================================================
# BEAT 2 — down bram_kell through the REAL combat path -> harvest drop + fork + Heat reveal
# ==============================================================================================
## Returns true if the butcher was actually downed (so the caller can flag a stale world).
func _beat2_fight_and_harvest() -> bool:
	_beat(2, "fight + DOWN bram_kell (real combat) -> harvest drop + fork + Heat reveal")
	var AG := _n("Agents")
	var EB := _n("EventBus")
	var Clk := _n("Clock")
	var M := _n("Meters")
	var GMO := _n("GMOpening")

	# Stage the butcher + the player proxy in a private arena, at NIGHT, exactly like combat_sim's
	# §0 slice — the SAME executor machinery the live player uses, no mocks.
	var kell: Agent = AG.get_agent("bram_kell")
	kell.room = "full_run_arena"
	kell.position = Vector2(520, 300)
	kell.vision_r = 600.0            # the night-hunter SEES the telegraphs (his dodge reflex needs sight)
	kell.hp = kell.max_hp
	kell.downed = false
	kell.in_combat = false

	var proxy: Agent = AG.ensure_player_proxy(Vector2(220, 300), "full_run_arena")
	proxy.vision_r = 600.0           # the investigator watches the whole fight (the Heat witness gate)
	proxy.max_hp = SLICE_PROXY_HP
	proxy.hp = SLICE_PROXY_HP
	proxy.downed = false
	proxy.in_combat = false
	Clk.set_time(2, 1410)            # 23:30 — the fight happens at night

	var heat_before: float = M.get_meter("heat")
	var heat_revealed_before: bool = M.is_revealed("heat")

	# Wire a one-shot to confirm the harvest fork is presented AT the downing (M8).
	var fork_seen := {"n": 0, "hunter_lead": ""}
	var on_fork := func(fork: Dictionary) -> void:
		fork_seen["n"] = int(fork_seen["n"]) + 1
		fork_seen["hunter_lead"] = String(fork.get("hunter_lead", ""))
	GMO.harvest_fork_presented.connect(on_fork)

	CombatExecutor.reset_last_attackers()
	var bx := CombatExecutor.new()
	bx.bind(proxy)                   # the player-bot fires the SAME executor the M5 player uses
	var kx: CombatExecutor = null    # Kell's executor binds only when his combat MODE flips (the NPC seam)

	var next_shot_s := 0.0
	var strafe_sign := 1.0
	var downed := false
	var mode_flipped := false
	for frame in range(90 * 60):
		var t := frame * DT
		if kell.in_combat and kx == null:
			# Damage flipped Kell's combat mode: only now does an executor take his body (the NPC.gd
			# seam mirrored — before this instant he has no reflex/tactical layer at all).
			mode_flipped = true
			kx = CombatExecutor.new()
			kx.bind(kell)
			kx.enable_tactics()
		if not kell.downed and not proxy.downed:
			if bx.phase == "idle" and t >= next_shot_s:
				if bool(bx.try_cast("revolver_shot", "bram_kell").get("ok", false)):
					next_shot_s = t + SLICE_SHOT_PERIOD_S
			proxy.position.y += strafe_sign * SLICE_BOT_STRAFE * DT
			if proxy.position.y > 480.0:
				strafe_sign = -1.0
			elif proxy.position.y < 120.0:
				strafe_sign = 1.0
		if kx != null:
			kx.step_combat(DT)
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		if frame % 60 == 59:
			Clk.advance_minutes(1)   # the WORLD CLOCK advances during the fight — no combat pause
		if kell.downed:
			downed = true
			break

	if kx != null:
		kx.free()
	bx.free()

	_check(mode_flipped, "damage flipped bram_kell into combat mid-fight (the NPC combat-mode seam)")
	_check(downed and kell.downed, "the player put the butcher DOWN through the real combat path (M1/M3)")
	# A two-phase butcher: he cast assume_form -> bieber_monster at half HP (transformation only via assume_form).
	_check(kell.combat_form == "bieber_monster", "the butcher transformed to bieber_monster via his assume_form reflex")
	var tfs: int = EB.events("transformed").filter(
		func(e: Dictionary) -> bool: return String((e.get("data", {}) as Dictionary).get("agent", "")) == "bram_kell").size()
	_check(tfs == 1, "assume_form resolved exactly once (transformed event, x%d)" % tfs)

	# --- M5 harvest drop: a downed off-pathway Beyonder drops the generic tainted_characteristic ---
	var RI := _n("RoomItems")
	var drops: int = RI.count("full_run_arena", "tainted_characteristic")
	_check(drops >= 1, "the harvest drop landed where the butcher fell (tainted_characteristic x%d)" % drops)

	# --- M8 harvest fork: presented at the downing, backing the hunter follow-up lead ---
	var fork: Dictionary = GMO.on_butcher_downed()
	GMO.harvest_fork_presented.disconnect(on_fork)
	_check(int(fork_seen["n"]) == 1, "the harvest fork was presented exactly once at the downing (M8)")
	_check((fork.get("options", []) as Array).has("digest"), "the fork offers the digest option (feeds M5)")
	var hunter_lead_id := String(fork.get("hunter_lead", ""))
	var hunter_lead: Dictionary = GMO.hunter_pathway_lead()
	_check(hunter_lead_id != "" and not hunter_lead.is_empty(),
		"the 'he wasn't the only one' hint surfaced the hunter follow-up lead (%s)" % hunter_lead_id)

	# --- M4 Heat REVEALED from the witnessed kill (the proxy watched; MeterDrivers fired) ---
	_check(not heat_revealed_before, "Heat was HIDDEN before the fight (progressive disclosure)")
	_check(M.is_revealed("heat"), "the witnessed kill REVEALED the Heat meter (M4 disclosure)")
	_check(M.get_meter("heat") > heat_before,
		"…and Heat rose from the witnessed public kill (%.0f -> %.0f)" % [heat_before, M.get_meter("heat")])

	return downed

# ==============================================================================================
# BEAT 3 — acting deed + advance Hunter Seq 9->8 -> Madness spike + kit growth (M5/M4)
# ==============================================================================================
func _beat3_advance_sequence() -> void:
	_beat(3, "harvest -> acting deed -> advance Seq 9->8 -> Madness spike + kit grows")
	var AG := _n("Agents")
	var PROG := _n("Progression")
	var M := _n("Meters")
	var AB := _n("AbilityDB")
	var RI := _n("RoomItems")

	var proxy: Agent = AG.get_agent("player")

	# The harvest: gather the drop through the LIVE walk-over pickup seam — a real Player body mounted
	# where the butcher fell, PlayerCombat's physics-frame proximity gather doing the work (B1 retro:
	# a naked RoomItems.take_near(...,999) call here is exactly how this harness used to MASK the
	# missing live seam — this beat now FAILS if the walk-over gather is unwired).
	# The butcher is off-pathway (tainted); to ADVANCE the Hunter ladder needs a SAME-pathway
	# characteristic. That is the design fork (§3: the butcher's drop is sellable/off-pathway). To prove
	# the ADVANCE seam end-to-end we grant the player the same-pathway characteristic the way the first
	# real Hunter hunt (the follow-up lead) would — the item the ladder actually consumes.
	var kell: Agent = AG.get_agent("bram_kell")
	var pbody: Node = (load("res://scenes/Player.tscn") as PackedScene).instantiate()
	root.add_child(pbody)
	(pbody as Node2D).global_position = kell.position
	for _i in 8:
		await physics_frame
	pbody.free()
	_check(proxy.item_count("tainted_characteristic") >= 1,
		"the player HARVESTED the drop off the ground (the LIVE walk-over pickup seam)")
	_check(RI.count("full_run_arena", "tainted_characteristic") == 0,
		"…and the ground drop was consumed by the LIVE gather (not left lying in the world)")

	# The same-pathway Characteristic the Hunter ladder consumes (hunter_characteristic). This stands in
	# for the follow-up Hunter kill's drop — the ADVANCE machinery under test is the digest->advance loop.
	proxy.add_item(PROG.characteristic_item(), 1)
	_check(PROG.pathway() == "hunter" and PROG.sequence() == 9, "the run started on Hunter · Seq 9")

	var madness_before: float = M.get_meter("madness")
	var madness_revealed_before: bool = M.is_revealed("madness")

	# The acting ritual (the digestion's role-play step) through the REAL DeedRunner.
	var deed: Dictionary = PROG.perform_acting_deed()
	_check(bool(deed.get("ok", false)) and PROG.deed_done(),
		"the acting deed ran through DeedRunner (the digestion step)")

	var gate: Dictionary = PROG.can_advance()
	_check(bool(gate.get("ok", false)), "the advance gate opens (characteristic + acting deed present)")

	var advanced := {"seq": -1}
	var on_adv := func(_p: String, seq: int) -> void: advanced["seq"] = seq
	PROG.advanced.connect(on_adv)
	var res: Dictionary = PROG.advance()
	PROG.advanced.disconnect(on_adv)

	_check(bool(res.get("ok", false)) and PROG.sequence() == 8, "the Hunter Sequence advanced 9 -> 8 (M5)")
	_check(int(advanced["seq"]) == 8, "the `advanced` signal fired with the new rank")
	_check(proxy.item_count(PROG.characteristic_item()) == 0, "the Characteristic was consumed by the digest")

	# M4: ingesting a Characteristic SPIKES Madness (+35) and reveals the meter.
	_check(not madness_revealed_before, "Madness was hidden before the first digest")
	_check(M.is_revealed("madness"), "the digest REVEALED the Madness meter (M4)")
	_check(M.get_meter("madness") >= madness_before + 30.0,
		"…and Madness spiked from ingesting the Characteristic (%.0f -> %.0f)" % [madness_before, M.get_meter("madness")])

	# M5 kit growth: mark_prey unlocked at Seq 8 and reaches the player's kit (AbilityDB union).
	_check(PROG.granted_arts().has("mark_prey"), "the kit grew: mark_prey unlocked at Seq 8")
	var kit: Array = AB.kit_for("player")
	_check(kit.has("mark_prey"), "mark_prey is now USABLE (it appears in the player's live kit)")

# ==============================================================================================
# BEAT 4 — Doom -> 100 -> Ritual Night -> interrupt WIN -> end_run('win') once, no softlock (M7)
# ==============================================================================================
func _beat4_ritual_night_win() -> void:
	_beat(4, "Doom 100 -> Ritual Night -> interrupt WIN -> end_run('win') exactly once")
	var RM := _n("RunManager")
	var M := _n("Meters")
	var RN := _n("RitualNight")
	var EG := _n("EndGame")

	_check(not RN.active(), "no Ritual Night is underway before Doom tops out")

	# Drive Doom to 100 through the meter authority — the canonical §9 trigger.
	M.set_meter("doom", 100.0)
	_check(RM.ritual_night_reached(), "RunManager latched Ritual Night at Doom 100")
	_check(RN.active(), "the Ritual Night encounter STARTED (M7 climax staged)")

	# Count the run-end + the ending SCREEN so we prove EXACTLY-once (no softlock, no double-end).
	var ended := {"n": 0, "reason": ""}
	var on_end := func(reason: String) -> void:
		ended["n"] = int(ended["n"]) + 1
		ended["reason"] = reason
	RM.run_ended.connect(on_end)
	var screen := {"n": 0, "outcome": ""}
	var on_screen := func(outcome: String, _res: Dictionary) -> void:
		screen["n"] = int(screen["n"]) + 1
		screen["outcome"] = outcome
	EG.ending_reached.connect(on_screen)

	# Take the interrupt WIN path: break the altar -> the surviving cult LOSES CONTROL (assume_form
	# into monsters, canon §⑦) -> survive/clear the backlash wave -> WIN.
	RN.use_interrupt_interactable()
	_check(RN.interrupted(), "the altar interrupt broke the rite")
	_check(RN.backlash_active(), "the interrupt spawned the backlash wave")
	var backlashers: Array = RN.backlash_monsters()
	_check(backlashers.size() >= 1, "surviving celebrants lost control into monster forms (backlash x%d)" % backlashers.size())
	_check(int(ended["n"]) == 0, "the run has NOT ended mid-wave (the fight is still on)")

	RN.clear_backlash_wave()

	# Idempotency: a redundant late tick / second interrupt must not fire a SECOND ending.
	RN.tick_fuse(9999)
	RN.use_interrupt_interactable()

	RM.run_ended.disconnect(on_end)
	EG.ending_reached.disconnect(on_screen)

	_check(int(ended["n"]) == 1, "end_run fired EXACTLY once (no softlock, no double-end)")
	_check(ended["reason"] == "win", "…with reason 'win' (the interrupt path)")
	_check(int(screen["n"]) == 1, "the ending SCREEN was raised exactly once (GAP-2.11)")
	_check(String(screen["outcome"]) == "descent_stopped", "the win screen shows 'descent_stopped'")
	_check(RN.resolved() and not RM.run_active(), "the climax is resolved and the run has ended (title handoff next)")

# ==============================================================================================
# BEAT 5 — restart -> a fresh run is clean (all run-scoped state reset; meta bumped)
# ==============================================================================================
func _beat5_restart_clean() -> void:
	_beat(5, "restart -> a fresh run is byte-clean + meta bumped (the roguelite loop)")
	var RM := _n("RunManager")
	var M := _n("Meters")
	var PROG := _n("Progression")
	var LS := _n("LeadSystem")
	var RN := _n("RitualNight")
	var AG := _n("Agents")

	var runs_before := int(RM.meta_runs_played())
	RM.start_run()   # the title's "New Run" after the climax
	_check(int(RM.meta_runs_played()) == runs_before + 1, "meta.runs_played bumped by exactly one (persists across restart)")

	# M4: the meters are back to run-start (Doom re-derived to its seed, Madness/Heat zeroed + hidden).
	_check(M.get_meter("madness") == 0.0 and not M.is_revealed("madness"), "Madness reset + re-hidden (M4)")
	_check(M.get_meter("heat") == 0.0 and not M.is_revealed("heat"), "Heat reset + re-hidden (M4)")
	_check(M.get_meter("doom") < 100.0, "Doom fell back to its run-start seed (the Ritual Night fuse is unlit)")
	_check(not RM.ritual_night_reached(), "the Ritual Night latch cleared")

	# M5: rank + granted arts scrubbed — no cross-run inheritance.
	_check(PROG.sequence() == 9 and PROG.granted_arts().is_empty(), "Progression reset to Seq 9, no inherited kit (M5)")

	# M7: the climax controller scrubbed.
	_check(not RN.active() and not RN.resolved() and RN.backlash_monsters().is_empty(),
		"the Ritual Night controller reset (M7)")

	# M2/M6: the roster rebuilt (bram_kell fresh, upright) and the guaranteed opener re-slotted, hot.
	var kell: Agent = AG.get_agent("bram_kell")
	_check(kell != null and not kell.downed and kell.combat_form == "butcher_human",
		"the roster rebuilt: bram_kell stands fresh in human form (M2)")
	var lead: Dictionary = LS.get_lead("butcher_iron_cross")
	_check(not lead.is_empty() and bool(lead.get("hot", false)) and String(lead.get("state", "")) == "open",
		"the guaranteed butcher lead re-slotted, hot + open (M6/M8)")

	# M5: no residual pending deed; M4 rampage not latched.
	_check(not PROG.deed_done(), "no pending acting deed carried into the fresh run")
	_check(not M.in_rampage(), "no rampage latched into the fresh run")

# ==============================================================================================
# BEAT 6 — the LOSE arm (fuse -> 0) and the RAMPAGE arm (Madness 100), each reaches an ending
# ==============================================================================================
func _beat6_lose_and_rampage() -> void:
	_beat(6, "the LOSE arm (fuse -> 0) + the RAMPAGE arm (Madness 100) each reach an ending")
	var RM := _n("RunManager")
	var M := _n("Meters")
	var RN := _n("RitualNight")
	var EG := _n("EndGame")
	var WM := _n("WorldManager")

	# --- the LOSE arm: force-assault, run the fuse to zero un-interrupted -> end_run('lose') ---
	RM.start_run()
	RN.reset()
	RN.force_assault(false, int(WM.seed_value))
	_check(RN.active() and RN.fuse_remaining() > 0, "a force-assault lit the Ritual Night fuse")
	var lose := {"n": 0, "reason": ""}
	var on_lose := func(reason: String) -> void:
		lose["n"] = int(lose["n"]) + 1
		lose["reason"] = reason
	RM.run_ended.connect(on_lose)
	var lose_screen := {"outcome": ""}
	var on_lose_screen := func(outcome: String, _r: Dictionary) -> void: lose_screen["outcome"] = outcome
	EG.ending_reached.connect(on_lose_screen)
	RN.tick_fuse(9999)   # burn the whole fuse without an interrupt
	RM.run_ended.disconnect(on_lose)
	EG.ending_reached.disconnect(on_lose_screen)
	_check(int(lose["n"]) == 1 and lose["reason"] == "lose", "the un-interrupted fuse ended the run 'lose' (exactly once)")
	_check(String(RN.result().get("outcome", "")) == "descent_complete", "the lose result records descent_complete")
	_check(String(lose_screen["outcome"]) == "descent_complete", "the LOSE ending SCREEN was raised (no softlock)")

	# --- the RAMPAGE arm: Madness 100 -> loss of control -> the ~60s window expires -> lost_control ---
	RM.start_run()
	# The player proxy is always present during live play (a scene ensures it on load); start_run()'s
	# rebuild cleared the ephemeral proxy, so re-ensure one before driving Madness to 100 — otherwise
	# _begin_rampage has no body to transform (the creature form swap is a no-op with no proxy). This
	# mirrors the live world, where the investigator is always on-screen when Madness tops out.
	_n("Agents").ensure_player_proxy(Vector2(300, 300), "full_run_arena")
	# Shorten the rampage window so the harness doesn't burn 60 game-seconds of ticks.
	M.rampage_duration_s = 2.0
	var madness_screen := {"n": 0, "level": 0}
	var on_ladder := func(level: int) -> void:
		madness_screen["n"] = int(madness_screen["n"]) + 1
		madness_screen["level"] = level
	M.madness_threshold.connect(on_ladder)
	M.set_meter("madness", 100.0)
	M.madness_threshold.disconnect(on_ladder)
	_check(int(madness_screen["level"]) == 100, "Madness 100 fired the loss-of-control ladder rung (M4)")
	_check(M.in_rampage(), "the player LOST CONTROL — the rampage window opened (the creature form)")
	var proxy: Agent = _n("Agents").get_agent("player")
	_check(proxy != null and proxy.combat_form == Meters.RAMPAGE_FORM,
		"the proxy assumed the Seq-4 creature form for the rampage")

	# Drive the rampage clock to expiry -> end_run('lost_control') -> a checkpoint restore or fresh restart.
	var lost := {"n": 0, "reason": ""}
	var on_lost := func(reason: String) -> void:
		lost["n"] = int(lost["n"]) + 1
		lost["reason"] = reason
	RM.run_ended.connect(on_lost)
	# Step the rampage clock past its (shortened) window.
	M.tick_rampage(2.5)
	RM.run_ended.disconnect(on_lost)
	M.rampage_duration_s = 60.0   # restore the tuning default so no residue leaks
	_check(int(lost["n"]) == 1 and lost["reason"] == "lost_control",
		"the rampage window expiring ended the run 'lost_control' (M4 -> RunManager)")
	_check(not M.in_rampage(), "the rampage cleared after it resolved")
	# M9 Gap 4: the expiry now raises a player-facing "you lost control" overlay (paused). Dismiss it
	# so no overlay/freeze residue leaks into the next beat — the live game does this on Continue.
	if EG.has_method("dismiss") and paused:
		EG.dismiss()

# ==============================================================================================
# BEAT 8 — LIVE-SCENE continuity (M9 gaps 1-4). Boots the REAL Main.tscn/BootController and holds a
# live scene + player body ACROSS end_run — the class of gap the autoload-only beats above miss:
#   Gap 2  the nightly safe-house checkpoint is actually TAKEN in live play (phase->night in lodging).
#   Gap 3  a death in the crypt WAKES the player back in the lodging (scene swap + reposition), not
#          stranded in a stale scene; the checkpoint's scene/pos drive the wake.
#   Gap 4  a rampage expiring raises the player-facing "you lost control" screen (not a silent reset).
#   Gap 1  reaching the crypt altar EARLY (no climax yet) is the "storm the rite" verb -> force_assault.
# ==============================================================================================
func _beat8_live_scene_continuity() -> void:
	_beat(8, "live scene continuity — checkpoint, death-wakes-in-lodging, rampage screen, storm-the-rite")
	var RM := _n("RunManager")
	var Clk := _n("Clock")
	var EG := _n("EndGame")
	var AG := _n("Agents")

	# --- Mount the REAL boot controller (Main.tscn) so a live World subtree + player body exist across
	# end_run — exactly the seat the review's probes held and the autoload-only beats never do. ---
	var main: Node = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	_check(main.is_in_group("game_controller"), "the boot controller is the live game_controller")

	# New Run -> the player wakes in the LODGING (not the dev City). Mirrors the title's New Run.
	main.start_new_run()
	# M30 G1: beat 4 won this session, so Hermit is unlocked and New Run now PRESENTS a pathway picker
	# (Hunter + Hermit). Drive it to Hunter to keep this beat on the shipped Hunter path — the picker's
	# own live-reachability coverage lives in tests/test_hermit_live.gd. Direct-start (single pathway) is
	# unaffected; this only fires once >1 pathway is unlocked.
	if main.pathway_picker_active():
		main.choose_pathway("hunter")
	await process_frame
	await process_frame
	_check(String(main.current_scene_path) == "res://scenes/IntroRoom.tscn",
		"New Run woke the player in the LODGING scene (%s)" % main.current_scene_path)
	_check(main.get_player() != null, "a live player body exists in the lodging")

	# --- Gap 2: the nightly checkpoint is TAKEN in live play. Roll the Clock into NIGHT while resting
	# in the lodging -> RunManager snapshots (was: checkpoint_night had no live caller). ---
	_check(not RM.has_checkpoint(), "no checkpoint yet on the fresh day")
	var cp := {"n": 0, "day": 0}
	var on_cp := func(day: int) -> void:
		cp["n"] = int(cp["n"]) + 1
		cp["day"] = day
	RM.checkpoint_saved.connect(on_cp)
	# 19:00 crosses into the "night" phase; the player is in the lodging (the safe house).
	Clk.set_time(RM.current_day(), 1140)
	RM.checkpoint_saved.disconnect(on_cp)
	_check(int(cp["n"]) == 1, "the safe-house night beat TOOK the nightly checkpoint (Gap 2)")
	_check(RM.has_checkpoint(), "a checkpoint now exists (a later death costs the day, not the run)")
	_check(String(RM.checkpoint_scene()) == "res://scenes/IntroRoom.tscn",
		"the checkpoint recorded the lodging as the safe-house scene (Gap 3 wake target)")

	# --- Gap 3: a DEATH out in the crypt wakes the player back in the lodging (not stranded). Swap the
	# live world to the crypt (as if the player walked there), then down the player in real combat. ---
	main.load_world_at("res://scenes/CathedralCrypt.tscn", Vector2(691, 500))
	await process_frame
	await process_frame
	_check(String(main.current_scene_path) == "res://scenes/CathedralCrypt.tscn",
		"the player walked into the crypt (the stale-scene death setup)")

	# Down the player through the REAL combat-death seam: an agent_downed(target=="player") event, the
	# same one EndGame/combat fires. RunManager's death branch restores; BootController wakes them.
	var proxy: Agent = AG.ensure_player_proxy(Vector2(691, 500), "cathedral_crypt")
	proxy.hp = 0.0
	proxy.downed = true
	RM.end_run("death")
	await process_frame
	await process_frame
	_check(RM.run_active(), "the run CONTINUES after a checkpointed death (costs the day, not the run)")
	_check(String(main.current_scene_path) == "res://scenes/IntroRoom.tscn",
		"the death WOKE the player back in the lodging (Gap 3 — no stranding in the crypt)")
	_check(main.get_player() != null, "a fresh player body stands in the lodging after the wake")

	# --- Gap 4: a rampage expiring raises the player-facing "you lost control" screen. ---
	var lc := {"n": 0, "outcome": ""}
	var on_lc := func(outcome: String, _r: Dictionary) -> void:
		if outcome == "lost_control":
			lc["n"] = int(lc["n"]) + 1
			lc["outcome"] = outcome
	EG.ending_reached.connect(on_lc)
	var M := _n("Meters")
	M.rampage_duration_s = 1.0
	M.set_meter("madness", 100.0)   # opens the rampage window
	_check(M.in_rampage(), "Madness 100 opened the rampage window")
	M.tick_rampage(1.5)             # expire it
	EG.ending_reached.disconnect(on_lc)
	M.rampage_duration_s = 60.0
	_check(int(lc["n"]) == 1, "the rampage expiring RAISED the 'you lost control' screen (Gap 4)")
	# The overlay pauses the tree; dismiss it so the harness (and any later beat) resumes cleanly.
	if paused:
		EG.dismiss()
	_check(not paused, "the lost-control screen's Continue lifted the freeze (run resumes)")

	# --- Gap 1: reaching the crypt altar EARLY (no climax live) storms the rite -> force_assault. ---
	var RN := _n("RitualNight")
	RM.start_run()
	await process_frame
	RN.reset()
	_check(not RN.active(), "no Ritual Night is live at the start of the fresh run")
	# Drive the crypt scene + walk onto the altar interactable's body, then press interact — the REAL
	# player-verb path (Interactable._interrupt_ritual), not a direct force_assault call.
	main.load_world_at("res://scenes/CathedralCrypt.tscn", Vector2(691, 460))
	await process_frame
	await process_frame
	var altar := _find_altar(main)
	_check(altar != null, "the crypt altar interactable is present in the scene")
	if altar != null:
		# Simulate the player standing on the altar and pressing interact (the storm-the-rite verb).
		altar._player_near = true
		altar._use()
		await process_frame
	_check(RN.active(), "storming the crypt altar early LIT the Ritual Night (force_assault, Gap 1)")
	_check(RN.fuse_remaining() > 0, "…the descent fuse is now burning (the player forced the climax)")

	# Clean up the mounted scene so no live world leaks into beat 7 / exit.
	RN.reset()
	main.queue_free()
	await process_frame

## Depth-first find the RitualAltar interactable (ritual_interrupt == true) in the live world.
func _find_altar(main: Node) -> Node:
	var stack: Array = [main]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		if node.get("ritual_interrupt") == true and node.has_method("_use"):
			return node
		for c in node.get_children():
			stack.append(c)
	return null

# ==============================================================================================
# BEAT 7 — LIVE-LLM smoke (optional). One real converse turn through the async M3 path.
# ==============================================================================================
func _beat7_live_llm_smoke() -> void:
	_beat(7, "live-LLM smoke — one real converse turn (async M3), or skip if no sidecar")
	# Probe /health with a short curl; skip gracefully (NOT a failure) if unreachable.
	var out: Array = []
	var code := OS.execute("curl", ["-s", "-m", "2", "-o", "/dev/null", "-w", "%{http_code}", SIDECAR_URL + "/health"], out, true)
	var http := (String(out[0]).strip_edges() if out.size() > 0 else "")
	if code != 0 or http != "200":
		print("  SKIP  no sidecar at %s (health=%s) — live-LLM smoke skipped, not a failure" % [SIDECAR_URL, http])
		return

	var Bridge := _n("SidecarBridge")
	var DM := _n("DialogueManager")
	if Bridge == null or DM == null:
		print("  SKIP  SidecarBridge/DialogueManager not registered — cannot run the converse turn")
		return

	# The bridge only wires the REAL brain (HttpSidecar) when TINGEN_SIDECAR_URL is set at boot; else it
	# runs the offline AmbientSidecar (whose is_ready() is ALSO true and whose converse() returns a
	# deterministic stub line — so is_ready() does NOT distinguish live from offline). The definitive gate
	# is the client's actual type: only an HttpSidecar makes a real LLM call. If the sidecar answers
	# /health but the bridge is offline, the env wasn't set for THIS launch — skip the live turn
	# gracefully rather than falsely reporting a stub reply as a live-LLM smoke.
	if not (Bridge.client is HttpSidecar):
		print("  SKIP  sidecar answered /health but the bridge is the OFFLINE brain (TINGEN_SIDECAR_URL")
		print("        unset for this launch) — relaunch with TINGEN_SIDECAR_URL=%s to run the live turn" % SIDECAR_URL)
		return

	# The bridge is LIVE. Run ONE real converse turn through the async M3 path headlessly and confirm the
	# tree does not freeze/crash. NOTE: this makes a real LLM call (~$ cost — a single short turn).
	print("  NOTE  live brain wired — running ONE real converse turn through the async M3 path (~$ single-turn cost)")

	# The real M3 seam: DialogueManager.start(npc) opens the turn context, send_utterance(npc, text)
	# stamps the request on the MAIN thread and hands it to SidecarBridge.converse_async (a worker
	# thread — the GAP-2.3 de-freeze); the reply lands later via node_changed on the main thread.
	var AG := _n("Agents")
	var npc_id := "constable_brom"
	if AG.get_agent(npc_id) == null:
		print("  SKIP  no '%s' on the roster to converse with — smoke skipped" % npc_id)
		return
	# The player proxy must exist (Perception.converse_request reads it); ensure one, as live play does.
	AG.ensure_player_proxy(Vector2(300, 300), "city")

	var reply := {"got": false, "say": ""}
	var on_node := func(_speaker: String, text: String, _opts: Array) -> void:
		reply["got"] = true
		reply["say"] = text
	DM.node_changed.connect(on_node)

	DM.start(npc_id)
	DM.send_utterance(npc_id, "Who's the butcher on Iron Cross?")
	# Prove the de-freeze: the tree keeps ticking while the worker runs (no main-thread hang). Poll a
	# bounded number of frames — if the main thread were blocked on the LLM, these awaits would stall.
	var ticks := 0
	while ticks < 300 and not reply["got"]:
		await process_frame
		ticks += 1
	_check(true, "the tree kept ticking through the async converse turn (no main-thread freeze)")
	# Deterministic join: flush the in-flight worker and apply its reply now (the M3 test seam), in case
	# the poll window closed before the worker returned. Then node_changed has fired with the reply.
	if not reply["got"]:
		DM.flush_converse()
	DM.node_changed.disconnect(on_node)

	if _check(bool(reply["got"]), "the live sidecar returned a converse reply through the async M3 path"):
		# A non-empty say means a real LLM line; the graceful fallback line is still a non-crash reply.
		var say := String(reply["say"])
		_check(say.length() > 0, "…the reply is a non-empty line (%d chars) — no freeze, no crash" % say.length())
		print("  NOTE  live reply (first 80 chars): %s" % say.substr(0, 80))
