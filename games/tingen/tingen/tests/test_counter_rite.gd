extends SceneTree
## M28 — the COUNTER-RITE: the ONLY player verb that pushes Doom DOWN (direction v2 §6).
## Standalone headless harness. Run: godot --headless --path tingen -s tests/test_counter_rite.gd
## Also folded into the main suite (run_tests.gd `_test_counter_rite`) via the SAME run_all() entry.
##
## A warding rite worked against the cult's descent: it SPENDS occult ingredients (Inventory), REDUCES
## Doom directly (Meters), ADDS impede to the SummoningPlan (a weaker climax), and TAXES Notice (the
## push-your-luck cost — buying time draws the Beyond's eye). Data-driven: the rite is authored in
## data/rituals.json under `counter_rite`; the engine node knows no item id or number of its own.
##
## The pins:
##  (a) performing the rite REDUCES Doom, RAISES Notice, ADDS impede, and CONSUMES the ingredients
##  (b) it refuses CLEANLY without the ingredients (no Doom/Notice/inventory change)
##  (c) it is the ONLY player verb that pushes Doom DOWN (Doom strictly decreases), and it is data-driven

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()
	var r: Dictionary = run_all()
	print("\n=== test_counter_rite: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_reduces_doom_taxes_notice_consumes(c, root)
	_b_refuses_without_ingredients(c, root)
	_c_data_driven_and_only_down_push(c, root)
	# Leave a clean world for whatever runs next in the shared suite.
	root.get_node("/root/RunManager").start_run()
	root.get_node("/root/Agents").rebuild()
	return c

# --- helpers ------------------------------------------------------------------------------------
static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

## Stock the player's inventory with a rite's full ingredient bill.
static func _stock(root: Node, cr: Object) -> void:
	var inv: Object = root.get_node("/root/Inventory")
	inv.clear()
	var ing: Dictionary = cr.ingredients()
	for item_id in ing:
		inv.add(String(item_id), int(ing[item_id]))

# (a) --------------------------------------------------------------------------------------------
static func _a_reduces_doom_taxes_notice_consumes(c: Dictionary, root: Node) -> void:
	print("[counter-rite (a): performing it reduces Doom, taxes Notice, adds impede, consumes the ingredients]")
	var CR: Object = root.get_node_or_null("/root/CounterRite")
	_check(c, CR != null, "CounterRite autoload is registered")
	if CR == null:
		return
	var RM: Object = root.get_node("/root/RunManager")
	var M: Object = root.get_node("/root/Meters")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var inv: Object = root.get_node("/root/Inventory")
	RM.start_run()
	SP.reset()
	_stock(root, CR)
	M.set_meter("doom", 50.0)
	M.set_meter("notice", 0.0)
	var impede_before: float = SP.impede_score
	var d: Dictionary = CR.rite_def()
	var doom_cut := float(d.get("doom_reduction", 0.0))
	var notice_cost := float(d.get("notice_cost", 0.0))
	var impede := float(d.get("impede", 0.0))
	_check(c, bool(CR.can_perform().get("ok", false)), "with the ingredients in hand the rite CAN be performed")
	var res: Dictionary = CR.perform()
	_check(c, bool(res.get("ok", false)), "the rite performs (ok)")
	_check(c, absf(M.get_meter("doom") - (50.0 - doom_cut)) < 0.01,
		"Doom DROPPED by the authored amount (50 -> %.1f, -%.0f)" % [M.get_meter("doom"), doom_cut])
	_check(c, M.get_meter("doom") < 50.0, "Doom went DOWN (the anti-Doom verb)")
	_check(c, absf(M.get_meter("notice") - notice_cost) < 0.01,
		"Notice ROSE by the authored tax (0 -> %.1f, +%.0f) — the Beyond's eye turned" % [M.get_meter("notice"), notice_cost])
	_check(c, absf(SP.impede_score - (impede_before + impede)) < 0.01,
		"impede ADDED to the cult's SummoningPlan (+%.0f -> a weaker descent)" % impede)
	# Every authored ingredient was consumed.
	var all_consumed := true
	for item_id in CR.ingredients():
		if inv.count_of(String(item_id)) != 0:
			all_consumed = false
	_check(c, all_consumed, "the occult ingredients were CONSUMED from the inventory")

# (b) --------------------------------------------------------------------------------------------
static func _b_refuses_without_ingredients(c: Dictionary, root: Node) -> void:
	print("[counter-rite (b): it refuses cleanly with no ingredients — no Doom/Notice/inventory change]")
	var CR: Object = root.get_node_or_null("/root/CounterRite")
	if CR == null:
		return
	var M: Object = root.get_node("/root/Meters")
	var inv: Object = root.get_node("/root/Inventory")
	inv.clear()
	M.set_meter("doom", 40.0)
	M.set_meter("notice", 5.0)
	_check(c, not bool(CR.can_perform().get("ok", false)), "with no ingredients the rite CANNOT be performed")
	var res: Dictionary = CR.perform()
	_check(c, not bool(res.get("ok", false)), "the rite REFUSES (not ok)")
	_check(c, is_equal_approx(M.get_meter("doom"), 40.0), "a refused rite does NOT move Doom (still 40)")
	_check(c, is_equal_approx(M.get_meter("notice"), 5.0), "a refused rite does NOT move Notice (still 5)")

# (c) --------------------------------------------------------------------------------------------
static func _c_data_driven_and_only_down_push(c: Dictionary, root: Node) -> void:
	print("[counter-rite (c): the rite is data-driven, and it is the anti-Doom verb (Doom strictly decreases)]")
	var CR: Object = root.get_node_or_null("/root/CounterRite")
	if CR == null:
		return
	var M: Object = root.get_node("/root/Meters")
	var d: Dictionary = CR.rite_def()
	_check(c, not d.is_empty() and (d.get("ingredients", {}) as Dictionary).size() >= 1,
		"the counter-rite is authored in data/rituals.json with an ingredient bill")
	_check(c, float(d.get("doom_reduction", 0.0)) > 0.0 and float(d.get("notice_cost", 0.0)) > 0.0,
		"the rite authors a positive Doom reduction AND a positive Notice tax (push-your-luck)")
	# The anti-Doom property, exercised: from a mid Doom, a stocked rite strictly LOWERS it.
	_stock(root, CR)
	M.set_meter("doom", 60.0)
	M.set_meter("notice", 0.0)
	var before: float = M.get_meter("doom")
	CR.perform()
	_check(c, M.get_meter("doom") < before,
		"the counter-rite pushed Doom DOWN (%.1f -> %.1f) — the only player verb that does" % [before, M.get_meter("doom")])
