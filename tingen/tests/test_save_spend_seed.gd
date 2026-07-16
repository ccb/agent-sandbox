extends SceneTree
## M21 harness — three HIGH bugs: cross-session save integrity (B3), LLM budget/pause (B4),
## per-run reseed (B5). Run standalone with:
##   godot --headless --path tingen -s tests/test_save_spend_seed.gd
## Also folded into the main suite (run_tests.gd `_test_save_spend_seed`) via the SAME run_all()
## entry point, so both share one set of assertions.
##
## The pins:
##   B3  the cross-session DISK save (SaveManager.save_game/load_game) round-trips EVERY run-scoped
##       subsystem — meters/progression/leads/shop included — and the disk key set matches the
##       in-memory _snapshot key set (they must not drift again).
##   B4  a session BUDGET GUARD in SidecarBridge routes to the ambient brain (no LLM call) past a
##       ceiling; GMPanel narration makes ZERO LLM calls while the game is paused.
##   B5  two fresh start_run()s reseed WorldManager.seed_value to a DIFFERENT value; a within-run
##       checkpoint restore keeps the seed STABLE.

## N1 (sprint safety): the temp save slot rides the harness sandbox (never the real user dir).
static func TMP_SAVE() -> String:
	return preload("res://src/TestSandbox.gd").path("test_save_spend_seed.json")

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	_b3_disk_roundtrips_every_subsystem(c)
	_b3_disk_and_snapshot_same_key_set(c)
	_b4_budget_guard_routes_to_ambient(c)
	_b4_paused_game_makes_zero_llm_narration(c)
	_b4_over_budget_gates_and_counts_gm_narration(c)
	_b5_two_fresh_runs_reseed_differently(c)
	_b5_checkpoint_restore_keeps_seed_stable(c)
	return c

# --- B3: cross-session save integrity -----------------------------------------------------------
static func _b3_disk_roundtrips_every_subsystem(c: Dictionary) -> void:
	print("[B3: cross-session disk save round-trips meters/progression/leads/shop]")
	var root := _r()
	var SM: Object = root.get_node("/root/SaveManager")
	var RM: Object = root.get_node("/root/RunManager")
	var M: Object = root.get_node("/root/Meters")
	var P: Object = root.get_node("/root/Progression")
	var LS: Object = root.get_node("/root/LeadSystem")
	var S: Object = root.get_node_or_null("/root/Shop")

	# A clean run, then DIRTY every subsystem the bug dropped.
	RM.start_run()
	M.set_meter("doom", 42.0)
	M.set_meter("madness", 37.0)
	P.from_dict({"pathway": "hunter", "sequence": 8, "granted_arts": ["mark_prey"], "deed_done": true})
	LS.slot_run(4242)
	LS.follow("butcher_iron_cross")
	if S != null:
		S.from_dict({"restocks_used": 2})

	var want_meters: Dictionary = M.to_dict()
	var want_prog: Dictionary = P.to_dict()
	var want_leads: Dictionary = LS.to_dict()
	var want_shop: Dictionary = S.to_dict() if S != null else {}

	# Persist to a temp slot, then SCRUB the live world (simulating a fresh process at title).
	_check(c, bool(SM.save_game(TMP_SAVE())), "save_game writes the temp slot")
	M.reset(); P.reset(); LS.reset()
	if S != null:
		S.reset()

	# RED before the fix: these four were never written, so load leaves the SCRUBBED state.
	_check(c, not _dict_eq(M.to_dict(), want_meters), "reset scrubbed the meters (state was live)")
	_check(c, P.sequence() != int(want_prog.get("sequence", 8)), "reset scrubbed progression")

	_check(c, bool(SM.load_game(TMP_SAVE())), "load_game reads the temp slot")

	_check(c, _dict_eq(M.to_dict(), want_meters), "B3: meters (Doom/Madness/…) restored from disk")
	_check(c, _dict_eq(P.to_dict(), want_prog), "B3: progression (rank + granted art) restored from disk")
	_check(c, _dict_eq(LS.to_dict(), want_leads), "B3: leads (the followed lead) restored from disk")
	if S != null:
		_check(c, _dict_eq(S.to_dict(), want_shop), "B3: shop (stock latch) restored from disk")

	# Leave a clean world for later tests.
	RM.start_run()

static func _b3_disk_and_snapshot_same_key_set(c: Dictionary) -> void:
	print("[B3: disk save manifest and in-memory _snapshot cover the same subsystem key set]")
	var root := _r()
	var SM: Object = root.get_node("/root/SaveManager")
	var RM: Object = root.get_node("/root/RunManager")
	RM.start_run()
	# The disk keys minus the file-envelope + scene-placement meta (version/scene_path/player_pos).
	_check(c, bool(SM.save_game(TMP_SAVE())), "save_game writes the temp slot (key-set probe)")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(TMP_SAVE()))
	var disk: Dictionary = parsed if parsed is Dictionary else {}
	var disk_keys: Array = []
	for k in disk.keys():
		if String(k) in ["version", "scene_path", "player_pos"]:
			continue
		disk_keys.append(String(k))
	disk_keys.sort()
	# The snapshot keys minus its restore-placement meta (day/scene/player_pos).
	var snap: Dictionary = RM._snapshot()
	var snap_keys: Array = []
	for k in snap.keys():
		if String(k) in ["day", "scene", "player_pos"]:
			continue
		snap_keys.append(String(k))
	snap_keys.sort()
	_check(c, disk_keys == snap_keys,
		"B3: disk key set == snapshot key set (no drift)\n    disk=%s\n    snap=%s" % [disk_keys, snap_keys])

# --- B4: LLM budget guard + paused-game gate ----------------------------------------------------
static func _b4_budget_guard_routes_to_ambient(c: Dictionary) -> void:
	print("[B4: past the budget ceiling SidecarBridge routes to the ambient brain (no LLM call)]")
	var root := _r()
	var SB: Object = root.get_node("/root/SidecarBridge")
	var counting := _CountingSidecar.new()
	SB.set_client(counting)
	SB.reset_budget()
	SB.set_budget(1.0, 0)   # $1.00 cost ceiling; no call cap for this probe

	var snaps: Array = [{"agent_id": "probe", "position": [0, 0], "phase": "morning", "nearby": []}]

	# Under budget -> the live client IS asked (control).
	var before := counting.propose_calls
	SB.propose(snaps)
	_check(c, counting.propose_calls == before + 1, "under budget -> the live client is called (control)")

	# Blow the ceiling, then a further propose must NOT reach the client — it degrades to ambient.
	SB.note_llm_spend(5.0)
	_check(c, bool(SB.budget_exceeded()), "budget_exceeded() true once cumulative spend passes the ceiling")
	var gated := counting.propose_calls
	var out: Array = SB.propose(snaps)
	_check(c, counting.propose_calls == gated, "B4: over budget -> LLM client NOT called (routed to ambient)")
	_check(c, out.size() == 1, "the ambient fallback still returns one action per snapshot (world never freezes)")

	# A call-count ceiling degrades the same way.
	SB.reset_budget()
	SB.set_budget(0.0, 1)   # one LLM call allowed, then degrade
	SB.note_llm_spend(0.0)  # records one call
	_check(c, bool(SB.budget_exceeded()), "budget_exceeded() true once the call ceiling is hit")
	var gated2 := counting.propose_calls
	SB.propose(snaps)
	_check(c, counting.propose_calls == gated2, "B4: over call-cap -> LLM client NOT called")

	SB.reset_budget()
	SB.set_client(_al(root, "AmbientSidecar", true))

static func _b4_paused_game_makes_zero_llm_narration(c: Dictionary) -> void:
	print("[B4: a PAUSED game makes zero GM LLM narration calls; unpaused+open still narrates]")
	var root := _r()
	var GP: Object = root.get_node_or_null("/root/GMPanel")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var EB: Object = root.get_node("/root/EventBus")
	var Clock: Object = root.get_node("/root/Clock")
	if GP == null:
		_check(c, true, "GMPanel autoload absent under this harness — narration gate not exercised")
		return
	var mock := MockSidecar.new()
	mock.set_narrate("THE CITY HOLDS ITS BREATH")
	SB.set_client(mock)
	SB.reset_budget()

	# Ensure the panel is OPEN so the gate would otherwise permit narration.
	if not GP.is_open():
		GP.toggle()

	# Control: NOT paused -> the digest narrates (proves the event yields a line + the gate opens).
	Clock.paused = false
	GP.reset()
	EB.clear()
	EB.emit_event("npc_said", {"agent": "clerk_voss", "text": "They gather at the crypt."})
	GP._digest_tick()
	GP.flush_narration()
	_check(c, String(GP.entry(0).get("narration", "")) == "THE CITY HOLDS ITS BREATH",
		"control: unpaused + panel open -> the digest is narrated")

	# The pin: PAUSED -> the same event digests, but NO LLM narration call fires.
	Clock.paused = true
	GP.reset()
	EB.clear()
	EB.emit_event("npc_said", {"agent": "clerk_voss", "text": "They gather at the crypt."})
	GP._digest_tick()
	GP.flush_narration()
	_check(c, GP.entry_count() == 1, "paused: the deterministic digest still records the beat")
	_check(c, String(GP.entry(0).get("narration", "")) == "",
		"B4: paused game makes ZERO LLM narration calls (narration stays empty)")

	# Restore state for later tests.
	Clock.paused = false
	if GP.is_open():
		GP.toggle()
	EB.clear()
	SB.set_client(_al(root, "AmbientSidecar", true))

static func _b4_over_budget_gates_and_counts_gm_narration(c: Dictionary) -> void:
	print("[B4 #1: GM narration is CAPPED by (and COUNTS toward) the same budget guard as propose]")
	var root := _r()
	var GP: Object = root.get_node_or_null("/root/GMPanel")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var EB: Object = root.get_node("/root/EventBus")
	var Clock: Object = root.get_node("/root/Clock")
	if GP == null:
		_check(c, true, "GMPanel autoload absent under this harness — narration budget gate not exercised")
		return
	var billing := _BillingNarrateSidecar.new()
	billing.set_narrate("THE LEDGER CLOSES")   # a would-be summary; only fires if the guard permits it
	SB.set_client(billing)
	SB.reset_budget()
	Clock.paused = false
	if not GP.is_open():
		GP.toggle()

	# (1) COUNTS: under a generous ceiling the live /narrate call is billed to the guard, so narration
	# spend accrues on the SAME meter as propose/converse (not a free, uncounted side channel).
	SB.set_budget(100.0, 0)
	var calls_before: int = int(SB.llm_calls())
	var spend_before: float = float(SB.llm_spend())
	GP.reset(); EB.clear()
	EB.emit_event("npc_said", {"agent": "clerk_voss", "text": "The hour is close."})
	GP._digest_tick()
	GP.flush_narration()
	_check(c, billing.narrate_calls == 1, "under budget -> the live narrate call fires (control)")
	_check(c, String(GP.entry(0).get("narration", "")) == "THE LEDGER CLOSES",
		"under budget -> the narration lands")
	_check(c, int(SB.llm_calls()) == calls_before + 1,
		"B4 #1: a realized narrate call COUNTS toward the budget guard's call total")
	_check(c, absf(float(SB.llm_spend()) - (spend_before + billing.narrate_cost)) < 0.0001,
		"B4 #1: the narrate call's cost is added to cumulative LLM spend")

	# (2) CAPPED: blow the ceiling, then the SAME open+unpaused panel fires ZERO /narrate calls — the
	# narration degrades with the rest of LLM spend instead of billing every 30s forever.
	SB.reset_budget()
	SB.set_budget(1.0, 0)
	SB.note_llm_spend(5.0)   # over the $1.00 ceiling
	_check(c, bool(SB.budget_exceeded()), "budget_exceeded() true (setup for the narration cap)")
	var gated := billing.narrate_calls
	GP.reset(); EB.clear()
	EB.emit_event("npc_said", {"agent": "clerk_voss", "text": "The hour is close."})
	GP._digest_tick()
	GP.flush_narration()
	_check(c, billing.narrate_calls == gated,
		"B4 #1: over budget -> GM narration makes ZERO LLM calls (no /narrate POST)")
	_check(c, GP.entry_count() == 1, "over budget: the deterministic digest still records the beat")
	_check(c, String(GP.entry(0).get("narration", "")) == "",
		"B4 #1: over budget -> the entry stays digest-only (no narration)")

	# Restore state for later tests.
	SB.reset_budget()
	SB.set_budget(SidecarBridge.DEFAULT_COST_CEILING, SidecarBridge.DEFAULT_CALL_CEILING)
	if GP.is_open():
		GP.toggle()
	EB.clear()
	SB.set_client(_al(root, "AmbientSidecar", true))

# --- B5: per-run reseed -------------------------------------------------------------------------
static func _b5_two_fresh_runs_reseed_differently(c: Dictionary) -> void:
	print("[B5: two fresh start_run()s reseed WorldManager.seed_value to a DIFFERENT value]")
	var root := _r()
	var RM: Object = root.get_node("/root/RunManager")
	var WM: Object = root.get_node("/root/WorldManager")
	# Seed the GLOBAL RNG deterministically so the assertion is reproducible: two consecutive draws
	# from the seeded stream differ, so the reseed DEMONSTRABLY happens (not left at the old value).
	seed(20260711)
	RM.start_run()
	var s1: int = int(WM.seed_value)
	RM.start_run()
	var s2: int = int(WM.seed_value)
	_check(c, s1 != s2, "B5: run 2 seed (%d) != run 1 seed (%d) — the run re-randomizes" % [s2, s1])

static func _b5_checkpoint_restore_keeps_seed_stable(c: Dictionary) -> void:
	print("[B5: a within-run checkpoint restore keeps WorldManager.seed_value STABLE]")
	var root := _r()
	var RM: Object = root.get_node("/root/RunManager")
	var WM: Object = root.get_node("/root/WorldManager")
	RM.start_run()
	var base_seed: int = int(WM.seed_value)
	RM.checkpoint_night()             # snapshots the run (seed included)
	WM.seed_value = 987654321         # dirty it AFTER the checkpoint
	RM.end_run("death")               # has a checkpoint -> restore (the day costs, the seed does not)
	_check(c, int(WM.seed_value) == base_seed,
		"B5: a death-restore reloads the checkpointed seed (%d), no reshuffle" % base_seed)
	RM.start_run()

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

static func _r() -> Node:
	return (Engine.get_main_loop() as SceneTree).root

## Resolve an autoload node; when `fresh` and it is a SidecarClient script, hand back a NEW instance
## (AmbientSidecar is a class, not an autoload node — restore the offline default after a mock swap).
static func _al(root: Node, name: String, fresh: bool) -> Object:
	if name == "AmbientSidecar":
		return AmbientSidecar.new()
	return root.get_node_or_null("/root/" + name)

## Compare two subsystem dicts for RESTORED-STATE equality. Both are normalized through a JSON
## round-trip first: a disk save→load coerces whole-number ints to floats (1 -> 1.0), which is a
## JSON representation artifact, NOT state loss (the game reads these via int()/float() casts). The
## in-memory `want` gets the same coercion so the compare is apples-to-apples.
static func _dict_eq(a: Dictionary, b: Dictionary) -> bool:
	return _norm(a) == _norm(b)

static func _norm(d: Variant) -> String:
	return JSON.stringify(JSON.parse_string(JSON.stringify(d, "", true, true)), "", true, true)

## A MockSidecar that COUNTS propose() calls, so a test can prove the budget guard bypasses the LLM.
class _CountingSidecar extends MockSidecar:
	var propose_calls: int = 0
	func propose(snapshots: Array) -> Array:
		propose_calls += 1
		return super.propose(snapshots)

## A MockSidecar standing in for the LIVE narrate path: it COUNTS narrate() calls and returns a
## realized "cost" key like HttpSidecar does, so a test can prove GM narration is both gated by and
## counted toward the session budget guard (B4 #1).
class _BillingNarrateSidecar extends MockSidecar:
	var narrate_calls: int = 0
	var narrate_cost: float = 0.25
	func narrate(request: Dictionary) -> Dictionary:
		narrate_calls += 1
		var base: Dictionary = super.narrate(request)   # {} or {"summary": ...} per scripted_narration
		base["cost"] = narrate_cost                     # the "cost" key == a realized /narrate round-trip
		return base
