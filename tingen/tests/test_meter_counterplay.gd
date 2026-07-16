extends SceneTree
## B5 retro-audit — METER-THREAT COUNTERPLAY (the live playtest's major finding). Run directly:
##   godot --headless --path tingen -s tests/test_meter_counterplay.gd
## or as part of the master suite (run_tests.gd calls run_all(), sharing pass/fail totals).
##
## Watched RED before the fixes (each scenario names its RED):
##   BUG A — MeterDrivers._on_player_cast raised Notice +6 on EVERY successful player cast with NO
##           class gate: a mundane dash (movement) or pistol_whip (strike) drew the Attention of the
##           Beyond exactly like an occult rite. Notice is OCCULT-power attention (Meters.gd §4);
##           the fix mirrors the Madness HEAVY_CLASSES gate: Notice rises only on an OCCULT cast —
##           class in OCCULT_CLASSES (spell/transform) or an `occult: true` DATA tag in
##           abilities.json (star_brand & co). revolver_shot stays MUNDANE: no Notice, but a
##           witnessed public shot still draws Heat (officialdom cares about gunfire, not the Beyond).
##   BUG B — fighting the dispatched hunter was self-defeating: every shot at the nighthawk was
##           "witnessed" by the nighthawk ITSELF (+8 Heat each) and the kill did nothing to the
##           meter, so the hunt could never be fought off (proven live: Heat 60->68->80, pinned
##           above the 70 respawn rung with the hunter alive). Fixes: (1) threat-form agents are
##           excluded from the public-witness gate (the hunter IS the pursuit — its own eyes don't
##           compound the meter that dispatched it); (2) downing a MeterThreats-spawned hunter
##           relieves its meter by the DATA `kill_relief` (40 > the 100-70 headroom, so a kill
##           ALWAYS clears below the rung) — killing the hunter is now a real, winnable sink.
##   BUG C — MeterThreats spawned hunters into the player's CURRENT room with no Ritual Night
##           exclusion: a high-Heat crypt arrival got hunters respawning into the climax every
##           hour on top of defenders + backlash. Fix: no spawn/respawn while RitualNight.active();
##           the pressure resumes on the first threat tick after the climax ends.
##
## LIVE REACHABILITY: every scenario drives the REAL autoloads through the REAL seams — casts go
## through a live CombatExecutor (CombatEvents.cast_started -> EventBus -> MeterDrivers), kills
## through the executor's real damage path (emit_attacked -> agent_downed -> MeterThreats), spawns
## through Meters.threat_threshold -> MeterThreats. Remove any wire and its scenario goes RED.
## Deterministic: fixed dt, no RNG, no wall time, no sidecar/network.

const DT: float = 1.0 / 60.0

# --- Standalone entry -----------------------------------------------------------------------------
func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): never touch the player's REAL persistent profile — redirect the meta slot first.
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all_on(root)
	print("\n=== meter counterplay: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

# --- Shared-suite entry (run_tests.gd) ------------------------------------------------------------
static func run_all() -> Dictionary:
	var st := Engine.get_main_loop() as SceneTree
	return run_all_on(st.root)

static func run_all_on(root: Node) -> Dictionary:
	var c: Dictionary = {"passed": 0, "failed": 0}
	_occult_gate_notice(c, root)
	_mundane_gun_still_draws_heat(c, root)
	_fighting_the_nighthawk_wins(c, root)
	_fighting_the_beyond_hunter_wins(c, root)
	_ritual_night_shields_spawns(c, root)
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

# --- staging helpers -------------------------------------------------------------------------------
static func _n(root: Node, autoload_name: String) -> Node:
	return root.get_node("/root/" + autoload_name)

## A clean run with the investigator proxy alone in a private arena. Returns the proxy.
static func _fresh_arena(root: Node, room_id: String, pos: Vector2) -> Agent:
	_n(root, "RunManager").start_run()
	_n(root, "Agents").rebuild()
	var proxy: Agent = _n(root, "Agents").ensure_player_proxy(pos, room_id)
	proxy.combat_form = "player"
	proxy.max_hp = 4000.0
	proxy.hp = 4000.0
	proxy.downed = false
	proxy.vision_r = 600.0
	return proxy

## Stage a plain civilian bystander (a legitimate public witness).
static func _stage_witness(root: Node, id: String, room_id: String, pos: Vector2) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	a.combat_form = "civilian"
	a.vision_r = 300.0
	_n(root, "Agents").register_agent(a)
	return a

## Cast one art through the REAL executor seam (CombatEvents.cast_started fires synchronously on a
## successful try_cast), then step the windup through so the next cast finds the executor idle.
static func _live_cast(c: Dictionary, root: Node, bx: CombatExecutor, art: String, target_id: String) -> void:
	var res: Dictionary = bx.try_cast(art, target_id, Vector2.RIGHT if target_id == "" else Vector2.ZERO)
	_check(c, bool(res.get("ok", false)), "the %s cast fired through the live executor" % art)
	for _i in range(90):
		bx.step_combat(DT)
	CombatExecutor.step_orphans(DT)

## Fight a staged threat down through the REAL combat path (revolver_shot volleys; the threat has no
## executor of its own — this isolates the METER dynamics of fighting it, not its counter-attacks).
## Returns the peak value the driven meter reached during the fight.
static func _shoot_down(root: Node, bx: CombatExecutor, target: Agent, meter: String) -> float:
	var M := _n(root, "Meters")
	var peak: float = M.get_meter(meter)
	var next_shot_s := 0.0
	for frame in range(90 * 60):
		var t := frame * DT
		if target.downed:
			break
		if bx.phase == "idle" and t >= next_shot_s:
			if bool(bx.try_cast("revolver_shot", target.id).get("ok", false)):
				next_shot_s = t + 1.0
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		peak = maxf(peak, M.get_meter(meter))
	return peak

# ===================================================================================================
# BUG A — the occult class-gate on Notice
# ===================================================================================================
## RED before the fix: dash 0->6 and pistol_whip 0->6 (every cast pulled +6 Notice, no gate).
## The occult arts must STILL raise it (mutation guard: gate everything off and these go RED).
static func _occult_gate_notice(c: Dictionary, root: Node) -> void:
	print("[counterplay A: Notice rises ONLY on occult power — mundane dash/pistol_whip stay silent]")
	var M := _n(root, "Meters")
	var proxy := _fresh_arena(root, "counterplay_gate", Vector2(300, 300))
	# A punching bag inside pistol_whip's 64px reach (also the only other agent — and it is staged
	# DOWNED so it never witnesses: Heat stays out of this scenario, isolating the Notice gate).
	var bag := _stage_witness(root, "counterplay_bag", "counterplay_gate", Vector2(340, 300))
	bag.downed = true
	var bx := CombatExecutor.new()
	bx.bind(proxy)

	# Mundane movement: dash raises NO Notice (RED today: 0 -> 6).
	M.set_meter("notice", 0.0)
	_live_cast(c, root, bx, "dash", "")
	_check(c, M.get_meter("notice") == 0.0,
		"a mundane dash raises NO Notice (got %.1f)" % M.get_meter("notice"))

	# Mundane melee: pistol_whip raises NO Notice (RED today: 0 -> 6).
	M.set_meter("notice", 0.0)
	_live_cast(c, root, bx, "pistol_whip", "counterplay_bag")
	_check(c, M.get_meter("notice") == 0.0,
		"a mundane pistol_whip raises NO Notice (got %.1f)" % M.get_meter("notice"))

	# Mundane gun: revolver_shot raises NO Notice (the Beyond does not care about gunpowder).
	M.set_meter("notice", 0.0)
	_live_cast(c, root, bx, "revolver_shot", "counterplay_bag")
	_check(c, M.get_meter("notice") == 0.0,
		"a mundane revolver_shot raises NO Notice (got %.1f)" % M.get_meter("notice"))

	# Occult-TAGGED projectile: star_brand (the Hermit's aimed rite) still draws the Beyond's eye.
	M.set_meter("notice", 0.0)
	_live_cast(c, root, bx, "star_brand", "counterplay_bag")
	_check(c, M.get_meter("notice") > 0.0,
		"the occult-tagged star_brand STILL raises Notice (got %.1f)" % M.get_meter("notice"))

	# Occult CLASS: paper_charm (spell) rides the class half of the gate.
	M.set_meter("notice", 0.0)
	_live_cast(c, root, bx, "paper_charm", "counterplay_bag")
	_check(c, M.get_meter("notice") > 0.0,
		"a spell-class cast (paper_charm) STILL raises Notice (got %.1f)" % M.get_meter("notice"))

	bx.free()
	_n(root, "RunManager").start_run()
	_n(root, "Agents").rebuild()

## The revolver decision, pinned: mundane gunfire is invisible to the Beyond (no Notice) but a
## WITNESSED public shot still draws officialdom — Heat keeps riding the one shared witness gate.
static func _mundane_gun_still_draws_heat(c: Dictionary, root: Node) -> void:
	print("[counterplay A2: a witnessed revolver_shot still draws Heat (mundane != invisible to the law)]")
	var M := _n(root, "Meters")
	var proxy := _fresh_arena(root, "counterplay_heat", Vector2(300, 300))
	_stage_witness(root, "counterplay_bystander", "counterplay_heat", Vector2(360, 300))
	var bx := CombatExecutor.new()
	bx.bind(proxy)
	M.set_meter("heat", 0.0)
	M.set_meter("notice", 0.0)
	_live_cast(c, root, bx, "revolver_shot", "")
	_check(c, M.get_meter("heat") > 0.0,
		"a bystander-witnessed revolver_shot raises Heat (got %.1f)" % M.get_meter("heat"))
	_check(c, M.get_meter("notice") == 0.0,
		"…while still raising NO Notice (got %.1f)" % M.get_meter("notice"))
	bx.free()
	_n(root, "RunManager").start_run()
	_n(root, "Agents").rebuild()

# ===================================================================================================
# BUG B — fighting the hunter is WINNABLE
# ===================================================================================================
## RED before the fix (the exact live-playtest spiral): every shot at the nighthawk was witnessed
## by the nighthawk itself (+8 Heat), pinning Heat at 100; the kill left the meter untouched, so
## the next threat tick respawned the hunt forever.
static func _fighting_the_nighthawk_wins(c: Dictionary, root: Node) -> void:
	print("[counterplay B: fighting the nighthawk doesn't spiral Heat; the kill clears below the rung]")
	var M := _n(root, "Meters")
	var MT := _n(root, "MeterThreats")
	var proxy := _fresh_arena(root, "counterplay_hawk", Vector2(220, 300))
	MT.spawn_room = "counterplay_hawk"
	MT.spawn_pos = Vector2(520, 300)
	M.set_meter("heat", 0.0)
	M.set_meter("heat", 75.0)   # cross the rung -> the Nighthawk is dispatched
	var hawk: Agent = _n(root, "Agents").get_agent(MT.active_threat_id("heat"))
	_check(c, hawk != null and not hawk.downed, "crossing the Heat rung dispatched a live nighthawk")
	if hawk == null:
		return
	hawk.vision_r = 600.0   # the hunter watches the whole fight — the live-bug witnessing setup
	var bx := CombatExecutor.new()
	bx.bind(proxy)
	var peak := _shoot_down(root, bx, hawk, "heat")
	bx.free()
	_check(c, hawk.downed, "the player put the nighthawk DOWN through the real combat path")
	# RED today: each witnessed shot pushed Heat 75 -> 83 -> ... -> 100 (the self-defeating spiral).
	_check(c, peak <= 75.0,
		"fighting the hunter never raised Heat above its start (peak %.1f, want <= 75)" % peak)
	# RED today: the kill did NOTHING to Heat; now it relieves kill_relief=40 -> 35, below the rung.
	_check(c, M.get_meter("heat") < 70.0,
		"the kill cleared Heat below the 70 rung (got %.1f)" % M.get_meter("heat"))
	_check(c, M.get_meter("heat") == 35.0,
		"the kill_relief landed exactly (75 - 40 = 35, got %.1f)" % M.get_meter("heat"))
	# The threat is RESOLVED: bookkeeping cleared, and the next threat tick does NOT respawn.
	_check(c, not MT.has_active_threat("heat"), "the threat bookkeeping cleared on the downing")
	MT.tick_threats()
	var respawned := false
	for a in _n(root, "Agents").all():
		if a != null and not a.downed and a.combat_form == "nighthawk_pursuer":
			respawned = true
	_check(c, not respawned, "no nighthawk respawns once the kill cleared Heat below the rung")
	# The resolution is a world fact the HUD can announce.
	var resolved := false
	for ev in _n(root, "EventBus").events("threat_resolved"):
		if String((ev.get("data", {}) as Dictionary).get("meter", "")) == "heat":
			resolved = true
	_check(c, resolved, "the downing emitted a threat_resolved world fact (HUD seam)")
	_n(root, "RunManager").start_run()
	_n(root, "Agents").rebuild()

## The Notice twin: the beyond_hunter's own eyes must not feed HEAT while you fight it (it is a
## dispatched threat, not a public witness), and its kill clears Notice below the rung.
static func _fighting_the_beyond_hunter_wins(c: Dictionary, root: Node) -> void:
	print("[counterplay B2: fighting the beyond_hunter — no witness compounding; kill clears Notice]")
	var M := _n(root, "Meters")
	var MT := _n(root, "MeterThreats")
	var proxy := _fresh_arena(root, "counterplay_beyond", Vector2(220, 300))
	MT.spawn_room = "counterplay_beyond"
	MT.spawn_pos = Vector2(520, 300)
	M.set_meter("heat", 0.0)
	M.set_meter("notice", 0.0)
	M.set_meter("notice", 75.0)   # cross the rung -> the Beyond-hunter is dispatched
	var hunter: Agent = _n(root, "Agents").get_agent(MT.active_threat_id("notice"))
	_check(c, hunter != null and not hunter.downed, "crossing the Notice rung dispatched a live beyond_hunter")
	if hunter == null:
		return
	hunter.vision_r = 600.0
	var bx := CombatExecutor.new()
	bx.bind(proxy)
	var heat_peak := _shoot_down(root, bx, hunter, "heat")
	bx.free()
	_check(c, hunter.downed, "the player put the beyond_hunter DOWN through the real combat path")
	# RED today: the hunter witnessed every shot -> Heat climbed toward ITS rung mid-fight (the
	# cross-meter spiral: fighting the Notice threat summoned the Heat one).
	_check(c, heat_peak == 0.0,
		"shots seen only by the dispatched hunter raise NO Heat (peak %.1f)" % heat_peak)
	# RED today: the kill left Notice at 75 (respawn pinned). Now: 75 - 40 = 35, below the rung.
	_check(c, M.get_meter("notice") < 70.0,
		"the kill cleared Notice below the 70 rung (got %.1f)" % M.get_meter("notice"))
	MT.tick_threats()
	var respawned := false
	for a in _n(root, "Agents").all():
		if a != null and not a.downed and a.combat_form == "beyond_hunter":
			respawned = true
	_check(c, not respawned, "no beyond_hunter respawns once the kill cleared Notice below the rung")
	_n(root, "RunManager").start_run()
	_n(root, "Agents").rebuild()

# ===================================================================================================
# BUG C — the climax shield
# ===================================================================================================
## RED before the fix: a threat threshold crossed DURING Ritual Night spawned a hunter straight
## into the climax (on top of defenders + backlash). Now the spawn/respawn pump holds while
## RitualNight.active() and RESUMES on the first threat tick after the climax ends.
static func _ritual_night_shields_spawns(c: Dictionary, root: Node) -> void:
	print("[counterplay C: no hunter spawns/respawns during Ritual Night; pressure resumes after]")
	var M := _n(root, "Meters")
	var MT := _n(root, "MeterThreats")
	var RN := _n(root, "RitualNight")
	_fresh_arena(root, "counterplay_climax", Vector2(300, 300))
	MT.spawn_room = "counterplay_climax"
	MT.spawn_pos = Vector2(360, 300)
	RN.force_assault(false, 7, "front")   # the climax is LIVE (the real §9 encounter seam)
	_check(c, RN.active(), "Ritual Night is active for the shield checks")
	M.set_meter("heat", 0.0)
	M.set_meter("heat", 90.0)   # the threshold fires mid-climax…
	var spawned := false
	for a in _n(root, "Agents").all():
		if a != null and not a.downed and a.combat_form == "nighthawk_pursuer":
			spawned = true
	# RED today: the nighthawk spawns straight into the climax.
	_check(c, not spawned, "no nighthawk spawns while Ritual Night is active")
	_check(c, not MT.has_active_threat("heat"), "no threat is staged for Heat during the climax")
	# …and the hourly reconcile pump holds too (the respawn path, not just the threshold ear).
	MT.tick_threats()
	spawned = false
	for a in _n(root, "Agents").all():
		if a != null and not a.downed and a.combat_form == "nighthawk_pursuer":
			spawned = true
	_check(c, not spawned, "the threat tick does not respawn a hunter mid-climax either")
	# The climax ends -> the FIRST threat tick re-dispatches (Heat is still high; pressure resumes).
	RN.reset()
	MT.tick_threats()
	var resumed := false
	for a in _n(root, "Agents").all():
		if a != null and not a.downed and a.combat_form == "nighthawk_pursuer":
			resumed = true
	_check(c, resumed, "the hunt RESUMES on the first threat tick after the climax ends")
	_n(root, "RunManager").start_run()
	_n(root, "Agents").rebuild()
