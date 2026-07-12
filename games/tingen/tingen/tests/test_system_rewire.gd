extends SceneTree
## M25 (backlog "M18") harness — reconnect the three orphaned player systems (prayer, occult
## tools, ambient events) to the LIVE v2 economy (Meters + LeadSystem). Run standalone with:
##   godot --headless --path tingen -s tests/test_system_rewire.gd
## Also folded into the main suite (run_tests.gd `_test_system_rewire`) via the SAME run_all()
## entry point, so both share one set of assertions.
##
## The pins (the RED evidence before the rewire: every effect landed on a DEAD legacy WorldState
## pressure and never moved a live meter; occult leads went to WorldState.set_lead, not LeadSystem):
##   (a) a prayer effect moves a LIVE meter by the mapped amount and does NOT drive the legacy
##       WorldState pressure (the dead path is no longer the driver).
##   (b) using an occult tool pays its live-meter cost (fatigue->Madness, attention->Notice) and its
##       lead output lands in LeadSystem.active_leads() — NOT WorldState.set_lead().
##   (c) an EventManager pressure effect moves a live meter, not the dead WorldState pressure.
##   (d) the legacy->meter mappings respect the M4 clamps (0..100) and scrub on a per-run reset().
##   (e) engine-neutrality: the mapping is one documented data table covering the five §8.3 pressures;
##       an unmapped pressure is a safe no-op (combat determinism is proven by the external sims).

func _init() -> void:
	await process_frame
	await process_frame
	var r: Dictionary = run_all()
	print("\n=== %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	_a_prayer_moves_live_meter_not_legacy(c)
	_b_occult_tool_pays_live_cost_and_lead_reaches_leadsystem(c)
	_c_event_effect_moves_live_meter(c)
	_d_mappings_clamp_and_reset(c)
	_e_mapping_is_a_documented_neutral_table(c)
	return c

# --- (a) prayer -> live meters ------------------------------------------------------------------
static func _a_prayer_moves_live_meter_not_legacy(c: Dictionary) -> void:
	print("[M25 (a): a prayer effect moves a LIVE meter, not the dead legacy pressure]")
	var root := _r()
	var M: Object = root.get_node("/root/Meters")
	var WS: Object = root.get_node("/root/WorldState")
	var PS: Object = root.get_node("/root/PrayerService")

	# --- punished: corruption*sev -> Doom, (panic+fatigue)*sev -> Madness ---
	M.reset()
	WS.set_pressure(&"corruption", 5.0)
	WS.set_pressure(&"panic", 5.0)
	WS.set_pressure(&"fatigue", 10.0)
	var doom0: float = M.get_meter("doom")
	var mad0: float = M.get_meter("madness")
	var corr0: float = WS.corruption
	var panic0: float = WS.panic
	var fat0: float = WS.fatigue
	var god: Dictionary = load("res://src/GodDB.gd").get_def("goddess_of_night")
	PS._apply_effects("goddess_of_night", god, "punished", 2)
	# corruption 10*2=20 -> Doom +20 ; panic 5*2=10 + fatigue 8*2=16 -> Madness +26
	_ok(c, is_equal_approx(M.get_meter("doom") - doom0, 20.0),
		"punished prayer raises Doom by the mapped corruption amount (+20, got %.1f)" % (M.get_meter("doom") - doom0))
	_ok(c, is_equal_approx(M.get_meter("madness") - mad0, 26.0),
		"punished prayer raises Madness by mapped panic+fatigue (+26, got %.1f)" % (M.get_meter("madness") - mad0))
	_ok(c, is_equal_approx(WS.corruption, corr0) and is_equal_approx(WS.panic, panic0) and is_equal_approx(WS.fatigue, fat0),
		"punished prayer does NOT drive the dead legacy pressures (corruption/panic/fatigue unmoved)")

	# --- granted, opposing god: fatigue relief -15 -> Madness -15 (observable from a raised floor) ---
	M.reset()
	M.set_meter("madness", 40.0)
	WS.set_pressure(&"fatigue", 30.0)
	var fat1: float = WS.fatigue
	PS._apply_effects("goddess_of_night", god, "granted", 1)
	_ok(c, is_equal_approx(M.get_meter("madness"), 25.0),
		"granted prayer eases Madness by the mapped fatigue-relief (40 - 15 = 25, got %.1f)" % M.get_meter("madness"))
	_ok(c, is_equal_approx(WS.fatigue, fat1),
		"granted prayer does NOT drive the dead legacy fatigue pressure")

	# --- granted, outer god: corruption+12 & cult_readiness+8 both -> Doom (the gate widens, +20) ---
	M.reset()
	WS.set_pressure(&"corruption", 5.0)
	WS.set_pressure(&"cult_readiness", 0.0)
	var doom1: float = M.get_meter("doom")
	var cr0: float = WS.cult_readiness
	var ogod: Dictionary = load("res://src/GodDB.gd").get_def("outer_god")
	PS._apply_effects("outer_god", ogod, "granted", 1)
	_ok(c, is_equal_approx(M.get_meter("doom") - doom1, 20.0),
		"the outer god's granted power widens the gate -> Doom +20 (got %.1f)" % (M.get_meter("doom") - doom1))
	_ok(c, is_equal_approx(WS.cult_readiness, cr0),
		"outer-god prayer does NOT drive the dead legacy cult_readiness pressure")

# --- (b) occult tool -> live cost + LeadSystem --------------------------------------------------
static func _b_occult_tool_pays_live_cost_and_lead_reaches_leadsystem(c: Dictionary) -> void:
	print("[M25 (b): an occult tool pays its live-meter cost; its lead lands in LeadSystem]")
	var root := _r()
	var M: Object = root.get_node("/root/Meters")
	var WS: Object = root.get_node("/root/WorldState")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var LS: Object = root.get_node("/root/LeadSystem")
	var INV: Object = root.get_node("/root/Inventory")

	M.reset()
	OTM.rebuild()
	LS.reset()
	# residue_sight requires the spirit_lens item, costs fatigue 6 / attention 2, no ingredients.
	INV.add("spirit_lens", 1)
	var notice0: float = M.get_meter("notice")
	var mad0: float = M.get_meter("madness")
	var att0: float = WS.attention
	var fat0: float = WS.fatigue
	var lead0: String = WS.current_lead
	var leads_before: int = LS.active_leads().size()

	var res: Dictionary = OTM.use("residue_sight")
	_ok(c, bool(res.get("ok", false)), "residue_sight used ok")
	# attention 2 -> Notice +2 (divination is the canon exposure channel), fatigue 6 -> Madness +6.
	_ok(c, is_equal_approx(M.get_meter("notice") - notice0, 2.0),
		"the sight tool pays Notice for its attention cost (+2, got %.1f)" % (M.get_meter("notice") - notice0))
	_ok(c, is_equal_approx(M.get_meter("madness") - mad0, 6.0),
		"the sight tool pays Madness for its fatigue cost (+6, got %.1f)" % (M.get_meter("madness") - mad0))
	_ok(c, is_equal_approx(WS.attention, att0) and is_equal_approx(WS.fatigue, fat0),
		"the tool does NOT drive the dead legacy attention/fatigue pressures")
	# The lead lands in LeadSystem.active_leads (not WorldState.set_lead).
	var leads_after: Array = LS.active_leads()
	_ok(c, leads_after.size() == leads_before + 1, "the occult lead is slotted into LeadSystem (active_leads grew by 1)")
	var found := false
	for lead in leads_after:
		if String(lead.get("source", "")) == "residue_sight" and String(lead.get("subject", "")) == String(res.get("lead", "")):
			found = true
	_ok(c, found, "the slotted lead carries the tool's output text and its tool id as source")
	_ok(c, WS.current_lead == lead0, "the occult tool no longer hijacks WorldState.current_lead (legacy set_lead is not the driver)")

# --- (c) event effect -> live meter -------------------------------------------------------------
static func _c_event_effect_moves_live_meter(c: Dictionary) -> void:
	print("[M25 (c): an ambient EventManager pressure effect moves a live meter]")
	var root := _r()
	var M: Object = root.get_node("/root/Meters")
	var WS: Object = root.get_node("/root/WorldState")
	var EM: Object = root.get_node("/root/EventManager")

	M.reset()
	WS.set_pressure(&"attention", 0.0)
	var notice0: float = M.get_meter("notice")
	var att0: float = WS.attention
	EM._apply_effect({"type": "pressure", "target": "attention", "delta": 6.0})
	_ok(c, is_equal_approx(M.get_meter("notice") - notice0, 6.0),
		"an ambient attention event raises Notice (+6, got %.1f)" % (M.get_meter("notice") - notice0))
	_ok(c, is_equal_approx(WS.attention, att0),
		"the ambient event does NOT drive the dead legacy attention pressure")

	# A corruption event lands on Doom.
	var doom0: float = M.get_meter("doom")
	EM._apply_effect({"type": "pressure", "target": "corruption", "delta": 4.0})
	_ok(c, is_equal_approx(M.get_meter("doom") - doom0, 4.0),
		"an ambient corruption event raises Doom (+4, got %.1f)" % (M.get_meter("doom") - doom0))

# --- (d) clamps + per-run reset -----------------------------------------------------------------
static func _d_mappings_clamp_and_reset(c: Dictionary) -> void:
	print("[M25 (d): the legacy->meter mappings clamp 0..100 and scrub on a per-run reset]")
	var root := _r()
	var M: Object = root.get_node("/root/Meters")
	var WS: Object = root.get_node("/root/WorldState")
	var EM: Object = root.get_node("/root/EventManager")

	M.reset()
	# A huge corruption event cannot push Doom past the M4 clamp.
	EM._apply_effect({"type": "pressure", "target": "corruption", "delta": 999.0})
	_ok(c, M.get_meter("doom") <= 100.0, "a mapped effect clamps at Doom 100 (got %.1f)" % M.get_meter("doom"))
	# A negative relief cannot push a meter below 0.
	EM._apply_effect({"type": "pressure", "target": "panic", "delta": -999.0})
	_ok(c, M.get_meter("madness") >= 0.0, "a mapped relief clamps at Madness 0 (got %.1f)" % M.get_meter("madness"))

	# Per-run reset re-derives the meters from run-start pressures (Madness/Notice/Heat -> 0..seed).
	WS.set_pressure(&"corruption", 5.0)
	WS.set_pressure(&"cult_readiness", 0.0)
	WS.set_pressure(&"attention", 0.0)   # Notice is derived from attention at reset — pin it.
	M.set_meter("madness", 55.0)
	M.set_meter("notice", 44.0)
	M.reset()
	_ok(c, is_equal_approx(M.get_meter("madness"), 0.0) and is_equal_approx(M.get_meter("notice"), 0.0),
		"per-run reset scrubs Madness/Notice back to run-start 0")
	_ok(c, is_equal_approx(M.get_meter("doom"), 5.0),
		"per-run reset re-derives Doom from the run-start corruption seed (5, got %.1f)" % M.get_meter("doom"))

# --- (e) engine-neutral documented table --------------------------------------------------------
static func _e_mapping_is_a_documented_neutral_table(c: Dictionary) -> void:
	print("[M25 (e): the legacy->meter map is one documented table; an unmapped pressure is a no-op]")
	var root := _r()
	var M: Object = root.get_node("/root/Meters")
	# The map covers exactly the five §8.3 pressures, each onto one of the four live meters.
	var mp: Dictionary = M.LEGACY_METER_MAP
	for p in ["corruption", "panic", "fatigue", "cult_readiness", "attention"]:
		_ok(c, mp.has(p) and mp[p] in M.METERS, "LEGACY_METER_MAP maps '%s' onto a live meter" % p)
	# An unmapped legacy name is a safe no-op (no crash, no meter moved).
	M.reset()
	var doom0: float = M.get_meter("doom")
	M.adjust_legacy("no_such_pressure", 50.0, "probe")
	_ok(c, is_equal_approx(M.get_meter("doom"), doom0), "adjust_legacy on an unmapped pressure is a no-op")

# --- helpers ------------------------------------------------------------------------------------
static func _r() -> Node:
	return (Engine.get_main_loop() as SceneTree).root

static func _ok(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  ok  - %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		print("  FAIL - %s" % label)
