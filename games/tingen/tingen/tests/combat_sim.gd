extends SceneTree
## Headless fight harness (combat plan §3) — the self-review core. NOT part of the main
## suite; run it directly:
##   godot --headless --path tingen -s tests/combat_sim.gd
##
## Stages synthetic fighters (agents + executors, no rendered bodies) in a bare room and
## steps the M2 action layer with a FIXED dt on the executors' own clocks — fully
## deterministic (no wall time, no RNG, no physics server), so every run of this file
## produces the identical fight. Scripted caster policies stand in for the M3 tactical/
## reflex layers (which will replace them):
##
##   Scenario A — brawler vs dodger: the brawler casts revolver_shot each cooldown; the
##   dodger reacts to the ability_cast_started TELEGRAPH (never to the projectile itself)
##   after a 200ms human-feel delay — dash perpendicular when off cooldown (i-frames +
##   displacement), else a perpendicular strafe-walk (stand-in for M3 strafe steering).
##   MUST end with the dodger untouched: every projectile is dodgeable by geometry.
##
##   Scenario B — brawler vs standing dummy: MUST end with the dummy downed (never
##   deleted), agent_downed exactly once, and EVERY agent_attacked event preceded by that
##   actor's ability_cast_started (telegraphs precede all damage — the §0 acceptance beat).
##
##   Scenario C (M3) — butcher Kell vs a brawler bot: Kell runs the REAL M3 layers (tactical
##   brain + his form's data reflex rows), no scripted policy. The bot fires a telegraphed
##   revolver_shot every few seconds and strafes. MUST show: the dodge reflex eats the early
##   telegraphs; the hp_below(0.5) reflex casts assume_form (combat_form swaps, transformed
##   fires once, the reloaded kit fights); the fight ENDS in 20-90 simulated seconds; and two
##   full runs produce byte-identical transcripts (determinism).
##
##   Scenario D (M6) — the §0 acceptance script end-to-end: the REAL bram_kell (npcs.json def,
##   worn form butcher_human) is struck at NIGHT by a player-bot firing the PROXY's revolver.
##   Damage flips his combat MODE (the executor binds only then — the NPC seam mirrored), he
##   fights back human-form, his authored hp_below(0.5) reflex casts assume_form, and the bot
##   puts the monster down. The M6 consequences fire on the way (DeedRunner data rows:
##   attention/panic pressure, the sight-gated reveal clue via the watching proxy, the downing
##   confirmation) while the WORLD CLOCK advances one game minute per simulated second (the
##   world never pauses for combat). MUST replay byte-identically across two full runs.
##
## Prints a per-second combat log + a final assert summary; exits non-zero on any failure.

const DT: float = 1.0 / 60.0

var _fails: int = 0
var _passes: int = 0

# Dodger reflex bookkeeping (scenario A).
var _dodge_due_ms: int = -1
var _walk_until_ms: int = -1
var _dodge_sign: float = 1.0
var _dashes: int = 0
var _walks: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	print("=== combat_sim: deterministic M2/M3 fight harness ===")
	_scenario_dodger()
	_scenario_dummy()
	_scenario_kell()
	_scenario_kell_slice()
	_scenario_wren()
	_scenario_mack()
	_scenario_neil()
	_scenario_finch()
	_scenario_auber()
	_scenario_cassian()
	print("\n=== combat_sim: %d asserts passed, %d failed ===" % [_passes, _fails])
	_cleanup_registry()
	quit(1 if _fails > 0 else 0)

func _check(cond: bool, label: String) -> void:
	if cond:
		_passes += 1
		print("  PASS  %s" % label)
	else:
		_fails += 1
		printerr("  FAIL  %s" % label)

func _stage(id: String, pos: Vector2, room_id: String) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	a.in_combat = true
	root.get_node("/root/Agents")._agents[id] = a
	return a

func _cleanup_registry() -> void:
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()

## ---- Scenario A: brawler vs dodger ----

func _scenario_dodger() -> void:
	print("\n--- scenario A: brawler vs dodger (10s) ---")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	# A private arena per scenario: first-run lesson — scenario B once shared scenario A's
	# room and its leftover brawler stood exactly on B's spawn point, eating the first four
	# rounds (stray bullets DO hit whoever is in the path; that is by design).
	var brawler := _stage("sim_brawler", Vector2(100, 200), "sim_arena_a")
	var dodger := _stage("sim_dodger", Vector2(500, 200), "sim_arena_a")
	var bex := CombatExecutor.new()
	bex.bind(brawler)
	var dex := CombatExecutor.new()
	dex.bind(dodger)
	# The dodger's reflex channel: it reacts to the TELEGRAPH event, 200ms later (the plan's
	# 150–800ms human-feel clamp), exactly how the M3 reflex rows will fire.
	var on_event := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) != "ability_cast_started":
			return
		var d: Dictionary = ev.get("data", {})
		if String(d.get("caster", "")) == "sim_brawler" and String(d.get("target", "")) == "sim_dodger":
			_dodge_due_ms = dex.now_ms() + 200
	EB.event_logged.connect(on_event)
	_dodge_due_ms = -1
	_walk_until_ms = -1
	_dodge_sign = 1.0
	_dashes = 0
	_walks = 0

	for frame in range(600):   # 10 simulated seconds
		# Brawler policy: cast revolver_shot each cooldown (try_cast itself gates readiness).
		if bex.phase == "idle":
			bex.try_cast("revolver_shot", "sim_dodger")
		# Dodger policy: when the reflex delay elapses, dash perpendicular; if the dash is
		# still cooling, strafe-walk perpendicular instead (M3 steering stand-in).
		var now := dex.now_ms()
		if _dodge_due_ms >= 0 and now >= _dodge_due_ms:
			_dodge_due_ms = -1
			var perp := Vector2(0, _dodge_sign)
			_dodge_sign = -_dodge_sign
			if bool(dex.try_cast("dash", "", perp).get("ok", false)):
				_dashes += 1
			else:
				_walk_until_ms = now + 500
				_walks += 1
			_walk_dir = perp
		if _walk_until_ms >= 0:
			if now < _walk_until_ms:
				dodger.position += _walk_dir * 140.0 * DT
			else:
				_walk_until_ms = -1
		bex.step_combat(DT)
		dex.step_combat(DT)
		if (frame + 1) % 60 == 0:
			print("  t=%2ds  brawler hp=%5.1f (%3.0f,%3.0f)  dodger hp=%5.1f (%3.0f,%3.0f)  shots=%d dash-dodges=%d walk-dodges=%d"
				% [(frame + 1) / 60, brawler.hp, brawler.position.x, brawler.position.y,
					dodger.hp, dodger.position.x, dodger.position.y,
					EB.events("ability_cast_started").size(), _dashes, _walks])

	EB.event_logged.disconnect(on_event)
	var shots: int = EB.events("ability_cast_started").filter(
		func(e: Dictionary) -> bool: return String((e.get("data", {}) as Dictionary).get("caster", "")) == "sim_brawler").size()
	var hits_on_dodger: int = EB.events("agent_attacked").filter(
		func(e: Dictionary) -> bool: return String((e.get("data", {}) as Dictionary).get("target", "")) == "sim_dodger").size()
	_check(shots >= 8, "the brawler kept firing on cooldown (%d telegraphs)" % shots)
	_check(_dashes >= 2 and _walks >= 2,
		"both dodge paths were exercised (dash x%d, strafe x%d)" % [_dashes, _walks])
	_check(dodger.hp == dodger.max_hp, "the dodger took 0 from dodgeable projectiles (hp %.0f)" % dodger.hp)
	_check(hits_on_dodger == 0, "no agent_attacked ever named the dodger")
	bex.free()
	dex.free()
	_cleanup_registry()

var _walk_dir: Vector2 = Vector2.ZERO

## ---- Scenario B: brawler vs standing dummy ----

func _scenario_dummy() -> void:
	print("\n--- scenario B: brawler vs standing dummy (8s) ---")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var brawler := _stage("sim_brawler2", Vector2(100, 200), "sim_arena_b")
	var dummy := _stage("sim_dummy", Vector2(420, 200), "sim_arena_b")
	var bex := CombatExecutor.new()
	bex.bind(brawler)
	var mex := CombatExecutor.new()
	mex.bind(dummy)

	for frame in range(480):   # 8 simulated seconds
		if bex.phase == "idle" and not dummy.downed:
			bex.try_cast("revolver_shot", "sim_dummy")
		bex.step_combat(DT)
		mex.step_combat(DT)
		if (frame + 1) % 60 == 0:
			print("  t=%2ds  dummy hp=%5.1f downed=%s  hits=%d"
				% [(frame + 1) / 60, dummy.hp, dummy.downed, EB.events("agent_attacked").size()])

	var attacks: Array = EB.events("agent_attacked")
	var telegraphs: Array = EB.events("ability_cast_started")
	_check(dummy.downed, "the standing dummy was downed (never deleted)")
	_check(attacks.size() == 4, "exactly 4 hits downed 100hp at 26 a round (%d)" % attacks.size())
	_check(EB.events("agent_downed").size() == 1, "agent_downed emitted exactly once")
	# The §0 acceptance beat: EVERY point of damage was telegraphed FIRST by its actor.
	var all_telegraphed := attacks.size() > 0
	for atk_v in attacks:
		var atk: Dictionary = atk_v
		var actor := String((atk.get("data", {}) as Dictionary).get("actor", ""))
		var preceded := false
		for tel_v in telegraphs:
			var tel: Dictionary = tel_v
			if String((tel.get("data", {}) as Dictionary).get("caster", "")) == actor \
					and int(tel.get("seq", 0)) < int(atk.get("seq", 0)):
				preceded = true
				break
		if not preceded:
			all_telegraphed = false
	_check(all_telegraphed, "telegraphs preceded ALL damage (every agent_attacked follows its actor's cast_started)")
	bex.free()
	mex.free()
	_cleanup_registry()

## ---- Scenario C: butcher Kell (M3 tactics + reflexes) vs a brawler bot ----

## The bot's pacing: one telegraphed shot every SHOT_PERIOD_S while both fighters stand, plus
## a slow vertical strafe (so melee swings happen against a moving man, hooks can miss, and
## the fight isn't a firing-squad line). Everything below is scripted DATA — Kell's side runs
## the real M3 layers untouched.
const KELL_SHOT_PERIOD_S: float = 4.0
const KELL_BOT_STRAFE: float = 60.0
const KELL_BOT_HP: float = 200.0

func _scenario_kell() -> void:
	print("\n--- scenario C: butcher Kell (tactics + reflexes) vs brawler bot (max 90s) ---")
	var first := _run_kell_fight(true)
	var second := _run_kell_fight(false)
	_check(first == second, "determinism: two full runs produce identical transcripts (%d lines)" % first.size())

## One full deterministic fight. Asserts run on the first (verbose) pass only; both passes
## return a transcript (per-5s log + the entire event signature + end state) for comparison.
func _run_kell_fight(verbose: bool) -> Array:
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	CombatExecutor.reset_last_attackers()
	var transcript: Array = []
	var kell := _stage("sim_kell", Vector2(700, 300), "sim_arena_c")
	kell.combat_form = "butcher_human"   # the human butcher; assume_form is IN his kit
	kell.vision_r = 600.0   # a night-hunter's eyes: he must SEE a 480px telegraph to dodge it
	var bot := _stage("sim_bot", Vector2(220, 300), "sim_arena_c")
	bot.max_hp = KELL_BOT_HP
	bot.hp = KELL_BOT_HP
	var kx := CombatExecutor.new()
	kx.bind(kell)
	kx.enable_tactics()   # the REAL M3 stack: no scripted policy on Kell's side
	var bx := CombatExecutor.new()
	bx.bind(bot)
	var tf := {"count": 0, "hp_at": -1.0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == "sim_kell":
			tf["count"] = int(tf["count"]) + 1
			tf["hp_at"] = kell.hp
	EB.event_logged.connect(on_tf)
	var next_shot_s := 0.0
	var strafe_sign := 1.0
	var end_frame := -1
	for frame in range(90 * 60):
		var t := frame * DT
		if not bot.downed and not kell.downed:
			if bx.phase == "idle" and t >= next_shot_s:
				if bool(bx.try_cast("revolver_shot", "sim_kell").get("ok", false)):
					next_shot_s = t + KELL_SHOT_PERIOD_S
			bot.position.y += strafe_sign * KELL_BOT_STRAFE * DT
			if bot.position.y > 520.0:
				strafe_sign = -1.0
			elif bot.position.y < 80.0:
				strafe_sign = 1.0
		kx.step_combat(DT)
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		if (frame + 1) % 300 == 0:
			var line := "t=%2ds  kell hp=%5.1f (%3.0f,%3.0f) form=%s  |  bot hp=%5.1f (%3.0f,%3.0f)" \
				% [(frame + 1) / 60, kell.hp, kell.position.x, kell.position.y, kell.combat_form,
					bot.hp, bot.position.x, bot.position.y]
			transcript.append(line)
			if verbose:
				print("  " + line)
		if bot.downed or kell.downed:
			end_frame = frame
			break
	EB.event_logged.disconnect(on_tf)
	var end_s := end_frame * DT
	transcript.append("END t=%.2f kell_hp=%.1f form=%s downed=%s | bot_hp=%.1f downed=%s"
		% [end_s, kell.hp, kell.combat_form, kell.downed, bot.hp, bot.downed])
	# The full event signature rides the transcript: any divergence in WHAT happened (not just
	# where everyone stood) breaks the determinism check.
	for ev_v in EB.events(""):
		var ev: Dictionary = ev_v
		transcript.append("%d %s %s" % [int(ev.get("seq", 0)), String(ev.get("type", "")),
			JSON.stringify(ev.get("data", {}))])
	if verbose:
		var shots: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("caster", "")) == "sim_bot").size()
		var hits_on_kell: int = EB.events("agent_attacked").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("target", "")) == "sim_kell").size()
		_check(end_frame >= 0, "the fight ENDED (someone was downed, nobody deleted)")
		_check(end_s >= 20.0 and end_s <= 90.0,
			"fight length %.1fs sits in the GDD's short-lethal 20-90s window" % end_s)
		_check(bot.downed and not kell.downed, "the butcher put the brawler down and still stands")
		_check(shots >= 5, "the bot kept shooting on its pacing (%d telegraphs)" % shots)
		_check(hits_on_kell <= shots - 3,
			"the dodge reflex ate telegraphs: %d shots, only %d ever landed" % [shots, hits_on_kell])
		_check(int(tf["count"]) == 1, "assume_form resolved exactly once (transformed event)")
		_check(float(tf["hp_at"]) < 50.0,
			"…cast by the data reflex hp_below(0.5) (hp %.0f at the transform)" % float(tf["hp_at"]))
		_check(kell.combat_form == "bieber_monster", "Kell's combat_form swapped to bieber_monster")
		var post_kit: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_kell" \
					and ["charge", "hook_throw", "blood_frenzy"].has(String(d.get("ability", "")))).size()
		_check(post_kit >= 1, "the reloaded kit is fighting (a bieber-only ability was cast, x%d)" % post_kit)
		# The §0 acceptance beat holds under the full M3 stack too.
		var attacks: Array = EB.events("agent_attacked")
		var telegraphs: Array = EB.events("ability_cast_started")
		var all_telegraphed := attacks.size() > 0
		for atk_v in attacks:
			var atk: Dictionary = atk_v
			var actor := String((atk.get("data", {}) as Dictionary).get("actor", ""))
			var preceded := false
			for tel_v in telegraphs:
				var tel: Dictionary = tel_v
				if String((tel.get("data", {}) as Dictionary).get("caster", "")) == actor \
						and int(tel.get("seq", 0)) < int(atk.get("seq", 0)):
					preceded = true
					break
			if not preceded:
				all_telegraphed = false
		_check(all_telegraphed, "telegraphs preceded ALL damage under the full M3 stack")
	kx.free()
	bx.free()
	_cleanup_registry()
	CombatExecutor.reset_last_attackers()
	return transcript

## ---- Scenario D: the §0 acceptance script end-to-end (combat plan §M6) ----

## Bot pacing for the slice: one telegraphed proxy revolver round every SLICE_SHOT_PERIOD_S
## plus a slow vertical strafe (same shape as scenario C's bot). The proxy's pool is a test
## rig's, not the real player's 100: the monster WILL land cleaver work while being put down,
## and the §0 slice under test is Kell's arc — player_downed already has its own pinned path
## (EndGame, M5 suite).
const SLICE_SHOT_PERIOD_S: float = 3.0
const SLICE_BOT_STRAFE: float = 60.0
const SLICE_PROXY_HP: float = 2000.0

func _scenario_kell_slice() -> void:
	print("\n--- scenario D: the §0 Kell slice end-to-end at night (max 90s) ---")
	var first := _run_kell_slice(true)
	var second := _run_kell_slice(false)
	_check(first == second, "determinism: two full slice runs produce identical transcripts (%d lines)" % first.size())

## One full deterministic run of the slice. Asserts fire on the first (verbose) pass only; both
## passes return a transcript (per-5s log + end state + the full event signature) to compare.
func _run_kell_slice(verbose: bool) -> Array:
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")
	var CD: Object = root.get_node("/root/ClueDB")
	var WS: Object = root.get_node("/root/WorldState")
	var Clk: Object = root.get_node("/root/Clock")
	var ART: Object = root.get_node("/root/AgentRuntime")
	var DR: Object = root.get_node("/root/DeedRunner")
	# Save what the run mutates, so the harness leaves no residue and the second pass replays
	# the exact same staged world.
	var clues_was: Dictionary = CD.to_dict()
	var clock_was: Dictionary = Clk.to_dict()
	var attention_was: float = WS.attention
	var panic_was: float = WS.panic
	var auto_was: bool = ART.auto_run
	# M11 fixture hygiene: the player-bot's revolver casts raise Notice (MeterDrivers), which can cross
	# the threat rung and dispatch a beyond_hunter into the roster mid-slice. That is LIVE-PLAY behavior,
	# not part of the pinned §0 slice — snapshot the meters + threat bookkeeping and scrub them to a clean
	# baseline so BOTH passes replay from the identical staged world (the sim already does this for
	# clues/clock/pressures). Restored verbatim at the end so the harness leaves no residue.
	var M: Object = root.get_node_or_null("/root/Meters")
	var MT: Object = root.get_node_or_null("/root/MeterThreats")
	var meters_was: Dictionary = M.to_dict() if M != null else {}
	if M != null:
		for meter in ["doom", "madness", "notice", "heat"]:
			M.set_meter(meter, 0.0)
	if MT != null and MT.has_method("reset"):
		MT.reset()
	# The dependency made EXPLICIT (M11 review, finding 1): the bot's revolver casts + Kell's downing
	# raise Notice/Heat and CAN re-cross the threat rung MID-fight, which would inject a live
	# nighthawk/beyond_hunter into this pinned §0 roster. It stays inert (no bound executor) so the
	# transcript is still byte-identical — but the slice should not silently depend on that invariant.
	# DISCONNECT the threat spawner from Meters for the whole slice so no spawn can leak into the pinned
	# roster; reconnected verbatim at teardown. The assert below then GUARANTEES a clean roster instead
	# of relying on an incidental orphan-inert property.
	var threat_was_connected := false
	if M != null and MT != null and M.threat_threshold.is_connected(MT._on_threat_threshold):
		threat_was_connected = true
		M.threat_threshold.disconnect(MT._on_threat_threshold)
	EB.clear()
	CombatExecutor.reset_last_attackers()
	AG.rebuild()
	DR.reset()
	CD.from_dict({})
	WS.set_pressure(&"attention", 10.0)
	WS.set_pressure(&"panic", 10.0)
	Clk.set_time(2, 1410)   # 23:30 — the §0 fight happens at NIGHT (late-night phase)
	ART.auto_run = false    # the clock runs live below; deliberation beats stay out of this scripted fight
	var start_minutes: int = Clk.day * 1440 + Clk.minute_of_day

	var kell: Agent = AG.get_agent("bram_kell")   # the REAL def: worn combat_form butcher_human
	kell.room = "sim_arena_d"
	kell.position = Vector2(520, 300)
	kell.vision_r = 600.0   # the night-hunter's eyes (scenario C staging): he SEES the telegraphs
	var proxy: Agent = AG.ensure_player_proxy(Vector2(220, 300), "sim_arena_d")
	proxy.vision_r = 600.0   # the investigator watches the whole fight — the clue's sight gate
	proxy.max_hp = SLICE_PROXY_HP
	proxy.hp = SLICE_PROXY_HP
	var bx := CombatExecutor.new()
	bx.bind(proxy)          # the player-bot fires the SAME executor machinery the M5 player uses
	var kx: CombatExecutor = null   # Kell's executor binds only when his combat MODE flips

	var transcript: Array = []
	var tf := {"count": 0, "hp_at": -1.0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == "bram_kell":
			tf["count"] = int(tf["count"]) + 1
			tf["hp_at"] = kell.hp
	EB.event_logged.connect(on_tf)
	var next_shot_s := 0.0
	var strafe_sign := 1.0
	var end_frame := -1
	var mode_flip_frame := -1
	for frame in range(90 * 60):
		var t := frame * DT
		if kell.in_combat and kx == null:
			# Damage flipped Kell's combat MODE (§0: damage flips the mask, world does not
			# pause): only NOW does an executor take his body's authority — the NPC.gd seam,
			# mirrored. Before this instant he has no reflex or tactical layer at all.
			mode_flip_frame = frame
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
		if (frame + 1) % 300 == 0:
			var line := "t=%2ds  kell hp=%5.1f form=%s in_combat=%s  |  bot hp=%6.1f  att=%4.1f panic=%4.1f" \
				% [(frame + 1) / 60, kell.hp, kell.combat_form, kell.in_combat,
					proxy.hp, WS.attention, WS.panic]
			transcript.append(line)
			if verbose:
				print("  " + line)
		if kell.downed or proxy.downed:
			end_frame = frame
			break
	EB.event_logged.disconnect(on_tf)
	var end_s := end_frame * DT
	var end_minutes: int = Clk.day * 1440 + Clk.minute_of_day
	transcript.append("END t=%.2f kell_hp=%.1f form=%s downed=%s | bot_hp=%.1f | att=%.1f panic=%.1f | revealed=%s suspicious=%s | clock+%dmin"
		% [end_s, kell.hp, kell.combat_form, kell.downed, proxy.hp, WS.attention, WS.panic,
			CD.is_collected("bram_kell_revealed"), CD.is_collected("bram_kell_suspicious"),
			end_minutes - start_minutes])
	for ev_v in EB.events(""):
		var ev: Dictionary = ev_v
		transcript.append("%d %s %s" % [int(ev.get("seq", 0)), String(ev.get("type", "")),
			JSON.stringify(ev.get("data", {}))])
	if verbose:
		var shots: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("caster", "")) == "player").size()
		var hits_on_kell: int = EB.events("agent_attacked").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("target", "")) == "bram_kell").size()
		_check(end_frame >= 0 and kell.downed and not proxy.downed,
			"the fight ENDED with the monster downed, never deleted (§0's 'downed with consequences' arm)")
		_check(end_s >= 20.0 and end_s <= 90.0,
			"fight length %.1fs sits in the GDD's short-lethal 20-90s window" % end_s)
		_check(mode_flip_frame > 0,
			"damage flipped Kell's combat MODE mid-run (no executor existed before the flip)")
		_check(shots >= 5 and hits_on_kell <= shots - 3,
			"his data reflex dodged telegraphs he could SEE (%d shots, only %d landed)" % [shots, hits_on_kell])
		# Human-form resistance first: at least one Kell art telegraphed BEFORE the transform.
		var tf_events: Array = EB.events("transformed")
		var tf_seq: int = int((tf_events[0] as Dictionary).get("seq", -1)) if tf_events.size() >= 1 else -1
		var human_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("caster", "")) == "bram_kell" \
					and int(e.get("seq", 0)) < tf_seq).size()
		_check(human_casts >= 1,
			"Kell fought back in HUMAN form first (%d casts before the transform)" % human_casts)
		_check(int(tf["count"]) == 1, "assume_form resolved exactly once (transformed event)")
		_check(float(tf["hp_at"]) < 50.0,
			"…cast by his authored hp_below(0.5) reflex (hp %.0f at the transform)" % float(tf["hp_at"]))
		_check(kell.combat_form == "bieber_monster", "Kell wears bieber_monster at the end")
		# The M6 consequences (DeedRunner data rows): +8 attention +5 panic at the reveal, +4
		# attention at the monster's downing; the watching proxy earned the sight-gated clue.
		_check(WS.attention == 22.0 and WS.panic == 15.0,
			"pressures adjusted: attention 10->%.0f (+8 reveal, +4 downing), panic 10->%.0f (+5)"
			% [WS.attention, WS.panic])
		_check(CD.is_collected("bram_kell_revealed"),
			"the proxy WITNESSED the reveal: clue bram_kell_revealed granted")
		_check(not CD.is_collected("bram_kell_suspicious"),
			"the canal deed never fired in the arena (its clue stays un-granted)")
		_check(end_minutes > start_minutes and end_minutes - start_minutes >= int(end_s / 60.0),
			"the world clock advanced throughout the fight (+%d game minutes)" % (end_minutes - start_minutes))
		# §0's spine holds across the whole slice: telegraphs preceded ALL damage.
		var attacks: Array = EB.events("agent_attacked")
		var telegraphs: Array = EB.events("ability_cast_started")
		var all_telegraphed := attacks.size() > 0
		for atk_v in attacks:
			var atk: Dictionary = atk_v
			var actor := String((atk.get("data", {}) as Dictionary).get("actor", ""))
			var preceded := false
			for tel_v in telegraphs:
				var tel: Dictionary = tel_v
				if String((tel.get("data", {}) as Dictionary).get("caster", "")) == actor \
						and int(tel.get("seq", 0)) < int(atk.get("seq", 0)):
					preceded = true
					break
			if not preceded:
				all_telegraphed = false
		_check(all_telegraphed, "telegraphs preceded ALL damage across the whole slice")
		# M11 fixture-hygiene invariant, made EXPLICIT (review finding 1): the threat spawner is
		# disconnected from Meters for the whole slice (at stage), so even though the bot's casts +
		# Kell's downing re-cross the Notice/Heat rung mid-fight, NO beyond_hunter / nighthawk_pursuer
		# is ever injected into this pinned §0 roster. Pin the clean roster directly so a future change
		# that reconnects the spawner or lets a threat leak into the slice fails HERE with a clear
		# message rather than as a confusing transcript diff — the determinism assert above no longer
		# silently depends on a live orphan threat staying inert.
		var threat_agents := 0
		for a in AG.all():
			if a != null and (a.combat_form == "beyond_hunter" or a.combat_form == "nighthawk_pursuer"):
				threat_agents += 1
		_check(threat_agents == 0,
			"no MeterThreats spawn leaks into the pinned §0 slice (spawner disconnected for the slice)")
	if kx != null:
		kx.free()
	bx.free()
	# Put the world back exactly as found.
	CD.from_dict(clues_was)
	Clk.from_dict(clock_was)
	WS.set_pressure(&"attention", attention_was)
	WS.set_pressure(&"panic", panic_was)
	ART.auto_run = auto_was
	DR.reset()
	# M11: restore the meters + scrub any threat bookkeeping the slice's Notice/Heat may have staged,
	# and reconnect the threat spawner disconnected at stage (leave the autoload exactly as found).
	if threat_was_connected and M != null and MT != null \
			and not M.threat_threshold.is_connected(MT._on_threat_threshold):
		M.threat_threshold.connect(MT._on_threat_threshold)
	if M != null and not meters_was.is_empty():
		M.from_dict(meters_was)
	if MT != null and MT.has_method("reset"):
		MT.reset()
	_cleanup_registry()
	CombatExecutor.reset_last_attackers()
	return transcript

## ---- Scenario E: Sable Wren (M12 — the SECOND adversary's two-phase fight) vs a brawler bot ----
##
## The per-adversary determinism gate (mirrors scenario C for the butcher). Sable Wren — the hidden
## Hunter-pathway Beyonder who LOST CONTROL — opens in her HUMAN form (wren_human) running the REAL
## M3 stack (tactical brain + her form's data reflex rows), no scripted policy. A brawler bot fires a
## telegraphed revolver_shot every few seconds and strafes. MUST show the two-phase descent:
##   * the dodge reflex eats early telegraphs;
##   * her authored hp_below(0.5) reflex casts shed_the_hunt (NOT assume_form) -> wren_predator, the
##     feral MONSTER form (transformed fires exactly once, the reloaded ranged/blood kit fights);
##   * the fight RESOLVES deterministically in 20-90 simulated seconds — Wren's two-phase descent
##     completes and the brawler bot is downed (never deleted). This scenario proves the
##     transform + determinism; the down->drop->advance harvest payoff is proven separately in
##     test_adversary2.gd (the pathway-driven hunter_characteristic drop -> can_advance chain).
##   * two full runs produce byte-identical transcripts (determinism).
## Distinct from scenario C: a RANGED blood-hunter kit (incendiary_round/hook_throw/charge/
## blood_frenzy), no cleaver_swipe anywhere — a different fight from the butcher's melee cleaver.

const WREN_SHOT_PERIOD_S: float = 4.0
const WREN_BOT_STRAFE: float = 60.0
const WREN_BOT_HP: float = 200.0

func _scenario_wren() -> void:
	print("\n--- scenario E: Sable Wren (two-phase Hunter prey: human -> wren_predator) vs brawler bot (max 90s) ---")
	var first := _run_wren_fight(true)
	var second := _run_wren_fight(false)
	_check(first == second, "determinism: two full runs produce identical transcripts (%d lines)" % first.size())

## One full deterministic two-phase fight. Asserts run on the first (verbose) pass only; both passes
## return a transcript (per-5s log + the entire event signature + end state) for comparison.
func _run_wren_fight(verbose: bool) -> Array:
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	CombatExecutor.reset_last_attackers()
	var transcript: Array = []
	var wren := _stage("sim_wren", Vector2(700, 300), "sim_arena_e")
	wren.combat_form = "wren_human"   # the human thief-taker; shed_the_hunt is IN her kit
	wren.vision_r = 620.0             # the hunter's eyes: she must SEE a telegraph to dodge it
	var bot := _stage("sim_bot", Vector2(220, 300), "sim_arena_e")
	bot.max_hp = WREN_BOT_HP
	bot.hp = WREN_BOT_HP
	var wx := CombatExecutor.new()
	wx.bind(wren)
	wx.enable_tactics()   # the REAL M3 stack: no scripted policy on Wren's side
	var bx := CombatExecutor.new()
	bx.bind(bot)
	var tf := {"count": 0, "hp_at": -1.0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == "sim_wren":
			tf["count"] = int(tf["count"]) + 1
			tf["hp_at"] = wren.hp
	EB.event_logged.connect(on_tf)
	var next_shot_s := 0.0
	var strafe_sign := 1.0
	var end_frame := -1
	for frame in range(90 * 60):
		var t := frame * DT
		if not bot.downed and not wren.downed:
			if bx.phase == "idle" and t >= next_shot_s:
				if bool(bx.try_cast("revolver_shot", "sim_wren").get("ok", false)):
					next_shot_s = t + WREN_SHOT_PERIOD_S
			bot.position.y += strafe_sign * WREN_BOT_STRAFE * DT
			if bot.position.y > 520.0:
				strafe_sign = -1.0
			elif bot.position.y < 80.0:
				strafe_sign = 1.0
		wx.step_combat(DT)
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		if (frame + 1) % 300 == 0:
			var line := "t=%2ds  wren hp=%5.1f (%3.0f,%3.0f) form=%s  |  bot hp=%5.1f (%3.0f,%3.0f)" \
				% [(frame + 1) / 60, wren.hp, wren.position.x, wren.position.y, wren.combat_form,
					bot.hp, bot.position.x, bot.position.y]
			transcript.append(line)
			if verbose:
				print("  " + line)
		if bot.downed or wren.downed:
			end_frame = frame
			break
	EB.event_logged.disconnect(on_tf)
	var end_s := end_frame * DT
	transcript.append("END t=%.2f wren_hp=%.1f form=%s downed=%s | bot_hp=%.1f downed=%s"
		% [end_s, wren.hp, wren.combat_form, wren.downed, bot.hp, bot.downed])
	# The full event signature rides the transcript: any divergence in WHAT happened (not just where
	# everyone stood) breaks the determinism check.
	for ev_v in EB.events(""):
		var ev: Dictionary = ev_v
		transcript.append("%d %s %s" % [int(ev.get("seq", 0)), String(ev.get("type", "")),
			JSON.stringify(ev.get("data", {}))])
	if verbose:
		var shots: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("caster", "")) == "sim_bot").size()
		var hits_on_wren: int = EB.events("agent_attacked").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("target", "")) == "sim_wren").size()
		_check(end_frame >= 0, "the fight ENDED (someone was downed, nobody deleted)")
		_check(end_s >= 20.0 and end_s <= 90.0,
			"fight length %.1fs sits in the GDD's short-lethal 20-90s window" % end_s)
		_check(bot.downed and not wren.downed, "Wren put the brawler down and still stands")
		_check(shots >= 5, "the bot kept shooting on its pacing (%d telegraphs)" % shots)
		_check(hits_on_wren <= shots - 3,
			"the dodge reflex ate telegraphs: %d shots, only %d ever landed" % [shots, hits_on_wren])
		# The two-phase descent (the M12 deliverable): human -> shed_the_hunt -> wren_predator, once.
		_check(int(tf["count"]) == 1, "shed_the_hunt resolved exactly once (transformed event)")
		_check(float(tf["hp_at"]) < 50.0,
			"…cast by the data reflex hp_below(0.5) (hp %.0f at the transform)" % float(tf["hp_at"]))
		_check(wren.combat_form == "wren_predator", "Wren's combat_form swapped to wren_predator (the monster)")
		# Her monster kit is a DISTINCT ranged/blood-hunter set, NOT the butcher's cleaver: a
		# wren_predator-only ability was cast after the transform, and it is a ranged/hunter art.
		var post_kit: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_wren" \
					and ["incendiary_round", "hook_throw", "charge", "blood_frenzy"].has(String(d.get("ability", "")))).size()
		_check(post_kit >= 1, "the reloaded blood-hunter kit is fighting (a wren_predator-only ability was cast, x%d)" % post_kit)
		var cleaver_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_wren" and String(d.get("ability", "")) == "cleaver_swipe").size()
		_check(cleaver_casts == 0, "Wren NEVER swings a cleaver (her kit is distinct from the butcher's melee)")
		# The §0 acceptance beat holds under the full M3 stack too: telegraphs preceded ALL damage.
		var attacks: Array = EB.events("agent_attacked")
		var telegraphs: Array = EB.events("ability_cast_started")
		var all_telegraphed := attacks.size() > 0
		for atk_v in attacks:
			var atk: Dictionary = atk_v
			var actor := String((atk.get("data", {}) as Dictionary).get("actor", ""))
			var preceded := false
			for tel_v in telegraphs:
				var tel: Dictionary = tel_v
				if String((tel.get("data", {}) as Dictionary).get("caster", "")) == actor \
						and int(tel.get("seq", 0)) < int(atk.get("seq", 0)):
					preceded = true
					break
			if not preceded:
				all_telegraphed = false
		_check(all_telegraphed, "telegraphs preceded ALL damage under the full M3 stack")
	wx.free()
	bx.free()
	_cleanup_registry()
	CombatExecutor.reset_last_attackers()
	return transcript

## ---- Scenario F: Leland Mack (M14 — the THIRD adversary's two-phase fight) vs a brawler bot ----
##
## The per-adversary determinism gate (mirrors scenario E for Wren). Leland Mack — a harbor
## poacher/line-handler who LOST CONTROL from over-ingesting a Red-Priest Hunter dose — opens in
## his HUMAN form (mack_harbor) running the REAL M3 stack (tactical brain + data reflex rows),
## no scripted policy. A brawler bot fires telegraphed revolver_shots every few seconds and strafes.
## MUST show:
##   * the dodge reflex eats early telegraphs;
##   * his authored hp_below(0.45) reflex casts lose_the_line -> mack_beast, the feral harbour beast
##     form (transformed fires exactly once, the hook/charge/frenzy kit fights);
##   * the fight RESOLVES deterministically in 20-90 simulated seconds;
##   * two full runs produce byte-identical transcripts (determinism).
## HARDER than Wren: hp_below at 0.45 (vs Wren's 0.5) means the human phase ends sooner and the
## bruiser beast emerges with the player LESS able to exploit the transition window. The bot is
## given more HP (250 vs Wren's 200) to reflect the Seq-8 player's upgraded kit/survivability.
## Distinct kit: hook_throw + charge + blood_frenzy (no revolver_shot, no cleaver_swipe, no
## incendiary_round) — a different fight from both the butcher and Wren.

const MACK_SHOT_PERIOD_S: float = 4.0
const MACK_BOT_STRAFE: float = 60.0
const MACK_BOT_HP: float = 250.0

func _scenario_mack() -> void:
	print("\n--- scenario F: Leland Mack (two-phase Hunter prey: mack_harbor -> mack_beast) vs brawler bot (max 90s) ---")
	var first := _run_mack_fight(true)
	var second := _run_mack_fight(false)
	_check(first == second, "determinism: two full runs produce identical transcripts (%d lines)" % first.size())

## One full deterministic two-phase fight. Asserts run on the first (verbose) pass only; both passes
## return a transcript (per-5s log + the entire event signature + end state) for byte comparison.
func _run_mack_fight(verbose: bool) -> Array:
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	CombatExecutor.reset_last_attackers()
	var transcript: Array = []
	var mack := _stage("sim_mack", Vector2(700, 300), "sim_arena_f")
	mack.combat_form = "mack_harbor"   # the harbor line-handler; lose_the_line is in his kit
	mack.vision_r = 640.0              # the hunter's eyes: he must SEE a telegraph to dodge it
	mack.max_hp = 200.0                # TUNING: harder than Wren (100 HP) — the Seq-8 meal survives longer
	mack.hp = 200.0
	var bot := _stage("sim_bot_f", Vector2(220, 300), "sim_arena_f")
	bot.max_hp = MACK_BOT_HP
	bot.hp = MACK_BOT_HP
	var mx := CombatExecutor.new()
	mx.bind(mack)
	mx.enable_tactics()   # the REAL M3 stack: no scripted policy on Mack's side
	var bx := CombatExecutor.new()
	bx.bind(bot)
	var tf := {"count": 0, "hp_at": -1.0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == "sim_mack":
			tf["count"] = int(tf["count"]) + 1
			tf["hp_at"] = mack.hp
	EB.event_logged.connect(on_tf)
	var next_shot_s := 0.0
	var strafe_sign := 1.0
	var end_frame := -1
	for frame in range(90 * 60):
		var t := frame * DT
		if not bot.downed and not mack.downed:
			if bx.phase == "idle" and t >= next_shot_s:
				if bool(bx.try_cast("revolver_shot", "sim_mack").get("ok", false)):
					next_shot_s = t + MACK_SHOT_PERIOD_S
			bot.position.y += strafe_sign * MACK_BOT_STRAFE * DT
			if bot.position.y > 520.0:
				strafe_sign = -1.0
			elif bot.position.y < 80.0:
				strafe_sign = 1.0
		mx.step_combat(DT)
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		if (frame + 1) % 300 == 0:
			var line := "t=%2ds  mack hp=%5.1f (%3.0f,%3.0f) form=%s  |  bot hp=%5.1f (%3.0f,%3.0f)" \
				% [(frame + 1) / 60, mack.hp, mack.position.x, mack.position.y, mack.combat_form,
					bot.hp, bot.position.x, bot.position.y]
			transcript.append(line)
			if verbose:
				print("  " + line)
		if bot.downed or mack.downed:
			end_frame = frame
			break
	EB.event_logged.disconnect(on_tf)
	var end_s := end_frame * DT
	transcript.append("END t=%.2f mack_hp=%.1f form=%s downed=%s | bot_hp=%.1f downed=%s"
		% [end_s, mack.hp, mack.combat_form, mack.downed, bot.hp, bot.downed])
	for ev_v in EB.events(""):
		var ev: Dictionary = ev_v
		transcript.append("%d %s %s" % [int(ev.get("seq", 0)), String(ev.get("type", "")),
			JSON.stringify(ev.get("data", {}))])
	if verbose:
		var shots: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("caster", "")) == "sim_bot_f").size()
		var hits_on_mack: int = EB.events("agent_attacked").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("target", "")) == "sim_mack").size()
		_check(end_frame >= 0, "the fight ENDED (someone was downed, nobody deleted)")
		_check(end_s >= 20.0 and end_s <= 90.0,
			"fight length %.1fs sits in the GDD's short-lethal 20-90s window" % end_s)
		_check(bot.downed and not mack.downed, "Mack put the brawler down and still stands")
		_check(shots >= 5, "the bot kept shooting on its pacing (%d telegraphs)" % shots)
		_check(hits_on_mack <= shots - 2,
			"the dodge reflex ate telegraphs: %d shots, only %d ever landed (faster reflex than Wren: 210ms)" % [shots, hits_on_mack])
		# The two-phase descent (the M14 deliverable): human -> lose_the_line -> mack_beast, once.
		_check(int(tf["count"]) == 1, "lose_the_line resolved exactly once (transformed event)")
		_check(float(tf["hp_at"]) < 91.0,
			"…cast by the data reflex hp_below(0.45) on a 200-HP pool: triggers at <=90 HP (hp %.0f at transform)" % float(tf["hp_at"]))
		_check(mack.combat_form == "mack_beast", "Mack's combat_form swapped to mack_beast (the monster)")
		# His monster kit is DISTINCT: hook_throw + charge + blood_frenzy, NO revolver_shot, NO cleaver_swipe.
		var post_kit: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_mack" \
					and ["hook_throw", "charge", "blood_frenzy"].has(String(d.get("ability", "")))).size()
		_check(post_kit >= 1, "the reloaded bruiser kit is fighting (a mack_beast-only ability was cast, x%d)" % post_kit)
		var cleaver_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_mack" and String(d.get("ability", "")) == "cleaver_swipe").size()
		_check(cleaver_casts == 0, "Mack NEVER swings a cleaver (distinct from the butcher's melee)")
		var revolver_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_mack" and String(d.get("ability", "")) == "revolver_shot").size()
		_check(revolver_casts == 0, "Mack NEVER fires a revolver (distinct from Wren's ranged kit)")
		# The §0 acceptance beat: telegraphs preceded ALL damage.
		var attacks: Array = EB.events("agent_attacked")
		var telegraphs: Array = EB.events("ability_cast_started")
		var all_telegraphed := attacks.size() > 0
		for atk_v in attacks:
			var atk: Dictionary = atk_v
			var actor := String((atk.get("data", {}) as Dictionary).get("actor", ""))
			var preceded := false
			for tel_v in telegraphs:
				var tel: Dictionary = tel_v
				if String((tel.get("data", {}) as Dictionary).get("caster", "")) == actor \
						and int(tel.get("seq", 0)) < int(atk.get("seq", 0)):
					preceded = true
					break
			if not preceded:
				all_telegraphed = false
		_check(all_telegraphed, "telegraphs preceded ALL damage under the full M3 stack")
	mx.free()
	bx.free()
	_cleanup_registry()
	CombatExecutor.reset_last_attackers()
	return transcript

## ---- Scenario G: Old Neil (M28 — the HERMIT pathway's Seq-9 prey, two-phase fight) vs a brawler bot ----
##
## The per-adversary determinism gate (mirrors scenario E for Wren, the SECOND playable pathway's first
## real hunt). Old Neil — a grieving alchemist who LOST CONTROL to the Hidden Sage's pollution — opens in
## his HUMAN form (neil_human) running the REAL M3 stack (tactical brain + his form's data reflex rows),
## no scripted policy. A brawler bot fires a telegraphed revolver_shot every few seconds and strafes.
## MUST show the two-phase descent:
##   * the dodge reflex eats early telegraphs;
##   * his authored hp_below(0.5) reflex casts neil_descend (NOT any Hunter transform) -> neil_monster,
##     the pollution-shaped Sage MONSTER form (transformed fires exactly once, the star/ritual kit fights);
##   * the fight RESOLVES deterministically in 20-90 simulated seconds and the brawler bot is downed;
##   * two full runs produce byte-identical transcripts (determinism).
## Distinct from every Hunter scenario: a HERMIT star/ritual kit (star_brand/ward_circle then
## collapsing_star/astral_chains) — NO cleaver_swipe, NO revolver_shot, NO incendiary_round anywhere.

const NEIL_SHOT_PERIOD_S: float = 4.0
const NEIL_BOT_STRAFE: float = 60.0
const NEIL_BOT_HP: float = 200.0

func _scenario_neil() -> void:
	print("\n--- scenario G: Old Neil (two-phase Hermit prey: neil_human -> neil_monster) vs brawler bot (max 90s) ---")
	var first := _run_neil_fight(true)
	var second := _run_neil_fight(false)
	_check(first == second, "determinism: two full runs produce identical transcripts (%d lines)" % first.size())

## One full deterministic two-phase fight. Asserts run on the first (verbose) pass only; both passes
## return a transcript (per-5s log + the entire event signature + end state) for byte comparison.
func _run_neil_fight(verbose: bool) -> Array:
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	CombatExecutor.reset_last_attackers()
	var transcript: Array = []
	var neil := _stage("sim_neil", Vector2(700, 300), "sim_arena_g")
	neil.combat_form = "neil_human"   # the human alchemist; neil_descend is IN his kit
	neil.vision_r = 600.0             # the Hermit's eyes: he must SEE a telegraph to dodge it
	var bot := _stage("sim_bot_g", Vector2(220, 300), "sim_arena_g")
	bot.max_hp = NEIL_BOT_HP
	bot.hp = NEIL_BOT_HP
	var nx := CombatExecutor.new()
	nx.bind(neil)
	nx.enable_tactics()   # the REAL M3 stack: no scripted policy on Neil's side
	var bx := CombatExecutor.new()
	bx.bind(bot)
	var tf := {"count": 0, "hp_at": -1.0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == "sim_neil":
			tf["count"] = int(tf["count"]) + 1
			tf["hp_at"] = neil.hp
	EB.event_logged.connect(on_tf)
	var next_shot_s := 0.0
	var strafe_sign := 1.0
	var end_frame := -1
	for frame in range(90 * 60):
		var t := frame * DT
		if not bot.downed and not neil.downed:
			if bx.phase == "idle" and t >= next_shot_s:
				if bool(bx.try_cast("revolver_shot", "sim_neil").get("ok", false)):
					next_shot_s = t + NEIL_SHOT_PERIOD_S
			bot.position.y += strafe_sign * NEIL_BOT_STRAFE * DT
			if bot.position.y > 520.0:
				strafe_sign = -1.0
			elif bot.position.y < 80.0:
				strafe_sign = 1.0
		nx.step_combat(DT)
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		if (frame + 1) % 300 == 0:
			var line := "t=%2ds  neil hp=%5.1f (%3.0f,%3.0f) form=%s  |  bot hp=%5.1f (%3.0f,%3.0f)" \
				% [(frame + 1) / 60, neil.hp, neil.position.x, neil.position.y, neil.combat_form,
					bot.hp, bot.position.x, bot.position.y]
			transcript.append(line)
			if verbose:
				print("  " + line)
		if bot.downed or neil.downed:
			end_frame = frame
			break
	EB.event_logged.disconnect(on_tf)
	var end_s := end_frame * DT
	transcript.append("END t=%.2f neil_hp=%.1f form=%s downed=%s | bot_hp=%.1f downed=%s"
		% [end_s, neil.hp, neil.combat_form, neil.downed, bot.hp, bot.downed])
	for ev_v in EB.events(""):
		var ev: Dictionary = ev_v
		transcript.append("%d %s %s" % [int(ev.get("seq", 0)), String(ev.get("type", "")),
			JSON.stringify(ev.get("data", {}))])
	if verbose:
		var shots: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("caster", "")) == "sim_bot_g").size()
		var hits_on_neil: int = EB.events("agent_attacked").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("target", "")) == "sim_neil").size()
		_check(end_frame >= 0, "the fight ENDED (someone was downed, nobody deleted)")
		_check(end_s >= 20.0 and end_s <= 90.0,
			"fight length %.1fs sits in the GDD's short-lethal 20-90s window" % end_s)
		_check(bot.downed and not neil.downed, "Neil put the brawler down and still stands")
		_check(shots >= 5, "the bot kept shooting on its pacing (%d telegraphs)" % shots)
		_check(hits_on_neil <= shots - 3,
			"the dodge reflex ate telegraphs: %d shots, only %d ever landed" % [shots, hits_on_neil])
		# The two-phase descent (the M28 deliverable): human -> neil_descend -> neil_monster, once.
		_check(int(tf["count"]) == 1, "neil_descend resolved exactly once (transformed event)")
		_check(float(tf["hp_at"]) < 50.0,
			"…cast by the data reflex hp_below(0.5) (hp %.0f at the transform)" % float(tf["hp_at"]))
		_check(neil.combat_form == "neil_monster", "Neil's combat_form swapped to neil_monster (the monster)")
		# His monster kit is a DISTINCT HERMIT star/ritual set, NOT any Hunter kit.
		var post_kit: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_neil" \
					and ["collapsing_star", "star_brand", "astral_chains"].has(String(d.get("ability", "")))).size()
		_check(post_kit >= 1, "the reloaded star/ritual kit is fighting (a Hermit ability was cast, x%d)" % post_kit)
		var hunter_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_neil" \
					and ["cleaver_swipe", "revolver_shot", "incendiary_round"].has(String(d.get("ability", "")))).size()
		_check(hunter_casts == 0, "Neil NEVER swings a Hunter art (his kit is a distinct Hermit star/ritual set)")
		# The §0 acceptance beat holds under the full M3 stack too: telegraphs preceded ALL damage.
		var attacks: Array = EB.events("agent_attacked")
		var telegraphs: Array = EB.events("ability_cast_started")
		var all_telegraphed := attacks.size() > 0
		for atk_v in attacks:
			var atk: Dictionary = atk_v
			var actor := String((atk.get("data", {}) as Dictionary).get("actor", ""))
			var preceded := false
			for tel_v in telegraphs:
				var tel: Dictionary = tel_v
				if String((tel.get("data", {}) as Dictionary).get("caster", "")) == actor \
						and int(tel.get("seq", 0)) < int(atk.get("seq", 0)):
					preceded = true
					break
			if not preceded:
				all_telegraphed = false
		_check(all_telegraphed, "telegraphs preceded ALL damage under the full M3 stack")
	nx.free()
	bx.free()
	_cleanup_registry()
	CombatExecutor.reset_last_attackers()
	return transcript

## ---- Scenario H: Ledger Finch (M30 — the HERMIT pathway's Seq-8 prey, two-phase fight) vs a brawler bot ----
##
## The per-adversary determinism gate (mirrors scenario G for Old Neil, the HERMIT pathway's OTHER real
## hunt — the Seq-8 meal). Ledger Finch — a university records clerk who stole a restricted forbidden
## volume and LOST CONTROL reading it — opens in her HUMAN form (finch_human) running the REAL M3 stack
## (tactical brain + her form's data reflex rows), no scripted policy, at her AUTHORED 100 HP (retro B4:
## the descent used to be proven only under a fixture-tuned 50-HP pool). A PURSUING brawler bot — faster
## than her 140 px/s kite — closes to a shooting standoff and fires a telegraphed revolver_shot every few
## seconds, so hits genuinely land once her dodge reflex (max_fires 3) is spent. MUST show the two-phase
## descent at the pool the live ledger_finch actually carries:
##   * the dodge reflex eats early telegraphs;
##   * her authored hp_below(0.5) reflex casts finch_descend (NOT any Hunter transform, NOT neil_descend)
##     -> finch_monster, the ink-and-index Sage MONSTER form (transformed fires exactly once, the ink/word
##     kit fights);
##   * the fight RESOLVES deterministically in 20-90 simulated seconds and the brawler bot is downed;
##   * two full runs produce byte-identical transcripts (determinism).
## Distinct from scenario G (neil): finch's kit is her OWN ink/word set (ink_flood/redacted_word/
## finch_recite) — NO art shared with neil_monster (no collapsing_star/star_brand/astral_chains) AND NO
## Hunter art (no cleaver_swipe/revolver_shot/incendiary_round). Proves finch's descent + her distinct
## monster kit, plus that every telegraph precedes its damage. PURELY ADDITIVE on top of A-G (its own
## arena/agents, cleared at both ends), so A-G's 71 asserts stay byte-identical.

## Bot-side fixtures (tuning the BOT is fair game — Finch's pool is not): a 3s trigger pulls a shot
## most cooldown windows; 420 HP makes the bot survive enough shot cycles for TWO post-dodge hits to
## land (100 -> 74 -> 48 crosses 50%) while still dying inside the GDD's 20-90s window.
const FINCH_SHOT_PERIOD_S: float = 3.0
const FINCH_BOT_HP: float = 420.0
## B4 (retro audit): Finch fights at her AUTHORED pool. The live ledger_finch (npcs.json) sets no
## max_hp override, so she carries the Agent default — 100 HP. The scenario PINS that value: if the
## authored default ever retunes, this pin goes red and the descent staging must be re-proven, not
## silently inherited. (The old staging fixture-tuned her to 50 HP because a strafing bot could never
## land the two hits her hp_below(0.5) reflex needs at 100 — the pursuing bot below fixes the BOT,
## not her pool.)
const FINCH_AUTHORED_HP: float = 100.0
## The pursuer: faster than COMBAT_WALK_SPEED (140 px/s — Finch's cautious kite), so she cannot skate
## off the firing line; it holds a close shooting standoff so every shot is still a real telegraphed
## projectile with travel time (dodgeable — her reflex eats 3), yet short enough flight that her
## constant 140 px/s strafe cannot out-drift every bullet once the dodges are spent. Deterministic —
## fixed dt, no RNG.
const FINCH_BOT_PURSUIT: float = 180.0
const FINCH_BOT_STANDOFF: float = 60.0

func _scenario_finch() -> void:
	print("\n--- scenario H: Ledger Finch (two-phase Hermit prey: finch_human -> finch_monster) vs brawler bot (max 90s) ---")
	var first := _run_finch_fight(true)
	var second := _run_finch_fight(false)
	_check(first == second, "determinism: two full runs produce identical transcripts (%d lines)" % first.size())

## One full deterministic two-phase fight. Asserts run on the first (verbose) pass only; both passes
## return a transcript (per-5s log + the entire event signature + end state) for byte comparison.
func _run_finch_fight(verbose: bool) -> Array:
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	CombatExecutor.reset_last_attackers()
	var transcript: Array = []
	var finch := _stage("sim_finch", Vector2(700, 300), "sim_arena_h")
	finch.combat_form = "finch_human"   # the human records clerk; finch_descend is IN her kit
	finch.vision_r = 600.0              # the Hermit's eyes: she must SEE a telegraph to dodge it
	finch.max_hp = FINCH_AUTHORED_HP    # B4: her AUTHORED pool (= the Agent default the live NPC carries)
	finch.hp = FINCH_AUTHORED_HP
	var bot := _stage("sim_bot_h", Vector2(220, 300), "sim_arena_h")
	bot.max_hp = FINCH_BOT_HP
	bot.hp = FINCH_BOT_HP
	var fx := CombatExecutor.new()
	fx.bind(finch)
	fx.enable_tactics()   # the REAL M3 stack: no scripted policy on Finch's side
	var bx := CombatExecutor.new()
	bx.bind(bot)
	var tf := {"count": 0, "hp_at": -1.0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == "sim_finch":
			tf["count"] = int(tf["count"]) + 1
			tf["hp_at"] = finch.hp
	EB.event_logged.connect(on_tf)
	var next_shot_s := 0.0
	var end_frame := -1
	for frame in range(90 * 60):
		var t := frame * DT
		if not bot.downed and not finch.downed:
			if bx.phase == "idle" and t >= next_shot_s:
				if bool(bx.try_cast("revolver_shot", "sim_finch").get("ok", false)):
					next_shot_s = t + FINCH_SHOT_PERIOD_S
			# B4 (retro): PURSUE — outpace her 140 px/s kite but hold a shooting standoff, so shots
			# stay real dodgeable projectiles yet genuinely LAND once her dodge reflex is spent.
			# The descent is proven at her AUTHORED 100 HP, not a fixture-tuned pool.
			var gap: Vector2 = finch.position - bot.position
			if gap.length() > FINCH_BOT_STANDOFF:
				bot.position += gap.normalized() * minf(FINCH_BOT_PURSUIT * DT, gap.length() - FINCH_BOT_STANDOFF)
		fx.step_combat(DT)
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		if (frame + 1) % 300 == 0:
			var line := "t=%2ds  finch hp=%5.1f (%3.0f,%3.0f) form=%s  |  bot hp=%5.1f (%3.0f,%3.0f)" \
				% [(frame + 1) / 60, finch.hp, finch.position.x, finch.position.y, finch.combat_form,
					bot.hp, bot.position.x, bot.position.y]
			transcript.append(line)
			if verbose:
				print("  " + line)
		if bot.downed or finch.downed:
			end_frame = frame
			break
	EB.event_logged.disconnect(on_tf)
	var end_s := end_frame * DT
	transcript.append("END t=%.2f finch_hp=%.1f form=%s downed=%s | bot_hp=%.1f downed=%s"
		% [end_s, finch.hp, finch.combat_form, finch.downed, bot.hp, bot.downed])
	for ev_v in EB.events(""):
		var ev: Dictionary = ev_v
		transcript.append("%d %s %s" % [int(ev.get("seq", 0)), String(ev.get("type", "")),
			JSON.stringify(ev.get("data", {}))])
	if verbose:
		var shots: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("caster", "")) == "sim_bot_h").size()
		var hits_on_finch: int = EB.events("agent_attacked").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("target", "")) == "sim_finch").size()
		_check(end_frame >= 0, "the fight ENDED (someone was downed, nobody deleted)")
		_check(end_s >= 20.0 and end_s <= 90.0,
			"fight length %.1fs sits in the GDD's short-lethal 20-90s window" % end_s)
		_check(bot.downed and not finch.downed, "Finch put the brawler down and still stands")
		_check(shots >= 5, "the bot kept shooting on its pacing (%d telegraphs)" % shots)
		_check(hits_on_finch <= shots - 3,
			"the dodge reflex ate telegraphs: %d shots, only %d ever landed" % [shots, hits_on_finch])
		# The two-phase descent (the M30 deliverable): human -> finch_descend -> finch_monster, exactly once.
		var tf_events: Array = EB.events("transformed").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("agent", "")) == "sim_finch")
		var tf_seq: int = int((tf_events[0] as Dictionary).get("seq", -1)) if tf_events.size() >= 1 else -1
		# B4 (retro): the pool itself is pinned — the descent below is proven at AUTHORED HP, and this
		# assert goes red if anyone re-introduces a fixture-tuned pool (or retunes the Agent default).
		_check(is_equal_approx(finch.max_hp, 100.0),
			"Finch fought at her AUTHORED 100 HP (the Agent default the live ledger_finch carries), not a fixture-tuned pool")
		_check(int(tf["count"]) == 1, "finch_descend resolved exactly once (transformed event)")
		_check(float(tf["hp_at"]) > 0.0 and float(tf["hp_at"]) < finch.max_hp * 0.5,
			"…cast by the data reflex hp_below(0.5) at authored HP (hp %.0f of %.0f at the transform)"
				% [float(tf["hp_at"]), finch.max_hp])
		_check(finch.combat_form == "finch_monster", "Finch's combat_form swapped to finch_monster (the monster)")
		# Her monster kit is a DISTINCT HERMIT ink/word set. Prove the RELOADED kit fights AFTER the
		# transform: at least one monster-kit art telegraphs with seq > the transform seq.
		var post_kit: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_finch" \
					and int(e.get("seq", 0)) > tf_seq \
					and ["ink_flood", "redacted_word", "finch_recite"].has(String(d.get("ability", "")))).size()
		_check(post_kit >= 1, "the reloaded ink/word kit is fighting after the descent (a finch_monster art was cast, x%d)" % post_kit)
		# ink_flood is finch_monster-ONLY (not in finch_human's kit) — its cast is ironclad proof the
		# monster kit reloaded (not a human-phase art bleeding through).
		var ink_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_finch" and String(d.get("ability", "")) == "ink_flood").size()
		_check(ink_casts >= 1, "the finch_monster-only art ink_flood was cast (x%d) — the reloaded kit is truly her monster set" % ink_casts)
		# DISTINCT from every Hunter monster: she never swings a Hunter art.
		var hunter_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_finch" \
					and ["cleaver_swipe", "revolver_shot", "incendiary_round"].has(String(d.get("ability", "")))).size()
		_check(hunter_casts == 0, "Finch NEVER swings a Hunter art (her kit is a distinct Hermit ink/word set)")
		# DISTINCT from neil_monster: no star_brand/collapsing_star/astral_chains — the two Hermit prey fight differently.
		var neil_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_finch" \
					and ["collapsing_star", "star_brand", "astral_chains", "ward_circle"].has(String(d.get("ability", "")))).size()
		_check(neil_casts == 0, "Finch shares NO art with neil_monster (finch_recite/ink_flood/redacted_word, never neil's star/ritual set)")
		# The §0 acceptance beat holds under the full M3 stack too: telegraphs preceded ALL damage.
		var attacks: Array = EB.events("agent_attacked")
		var telegraphs: Array = EB.events("ability_cast_started")
		var all_telegraphed := attacks.size() > 0
		for atk_v in attacks:
			var atk: Dictionary = atk_v
			var actor := String((atk.get("data", {}) as Dictionary).get("actor", ""))
			var preceded := false
			for tel_v in telegraphs:
				var tel: Dictionary = tel_v
				if String((tel.get("data", {}) as Dictionary).get("caster", "")) == actor \
						and int(tel.get("seq", 0)) < int(atk.get("seq", 0)):
					preceded = true
					break
			if not preceded:
				all_telegraphed = false
		_check(all_telegraphed, "telegraphs preceded ALL damage under the full M3 stack")
	fx.free()
	bx.free()
	_cleanup_registry()
	CombatExecutor.reset_last_attackers()
	return transcript

## ---- Scenario I: Sister Auber (N5 — the DEATH pathway's Seq-9 prey, two-phase fight) vs a brawler bot ----
##
## The per-adversary determinism gate (mirrors scenario H for Finch — the THIRD playable pathway's
## first real hunt). Sister Auber — the cathedral lay-sister whose paupers' graves began answering
## her, a hidden Death-pathway Beyonder losing the leash — opens in her HUMAN form (auber_human)
## running the REAL M3 stack (tactical brain + her form's data reflex rows), no scripted policy, at
## her AUTHORED 100 HP (the B4 lesson: the live sister_auber sets no max_hp override, so she carries
## the Agent default — the pin goes red if anyone re-introduces a fixture-tuned pool or retunes the
## default). A PURSUING brawler bot — faster than her 140 px/s cautious kite — closes to a shooting
## standoff and fires a telegraphed revolver_shot every few seconds. MUST show the two-phase descent:
##   * the dodge reflex eats early telegraphs;
##   * her authored hp_below(0.5) reflex casts auber_descend (NOT any prior transform) ->
##     auber_monster, the grave-power MONSTER form (transformed fires exactly once, the reloaded
##     censer/grave kit fights — wailing_host is auber_monster-ONLY, the ironclad kit-reload proof);
##   * the fight RESOLVES deterministically in 20-90 simulated seconds and the brawler bot is downed;
##   * two full runs produce byte-identical transcripts (determinism).
## Distinct from EVERY prior scenario: a DEATH censer/grave kit — zero Hunter arts (no cleaver_swipe/
## revolver_shot/incendiary_round) AND zero Hermit arts (no star_brand/collapsing_star/astral_chains/
## ink_flood/redacted_word/finch_recite) are ever cast. PURELY ADDITIVE on top of A-H (its own
## arena/agents, cleared at both ends), so A-H's transcripts stay byte-identical.

## Bot-side fixtures (tuning the BOT is fair game — Auber's pool is not): the scenario-H shape.
const AUBER_SHOT_PERIOD_S: float = 3.0
const AUBER_BOT_HP: float = 420.0
## The authored pool pin: the live sister_auber (npcs.json) sets no max_hp override, so she carries
## the Agent default — 100 HP. The scenario PINS that value (B4 precedent).
const AUBER_AUTHORED_HP: float = 100.0
## The pursuer: outpace her 140 px/s cautious kite, hold a close shooting standoff (scenario H).
const AUBER_BOT_PURSUIT: float = 180.0
const AUBER_BOT_STANDOFF: float = 60.0

func _scenario_auber() -> void:
	print("\n--- scenario I: Sister Auber (two-phase Death prey: auber_human -> auber_monster) vs brawler bot (max 90s) ---")
	var first := _run_auber_fight(true)
	var second := _run_auber_fight(false)
	_check(first == second, "determinism: two full runs produce identical transcripts (%d lines)" % first.size())

## One full deterministic two-phase fight. Asserts run on the first (verbose) pass only; both passes
## return a transcript (per-5s log + the entire event signature + end state) for byte comparison.
func _run_auber_fight(verbose: bool) -> Array:
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	CombatExecutor.reset_last_attackers()
	var transcript: Array = []
	var auber := _stage("sim_auber", Vector2(700, 300), "sim_arena_i")
	if verbose:
		# Follow-up review pin: the fixture literal below is only honest while the LIVE
		# sister_auber row authors NO max_hp override (she carries the Agent default).
		var live_np: Dictionary = root.get_node("/root/NpcDB").get_def("sister_auber")
		_check(not live_np.has("max_hp"),
			"the LIVE sister_auber npcs.json row authors no max_hp override (fixture 100 = the Agent default she really carries)")
	auber.combat_form = "auber_human"   # the human lay-sister; auber_descend is IN her kit
	auber.vision_r = 600.0              # the caster's eyes: she must SEE a telegraph to dodge it
	auber.max_hp = AUBER_AUTHORED_HP    # B4: her AUTHORED pool (= the Agent default the live NPC carries)
	auber.hp = AUBER_AUTHORED_HP
	var bot := _stage("sim_bot_i", Vector2(220, 300), "sim_arena_i")
	bot.max_hp = AUBER_BOT_HP
	bot.hp = AUBER_BOT_HP
	var ax := CombatExecutor.new()
	ax.bind(auber)
	ax.enable_tactics()   # the REAL M3 stack: no scripted policy on Auber's side
	var bx := CombatExecutor.new()
	bx.bind(bot)
	var tf := {"count": 0, "hp_at": -1.0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == "sim_auber":
			tf["count"] = int(tf["count"]) + 1
			tf["hp_at"] = auber.hp
	EB.event_logged.connect(on_tf)
	var next_shot_s := 0.0
	var end_frame := -1
	for frame in range(90 * 60):
		var t := frame * DT
		if not bot.downed and not auber.downed:
			if bx.phase == "idle" and t >= next_shot_s:
				if bool(bx.try_cast("revolver_shot", "sim_auber").get("ok", false)):
					next_shot_s = t + AUBER_SHOT_PERIOD_S
			# PURSUE — outpace her cautious kite but hold a shooting standoff, so shots stay real
			# dodgeable projectiles yet genuinely LAND once her dodge reflex is spent (scenario H).
			var gap: Vector2 = auber.position - bot.position
			if gap.length() > AUBER_BOT_STANDOFF:
				bot.position += gap.normalized() * minf(AUBER_BOT_PURSUIT * DT, gap.length() - AUBER_BOT_STANDOFF)
		ax.step_combat(DT)
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		if (frame + 1) % 300 == 0:
			var line := "t=%2ds  auber hp=%5.1f (%3.0f,%3.0f) form=%s  |  bot hp=%5.1f (%3.0f,%3.0f)" \
				% [(frame + 1) / 60, auber.hp, auber.position.x, auber.position.y, auber.combat_form,
					bot.hp, bot.position.x, bot.position.y]
			transcript.append(line)
			if verbose:
				print("  " + line)
		if bot.downed or auber.downed:
			end_frame = frame
			break
	EB.event_logged.disconnect(on_tf)
	var end_s := end_frame * DT
	transcript.append("END t=%.2f auber_hp=%.1f form=%s downed=%s | bot_hp=%.1f downed=%s"
		% [end_s, auber.hp, auber.combat_form, auber.downed, bot.hp, bot.downed])
	for ev_v in EB.events(""):
		var ev: Dictionary = ev_v
		transcript.append("%d %s %s" % [int(ev.get("seq", 0)), String(ev.get("type", "")),
			JSON.stringify(ev.get("data", {}))])
	if verbose:
		var shots: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("caster", "")) == "sim_bot_i").size()
		var hits_on_auber: int = EB.events("agent_attacked").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("target", "")) == "sim_auber").size()
		_check(end_frame >= 0, "the fight ENDED (someone was downed, nobody deleted)")
		_check(end_s >= 20.0 and end_s <= 90.0,
			"fight length %.1fs sits in the GDD's short-lethal 20-90s window" % end_s)
		_check(bot.downed and not auber.downed, "Auber put the brawler down and still stands")
		_check(shots >= 5, "the bot kept shooting on its pacing (%d telegraphs)" % shots)
		_check(hits_on_auber <= shots - 3,
			"the dodge reflex ate telegraphs: %d shots, only %d ever landed" % [shots, hits_on_auber])
		# The two-phase descent (the N5 deliverable): human -> auber_descend -> auber_monster, once.
		var tf_events: Array = EB.events("transformed").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("agent", "")) == "sim_auber")
		var tf_seq: int = int((tf_events[0] as Dictionary).get("seq", -1)) if tf_events.size() >= 1 else -1
		# B4: the pool itself is pinned — the descent is proven at AUTHORED HP, and this assert goes
		# red if anyone re-introduces a fixture-tuned pool (or retunes the Agent default).
		_check(is_equal_approx(auber.max_hp, 100.0),
			"Auber fought at her AUTHORED 100 HP (the Agent default the live sister_auber carries), not a fixture-tuned pool")
		_check(int(tf["count"]) == 1, "auber_descend resolved exactly once (transformed event)")
		_check(float(tf["hp_at"]) > 0.0 and float(tf["hp_at"]) < auber.max_hp * 0.5,
			"…cast by the data reflex hp_below(0.5) at authored HP (hp %.0f of %.0f at the transform)"
				% [float(tf["hp_at"]), auber.max_hp])
		_check(auber.combat_form == "auber_monster", "Auber's combat_form swapped to auber_monster (the monster)")
		# The RELOADED grave/spirit kit fights AFTER the transform (seq > the transform seq).
		var post_kit: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_auber" \
					and int(e.get("seq", 0)) > tf_seq \
					and ["wailing_host", "censer_ember", "grave_hands"].has(String(d.get("ability", "")))).size()
		_check(post_kit >= 1, "the reloaded grave/spirit kit is fighting after the descent (an auber_monster art was cast, x%d)" % post_kit)
		# wailing_host is auber_monster-ONLY (not in auber_human's kit) — its cast is ironclad proof
		# the monster kit reloaded (not a human-phase art bleeding through).
		var wail_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_auber" and String(d.get("ability", "")) == "wailing_host").size()
		_check(wail_casts >= 1, "the auber_monster-only art wailing_host was cast (x%d) — the reloaded kit is truly her monster set" % wail_casts)
		# ZERO Hunter arts: she never swings a Hunter art.
		var hunter_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_auber" \
					and ["cleaver_swipe", "revolver_shot", "incendiary_round"].has(String(d.get("ability", "")))).size()
		_check(hunter_casts == 0, "Auber NEVER swings a Hunter art (her kit is a distinct Death censer/grave set)")
		# ZERO Hermit arts: the Death prey is not a Hermit re-skin — no art shared with neil/finch.
		var hermit_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_auber" \
					and ["star_brand", "collapsing_star", "astral_chains", "ward_circle",
						"ink_flood", "redacted_word", "finch_recite"].has(String(d.get("ability", "")))).size()
		_check(hermit_casts == 0, "Auber NEVER casts a Hermit art (no star/ritual or ink/word set — a real THIRD identity)")
		# The §0 acceptance beat holds under the full M3 stack too: telegraphs preceded ALL damage.
		var attacks: Array = EB.events("agent_attacked")
		var telegraphs: Array = EB.events("ability_cast_started")
		var all_telegraphed := attacks.size() > 0
		for atk_v in attacks:
			var atk: Dictionary = atk_v
			var actor := String((atk.get("data", {}) as Dictionary).get("actor", ""))
			var preceded := false
			for tel_v in telegraphs:
				var tel: Dictionary = tel_v
				if String((tel.get("data", {}) as Dictionary).get("caster", "")) == actor \
						and int(tel.get("seq", 0)) < int(atk.get("seq", 0)):
					preceded = true
					break
			if not preceded:
				all_telegraphed = false
		_check(all_telegraphed, "telegraphs preceded ALL damage under the full M3 stack")
	ax.free()
	bx.free()
	_cleanup_registry()
	CombatExecutor.reset_last_attackers()
	return transcript

## ---- Scenario J: Brother Cassian (N5 — the DEATH pathway's Seq-8 prey, two-phase fight) vs a brawler bot ----
##
## The per-adversary determinism gate for the SECOND Death hunt (the Seq-8 meal, mirroring scenario I
## for Auber the way F mirrors E for the Hunter meals). Brother Cassian — the young curate whose
## staged miracles stopped being staged, a hidden Death-pathway Beyonder losing the leash — opens in
## his HUMAN form (cassian_human) running the REAL M3 stack, no scripted policy, at his AUTHORED
## 130 HP (a STRONGER authored-HP proof than scenario I's default pin: the sim stages max_hp to
## exactly what the live npcs.json def authors, the assert names 130, AND the def row itself is
## pinned — a drift in either goes red HERE). His descent band is TIGHTER than Auber's:
## hp_below(0.45) (the mack_harbor 0.45-vs-wren 0.5 precedent — the Seq-8 meal fights meaner).
## MUST show:
##   * the dodge reflex eats early telegraphs (210ms — meaner reactions, the mack_beast precedent);
##   * his authored hp_below(0.45) reflex casts cassian_descend -> cassian_monster (transformed
##     fires exactly once; choir_of_the_dead is cassian_monster-ONLY, the ironclad kit-reload proof);
##   * the fight RESOLVES deterministically in 20-90 simulated seconds and the brawler bot is downed;
##   * two full runs produce byte-identical transcripts (determinism).
## Distinct from scenario I: cassian's kit is his OWN requiem/shroud set (choir_of_the_dead/
## shroud_binding/requiem_bolt) — NO art shared with auber_monster AND zero Hunter/Hermit arts.
## PURELY ADDITIVE on top of A-I (its own arena/agents, cleared at both ends).

## Bot-side fixtures (tuning the BOT is fair game — Cassian's pool is not): 460 HP survives one more
## shot cycle than scenario H's 420 (three post-dodge hits must land to cross 45% of 130).
const CASSIAN_SHOT_PERIOD_S: float = 3.0
const CASSIAN_BOT_HP: float = 460.0
## The authored pool pin — npcs.json authors brother_cassian max_hp: 130 (the leland_mack precedent:
## the Seq-8 meal is HARDER — more pool AND a tighter descent band).
const CASSIAN_AUTHORED_HP: float = 130.0
const CASSIAN_BOT_PURSUIT: float = 180.0
const CASSIAN_BOT_STANDOFF: float = 60.0

func _scenario_cassian() -> void:
	print("\n--- scenario J: Brother Cassian (two-phase Death prey: cassian_human -> cassian_monster) vs brawler bot (max 90s) ---")
	var first := _run_cassian_fight(true)
	var second := _run_cassian_fight(false)
	_check(first == second, "determinism: two full runs produce identical transcripts (%d lines)" % first.size())

## One full deterministic two-phase fight. Asserts run on the first (verbose) pass only; both passes
## return a transcript (per-5s log + the entire event signature + end state) for byte comparison.
func _run_cassian_fight(verbose: bool) -> Array:
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	CombatExecutor.reset_last_attackers()
	var transcript: Array = []
	var cassian := _stage("sim_cassian", Vector2(700, 300), "sim_arena_j")
	cassian.combat_form = "cassian_human"   # the human curate; cassian_descend is IN his kit
	cassian.vision_r = 600.0                # the caster's eyes: he must SEE a telegraph to dodge it
	cassian.max_hp = CASSIAN_AUTHORED_HP    # his AUTHORED pool (= the npcs.json max_hp override)
	cassian.hp = CASSIAN_AUTHORED_HP
	var bot := _stage("sim_bot_j", Vector2(220, 300), "sim_arena_j")
	bot.max_hp = CASSIAN_BOT_HP
	bot.hp = CASSIAN_BOT_HP
	var cx := CombatExecutor.new()
	cx.bind(cassian)
	cx.enable_tactics()   # the REAL M3 stack: no scripted policy on Cassian's side
	var bx := CombatExecutor.new()
	bx.bind(bot)
	var tf := {"count": 0, "hp_at": -1.0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == "sim_cassian":
			tf["count"] = int(tf["count"]) + 1
			tf["hp_at"] = cassian.hp
	EB.event_logged.connect(on_tf)
	var next_shot_s := 0.0
	var end_frame := -1
	for frame in range(90 * 60):
		var t := frame * DT
		if not bot.downed and not cassian.downed:
			if bx.phase == "idle" and t >= next_shot_s:
				if bool(bx.try_cast("revolver_shot", "sim_cassian").get("ok", false)):
					next_shot_s = t + CASSIAN_SHOT_PERIOD_S
			# PURSUE — outpace his cautious kite but hold a shooting standoff (the scenario H/I shape).
			var gap: Vector2 = cassian.position - bot.position
			if gap.length() > CASSIAN_BOT_STANDOFF:
				bot.position += gap.normalized() * minf(CASSIAN_BOT_PURSUIT * DT, gap.length() - CASSIAN_BOT_STANDOFF)
		cx.step_combat(DT)
		bx.step_combat(DT)
		CombatExecutor.step_orphans(DT)
		if (frame + 1) % 300 == 0:
			var line := "t=%2ds  cassian hp=%5.1f (%3.0f,%3.0f) form=%s  |  bot hp=%5.1f (%3.0f,%3.0f)" \
				% [(frame + 1) / 60, cassian.hp, cassian.position.x, cassian.position.y, cassian.combat_form,
					bot.hp, bot.position.x, bot.position.y]
			transcript.append(line)
			if verbose:
				print("  " + line)
		if bot.downed or cassian.downed:
			end_frame = frame
			break
	EB.event_logged.disconnect(on_tf)
	var end_s := end_frame * DT
	transcript.append("END t=%.2f cassian_hp=%.1f form=%s downed=%s | bot_hp=%.1f downed=%s"
		% [end_s, cassian.hp, cassian.combat_form, cassian.downed, bot.hp, bot.downed])
	for ev_v in EB.events(""):
		var ev: Dictionary = ev_v
		transcript.append("%d %s %s" % [int(ev.get("seq", 0)), String(ev.get("type", "")),
			JSON.stringify(ev.get("data", {}))])
	if verbose:
		var shots: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("caster", "")) == "sim_bot_j").size()
		var hits_on_cassian: int = EB.events("agent_attacked").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("target", "")) == "sim_cassian").size()
		_check(end_frame >= 0, "the fight ENDED (someone was downed, nobody deleted)")
		_check(end_s >= 20.0 and end_s <= 90.0,
			"fight length %.1fs sits in the GDD's short-lethal 20-90s window" % end_s)
		_check(bot.downed and not cassian.downed, "Cassian put the brawler down and still stands")
		_check(shots >= 5, "the bot kept shooting on its pacing (%d telegraphs)" % shots)
		_check(hits_on_cassian <= shots - 3,
			"the dodge reflex ate telegraphs: %d shots, only %d ever landed" % [shots, hits_on_cassian])
		# The AUTHORED-HP pin, both sides of the seam: the staged pool IS 130 AND the live npcs.json
		# def authors exactly that override (a retune of either goes red here, by name).
		_check(is_equal_approx(cassian.max_hp, 130.0),
			"Cassian fought at his AUTHORED 130 HP (the npcs.json max_hp override), not a fixture-tuned pool")
		var live_def: Dictionary = root.get_node("/root/NpcDB").get_def("brother_cassian")
		_check(is_equal_approx(float(live_def.get("max_hp", 0.0)), 130.0),
			"…and the live brother_cassian def authors max_hp 130 (the sim stages what the data ships)")
		# The two-phase descent: human -> cassian_descend -> cassian_monster, exactly once, in the
		# TIGHTER 0.45 band (the Seq-8 meal fights meaner — the mack precedent).
		var tf_events: Array = EB.events("transformed").filter(
			func(e: Dictionary) -> bool:
				return String((e.get("data", {}) as Dictionary).get("agent", "")) == "sim_cassian")
		var tf_seq: int = int((tf_events[0] as Dictionary).get("seq", -1)) if tf_events.size() >= 1 else -1
		_check(int(tf["count"]) == 1, "cassian_descend resolved exactly once (transformed event)")
		_check(float(tf["hp_at"]) > 0.0 and float(tf["hp_at"]) < cassian.max_hp * 0.45,
			"…cast by the data reflex hp_below(0.45) at authored HP (hp %.0f of %.0f at the transform — tighter than Auber's 0.5)"
				% [float(tf["hp_at"]), cassian.max_hp])
		_check(cassian.combat_form == "cassian_monster", "Cassian's combat_form swapped to cassian_monster (the monster)")
		# The RELOADED requiem/shroud kit fights AFTER the transform (seq > the transform seq).
		var post_kit: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_cassian" \
					and int(e.get("seq", 0)) > tf_seq \
					and ["choir_of_the_dead", "shroud_binding", "requiem_bolt"].has(String(d.get("ability", "")))).size()
		_check(post_kit >= 1, "the reloaded requiem/shroud kit is fighting after the descent (a cassian_monster art was cast, x%d)" % post_kit)
		# choir_of_the_dead is cassian_monster-ONLY (not in cassian_human's kit) — ironclad kit-reload proof.
		var choir_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_cassian" and String(d.get("ability", "")) == "choir_of_the_dead").size()
		_check(choir_casts >= 1, "the cassian_monster-only art choir_of_the_dead was cast (x%d) — the reloaded kit is truly his monster set" % choir_casts)
		# ZERO Hunter arts, ZERO Hermit arts, and NO art shared with auber_monster.
		var hunter_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_cassian" \
					and ["cleaver_swipe", "revolver_shot", "incendiary_round"].has(String(d.get("ability", "")))).size()
		_check(hunter_casts == 0, "Cassian NEVER swings a Hunter art (his kit is a distinct Death requiem/shroud set)")
		var hermit_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_cassian" \
					and ["star_brand", "collapsing_star", "astral_chains", "ward_circle",
						"ink_flood", "redacted_word", "finch_recite"].has(String(d.get("ability", "")))).size()
		_check(hermit_casts == 0, "Cassian NEVER casts a Hermit art (no star/ritual or ink/word set)")
		var auber_casts: int = EB.events("ability_cast_started").filter(
			func(e: Dictionary) -> bool:
				var d: Dictionary = e.get("data", {})
				return String(d.get("caster", "")) == "sim_cassian" \
					and ["wailing_host", "censer_ember", "grave_hands", "grave_ring", "grave_stillness"].has(String(d.get("ability", "")))).size()
		_check(auber_casts == 0, "Cassian shares NO art with auber_monster (the two Death prey fight differently)")
		# The §0 acceptance beat holds under the full M3 stack too: telegraphs preceded ALL damage.
		var attacks: Array = EB.events("agent_attacked")
		var telegraphs: Array = EB.events("ability_cast_started")
		var all_telegraphed := attacks.size() > 0
		for atk_v in attacks:
			var atk: Dictionary = atk_v
			var actor := String((atk.get("data", {}) as Dictionary).get("actor", ""))
			var preceded := false
			for tel_v in telegraphs:
				var tel: Dictionary = tel_v
				if String((tel.get("data", {}) as Dictionary).get("caster", "")) == actor \
						and int(tel.get("seq", 0)) < int(atk.get("seq", 0)):
					preceded = true
					break
			if not preceded:
				all_telegraphed = false
		_check(all_telegraphed, "telegraphs preceded ALL damage under the full M3 stack")
	cx.free()
	bx.free()
	_cleanup_registry()
	CombatExecutor.reset_last_attackers()
	return transcript
