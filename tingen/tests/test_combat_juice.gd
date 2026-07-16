extends SceneTree
## M24 (backlog "M19") — Tier-1 combat JUICE. Runs headless:
##   godot --headless --path tingen -s tests/test_combat_juice.gd
## Also folded into the main suite (run_tests.gd `_test_combat_juice`) via the SAME run_all()
## entry point, so both share one set of assertions.
##
## The juice is a PURELY COSMETIC, LIVE-ONLY, READ-ONLY companion on the combat lifecycle events
## (extends the M10 CombatFeedback autoload). Four pins:
##   (a) the PLAYER landing a hit (agent_attacked actor==player) -> a brief global HIT-STOP + a small
##       shake/kick, each GATED by a Settings toggle (a gated-off call is a verified no-op).
##   (b) the STRUCK enemy body whitens for a beat on agent_attacked, then restores (gated hit_flash).
##   (c) transformed -> a BIG shake (the mask-drop signature beat); agent_downed -> a MEDIUM shake +
##       a beat of hit-stop (the kill punch). Magnitudes tier: transform > downed > hit-kick.
##   (d) DETERMINISM: the juice NEVER perturbs the combat_sim transcript — a fixed-dt fight is
##       byte-identical with the juice Settings ON vs OFF (the hit-stop is a LIVE-ONLY time_scale dip
##       the headless fixed-dt sim never observes; shake/whiten are cosmetic camera/sprite writes).

const DT: float = 1.0 / 60.0

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = await run_all()
	print("\n=== combat_juice: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd. A coroutine (one step
## awaits a frame), so callers must `await run_all()`.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_player_hit_triggers_hitstop_and_shake_gated(c, root)
	await _b_struck_enemy_whitens_then_restores(c, root)
	_c_transform_big_shake_downed_shake_plus_hitstop(c, root)
	_d_juice_never_alters_combat_sim_transcript(c, root)
	return c

# --- (a) player-landed hit -> hit-stop + shake, both Settings-gated -----------------------------
static func _a_player_hit_triggers_hitstop_and_shake_gated(c: Dictionary, root: Node) -> void:
	print("[a: a PLAYER-landed hit fires the hit-stop + shake helpers, gated by Settings]")
	var S: Object = root.get_node_or_null("/root/Settings")
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	_check(c, FB != null and S != null, "Settings + CombatFeedback autoloads present")
	if FB == null or S == null:
		return
	S.reset_defaults()
	S.set_value("screen_shake", true)
	S.set_value("hit_stop", true)
	var ev := {"type": "agent_attacked", "data": {"actor": "player", "target": "juice_enemy", "damage": 12.0, "target_hp": 40.0, "downed": false}}
	FB.reset_probe()
	FB._on_event(ev)
	_check(c, FB.last_hitstop_ms() > 0.0, "player hit -> a hit-stop is committed (%.1fms)" % FB.last_hitstop_ms())
	_check(c, FB.last_shake_amplitude() > 0.0, "player hit -> a shake/kick is committed (%.2f)" % FB.last_shake_amplitude())

	# Gate OFF the hit-stop -> the helper is a verified no-op (0.0), shake still fires.
	S.set_value("hit_stop", false)
	FB.reset_probe()
	FB._on_event(ev)
	_check(c, FB.last_hitstop_ms() == 0.0, "hit_stop OFF -> the hit-stop is a NO-OP (not dead code)")

	# Gate OFF the shake -> the kick is a verified no-op (0.0).
	S.set_value("hit_stop", true)
	S.set_value("screen_shake", false)
	FB.reset_probe()
	FB._on_event(ev)
	_check(c, FB.last_shake_amplitude() == 0.0, "screen_shake OFF -> the kick is a NO-OP")
	S.reset_defaults()

# --- (b) the struck enemy body whitens then restores (gated hit_flash) --------------------------
static func _b_struck_enemy_whitens_then_restores(c: Dictionary, root: Node) -> void:
	print("[b: the STRUCK enemy sprite whitens on a hit, then restores (gated hit_flash)]")
	var S: Object = root.get_node_or_null("/root/Settings")
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	if FB == null or S == null:
		return
	S.reset_defaults()
	S.set_value("hit_flash", true)
	var npc = load("res://scenes/NPC.tscn").instantiate()
	npc.npc_id = "zz_juice_struck_probe"
	root.add_child(npc)
	await (Engine.get_main_loop() as SceneTree).process_frame
	var spr: Sprite2D = npc.get_node("Sprite2D")
	var base: Color = spr.modulate
	var ev := {"type": "agent_attacked", "data": {"actor": "player", "target": "zz_juice_struck_probe", "damage": 9.0}}
	FB._on_event(ev)
	var flashed: Color = spr.modulate
	_check(c, flashed.r > base.r and flashed.g > base.g and flashed.b > base.b,
		"the struck body moved TOWARD white (base %.2f -> flash %.2f)" % [base.r, flashed.r])
	# Drive the flash past its lifetime -> restore to the exact base.
	npc.step_hit_flash(1.0)
	_check(c, npc.get_node("Sprite2D").modulate.is_equal_approx(base),
		"the struck body restored to its base modulate after the flash")

	# Gate OFF hit_flash -> no whiten at all.
	S.set_value("hit_flash", false)
	var base2: Color = npc.get_node("Sprite2D").modulate
	FB._on_event(ev)
	_check(c, npc.get_node("Sprite2D").modulate.is_equal_approx(base2),
		"hit_flash OFF -> the struck body does NOT whiten (no-op)")
	npc.queue_free()
	await (Engine.get_main_loop() as SceneTree).process_frame
	S.reset_defaults()

# --- (c) transformed -> big shake; agent_downed -> medium shake + hit-stop ----------------------
static func _c_transform_big_shake_downed_shake_plus_hitstop(c: Dictionary, root: Node) -> void:
	print("[c: transformed -> BIG shake; agent_downed -> MEDIUM shake + hit-stop; tiers ordered]")
	var S: Object = root.get_node_or_null("/root/Settings")
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	if FB == null or S == null:
		return
	S.reset_defaults()
	S.set_value("screen_shake", true)
	S.set_value("hit_stop", true)

	# The small hit-kick (player-landed hit) amplitude.
	FB.reset_probe()
	FB._on_event({"type": "agent_attacked", "data": {"actor": "player", "target": "juice_enemy", "damage": 5.0}})
	var kick_amp: float = FB.last_shake_amplitude()

	# The mask-drop signature: transformed -> a BIG shake.
	FB.reset_probe()
	FB._on_event({"type": "transformed", "data": {"agent": "juice_enemy"}})
	var transform_amp: float = FB.last_shake_amplitude()

	# The kill punch: agent_downed -> a MEDIUM shake + a beat of hit-stop.
	FB.reset_probe()
	FB._on_event({"type": "agent_downed", "data": {"actor": "player", "target": "juice_enemy"}})
	var downed_amp: float = FB.last_shake_amplitude()
	var downed_ms: float = FB.last_hitstop_ms()

	_check(c, transform_amp > downed_amp, "transform shake (%.1f) is BIGGER than the downed shake (%.1f)" % [transform_amp, downed_amp])
	_check(c, downed_amp > kick_amp and kick_amp > 0.0, "downed shake (%.1f) > hit-kick (%.1f) > 0" % [downed_amp, kick_amp])
	_check(c, downed_ms > 0.0, "agent_downed commits a beat of hit-stop (%.1fms) — the kill punch" % downed_ms)

	# Both are Settings-gated: shake OFF -> transform/downed shakes are no-ops.
	S.set_value("screen_shake", false)
	FB.reset_probe()
	FB._on_event({"type": "transformed", "data": {"agent": "juice_enemy"}})
	_check(c, FB.last_shake_amplitude() == 0.0, "screen_shake OFF -> the transform shake is a NO-OP")
	S.reset_defaults()

# --- (d) determinism: the juice never touches the combat_sim transcript -------------------------
static func _d_juice_never_alters_combat_sim_transcript(c: Dictionary, root: Node) -> void:
	print("[d: a fixed-dt fight is byte-identical with the juice Settings ON vs OFF]")
	var S: Object = root.get_node_or_null("/root/Settings")
	if S == null:
		return
	# Juice fully ON.
	S.reset_defaults()
	S.set_value("screen_shake", true)
	S.set_value("hit_flash", true)
	S.set_value("hit_stop", true)
	var on_transcript := _run_fixed_fight(root)
	# Juice fully OFF.
	S.set_value("screen_shake", false)
	S.set_value("hit_flash", false)
	S.set_value("hit_stop", false)
	var off_transcript := _run_fixed_fight(root)
	_check(c, on_transcript == off_transcript,
		"the fixed-dt fight transcript is IDENTICAL juice-on vs juice-off (%d lines)" % on_transcript.size())
	# And identical run-to-run with the juice live (the sim never observes the cosmetic autoload).
	S.reset_defaults()
	var again := _run_fixed_fight(root)
	_check(c, again == _run_fixed_fight(root), "the fight is deterministic run-to-run with the juice live")
	S.reset_defaults()

## One scripted fixed-dt fight: a brawler telegraphs + shoots a standing dummy down. Returns a
## transcript (per-frame hp + the full ordered event signature) — the exact thing the juice must
## never perturb. Mirrors combat_sim's scenario B shape, kept tiny + self-contained.
static func _run_fixed_fight(root: Node) -> Array:
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var brawler := _stage(AG, "juice_sim_brawler", Vector2(100, 200), "juice_arena")
	var dummy := _stage(AG, "juice_sim_dummy", Vector2(420, 200), "juice_arena")
	var bex := CombatExecutor.new()
	bex.bind(brawler)
	var mex := CombatExecutor.new()
	mex.bind(dummy)
	var transcript: Array = []
	for frame in range(480):
		if bex.phase == "idle" and not dummy.downed:
			bex.try_cast("revolver_shot", "juice_sim_dummy")
		bex.step_combat(DT)
		mex.step_combat(DT)
		if (frame + 1) % 30 == 0:
			transcript.append("f=%d dummy_hp=%.2f downed=%s" % [frame + 1, dummy.hp, dummy.downed])
	for ev_v in EB.events():
		var ev: Dictionary = ev_v
		transcript.append("%d %s %s" % [int(ev.get("seq", 0)), String(ev.get("type", "")), JSON.stringify(ev.get("data", {}))])
	bex.free()
	mex.free()
	AG.rebuild()
	EB.clear()
	return transcript

static func _stage(AG: Object, id: String, pos: Vector2, room_id: String) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	a.in_combat = true
	AG._agents[id] = a
	return a

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)
