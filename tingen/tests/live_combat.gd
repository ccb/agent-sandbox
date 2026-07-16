extends SceneTree
## LIVE-LLM combat validation (M4 checklist; NOT part of the suite):
##   TINGEN_SIDECAR_URL=http://127.0.0.1:8777 godot --headless --path tingen -s tests/live_combat.gd
## Stages the player striking a cult member with a real executor-cast revolver shot, then drives
## real beats through the REAL sidecar. Asserts the intent layer's live behavior; the full prompt
## text is inspected afterwards in the sidecar's own log (TINGEN_DECIDE_LOG=1). Costs ~$1.
## Phase 2 kills the sidecar client mid-fight to prove the ambient fallback keeps fighting.

const BEATS_LIVE := 8
const BEAT_WAIT_MS := 4500

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
	var AG: Object = _al("Agents")
	var ART: Object = _al("AgentRuntime")
	var SB: Object = _al("SidecarBridge")
	var EB: Object = _al("EventBus")
	var CL: Object = _al("Clock")
	AG.rebuild()
	EB.clear()
	# Stage: voss on his morning spot, player proxy right next to him, in the city.
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.room = "city"
	voss.position = Vector2(5380, 2330)
	voss.hp = 100.0
	voss.downed = false
	voss.in_combat = false
	voss.combat_intent = {}
	var proxy: Agent = AG.ensure_player_proxy(Vector2(5300, 2330), "city")
	ART.player_position = proxy.position
	ART.always_active["clerk_voss"] = true
	SB.set_client(HttpSidecar.new(url))
	print("[live_combat] striking voss with a real revolver cast...")
	# The player's shot via the real executor machinery (as PlayerCombat does).
	var pexec := CombatExecutor.new()
	root.add_child(pexec)
	pexec.bind(proxy, null)
	var accepted: Variant = pexec.try_cast("revolver_shot", "clerk_voss")
	print("[live_combat] cast accepted: ", accepted)
	# Step the executor's own clock until the projectile resolves (~2s of 60fps frames).
	# dt is SECONDS (combat_sim.gd convention) — ms here tunneled the projectile past the target.
	for i in 120:
		pexec.step_combat(1.0 / 60.0)
	print("[live_combat] voss hp=%.0f in_combat=%s" % [voss.hp, str(voss.in_combat)])
	if not voss.in_combat:
		print("[live_combat] FATAL: damage did not flip combat mode — aborting")
		quit(1)
		return

	var intent_beat := -1
	var proposed_verbs: Array = []
	for beat in BEATS_LIVE:
		CL.beat_index = beat
		var before: int = (EB.events() as Array).size()
		ART.run_beat()
		for e in (EB.events() as Array).slice(before):
			var t := String(e.get("type", ""))
			var d: Dictionary = e.get("data", {})
			if String(d.get("actor", "")) != "clerk_voss":
				continue
			if t == "agent_action" or t == "agent_action_amended":
				proposed_verbs.append(String(d.get("verb", "")))
			if t == "sidecar_proposed":
				print("[live_combat] beat %d LLM proposed: %s %s" % [beat, d.get("verb"), str(d.get("args"))])
		var im := String(voss.combat_intent.get("mode", ""))
		print("[live_combat] beat %02d | intent=%s style=%s | hp=%.0f | verbs so far: %s"
			% [beat, im, String(voss.combat_intent.get("style", "")), voss.hp, str(proposed_verbs)])
		if im != "" and intent_beat < 0:
			intent_beat = beat
		OS.delay_msec(BEAT_WAIT_MS)
	print("[live_combat] RESULT intent_mode=%s style=%s intent_beat=%d"
		% [String(voss.combat_intent.get("mode", "")), String(voss.combat_intent.get("style", "")), intent_beat])
	var style := String(voss.combat_intent.get("style", ""))
	var mode := String(voss.combat_intent.get("mode", ""))
	print("[live_combat] CHECK intent arrived: ", mode != "")
	print("[live_combat] CHECK style legal: ", style == "" or ActionCommit.ENGAGE_STYLES.has(style))
	print("[live_combat] CHECK no cast_ability from LLM: ", not proposed_verbs.has("cast_ability"))

	# Phase 2 — sidecar dies mid-fight: the ambient ladder must keep the fight coherent.
	print("[live_combat] phase 2: killing the live client mid-fight (ambient fallback)...")
	var hs := SB.client as HttpSidecar
	if hs != null:
		hs.shutdown()
	SB.set_client(AmbientSidecar.new())
	voss.combat_intent = {}
	for beat in 3:
		CL.beat_index = BEATS_LIVE + beat
		ART.run_beat()
	print("[live_combat] CHECK ambient fallback intent: mode=%s (expect engage — kit-bearing task-holder)"
		% String(voss.combat_intent.get("mode", "")))
	ART.always_active.erase("clerk_voss")
	pexec.queue_free()
	quit(0)
