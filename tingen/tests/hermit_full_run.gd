extends SceneTree
## M33 — the HERMIT FULL-RUN INTEGRATION HARNESS. The Hermit counterpart to tests/full_run.gd (which
## is Hunter-only): it proves the WHOLE HERMIT LOOP CLOSES end-to-end, in ONE continuous run, through
## the REAL autoloads + live seams — not per-milestone unit calls. full_run proves the Hunter loop;
## combat_sim scenarios G/H prove each Hermit adversary's two-phase fight resolves deterministically;
## THIS harness proves they compose into a single playable Hermit run: pick Hermit at the New-Run
## picker -> hunt BOTH Hermit prey down through real combat -> harvest each dropped Characteristic off
## the ground -> digest via the LIVE advance verb -> climb Seq 9->8->7 -> reach a Ritual Night WIN.
##
## Run:  godot --headless --path tingen -s tests/hermit_full_run.gd
## Also folded into the main suite (run_tests.gd `_test_hermit_full_run`) via the SAME run_all() entry.
##
## Structure — one live Hermit run driven beat by beat, each printing a PASS/FAIL trace line:
##   Beat 1  A first WIN unlocks Hermit; the mounted BootController New-Run flow PRESENTS the pathway
##           picker; picking Hermit starts a LIVE Hermit run (Seq 9) in the lodging. (mirrors the M30
##           live-reachability wire, but as the OPENING of the continuous run the rest of the beats play.)
##   Beat 2  Hunt old_neil (the Seq-9 prey) through the REAL combat path: a pursuing player-bot pressures
##           him, his combat MODE flips, his hp_below reflex descends neil_human -> neil_monster, and the
##           bot puts him DOWN. The kill DROPS a hermit_characteristic on the ground; harvest it off the
##           ground (RoomItems.take_near) and DIGEST it via the LIVE Interactable advance verb -> Seq 9->8,
##           astral_chains unlocked.
##   Beat 3  Hunt ledger_finch (the Seq-8 prey) the same way (finch_human -> finch_monster), harvest +
##           digest her Characteristic via the SAME live verb -> Seq 8->7, collapsing_star unlocked. The
##           SECOND advance is fed by a SECOND real kill — the ladder closes on real hunts, not injection.
##   Beat 4  Drive Doom -> 100 -> Ritual Night starts -> take the interrupt WIN path (altar/celebrant) ->
##           backlash wave -> end_run('win') fires EXACTLY once, the run ends, no softlock (mirrors
##           full_run's win arm).
##
## Constraints preserved: the fights reuse combat_sim's deterministic executor machinery (fixed dt, no
## RNG-in-combat, no wall time); transformation only via each form's authored descend reflex; the world
## clock advances during the fight (never pauses). Nothing here edits combat vectors or City.tscn.
## Every failure path routes through _quit (a bare failed assert would hang the tree forever).

const DT: float = 1.0 / 60.0

## The player-bot: a fat pool so the monster lands work while being put down, but the fight still ENDS
## with the prey downed. Unlike the butcher (who charges in), the Hermit prey are CAUTIOUS long-range
## casters who kite — so the bot PURSUES (closes to revolver range) instead of merely strafing, else a
## kiter is never in the firing line and the hunt never resolves. Determinism is unchanged (fixed dt).
const PROXY_HP: float = 2000.0
const SHOT_PERIOD_S: float = 3.0
const PURSUE_SPEED: float = 220.0   # px/s — keeps pace with a fleeing caster
const PURSUE_RANGE: float = 260.0   # hold ~inside revolver range so telegraphed shots actually land

var _pass: int = 0
var _fail: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()
	var r: Dictionary = await run_all()
	print("\n=== hermit_full_run: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd. Coroutine (mounts the boot
## controller + awaits frames), so callers must `await run_all()`.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	print("=== hermit_full_run: the whole HERMIT loop, end-to-end, through the real systems ===")
	await _beat1_pick_hermit(c, root)
	await _beat2_hunt(c, root, "old_neil", "neil_monster", 8, "astral_chains", "hermit_full_arena_neil")
	await _beat3_hunt(c, root, "ledger_finch", "finch_monster", 7, "collapsing_star", "hermit_full_arena_finch")
	_beat4_ritual_night_win(c, root)
	# Leave a clean Hunter world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/Progression").select_pathway("hunter")
	CombatExecutor.reset_last_attackers()
	return c

# --- trace helpers ----------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> bool:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)
	return cond

static func _n(root: Node, name: String) -> Object:
	return root.get_node_or_null("/root/" + name)

# ==============================================================================================
# BEAT 1 — a first WIN unlocks Hermit; the New-Run picker selects Hermit; a live Hermit run begins
# ==============================================================================================
static func _beat1_pick_hermit(c: Dictionary, root: Node) -> void:
	print("\n--- beat 1: first win unlocks Hermit -> New-Run picker selects Hermit -> live Hermit run ---")
	var RM: Object = _n(root, "RunManager")
	var P: Object = _n(root, "Progression")
	var AG: Object = _n(root, "Agents")

	# A first WIN writes the Hermit unlock into the persistent meta (M27/M28 payoff).
	RM.reset_meta()
	RM.start_run()
	RM.end_run("win", {"outcome": "descent_stopped"})
	RM.reload_meta()
	_check(c, P.available_pathways().has("hermit"),
		"a first win unlocked Hermit as a New-Run pathway option")

	# Mount the REAL boot controller so the New-Run flow + its pathway picker are live (not a bare
	# start_run('hermit') in isolation — the M30 wire, driven here as the run's opening).
	var main: Node = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)
	await root.get_tree().process_frame
	_check(c, main.is_in_group("game_controller"), "the boot controller mounted as the live game_controller")
	_check(c, main.is_at_title(), "the win returned the boot controller to the title (New Run reachable)")

	# New Run -> with >1 pathway unlocked the flow PRESENTS the picker; pick Hermit through the REAL button.
	main.start_new_run()
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, main.pathway_picker_active(),
		"with Hermit unlocked the New-Run flow PRESENTS a pathway picker")
	_check(c, main.pathway_picker_options().has("hermit") and main.pathway_picker_options().has("hunter"),
		"the picker offers both the unlocked Hermit build and the always-available Hunter build")
	main.choose_pathway("hermit")
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	_check(c, P.pathway() == "hermit" and P.sequence() == 9,
		"picking Hermit started a LIVE Hermit run at Seq 9 (the continuous run the rest of the beats play)")
	_check(c, String(main.current_scene_path) == "res://scenes/IntroRoom.tscn" and main.get_player() != null,
		"…and woke a live player body in the lodging")

	# Free the boot controller: the RUN stays live (RunManager/Progression are autoloads — freeing the
	# scene does NOT end the run) and beats 2-4 continue it through the autoload seams (full_run's shape).
	# Quiet the deliberation loop so the mounted world's residue can't tick during the staged fights.
	var ART: Object = _n(root, "AgentRuntime")
	if ART != null:
		ART.auto_run = false
	main.queue_free()
	await root.get_tree().process_frame
	AG.rebuild()   # a clean roster for the staged hunts (neil/finch carry pathway:hermit)
	_check(c, RM.run_active() and P.pathway() == "hermit",
		"the Hermit run is STILL live after the title scene is freed (one continuous run)")

# ==============================================================================================
# BEAT 2 / BEAT 3 — hunt a Hermit prey down (real combat) -> harvest -> live digest -> advance
# ==============================================================================================
static func _beat2_hunt(c: Dictionary, root: Node, prey: String, monster_form: String,
		want_seq: int, want_art: String, arena: String) -> void:
	print("\n--- beat 2: hunt %s (real combat) -> harvest -> live digest -> advance Seq 9->%d (%s) ---"
		% [prey, want_seq, want_art])
	await _hunt_harvest_digest(c, root, prey, monster_form, want_seq, want_art, arena)

static func _beat3_hunt(c: Dictionary, root: Node, prey: String, monster_form: String,
		want_seq: int, want_art: String, arena: String) -> void:
	print("\n--- beat 3: hunt %s (real combat) -> harvest -> live digest -> advance Seq 8->%d (%s) ---"
		% [prey, want_seq, want_art])
	await _hunt_harvest_digest(c, root, prey, monster_form, want_seq, want_art, arena)

## The shared hunt beat: stage the prey + a pursuing fat player-bot at night, DOWN the prey through the
## real combat path (mode-flip -> two-phase descent -> agent_downed), HARVEST the dropped Characteristic
## off the ground, DIGEST it via the LIVE Interactable advance verb, and assert the ladder advanced +
## the rank's art unlocked. Every seam here is the one the live player walks.
static func _hunt_harvest_digest(c: Dictionary, root: Node, prey: String, monster_form: String,
		want_seq: int, want_art: String, arena: String) -> void:
	var AG: Object = _n(root, "Agents")
	var EB: Object = _n(root, "EventBus")
	var Clk: Object = _n(root, "Clock")
	var P: Object = _n(root, "Progression")
	var DB: Object = _n(root, "AbilityDB")
	var RI: Object = _n(root, "RoomItems")

	var seq_before: int = P.sequence()

	# --- stage: the prey (its npcs.json def, worn human form) + a fat pursuing player-bot, at night. ---
	var adv: Agent = AG.get_agent(prey)
	_check(c, adv != null and String(adv.pathway) == "hermit",
		"%s stands in the roster carrying pathway:hermit (a Hermit-pathway prey)" % prey)
	adv.room = arena
	adv.position = Vector2(520, 300)
	adv.vision_r = 600.0
	adv.hp = adv.max_hp
	adv.downed = false
	adv.in_combat = false

	var proxy: Agent = AG.ensure_player_proxy(Vector2(300, 300), arena)
	proxy.vision_r = 600.0
	proxy.max_hp = PROXY_HP
	proxy.hp = PROXY_HP
	proxy.downed = false
	proxy.in_combat = false
	Clk.set_time(2, 1410)   # 23:30 — the hunt happens at night (the reveal/witness window)

	CombatExecutor.reset_last_attackers()
	var bx := CombatExecutor.new()
	bx.bind(proxy)                    # the player-bot fires the SAME executor machinery the M5 player uses
	var ax: CombatExecutor = null     # the prey's executor binds only when its combat MODE flips (NPC seam)

	var tf := {"count": 0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == prey:
			tf["count"] = int(tf["count"]) + 1
	EB.event_logged.connect(on_tf)

	var next_shot := 0.0
	var mode_flipped := false
	var downed := false
	var start_minutes: int = Clk.day * 1440 + Clk.minute_of_day
	for frame in range(90 * 60):
		var t := frame * DT
		if adv.in_combat and ax == null:
			mode_flipped = true
			ax = CombatExecutor.new()
			ax.bind(adv)
			ax.enable_tactics()
		if not adv.downed and not proxy.downed:
			# PURSUE: close to revolver range on the kiting caster so telegraphed shots actually land.
			var to: Vector2 = adv.position - proxy.position
			if to.length() > PURSUE_RANGE:
				proxy.position += to.normalized() * PURSUE_SPEED * DT
			if bx.phase == "idle" and t >= next_shot:
				if bool(bx.try_cast("revolver_shot", prey).get("ok", false)):
					next_shot = t + SHOT_PERIOD_S
		if ax != null:
			ax.step_combat(DT)
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		if frame % 60 == 59:
			Clk.advance_minutes(1)   # the WORLD CLOCK advances during the fight — no combat pause
		if adv.downed:
			downed = true
			break
	EB.event_logged.disconnect(on_tf)
	if ax != null:
		ax.free()
	bx.free()

	_check(c, mode_flipped, "damage flipped %s into combat mid-fight (the NPC combat-mode seam)" % prey)
	_check(c, int(tf["count"]) == 1 and adv.combat_form == monster_form,
		"%s descended to its monster form %s exactly once (the two-phase reflex, live in the run)" % [prey, monster_form])
	_check(c, downed and adv.downed,
		"the player put %s DOWN through the real combat path (never deleted)" % prey)
	var end_minutes: int = Clk.day * 1440 + Clk.minute_of_day
	_check(c, end_minutes > start_minutes,
		"the world clock advanced throughout the hunt (+%d game minutes)" % (end_minutes - start_minutes))

	# --- the kill DROPS a hermit_characteristic on the ground; HARVEST it via the LIVE walk-over
	# pickup seam — a real Player body mounted where the prey fell, PlayerCombat's physics-frame
	# proximity gather doing the work (B1 retro: a naked RoomItems.take_near(...,999) call here is
	# exactly how this harness used to MASK the missing live seam — this beat now FAILS if the
	# walk-over gather is unwired). ---
	_check(c, RI.count(arena, "hermit_characteristic") >= 1,
		"downing %s DROPPED a hermit_characteristic where it fell (a real kill -> a real drop)" % prey)
	var pbody: Node = (load("res://scenes/Player.tscn") as PackedScene).instantiate()
	root.add_child(pbody)
	(pbody as Node2D).global_position = adv.position
	for _i in 8:
		await root.get_tree().physics_frame
	pbody.free()
	_check(c, RI.count(arena, "hermit_characteristic") == 0,
		"the player HARVESTED the Characteristic off the ground via the LIVE walk-over seam (the drop is gone from the world)")
	_check(c, proxy.item_count("hermit_characteristic") >= 1, "…and it is now in the player's hands")

	# --- DIGEST it via the LIVE Interactable advance verb (the SAME verb the Hunter uses). ---
	var digest: Node = (load("res://scenes/Interactable.tscn") as PackedScene).instantiate()
	digest.digest_advance = true
	root.add_child(digest)
	await root.get_tree().process_frame
	digest._use()   # the live acting-rite + advance
	digest.free()

	_check(c, P.sequence() == want_seq,
		"the LIVE digest verb advanced the Hermit ladder %d -> %d via a real kill" % [seq_before, want_seq])
	_check(c, proxy.item_count("hermit_characteristic") == 0, "…consuming the harvested Characteristic")
	_check(c, DB.kit_for("player").has(want_art),
		"…and unlocking %s on the player kit at Seq %d" % [want_art, want_seq])

# ==============================================================================================
# BEAT 4 — Doom -> 100 -> Ritual Night -> interrupt WIN -> end_run('win') exactly once, no softlock
# ==============================================================================================
static func _beat4_ritual_night_win(c: Dictionary, root: Node) -> void:
	print("\n--- beat 4: Doom 100 -> Ritual Night -> interrupt WIN -> end_run('win') exactly once ---")
	var RM: Object = _n(root, "RunManager")
	var M: Object = _n(root, "Meters")
	var RN: Object = _n(root, "RitualNight")
	var EG: Object = _n(root, "EndGame")
	var P: Object = _n(root, "Progression")

	_check(c, RM.run_active() and P.pathway() == "hermit" and P.sequence() == 7,
		"the Hermit run is still one continuous live run at the climax (Seq 7 reached, no restart)")
	_check(c, not RN.active(), "no Ritual Night is underway before Doom tops out")

	# Drive Doom to 100 through the meter authority — the canonical §9 trigger.
	M.set_meter("doom", 100.0)
	_check(c, RM.ritual_night_reached(), "RunManager latched Ritual Night at Doom 100")
	_check(c, RN.active(), "the Ritual Night encounter STARTED (the Hermit run's climax staged)")

	# Count the run-end + the ending SCREEN to prove EXACTLY-once (no softlock, no double-end).
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

	# The interrupt WIN path: break the altar -> the surviving cult LOSES CONTROL -> clear the wave -> WIN.
	RN.use_interrupt_interactable()
	_check(c, RN.interrupted(), "the altar interrupt broke the rite")
	_check(c, RN.backlash_active(), "the interrupt spawned the backlash wave")
	_check(c, RN.backlash_monsters().size() >= 1, "surviving celebrants lost control into monster forms")
	_check(c, int(ended["n"]) == 0, "the run has NOT ended mid-wave (the fight is still on)")

	RN.clear_backlash_wave()

	# Idempotency: a redundant late tick / second interrupt must not fire a SECOND ending.
	RN.tick_fuse(9999)
	RN.use_interrupt_interactable()

	RM.run_ended.disconnect(on_end)
	EG.ending_reached.disconnect(on_screen)

	_check(c, int(ended["n"]) == 1, "end_run fired EXACTLY once (no softlock, no double-end)")
	_check(c, ended["reason"] == "win", "…with reason 'win' (the interrupt path)")
	_check(c, int(screen["n"]) == 1, "the ending SCREEN was raised exactly once")
	_check(c, RN.resolved() and not RM.run_active(),
		"the Hermit run's climax is resolved and the run has ended (the whole Hermit loop closed)")
