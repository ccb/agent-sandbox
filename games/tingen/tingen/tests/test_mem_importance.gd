extends SceneTree
## LAB PULL-IN P1 — memory-importance LADDER + one-shot `just_*` transition markers.
## Pattern port from the lab's Penn-sim work (lab_adoption_report §1): importance becomes a number
## written ON the memory row AT WRITE TIME (ladder: 1.0 ambient / 2.0 action-outcome / 8.0 pinned)
## instead of being keyword-guessed at prompt-build; Perception._event_importance is DEMOTED to a
## fallback scorer for unscored/legacy rows. State flips additionally write a `just_*` one-shot
## transition marker consumed by exactly ONE deliberation snapshot.
## Standalone: godot --headless --path tingen -s tests/test_mem_importance.gd
## Also folded into the main suite (run_tests.gd `_test_mem_importance`) via the SAME run_all().

func _init() -> void:
	await process_frame
	await process_frame
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_mem_importance: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_fan_rows_carry_authored_importance(c, root)
	_b_decide_request_reads_stored_importance(c, root)
	_c_just_markers_one_shot(c, root)
	_d_rows_roundtrip_and_stay_readable(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
	root.get_node("/root/Agents").rebuild()
	root.get_node("/root/EventBus").clear()
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

## Importance (0.0 = unscored) of one short_memory row, whatever its shape.
static func _imp(row: Variant) -> float:
	return Agent.mem_importance(row)

# (a) --------------------------------------------------------------------------------------------
## Stimulus fan blocks author the ladder value ON the row: room entry = ambient 1.0; a witnessed
## act (gather/telegraph/strike) = action-outcome 2.0; a transform = pinned 8.0.
static func _a_fan_rows_carry_authored_importance(c: Dictionary, root: Node) -> void:
	print("[mem importance (a): fanned rows carry their authored ladder value]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var WS: Object = root.get_node("/root/WorldState")
	AG.rebuild()
	AG.ensure_player_proxy(Vector2.ZERO, "cathedral_crypt")
	var voss: Agent = AG.get_agent("clerk_voss")
	var dalia: Agent = AG.get_agent("fishwife_dalia")
	if not voss.has_method("remember_scored"):
		_check(c, false, "Agent.remember_scored exists (write-time importance seam)")
		return
	voss.room = "cathedral_crypt"; voss.position = Vector2(50, 0); voss.short_memory.clear()
	dalia.room = "cathedral_crypt"; dalia.position = Vector2(100, 0); dalia.short_memory.clear()
	# Room entry -> ambient 1.0 on the witness's row.
	WS.room_changed.emit("cathedral_crypt", "res://scenes/CathedralCrypt.tscn")
	_check(c, voss.short_memory.size() == 1, "entry fan lands one row")
	_check(c, absf(_imp(voss.short_memory[-1]) - 1.0) < 0.001,
		"room-entry fan row is AMBIENT 1.0 (got %.1f)" % _imp(voss.short_memory[-1]))
	_check(c, Agent.mem_text(voss.short_memory[-1]).contains("entered"),
		"the scored row still reads as the plain fact text")
	# A witnessed act -> action-outcome 2.0.
	voss.short_memory.clear()
	EB.emit_event("item_gathered", {"actor": "fishwife_dalia", "item_id": "ritual_salt", "count": 1})
	_check(c, voss.short_memory.size() == 1 and absf(_imp(voss.short_memory[-1]) - 2.0) < 0.001,
		"witnessed gather fan row is ACTION-OUTCOME 2.0 (got %.1f)" % _imp(voss.short_memory[-1]))
	# A strike -> the victim's own felt row is also action-outcome 2.0.
	dalia.short_memory.clear()
	EB.emit_event("agent_attacked", {"actor": "clerk_voss", "target": "fishwife_dalia", "damage": 34})
	_check(c, not dalia.short_memory.is_empty() and absf(_imp(dalia.short_memory[0]) - 2.0) < 0.001,
		"the victim's felt-blow row is ACTION-OUTCOME 2.0")
	# A transform -> pinned 8.0 in every witness.
	voss.short_memory.clear()
	EB.emit_event("transformed", {"agent": "fishwife_dalia", "form": "bieber_monster"})
	_check(c, voss.short_memory.size() == 1 and absf(_imp(voss.short_memory[-1]) - 8.0) < 0.001,
		"witnessed transform fan row is PINNED 8.0 (got %.1f)" % _imp(voss.short_memory[-1]))
	AG.rebuild()

# (b) --------------------------------------------------------------------------------------------
## decide_request forwards the STORED importance for scored rows; the old keyword scorer survives
## ONLY as the fallback for unscored/legacy string rows (6.0 occult keyword / 3.0 default).
static func _b_decide_request_reads_stored_importance(c: Dictionary, root: Node) -> void:
	print("[mem importance (b): decide_request reads stored values; keyword scorer is the fallback]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var a: Agent = AG.get_agent("clerk_voss")
	if not a.has_method("remember_scored"):
		_check(c, false, "Agent.remember_scored exists")
		return
	a.short_memory.clear(); a.mem_total = 0
	a.remember_scored("the bell tolled over the market", 1.0)          # scored ambient
	a.remember_scored("something else stands in their skin", 8.0)      # scored pinned
	a.remember("a Nighthawk watched the cathedral")                    # legacy unscored: keyword 6.0
	a.remember("bought bread at the corner stall")                     # legacy unscored: default 3.0
	var snap: Dictionary = Perception.build_snapshot(a, Vector2.ZERO)
	var req: Dictionary = Perception.decide_request(snap, "s")
	var ev: Array = req.get("events", [])
	_check(c, ev.size() == 4, "all four rows ride as events (got %d)" % ev.size())
	if ev.size() != 4:
		return
	_check(c, absf(float(ev[0]["importance"]) - 1.0) < 0.001, "scored ambient row forwards 1.0")
	_check(c, absf(float(ev[1]["importance"]) - 8.0) < 0.001, "scored pinned row forwards 8.0")
	_check(c, absf(float(ev[2]["importance"]) - 6.0) < 0.001, "unscored occult row falls back to the keyword scorer (6.0)")
	_check(c, absf(float(ev[3]["importance"]) - 3.0) < 0.001, "unscored mundane row falls back to the default (3.0)")
	_check(c, String(ev[1]["text"]) == "something else stands in their skin",
		"a scored row's TEXT rides clean (no dict wrapper leaks into the prompt)")
	AG.rebuild()

# (c) --------------------------------------------------------------------------------------------
## State flips write a `just_*` one-shot transition marker; the deliberation beat consumes each
## marker into exactly ONE snapshot (present once, gone after), and decide_request forwards it.
static func _c_just_markers_one_shot(c: Dictionary, root: Node) -> void:
	print("[mem importance (c): just_* transition markers are written on flips and consumed once]")
	var AG: Object = root.get_node("/root/Agents")
	var CM: Object = root.get_node("/root/CombatMode")
	var AR: Object = root.get_node("/root/AgentRuntime")
	var SB: Object = root.get_node("/root/SidecarBridge")
	AG.rebuild()
	var a: Agent = AG.get_agent("clerk_voss")
	if not ("transition_markers" in a):
		_check(c, false, "Agent carries transition_markers (state-flip seam)")
		return
	# Combat enter/exit flips write markers (deduped, ordered).
	a.transition_markers.clear()
	CM.enter_combat(a)
	_check(c, a.transition_markers.has("just_entered_combat"), "entering combat writes just_entered_combat")
	CM.enter_combat(a)   # idempotent flip -> no duplicate marker
	_check(c, a.transition_markers.count("just_entered_combat") == 1, "an idempotent re-enter writes no duplicate")
	CM.exit_combat(a)
	_check(c, a.transition_markers.has("just_left_combat"), "leaving combat writes just_left_combat")
	# A portal crossing writes just_changed_room.
	a.transition_markers.clear()
	a.room = "cathedral_nave"
	a.position = Vector2(1680, 160)   # ON the nave->crypt portal
	ActionCommit.commit({"actor": a.id, "verb": "move_to", "args": {"target": "crypt_altar"}}, a)
	_check(c, a.room == "cathedral_crypt" and a.transition_markers.has("just_changed_room"),
		"crossing a portal writes just_changed_room")
	# The deliberation beat consumes markers into exactly ONE snapshot.
	var rec_src := GDScript.new()
	rec_src.source_code = "extends MockSidecar\nvar seen: Array = []\nfunc propose(snapshots: Array) -> Array:\n\tseen.append(snapshots.duplicate(true))\n\treturn super.propose(snapshots)\n"
	rec_src.reload()
	var rec: MockSidecar = rec_src.new()
	var saved_client: SidecarClient = SB.client
	SB.set_client(rec)
	AR.always_active[a.id] = true
	a.transition_markers.clear()
	a.mark_transition("just_entered_combat")
	AR.run_beat()
	AR.run_beat()
	AR.always_active.erase(a.id)
	SB.set_client(saved_client)
	var first_snap := _snap_for(rec.seen[0] if rec.seen.size() > 0 else [], a.id)
	var second_snap := _snap_for(rec.seen[1] if rec.seen.size() > 1 else [], a.id)
	var first_marks: Array = first_snap.get("just_happened", []) if first_snap.get("just_happened") is Array else []
	var second_marks: Array = second_snap.get("just_happened", []) if second_snap.get("just_happened") is Array else []
	_check(c, first_marks.has("just_entered_combat"), "beat 1's snapshot carries the marker")
	_check(c, second_marks.is_empty(), "beat 2's snapshot does NOT (consumed exactly once)")
	_check(c, a.transition_markers.is_empty(), "the agent's marker store is empty after consumption")
	# decide_request forwards the consumed markers to the brain as perception facts.
	var snap: Dictionary = Perception.build_snapshot(a, Vector2.ZERO)
	snap["just_happened"] = ["just_entered_combat"]
	var req: Dictionary = Perception.decide_request(snap, "s")
	var perc: Dictionary = req.get("perception", {})
	_check(c, (perc.get("just_happened", []) as Array).has("just_entered_combat"),
		"decide_request forwards just_happened into perception")
	# Ephemeral scratch: markers never persist through save/load (like pending_cast).
	a.mark_transition("just_left_combat")
	var d: Dictionary = a.to_dict()
	var b := Agent.new()
	b.from_dict(d)
	_check(c, b.transition_markers.is_empty(), "markers are run scratch — never persisted")
	AG.rebuild()

static func _snap_for(snaps: Array, agent_id: String) -> Dictionary:
	for s in snaps:
		if s is Dictionary and String((s as Dictionary).get("agent_id", "")) == agent_id:
			return s
	return {}

# (d) --------------------------------------------------------------------------------------------
## Scored dict rows survive the save/load round-trip, and every legacy consumer keeps reading
## clean TEXT (talk_to hearsay must never leak a "{ \"text\": ... }" wrapper into a rumor).
static func _d_rows_roundtrip_and_stay_readable(c: Dictionary, root: Node) -> void:
	print("[mem importance (d): scored rows round-trip; consumers read clean text]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var a: Agent = AG.get_agent("clerk_voss")
	if not a.has_method("remember_scored"):
		_check(c, false, "Agent.remember_scored exists")
		return
	a.short_memory.clear(); a.mem_total = 0
	a.remember_scored("saw the rite advance at the warehouse", 8.0)
	var b := Agent.new()
	b.from_dict(a.to_dict())
	_check(c, absf(_imp(b.short_memory[-1]) - 8.0) < 0.001, "a scored row's importance survives save/load")
	_check(c, Agent.mem_text(b.short_memory[-1]) == "saw the rite advance at the warehouse",
		"a scored row's text survives save/load")
	# talk_to passes the TEXT of a scored last observation as the rumor, not a stringified dict.
	var listener: Agent = AG.get_agent("fishwife_dalia")
	listener.room = a.room
	listener.position = a.position + Vector2(20, 0)
	listener.short_memory.clear()
	ActionCommit.commit({"actor": a.id, "verb": "talk_to",
		"args": {"agent": listener.id, "topic": "the rite"}}, a)
	var heard := Agent.mem_text(listener.short_memory[-1]) if not listener.short_memory.is_empty() else ""
	_check(c, heard.contains("saw the rite advance at the warehouse"), "the hearsay carries the observation text")
	_check(c, not heard.contains("{"), "no dict wrapper leaks into the rumor line")
	AG.rebuild()
