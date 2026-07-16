extends SceneTree
## LAB PULL-IN P5 — the repeat-failure FREEZE GUARD. Counts consecutive IDENTICAL gate-failed
## commits per agent; on the 3rd it forces idle/replan, writes an informed-failure memory row
## (generalizing gather_item's contention-fact pattern), and emits ONE `agent_stuck` EventBus
## fact so the GM sees stuck NPCs. A DIFFERENT failure — or any success — resets the counter, so
## normal play never trips it (the pinned sims stay byte-identical).
## Standalone: godot --headless --path tingen -s tests/test_stuck_guard.gd
## Also folded into the main suite (run_tests.gd `_test_stuck_guard`) via the SAME run_all().

func _init() -> void:
	await process_frame
	await process_frame
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_stuck_guard: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_failure_classifier(c)
	_b_three_identical_failures_trip_the_guard(c, root)
	_c_different_failure_resets(c, root)
	_d_success_resets(c, root)
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

# (a) --------------------------------------------------------------------------------------------
## The classifier: "" for successes and informed partial states; a stable key (verb+args+reason)
## for every commit the gate itself refused.
static func _a_failure_classifier(c: Dictionary) -> void:
	print("[stuck guard (a): failure_key classifies gate refusals, never successes]")
	var atk := {"verb": "attack", "args": {"target": "x"}}
	_check(c, ActionCommit.failure_key(atk, {"attacked": "x", "hit": false}) != "",
		"an out-of-reach swing is a gate failure")
	_check(c, ActionCommit.failure_key(atk, {"attacked": "x", "hit": true, "target_hp": 66.0, "downed": false}) == "",
		"a landed strike is never a failure")
	var gat := {"verb": "gather_item", "args": {"item_id": "salt"}}
	_check(c, ActionCommit.failure_key(gat, {"gathered": "salt", "added": false, "reason": "none_here", "count": 0}).contains("none_here"),
		"an empty-pile gather keys on its refusal reason")
	_check(c, ActionCommit.failure_key(gat, {"gathered": "salt", "added": true, "from_ground": true, "count": 1}) == "",
		"a successful gather is never a failure")
	var mov := {"verb": "move_to", "args": {"target": "nowhere"}}
	_check(c, ActionCommit.failure_key(mov, {"noop": "unresolved target 'nowhere'"}) != "",
		"an unresolved move noop is a gate failure")
	_check(c, ActionCommit.failure_key(mov, {"moved_to": [1.0, 2.0]}) == "",
		"a normal step is never a failure")
	var rit := {"verb": "perform_ritual_step", "args": {"step": "s"}}
	_check(c, ActionCommit.failure_key(rit, {"ritual_step": "s", "advanced": false}) != "",
		"an off-site rite step is a gate failure")
	_check(c, ActionCommit.failure_key(rit, {"ritual_step": "s", "deposited": "salt", "advanced": false}) == "",
		"a phase-1 material deposit is progress, never a failure")
	# IDENTICAL means identical: same verb + args + reason share a key; different args do not.
	var k1 := ActionCommit.failure_key(atk, {"attacked": "x", "hit": false})
	var k2 := ActionCommit.failure_key(atk, {"attacked": "x", "hit": false})
	var k3 := ActionCommit.failure_key({"verb": "attack", "args": {"target": "y"}}, {"attacked": "y", "hit": false})
	_check(c, k1 == k2 and k1 != k3, "the key is stable for identical failures, distinct across targets")

# (b) --------------------------------------------------------------------------------------------
static func _b_three_identical_failures_trip_the_guard(c: Dictionary, root: Node) -> void:
	print("[stuck guard (b): the 3rd identical gate failure forces replan + row + fact]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var AR: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	EB.clear()
	AR._fail_streaks.clear()   # section isolation, like the EB/AG resets
	var a: Agent = AG.get_agent("clerk_voss")
	var prey: Agent = AG.get_agent("old_neil")
	a.room = "city"
	prey.room = "cathedral_crypt"   # unreachable: every swing is the identical gate failure
	a.short_memory.clear()
	var mock := MockSidecar.new()
	mock.set_action(a.id, {"actor": a.id, "verb": "attack", "args": {"target": prey.id}})
	SB.set_client(mock)
	AR.always_active[a.id] = true
	AR.run_beat()
	AR.run_beat()
	_check(c, EB.events("agent_stuck").is_empty(), "two identical failures do NOT trip the guard")
	AR.run_beat()
	var stuck: Array = EB.events("agent_stuck")
	_check(c, stuck.size() == 1, "the 3rd identical failure emits exactly ONE agent_stuck fact")
	if stuck.size() == 1:
		var d: Dictionary = stuck[0].get("data", {})
		_check(c, String(d.get("agent", "")) == a.id and String(d.get("verb", "")) == "attack"
			and int(d.get("failures", 0)) == 3,
			"the fact names the agent, the hammered verb, and the failure count")
	_check(c, String(a.current_action.get("verb", "")) == "idle",
		"the agent is FORCED to idle/replan (current_action cleared to idle)")
	var row := Agent.mem_text(a.short_memory[-1]) if not a.short_memory.is_empty() else ""
	_check(c, row.contains("three times") and row.contains("attack"),
		"an informed-failure memory row tells the next deliberation WHY to replan")
	_check(c, absf(Agent.mem_importance(a.short_memory[-1]) - 8.0) < 0.001,
		"the stuck row is PINNED (8.0) so it cannot fade before the next decision")
	# The guard RESETS after firing: two more identical failures alone do not re-trip it.
	AR.run_beat()
	AR.run_beat()
	_check(c, EB.events("agent_stuck").size() == 1, "the counter reset after firing (no re-trip at 5)")
	AR.always_active.erase(a.id)
	AG.rebuild()

# (c) --------------------------------------------------------------------------------------------
static func _c_different_failure_resets(c: Dictionary, root: Node) -> void:
	print("[stuck guard (c): a DIFFERENT failure resets the counter]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var AR: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	EB.clear()
	AR._fail_streaks.clear()   # section isolation
	var a: Agent = AG.get_agent("clerk_voss")
	var n1: Agent = AG.get_agent("old_neil")
	var n2: Agent = AG.get_agent("dockhand_pell")
	a.room = "city"
	n1.room = "cathedral_crypt"
	n2.room = "cathedral_crypt"
	var mock := MockSidecar.new()
	# A queue alternating two DIFFERENT gate failures — never 3 identical in a row.
	mock.set_action(a.id, [
		{"actor": a.id, "verb": "attack", "args": {"target": n1.id}},
		{"actor": a.id, "verb": "attack", "args": {"target": n2.id}},
		{"actor": a.id, "verb": "attack", "args": {"target": n1.id}},
		{"actor": a.id, "verb": "attack", "args": {"target": n2.id}},
		{"actor": a.id, "verb": "attack", "args": {"target": n1.id}},
		{"actor": a.id, "verb": "attack", "args": {"target": n2.id}},
	])
	SB.set_client(mock)
	AR.always_active[a.id] = true
	for i in 6:
		AR.run_beat()
	_check(c, EB.events("agent_stuck").is_empty(),
		"six alternating failures never trip the guard (identical means identical)")
	AR.always_active.erase(a.id)
	AG.rebuild()

# (d) --------------------------------------------------------------------------------------------
static func _d_success_resets(c: Dictionary, root: Node) -> void:
	print("[stuck guard (d): any success resets the streak]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var AR: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	EB.clear()
	AR._fail_streaks.clear()   # section isolation
	var a: Agent = AG.get_agent("clerk_voss")
	var prey: Agent = AG.get_agent("old_neil")
	a.room = "city"
	a.position = Vector2(100, 100)
	prey.room = "cathedral_crypt"
	var fail := {"actor": a.id, "verb": "attack", "args": {"target": prey.id}}
	var ok := {"actor": a.id, "verb": "move_to", "args": {"target": "200,200"}}
	var mock := MockSidecar.new()
	mock.set_action(a.id, [fail, fail, ok, fail, fail])
	SB.set_client(mock)
	AR.always_active[a.id] = true
	for i in 5:
		AR.run_beat()
	_check(c, EB.events("agent_stuck").is_empty(),
		"fail-fail-SUCCESS-fail-fail never reaches three consecutive (reset on success)")
	AR.always_active.erase(a.id)
	AG.rebuild()
