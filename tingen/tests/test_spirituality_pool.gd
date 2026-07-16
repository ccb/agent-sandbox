extends SceneTree
## M31 — the PLAYER'S SPIRITUALITY (mana) POOL: a regenerating reservoir OWNED by the PlayerCombat
## node and enforced EXCLUSIVELY inside PlayerCombat.try_pay, so the Hermit's star/ritual casts have a
## real cadence instead of playing as a strictly-easier free-fire Hunter. Standalone headless harness.
## Run: godot --headless --path tingen -s tests/test_spirituality_pool.gd
## Also folded into the main suite (run_tests.gd `_test_spirituality_pool`) via the SAME run_all() entry.
##
## DETERMINISM is the whole point: the pool + its refusal live ONLY on PlayerCombat (fields + try_pay);
## the pinned sims (combat_sim / run_combat_vectors / full_run) never route a cast through
## PlayerCombat.try_pay (their bots are bare bx.bind(proxy) with NO cost_provider) and enemies pay via
## AgentCostProvider (untouched) — so NPC casters stay byte-identical free casters. The two green-guards
## below (4.4 enemy-not-gated, 4.5 drift alarm) fail LOUDLY if that invariant is ever broken.
##
## Covers (TDD):
##  4.1 RED  — try_pay enforces + debits the pool (check-all-then-deduct; never half-pays)
##  4.2 RED  — a cast through the executor is refused "no_spirit" when empty, burning NO cooldown
##  4.3 RED  — step_spirituality(dt) is a pure per-frame regen that clamps at MAX
##  4.4 GUARD — an enemy caster bound to AgentCostProvider is NOT gated by the player pool
##  4.5 GUARD — the Hunter default kit never touches spirituality + the spirit-costed set is pinned

const DT: float = 1.0 / 60.0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_spirituality_pool: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_t_try_pay_enforce_and_debit(c)
	_t_executor_refused_no_spirit(c)
	_t_regen_step(c)
	_t_reserve_fork(c)
	_t_enemy_caster_not_gated(c)
	_t_drift_alarm(c, root)
	# Leave a clean world (Hunter default) for whatever the shared suite finished with.
	var P: Object = root.get_node_or_null("/root/Progression")
	if P != null:
		P.select_pathway("hunter")
	return c

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

## Read the pool through the dynamic seam so this file PARSES before the field exists (TDD RED):
## a missing property reads back null -> a sentinel that no assert accepts.
static func _spirit(pc: Object) -> float:
	var v: Variant = pc.get("spirituality")
	return float(v) if v != null else -1.0

static func _step(ex: CombatExecutor, seconds: float) -> void:
	var t := 0.0
	while t < seconds:
		ex.step_combat(DT)
		t += DT

# 4.1 --------------------------------------------------------------------------------------------
## Pure unit: PlayerCombat.new() (proxy/body null; star_brand names only spirituality, so try_pay's
## ammo + stamina legs never touch the null proxy/body). The pool enforces the cost and debits it, and
## a refusal NEVER half-pays. RED today: try_pay has no spirituality branch -> every cast "pays" ok and
## the pool is never touched.
static func _t_try_pay_enforce_and_debit(c: Dictionary) -> void:
	print("[M31 4.1: try_pay enforces + debits the spirituality pool; a refusal never half-pays]")
	var pc = PlayerCombat.new()
	pc.set("spirituality", 25.0)
	# star_brand's authored cost is {spirituality: 10} (data). Kept literal here so the arithmetic
	# 25 -> 15 -> 5 -> refuse is a pure statement of the pool math, independent of a live AbilityDB.
	var ability := {"id": "star_brand", "cost": {"spirituality": 10.0}}
	var r1: Dictionary = pc.try_pay(ability)
	_check(c, bool(r1.get("ok", false)) and is_equal_approx(_spirit(pc), 15.0),
		"first star_brand pays 10 -> pool 25 becomes 15 (got %s, ok=%s)" % [str(_spirit(pc)), str(r1.get("ok"))])
	var r2: Dictionary = pc.try_pay(ability)
	_check(c, bool(r2.get("ok", false)) and is_equal_approx(_spirit(pc), 5.0),
		"second star_brand pays 10 -> pool 15 becomes 5 (got %s)" % str(_spirit(pc)))
	var r3: Dictionary = pc.try_pay(ability)
	_check(c, not bool(r3.get("ok", true)) and String(r3.get("reason", "")) == "no_spirit",
		"third star_brand is REFUSED with reason 'no_spirit' (pool 5 < cost 10)")
	_check(c, is_equal_approx(_spirit(pc), 5.0),
		"the refused cast NEVER half-paid — the pool is still exactly 5 (got %s)" % str(_spirit(pc)))
	pc.free()

# 4.2 --------------------------------------------------------------------------------------------
## Through the real CombatExecutor: with an EMPTY pool the executor's cost seam refuses "no_spirit",
## and — because the cost is asked LAST, before ledger_mark/phase — the cast burns NO cooldown and
## stays idle (never half-committed). RED today: try_pay pays free -> the cast is ACCEPTED (windup,
## ledger marked), so all three asserts fail.
static func _t_executor_refused_no_spirit(c: Dictionary) -> void:
	print("[M31 4.2: an executor cast is refused 'no_spirit' on an empty pool, burning NO cooldown]")
	var enemyless := Agent.new("m31_caster")
	var ex := CombatExecutor.new()
	ex.bind(enemyless)
	var pc = PlayerCombat.new()
	pc.set("spirituality", 0.0)
	ex.cost_provider = pc
	var before_ready: bool = CombatResolver.ledger_ready(ex.ledger, "star_brand", ex.now_ms())
	var r: Dictionary = ex.try_cast("star_brand", "")
	_check(c, not bool(r.get("ok", true)) and String(r.get("reason", "")) == "no_spirit",
		"the executor refuses star_brand with 'no_spirit' when the pool is empty (got %s)" % str(r))
	_check(c, ex.phase == "idle",
		"a refused cast stays idle — no windup entered (phase=%s)" % str(ex.phase))
	_check(c, before_ready and CombatResolver.ledger_ready(ex.ledger, "star_brand", ex.now_ms()),
		"the refused cast burns NO cooldown — the ledger is untouched (asked last in the chain)")
	ex.free()
	pc.free()

# 4.3 --------------------------------------------------------------------------------------------
## step_spirituality(dt) is a PURE per-frame regen (mirrors Player.step_stamina): it lifts the pool by
## SPIRIT_REGEN * dt and clamps at MAX. Drained-to-one-primary is a short bounded wait, never a
## dead-end. RED today: PlayerCombat has no step_spirituality method, so has_method is false and the
## pool never climbs. M34 RETUNE (MAX 60->40, REGEN 8->4): the constant-dependent numbers move — a fully
## drained pool now takes ~2.5s to afford one star_brand, and the reservoir clamps at 40.
static func _t_regen_step(c: Dictionary) -> void:
	print("[M31 4.3: step_spirituality(dt) is a pure per-frame regen that clamps at MAX]")
	var pc = PlayerCombat.new()
	_check(c, pc.has_method("step_spirituality"),
		"PlayerCombat exposes a pure regen helper step_spirituality(dt)")
	# From a FULLY drained pool, ~2.5s (150 frames) of regen crosses the 10 star_brand cost (REGEN 4 ·
	# 2.5s = 10). Step a hair past that (160 frames) so the >= 10 assert is float-clean — a bounded wait.
	pc.set("spirituality", 0.0)
	if pc.has_method("step_spirituality"):
		for i in 160:
			pc.call("step_spirituality", DT)
	_check(c, _spirit(pc) >= 10.0,
		"~2.7s (160 frames) of regen lift the pool from drained (0) past a 10 cost (got %s) — a bounded wait, not a dead-end" % str(_spirit(pc)))
	var pay: Dictionary = pc.try_pay({"id": "star_brand", "cost": {"spirituality": 10.0}})
	_check(c, bool(pay.get("ok", false)) and _spirit(pc) < 10.0,
		"after regen the primary casts again and debits the pool (post-cast %s)" % str(_spirit(pc)))
	# HUD read seam: the getters mirror the live pool (max is the constant reservoir, M34-retuned to 40).
	if pc.has_method("spirituality_now") and pc.has_method("spirituality_max"):
		_check(c, is_equal_approx(float(pc.call("spirituality_now")), _spirit(pc))
				and is_equal_approx(float(pc.call("spirituality_max")), 40.0),
			"the HUD getters expose the live pool + a 40 max reservoir (M34 retune 60->40)")
	else:
		_check(c, false, "PlayerCombat exposes spirituality_now()/spirituality_max() for the HUD")
	# Clamp: near-full, several frames of regen never overfill past MAX (40).
	pc.set("spirituality", 39.0)
	if pc.has_method("step_spirituality"):
		for j in 30:
			pc.call("step_spirituality", DT)
	_check(c, is_equal_approx(_spirit(pc), 40.0),
		"regen clamps hard at MAX (40) — it never overfills (got %s)" % str(_spirit(pc)))
	pc.free()

# 4.6 --------------------------------------------------------------------------------------------
## M34 RESERVE FORK: the retune (MAX 40 / REGEN 4) turns the primary into a real push-your-luck reserve
## instead of a free-fire hose. From a FULL pool, casting star_brand (10) with one cooldown of regen
## between shots empties in a bounded handful (net drain 6/s -> ~6 casts, was ~26 at 60/8), and the
## drained throttle (10/REGEN) is a real pause (~2.5s, was 1.25). It is NOT a dead-end: recovery to one
## star_brand is <=3.5s and to one collapsing_star (20) <=6.0s. Pure loop — no proxy/body/tree.
## Mutation-RED at the OLD constants: casts_before_dry ~26 (fails <=8) and the throttle 1.25 (fails >=2.0).
static func _t_reserve_fork(c: Dictionary) -> void:
	print("[M34 4.6: the retuned pool is a push-your-luck reserve — bounded casts before dry, a real throttle, no dead-end]")
	var pc = PlayerCombat.new()
	var star := {"id": "star_brand", "cost": {"spirituality": 10.0}}
	# From FULL: cast when affordable, then one cooldown (1.0s) of regen between casts. Count the casts
	# the reserve buys before it runs dry (the push-your-luck window).
	var casts := 0
	for i in 100:
		if not bool(pc.try_pay(star).get("ok", false)):
			break
		casts += 1
		pc.step_spirituality(1.0)
	_check(c, casts <= 8,
		"a full reserve buys a BOUNDED burst — %d star_brand casts before dry (<=8; RED at old 60/8 ~26)" % casts)
	_check(c, casts >= 4,
		"…but not a starved trickle — %d casts before dry (>=4, guards against over-cutting the pool)" % casts)
	# The drained throttle + the no-dead-end recovery bounds, straight off the retuned constants.
	var regen := float(pc.SPIRIT_REGEN)
	var throttle_star := 10.0 / regen
	_check(c, throttle_star >= 2.0,
		"drained->one star_brand is a REAL pause: %.2fs (>=2.0; RED at old REGEN 8 -> 1.25)" % throttle_star)
	_check(c, throttle_star <= 3.5,
		"…yet bounded (%.2fs <=3.5) — a drained Hermit recovers its primary quickly, never a dead-end" % throttle_star)
	var recovery_collapsing := 20.0 / regen
	_check(c, recovery_collapsing <= 6.0,
		"drained->one collapsing_star (20) is bounded too: %.2fs (<=6.0) — no starvation dead-end" % recovery_collapsing)
	pc.free()

# 4.4 GREEN-GUARD --------------------------------------------------------------------------------
## An enemy caster pays through AgentCostProvider (which leaves spirituality FREE, by decision). It
## must be UNAFFECTED by the player's pool: with the player pool at 0 the enemy still casts star_brand
## repeatedly, and the player's pool is never touched. Fails only if spirituality gating wrongly leaks
## into AgentCostProvider / the shared Agent (a determinism breach for the sims).
static func _t_enemy_caster_not_gated(c: Dictionary) -> void:
	print("[M31 4.4 GUARD: an enemy caster (AgentCostProvider) is NOT gated by the player's pool]")
	var enemy := Agent.new("m31_enemy")
	var ex := CombatExecutor.new()
	ex.bind(enemy)
	ex.cost_provider = AgentCostProvider.new(enemy)
	var pc = PlayerCombat.new()
	pc.set("spirituality", 0.0)
	var r1: Dictionary = ex.try_cast("star_brand", "")
	_check(c, bool(r1.get("ok", false)) and String(r1.get("reason", "")) != "no_spirit",
		"the enemy casts star_brand with the player pool empty — not gated (got %s)" % str(r1))
	_step(ex, 1.5)   # clear the 0.3s windup + 1.0s cooldown
	var r2: Dictionary = ex.try_cast("star_brand", "")
	_check(c, bool(r2.get("ok", false)) and String(r2.get("reason", "")) != "no_spirit",
		"the enemy casts star_brand a second time — still never 'no_spirit' (got %s)" % str(r2))
	_check(c, is_equal_approx(_spirit(pc), 0.0),
		"the enemy's casts never touched the PLAYER's spirituality pool (still %s)" % str(_spirit(pc)))
	ex.free()
	pc.free()

# 4.5 GREEN-GUARD --------------------------------------------------------------------------------
## Pins the sims: the Hunter default kit is exactly [revolver_shot, dash, paper_charm, pistol_whip] and
## the arts the sim bot actually casts (revolver_shot, dash) carry NO spirituality cost, so the new
## pool can never change a pinned fight. The spirit-costed SET is a drift alarm: if a future edit adds
## or removes a spirituality cost, this fires so determinism gets re-checked.
static func _t_drift_alarm(c: Dictionary, root: Node) -> void:
	print("[M31 4.5 GUARD: Hunter kit is spirituality-free + the spirit-costed set is pinned (drift alarm)]")
	var RM: Object = root.get_node("/root/RunManager")
	var AG: Object = root.get_node("/root/Agents")
	var P: Object = root.get_node("/root/Progression")
	var DB: Object = root.get_node("/root/AbilityDB")
	# Fresh Hunter Seq-9 so the base kit has no earned additions (mirrors the hermit-pathway staging).
	RM.start_run("hunter")
	AG.rebuild()
	P.select_pathway("hunter")
	var kit: Array = DB.kit_for("player")
	_check(c, kit == ["revolver_shot", "dash", "paper_charm", "pistol_whip"],
		"the Hunter default kit is exactly [revolver_shot, dash, paper_charm, pistol_whip]: %s" % str(kit))
	for aid in ["revolver_shot", "dash"]:
		var cost: Variant = (DB.ability_for(aid) as Dictionary).get("cost", {})
		var s := float((cost as Dictionary).get("spirituality", 0.0)) if cost is Dictionary else 0.0
		_check(c, s == 0.0, "%s carries NO spirituality cost (a sim-bot art, so the pool can't touch the sims)" % aid)
	# The complete spirit-costed set (order-independent), as authored in data/abilities.json.
	var spirit_set := {}
	for aid in DB.all_ability_ids():
		var cost: Variant = (DB.ability_for(String(aid)) as Dictionary).get("cost", {})
		if cost is Dictionary and float((cost as Dictionary).get("spirituality", 0.0)) > 0.0:
			spirit_set[String(aid)] = true
	# N5 (M_death): the alarm fired on the Death package landing — the five spirit-costed Death arts
	# (censer_ember/grave_ring/wailing_host player-side + requiem_bolt/choir_of_the_dead on cassian's
	# NPC kits) join the pin DELIBERATELY. Determinism re-checked: none is in the Hunter kit or any
	# pinned A-H sim; NPC casters stay un-gated (4.4); combat_sim A-H stdout re-verified byte-identical.
	var expected := {
		"star_brand": true, "ward_circle": true, "collapsing_star": true,
		"paper_charm": true, "finch_recite": true, "ink_flood": true,
		"censer_ember": true, "grave_ring": true, "wailing_host": true,
		"requiem_bolt": true, "choir_of_the_dead": true,
	}
	_check(c, spirit_set == expected,
		"the spirituality-costed set is exactly %s (drift alarm) — got %s" % [str(expected.keys()), str(spirit_set.keys())])
