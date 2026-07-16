extends SceneTree
## LAB PULL-IN P3 — decide TIMEOUT -> offline fallback + the `deciding` lifecycle fact.
## Every sidecar /decide is bounded by the client timeout; a hung/slow responder never hangs an
## NPC (the beat completes with the OFFLINE brain's decision — the fallback IS AmbientSidecar) and
## the in-flight call still lands in the per-NPC cost ledger attributed to the causing agent.
## `deciding {agent, phase: begin|end, beat}` is ONE typed EventBus fact, paired exactly once per
## decide, consumed by PlayLog (transcript line) + the thought-panel "thinking" tell.
## Standalone: godot --headless --path tingen -s tests/test_deciding_fact.gd
## Also folded into the main suite (run_tests.gd `_test_deciding_fact`) via the SAME run_all().

func _init() -> void:
	await process_frame
	await process_frame
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = await run_all()
	print("\n=== test_deciding_fact: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd (a coroutine — the
## thinking-tell step mounts the real CharacterCard scene).
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_timeout_falls_back_offline_and_pairs_facts(c, root)
	_b_ok_reply_pairs_once_and_attributes_cost(c, root)
	_c_beat_completes_under_hung_sidecar(c, root)
	await _d_playlog_and_thinking_tell(c, root)
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()
	root.get_node("/root/SidecarBridge").set_client(MockSidecar.new())
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

## Every `deciding` fact for one agent, in order.
static func _facts_for(root: Node, agent_id: String) -> Array:
	var out: Array = []
	for e in root.get_node("/root/EventBus").events("deciding"):
		if String((e.get("data", {}) as Dictionary).get("agent", "")) == agent_id:
			out.append(e.get("data", {}))
	return out

## A TCP listener that accepts nothing and answers nothing — the "stubbed slow responder": the
## HTTP client connects (the OS queues it) and then starves until the client's own deadline.
static func _hung_server(port: int) -> TCPServer:
	var srv := TCPServer.new()
	srv.listen(port, "127.0.0.1")
	return srv

# (a) --------------------------------------------------------------------------------------------
static func _a_timeout_falls_back_offline_and_pairs_facts(c: Dictionary, root: Node) -> void:
	print("[deciding (a): a slow responder times out -> offline decision + one begin/end pair]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	AG.rebuild()
	EB.clear()
	if SB.has_method("reset_agent_llm"):
		SB.reset_agent_llm()
	else:
		_check(c, false, "SidecarBridge exposes the per-agent LLM ledger (P3 seam)")
		return
	var srv := _hung_server(58731)
	var hs := HttpSidecar.new("http://127.0.0.1:58731")
	hs.timeout_sec = 0.3   # the decide BOUND — well under the 15s beat
	var a: Agent = AG.get_agent("clerk_voss")
	var snaps: Array = [Perception.build_snapshot(a, Vector2.ZERO)]
	var out: Array = hs.propose(snaps)
	# The beat's answer is IMMEDIATE and offline: the ambient brain's goal-seek, never a hang.
	_check(c, out.size() == 1 and String((out[0] as Dictionary).get("verb", "")) != "",
		"propose answers immediately with an offline decision (verb '%s')" % (out[0] as Dictionary).get("verb", ""))
	var after_launch := _facts_for(root, a.id)
	_check(c, after_launch.size() == 1 and String(after_launch[0].get("phase", "")) == "begin",
		"launching the decide emits exactly ONE `deciding begin` fact")
	# Let the worker starve past its deadline, then drain the reply on the next main-thread pass.
	OS.delay_msec(700)
	hs._drain_pending()
	var facts := _facts_for(root, a.id)
	_check(c, facts.size() == 2 and String(facts[1].get("phase", "")) == "end",
		"the timed-out decide emits exactly ONE `deciding end` fact (begin/end paired)")
	_check(c, String(facts[1].get("outcome", "")) == "timeout",
		"the end fact carries outcome=timeout (got '%s')" % facts[1].get("outcome", ""))
	_check(c, int(facts[1].get("beat", -1)) >= 0, "the fact carries the beat it landed on")
	# The in-flight call still lands in the cost ledger, attributed to the CAUSING agent.
	var ledger: Dictionary = SB.agent_llm(a.id)
	_check(c, int(ledger.get("calls", 0)) == 1 and int(ledger.get("timeouts", 0)) == 1,
		"the timed-out call is attributed to the causing NPC (calls=1, timeouts=1)")
	hs.shutdown()
	srv.stop()

# (b) --------------------------------------------------------------------------------------------
static func _b_ok_reply_pairs_once_and_attributes_cost(c: Dictionary, root: Node) -> void:
	print("[deciding (b): a landed reply ends the SAME decide exactly once, cost attributed]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	AG.rebuild()
	EB.clear()
	SB.reset_agent_llm()
	var srv := _hung_server(58732)
	var hs := HttpSidecar.new("http://127.0.0.1:58732")
	hs.timeout_sec = 0.3
	var a: Agent = AG.get_agent("fishwife_dalia")
	hs.propose([Perception.build_snapshot(a, Vector2.ZERO)])   # begin (worker will time out later)
	# A reply lands (simulated through the same publish/drain seam the worker uses).
	hs._publish({"actions": [{"actor": a.id, "verb": "idle", "args": {},
		"_tokens_in": 100, "_tokens_out": 20, "_cost": 0.0123, "_model": "m"}], "error": ""})
	hs._drain_pending()
	var facts := _facts_for(root, a.id)
	_check(c, facts.size() == 2 and String(facts[1].get("phase", "")) == "end"
		and String(facts[1].get("outcome", "")) == "ok",
		"the landed reply emits exactly ONE `deciding end` (outcome=ok)")
	var ledger: Dictionary = SB.agent_llm(a.id)
	_check(c, absf(float(ledger.get("cost", 0.0)) - 0.0123) < 0.0001,
		"the call's realized cost is attributed to the causing NPC")
	# The orphaned worker's LATE timeout must NOT emit a second end for the already-ended decide.
	OS.delay_msec(700)
	hs._drain_pending()
	_check(c, _facts_for(root, a.id).size() == 2,
		"a late worker error adds NO duplicate end fact (still exactly one pair)")
	hs.shutdown()
	srv.stop()

# (c) --------------------------------------------------------------------------------------------
static func _c_beat_completes_under_hung_sidecar(c: Dictionary, root: Node) -> void:
	print("[deciding (c): the WHOLE deliberation beat completes under a hung sidecar]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var AR: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	EB.clear()
	var srv := _hung_server(58733)
	var hs := HttpSidecar.new("http://127.0.0.1:58733")
	hs.timeout_sec = 0.3
	var saved: SidecarClient = SB.client
	SB.set_client(hs)
	# Pick an agent that re-decides THIS beat under the LLM brain's stagger (k=2).
	var CL: Object = root.get_node("/root/Clock")
	var chosen: Agent = null
	for cand in AG.all():
		if cand.deliberates and AR.in_cohort(cand.id, int(CL.beat_index), 2):
			chosen = cand
			break
	AR.always_active[chosen.id] = true
	AR.run_beat()
	AR.always_active.erase(chosen.id)
	SB.set_client(saved)
	# The beat NEVER hangs: the chosen agent committed a real (offline) action this beat.
	var acted := false
	for e in EB.events("agent_action"):
		if String((e.get("data", {}) as Dictionary).get("actor", "")) == chosen.id:
			acted = true
	_check(c, acted, "the cohort agent committed an offline decision the same beat (cadence holds)")
	_check(c, _facts_for(root, chosen.id).size() >= 1, "the in-flight decide announced itself (begin fact)")
	hs.shutdown()
	srv.stop()

# (d) --------------------------------------------------------------------------------------------
static func _d_playlog_and_thinking_tell(c: Dictionary, root: Node) -> void:
	print("[deciding (d): PlayLog renders the fact; the thought panel shows the thinking tell]")
	var PL: Object = root.get_node("/root/PlayLog")
	var line_begin: String = PL._world_line("deciding", {"agent": "clerk_voss", "phase": "begin", "beat": 3})
	var line_end: String = PL._world_line("deciding", {"agent": "clerk_voss", "phase": "end", "beat": 3, "outcome": "timeout"})
	_check(c, not line_begin.begins_with("*") and line_begin.length() > 0,
		"PlayLog renders `deciding begin` as a readable line (not the raw-event fallback)")
	_check(c, line_end.contains("timeout") or line_end.contains("instinct"),
		"PlayLog's end line surfaces a cut-short deliberation")
	# The thought panel: while a decide is in flight for the inspected agent, the card shows the
	# thinking tell instead of a stale thought; the end fact restores the live thought.
	var AG: Object = root.get_node("/root/Agents")
	var WS: Object = root.get_node("/root/WorldState")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	var a: Agent = AG.all()[0]
	var card: Node = load("res://ui/CharacterCard.tscn").instantiate()
	root.add_child(card)
	await (Engine.get_main_loop() as SceneTree).process_frame
	WS.inspect_requested.emit(a.id)
	await (Engine.get_main_loop() as SceneTree).process_frame
	EB.emit_event("deciding", {"agent": a.id, "phase": "begin", "beat": 1})
	await (Engine.get_main_loop() as SceneTree).process_frame
	var thought_label: Label = card.get_node("Margin/Body/Thought")
	_check(c, thought_label.text.to_lower().contains("thinking"),
		"an in-flight decide shows the THINKING tell on the inspect card")
	EB.emit_event("deciding", {"agent": a.id, "phase": "end", "beat": 1, "outcome": "ok"})
	await (Engine.get_main_loop() as SceneTree).process_frame
	_check(c, not thought_label.text.to_lower().contains("thinking"),
		"the end fact restores the live thought line")
	card.queue_free()
	await (Engine.get_main_loop() as SceneTree).process_frame
