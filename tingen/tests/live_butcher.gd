extends SceneTree
## LIVE-LLM acceptance run of the §0 Butcher script (NOT part of the suite; costs ~$1-2):
##   TINGEN_SIDECAR_URL=http://127.0.0.1:8777 godot --headless --path tingen -s tests/live_butcher.gd
## Scenario D's staging (tests/combat_sim.gd) with the scripted intent rail removed: the REAL
## sidecar (real Sonnet) decides bram_kell's combat intents beat by beat while the deterministic
## tactical/executor/reflex stack fights the fight. Composition under live latency is the thing
## under test — every seam it crosses is already pinned by the suite, the offline sim, and the
## live_combat gate. PASS/FAIL prints + exit code, live-gate conventions.

const DT: float = 1.0 / 60.0
const FRAMES_PER_BEAT := 300           # 5 sim-seconds of fighting between deliberation beats
const MAX_BEATS := 24                  # 120 sim-seconds ceiling (the GDD window is 20-90)
const BEAT_WAIT_MS := 4500             # real-LLM latency; consume-once cache applies next beat
const SHOT_PERIOD_S: float = 3.0
const BOT_STRAFE: float = 60.0
const PROXY_HP: float = 2000.0

var _fails := 0

func _check(ok: bool, what: String) -> void:
	print("  %s  %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		_fails += 1

func _al(n: String) -> Node:
	return root.get_node("/root/" + n)

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	_run()

func _run() -> void:
	var url := OS.get_environment("TINGEN_SIDECAR_URL")
	if url == "":
		url = "http://127.0.0.1:8777"
	var EB: Object = _al("EventBus")
	var AG: Object = _al("Agents")
	var CD: Object = _al("ClueDB")
	var WS: Object = _al("WorldState")
	var Clk: Object = _al("Clock")
	var ART: Object = _al("AgentRuntime")
	var SB: Object = _al("SidecarBridge")
	var DR: Object = _al("DeedRunner")
	EB.clear()
	CombatExecutor.reset_last_attackers()
	AG.rebuild()
	DR.reset()
	CD.from_dict({})
	WS.set_pressure(&"attention", 10.0)
	WS.set_pressure(&"panic", 10.0)
	Clk.set_time(2, 1410)   # 23:30 — the §0 fight happens at NIGHT
	ART.auto_run = false    # beats are driven by hand below, between fight windows
	var start_minutes: int = Clk.day * 1440 + Clk.minute_of_day

	var kell: Agent = AG.get_agent("bram_kell")
	kell.room = "sim_arena_d"
	kell.position = Vector2(520, 300)
	var proxy: Agent = AG.ensure_player_proxy(Vector2(220, 300), "sim_arena_d")
	proxy.vision_r = 600.0
	proxy.max_hp = PROXY_HP
	proxy.hp = PROXY_HP
	ART.player_position = proxy.position
	ART.always_active["bram_kell"] = true
	SB.set_client(HttpSidecar.new(url))
	var bx := CombatExecutor.new()
	bx.bind(proxy)
	var kx: CombatExecutor = null

	print("[live_butcher] opening shot — the investigator jumps the butcher on his canal round...")
	# Dictionary capture: GDScript lambdas copy primitives, reference containers (combat_sim's tf).
	var tf := {"hp_at": -1.0}
	var on_tf := func(ev: Dictionary) -> void:
		if String(ev.get("type", "")) == "transformed" \
				and String((ev.get("data", {}) as Dictionary).get("agent", "")) == "bram_kell":
			tf["hp_at"] = kell.hp
	EB.event_logged.connect(on_tf)

	var next_shot_s := 0.0
	var strafe_sign := 1.0
	var sim_s := 0.0
	var intent_beat := -1
	var llm_verbs: Array = []
	var end_beat := -1
	for beat in MAX_BEATS:
		Clk.beat_index = beat
		var before: int = (EB.events() as Array).size()
		ART.run_beat()
		for e in (EB.events() as Array).slice(before):
			var t := String(e.get("type", ""))
			var d: Dictionary = e.get("data", {})
			if String(d.get("actor", "")) != "bram_kell":
				continue
			if t == "agent_action" or t == "agent_action_amended":
				llm_verbs.append(String(d.get("verb", "")))
		var im := String(kell.combat_intent.get("mode", ""))
		if im != "" and intent_beat < 0:
			intent_beat = beat
		print("[live_butcher] beat %02d | intent=%s target=%s style=%s | kell hp=%.0f form=%s | verbs: %s"
			% [beat, im, String(kell.combat_intent.get("target", "")),
				String(kell.combat_intent.get("style", "")), kell.hp, kell.combat_form, str(llm_verbs)])
		OS.delay_msec(BEAT_WAIT_MS)
		# The fight window: 5 sim-seconds of the deterministic stack between deliberations.
		for frame in FRAMES_PER_BEAT:
			if kell.in_combat and kx == null:
				kx = CombatExecutor.new()
				kx.bind(kell)
				kx.enable_tactics()
			if not kell.downed and not proxy.downed:
				if bx.phase == "idle" and sim_s >= next_shot_s:
					if bool(bx.try_cast("revolver_shot", "bram_kell").get("ok", false)):
						next_shot_s = sim_s + SHOT_PERIOD_S
				proxy.position.y += strafe_sign * BOT_STRAFE * DT
				if proxy.position.y > 480.0:
					strafe_sign = -1.0
				elif proxy.position.y < 120.0:
					strafe_sign = 1.0
				ART.player_position = proxy.position
			if kx != null:
				kx.step_combat(DT)
			bx.step_combat(DT)
			CombatExecutor.step_orphans(DT)
			sim_s += DT
			if int(sim_s * 60.0) % 60 == 59:
				Clk.advance_minutes(1)
			if kell.downed or proxy.downed:
				break
		if kell.downed or proxy.downed:
			end_beat = beat
			break

	EB.event_logged.disconnect(on_tf)
	var end_minutes: int = Clk.day * 1440 + Clk.minute_of_day
	var shots: int = EB.events("ability_cast_started").filter(
		func(e: Dictionary) -> bool:
			return String((e.get("data", {}) as Dictionary).get("caster", "")) == "player").size()
	print("[live_butcher] RESULT end_beat=%d sim=%.1fs kell downed=%s form=%s transformed_at_hp=%.0f shots=%d"
		% [end_beat, sim_s, str(kell.downed), kell.combat_form, float(tf["hp_at"]), shots])
	_check(intent_beat >= 0 and intent_beat <= 3, "the LLM committed a combat intent within 3 beats (beat %d)" % intent_beat)
	_check(llm_verbs.has("engage"), "…and it chose engage (the butcher defends his secret)")
	_check(not llm_verbs.has("cast_ability"), "no cast_ability leaked through the intent seam (Critic amends in-combat)")
	_check(String(kell.combat_intent.get("target", "")) == "player" or kell.downed,
		"the intent targeted the attacker")
	_check(float(tf["hp_at"]) > 0.0, "the hp_below reflex cast assume_form mid-fight (at hp %.0f)" % float(tf["hp_at"]))
	_check(String(kell.combat_form) == "bieber_monster", "…and the monster is the worn form at the end")
	_check(kell.downed and not proxy.downed, "the fight ended with the monster downed, the investigator standing")
	_check(sim_s >= 20.0 and sim_s <= 120.0, "fight length %.1fs sits in the live window (20-120s)" % sim_s)
	_check(CD.is_collected("bram_kell_revealed"), "the transformation seen -> bram_kell_revealed clue granted")
	_check(WS.attention > 10.0 and WS.panic > 10.0, "attention/panic rose (att %.1f, panic %.1f)" % [WS.attention, WS.panic])
	_check(end_minutes - start_minutes > 0, "the world clock advanced %d game-minutes DURING the fight" % (end_minutes - start_minutes))

	var hs := SB.client as HttpSidecar
	if hs != null:
		hs.shutdown()
	ART.always_active.erase("bram_kell")
	print("[live_butcher] %s (%d checks failed)" % ["ALL CHECKS PASSED" if _fails == 0 else "FAILURES", _fails])
	quit(1 if _fails > 0 else 0)
