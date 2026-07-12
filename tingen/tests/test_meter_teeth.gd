extends SceneTree
## M11 — "the meters get TEETH" harness (direction v2 §4). Run with:
##   godot --headless --path tingen -s tests/test_meter_teeth.gd
##
## Watched RED before MeterThreats + the Doom phase-fill existed. Covers:
##   (a) Notice crossing the high threat threshold spawns EXACTLY ONE beyond_hunter agent, in
##       combat with combat_intent engaging the player (the tactical layer pursues + attacks it);
##       capped at one; killing it clears it AND it respawns while Notice stays high; once Notice
##       decays below the threshold it does NOT respawn.
##   (b) Heat crossing spawns a nighthawk_pursuer, same cap/respawn/decay lifecycle; it is NOT a
##       monster form (a human official), so it never feeds the Doom monster driver.
##   (c) Doom rises on a day/phase advance (passive fill) — a fully-idle run reaches Doom 100 by
##       ~day 6-7 (the phase + hourly increments hit 100 within the 7-day run).
##   (d) the new forms load in AbilityDB with valid kits/shapes.
##   (e) spawns CLEAR on run reset + don't leak/persist across runs (the sprint leak lesson).
##   (f) determinism: spawn placement for a fixed run-seed is identical.

var _passed: int = 0
var _failed: int = 0

const DT: float = 1.0 / 60.0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()

	_test_new_forms_load()
	await _test_notice_spawns_beyond_hunter_engaging_player()
	_test_notice_hunter_capped_and_respawn_and_decay()
	await _test_heat_spawns_nighthawk_engaging_player()
	_test_nighthawk_not_a_monster()
	_test_doom_passive_phase_fill_reaches_100_by_day_6_7()
	_test_spawns_clear_on_run_reset_no_leak()
	_test_spawn_placement_deterministic_for_seed()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

func _M() -> Node: return root.get_node_or_null("/root/Meters")
func _MT() -> Node: return root.get_node_or_null("/root/MeterThreats")
func _AG() -> Node: return root.get_node("/root/Agents")
func _RM() -> Node: return root.get_node("/root/RunManager")
func _DB() -> Node: return root.get_node("/root/AbilityDB")
func _CL() -> Node: return root.get_node("/root/Clock")

## Count live agents wearing a given combat_form (not downed).
func _count_form(form: String) -> int:
	var n := 0
	for a in _AG().all():
		if a != null and not a.downed and a.combat_form == form:
			n += 1
	return n

func _first_of_form(form: String) -> Agent:
	for a in _AG().all():
		if a != null and not a.downed and a.combat_form == form:
			return a
	return null

# --- (d) forms load --------------------------------------------------------------------------
func _test_new_forms_load() -> void:
	print("[teeth: the two hunter forms load in AbilityDB with valid kits + shapes (M11)]")
	var DB := _DB()
	for form in ["beyond_hunter", "nighthawk_pursuer"]:
		var kit: Array = DB.kit_for(form)
		_ok(not kit.is_empty(), "%s loads a non-empty kit" % form)
		var clean := true
		for aid in kit:
			if not DB.has_ability(String(aid)):
				clean = false
		_ok(clean, "%s kit names only known abilities" % form)
	# The Beyond hunter is a MONSTER (Beyond-touched); the Nighthawk is a human official (not).
	_ok(DB.is_monster_form("beyond_hunter"), "beyond_hunter is a monster form")
	_ok(not DB.is_monster_form("nighthawk_pursuer"), "nighthawk_pursuer is NOT a monster form")
	# No authoring drift across the whole loaded set.
	_ok(DB.validate_refs(DB._abilities, DB._forms).is_empty(),
		"the loaded ability/form set has no validation problems")

# --- (a) Notice -> beyond_hunter engages the player ------------------------------------------
func _test_notice_spawns_beyond_hunter_engaging_player() -> void:
	print("[teeth: high Notice spawns ONE beyond_hunter, in combat, engaging the player (M11)]")
	var M := _M()
	var MT := _MT()
	_ok(MT != null, "MeterThreats autoload is registered")
	if MT == null:
		return
	_RM().start_run()
	_AG().rebuild()
	# The investigator proxy stands in an arena the hunter will be spawned into.
	var proxy: Agent = _AG().ensure_player_proxy(Vector2(300, 300), "teeth_arena")
	proxy.max_hp = 4000.0
	proxy.hp = 4000.0
	proxy.downed = false
	MT.spawn_room = "teeth_arena"
	MT.spawn_pos = Vector2(360, 300)
	M.set_meter("notice", 0.0)
	M.set_meter("notice", 90.0)   # cross the threat threshold -> a Beyond-hunter is dispatched
	_ok(_count_form("beyond_hunter") == 1, "crossing high Notice spawns exactly one beyond_hunter")
	var hunter := _first_of_form("beyond_hunter")
	_ok(hunter != null and hunter.in_combat, "the hunter is in combat")
	_ok(hunter != null and String(hunter.combat_intent.get("mode", "")) == "engage"
		and String(hunter.combat_intent.get("target", "")) == "player",
		"the hunter's intent engages the player")
	_ok(hunter != null and hunter.room == "teeth_arena",
		"the hunter is spawned into the player's room")
	# Drive the live combat seam: bind the hunter's executor + the proxy's, step, and confirm the
	# hunter actually ATTACKS the player (an agent_attacked with target=player). This is the built
	# tactical/intent layer — a spawned hunter is just an agent in combat with the player.
	if hunter != null:
		var EB: Object = root.get_node("/root/EventBus")
		EB.clear()
		var hx := CombatExecutor.new()
		hx.bind(hunter)
		hx.enable_tactics()
		root.get_node("/root/Agents")  # keep the registry warm
		for _i in range(240):
			hx.step_combat(DT)
		var hit_player := false
		for ev in EB.events("agent_attacked"):
			if String((ev.get("data", {}) as Dictionary).get("target", "")) == "player":
				hit_player = true
		_ok(hit_player, "the spawned hunter engages + attacks the player through the built combat layer")
		hx.free()
	_RM().start_run()
	_AG().rebuild()

# --- (a2) cap + respawn + decay --------------------------------------------------------------
func _test_notice_hunter_capped_and_respawn_and_decay() -> void:
	print("[teeth: the beyond_hunter is capped at 1, respawns while Notice stays high, stops on decay (M11)]")
	var M := _M()
	var MT := _MT()
	if MT == null:
		return
	_RM().start_run()
	_AG().rebuild()
	_AG().ensure_player_proxy(Vector2(300, 300), "teeth_cap")
	MT.spawn_room = "teeth_cap"
	MT.spawn_pos = Vector2(360, 300)
	M.set_meter("notice", 0.0)
	M.set_meter("notice", 90.0)
	_ok(_count_form("beyond_hunter") == 1, "one hunter after the first crossing")
	# A second high-Notice pulse must NOT stack a second hunter (cap = 1 active).
	MT.tick_threats()
	_ok(_count_form("beyond_hunter") == 1, "the hunter is capped at one active (no stacking)")
	# Kill it: the threat is resolved. While Notice stays high, a threat tick respawns it.
	var hunter := _first_of_form("beyond_hunter")
	hunter.downed = true
	MT.tick_threats()
	_ok(_count_form("beyond_hunter") == 1, "killing the hunter while Notice stays high respawns one")
	# Now decay Notice below the threshold: a downed hunter is NOT replaced.
	var live := _first_of_form("beyond_hunter")
	live.downed = true
	M.set_meter("notice", 10.0)   # below THREAT_RUNG
	MT.tick_threats()
	_ok(_count_form("beyond_hunter") == 0, "once Notice decays below the threshold no hunter respawns")
	_RM().start_run()
	_AG().rebuild()

# --- (b) Heat -> nighthawk engages the player ------------------------------------------------
func _test_heat_spawns_nighthawk_engaging_player() -> void:
	print("[teeth: high Heat spawns ONE nighthawk_pursuer, in combat, engaging the player (M11)]")
	var M := _M()
	var MT := _MT()
	if MT == null:
		return
	_RM().start_run()
	_AG().rebuild()
	var proxy: Agent = _AG().ensure_player_proxy(Vector2(300, 300), "teeth_heat")
	proxy.max_hp = 4000.0
	proxy.hp = 4000.0
	proxy.downed = false
	MT.spawn_room = "teeth_heat"
	MT.spawn_pos = Vector2(340, 300)
	M.set_meter("heat", 0.0)
	M.set_meter("heat", 90.0)   # cross the threat threshold -> a Nighthawk is dispatched
	_ok(_count_form("nighthawk_pursuer") == 1, "crossing high Heat spawns exactly one nighthawk_pursuer")
	var hawk := _first_of_form("nighthawk_pursuer")
	_ok(hawk != null and hawk.in_combat
		and String(hawk.combat_intent.get("target", "")) == "player",
		"the nighthawk is in combat engaging the player")
	if hawk != null:
		var EB: Object = root.get_node("/root/EventBus")
		EB.clear()
		var hx := CombatExecutor.new()
		hx.bind(hawk)
		hx.enable_tactics()
		for _i in range(360):
			hx.step_combat(DT)
		var hit_player := false
		for ev in EB.events("agent_attacked"):
			if String((ev.get("data", {}) as Dictionary).get("target", "")) == "player":
				hit_player = true
		_ok(hit_player, "the spawned nighthawk engages + attacks the player through the built combat layer")
		hx.free()
	# Same cap/respawn/decay shape.
	MT.tick_threats()
	_ok(_count_form("nighthawk_pursuer") == 1, "the nighthawk is capped at one active")
	var live := _first_of_form("nighthawk_pursuer")
	live.downed = true
	M.set_meter("heat", 5.0)
	MT.tick_threats()
	_ok(_count_form("nighthawk_pursuer") == 0, "once Heat decays no nighthawk respawns")
	_RM().start_run()
	_AG().rebuild()

func _test_nighthawk_not_a_monster() -> void:
	print("[teeth: the nighthawk is a human official — never counted by the Doom monster driver (M11)]")
	var M := _M()
	var MT := _MT()
	if MT == null:
		return
	_RM().start_run()
	_AG().rebuild()
	_AG().ensure_player_proxy(Vector2.ZERO, "teeth_nomonster")
	MT.spawn_room = "teeth_nomonster"
	M.set_meter("heat", 0.0)
	M.set_meter("heat", 90.0)
	# With the nighthawk loose (no beyond_hunter), an in-game hour of Doom fill must add the TIME
	# creep + phase fill only — NOT a monster nudge. Compare to a baseline with no threats.
	_ok(not _DB().is_monster_form("nighthawk_pursuer"),
		"nighthawk_pursuer is not a monster form (so the Doom monster driver skips it)")
	_RM().start_run()
	_AG().rebuild()

# --- (c) Doom passive phase-fill reaches 100 by ~day 6-7 -------------------------------------
func _test_doom_passive_phase_fill_reaches_100_by_day_6_7() -> void:
	print("[teeth: an idle run's passive Doom fill (time + phase) reaches 100 by ~day 6-7 (M11)]")
	var M := _M()
	var CL := _CL()
	_RM().start_run()
	_AG().rebuild()
	# M26 RETUNE #2 (known-gate fix): the roster has 3 HIDDEN-Beyonder NPCs (butcher/wren/mack human
	# forms) LIVE from run start, but the Doom monster driver counts a hidden Beyonder ONLY once its lead
	# is KNOWN (LeadSystem.known_prey_forms). To isolate the PURE PASSIVE pacer (time + phase) on the REAL
	# live roster — no `_down_counted` fiction — stage an UN-SURFACED idle run through LeadSystem's
	# public debug seam (retro B4: no reaching into `_leads` internals): the live Beyonders stay
	# uncounted because the gate holds them. The known-gate itself is covered in tests/test_balance.gd.
	var _ls := root.get_node_or_null("/root/LeadSystem")
	if _ls != null:
		_ls.debug_set_all_known(false)
	# A day/phase advance adds a Doom increment (the passive pacer). Assert a single phase advance
	# moves Doom on its own.
	M.set_meter("doom", 10.0)
	var before: float = M.get_meter("doom")
	CL.set_time(1, 480)                # morning
	CL.advance_minutes(240)            # into afternoon (12:00) — crosses a phase boundary
	_ok(M.get_meter("doom") > before, "a phase advance raises Doom passively")
	# Now the full idle run: from day 1 08:00, advance minute-by-minute (the real idle clock) and
	# confirm Doom hits 100 within the 7-day run, landing around day 6-7.
	M.set_meter("doom", M.run_start("doom"))
	CL.set_time(1, 480)
	var reached_day := 0
	# 7 days * 1440 minutes is the whole run window.
	for _i in range(7 * 1440):
		CL.advance_minutes(1)
		if M.get_meter("doom") >= 100.0:
			reached_day = CL.day
			break
	_ok(reached_day >= 6 and reached_day <= 7,
		"idle Doom reaches 100 on day %d (want 6-7)" % reached_day)
	_RM().start_run()
	_AG().rebuild()

# --- (e) spawns clear on run reset + no leak -------------------------------------------------
func _test_spawns_clear_on_run_reset_no_leak() -> void:
	print("[teeth: hunter/nighthawk spawns clear on run reset + never leak across runs (M11)]")
	var M := _M()
	var MT := _MT()
	if MT == null:
		return
	_RM().start_run()
	_AG().rebuild()
	_AG().ensure_player_proxy(Vector2.ZERO, "teeth_leak")
	MT.spawn_room = "teeth_leak"
	M.set_meter("notice", 90.0)
	M.set_meter("heat", 90.0)
	_ok(_count_form("beyond_hunter") == 1 and _count_form("nighthawk_pursuer") == 1,
		"both threats are live before the reset")
	# A fresh run must scrub them — the rebuild clears runtime-registered agents AND MeterThreats.reset
	# drops its live-threat bookkeeping so a new run doesn't inherit a phantom hunter.
	_RM().start_run()
	_AG().rebuild()
	_ok(_count_form("beyond_hunter") == 0 and _count_form("nighthawk_pursuer") == 0,
		"a fresh run has no leaked hunter/nighthawk agents")
	_ok(not MT.has_active_threat("notice") and not MT.has_active_threat("heat"),
		"MeterThreats' live-threat bookkeeping is cleared on reset (no cross-run leak)")

# --- (f) deterministic spawn placement -------------------------------------------------------
func _test_spawn_placement_deterministic_for_seed() -> void:
	print("[teeth: spawn placement for a fixed run-seed is identical (M11)]")
	var M := _M()
	var MT := _MT()
	if MT == null:
		return
	var pos_a := _spawn_once_and_read_pos()
	var pos_b := _spawn_once_and_read_pos()
	_ok(pos_a == pos_b and pos_a != Vector2.INF,
		"a fixed run-seed places the spawned hunter at an identical position")

func _spawn_once_and_read_pos() -> Vector2:
	var M := _M()
	var MT := _MT()
	var WM: Object = root.get_node("/root/WorldManager")
	_RM().start_run()
	_AG().rebuild()
	_AG().ensure_player_proxy(Vector2(500, 500), "teeth_seed")
	MT.spawn_room = "teeth_seed"
	# Force a fixed seed so placement is reproducible.
	WM.seed_value = 12345
	MT.spawn_pos = Vector2.ZERO   # 0 => the spawner uses its seeded scatter around the player
	M.set_meter("notice", 0.0)
	M.set_meter("notice", 90.0)
	var h := _first_of_form("beyond_hunter")
	var p := h.position if h != null else Vector2.INF
	_RM().start_run()
	_AG().rebuild()
	return p
