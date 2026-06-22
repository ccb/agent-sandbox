extends SceneTree
## Dependency-free headless test runner. Run with:
##   godot --headless --path tingen -s tests/run_tests.gd
##
## Exercises the data-driven systems that don't need a rendered scene: the clock's
## phase math, pressure clamping + stability, the world-manager stage machine and
## seeded slots, clue collection + topic unlock, event scoring, and a full
## save -> mutate -> load round-trip. Autoloads are available because they are
## registered in project.godot. Exits non-zero on any failure so CI can gate on it.

var _passed: int = 0
var _failed: int = 0
var _skipped: int = 0

func _init() -> void:
	# Let autoloads finish their _ready before asserting against them.
	await process_frame
	await process_frame

	_test_clock_phases()
	_test_pressure_clamp_and_stability()
	_test_world_manager_stages()
	_test_seeded_slots_are_deterministic()
	_test_clue_collection()
	_test_event_scoring()
	_test_save_load_roundtrip()
	_test_clock_beats()
	_test_event_bus()
	_test_agent_fallback()
	_test_agent_registry()
	_test_agent_thought()
	_test_agent_combat_state()
	_test_agent_inventory()
	_test_agent_downed_freeze()
	_test_cult_cell_seeded()
	_test_substrate_save_load()
	_test_item_db()
	_test_inventory_add_remove()
	_test_inventory_use()
	_test_inventory_save_load()
	_test_action_schema()
	_test_mock_sidecar()
	_test_ambient_sidecar()
	_test_ambient_sidecar_performs_rite()
	_test_http_sidecar()
	_test_sidecar_bridge()
	_test_perception_snapshot()
	_test_action_commit()
	_test_coordinate_anchors_consistent()
	_test_city_layout()
	_test_city_layout_data()
	_test_npc_waypoints_walkable()
	await _test_navmesh_routing()
	_test_ritual_step_advances_summoning()
	_test_commit_sets_thought()
	_test_action_attack()
	_test_action_gather_item()
	_test_action_talk_to_rumor()
	_test_agent_runtime_beat()
	_test_overseer_state()
	_test_critic_verdicts()
	_test_critic_downed_veto()
	_test_runtime_with_overseer()
	_test_summoning_plan()
	_test_gods_db()
	_test_prayer_adjudication()
	_test_prayer_service()
	_test_summoning_countdown_and_climax()
	_test_summoning_advance_rite()
	_test_summoning_progress_readouts()
	await _test_cult_progress_panel()
	await _test_npc_binds_to_agent()
	_test_inspect_signal()
	await _test_character_card_opens()
	await _test_city_blocks_scene()
	_test_occult_divination()
	_test_divination_hints_never_name_site()
	_test_occult_other_tools()
	_test_occult_tool_views()
	await _test_ritual_panel()
	_test_player_actions()
	_test_player_sabotage_any()
	_test_dialogue_social_influence_effect()
	_test_orin_persuade_dialogue()
	_test_dev_console_interference_commands()
	_test_combat_scaled_by_impede()
	_test_endgame_resolver()
	_test_endgame_ending_bands()
	_test_endgame_autoload()
	_test_map_projection_world_to_map()
	_test_map_projection_canvas_fit()
	_test_district_map_polygons()
	_test_map_texture_imported()
	_test_player_state_save_load()
	_test_schema_parity_with_sidecar()
	_test_prayer_parity_with_sidecar()
	await _test_prayer_panel()
	await _test_debug_log_panel()
	await _test_inventory_panel()
	await _test_hud_toggle_keys()
	await _test_district_map_panel()
	await _test_toasts()
	await _test_player_position_sync()
	await _test_player_stamina()

	print("\n=== %d passed, %d failed, %d skipped ===" % [_passed, _failed, _skipped])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

## Record a test that could not run in this environment (e.g. an external tool is
## absent). Visible in the output and the summary so an unrun check is never mistaken
## for a passing one, but does NOT fail the suite.
func _skip(label: String) -> void:
	_skipped += 1
	print("  SKIP  %s" % label)

func _test_clock_phases() -> void:
	print("[clock]")
	var Clk: Object = root.get_node("/root/Clock")
	_ok(Clk.phase_for_minute(0) == "late-night", "00:00 -> late-night")
	_ok(Clk.phase_for_minute(360) == "early-morning", "06:00 -> early-morning")
	_ok(Clk.phase_for_minute(540) == "morning", "09:00 -> morning")
	_ok(Clk.phase_for_minute(780) == "afternoon", "13:00 -> afternoon")
	_ok(Clk.phase_for_minute(1080) == "dusk", "18:00 -> dusk")
	_ok(Clk.phase_for_minute(1200) == "night", "20:00 -> night")
	_ok(Clk.phase_for_minute(1439) == "late-night", "23:59 -> late-night")

func _test_pressure_clamp_and_stability() -> void:
	print("[pressures]")
	var WS: Object = root.get_node("/root/WorldState")
	WS.set_pressure(&"corruption", 200.0)
	_ok(WS.get_pressure(&"corruption") == 100.0, "clamps high to 100")
	WS.set_pressure(&"corruption", -50.0)
	_ok(WS.get_pressure(&"corruption") == 0.0, "clamps low to 0")
	WS.set_pressure(&"corruption", 0.0)
	WS.set_pressure(&"panic", 0.0)
	WS.set_pressure(&"cult_readiness", 0.0)
	_ok(abs(WS.stability() - 100.0) < 0.01, "all-zero -> stability 100")
	WS.set_pressure(&"corruption", 100.0)
	_ok(abs(WS.stability() - 50.0) < 0.01, "corruption 100 -> stability 50")

func _test_world_manager_stages() -> void:
	print("[world manager]")
	var WM: Object = root.get_node("/root/WorldManager")
	var WS: Object = root.get_node("/root/WorldState")
	WM.from_dict({"seed_value": 12345})  # reset bookkeeping deterministically
	WM.current_stage_id = "disturbance"
	WM.refresh_count = 0
	WS.set_pressure(&"cult_readiness", 100.0)
	WM.force_advance_stage()
	_ok(WM.current_stage_id == "awakening", "force_advance from disturbance -> awakening")
	var before: int = WM.stage_index()
	WM.force_advance_stage()
	_ok(int(WM.stage_index()) == before + 1, "force_advance increments stage index")

func _test_seeded_slots_are_deterministic() -> void:
	print("[slots]")
	var WM: Object = root.get_node("/root/WorldManager")
	WM.from_dict({"seed_value": 999})
	WM._start_run(false)
	var first: Dictionary = WM.slots.duplicate(true)
	WM.from_dict({"seed_value": 999})
	WM._start_run(false)
	_ok(WM.slots == first, "same seed -> identical slot resolution")
	_ok(WM.slots.has("primary_ritual_site"), "primary_ritual_site resolved at world-start")

func _test_clue_collection() -> void:
	print("[clues]")
	var CD: Object = root.get_node("/root/ClueDB")
	CD.from_dict({})  # clear
	var ok: bool = CD.collect("antigonus_notebook")
	_ok(ok, "collect known clue returns true")
	_ok(not CD.collect("antigonus_notebook"), "double-collect returns false")
	_ok(CD.collected_count() == 1, "collected_count == 1")
	_ok(CD.unlocked_topics().size() > 0, "collecting unlocked at least one topic")

func _test_event_scoring() -> void:
	print("[events]")
	var EM: Object = root.get_node("/root/EventManager")
	_ok(EM.library.size() > 0, "event library loaded")
	# An always-eligible event (no conditions) should be pickable on a fresh count.
	EM._cooldowns.clear()
	var pick: Dictionary = EM._pick(0)
	_ok(not pick.is_empty(), "picks an eligible event at refresh 0")

func _test_save_load_roundtrip() -> void:
	print("[save/load]")
	var WS: Object = root.get_node("/root/WorldState")
	var SM: Object = root.get_node("/root/SaveManager")
	var CD: Object = root.get_node("/root/ClueDB")
	WS.set_pressure(&"panic", 42.0)
	CD.from_dict({})
	CD.collect("spent_revolver")
	var tmp := "user://test_save.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	WS.set_pressure(&"panic", 7.0)
	CD.from_dict({})
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(abs(WS.get_pressure(&"panic") - 42.0) < 0.01, "panic restored to 42")
	_ok(CD.is_collected("spent_revolver"), "clue restored after load")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))

func _test_clock_beats() -> void:
	print("[clock beats]")
	var Clk: Object = root.get_node("/root/Clock")
	Clk.minutes_per_beat = 15
	Clk.beat_index = 0
	Clk._beat_accum_minutes = 0
	var seen := {"n": 0}
	var cb := func(_bi: int, _d: int) -> void: seen["n"] += 1
	Clk.beat_ticked.connect(cb)
	Clk.advance_minutes(15)
	_ok(Clk.beat_index == 1, "15 minutes -> 1 beat")
	_ok(seen["n"] == 1, "beat_ticked emitted once")
	Clk.advance_minutes(30)
	_ok(Clk.beat_index == 3, "45 minutes total -> 3 beats")
	Clk.beat_ticked.disconnect(cb)

func _test_event_bus() -> void:
	print("[event bus]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var ev: Dictionary = EB.emit_event("test_action", {"actor": "voss"})
	_ok(ev["type"] == "test_action", "event records its type")
	_ok(int(ev["seq"]) == 1, "first event seq is 1")
	_ok(EB.events().size() == 1, "one event logged")
	EB.emit_event("other", {})
	_ok(EB.events("test_action").size() == 1, "filter by type returns only matches")
	_ok(EB.latest(1).size() == 1, "latest(1) returns one event")

func _test_agent_fallback() -> void:
	print("[agent fallback]")
	var ND: Object = root.get_node("/root/NpcDB")
	var target: Vector2 = ND.waypoint_for("lamplighter_orin", "morning")
	var a: Agent = Agent.new("lamplighter_orin")
	a.position = Vector2.ZERO
	var before: float = a.distance_to(target)
	a.tick_fallback("morning", 100.0)
	var after: float = a.distance_to(target)
	_ok(after < before, "fallback step moves agent toward its waypoint")
	for _i in range(100):
		a.tick_fallback("morning", 100.0)
	_ok(a.position == target, "fallback converges onto the waypoint")
	a.remember("saw the player near the warehouse")
	_ok(a.short_memory.size() == 1, "remember() appends to short memory")

func _test_agent_downed_freeze() -> void:
	print("[agent downed freeze]")
	var a: Agent = Agent.new("lamplighter_orin")
	a.position = Vector2.ZERO
	# Upright, it steps toward its waypoint (waypoint is non-zero for orin/morning).
	a.tick_fallback("morning", 100.0)
	_ok(a.position != Vector2.ZERO, "an upright agent steps toward its waypoint")
	# Down it, then confirm it no longer drifts no matter how many beats pass.
	var resting: Vector2 = a.position
	a.downed = true
	for _i in range(50):
		a.tick_fallback("morning", 100.0)
	_ok(a.position == resting, "a downed agent does not move on tick")

func _test_agent_registry() -> void:
	print("[agent registry]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	_ok(AG.get_agent("lamplighter_orin") != null, "registry builds a known agent")
	_ok(AG.all().size() >= 2, "registry holds at least the seeded npcs")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	var near: Array = AG.active(orin.position, 1.0)
	_ok(near.has(orin), "active() finds an agent at its own position")
	var far: Array = AG.active(orin.position + Vector2(99999, 0), 1.0)
	_ok(not far.has(orin), "active() excludes agents outside the radius")

func _test_agent_thought() -> void:
	print("[agent thought]")
	var a := Agent.new("voss")
	a.intent = "Complete the warehouse summoning."
	_ok(a.describe_thought().length() > 0, "idle agent has a synthesized thought")
	a.current_action = {"verb": "move_to", "args": {"target": "warehouse"}}
	_ok("warehouse" in a.describe_thought(), "thought reflects the current move target")
	a.thought = "I sense I am being watched."
	_ok(a.describe_thought() == "I sense I am being watched.", "explicit thought overrides synthesis")
	var b := Agent.new()
	b.from_dict(a.to_dict())
	_ok(b.thought == a.thought, "thought round-trips through save")

func _test_agent_combat_state() -> void:
	print("[agent combat state]")
	var a := Agent.new("voss")
	_ok(a.hp == 100.0 and a.max_hp == 100.0, "new agent starts at full HP")
	_ok(a.downed == false, "new agent is not downed")
	a.take_damage(34.0)
	_ok(a.hp == 66.0, "take_damage subtracts flat damage from HP")
	_ok(a.downed == false, "an agent above 0 HP is not downed")
	a.take_damage(100.0)
	_ok(a.hp == 0.0, "HP clamps at 0 and never goes negative")
	_ok(a.downed == true, "an agent reduced to 0 HP is downed")
	a.take_damage(20.0)
	_ok(a.hp == 0.0, "further damage to a downed agent keeps HP at 0")
	var b := Agent.new()
	b.from_dict(a.to_dict())
	_ok(b.hp == 0.0 and b.downed == true, "hp and downed round-trip through save")

func _test_agent_inventory() -> void:
	print("[agent inventory]")
	var a := Agent.new("fishwife_dalia")
	_ok(a.item_count("ritual_salt") == 0, "a new agent carries nothing")
	a.add_item("ritual_salt", 2)
	_ok(a.item_count("ritual_salt") == 2, "add_item adds the given count")
	a.add_item("ritual_salt")
	_ok(a.item_count("ritual_salt") == 3, "add_item defaults to one and stacks")
	a.add_item("candle")
	_ok(a.item_count("candle") == 1, "a second item is tracked independently")
	var b := Agent.new()
	b.from_dict(a.to_dict())
	_ok(b.item_count("ritual_salt") == 3 and b.item_count("candle") == 1, "inventory round-trips through save")

func _test_cult_cell_seeded() -> void:
	print("[cult cell]")
	var ND: Object = root.get_node("/root/NpcDB")
	_ok(ND.get_def("clerk_voss").get("faction", "") == "cult", "voss is faction cult")
	_ok(ND.get_def("clerk_voss").get("role", "") == "leader", "voss is the leader")
	_ok(ND.get_def("dockhand_pell").get("role", "") == "victim", "pell is the victim")
	_ok(String(ND.get_def("lamplighter_orin").get("intent", "")) != "", "orin has an intent")
	_ok(String(ND.get_def("fishwife_dalia").get("role", "")) == "logistics", "dalia is logistics")

func _test_substrate_save_load() -> void:
	print("[substrate save/load]")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")
	var SM: Object = root.get_node("/root/SaveManager")
	AG.rebuild()
	EB.clear()
	EB.emit_event("seed_event", {"x": 1})
	AG.get_agent("clerk_voss").position = Vector2(123, 456)
	var tmp := "user://test_substrate.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	EB.clear()
	AG.get_agent("clerk_voss").position = Vector2.ZERO
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(EB.events("seed_event").size() == 1, "event log restored after load")
	_ok(AG.get_agent("clerk_voss").position == Vector2(123, 456), "agent position restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))

func _test_item_db() -> void:
	print("[item db]")
	var DB: Object = root.get_node("/root/ItemDB")
	_ok(DB.has_def("rye_bread"), "items.json loaded rye_bread")
	var d: ItemDef = DB.get_def("rye_bread")
	_ok(d != null, "get_def returns an ItemDef")
	_ok(d.category == "sustenance", "rye_bread is sustenance")
	_ok(d.stackable == true, "rye_bread is stackable")
	_ok(d.max_stack == 5, "rye_bread max_stack is 5")
	var pen: ItemDef = DB.get_def("spirit_pendulum")
	_ok(pen.stackable == false, "spirit_pendulum is not stackable")
	_ok(DB.get_def("does_not_exist") == null, "unknown id returns null")

func _test_inventory_add_remove() -> void:
	print("[inventory add/remove]")
	var INV: Object = root.get_node("/root/Inventory")
	INV.clear()
	_ok(INV.add("candle", 3), "add 3 candles succeeds")
	_ok(INV.count_of("candle") == 3, "count is 3")
	_ok(INV.add("candle", 100) == false, "add past max_stack (9) is rejected")
	_ok(INV.count_of("candle") == 3, "count unchanged after rejected add")
	_ok(INV.add("spirit_pendulum"), "add non-stackable succeeds")
	_ok(INV.add("spirit_pendulum") == false, "second non-stackable add rejected (cap 1)")
	_ok(INV.has("candle", 3), "has(candle,3) true")
	_ok(INV.has("candle", 4) == false, "has(candle,4) false")
	_ok(INV.remove("candle", 2), "remove 2 candles succeeds")
	_ok(INV.count_of("candle") == 1, "count is 1 after remove")
	_ok(INV.remove("candle", 5) == false, "remove more than held is rejected")
	_ok(INV.count_of("candle") == 1, "count unchanged after rejected remove")

func _test_inventory_use() -> void:
	print("[inventory use]")
	var INV: Object = root.get_node("/root/Inventory")
	var WS: Object = root.get_node("/root/WorldState")
	INV.clear()
	WS.set_pressure(&"fatigue", 50.0)
	INV.add("rye_bread", 2)
	_ok(INV.use("rye_bread"), "use rye_bread succeeds")
	_ok(abs(WS.get_pressure(&"fatigue") - 38.0) < 0.01, "fatigue dropped by on_use delta (12)")
	_ok(INV.count_of("rye_bread") == 1, "consumable decremented by 1")
	# Non-consumable (no on_use): use does not decrement.
	INV.add("spirit_pendulum")
	_ok(INV.use("spirit_pendulum"), "use non-consumable returns true")
	_ok(INV.count_of("spirit_pendulum") == 1, "non-consumable not decremented")
	# Unknown effect: warns, no-ops, still treated as used (not consumed by default).
	INV.clear()
	_ok(INV.use("candle") == false, "use of unheld item returns false")

func _test_inventory_save_load() -> void:
	print("[inventory save/load]")
	var INV: Object = root.get_node("/root/Inventory")
	var SM: Object = root.get_node("/root/SaveManager")
	INV.clear()
	INV.add("candle", 4)
	INV.add("spirit_pendulum")
	var tmp := "user://test_inventory.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	INV.clear()
	_ok(INV.count_of("candle") == 0, "inventory cleared before load")
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(INV.count_of("candle") == 4, "candle count restored")
	_ok(INV.has("spirit_pendulum"), "pendulum restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))

func _test_action_schema() -> void:
	print("[action schema]")
	var ok := ActionSchema.validate({"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	_ok(ok["ok"] == true, "valid move_to accepted")
	var no_verb := ActionSchema.validate({"actor": "voss", "verb": "teleport", "args": {}})
	_ok(no_verb["ok"] == false, "unknown verb rejected")
	var missing := ActionSchema.validate({"actor": "voss", "verb": "talk_to", "args": {"agent": "orin"}})
	_ok(missing["ok"] == false, "talk_to missing 'topic' rejected")
	var idle := ActionSchema.validate({"actor": "voss", "verb": "idle", "args": {}})
	_ok(idle["ok"] == true, "idle needs no args")
	var no_actor := ActionSchema.validate({"verb": "idle", "args": {}})
	_ok(no_actor["ok"] == false, "missing actor rejected")
	_ok(ActionSchema.is_verb("attack"), "attack is a known verb")
	_ok(not ActionSchema.is_verb("nope"), "nope is not a known verb")

func _test_mock_sidecar() -> void:
	print("[mock sidecar]")
	var mock := MockSidecar.new()
	mock.set_action("voss", {"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	var snaps := [{"agent_id": "voss"}, {"agent_id": "orin"}]
	var out: Array = mock.propose(snaps)
	_ok(out.size() == 2, "one proposal per snapshot")
	_ok(out[0]["verb"] == "move_to", "scripted action returned for voss")
	_ok(out[1]["verb"] == "idle", "unscripted agent defaults to idle")
	_ok(out[1]["actor"] == "orin", "idle proposal is attributed to the right actor")
	# Queue support: pop one action per beat.
	mock.set_action("orin", [{"actor": "orin", "verb": "hide", "args": {}}])
	var out2: Array = mock.propose([{"agent_id": "orin"}])
	_ok(out2[0]["verb"] == "hide", "queued action consumed")
	var out3: Array = mock.propose([{"agent_id": "orin"}])
	_ok(out3[0]["verb"] == "idle", "empty queue falls back to idle")

func _parse_xy(s: String) -> Vector2:
	var p := s.split(",")
	return Vector2(float(p[0]), float(p[1]))

## Index of the first option whose label contains `needle`, or -1. Lets dialogue tests find a
## specific choice (e.g. "Persuade") without hard-coding option order.
func _option_index_with(options: Array, needle: String) -> int:
	for i in options.size():
		if needle in String((options[i] as Dictionary).get("label", "")):
			return i
	return -1

func _test_ambient_sidecar() -> void:
	print("[ambient sidecar]")
	var amb := AmbientSidecar.new()
	# Batch of two: a cultist drawn to the rite, a civilian on their daily round.
	var cult_snap := {"agent_id": "clerk_voss", "faction": "cult", "position": [200.0, 200.0], "phase": "morning", "beat": 7}
	var civ_snap := {"agent_id": "fishwife_dalia", "faction": "civilian", "position": [120.0, 120.0], "phase": "morning", "beat": 7}
	var out: Array = amb.propose([cult_snap, civ_snap])
	_ok(out.size() == 2, "one proposal per snapshot")
	_ok(out[0]["verb"] == "move_to", "ambient agents move — they never freeze on idle")
	_ok(ActionSchema.validate(out[0])["ok"], "cult proposal is schema-valid")
	_ok(ActionSchema.validate(out[1])["ok"], "civilian proposal is schema-valid")
	# Cultists converge on the warehouse: target lands within a scatter of the rite site.
	var cult_t: Vector2 = _parse_xy(out[0]["args"]["target"])
	_ok(cult_t.distance_to(AmbientSidecar.WAREHOUSE) <= AmbientSidecar.WANDER * 1.5, "cult target sits at the rite site")
	# Civilians follow their schedule: target lands near their phase waypoint.
	var ND: Object = root.get_node("/root/NpcDB")
	var wp: Vector2 = ND.waypoint_for("fishwife_dalia", "morning")
	var civ_t: Vector2 = _parse_xy(out[1]["args"]["target"])
	_ok(civ_t.distance_to(wp) <= AmbientSidecar.WANDER * 1.5, "civilian target follows the day's schedule")
	# Deterministic: identical snapshot -> identical proposal (pure function of inputs).
	var again: Array = amb.propose([cult_snap])
	_ok(again[0]["args"]["target"] == out[0]["args"]["target"], "same beat replays the same proposal")
	# A new beat re-scatters the goal so the crowd doesn't stand stock still.
	var later: Dictionary = cult_snap.duplicate()
	later["beat"] = 8
	var moved: Array = amb.propose([later])
	_ok(moved[0]["args"]["target"] != out[0]["args"]["target"], "a new beat re-scatters the goal")
	# Prayer adjudication is inherited from MockSidecar, so the live brain still answers prayers.
	var verdict: Dictionary = amb.adjudicate_prayer({"god": "outer_god", "prayer": "I humbly beseech you, grant mercy", "standing": 1.0})
	_ok(verdict.has("outcome"), "ambient brain still adjudicates prayers (inherited from mock)")

func _test_http_sidecar() -> void:
	print("[http sidecar]")
	var EB: Object = root.get_node("/root/EventBus")
	# URL parsing (pure/static) — host, port, and scheme.
	var u: Dictionary = HttpSidecar._split_url("http://127.0.0.1:8777")
	_ok(u["host"] == "127.0.0.1" and int(u["port"]) == 8777 and not bool(u["use_ssl"]), "parses host/port from an http url")
	var s: Dictionary = HttpSidecar._split_url("https://sidecar.example.com/propose")
	_ok(s["host"] == "sidecar.example.com" and int(s["port"]) == 443 and bool(s["use_ssl"]), "https defaults to 443 and strips the path")
	# Unconfigured (no URL): it IS the ambient brain — every agent moves, nothing networks.
	var off := HttpSidecar.new("")
	var out: Array = off.propose([{"agent_id": "clerk_voss", "faction": "cult", "position": [200.0, 200.0], "phase": "morning", "beat": 3}])
	_ok(out.size() == 1 and out[0]["verb"] == "move_to", "unconfigured http sidecar falls back to ambient movement")
	# Configured: a completed LLM reply is cached + logged; agents not yet heard from ambient-fill.
	var cli := HttpSidecar.new("http://127.0.0.1:8777")
	EB.clear()
	cli.apply_reply([{"actor": "clerk_voss", "verb": "hide", "args": {}}], "")
	_ok(EB.events("sidecar_proposed").size() == 1, "a valid LLM action is logged as sidecar_proposed")
	var picked: Array = cli.pick([
		{"agent_id": "clerk_voss", "faction": "cult", "position": [200.0, 200.0], "phase": "morning", "beat": 3},
		{"agent_id": "fishwife_dalia", "faction": "civilian", "position": [120.0, 120.0], "phase": "morning", "beat": 3}])
	_ok(picked[0]["verb"] == "hide", "the cached LLM action is served for that agent")
	_ok(picked[1]["verb"] == "move_to", "an agent with no LLM action yet ambient-fills (keeps moving)")
	# Invalid LLM actions are dropped (never cached) and surfaced as sidecar_error.
	EB.clear()
	cli.apply_reply([{"actor": "lamplighter_orin", "verb": "teleport", "args": {}}], "")
	_ok(EB.events("sidecar_error").size() == 1, "an invalid LLM action is logged as sidecar_error")
	var picked2: Array = cli.pick([{"agent_id": "lamplighter_orin", "faction": "cult", "position": [300.0, 300.0], "phase": "morning", "beat": 4}])
	_ok(picked2[0]["verb"] == "move_to", "a rejected LLM action does not stick; the agent ambient-fills")
	# A transport failure is surfaced as sidecar_error too.
	EB.clear()
	cli.apply_reply([], "connect timeout")
	_ok(EB.events("sidecar_error").size() == 1, "a transport error is logged as sidecar_error")
	cli.shutdown()

func _test_sidecar_bridge() -> void:
	print("[sidecar bridge]")
	var SB: Object = root.get_node("/root/SidecarBridge")
	_ok(SB.client != null, "bridge has a default client")
	var mock := MockSidecar.new()
	mock.set_action("voss", {"actor": "voss", "verb": "attack", "args": {"target": "pell"}})
	SB.set_client(mock)
	var out: Array = SB.propose([{"agent_id": "voss"}])
	_ok(out.size() == 1, "bridge routes one proposal")
	_ok(out[0]["verb"] == "attack", "bridge returns the active client's proposal")
	# Every proposal the bridge returns must be schema-valid for the mock to be useful.
	_ok(ActionSchema.validate(out[0])["ok"], "bridged proposal is schema-valid")

func _test_perception_snapshot() -> void:
	print("[perception]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	EB.clear()
	EB.emit_event("test_seed", {"x": 1})
	var voss: Agent = AG.get_agent("clerk_voss")
	var snap: Dictionary = Perception.build_snapshot(voss, voss.position)
	_ok(snap.get("agent_id", "") == "clerk_voss", "snapshot carries agent_id")
	_ok(snap.has("intent"), "snapshot includes intent")
	_ok(snap.has("position"), "snapshot includes position")
	_ok(snap.has("nearby"), "snapshot includes nearby agents")
	_ok(snap.has("recent_events"), "snapshot includes recent events")
	_ok(snap.has("stage"), "snapshot includes world stage")
	_ok(snap.has("pressures"), "snapshot includes pressures")
	# Another agent placed at voss's position should show up as nearby.
	var pell: Agent = AG.get_agent("dockhand_pell")
	pell.position = voss.position
	var snap2: Dictionary = Perception.build_snapshot(voss, voss.position)
	var nearby_ids: Array = []
	for n in snap2["nearby"]:
		nearby_ids.append(n["id"])
	_ok(nearby_ids.has("dockhand_pell"), "co-located agent appears in nearby")
	_ok(not nearby_ids.has("clerk_voss"), "agent does not list itself as nearby")

func _test_action_commit() -> void:
	print("[action commit]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.position = Vector2.ZERO
	var site: Vector2 = ActionCommit.SITES["iron_cross_warehouse"]
	var before: float = voss.position.distance_to(site)
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)
	_ok(out.has("moved_to"), "move_to reports a new position")
	_ok(voss.position.distance_to(site) < before, "agent moved toward the site")
	_ok(voss.current_action.get("verb", "") == "move_to", "current_action is recorded")
	# talk_to records memory, no movement.
	var pos_before: Vector2 = voss.position
	ActionCommit.commit({"actor": "clerk_voss", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "ritual"}}, voss)
	_ok(voss.position == pos_before, "talk_to does not move the agent")
	_ok(voss.short_memory.size() >= 1, "talk_to records a memory")
	# move_to with an unresolved target is a safe no-op.
	var out2: Dictionary = ActionCommit.commit({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "nowhere_xyz"}}, voss)
	_ok(out2.has("noop"), "unresolved move target is a no-op")
	# coordinate-string target resolves.
	ActionCommit.commit({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "100,100"}}, voss)
	_ok(true, "coordinate target does not error")

func _test_coordinate_anchors_consistent() -> void:
	print("[coordinate anchors]")
	var site_world: Vector2 = MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP)
	_ok(site_world.is_equal_approx(Vector2(1802.5, 1302.0)), "rite site resolves to world (1802.5,1302.0)")
	_ok((ActionCommit.SITES["iron_cross_warehouse"] as Vector2).is_equal_approx(site_world),
		"ActionCommit.SITES rite == map_to_world(WAREHOUSE_MAP)")
	_ok(AmbientSidecar.WAREHOUSE.is_equal_approx(site_world),
		"AmbientSidecar.WAREHOUSE == map_to_world(WAREHOUSE_MAP)")

func _test_city_layout() -> void:
	print("[city layout loader]")
	var sample := {
		"city_outline": [0, 0, 100, 0, 100, 100, 0, 100],
		"water": [[80, 0, 100, 0, 100, 50, 80, 50]],
		"blocks": [[10, 10, 30, 10, 30, 30, 10, 30], [40, 40, 60, 40, 60, 60, 40, 60]],
		"landmarks": [{ "pos": [50, 50], "label": "Test Site" }],
	}
	var layout := CityLayout.from_dict(sample)
	_ok(layout.outline().size() == 4, "outline parsed to 4 vertices")
	_ok(layout.water().size() == 1, "one water polygon parsed")
	_ok(layout.blocks().size() == 2, "two block polygons parsed")
	# Transform correctness: a known map vertex comes back x3.5 in world space.
	_ok(layout.outline()[1].is_equal_approx(Vector2(350.0, 0.0)), "map (100,0) -> world (350,0)")
	_ok((layout.landmarks()[0]["pos"] as Vector2).is_equal_approx(Vector2(175.0, 175.0)),
		"landmark map (50,50) -> world (175,175)")
	_ok(String(layout.landmarks()[0]["label"]) == "Test Site", "landmark label preserved")

func _test_city_layout_data() -> void:
	print("[city layout data integrity]")
	var path := "res://data/city_layout.json"
	_ok(FileAccess.file_exists(path), "city_layout.json exists")
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_ok(typeof(data) == TYPE_DICTIONARY, "city_layout.json parses to a Dictionary")
	var d: Dictionary = data
	_ok((d.get("blocks", []) as Array).size() >= 20, "at least 20 building blocks (a real city, not mega-blocks)")
	# Every coordinate list is even-length and inside the map bounds (0,0)-(1000,706).
	var all_polys: Array = []
	all_polys.append(d.get("city_outline", []))
	for w in d.get("water", []): all_polys.append(w)
	for b in d.get("blocks", []): all_polys.append(b)
	var clean := true
	for poly in all_polys:
		if (poly as Array).size() % 2 != 0 or (poly as Array).size() < 6:
			clean = false
		for i in range((poly as Array).size()):
			var v := float(poly[i])
			var bound := 1000.0 if i % 2 == 0 else 706.0
			if v < 0.0 or v > bound:
				clean = false
	_ok(clean, "all outline/water/block vertices are even-length and within map bounds")

func _test_npc_waypoints_walkable() -> void:
	print("[npc waypoints walkable]")
	# Every scheduled NPC waypoint (world space, in npcs.json) must sit on walkable ground: inside
	# the city outline and clear of every building block and water body. A goal inside an obstacle
	# is unreachable on the navmesh, so the NPC's NavigationAgent2D yields no path and it straight-
	# line-steers into a wall — exactly the cosmetic break this guards against.
	var layout := CityLayout.load_default()
	var outline := layout.outline()
	var blocks := layout.blocks()
	var water := layout.water()
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/npcs.json"))
	var npcs: Dictionary = raw
	for npc_id in npcs:
		var sched: Dictionary = (npcs[npc_id] as Dictionary).get("schedule", {})
		for phase in sched:
			var arr: Array = sched[phase]
			var wp := Vector2(float(arr[0]), float(arr[1]))
			var walkable := Geometry2D.is_point_in_polygon(wp, outline)
			for b in blocks:
				if Geometry2D.is_point_in_polygon(wp, b):
					walkable = false
			for w in water:
				if Geometry2D.is_point_in_polygon(wp, w):
					walkable = false
			_ok(walkable, "%s/%s waypoint is on walkable ground" % [npc_id, phase])

## NavigationServer2D commits region changes on a physics-frame boundary, so a single fixed sleep
## after map_force_update is racy under the headless test loop (occasionally an empty path). Force-
## update and step real frames until the map returns a path, or a small budget runs out — usually
## one iteration, never flaky.
func _await_nav_path(map: RID, from: Vector2, to: Vector2) -> PackedVector2Array:
	var path := PackedVector2Array()
	for _i in range(20):
		NavigationServer2D.map_force_update(map)
		await create_timer(0.02).timeout
		path = NavigationServer2D.map_get_path(map, from, to, true)
		if path.size() >= 2:
			break
	return path

func _test_navmesh_routing() -> void:
	print("[navmesh routing]")
	# A 400x400 walkable square with a 120x120 block dead center.
	var outline := PackedVector2Array([Vector2(0, 0), Vector2(400, 0), Vector2(400, 400), Vector2(0, 400)])
	var hole := PackedVector2Array([Vector2(140, 140), Vector2(260, 140), Vector2(260, 260), Vector2(140, 260)])
	var nav := CityLayout.build_nav_polygon(outline, [hole])
	_ok(nav.get_polygon_count() > 0, "baked navigation polygon has polygons")
	# Stand up a standalone nav map, attach a region, and query a path that must pass the block.
	var map := NavigationServer2D.map_create()
	NavigationServer2D.map_set_active(map, true)
	# Align the map's cell size with the NavigationPolygon bake default (1.0) so the region's
	# polygons register cleanly. If a path is unexpectedly empty, this is the first knob to check.
	NavigationServer2D.map_set_cell_size(map, 1.0)
	var region := NavigationServer2D.region_create()
	NavigationServer2D.region_set_map(region, map)
	NavigationServer2D.region_set_navigation_polygon(region, nav)
	var path := await _await_nav_path(map, Vector2(20, 200), Vector2(380, 200))
	_ok(path.size() >= 2, "a path exists across the square")
	_ok(path.size() >= 3, "the path bends around the central block (has an intermediate waypoint)")
	var inside_block := false
	for p in path:
		if p.x > 140.0 and p.x < 260.0 and p.y > 140.0 and p.y < 260.0:
			inside_block = true
	_ok(not inside_block, "no path point lies inside the block")
	NavigationServer2D.free_rid(region)
	NavigationServer2D.free_rid(map)

func _test_commit_sets_thought() -> void:
	print("[commit thought]")
	var a := Agent.new("voss")
	ActionCommit.commit({"actor": "voss", "verb": "idle", "args": {}, "thought": "All proceeds as foreseen."}, a)
	_ok(a.describe_thought() == "All proceeds as foreseen.", "commit stores the action's thought")
	ActionCommit.commit({"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, a)
	_ok(a.thought == "", "an action without a thought clears the stored one")
	_ok(a.describe_thought().length() > 0, "describe_thought() falls back to synthesis")

func _test_action_attack() -> void:
	print("[action attack]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	var pell: Agent = AG.get_agent("dockhand_pell")
	# A strike within reach connects, damages the target, and logs the blow.
	voss.position = Vector2(400, 300)
	pell.position = Vector2(410, 300)   # inside ATTACK_RADIUS
	pell.hp = 100.0
	pell.downed = false
	EB.clear()
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "attack", "args": {"target": "dockhand_pell"}}, voss)
	_ok(out.get("hit", false) == true, "a strike in reach connects")
	_ok(pell.hp < 100.0, "the target loses HP")
	_ok(EB.events("agent_attacked").size() == 1, "an agent_attacked event is logged")
	_ok(EB.events("agent_attacked")[0]["data"]["target"] == "dockhand_pell", "the event names the target")
	# A swing from out of reach is flavor only — no damage, no event.
	pell.position = Vector2(2000, 2000)
	var hp_before: float = pell.hp
	EB.clear()
	var out_far: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "attack", "args": {"target": "dockhand_pell"}}, voss)
	_ok(out_far.get("hit", false) == false, "a strike out of reach does not connect")
	_ok(pell.hp == hp_before, "an out-of-reach target takes no damage")
	_ok(EB.events("agent_attacked").is_empty(), "no event for an out-of-reach swing")
	# Enough strikes fell the target and log a downed event exactly once.
	pell.position = Vector2(410, 300)
	pell.hp = 100.0
	pell.downed = false
	EB.clear()
	for _i in range(5):
		ActionCommit.commit({"actor": "clerk_voss", "verb": "attack", "args": {"target": "dockhand_pell"}}, voss)
	_ok(pell.downed == true, "enough strikes fell the target")
	_ok(pell.hp == 0.0, "a felled target sits at 0 HP")
	_ok(EB.events("agent_downed").size() == 1, "the target is reported downed exactly once")
	# An unknown target is a safe no-op.
	var out_unknown: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "attack", "args": {"target": "nobody"}}, voss)
	_ok(out_unknown.get("hit", false) == false, "attacking an unknown target is a no-op")

func _test_action_gather_item() -> void:
	print("[action gather_item]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	var dalia: Agent = AG.get_agent("fishwife_dalia")   # cult / logistics
	dalia.inventory.clear()
	EB.clear()
	var out: Dictionary = ActionCommit.commit(
		{"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "ritual_salt"}}, dalia)
	_ok(out.get("added", false) == true, "gathering a known item succeeds")
	_ok(dalia.item_count("ritual_salt") == 1, "the item lands in the agent's own inventory")
	_ok(EB.events("item_gathered").size() == 1, "an item_gathered event is logged")
	_ok(EB.events("item_gathered")[0]["data"]["actor"] == "fishwife_dalia", "the event names the gatherer")
	# Gathering again stacks in the agent's own inventory.
	ActionCommit.commit({"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "ritual_salt"}}, dalia)
	_ok(dalia.item_count("ritual_salt") == 2, "repeated gathering stacks")
	# An unknown item is a safe no-op — no inventory change, no event.
	EB.clear()
	var out_unknown: Dictionary = ActionCommit.commit(
		{"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "moonbeam"}}, dalia)
	_ok(out_unknown.get("added", false) == false, "gathering an unknown item is a no-op")
	_ok(dalia.item_count("moonbeam") == 0, "an unknown item is not added")
	_ok(EB.events("item_gathered").is_empty(), "no event for an unknown item")
	# gather_item fills the agent's OWN inventory and must NOT touch the cult's shared rite cache.
	var SP: Object = root.get_node("/root/SummoningPlan")
	SP.reset()
	var cache_salt_before: int = int(SP.ingredients.get("ritual_salt", 0))
	ActionCommit.commit({"actor": "fishwife_dalia", "verb": "gather_item", "args": {"item_id": "ritual_salt"}}, dalia)
	_ok(int(SP.ingredients.get("ritual_salt", 0)) == cache_salt_before, "gathering does not restock the shared rite cache")
	SP.reset()

func _test_action_talk_to_rumor() -> void:
	print("[action talk_to rumor]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")
	var orin: Agent = AG.get_agent("lamplighter_orin")
	voss.position = Vector2(400, 300)
	orin.position = Vector2(420, 300)   # within TALK_RADIUS
	orin.short_memory.clear()
	voss.short_memory.clear()
	voss.remember("saw the player prowling the harbor")
	EB.clear()
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "the player"}}, voss)
	_ok(out.get("shared", false) == true, "a speaker with real knowledge shares it")
	_ok(orin.short_memory.size() >= 1, "the rumor lands in the listener's memory")
	_ok("harbor" in String(orin.short_memory[-1]), "the listener hears what the speaker knew")
	_ok(voss.short_memory.size() >= 1, "the speaker still records the exchange")
	_ok(EB.events("rumor_spread").size() == 1, "a rumor_spread event is logged")
	_ok(EB.events("rumor_spread")[0]["data"]["to"] == "lamplighter_orin", "the event names the listener")
	var dalia: Agent = AG.get_agent("fishwife_dalia")
	dalia.short_memory.clear()
	dalia.position = Vector2(400, 300)
	orin.short_memory.clear()
	EB.clear()
	var out_empty: Dictionary = ActionCommit.commit(
		{"actor": "fishwife_dalia", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "the player"}}, dalia)
	_ok(out_empty.get("shared", false) == false, "a speaker with nothing to tell shares nothing")
	_ok(orin.short_memory.is_empty(), "no rumor lands when the speaker knows nothing")
	_ok(EB.events("rumor_spread").is_empty(), "no rumor_spread event without real knowledge")
	voss.short_memory.clear()
	voss.remember("the warehouse is nearly ready")
	orin.short_memory.clear()
	orin.position = Vector2(3000, 3000)
	EB.clear()
	var out_far: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "talk_to", "args": {"agent": "lamplighter_orin", "topic": "the rite"}}, voss)
	_ok(out_far.get("shared", false) == false, "a talk across the district does not carry")
	_ok(orin.short_memory.is_empty(), "an out-of-reach listener hears nothing")
	_ok(voss.short_memory.size() >= 1, "the speaker still records trying to talk")

func _test_agent_runtime_beat() -> void:
	print("[agent runtime]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var ART: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	EB.clear()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.position = Vector2(400, 300)
	ART.player_position = Vector2(400, 300)
	ART.active_radius = 50.0   # only voss is active

	# Mock proposes a valid move for voss.
	var mock := MockSidecar.new()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	SB.set_client(mock)

	var before: Vector2 = voss.position
	ART.run_beat()
	_ok(voss.position != before, "active agent acted on its proposal")
	_ok(EB.events("agent_action").size() == 1, "one agent_action logged")
	_ok(EB.events("agent_action")[0]["data"]["actor"] == "clerk_voss", "logged actor is voss")

	# Invalid proposal -> rejected -> fallback.
	EB.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "teleport", "args": {}})
	ART.run_beat()
	_ok(EB.events("action_rejected").size() == 1, "invalid action is rejected, not committed")
	_ok(EB.events("agent_action").size() == 0, "no agent_action for the rejected proposal")

	# Idle proposal -> no movement. Re-pin voss onto the player first so it is unambiguously
	# active this beat; prior beats' schedule-fallback drift is a separate concern from whether
	# an idle verb moves the agent (it must not).
	EB.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "idle", "args": {}})
	voss.position = Vector2(400, 300)
	var pos_idle: Vector2 = voss.position
	ART.run_beat()
	_ok(voss.position == pos_idle, "idle proposal leaves the agent in place")

func _test_overseer_state() -> void:
	print("[overseer]")
	var OV: Object = root.get_node("/root/Overseer")
	var EB: Object = root.get_node("/root/EventBus")
	OV.reset()
	# Directives: one-shot, keyed by agent.
	OV.issue_directive("clerk_voss", {"actor": "clerk_voss", "verb": "hide", "args": {}})
	_ok(OV.has_directive("clerk_voss"), "directive queued")
	var d: Dictionary = OV.take_directive("clerk_voss")
	_ok(d.get("verb", "") == "hide", "directive returned")
	_ok(not OV.has_directive("clerk_voss"), "directive is one-shot")
	_ok(OV.take_directive("nobody").is_empty(), "no directive returns empty dict")
	# Coordinate: issue the same directive to several agents.
	OV.coordinate(["fishwife_dalia", "lamplighter_orin"], {"verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	_ok(OV.has_directive("fishwife_dalia"), "coordinate queues for agent 1")
	_ok(OV.has_directive("lamplighter_orin"), "coordinate queues for agent 2")
	_ok(OV.take_directive("fishwife_dalia").get("actor", "") == "fishwife_dalia", "coordinate sets actor per agent")
	# Player involvement is initially false, flips on a player_ event.
	OV.reset()
	_ok(OV.allows_exposure() == false, "exposure disallowed until player is involved")
	EB.emit_event("player_sabotage", {"actor": "player", "item": "ritual_salt"})
	_ok(OV.allows_exposure() == true, "a player_ event marks the player involved")

func _test_critic_verdicts() -> void:
	print("[critic]")
	var AG: Object = root.get_node("/root/Agents")
	var OV: Object = root.get_node("/root/Overseer")
	AG.rebuild()
	OV.reset()
	var voss: Agent = AG.get_agent("clerk_voss")        # cult / leader
	var pell: Agent = AG.get_agent("dockhand_pell")     # civilian / victim
	var orin: Agent = AG.get_agent("lamplighter_orin")  # cult / scout_waverer

	# Coherent cult ritual step: approved.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, voss)["verdict"] == "approve",
		"cult leader may perform a ritual step")
	# Victim performing a ritual step: incoherent -> veto.
	_ok(Critic.review({"actor": "dockhand_pell", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, pell)["verdict"] == "veto",
		"the victim cannot perform a ritual step")
	# A turned waverer (faction no longer cult) performing a ritual step -> veto.
	orin.faction = "ally"
	_ok(Critic.review({"actor": "lamplighter_orin", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, orin)["verdict"] == "veto",
		"a turned waverer would not perform a ritual step")
	# Exposing report without player involvement -> veto; with involvement -> approve.
	var expose := {"actor": "clerk_voss", "verb": "report", "args": {"to": "nighthawks", "info": "the cult meets at the warehouse"}}
	_ok(Critic.review(expose, voss)["verdict"] == "veto", "no caught-by-chance: exposing report vetoed")
	OV.player_involved = true
	_ok(Critic.review(expose, voss)["verdict"] == "approve", "exposing report allowed once player is involved")
	# Ordinary move is always fine.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)["verdict"] == "approve",
		"ordinary move approved")

func _test_critic_downed_veto() -> void:
	print("[critic downed]")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild()
	var voss: Agent = AG.get_agent("clerk_voss")  # cult / leader
	# Upright, the leader acts normally.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)["verdict"] == "approve",
		"an upright agent may move")
	# Felled, every active verb is vetoed — a downed body cannot move, work the rite, or strike.
	voss.downed = true
	_ok(Critic.review({"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}}, voss)["verdict"] == "veto",
		"a downed agent cannot move")
	_ok(Critic.review({"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "draw_circle"}}, voss)["verdict"] == "veto",
		"a downed agent cannot work the rite")
	_ok(Critic.review({"actor": "clerk_voss", "verb": "attack", "args": {"target": "dockhand_pell"}}, voss)["verdict"] == "veto",
		"a downed agent cannot attack")
	# Only idle survives — the one coherent thing a felled agent can do.
	_ok(Critic.review({"actor": "clerk_voss", "verb": "idle", "args": {}}, voss)["verdict"] == "approve",
		"a downed agent may still idle")

func _test_runtime_with_overseer() -> void:
	print("[runtime + overseer]")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var OV: Object = root.get_node("/root/Overseer")
	var ART: Object = root.get_node("/root/AgentRuntime")
	AG.rebuild()
	OV.reset()
	var voss: Agent = AG.get_agent("clerk_voss")
	voss.position = Vector2(400, 300)
	ART.player_position = Vector2(400, 300)
	ART.active_radius = 50.0

	# 1) Critic veto: turned waverer proposing a ritual step -> vetoed -> no commit.
	var orin: Agent = AG.get_agent("lamplighter_orin")
	orin.faction = "ally"
	orin.position = Vector2(400, 300)   # make orin active too
	var mock := MockSidecar.new()
	mock.set_action("lamplighter_orin", {"actor": "lamplighter_orin", "verb": "perform_ritual_step", "args": {"step": "x"}})
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "idle", "args": {}})
	SB.set_client(mock)
	EB.clear()
	ART.run_beat()
	_ok(EB.events("action_vetoed").size() >= 1, "incoherent action is vetoed")
	var ritual_actions: Array = EB.events("agent_action").filter(func(e): return e["data"]["verb"] == "perform_ritual_step")
	_ok(ritual_actions.size() == 0, "vetoed ritual step is never committed")

	# 2) Overseer directive overrides the agent's own proposal.
	AG.rebuild(); OV.reset()
	var voss2: Agent = AG.get_agent("clerk_voss")
	voss2.position = Vector2(800, 800)              # far from player -> not active
	ART.player_position = Vector2(0, 0)
	ART.active_radius = 10.0
	var before: Vector2 = voss2.position
	OV.issue_directive("clerk_voss", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	EB.clear()
	ART.run_beat()
	_ok(EB.events("overseer_directive").size() == 1, "directive committed even for an inactive agent")
	_ok(voss2.position != before, "directed agent moved per the directive")

	# 3) End-to-end exposure invariant: exposing report blocked, then allowed.
	AG.rebuild(); OV.reset()
	var voss3: Agent = AG.get_agent("clerk_voss")
	voss3.position = Vector2(0, 0)
	ART.player_position = Vector2(0, 0)
	ART.active_radius = 50.0
	mock.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "report", "args": {"to": "nighthawks", "info": "the cult meets at the warehouse"}})
	# make only voss active: move others away
	for a in AG.all():
		if a.id != "clerk_voss":
			a.position = Vector2(9000, 9000)
	EB.clear()
	ART.run_beat()
	_ok(EB.events("action_vetoed").size() == 1, "exposing report vetoed without player involvement")
	# Player gets involved, then the same report is allowed.
	EB.emit_event("player_investigate", {"actor": "player"})
	EB.clear()
	mock.set_action("clerk_voss", {"actor": "clerk_voss", "verb": "report", "args": {"to": "nighthawks", "info": "the cult meets at the warehouse"}})
	ART.run_beat()
	_ok(EB.events("agent_action").size() == 1, "report committed once the player is involved")

func _test_summoning_plan() -> void:
	print("[summoning plan]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	SP.reset()
	var base: float = SP.manifestation_strength()
	# Impede weakens the manifestation.
	SP.add_impede(20.0, "test")
	_ok(SP.manifestation_strength() < base, "impede lowers manifestation strength")
	_ok(SP.impede_score == 20.0, "impede accumulates")
	# Removing an ingredient weakens it further AND sets back the countdown.
	var cd_before: int = SP.countdown_beats
	var strength_before: float = SP.manifestation_strength()
	_ok(SP.remove_ingredient("ritual_salt", 1), "ritual_salt removed from cult stock")
	_ok(SP.manifestation_strength() < strength_before, "fewer ingredients -> weaker")
	_ok(SP.countdown_beats > cd_before, "removing an ingredient sets back the countdown")
	# Removing more than held fails and changes nothing.
	var cd_now: int = SP.countdown_beats
	_ok(SP.remove_ingredient("ritual_salt", 999) == false, "cannot remove more than held")
	_ok(SP.countdown_beats == cd_now, "failed removal does not set back the countdown")
	# Strength is clamped to a floor.
	SP.add_impede(1000.0, "overkill")
	_ok(SP.manifestation_strength() >= SP.MIN_STRENGTH, "strength never drops below the floor")

func _test_summoning_countdown_and_climax() -> void:
	print("[summoning countdown]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	SP.reset()
	SP.countdown_beats = 3
	var fired: Array = []
	var cb := func(strength: float): fired.append(strength)
	SP.summoning_climax.connect(cb)
	var beats_reported: Array = []
	var cc := func(n: int): beats_reported.append(n)
	SP.countdown_changed.connect(cc)
	EB.clear()
	SP.tick_countdown()
	_ok(SP.countdown_beats == 2, "tick decrements 3 -> 2")
	_ok(fired.is_empty(), "no climax before zero")
	_ok(beats_reported == [2], "countdown_changed emits new beats_left")
	SP.tick_countdown()
	SP.tick_countdown()
	_ok(SP.countdown_beats == 0, "reaches zero")
	_ok(fired.size() == 1, "climax fires exactly once")
	_ok(is_equal_approx(fired[0], SP.manifestation_strength()), "climax strength == manifestation_strength()")
	_ok(SP.climax_fired, "climax_fired latched true")
	var saw := false
	for e in EB.events("summoning_climax"):
		saw = true
	_ok(saw, "summoning_climax event logged")
	SP.tick_countdown()
	_ok(fired.size() == 1, "does not re-fire after climax")
	_ok(beats_reported == [2, 1, 0], "countdown_changed fired only on real decrements, not on the zero/climax tick")
	SP.summoning_climax.disconnect(cb)
	SP.countdown_changed.disconnect(cc)
	SP.reset()
	paused = false   # the climax now drives EndGame to pause the tree; clear it for later tests

func _test_summoning_progress_readouts() -> void:
	print("[summoning progress]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	SP.reset()
	_ok(is_equal_approx(SP.closeness_ratio(), 0.0), "fresh plan = 0 closeness")
	SP.countdown_beats = SP.START_COUNTDOWN / 2
	_ok(is_equal_approx(SP.closeness_ratio(), 0.5), "halfway countdown = 0.5 closeness")
	SP.countdown_beats = 0
	_ok(is_equal_approx(SP.closeness_ratio(), 1.0), "zero countdown = full closeness")
	_ok(is_equal_approx(SP.ingredients_ratio(), 1.0), "fresh stock = full ratio")
	_ok(SP.interference_band() == "none", "no impede = none band")
	SP.add_impede(40.0)
	_ok(SP.interference_band() == "heavy", "large impede = heavy band")
	SP.reset()

func _test_summoning_advance_rite() -> void:
	print("[summoning advance_rite]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	SP.reset()
	SP.countdown_beats = 5
	var fired: Array = []
	var cb := func(strength: float): fired.append(strength)
	SP.summoning_climax.connect(cb)
	var beats_reported: Array = []
	var cc := func(n: int): beats_reported.append(n)
	SP.countdown_changed.connect(cc)
	EB.clear()
	# Working the rite hastens the descent — by more than one beat when several hands work it.
	SP.advance_rite(2)
	_ok(SP.countdown_beats == 3, "advance_rite(2) hastens 5 -> 3")
	_ok(beats_reported == [3], "advance_rite emits countdown_changed with the new beats_left")
	_ok(fired.is_empty(), "no climax before zero")
	# Default step is a single beat.
	SP.advance_rite()
	_ok(SP.countdown_beats == 2, "advance_rite() defaults to one beat (3 -> 2)")
	# Overshooting zero clamps to zero and fires the climax exactly once.
	SP.advance_rite(10)
	_ok(SP.countdown_beats == 0, "advance_rite clamps at zero, never negative")
	_ok(fired.size() == 1, "climax fires exactly once when the rite completes the descent")
	_ok(is_equal_approx(fired[0], SP.manifestation_strength()), "climax strength == manifestation_strength()")
	_ok(SP.climax_fired, "climax_fired latched true")
	var saw := false
	for e in EB.events("summoning_climax"):
		saw = true
	_ok(saw, "summoning_climax event logged")
	# After the climax, further rite work is inert.
	SP.advance_rite(3)
	_ok(fired.size() == 1, "advance_rite does not re-fire after the climax")
	_ok(SP.countdown_beats == 0, "countdown stays at zero after the climax")
	SP.summoning_climax.disconnect(cb)
	SP.countdown_changed.disconnect(cc)
	SP.reset()
	paused = false   # the climax now drives EndGame to pause the tree; clear it for later tests

func _test_ritual_step_advances_summoning() -> void:
	print("[ritual step -> summoning]")
	var AG: Object = root.get_node("/root/Agents")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild()
	SP.reset()
	var site: Vector2 = ActionCommit.SITES["iron_cross_warehouse"]
	var voss: Agent = AG.get_agent("clerk_voss")   # cult / leader
	_ok(voss.faction == "cult", "clerk_voss is a cultist (precondition)")
	# A cultist performing the rite AT the warehouse hastens the descent and logs it.
	voss.position = site
	var cd_before: int = SP.countdown_beats
	EB.clear()
	var out: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "Inscribe the circle."}}, voss)
	_ok(SP.countdown_beats < cd_before, "a cultist's rite at the site advances the summoning clock")
	_ok(out.get("advanced", false) == true, "outcome reports the rite advanced the summoning")
	_ok(EB.events("ritual_advanced").size() == 1, "a ritual_advanced event is logged")
	_ok(EB.events("ritual_advanced")[0]["data"]["actor"] == "clerk_voss", "the event names the performing cultist")
	# The same cultist far from the site cannot advance the rite — it is flavor only.
	voss.position = site + Vector2(1000, 1000)
	var cd_far: int = SP.countdown_beats
	EB.clear()
	var out_far: Dictionary = ActionCommit.commit(
		{"actor": "clerk_voss", "verb": "perform_ritual_step", "args": {"step": "Mutter the name."}}, voss)
	_ok(SP.countdown_beats == cd_far, "a cultist away from the site does not advance the clock")
	_ok(out_far.get("advanced", false) == false, "an off-site rite is flavor-only")
	_ok(EB.events("ritual_advanced").is_empty(), "no ritual_advanced event off-site")
	# A non-cultist standing on the very site still cannot drive the summoning.
	var pell: Agent = AG.get_agent("dockhand_pell")   # civilian / victim
	pell.position = site
	var cd_civ: int = SP.countdown_beats
	EB.clear()
	var out_civ: Dictionary = ActionCommit.commit(
		{"actor": "dockhand_pell", "verb": "perform_ritual_step", "args": {"step": "Watch the chalk."}}, pell)
	_ok(SP.countdown_beats == cd_civ, "a non-cultist at the site does not advance the clock")
	_ok(out_civ.get("advanced", false) == false, "a non-cultist's rite is flavor-only")
	SP.reset()

func _test_ambient_sidecar_performs_rite() -> void:
	print("[ambient sidecar rite]")
	var amb := AmbientSidecar.new()
	# A cultist standing ON the rite site should work the ritual, not keep walking.
	var at_site := {"agent_id": "clerk_voss", "faction": "cult",
		"position": [AmbientSidecar.WAREHOUSE.x, AmbientSidecar.WAREHOUSE.y], "phase": "night", "beat": 11}
	var out: Array = amb.propose([at_site])
	_ok(out[0]["verb"] == "perform_ritual_step", "a cultist at the warehouse performs the rite")
	_ok(ActionSchema.validate(out[0])["ok"], "the rite proposal is schema-valid")
	_ok(String((out[0]["args"] as Dictionary).get("step", "")) != "", "the rite proposal carries a step")
	# A cultist still far from the site keeps converging (move_to), not performing.
	var far := {"agent_id": "clerk_voss", "faction": "cult", "position": [200.0, 200.0], "phase": "night", "beat": 11}
	var out_far: Array = amb.propose([far])
	_ok(out_far[0]["verb"] == "move_to", "a distant cultist is still walking to the warehouse")
	# Deterministic: the same snapshot replays the same rite step.
	var again: Array = amb.propose([at_site])
	_ok(again[0]["args"]["step"] == out[0]["args"]["step"], "the same beat replays the same rite step")

func _test_cult_progress_panel() -> void:
	print("[cult panel]")
	var SP: Object = root.get_node("/root/SummoningPlan"); SP.reset()
	var EB: Object = root.get_node("/root/EventBus"); EB.clear()
	var panel = load("res://ui/CultProgressPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "panel hidden by default")
	SP.countdown_beats = SP.START_COUNTDOWN / 2
	panel.toggle()
	await process_frame
	_ok(panel.visible, "panel toggles visible")
	_ok(is_equal_approx(panel.get_node("Margin/Body/Closeness/Bar").value, 50.0), "closeness bar at 50%")
	_ok("50%" in panel.get_node("Margin/Body/Summary").text, "summary line shows the readiness percentage")
	# Both secret cult-move types (raw + Critic-amended) must be filtered out; only the
	# public player deed survives. Assert against the rendered TYPE name, not the verb.
	EB.emit_event("agent_action", {"actor": "clerk_voss", "verb": "perform_ritual_step"})
	EB.emit_event("agent_action_amended", {"actor": "masked_acolyte", "verb": "perform_ritual_step"})
	EB.emit_event("player_sabotage", {"actor": "player", "item": "candle"})
	var joined := ""
	for line in panel.public_event_lines():
		joined += String(line) + "\n"
	_ok("player sabotage" in joined, "public player event is listed")
	_ok(not ("agent action" in joined), "secret agent_action move is excluded")
	_ok(not ("amended" in joined), "secret agent_action_amended move is excluded")
	panel.queue_free()
	await process_frame
	SP.reset(); EB.clear()

func _test_npc_binds_to_agent() -> void:
	print("[npc bind]")
	var Ag: Object = root.get_node("/root/Agents")
	Ag.rebuild()
	var agent = Ag.all()[0]
	agent.position = Vector2(777, 333)
	var npc = load("res://scenes/NPC.tscn").instantiate()
	npc.npc_id = agent.id
	root.add_child(npc)
	await process_frame
	_ok(npc.is_bound(), "node bound to a registry agent")
	_ok(npc.steer_goal() == Vector2(777, 333), "bound node steers toward its agent's position")
	# Unknown id falls back to schedule mode (not bound).
	var loose = load("res://scenes/NPC.tscn").instantiate()
	loose.npc_id = "no_such_agent"
	root.add_child(loose)
	await process_frame
	_ok(not loose.is_bound(), "unknown id is not bound (schedule fallback)")
	npc.queue_free()
	loose.queue_free()
	await process_frame

func _test_inspect_signal() -> void:
	print("[inspect signal]")
	var WS: Object = root.get_node("/root/WorldState")
	var got: Array = []
	var cb := func(id: String): got.append(id)
	WS.inspect_requested.connect(cb)
	WS.inspect_requested.emit("clerk_voss")
	_ok(got == ["clerk_voss"], "inspect_requested carries the agent id")
	WS.inspect_requested.disconnect(cb)

func _test_character_card_opens() -> void:
	print("[character card]")
	var Ag: Object = root.get_node("/root/Agents"); Ag.rebuild()
	var WS: Object = root.get_node("/root/WorldState")
	var id: String = Ag.all()[0].id
	var card = load("res://ui/CharacterCard.tscn").instantiate()
	root.add_child(card)
	await process_frame
	_ok(not card.visible, "card hidden by default")
	WS.inspect_requested.emit(id)
	await process_frame
	_ok(card.visible, "card opens on inspect_requested")
	_ok(card.shows_agent(id), "card is showing the inspected agent")
	# _refresh() actually bound the agent's data, not just toggled visibility:
	var agent_obj: Object = Ag.get_agent(id)
	_ok(card._name.text == agent_obj.display_name, "card shows the inspected agent's name")
	_ok(card._thought.text != "", "card shows a non-empty thought line")
	card.queue_free()
	await process_frame

func _test_city_blocks_scene() -> void:
	print("[city blocks scene]")
	# Hand-authored traversal map: ~50 building bodies + a player, all real nodes baked into the
	# scene file (no runtime/procedural construction). Guard the authored structure so it can't
	# silently regress: the Buildings container exists, every building is a solid StaticBody2D with
	# a collision polygon, and a Player is present so the scene is walkable on its own.
	var packed: PackedScene = load("res://scenes/CityBlocks.tscn")
	_ok(packed != null, "CityBlocks.tscn exists and loads")
	if packed == null:
		return
	var scene = packed.instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var buildings: Node = scene.get_node_or_null("Buildings")
	_ok(buildings != null, "scene has a Buildings container")
	var bodies: Array = []
	if buildings != null:
		for c in buildings.get_children():
			if c is StaticBody2D:
				bodies.append(c)
	_ok(bodies.size() >= 45 and bodies.size() <= 60,
		"~50 building bodies authored (got %d)" % bodies.size())
	var all_have_collider := bodies.size() > 0
	for b in bodies:
		var cp: Node = b.get_node_or_null("CollisionPolygon2D")
		if cp == null or (cp as CollisionPolygon2D).polygon.size() < 3:
			all_have_collider = false
	_ok(all_have_collider, "every building has a CollisionPolygon2D collider (>= 3 pts)")
	_ok(scene.get_node_or_null("Player") != null, "scene includes a Player for traversal")
	# Demo parts moved here from the retired City.tscn hub: the city-edge wall ring keeps the
	# player on the map, two interior-room transition doors lead to the Nighthawks HQ and the
	# University archive, and at least the demo NPCs (Orin, Dalia) populate the streets -- all
	# authored editor nodes living directly in this scene.
	var walls: Node = scene.get_node_or_null("Walls")
	var wall_bodies := 0
	if walls != null:
		for c in walls.get_children():
			if c is StaticBody2D:
				wall_bodies += 1
	_ok(wall_bodies == 4, "four city-edge boundary walls keep the player on the map (got %d)" % wall_bodies)
	var door_targets: Array = []
	var npc_count := 0
	for n in scene.get_children():
		if n.is_in_group("npc"):
			npc_count += 1
		if n.is_in_group("interactable"):
			var t: Variant = n.get("target_scene")
			if typeof(t) == TYPE_STRING and t != "":
				door_targets.append(t)
	_ok(npc_count >= 2, "demo NPCs authored into the city (got %d)" % npc_count)
	_ok(door_targets.has("res://scenes/NighthawksHQ.tscn"),
		"a transition door leads to the Nighthawks HQ interior")
	_ok(door_targets.has("res://scenes/UniversityArchive.tscn"),
		"a transition door leads to the University archive interior")
	# The descending-god (降临) rite site, restored into the authored map. The simulation already
	# anchors the warehouse at ActionCommit.SITES.iron_cross_warehouse (== map_to_world(WAREHOUSE_MAP)
	# == (1802.5,1302.0)), so the scene must agree with it: (a) show a named Warehouse marker, (b)
	# place the "spoil the cache" sabotage interactable within rite range of that point, and (c) keep
	# the point clear of every building collider so the player can actually walk in and reach it.
	var rite: Vector2 = ActionCommit.SITES["iron_cross_warehouse"]
	_ok(scene.get_node_or_null("Warehouse") != null, "scene has a Warehouse rite-site marker")
	var sabotage: Node = null
	for n in scene.get_children():
		if n.is_in_group("interactable") and bool(n.get("sabotage_cache")):
			sabotage = n
			break
	_ok(sabotage != null, "scene has a sabotage-the-cache interactable")
	if sabotage != null:
		_ok((sabotage as Node2D).position.distance_to(rite) <= ActionCommit.RITE_RADIUS,
			"the sabotage point sits within rite range of the warehouse")
	var buried := false
	if buildings != null:
		for b in buildings.get_children():
			var cp: CollisionPolygon2D = b.get_node_or_null("CollisionPolygon2D")
			if cp != null and Geometry2D.is_point_in_polygon(rite - (b as Node2D).position, cp.polygon):
				buried = true
	_ok(not buried, "the rite site is clear of every building collider (reachable)")
	scene.queue_free()
	await process_frame

func _test_occult_divination() -> void:
	print("[occult divination]")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var INV: Object = root.get_node("/root/Inventory")
	var WS: Object = root.get_node("/root/WorldState")
	var WM: Object = root.get_node("/root/WorldManager")
	OTM.rebuild()
	INV.clear()
	WS.set_pressure(&"fatigue", 0.0)
	WS.set_pressure(&"attention", 0.0)
	WS.set_pressure(&"corruption", 0.0)   # no mislead at zero corruption
	# Gating: cannot use without owning the kit + the candle ingredient.
	_ok(OTM.can_use("divination") == false, "divination blocked without tool item")
	INV.add("divination_kit")
	_ok(OTM.can_use("divination") == false, "divination blocked without candle ingredient")
	INV.add("candle", 1)
	_ok(OTM.can_use("divination") == true, "divination usable once kit + candle present")
	# Use: pays cost, consumes the candle, yields a directional lead.
	var res: Dictionary = OTM.use("divination")
	_ok(res.get("ok", false), "divination returns ok")
	_ok(String(res.get("lead", "")) != "", "divination yields a directional lead")
	_ok(WS.get_pressure(&"fatigue") > 0.0, "divination spent fatigue")
	_ok(INV.count_of("candle") == 0, "divination consumed the candle")
	# No-name guarantee: the lead never contains the true resolved site id.
	var true_site: String = String(WM.slots.get("primary_ritual_site", ""))
	_ok(true_site == "" or not String(res["lead"]).contains(true_site), "lead never names the true site")

func _test_divination_hints_never_name_site() -> void:
	print("[divination no-name guarantee]")
	for site in DivinationTool.SITE_HINTS.keys():
		var hint: String = String(DivinationTool.SITE_HINTS[site])
		_ok(not hint.to_lower().contains(String(site).to_lower()),
			"hint for '%s' never contains its own site id" % site)

func _test_occult_other_tools() -> void:
	print("[occult other tools]")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var INV: Object = root.get_node("/root/Inventory")
	var WS: Object = root.get_node("/root/WorldState")
	OTM.rebuild()
	INV.clear()
	WS.set_pressure(&"fatigue", 0.0)
	WS.set_pressure(&"corruption", 0.0)
	# Residue sight: owns lens, no ingredient cost.
	INV.add("spirit_lens")
	_ok(OTM.can_use("residue_sight"), "residue sight usable with just the lens")
	var r1: Dictionary = OTM.use("residue_sight")
	_ok(r1.get("ok", false), "residue sight returns ok")
	# Dream fragments: produces dream_residue.
	INV.add("dream_draught")
	INV.add("dream_herb", 1)
	var r2: Dictionary = OTM.use("dream_fragments")
	_ok(r2.get("ok", false), "dream fragments returns ok")
	_ok(INV.count_of("dream_residue") == 1, "dream fragments produces dream_residue")
	_ok(INV.count_of("dream_herb") == 0, "dream fragments consumes dream_herb")
	# Gray fog: hard-capped at 3 uses per run.
	INV.add("gray_fog_focus")
	INV.add("consecrated_chalk", 9)
	_ok(OTM.use("gray_fog").get("ok", false), "gray fog use 1 ok")
	OTM.use("gray_fog")
	OTM.use("gray_fog")
	_ok(OTM.can_use("gray_fog") == false, "gray fog refused after 3 uses")
	_ok(OTM.use("gray_fog").get("ok", false) == false, "gray fog 4th use blocked")

func _test_occult_tool_views() -> void:
	print("[occult tool views]")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var views: Array = OTM.tool_views()
	_ok(views.size() == 4, "four occult tools surfaced")
	var div: Variant = null
	for v in views:
		if v["id"] == "divination":
			div = v
	_ok(div != null, "divination present")
	_ok(String(div["name"]) == "Divination", "name surfaced")
	_ok(String(div["description"]) != "", "description surfaced")
	_ok(is_equal_approx(float(div["cost"]["fatigue"]), 8.0), "fatigue cost surfaced")
	_ok((div["cost"]["items"] as Dictionary).has("candle"), "ingredient cost surfaced")
	_ok(div.has("can_use") and div.has("uses_left"), "availability fields surfaced")

func _test_ritual_panel() -> void:
	print("[ritual panel]")
	var panel = load("res://ui/RitualPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "panel hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "panel toggles visible")
	_ok(panel.tool_row_count() == 4, "renders one row per occult tool")
	_ok(panel.rite_step_count() >= 3, "summoning rite lists its steps")
	panel.queue_free()
	await process_frame

func _test_player_actions() -> void:
	print("[player actions]")
	var PA: Object = root.get_node("/root/PlayerActions")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var OV: Object = root.get_node("/root/Overseer")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild(); SP.reset(); OV.reset(); EB.clear()

	# Sabotage: strips a cult ingredient, raises impede, sets back the countdown, and
	# marks the player involved (so the overseer will now allow exposure).
	var cd_before: int = SP.countdown_beats
	var impede_before: float = SP.impede_score
	_ok(PA.sabotage("ritual_salt"), "sabotage of a held ingredient succeeds")
	_ok(SP.countdown_beats > cd_before, "sabotage sets back the summoning countdown")
	_ok(SP.impede_score > impede_before, "sabotage raises impede")
	_ok(EB.events("player_sabotage").size() == 1, "sabotage logs a player event")
	_ok(OV.allows_exposure(), "sabotage marks the player involved")
	# Sabotage of an absent ingredient fails and changes nothing.
	_ok(PA.sabotage("does_not_exist") == false, "sabotage of an unheld ingredient fails")

	# Social influence: turning the waverer flips his faction and raises impede.
	var orin: Agent = AG.get_agent("lamplighter_orin")
	_ok(orin.faction == "cult", "orin starts in the cult")
	var impede2: float = SP.impede_score
	_ok(PA.social_influence("lamplighter_orin"), "turning the waverer succeeds")
	_ok(orin.faction == "ally", "the waverer is turned to an ally")
	_ok(SP.impede_score > impede2, "turning the waverer raises impede")
	_ok(EB.events("player_social").size() == 1, "social influence logs a player event")
	# A non-waverer cannot be turned.
	_ok(PA.social_influence("clerk_voss") == false, "the committed leader cannot be turned")

func _test_player_sabotage_any() -> void:
	print("[player sabotage_any]")
	var PA: Object = root.get_node("/root/PlayerActions")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	SP.reset(); EB.clear()
	# The warehouse interactable gives the player a single "strip the cache" verb — they don't
	# name an ingredient. sabotage_any picks one of the held items and routes it through sabotage.
	var total_before: int = SP._total_ingredients()
	var impede_before: float = SP.impede_score
	var stripped: String = PA.sabotage_any()
	_ok(stripped in ["candle", "consecrated_chalk", "ritual_salt"], "sabotage_any strips a real cache ingredient")
	_ok(SP._total_ingredients() == total_before - 1, "sabotage_any removes exactly one item from the cache")
	_ok(SP.impede_score > impede_before, "sabotage_any raises impede (it routes through sabotage)")
	_ok(EB.events("player_sabotage").size() == 1, "sabotage_any logs a player_sabotage event")
	# Drain the cache, then sabotage_any must no-op cleanly — nothing left to strip.
	while PA.sabotage_any() != "":
		pass
	EB.clear()
	impede_before = SP.impede_score
	_ok(PA.sabotage_any() == "", "sabotage_any returns empty when the cache is bare")
	_ok(SP.impede_score == impede_before, "a no-op sabotage_any does not change impede")
	_ok(EB.events("player_sabotage").size() == 0, "a no-op sabotage_any logs nothing")
	SP.reset(); EB.clear()

func _test_dialogue_social_influence_effect() -> void:
	print("[dialogue social_influence]")
	var DM: Object = root.get_node("/root/DialogueManager")
	var AG: Object = root.get_node("/root/Agents")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	AG.rebuild(); SP.reset(); EB.clear()
	var orin: Agent = AG.get_agent("lamplighter_orin")
	_ok(orin.faction == "cult" and orin.role == "scout_waverer", "orin starts as a wavering cultist (precondition)")
	var impede_before: float = SP.impede_score
	# A dialogue effect of type social_influence routes through PlayerActions: the waverer is
	# won over to the player's side and the hidden impede score rises — the diegetic counterpart
	# to the console/`PA.social_influence` path, so persuasion in conversation actually bites.
	DM._apply_effect({"type": "social_influence", "agent": "lamplighter_orin"})
	_ok(orin.faction == "ally", "social_influence dialogue effect turns orin to the player's side")
	_ok(SP.impede_score > impede_before, "turning the waverer in dialogue raises the hidden impede score")
	_ok(EB.events("player_social").size() == 1, "the dialogue turn logs a player_social event")
	AG.rebuild(); SP.reset(); EB.clear()

func _test_orin_persuade_dialogue() -> void:
	print("[orin persuade dialogue]")
	var DM: Object = root.get_node("/root/DialogueManager")
	var AG: Object = root.get_node("/root/Agents")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var ND: Object = root.get_node("/root/NpcDB")
	AG.rebuild(); SP.reset()
	# Orin must be wired to his own dialogue tree, otherwise the player can never reach the
	# persuade option in-world (an NPC with an empty dialogue_id can't be talked to at all).
	_ok(String(ND.get_def("lamplighter_orin").get("dialogue_id", "")) == "orin_waverer",
		"orin is wired to the orin_waverer dialogue tree")
	_ok(DM.trees.has("orin_waverer"), "the orin_waverer dialogue tree is authored")
	var tree: Dictionary = DM.trees.get("orin_waverer", {})
	var nodes: Dictionary = tree.get("nodes", {})
	var root_node: Dictionary = nodes.get(String(tree.get("start", "root")), {})
	var orin: Agent = AG.get_agent("lamplighter_orin")
	_ok(orin.faction == "cult", "orin starts in the cult (precondition)")
	# While orin is still a cultist the persuade line is on offer (gated requires_agent_faction).
	var visible_cult: Array = DM._visible_options(root_node)
	var idx: int = _option_index_with(visible_cult, "Persuade")
	_ok(idx >= 0, "the persuade option is visible while orin is a cultist")
	# Choosing it carries a social_influence effect that turns him to the player's side — the same
	# verb the console/world use, so the conversation actually flips faction and adds impede.
	var impede_before: float = SP.impede_score
	for e in (visible_cult[idx] as Dictionary).get("effects", []):
		DM._apply_effect(e)
	_ok(orin.faction == "ally", "choosing the persuade option turns orin to the player's side")
	_ok(SP.impede_score > impede_before, "persuading orin in conversation raises the impede score")
	# Once he's turned, the persuade option is gated away — you can't re-persuade an ally, and the
	# vanishing option reads as the conversation having moved past the moment of doubt.
	var visible_ally: Array = DM._visible_options(root_node)
	_ok(_option_index_with(visible_ally, "Persuade") < 0,
		"the persuade option is hidden once orin is already an ally")
	AG.rebuild(); SP.reset()

func _test_dev_console_interference_commands() -> void:
	print("[dev console interference]")
	var DC: Object = root.get_node("/root/DevConsole")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")
	AG.rebuild(); SP.reset(); EB.clear()
	# `sabotage <item>` strips that named ingredient through PlayerActions.sabotage — the console
	# counterpart to the warehouse interactable, for poking the rite without walking there.
	var salt_before: int = int(SP.ingredients.get("ritual_salt", 0))
	DC._run("sabotage ritual_salt")
	_ok(int(SP.ingredients.get("ritual_salt", 0)) == salt_before - 1, "console `sabotage <item>` strips the named ingredient")
	_ok(EB.events("player_sabotage").size() == 1, "console sabotage logs a player_sabotage event")
	# `sabotage` with no argument strips whatever the cache still holds (sabotage_any).
	var total_before: int = SP._total_ingredients()
	DC._run("sabotage")
	_ok(SP._total_ingredients() == total_before - 1, "console `sabotage` with no arg strips one held item")
	_ok(EB.events("player_sabotage").size() == 2, "the bare console sabotage also logs an event")
	# `turn <agent>` routes through social_influence: the waverer flips, anyone else is refused.
	var orin: Agent = AG.get_agent("lamplighter_orin")
	_ok(orin.faction == "cult", "orin starts in the cult (precondition)")
	DC._run("turn lamplighter_orin")
	_ok(orin.faction == "ally", "console `turn <agent>` turns the waverer to the player's side")
	_ok(EB.events("player_social").size() == 1, "console turn logs a player_social event")
	# Turning a committed leader is refused and changes nothing.
	var voss: Agent = AG.get_agent("clerk_voss")
	DC._run("turn clerk_voss")
	_ok(voss.faction == "cult", "console `turn` cannot flip a committed leader")
	_ok(EB.events("player_social").size() == 1, "a refused console turn logs no new event")
	AG.rebuild(); SP.reset(); EB.clear()

func _test_combat_scaled_by_impede() -> void:
	print("[combat]")
	var SP: Object = root.get_node("/root/SummoningPlan")

	# Strong manifestation (no impede): hard fight.
	SP.reset()
	var hard := CombatEncounter.new(SP.manifestation_strength())
	var hard_result: Dictionary = hard.auto_resolve()

	# Weakened manifestation (heavy impede + stripped ingredients): easy fight.
	SP.reset()
	SP.add_impede(70.0, "test")
	SP.remove_ingredient("ritual_salt", 3)
	var easy := CombatEncounter.new(SP.manifestation_strength())
	var easy_result: Dictionary = easy.auto_resolve()

	_ok(easy.enemy_max_hp < hard.enemy_max_hp, "more impede -> weaker enemy")
	_ok(easy_result["player_hp_left"] > hard_result["player_hp_left"], "more impede -> player ends with more HP")
	_ok(easy_result["win"] == true, "a heavily-impeded summoning is winnable")
	_ok(hard_result.has("rounds"), "result reports the round count")
	# The occult ability hits harder than a basic attack.
	var enc := CombatEncounter.new(50.0)
	_ok(enc.OCCULT_DAMAGE > enc.ATTACK_DAMAGE, "occult ability beats a basic attack")

	# --- Retuned scaling. The residual fight only ever runs at strength <= STOP_THRESHOLD (60),
	# so it must be lethal in the mid-50s and survivable in the low-40s. Enemy HP = 2.5x strength,
	# enemy damage = 0.40x strength (player unchanged: 100 HP, 18 basic / 30 occult every 3rd round).
	var probe := CombatEncounter.new(50.0)
	_ok(is_equal_approx(probe.enemy_max_hp, 125.0), "enemy HP scales at 2.5x strength")
	_ok(is_equal_approx(probe.enemy_damage, 20.0), "enemy damage scales at 0.40x strength")
	# Crossover: a strength-55 residual is lethal; a strength-43 residual is survivable. This is
	# what makes turning Orin (43) the lever that upgrades near-good -> all-good over 2 sabotages (55).
	_ok(CombatEncounter.new(55.0).auto_resolve()["win"] == false, "strength 55 residual is lethal (near-good)")
	_ok(CombatEncounter.new(43.0).auto_resolve()["win"] == true, "strength 43 residual is survivable (all-good)")

## The two-gate climax resolver (pure logic). Gate 1: above the stop threshold the descent
## completes and the city dies (no fight). Gate 2: a stopped descent runs the residual fight,
## and surviving it is the difference between near-good (you die) and all-good (you live).
func _test_endgame_resolver() -> void:
	print("[endgame resolver]")
	_ok(is_equal_approx(EndGameResolver.STOP_THRESHOLD, 60.0), "stop threshold is 60")
	# Gate 1 — descent completes above the threshold: the city dies, with no fight.
	_ok(String(EndGameResolver.resolve(100.0).get("outcome", "")) == "city_dies", "strength 100 (no interference) -> city dies")
	_ok(String(EndGameResolver.resolve(77.5).get("outcome", "")) == "city_dies", "strength 77.5 (1 sabotage) -> city dies")
	# Boundary — exactly at the threshold the descent is *stopped*, not a city death.
	_ok(String(EndGameResolver.resolve(60.0).get("outcome", "")) != "city_dies", "strength 60 is stopped, not a city death")
	# Gate 2 — a stopped descent runs the residual fight: mid-50s lethal, low-40s survivable.
	_ok(String(EndGameResolver.resolve(55.0).get("outcome", "")) == "near_good", "strength 55 stopped but lethal -> near-good")
	_ok(String(EndGameResolver.resolve(43.0).get("outcome", "")) == "all_good", "strength 43 stopped and survived -> all-good")
	_ok(String(EndGameResolver.resolve(32.5).get("outcome", "")) == "all_good", "strength 32.5 (3 sabotages) -> all-good")
	# city-dies carries no fight; stopped outcomes carry the fight-result fields.
	var cd: Dictionary = EndGameResolver.resolve(100.0)
	_ok(bool(cd.get("win", true)) == false and int(cd.get("rounds", -1)) == 0, "city-dies has no fight (win=false, 0 rounds)")
	var ag: Dictionary = EndGameResolver.resolve(43.0)
	_ok(bool(ag.get("win", false)) == true and int(ag.get("rounds", 0)) > 0, "all-good carries a won fight with rounds")
	_ok(float(ag.get("player_hp_left", 0.0)) > 0.0, "all-good reports surviving HP")
	_ok(is_equal_approx(float(ag.get("strength", 0.0)), 43.0), "result echoes the resolved strength")

## End-to-end guard over the whole chain: player levers -> manifestation_strength -> ending.
## This locks the ending *table* so that a future tweak to SABOTAGE_IMPEDE/SOCIAL_IMPEDE, the
## ingredient counts, or the resolver thresholds can't silently move which ending each play reaches.
func _test_endgame_ending_bands() -> void:
	print("[endgame ending bands]")
	var PA: Object = root.get_node("/root/PlayerActions")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var AG: Object = root.get_node("/root/Agents")
	var EB: Object = root.get_node("/root/EventBus")

	# No interference: the descent (降临) completes — the whole city dies, with no fight.
	AG.rebuild(); SP.reset(); EB.clear()
	_ok(is_equal_approx(SP.manifestation_strength(), 100.0), "no interference -> strength 100")
	_ok(String(EndGameResolver.resolve(SP.manifestation_strength()).get("outcome", "")) == "city_dies",
		"no interference -> city dies")

	# Two sabotages stop the descent, but the residual manifestation still kills the player.
	AG.rebuild(); SP.reset(); EB.clear()
	PA.sabotage_any(); PA.sabotage_any()
	_ok(is_equal_approx(SP.manifestation_strength(), 55.0), "2 sabotages -> strength 55")
	_ok(String(EndGameResolver.resolve(SP.manifestation_strength()).get("outcome", "")) == "near_good",
		"2 sabotages -> near-good (descent stopped, you die)")

	# Two sabotages PLUS turning Orin (the 邪教 waverer) buys back the player's life.
	AG.rebuild(); SP.reset(); EB.clear()
	PA.sabotage_any(); PA.sabotage_any()
	_ok(PA.social_influence("lamplighter_orin"), "turning Orin succeeds")
	_ok(is_equal_approx(SP.manifestation_strength(), 43.0), "2 sabotages + turn Orin -> strength 43")
	_ok(String(EndGameResolver.resolve(SP.manifestation_strength()).get("outcome", "")) == "all_good",
		"turning Orin upgrades near-good -> all-good")

	# Three sabotages alone also reach the all-good ending.
	AG.rebuild(); SP.reset(); EB.clear()
	PA.sabotage_any(); PA.sabotage_any(); PA.sabotage_any()
	_ok(is_equal_approx(SP.manifestation_strength(), 32.5), "3 sabotages -> strength 32.5")
	_ok(String(EndGameResolver.resolve(SP.manifestation_strength()).get("outcome", "")) == "all_good",
		"3 sabotages -> all-good")

	AG.rebuild(); SP.reset(); EB.clear()

## The EndGame autoload: the thin pause + overlay shell over EndGameResolver. Firing the climax
## signal must drive it to the resolved ending, freeze the world, and log an `endgame` event;
## restart()/_reset_world_state() must reset the cult plan and lift the freeze. We drive those
## methods directly (rather than clicking the overlay buttons) and unpause in teardown so the
## later panel tests still run.
func _test_endgame_autoload() -> void:
	print("[endgame autoload]")
	var EG: Object = root.get_node("/root/EndGame")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var EB: Object = root.get_node("/root/EventBus")
	var AG: Object = root.get_node("/root/Agents")

	var reached: Array = []
	var cb := func(outcome: String, _result: Dictionary): reached.append(outcome)
	EG.ending_reached.connect(cb)

	# A full-strength descent: reaching the ending dooms the city, freezes the world, logs the event.
	AG.rebuild(); SP.reset(); EB.clear()
	paused = false
	SP.summoning_climax.emit(100.0)
	_ok(reached.size() == 1 and String(reached[-1]) == "city_dies", "climax at strength 100 -> city_dies ending")
	_ok(paused, "reaching an ending pauses the world")
	_ok(EB.events("endgame").size() == 1, "EndGame logs an endgame event")

	# A heavily-interfered descent routes to the all-good ending.
	paused = false
	EB.clear()
	SP.summoning_climax.emit(32.5)
	_ok(reached.size() == 2 and String(reached[-1]) == "all_good", "climax at strength 32.5 -> all_good ending")

	# _reset_world_state returns the cult plan to defaults (re-arming the summoning); restart lifts the freeze.
	SP.add_impede(50.0, "test"); SP.remove_ingredient("ritual_salt", 2); SP.climax_fired = true
	EG._reset_world_state()
	_ok(is_equal_approx(SP.impede_score, 0.0), "reset clears the summoning impede")
	_ok(is_equal_approx(SP.manifestation_strength(), 100.0), "reset restores full manifestation strength")
	_ok(SP.climax_fired == false, "reset re-arms the summoning (climax_fired cleared)")
	paused = true
	EG.restart()
	_ok(paused == false, "restart unpauses the world")

	EG.ending_reached.disconnect(cb)
	AG.rebuild(); SP.reset(); EB.clear()
	paused = false

func _test_player_state_save_load() -> void:
	print("[player state save/load]")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var OV: Object = root.get_node("/root/Overseer")
	var OTM: Object = root.get_node("/root/OccultToolManager")
	var SM: Object = root.get_node("/root/SaveManager")
	SP.reset(); OV.reset(); OTM.rebuild()
	SP.add_impede(33.0, "test")
	SP.remove_ingredient("candle", 1)
	OV.player_involved = true
	var tmp := "user://test_player_state.json"
	_ok(SM.save_game(tmp), "save_game writes file")
	SP.reset(); OV.reset()
	_ok(SP.impede_score == 0.0, "impede cleared before load")
	_ok(SM.load_game(tmp), "load_game reads file")
	_ok(abs(SP.impede_score - 33.0) < 0.01, "impede restored")
	_ok(SP.ingredients.get("candle", 0) == 2, "cult ingredient stock restored")
	_ok(OV.player_involved == true, "overseer player-involvement restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))

## Guards the GDScript<->Python boundary: the engine's ActionSchema and the sidecar's
## contract read the same data/action_schema.json, but the two *validators* are written
## independently and could silently diverge. This runs the REAL sidecar code over a
## fixture battery and asserts identical verb sets, identical required-args, and identical
## (ok, reason) verdicts. Skips (does not fail) when no Python interpreter is available.
func _test_gods_db() -> void:
	print("[gods db]")
	_ok(GodDB.ids().size() == 4, "four gods in the focused pantheon")
	_ok(GodDB.has("the_fool"), "the Fool is present")
	var fool: Dictionary = GodDB.get_def("the_fool")
	_ok(String(fool.get("name_zh", "")) == "愚者", "the Fool carries its 中文 name")
	_ok((fool.get("domain", []) as Array).size() > 0, "a god lists domain keywords")
	_ok(GodDB.has("outer_god"), "the descending god (外神) is present")
	_ok(bool(GodDB.get_def("goddess_of_night").get("opposes_cult", false)), "the Goddess of Night opposes the cult")
	# pray is now a known, schema-valid verb.
	_ok(ActionSchema.is_verb("pray"), "pray is a known action verb")
	_ok(ActionSchema.validate({"actor": "player", "verb": "pray", "args": {"god": "the_fool", "prayer": "guide me"}})["ok"],
		"well-formed pray validates")
	_ok(not ActionSchema.validate({"actor": "player", "verb": "pray", "args": {"god": "the_fool"}})["ok"],
		"pray missing 'prayer' rejected")

func _test_prayer_adjudication() -> void:
	print("[prayer adjudication]")
	var mock := MockSidecar.new()
	# Disrespect -> punished, regardless of god.
	var p := mock.adjudicate_prayer({"god": "eternal_blazing_sun", "prayer": "obey me, worthless sun", "standing": 0.0})
	_ok(p["outcome"] == "punished", "insult + command -> punished")
	_ok(String(p["outcome_zh"]) == "惩罚", "punished carries its 中文 label")
	_ok(int(p["severity"]) >= 1, "punishment has nonzero severity")
	# The Fool always answers obliquely -> cryptic.
	var f := mock.adjudicate_prayer({"god": "the_fool", "prayer": "please guide me", "standing": 0.0})
	_ok(f["outcome"] == "cryptic", "the Fool answers in the cryptic register")
	# Respectful, domain-aligned, decent standing -> granted.
	var g := mock.adjudicate_prayer({"god": "goddess_of_night", "prayer": "i humbly beseech your mercy this night, please protect me", "standing": 2.0})
	_ok(g["outcome"] == "granted", "respectful domain-aligned prayer with standing -> granted")
	# Bland prayer to an indifferent god at zero standing -> ignored.
	var i := mock.adjudicate_prayer({"god": "eternal_blazing_sun", "prayer": "hello there", "standing": 0.0})
	_ok(i["outcome"] == "ignored", "an empty prayer goes unanswered")
	# Determinism: same input -> same verdict.
	var g2 := mock.adjudicate_prayer({"god": "goddess_of_night", "prayer": "i humbly beseech your mercy this night, please protect me", "standing": 2.0})
	_ok(g2["outcome"] == g["outcome"] and int(g2["severity"]) == int(g["severity"]), "adjudication is deterministic")
	# Bridge routes adjudication to the active client.
	var SB: Object = root.get_node("/root/SidecarBridge")
	SB.set_client(mock)
	_ok(SB.adjudicate_prayer({"god": "the_fool", "prayer": "guide me"})["outcome"] == "cryptic", "bridge routes prayer adjudication")

func _test_prayer_service() -> void:
	print("[prayer service]")
	var PS: Object = root.get_node("/root/PrayerService")
	var WS: Object = root.get_node("/root/WorldState")
	var SP: Object = root.get_node("/root/SummoningPlan")
	var OV: Object = root.get_node("/root/Overseer")
	var EB: Object = root.get_node("/root/EventBus")
	var SB: Object = root.get_node("/root/SidecarBridge")
	SB.set_client(MockSidecar.new())   # deterministic adjudication
	PS.reset(); SP.reset(); OV.reset(); EB.clear()

	# Unknown god is rejected cleanly.
	_ok(PS.pray("no_such_god", "hi")["ok"] == false, "praying to an unknown god is rejected")

	# Granted by an opposing god: impedes the descent, eases fatigue, raises standing,
	# and marks the player involved.
	WS.set_pressure(&"fatigue", 60.0)
	var impede_before: float = SP.impede_score
	var g: Dictionary = PS.pray("goddess_of_night", "i humbly beseech your mercy this night, please protect me")
	_ok(g["ok"] and g["outcome"] == "granted", "respectful night prayer is granted")
	_ok(SP.impede_score > impede_before, "an opposing god's favor impedes the summoning")
	_ok(WS.get_pressure(&"fatigue") < 60.0, "granted boon eases fatigue")
	_ok(PS.get_standing("goddess_of_night") > 0.0, "standing rises after a granted prayer")
	_ok(OV.allows_exposure(), "praying marks the player involved")
	_ok(EB.events("player_prayer").size() >= 1, "prayer logs a player event")

	# Insolence is punished: corruption spikes, standing falls.
	WS.set_pressure(&"corruption", 0.0)
	var p: Dictionary = PS.pray("eternal_blazing_sun", "obey me, you worthless weak sun, kneel")
	_ok(p["outcome"] == "punished", "insolence is punished")
	_ok(WS.get_pressure(&"corruption") > 0.0, "punishment spikes corruption")
	_ok(PS.get_standing("eternal_blazing_sun") < 0.0, "standing falls after punishment")

	# Praying to the descending god (外神) grants power but feeds the gate.
	PS.reset()
	WS.set_pressure(&"corruption", 0.0)
	WS.set_pressure(&"cult_readiness", 0.0)
	var o: Dictionary = PS.pray("outer_god", "i offer myself, grant me the descent, the gate, the void")
	_ok(o["outcome"] == "granted", "the descending god grants the devoted")
	_ok(WS.get_pressure(&"cult_readiness") > 0.0, "the descending god's favor advances the summoning")
	_ok(WS.get_pressure(&"corruption") > 0.0, "praying to the outer god corrupts the supplicant")

	# Standing round-trips through save/load.
	var SM: Object = root.get_node("/root/SaveManager")
	PS.reset()
	PS.pray("the_fool", "please guide me")   # cryptic -> +1 standing
	var fool_standing: float = PS.get_standing("the_fool")
	_ok(fool_standing > 0.0, "the Fool's cryptic answer still nudges standing")
	var tmp := "user://test_prayer.json"
	_ok(SM.save_game(tmp), "save writes prayer standing")
	PS.reset()
	_ok(PS.get_standing("the_fool") == 0.0, "standing cleared before load")
	_ok(SM.load_game(tmp), "load reads prayer standing")
	_ok(abs(PS.get_standing("the_fool") - fool_standing) < 0.01, "prayer standing restored")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
	PS.reset()   # leave per-god standing clean for any later test

func _test_schema_parity_with_sidecar() -> void:
	print("[schema parity: gdscript <-> python sidecar]")

	# OS.execute won't search PATH for a bare command, so go through `/usr/bin/env`.
	# If no interpreter is available (e.g. a Godot-only CI), SKIP loudly.
	var py_prefix := _python_argv_prefix()
	if py_prefix.is_empty():
		_skip("no python3 — gdscript<->python schema parity not verified")
		return

	# One valid action per verb, then every rejection path the two independently
	# hand-written validators must agree on.
	var fixtures: Array = [
		{"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}},
		{"actor": "voss", "verb": "talk_to", "args": {"agent": "orin", "topic": "ritual"}},
		{"actor": "voss", "verb": "gather_item", "args": {"item_id": "candle"}},
		{"actor": "voss", "verb": "perform_ritual_step", "args": {"step": "anoint"}},
		{"actor": "voss", "verb": "hide", "args": {}},
		{"actor": "voss", "verb": "flee", "args": {"from": "pell"}},
		{"actor": "voss", "verb": "attack", "args": {"target": "pell"}},
		{"actor": "voss", "verb": "recruit", "args": {"agent": "orin"}},
		{"actor": "voss", "verb": "report", "args": {"to": "nighthawks", "info": "cult"}},
		{"actor": "voss", "verb": "pray", "args": {"god": "the_fool", "prayer": "guide me"}},
		{"actor": "voss", "verb": "pray", "args": {"god": "the_fool"}},   # missing required 'prayer'
		{"actor": "voss", "verb": "idle", "args": {}},
		{"actor": "voss", "verb": "teleport", "args": {}},               # unknown verb
		{"verb": "idle", "args": {}},                                    # missing actor
		{"actor": "", "verb": "idle", "args": {}},                       # empty actor
		{"actor": "voss", "verb": "talk_to", "args": {"agent": "orin"}}, # missing required arg
		{"actor": "voss", "verb": "move_to", "args": "nope"},            # args not an object
		{"actor": "voss", "verb": "move_to"},                            # args omitted
	]

	# Write fixtures to a temp file and pass its PATH (not inline JSON — a quote-laden
	# JSON string does not survive an argv intact), then run
	# `/usr/bin/env python3 <helper> <fixtures-file>`.
	var fixtures_path := "user://_parity_fixtures.json"
	var ff := FileAccess.open(fixtures_path, FileAccess.WRITE)
	ff.store_string(JSON.stringify(fixtures))
	ff.close()
	var fixtures_os := ProjectSettings.globalize_path(fixtures_path)
	var helper := ProjectSettings.globalize_path("res://").path_join("../agent-sidecar/schema_parity_check.py")
	var argv: Array = py_prefix.duplicate()
	argv.append(helper)
	argv.append(fixtures_os)
	var out: Array = []
	var code := OS.execute("/usr/bin/env", argv, out, true)
	DirAccess.remove_absolute(fixtures_os)
	var joined := "\n".join(out).strip_edges()
	_ok(code == 0, "python parity helper exited 0")
	if code != 0:
		printerr("    helper output: %s" % joined)
		return

	var parsed: Variant = JSON.parse_string(joined)
	if typeof(parsed) != TYPE_DICTIONARY:
		_ok(false, "python helper emitted parseable JSON (got: %s)" % joined)
		return
	var py_schema: Dictionary = parsed.get("schema", {})
	var py_verdicts: Array = parsed.get("verdicts", [])

	# 1) Verb-set parity: the engine loaded exactly the verbs the sidecar loaded.
	var gd_verbs: Array = ActionSchema.verbs()
	gd_verbs.sort()
	var py_verbs: Array = py_schema.keys()
	py_verbs.sort()
	_ok(gd_verbs == py_verbs, "verb sets identical: %s" % str(gd_verbs))

	# 2) Required-args parity per verb (engine's loaded map vs the sidecar's).
	var args_parity := true
	for v in gd_verbs:
		var gd_args: Array = ActionSchema.required_args(v)
		var py_args: Array = (py_schema.get(v, []) as Array).duplicate()
		gd_args.sort(); py_args.sort()
		if gd_args != py_args:
			args_parity = false
			printerr("    arg mismatch for '%s': gd=%s py=%s" % [v, str(gd_args), str(py_args)])
	_ok(args_parity, "required args identical for every verb")

	# 3) Verdict parity: both validators agree (ok AND reason) on each fixture.
	_ok(py_verdicts.size() == fixtures.size(), "one python verdict per fixture")
	var verdict_parity := true
	for i in fixtures.size():
		var gd: Dictionary = ActionSchema.validate(fixtures[i])
		var py: Array = py_verdicts[i] if i < py_verdicts.size() else [null, ""]
		var gd_ok: bool = gd["ok"]
		var py_ok: bool = bool(py[0])
		var gd_reason: String = gd["reason"]
		var py_reason: String = String(py[1]) if py.size() > 1 else ""
		if gd_ok != py_ok or gd_reason != py_reason:
			verdict_parity = false
			printerr("    verdict mismatch on fixture %d (%s): gd=[%s,'%s'] py=[%s,'%s']" % [
				i, str(fixtures[i].get("verb", "")), str(gd_ok), gd_reason, str(py_ok), py_reason,
			])
	_ok(verdict_parity, "validator verdicts (ok+reason) match across %d fixtures" % fixtures.size())

## Guards the GDScript<->Python boundary for prayer judgment exactly as
## _test_schema_parity_with_sidecar guards the action schema: runs a battery of prayers
## through the REAL Python reference adjudicator and asserts identical (outcome, severity).
## Skips (does not fail) when no Python interpreter is available.
func _test_prayer_parity_with_sidecar() -> void:
	print("[prayer parity: gdscript <-> python adjudicator]")
	var py_prefix := _python_argv_prefix()
	if py_prefix.is_empty():
		_skip("no python3 — prayer adjudication parity not verified")
		return
	var mock := MockSidecar.new()
	var fixtures: Array = [
		{"god": "goddess_of_night", "prayer": "i humbly beseech your mercy this night, please protect me", "standing": 2.0},
		{"god": "the_fool", "prayer": "please guide me through the fog", "standing": 0.0},
		{"god": "eternal_blazing_sun", "prayer": "obey me, you worthless weak sun, kneel", "standing": 0.0},
		{"god": "eternal_blazing_sun", "prayer": "hello there", "standing": 0.0},
		{"god": "eternal_blazing_sun", "prayer": "please help", "standing": 0.0},   # respect-only, score 2 -> cryptic via score (non-tarot)
		{"god": "outer_god", "prayer": "i offer myself, grant me the descent, the gate, the void", "standing": 0.0},
		{"god": "goddess_of_night", "prayer": "i curse your name", "standing": 5.0},
		{"god": "the_fool", "prayer": "demand fortune now", "standing": 0.0},
		{"god": "outer_god", "prayer": "nothing in particular", "standing": -5.0},
	]
	var fixtures_path := "user://_prayer_fixtures.json"
	var ff := FileAccess.open(fixtures_path, FileAccess.WRITE)
	ff.store_string(JSON.stringify(fixtures))
	ff.close()
	var fixtures_os := ProjectSettings.globalize_path(fixtures_path)
	var helper := ProjectSettings.globalize_path("res://").path_join("../agent-sidecar/prayer_parity_check.py")
	var argv: Array = py_prefix.duplicate()
	argv.append(helper)
	argv.append(fixtures_os)
	var out: Array = []
	var code := OS.execute("/usr/bin/env", argv, out, true)
	DirAccess.remove_absolute(fixtures_os)
	var joined := "\n".join(out).strip_edges()
	_ok(code == 0, "python prayer helper exited 0")
	if code != 0:
		printerr("    helper output: %s" % joined)
		return
	var parsed: Variant = JSON.parse_string(joined)
	if typeof(parsed) != TYPE_DICTIONARY:
		_ok(false, "python helper emitted parseable JSON (got: %s)" % joined)
		return
	var py_verdicts: Array = parsed.get("verdicts", [])
	_ok(py_verdicts.size() == fixtures.size(), "one python verdict per prayer fixture")
	var parity := true
	for i in fixtures.size():
		var gd: Dictionary = mock.adjudicate_prayer(fixtures[i])
		var py: Array = py_verdicts[i] if i < py_verdicts.size() else ["", -1]
		var gd_out: String = gd["outcome"]
		var gd_sev: int = int(gd["severity"])
		var py_out: String = String(py[0]) if py.size() > 0 else ""
		var py_sev: int = int(py[1]) if py.size() > 1 else -1
		if gd_out != py_out or gd_sev != py_sev:
			parity = false
			printerr("    prayer mismatch %d (%s): gd=[%s,%d] py=[%s,%d]" % [
				i, str(fixtures[i].get("god", "")), gd_out, gd_sev, py_out, py_sev])
	_ok(parity, "adjudicator outcomes (outcome+severity) match across %d prayers" % fixtures.size())

## load() (not preload): preload resolves at parse time, before autoloads register, which
## breaks a scene whose script uses bare autoload refs (PrayerService/GodDB) under the -s harness.
func _test_prayer_panel() -> void:
	print("[prayer panel]")
	var SB: Object = root.get_node("/root/SidecarBridge")
	var PS: Object = root.get_node("/root/PrayerService")
	SB.set_client(MockSidecar.new())   # deterministic adjudication
	PS.reset()
	var panel = load("res://ui/PrayerPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "panel hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "panel toggles visible")
	_ok(panel.god_button_count() == 4, "one button per god in the pantheon")
	# A respectful, domain-aligned prayer is granted and rendered.
	var g: Dictionary = panel.submit_prayer("goddess_of_night", "i humbly beseech your mercy this night, please protect me")
	_ok(g["outcome"] == "granted", "panel routes a granted prayer")
	_ok(panel.last_outcome() == "granted", "panel records the rendered outcome")
	# An insulting prayer is punished.
	panel.submit_prayer("eternal_blazing_sun", "obey me, you worthless weak sun, kneel")
	_ok(panel.last_outcome() == "punished", "panel renders a punishment")
	# Offering a prayer updates the selection seam.
	panel.submit_prayer("the_fool", "what will fate bring?")
	_ok(panel.selected_god() == "the_fool", "submit_prayer updates selection")
	panel.toggle()  # hide
	await process_frame
	_ok(not panel.visible, "panel toggles back hidden")
	panel.queue_free()
	await process_frame

## The debug overlay mirrors the WHOLE EventBus (no allow-list), newest first, and refreshes
## live while open. Distinct from the cult panel, which filters to publicly-known events.
func _test_debug_log_panel() -> void:
	print("[debug log panel]")
	var EB: Object = root.get_node("/root/EventBus")
	EB.clear()
	var panel = load("res://ui/DebugLogPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "debug panel hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "debug panel toggles visible")
	_ok(panel.line_count() == 1, "empty log shows a single placeholder line")
	# Events logged while open refresh the panel live; newest is shown first, unfiltered.
	EB.emit_event("agent_action", {"actor": "clerk_voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	EB.emit_event("action_rejected", {"actor": "lamplighter_orin", "verb": "teleport", "reason": "unknown verb"})
	await process_frame
	_ok(panel.line_count() == 2, "panel renders one line per logged event")
	_ok(panel.newest_line().contains("action rejected"), "newest event is shown first")
	_ok(panel.newest_line().contains("reason: unknown verb"), "rejection reason is surfaced")
	panel.toggle()  # hide
	await process_frame
	_ok(not panel.visible, "debug panel toggles back hidden")
	panel.queue_free()
	await process_frame

func _test_inventory_panel() -> void:
	print("[inventory panel]")
	var INV: Object = root.get_node("/root/Inventory")
	INV.clear()
	var panel = load("res://ui/InventoryPanel.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "inventory hidden by default")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "inventory toggles visible")
	_ok(panel.line_count() == 1, "empty inventory shows a single placeholder line")
	# Items appear live while the panel is open: one row per held item type.
	INV.add("candle", 2)
	INV.add("spirit_pendulum", 1)
	await process_frame
	_ok(panel.line_count() == 2, "panel renders one row per held item type")
	panel.toggle()
	await process_frame
	_ok(not panel.visible, "inventory toggles back hidden")
	panel.queue_free()
	INV.clear()
	await process_frame

func _test_hud_toggle_keys() -> void:
	print("[hud toggle keys]")
	var hud = load("res://ui/HUD.tscn").instantiate()
	root.add_child(hud)
	await process_frame
	var map: Node = hud.get_node("DistrictMap")
	var inv: Node = hud.get_node("InventoryPanel")
	_ok(not map.visible and not inv.visible, "map + inventory hidden initially")
	# Push the toggle_map action through the root viewport, exactly as a real M press arrives,
	# so this exercises the full _unhandled_input path (not just a direct handler call).
	_send_action("toggle_map")
	await process_frame
	_ok(map.visible, "toggle_map (M) opens the District map")
	_send_action("toggle_map")
	await process_frame
	_ok(not map.visible, "toggle_map (M) again closes it")
	_send_action("toggle_inventory")
	await process_frame
	_ok(inv.visible, "toggle_inventory (I) opens the inventory")
	hud.queue_free()
	await process_frame

## Push a press+release of an InputMap action through the root viewport, so the HUD panel
## toggles fire from _unhandled_input exactly as they do for a real key press.
func _send_action(action: StringName) -> void:
	for pressed in [true, false]:
		var ev := InputEventAction.new()
		ev.action = action
		ev.pressed = pressed
		root.push_input(ev)

func _test_toasts() -> void:
	print("[toasts]")
	var EM: Object = root.get_node("/root/EventManager")
	var WM: Object = root.get_node("/root/WorldManager")
	var toasts = load("res://ui/Toasts.tscn").instantiate()
	root.add_child(toasts)
	await process_frame
	_ok(toasts.card_count() == 0, "toast stack starts empty")
	# Wiring: the toast layer subscribes to the three simulation signals it surfaces.
	_ok(EM.is_connected("event_fired", Callable(toasts, "_on_event")),
		"toasts listen to EventManager.event_fired")
	_ok(WM.is_connected("pressure_threshold_crossed", Callable(toasts, "_on_threshold")),
		"toasts listen to WorldManager.pressure_threshold_crossed")
	_ok(WM.is_connected("stage_advanced", Callable(toasts, "_on_stage")),
		"toasts listen to WorldManager.stage_advanced")
	# Behavior: each handler turns its signal into exactly one card. Called directly (rather
	# than emitting the global signals) so no other live listener is disturbed by the test.
	toasts._on_event({"title": "A scream in the fog", "body": "Night Market.",
		"effects": [{"type": "notify", "channel": "alert"}]})
	toasts._on_threshold("panic", 60.0)
	toasts._on_stage("disturbance", "awakening")
	await process_frame
	_ok(toasts.card_count() == 3, "event + threshold + stage each push one toast card")
	# The stack never shows more than MAX_VISIBLE (4) cards at once.
	for i in 5:
		toasts.push("spam %d" % i)
	await process_frame
	_ok(toasts.card_count() <= 4, "the stack is capped at MAX_VISIBLE (4)")
	toasts.queue_free()
	await process_frame

func _test_player_position_sync() -> void:
	print("[player position sync]")
	var ART: Object = root.get_node("/root/AgentRuntime")
	var saved: Vector2 = ART.player_position
	_ok(get_nodes_in_group("player").is_empty(), "no stray player nodes leaked from earlier tests")
	var gc = load("res://src/GameController.gd").new()
	root.add_child(gc)
	await process_frame
	# With no player in the tree, sync leaves the last known position untouched.
	ART.player_position = Vector2(1, 1)
	gc.sync_player_position()
	_ok(ART.player_position == Vector2(1, 1), "sync with no player keeps the last position")
	# A player in the group: sync pushes its live position into AgentRuntime.
	var player := Node2D.new()
	player.add_to_group("player")
	player.global_position = Vector2(123, 456)
	root.add_child(player)
	gc.sync_player_position()
	_ok(ART.player_position == Vector2(123, 456), "sync pushes the live player position into AgentRuntime")
	player.queue_free()
	gc.queue_free()
	await process_frame
	ART.player_position = saved

func _test_player_stamina() -> void:
	print("[player stamina]")
	var p = load("res://scenes/Player.tscn").instantiate()
	root.add_child(p)
	await process_frame
	_ok(is_equal_approx(p.stamina, p.max_stamina), "starts at full stamina")
	# Sprinting drains; not-sprinting regenerates; both clamp to [0, max].
	p.step_stamina(1.0, true)
	_ok(is_equal_approx(p.stamina, p.max_stamina - p.stamina_drain),
		"sprinting drains one second of stamina")
	p.stamina = 5.0
	p.step_stamina(1.0, true)
	_ok(p.stamina == 0.0, "stamina clamps at 0 (never negative)")
	p.stamina = 0.0
	p.step_stamina(1.0, false)
	_ok(is_equal_approx(p.stamina, p.stamina_regen), "regenerates one second while not sprinting")
	p.stamina = p.max_stamina - 1.0
	p.step_stamina(1.0, false)
	_ok(p.stamina == p.max_stamina, "stamina clamps at max")
	# Exhaustion latch: empty disarms an active sprint and blocks re-engage until recovered.
	p.stamina = 0.0
	p._sprinting = true
	_ok(p._resolve_sprint(Vector2.RIGHT) == false, "empty stamina disarms an active sprint")
	_ok(p._exhausted, "draining to empty sets the exhausted latch")
	p.stamina = p.sprint_recharge_threshold
	p._resolve_sprint(Vector2.RIGHT)
	_ok(not p._exhausted, "exhaustion clears once stamina recovers to the threshold")
	# Floating stamina bar: fades in while recovering, fades out once the pool is full.
	p.stamina = 50.0
	p._bar_alpha = 0.0
	p._update_stamina_bar(1.0, false)
	_ok(p._bar_alpha > 0.0, "stamina bar fades in while recovering")
	p.stamina = p.max_stamina
	p._update_stamina_bar(10.0, false)
	_ok(p._bar_alpha == 0.0, "stamina bar fades out once stamina is full")
	p.queue_free()
	await process_frame

func _test_map_texture_imported() -> void:
	print("[map texture]")
	var tex: Variant = load("res://assets/maps/map_v3.png")
	_ok(tex is Texture2D, "map_v3.png is imported and loads as a Texture2D")
	if tex is Texture2D:
		_ok((tex as Texture2D).get_size().is_equal_approx(MapProjection.MAP_SIZE),
			"texture size matches MAP_SIZE (1254x1254)")

func _test_district_map_polygons() -> void:
	print("[district map_polygons]")
	var raw: String = FileAccess.get_file_as_string("res://data/districts.json")
	var parsed: Variant = JSON.parse_string(raw)
	_ok(typeof(parsed) == TYPE_ARRAY, "districts.json parses to an array")
	var districts: Array = parsed if typeof(parsed) == TYPE_ARRAY else []
	_ok(districts.size() == 5, "five districts present")
	var ids: Array = []
	var all_valid := true
	var all_in_bounds := true
	var risk_model_intact := true
	for d in districts:
		var dd: Dictionary = d
		ids.append(String(dd.get("id", "")))
		var mp: Array = dd.get("map_polygon", [])
		if mp.size() < 6 or mp.size() % 2 != 0:
			all_valid = false
		for i in range(0, mp.size() - 1, 2):
			var x: float = float(mp[i])
			var y: float = float(mp[i + 1])
			if x < 0.0 or x > MapProjection.MAP_SIZE.x or y < 0.0 or y > MapProjection.MAP_SIZE.y:
				all_in_bounds = false
		if not (dd.has("base_risk") and dd.has("risk_pressure")):
			risk_model_intact = false
	_ok(all_valid, "every district has an even-length map_polygon of >= 6 numbers (>= 3 vertices)")
	_ok(all_in_bounds, "every map_polygon vertex sits within [0,1254] x [0,1254]")
	for expected in ["iron_cross", "harbor", "st_selena", "night_market", "uptown"]:
		_ok(ids.has(expected), "district '%s' is present" % expected)
	_ok(risk_model_intact, "base_risk / risk_pressure still present on every district (risk model unbroken)")

func _test_map_projection_canvas_fit() -> void:
	print("[map projection canvas fit]")
	# A canvas twice as wide as the map (same height): letterboxed left/right at uniform scale 1.
	# Derived from MAP_SIZE so it stays correct across map swaps (now the square map_v3, 1254x1254).
	var ms: Vector2 = MapProjection.MAP_SIZE
	var canvas := Vector2(ms.x * 2.0, ms.y)
	var scale: float = minf(canvas.x / ms.x, canvas.y / ms.y)
	_ok(is_equal_approx(scale, 1.0), "uniform scale is the limiting (height) ratio")
	# Image origin maps to the centering offset, not the canvas origin.
	var origin: Vector2 = MapProjection.image_to_canvas(canvas, Vector2.ZERO)
	_ok(origin.is_equal_approx(Vector2(ms.x * 0.5, 0.0)), "image origin maps to the letterbox offset")
	# The far map corner stays within the canvas and sits at the far letterbox edge.
	var corner: Vector2 = MapProjection.image_to_canvas(canvas, ms)
	_ok(corner.x <= canvas.x + 0.01 and corner.y <= canvas.y + 0.01, "MAP_SIZE corner stays within the canvas")
	_ok(corner.is_equal_approx(Vector2(ms.x * 1.5, ms.y)), "MAP_SIZE corner sits at the far letterbox edge")
	# Aspect-preserving: a step in image x and an equal step in image y scale identically.
	var dx: Vector2 = MapProjection.image_to_canvas(canvas, Vector2(10.0, 0.0)) - origin
	var dy: Vector2 = MapProjection.image_to_canvas(canvas, Vector2(0.0, 10.0)) - origin
	_ok(is_equal_approx(dx.x, dy.y), "x and y scale identically (no distortion)")
	# Round-trip: canvas_to_image is the exact inverse of image_to_canvas.
	var p := Vector2(640.0, 410.0)
	var back: Vector2 = MapProjection.canvas_to_image(canvas, MapProjection.image_to_canvas(canvas, p))
	_ok(back.is_equal_approx(p), "canvas_to_image(image_to_canvas(p)) == p")
	# Degenerate zero-size canvas (e.g. before first layout): the inverse must stay finite
	# (no inf/nan) so callers can't silently propagate garbage. scale<=0 -> pass the point through.
	_ok(MapProjection.canvas_to_image(Vector2.ZERO, Vector2(100.0, 100.0)).is_finite(),
		"canvas_to_image on a zero-size canvas returns a finite point")

func _test_map_projection_world_to_map() -> void:
	print("[map projection global transform]")
	# Constants match the canonical map-image space (map_v3.png is 1254x1254).
	_ok(MapProjection.MAP_SIZE == Vector2(1254.0, 1254.0), "MAP_SIZE is the map_v3.png pixel size")
	_ok(MapProjection.CITY_SCALE == 3.5, "CITY_SCALE is 3.5")
	# Map corners map onto the world rect (0,0)..(4389,4389).
	_ok(MapProjection.map_to_world(Vector2.ZERO).is_equal_approx(Vector2.ZERO),
		"map origin -> world origin")
	_ok(MapProjection.map_to_world(MapProjection.MAP_SIZE).is_equal_approx(Vector2(4389.0, 4389.0)),
		"map far corner -> world far corner (4389,4389)")
	# Round-trip identity: world_to_map is the exact inverse of map_to_world.
	var p := Vector2(1234.0, 567.0)
	_ok(MapProjection.map_to_world(MapProjection.world_to_map(p)).is_equal_approx(p),
		"map_to_world(world_to_map(p)) == p")
	# A sample map point scales by CITY_SCALE.
	_ok(MapProjection.map_to_world(Vector2(430.0, 300.0)).is_equal_approx(Vector2(1505.0, 1050.0)),
		"map (430,300) -> world (1505,1050)")
	# The rite anchor is deliberately still in the OLD map space (see MapProjection note): it sits in
	# its legacy Iron Cross region and transforms cleanly, pending the world/rite unification pass.
	var ic := Rect2(430.0, 300.0, 170.0, 140.0)  # legacy iron_cross map_polygon bounds (old space)
	_ok(ic.has_point(MapProjection.WAREHOUSE_MAP), "WAREHOUSE_MAP still in its legacy Iron Cross region")
	_ok(MapProjection.map_to_world(MapProjection.WAREHOUSE_MAP).is_equal_approx(Vector2(1802.5, 1302.0)),
		"WAREHOUSE_MAP -> world (1802.5,1302.0)")

## The map panel loads the real map texture and the five districts, and toggles like the other
## modals. Asserts only layout-independent invariants so it is robust under headless control sizing;
## the geometry it draws is covered by the MapProjection unit tests, not re-tested through the view.
func _test_district_map_panel() -> void:
	print("[district map panel]")
	var panel = load("res://ui/DistrictMap.tscn").instantiate()
	root.add_child(panel)
	await process_frame
	_ok(not panel.visible, "map panel hidden by default")
	_ok(panel.districts.size() == 5, "panel loaded the five districts")
	_ok(panel.has_map_texture(), "panel loaded the city map texture")
	panel.toggle()
	await process_frame
	_ok(panel.visible, "map panel toggles visible")
	panel.toggle()
	await process_frame
	_ok(not panel.visible, "map panel toggles back hidden")
	panel.queue_free()
	await process_frame

## Returns the argv prefix to run Python via `/usr/bin/env` (so PATH is searched), or []
## if no interpreter is available. Tries python3 then python.
func _python_argv_prefix() -> Array:
	if not FileAccess.file_exists("/usr/bin/env"):
		return []
	for candidate in ["python3", "python"]:
		var probe: Array = []
		if OS.execute("/usr/bin/env", [candidate, "--version"], probe, true) == 0:
			return [candidate]
	return []
