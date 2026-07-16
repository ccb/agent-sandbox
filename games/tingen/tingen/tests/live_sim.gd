extends SceneTree
## LIVE-LLM sim harness (NOT part of the suite — run on demand):
##   TINGEN_SIDECAR_URL=http://127.0.0.1:8777 godot --headless --path tingen -s tests/live_sim.gd
## Stages the summoning demo exactly like CitySummoning (data only, no scenes), points the runtime
## at the REAL sidecar (HttpSidecar), then drives N beats with real waits so the one-beat-latency
## LLM pipeline fills. Prints each beat's committed action per cult agent so a human (or the
## calling agent) can judge decision DIVERSITY — the concurrency fix's live acceptance check.
## Costs real API tokens: ~15-25 /decide calls per run.
## Autoloads are resolved via /root lookups (a -s SceneTree script parses before autoloads register).

const BEATS := 12
const BEAT_WAIT_MS := 4500   # LLM round-trip headroom (one in-flight slot; stagger k=2)
const CULT := ["clerk_voss", "fishwife_dalia", "lamplighter_orin"]

func _al(n: String) -> Node:
	return root.get_node("/root/" + n)

## _init + two awaited frames (the run_tests.gd pattern): autoloads register only after the
## SceneTree script's _initialize, so asserting against them there crashes on missing /root nodes.
func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	_run()

func _run() -> void:
	# TINGEN_SIDECAR_URL=offline runs the free deterministic brain instead (no waits, more beats) —
	# the end-to-end regression that the cult still completes the descent under the new machinery.
	var url := OS.get_environment("TINGEN_SIDECAR_URL")
	var offline := url == "offline"
	if url == "":
		url = "http://127.0.0.1:8777"
	var AG: Object = _al("Agents")
	var SP: Object = _al("SummoningPlan")
	var RI: Object = _al("RoomItems")
	var ART: Object = _al("AgentRuntime")
	var SB: Object = _al("SidecarBridge")
	var EB: Object = _al("EventBus")
	var CL: Object = _al("Clock")
	print("[live_sim] sidecar: %s  model default: %s" % [url, _al("ModelConfig").default_model])
	# Stage the demo (mirrors CitySummoning._bootstrap, data only).
	AG.rebuild()
	SP.reset()
	SP.ritual_requirement = {"ritual_salt": 1, "consecrated_chalk": 1, "candle": 1}
	SP.deposited = {}
	AG.fallback_speed = 170.0
	RI.clear()
	var CS: GDScript = load("res://src/CitySummoning.gd")
	ActionCommit.set_nav_site("ritual_cache", CS.CACHE_NAV_POS, "city")
	for item_id in CS.CACHE_ITEMS:
		RI.place("city", item_id, CS.CACHE_ITEMS[item_id], 1)
	for id in CULT:
		var a: Agent = AG.get_agent(id)
		a.position = CS.SPOTS.get(id, Vector2(2118, 5440))
		a.room = "city"
		a.carry_capacity = 2
		a.intent = ("Complete the summoning. FIRST gather the ritual offerings (ritual_salt, "
			+ "consecrated_chalk, candle) from the supply cache 'ritual_cache' nearby — gather_item to "
			+ "pick them up (your hands hold only a couple). THEN descend through Saint Selena's "
			+ "Cathedral to the site named 'crypt_altar' (the crypt altar): perform_ritual_step to lay "
			+ "each offering, and once every offering is laid keep performing the rite to drive the "
			+ "descent. Let nothing stop it.")
		ART.always_active[id] = true
	SB.set_client(AmbientSidecar.new() if offline else HttpSidecar.new(url))
	ART.auto_run = false

	var distinct_beats := 0
	var llm_beats := 0
	var total_beats: int = 60 if offline else BEATS
	for beat in total_beats:
		CL.beat_index = beat
		var seq_before: int = (EB.events() as Array).size()
		ART.run_beat()
		# Report what each cult agent committed this beat.
		var verbs: Dictionary = {}
		for e in (EB.events() as Array).slice(seq_before):
			var t := String(e.get("type", ""))
			if t != "agent_action" and t != "agent_action_amended":
				continue
			var d: Dictionary = e.get("data", {})
			var who := String(d.get("actor", ""))
			if who in CULT:
				verbs[who] = "%s %s" % [String(d.get("verb", "")), str((d.get("args", {}) as Dictionary).values())]
		var line := "beat %02d | " % beat
		for id in CULT:
			var a: Agent = AG.get_agent(id)
			line += "%s: %-40s @(%4.0f,%4.0f) %s | " % [id.split("_")[1], String(verbs.get(id, "-")), a.position.x, a.position.y, a.room]
		print(line)
		var vals: Array = []
		for id in verbs:
			if not vals.has(verbs[id]):
				vals.append(verbs[id])
		if verbs.size() >= 2 and vals.size() >= 2:
			distinct_beats += 1
		if verbs.size() >= 2:
			llm_beats += 1
		if not offline:
			OS.delay_msec(BEAT_WAIT_MS)
	print("[live_sim] beats where >=2 cultists acted: %d; of those, beats with DISTINCT actions: %d" % [llm_beats, distinct_beats])
	print("[live_sim] altar: deposited %d/%d  countdown %d" % [SP.materials_deposited_total(), SP.materials_required_total(), SP.countdown_beats])
	var spread := 0.0
	for i in CULT.size():
		for j in range(i + 1, CULT.size()):
			spread = maxf(spread, (AG.get_agent(CULT[i]) as Agent).position.distance_to((AG.get_agent(CULT[j]) as Agent).position))
	print("[live_sim] max pairwise cult distance at end: %.1f px (same-pixel stacking would be ~0)" % spread)
	var hs := SB.client as HttpSidecar
	if hs != null:
		hs.shutdown()
	quit(0)
