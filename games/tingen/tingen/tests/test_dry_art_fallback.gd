extends SceneTree
## B2 retro-audit, finding 1 (the M18 overclaim): a DRY gunman NPC must "lean on free arts",
## not livelock. Run directly:
##   godot --headless --path tingen -s tests/test_dry_art_fallback.gd
## or as part of the master suite (run_tests.gd calls run_all_on(), sharing pass/fail totals).
##
## Watched RED before the fix: TacticalBrain._select_ability filters only on ledger_ready +
## range and ranks by class_pref, while CombatExecutor.try_cast asks the cost_provider LAST —
## a no_ammo refusal never marks the ledger, so the refused art stays "ready", stays top pick,
## and the NPC re-locks it every tactical tick forever. A dry wren/nighthawk never cast ANYTHING.
##
## The fix under test is executor/tactics-driver level ONLY (TacticalBrain's pure statics are
## M9 vector seeds and stay untouched): a cost refusal stamps a short executor-side
## retry-suppression that excludes the art from tactics RE-SELECTION; it never marks the cast
## ledger and never changes try_cast's own refusal contract (the player's direct-input path
## still refuses no_ammo with NO cooldown burned, exactly as test_npc_cost_loot pins).
##
## All scenarios run the REAL live NPC stack: bind + AgentCostProvider + enable_tactics — the
## exact seam NPC.gd wires when a bound NPC enters combat — stepped deterministically (fixed dt,
## no RNG, no wall time). Remove the suppression wire and these scenarios go RED.

const DT: float = 1.0 / 60.0

# --- Standalone entry -----------------------------------------------------------------------------
func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all_on(root)
	print("\n=== dry-art fallback: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

# --- Shared-suite entry (run_tests.gd) ------------------------------------------------------------
static func run_all() -> Dictionary:
	var st := Engine.get_main_loop() as SceneTree
	return _run(st.root)

static func run_all_on(root_node: Node) -> Dictionary:
	return _run(root_node)

static func _run(root: Node) -> Dictionary:
	var c: Dictionary = {"passed": 0, "failed": 0}
	_dry_gunman_falls_back_to_free_art(c, root)
	_dry_melee_fallback_in_reach(c, root)
	_direct_try_cast_contract_unchanged(c, root)
	_resupply_reenables_the_gun(c, root)
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

# --- staging helpers (test_npc_cost_loot conventions) ----------------------------------------------
static func _stage(root: Node, id: String, form: String, room_id: String, pos: Vector2) -> Agent:
	var a := Agent.new(id)
	a.display_name = id
	a.room = room_id
	a.position = pos
	a.combat_form = form
	a.in_combat = true
	root.get_node("/root/Agents")._agents[id] = a
	return a

## The EXACT live NPC combat seam (NPC.gd): bind + AgentCostProvider + enable_tactics.
static func _live_npc_executor(agent: Agent) -> CombatExecutor:
	var ex := CombatExecutor.new()
	ex.bind(agent)
	ex.cost_provider = AgentCostProvider.new(agent)
	ex.enable_tactics()
	return ex

static func _step(executors: Array, seconds: float) -> void:
	var steps := int(round(seconds * 60.0))
	for _i in steps:
		for ex in executors:
			ex.step_combat(DT)

## Every ability this caster telegraphed since seq_floor, in order.
static func _casts_by(root: Node, caster_id: String, seq_floor: int = 0) -> Array:
	var out: Array = []
	for ev in root.get_node("/root/EventBus").events("ability_cast_started"):
		if int(ev.get("seq", 0)) <= seq_floor:
			continue
		var d: Dictionary = ev.get("data", {})
		if String(d.get("caster", "")) == caster_id:
			out.append(String(d.get("ability", "")))
	return out

static func _seq_now(root: Node) -> int:
	var evs: Array = root.get_node("/root/EventBus").latest(1)
	return int((evs[0] as Dictionary).get("seq", 0)) if not evs.is_empty() else 0

static func _cleanup(root: Node, executors: Array) -> void:
	for ex in executors:
		ex.free()
	CombatExecutor.reset_last_attackers()
	root.get_node("/root/Agents").rebuild()

# --- (1) the M18 claim itself: a dry ranged gunman leans on its FREE art ---------------------------
static func _dry_gunman_falls_back_to_free_art(c: Dictionary, root: Node) -> void:
	print("[dry gunman (wren_human, tactics on, ZERO ammo) casts its free art within bounded beats]")
	var seq0 := _seq_now(root)
	var wren := _stage(root, "t_b2_dry_wren", "wren_human", "t_b2_arena_a", Vector2.ZERO)
	wren.add_item("revolver", 1)   # the granting weapon, but NO rounds — a dry gun
	wren.combat_intent = {"mode": "engage", "target": "t_b2_prey_a"}
	_stage(root, "t_b2_prey_a", "civilian", "t_b2_arena_a", Vector2(300, 0))
	var ex := _live_npc_executor(wren)
	_step([ex], 2.0)   # 16 tactical beats — "bounded" is generous here
	var casts := _casts_by(root, "t_b2_dry_wren", seq0)
	_check(c, not casts.is_empty(),
		"a dry gunman under enable_tactics still casts SOMETHING within 2s (no livelock)")
	_check(c, casts.has("mark_prey"),
		"…and what it casts is its FREE art, mark_prey (the M18 'leans on free arts' claim)")
	_check(c, not casts.has("revolver_shot"),
		"…and the dry revolver_shot never telegraphs (a refused cost cannot enter windup)")
	_cleanup(root, [ex])

# --- (2) the melee fallback: a dry nighthawk in reach swings the cleaver ---------------------------
static func _dry_melee_fallback_in_reach(c: Dictionary, root: Node) -> void:
	print("[dry nighthawk_pursuer in melee reach falls back to its free cleaver_swipe]")
	var seq0 := _seq_now(root)
	var hawk := _stage(root, "t_b2_dry_hawk", "nighthawk_pursuer", "t_b2_arena_b", Vector2.ZERO)
	hawk.add_item("revolver", 1)   # dry: weapon carried, zero rounds
	hawk.combat_intent = {"mode": "engage", "target": "t_b2_prey_b"}
	_stage(root, "t_b2_prey_b", "civilian", "t_b2_arena_b", Vector2(30, 0))
	var ex := _live_npc_executor(hawk)
	_step([ex], 2.0)
	var casts := _casts_by(root, "t_b2_dry_hawk", seq0)
	_check(c, casts.has("cleaver_swipe"),
		"a dry nighthawk with prey in arm's reach swings its free cleaver within 2s")
	_check(c, not casts.has("revolver_shot"),
		"…and never telegraphs the dry revolver")
	_cleanup(root, [ex])

# --- (3) the invariant: try_cast's own refusal contract is UNTOUCHED (player direct-input path) ----
static func _direct_try_cast_contract_unchanged(c: Dictionary, root: Node) -> void:
	print("[suppression is re-SELECTION only: direct try_cast still refuses no_ammo, burns nothing]")
	var dry := _stage(root, "t_b2_direct", "wren_human", "t_b2_arena_c", Vector2.ZERO)
	dry.add_item("revolver", 1)
	var ex := _live_npc_executor(dry)
	var r1: Dictionary = ex.try_cast("revolver_shot", "")
	_check(c, not bool(r1.get("ok", false)) and String(r1.get("reason", "")) == "no_ammo",
		"first direct try_cast refuses with 'no_ammo'")
	# The IMMEDIATE retry — the player's direct input path hammers this — must behave identically:
	# the tactics-side suppression must never surface as a new refusal reason or a burned cooldown.
	var r2: Dictionary = ex.try_cast("revolver_shot", "")
	_check(c, not bool(r2.get("ok", false)) and String(r2.get("reason", "")) == "no_ammo",
		"an immediate direct retry STILL refuses 'no_ammo' (suppression never gates try_cast itself)")
	_check(c, ex.phase == "idle" and CombatResolver.ledger_ready(ex.ledger, "revolver_shot", ex.now_ms()),
		"…and no refusal burned a cooldown or entered windup (the M18 ledger invariant holds)")
	_check(c, dry.item_count("revolver_round") == 0, "…and nothing was half-paid")
	_cleanup(root, [ex])

# --- (4) suppression is a RETRY-suppression: resupplied rounds re-enable the gun -------------------
static func _resupply_reenables_the_gun(c: Dictionary, root: Node) -> void:
	print("[the suppression self-heals: rounds gained mid-fight bring revolver_shot back]")
	var seq0 := _seq_now(root)
	var wren := _stage(root, "t_b2_resupply", "wren_human", "t_b2_arena_d", Vector2.ZERO)
	wren.add_item("revolver", 1)
	wren.combat_intent = {"mode": "engage", "target": "t_b2_prey_d"}
	_stage(root, "t_b2_prey_d", "civilian", "t_b2_arena_d", Vector2(300, 0))
	var ex := _live_npc_executor(wren)
	_step([ex], 1.0)                    # runs dry-locked: refusal stamped, free art cast
	wren.add_item("revolver_round", 2)  # mid-fight resupply
	_step([ex], 4.0)                    # any short retry-suppression must lapse well within this
	var casts := _casts_by(root, "t_b2_resupply", seq0)
	_check(c, casts.has("revolver_shot"),
		"once rounds exist again the tactic loop re-selects revolver_shot (no permanent lockout)")
	_cleanup(root, [ex])
