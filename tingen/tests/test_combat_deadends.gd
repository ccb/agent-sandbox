extends SceneTree
## M22 — two combat DEAD-ENDS that can strand a player with no path to any ending. Runs headless.
##   godot --headless --path tingen -s tests/test_combat_deadends.gd
## Also folded into the main suite (run_tests.gd `_test_combat_deadends`) via the SAME run_all()
## entry point, so both share one set of assertions.
##
## The pins:
##   B8  the Hunter kit had ZERO ammo-free damage -> a dry (0-round) player could deal NO hp damage
##       at all (an unrecoverable soft-loss). The fix adds an AMMO-FREE MELEE floor (pistol_whip) to
##       the player base kit: a dry hunter can ALWAYS chip hp, with no round consumed and no
##       'no_ammo' refusal. The art must load with a valid strike shape + a real fx texture.
##   B9  an interrupted Ritual Night froze the fuse -> a 0-ammo player who triggers the altar
##       interrupt (needs no ammo) but cannot clear the backlash wave (B8) hard-softlocked: no clock
##       forced any ending. The fix gives the BACKLASH WAVE its own backstop countdown — if the wave
##       is not cleared within N beats of the interrupt, the rite's stored power completes -> _lose.
##       So an interrupted-then-abandoned climax ALWAYS still resolves; clearing in-window still WINS.

const DT: float = 1.0 / 60.0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()
	var r: Dictionary = run_all()
	print("\n=== combat_deadends: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_b8_dry_player_has_ammo_free_floor(c, root)
	_b9_interrupt_then_abandon_still_ends(c, root)
	_b9_clearing_in_window_still_wins(c, root)
	return c

# --- B8: a dry (0-ammo) player always has an ammo-free melee floor ------------------------------
static func _b8_dry_player_has_ammo_free_floor(c: Dictionary, root: Node) -> void:
	print("[B8: a bone-dry hunter can STILL chip hp via the ammo-free melee floor]")
	var AG: Object = root.get_node("/root/Agents")
	var DB: Object = root.get_node("/root/AbilityDB")

	# The art loads with a valid strike shape + a real fx texture, and lives in the player base kit.
	_check(c, DB.has_ability("pistol_whip"), "the ammo-free melee art 'pistol_whip' loads")
	if not DB.has_ability("pistol_whip"):
		return
	var pw: Dictionary = DB.ability_for("pistol_whip")
	var pw_cost: Dictionary = pw.get("cost", {}) if pw.get("cost") is Dictionary else {}
	_check(c, String(pw.get("class", "")) == "strike", "pistol_whip is a strike (a melee floor)")
	_check(c, int(pw_cost.get("ammo", 0)) == 0, "pistol_whip costs NO ammo (a dry player can pay it)")
	_check(c, int(pw.get("range", 0)) > 0 and String(pw.get("target_type", "")) == "enemy",
		"pistol_whip has a valid melee shape (positive range, enemy target)")
	_check(c, (DB.kit_for("player") as Array).has("pistol_whip"), "pistol_whip is in the player base kit")
	var fx_path: String = CombatFxLib.texture_path(CombatFxLib.fx_id_of(pw))
	_check(c, ResourceLoader.exists(fx_path), "pistol_whip resolves a REAL fx texture (%s)" % fx_path)

	# Stage a bone-dry hunter (player form): it CARRIES the revolver but has ZERO rounds, plus a
	# stationary dummy within melee reach. This is the exact ammo-starvation dead-end.
	var hunter := Agent.new("deadend_dry_hunter")
	hunter.display_name = "deadend_dry_hunter"
	hunter.combat_form = "player"
	hunter.room = "deadend_arena"
	hunter.position = Vector2(100, 200)
	hunter.in_combat = true
	hunter.add_item("revolver", 1)            # has the gun ...
	# ... and NO revolver_round (bone dry)
	AG._agents["deadend_dry_hunter"] = hunter
	var dummy := Agent.new("deadend_dummy")
	dummy.display_name = "deadend_dummy"
	dummy.room = "deadend_arena"
	dummy.position = Vector2(150, 200)        # ~50px away, inside pistol_whip reach
	dummy.in_combat = true
	AG._agents["deadend_dummy"] = dummy

	var hex := CombatExecutor.new()
	hex.bind(hunter)
	hex.cost_provider = AgentCostProvider.new(hunter)   # the same generic ammo cost seam the player uses
	var dex := CombatExecutor.new()
	dex.bind(dummy)

	# THE DEAD-END: with 0 rounds the gun art is starved — revolver_shot refuses 'no_ammo'.
	_check(c, int(hunter.item_count("revolver_round")) == 0, "the hunter is bone dry (0 rounds)")
	var dry_shot: Dictionary = hex.try_cast("revolver_shot", "deadend_dummy")
	_check(c, not bool(dry_shot.get("ok", false)) and String(dry_shot.get("reason", "")) == "no_ammo",
		"the ammo art is starved (revolver_shot refuses 'no_ammo' — the dead-end)")

	# THE FLOOR: the ammo-free melee art casts and LANDS hp damage — the survivability floor.
	var hp0: float = dummy.hp
	var pw_verdict: Dictionary = hex.try_cast("pistol_whip", "deadend_dummy")
	_check(c, bool(pw_verdict.get("ok", false)), "the DRY hunter can cast the ammo-free melee art")
	_check(c, String(pw_verdict.get("reason", "")) != "no_ammo", "the melee floor is never refused for ammo")
	for _i in range(120):
		hex.step_combat(DT)
		dex.step_combat(DT)
		if dummy.hp < hp0:
			break
	_check(c, dummy.hp < hp0, "the dry hunter DEALT hp damage with the melee floor (%.0f -> %.0f)" % [hp0, dummy.hp])
	_check(c, int(hunter.item_count("revolver_round")) == 0, "the melee floor consumed NO round (still 0)")

	hex.free()
	dex.free()
	AG._agents.erase("deadend_dry_hunter")
	AG._agents.erase("deadend_dummy")

# --- B9: an interrupted-then-ABANDONED Ritual Night STILL resolves (no softlock) ----------------
static func _b9_interrupt_then_abandon_still_ends(c: Dictionary, root: Node) -> void:
	print("[B9: interrupt the altar, then abandon the wave -> the backstop STILL ends the run]")
	var rm: Object = root.get_node("/root/RunManager")
	var rn: Object = root.get_node("/root/RitualNight")
	var AG: Object = root.get_node("/root/Agents")

	_check(c, rn.has_method("tick_backlash") and rn.has_method("backlash_fuse_remaining"),
		"RitualNight exposes a backlash backstop (tick_backlash + backlash_fuse_remaining)")
	if not (rn.has_method("tick_backlash") and rn.has_method("backlash_fuse_remaining")):
		return

	rm.start_run()
	AG.rebuild()
	rn.reset()
	rn.force_assault(false, 4242)
	# The altar interrupt needs NO ammo — a bone-dry player can always trigger it.
	rn.use_interrupt_interactable()
	_check(c, rn.interrupted() and rn.backlash_active(), "the altar interrupt fires the backlash (no ammo needed)")
	_check(c, not rn.resolved(), "the climax is NOT resolved the instant the wave spawns")
	var window: int = int(rn.backlash_fuse_remaining())
	_check(c, window > 0, "the backlash wave carries a backstop countdown (%d beats)" % window)

	# HARDENING (M22 B9): prove the LIVE seam, not just the direct call. Emit one real Clock beat
	# post-interrupt and assert the backstop decremented THROUGH the signal delegation
	# (Clock.beat_ticked -> RitualNight._on_beat -> tick_backlash) — the live tree drives it this way.
	var CK: Object = root.get_node("/root/Clock")
	CK.beat_ticked.emit(999, 1)
	_check(c, int(rn.backlash_fuse_remaining()) == window - 1,
		"a live Clock beat pumps the backstop via _on_beat (window %d -> %d)" % [window, window - 1])
	_check(c, not rn.resolved(), "one live beat does not prematurely resolve the climax")

	# ABANDON: advance the backstop past its window WITHOUT clearing the wave (the softlock case).
	var ended := {"n": 0, "reason": ""}
	var cb := func(reason: String) -> void:
		ended["n"] = int(ended["n"]) + 1
		ended["reason"] = reason
	rm.run_ended.connect(cb)
	for _i in range(window + 1):
		rn.tick_backlash(1)
	rm.run_ended.disconnect(cb)

	_check(c, rn.resolved(), "an interrupted-then-abandoned climax STILL resolves (no softlock)")
	_check(c, int(ended["n"]) == 1, "the backstop ends the run EXACTLY once")
	_check(c, String(ended["reason"]) == "lose", "the abandoned backlash resolves to a LOSE ending")
	_check(c, String(rn.result().get("outcome", "")) == "backlash_overrun",
		"the lose result records 'backlash_overrun' (the stored power completed)")

# --- B9 (win path intact): clearing the wave WITHIN the window still WINS -----------------------
static func _b9_clearing_in_window_still_wins(c: Dictionary, root: Node) -> void:
	print("[B9: clearing the backlash within the backstop window still WINS (win path intact)]")
	var rm: Object = root.get_node("/root/RunManager")
	var rn: Object = root.get_node("/root/RitualNight")
	var AG: Object = root.get_node("/root/Agents")
	if not rn.has_method("tick_backlash"):
		return

	rm.start_run()
	AG.rebuild()
	rn.reset()
	rn.force_assault(false, 4242)
	rn.use_interrupt_interactable()
	var w := {"n": 0, "reason": ""}
	var cb := func(reason: String) -> void:
		w["n"] = int(w["n"]) + 1
		w["reason"] = reason
	rm.run_ended.connect(cb)
	rn.tick_backlash(1)   # a beat passes while the player is still fighting the wave
	_check(c, not rn.resolved(), "a partial backstop tick does not pre-empt a live, uncleared wave")
	rn.clear_backlash_wave()
	rm.run_ended.disconnect(cb)
	_check(c, String(w["reason"]) == "win", "clearing the wave inside the window still WINS")
	_check(c, int(w["n"]) == 1, "the win fires exactly once")

# --- shared -------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)
