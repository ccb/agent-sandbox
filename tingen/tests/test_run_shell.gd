extends SceneTree
## Headless harness for the M2 run shell (RunManager autoload + run lifecycle).
## Run:  <godot> --headless --path tingen -s tests/test_run_shell.gd
##
## Pins the run/meta contract:
##   (a) project.godot main_scene is Main.tscn (boot controller), not City.tscn.
##   (b) the RunManager autoload is registered and reachable at /root/RunManager.
##   (c) start_run() sets day 1 / morning and RESETS a dirtied WorldState/ClueDB/pressure
##       back to run-start values.
##   (d) advancing the Clock rolls days; checkpoint_night() snapshots.
##   (e) THE LEAK TEST (GAP-2.9): dirty the world hard, end_run + restart, assert everything
##       is back byte-identical to a fresh run.
##   (f) meta (runs_played) SURVIVES a restart while run state resets.
##   (g) end_run("death") after a nightly checkpoint restores to that checkpoint (costs the
##       day), NOT a full wipe.

var _passed := 0
var _failed := 0

# Autoloads are resolved by /root lookup (the `_al` pattern) — under the `-s` SceneTree harness
# the autoload GLOBALS (WorldState, Clock, ...) are not visible as identifiers.
var WorldState: Node
var Clock: Node
var ClueDB: Node
var SummoningPlan: Node
var Agents: Node
var EventBus: Node
var Inventory: Node
var PrayerService: Node
var DeedRunner: Node
var RoomItems: Node
var EventManager: Node

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()

	WorldState = root.get_node("/root/WorldState")
	Clock = root.get_node("/root/Clock")
	ClueDB = root.get_node("/root/ClueDB")
	SummoningPlan = root.get_node("/root/SummoningPlan")
	Agents = root.get_node("/root/Agents")
	EventBus = root.get_node("/root/EventBus")
	Inventory = root.get_node("/root/Inventory")
	PrayerService = root.get_node("/root/PrayerService")
	DeedRunner = root.get_node("/root/DeedRunner")
	RoomItems = root.get_node("/root/RoomItems")
	EventManager = root.get_node("/root/EventManager")

	var RM: Object = root.get_node_or_null("/root/RunManager")
	_ok(RM != null, "RunManager autoload is registered (/root/RunManager)")
	if RM == null:
		print("\n=== %d passed, %d failed ===" % [_passed, _failed])
		quit(1)
		return

	_test_main_scene_is_boot()
	_test_start_run_resets_and_seeds(RM)
	_test_calendar_rolls_days(RM)
	_test_checkpoint_night(RM)
	_test_leak_on_restart(RM)
	_test_meta_survives_restart(RM)
	_test_death_restores_checkpoint(RM)

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

# (a) The game must boot through the boot controller, not straight into the dev City scene.
func _test_main_scene_is_boot() -> void:
	var cfg: String = String(ProjectSettings.get_setting("application/run/main_scene", ""))
	_ok(cfg == "res://scenes/Main.tscn",
		"project.godot main_scene is Main.tscn (got '%s')" % cfg)

# (c) A fresh run resets a dirtied world and stamps day 1 / morning.
func _test_start_run_resets_and_seeds(RM: Object) -> void:
	# Dirty the world first.
	WorldState.set_pressure(&"corruption", 88.0)
	WorldState.set_lead("garbage lead")
	ClueDB.collect("antigonus_notebook")
	SummoningPlan.impede_score = 42.0
	Clock.set_time(4, 900)

	RM.start_run()

	_ok(RM.current_day() == 1, "start_run -> current_day() == 1 (got %d)" % RM.current_day())
	_ok(RM.current_phase() == "morning",
		"start_run -> current_phase() == morning (got '%s')" % RM.current_phase())
	_ok(is_equal_approx(WorldState.corruption, 5.0),
		"start_run resets corruption to run-start 5 (got %.1f)" % WorldState.corruption)
	_ok(ClueDB.collected_count() == 0,
		"start_run clears collected clues (got %d)" % ClueDB.collected_count())
	_ok(is_equal_approx(SummoningPlan.impede_score, 0.0),
		"start_run resets SummoningPlan.impede_score (got %.1f)" % SummoningPlan.impede_score)
	_ok(SummoningPlan.countdown_beats == SummoningPlan.START_COUNTDOWN,
		"start_run resets the summoning countdown")

# (b/d) ~7-day calendar over the existing Clock phases; a Clock day boundary rolls the run day.
func _test_calendar_rolls_days(RM: Object) -> void:
	RM.start_run()
	_ok(RM.current_day() == 1, "calendar starts on day 1")
	# Cross one Clock day boundary.
	Clock.set_time(1, Clock.DAY_MINUTES - 1)
	Clock.advance_minutes(2)
	_ok(RM.current_day() == 2, "crossing the Clock day boundary rolls to day 2 (got %d)" % RM.current_day())
	_ok(RM.total_days() >= 7, "the run calendar is ~7 in-game days (got %d)" % RM.total_days())

# (d) checkpoint_night snapshots the current run state.
func _test_checkpoint_night(RM: Object) -> void:
	RM.start_run()
	Clock.set_time(2, 480)
	WorldState.set_pressure(&"panic", 33.0)
	RM.checkpoint_night()
	_ok(RM.has_checkpoint(), "checkpoint_night() records a checkpoint")
	_ok(RM.checkpoint_day() == 2, "checkpoint is stamped with the current day (got %d)" % RM.checkpoint_day())

# (e) THE LEAK TEST — GAP-2.9. Dirty everything, end_run + restart, assert run-start clean.
func _test_leak_on_restart(RM: Object) -> void:
	RM.start_run()
	# Dirty a broad cross-section of the run world.
	Agents.rebuild()
	var before_agents: int = Agents.all().size()
	WorldState.set_pressure(&"corruption", 77.0)
	WorldState.set_pressure(&"cult_readiness", 55.0)
	ClueDB.collect("antigonus_notebook")
	ClueDB.collect("spent_revolver")
	SummoningPlan.add_impede(30.0)
	SummoningPlan.advance_rite(5)
	Clock.set_time(5, 1000)
	EventBus.emit_event("player_test_noise", {"actor": "player"})
	# Dirty EVERY remaining run-scoped singleton in SaveManager's manifest plus the CombatExecutor
	# static ledger — these are the leaks the original test never probed (findings 1-5, GAP-2.9).
	Inventory.add("spirit_pendulum", 1)
	PrayerService.standing["ossric"] = 44.0
	DeedRunner._fired["some_deed"] = 3
	RoomItems.place("city", "candle", Vector2(10, 10), 1)
	EventManager._cooldowns["some_event"] = 999
	CombatExecutor._last_attacker["victim_x"] = "attacker_y"

	# End the run on day 1 pre-checkpoint (no checkpoint) -> full restart.
	RM.end_run("death")   # day 5 but no checkpoint recorded this run -> restart to run-start
	RM.start_run()

	# --- Every singleton SaveManager persists must be reset by the run-reset seam (finding 6): the
	# reset path must cover the whole save manifest, not just the subset it happened to handle. ---
	_ok(Inventory.count_of("spirit_pendulum") == 0,
		"LEAK: inventory cleared after restart (got %d)" % Inventory.count_of("spirit_pendulum"))
	_ok(PrayerService.get_standing("ossric") == 0.0,
		"LEAK: prayer standing reset after restart (got %.1f)" % PrayerService.get_standing("ossric"))
	_ok(int(DeedRunner._fired.get("some_deed", -1)) == -1,
		"LEAK: deed latches cleared after restart")
	_ok(RoomItems.count("city") == 0,
		"LEAK: ground items cleared after restart (got %d)" % RoomItems.count("city"))
	_ok(int(EventManager._cooldowns.get("some_event", -1)) == -1,
		"LEAK: event cooldowns cleared after restart")
	_ok(CombatExecutor.last_attacker_of("victim_x") == "",
		"LEAK: combat attacker ledger cleared after restart (got '%s')" % CombatExecutor.last_attacker_of("victim_x"))

	_ok(is_equal_approx(WorldState.corruption, 5.0),
		"LEAK: corruption reset to 5 after restart (got %.1f)" % WorldState.corruption)
	_ok(is_equal_approx(WorldState.cult_readiness, 0.0),
		"LEAK: cult_readiness reset to 0 after restart (got %.1f)" % WorldState.cult_readiness)
	_ok(ClueDB.collected_count() == 0,
		"LEAK: clues cleared after restart (got %d)" % ClueDB.collected_count())
	_ok(SummoningPlan.countdown_beats == SummoningPlan.START_COUNTDOWN,
		"LEAK: summoning countdown reset after restart (got %d)" % SummoningPlan.countdown_beats)
	_ok(is_equal_approx(SummoningPlan.impede_score, 0.0),
		"LEAK: impede_score reset after restart")
	_ok(not SummoningPlan.climax_fired, "LEAK: climax_fired cleared after restart")
	_ok(RM.current_day() == 1, "LEAK: day reset to 1 after restart")
	_ok(Agents.all().size() == before_agents, "LEAK: agent roster rebuilt to the same size")
	_ok(EventBus.events().size() == 0, "LEAK: event bus cleared after restart")

# (f) MetaState survives a restart while run state resets.
func _test_meta_survives_restart(RM: Object) -> void:
	RM.reset_meta()
	RM.start_run()
	var runs_after_first: int = RM.meta_runs_played()
	_ok(runs_after_first == 1, "first start_run bumps runs_played to 1 (got %d)" % runs_after_first)
	RM.end_run("death")
	RM.start_run()
	_ok(RM.meta_runs_played() == 2,
		"meta runs_played SURVIVES restart and increments (got %d)" % RM.meta_runs_played())
	# ...while the run itself is back at day 1.
	_ok(RM.current_day() == 1, "run day is back to 1 even though meta persisted")

# (g) end_run("death") AFTER a nightly checkpoint restores to that checkpoint (costs the day).
func _test_death_restores_checkpoint(RM: Object) -> void:
	RM.start_run()
	# Reach night of day 2 and checkpoint there.
	Clock.set_time(2, 480)
	WorldState.set_pressure(&"corruption", 40.0)
	ClueDB.collect("antigonus_notebook")
	# Prayer standing + a deed latch set at the checkpoint must SURVIVE the restore (findings 2/3:
	# the checkpoint used to silently drop these — snapshot/restore now carry them).
	PrayerService.standing["ossric"] = 10.0
	DeedRunner._fired["morning_deed"] = 2
	RM.checkpoint_night()
	# Now push into day 3 and dirty further (this is the "lost" day).
	Clock.set_time(3, 600)
	WorldState.set_pressure(&"corruption", 90.0)
	ClueDB.collect("spent_revolver")
	# Post-checkpoint mutations that must be UNDONE by the restore (data-loss regression: the
	# restore used to keep these because they weren't in the snapshot at all).
	PrayerService.standing["ossric"] = 99.0
	DeedRunner._fired["evening_deed"] = 3

	RM.end_run("death")

	# Restored to the checkpoint: day 2, corruption 40, only the first clue — NOT a full wipe.
	_ok(RM.current_day() == 2,
		"death after checkpoint restores to the checkpoint day 2 (got %d)" % RM.current_day())
	_ok(is_equal_approx(WorldState.corruption, 40.0),
		"death restores checkpoint corruption 40, not run-start 5 (got %.1f)" % WorldState.corruption)
	_ok(ClueDB.is_collected("antigonus_notebook"),
		"death keeps the clue collected before the checkpoint")
	_ok(not ClueDB.is_collected("spent_revolver"),
		"death drops the clue collected AFTER the checkpoint (the lost day)")
	# Prayer standing restored to its pre-checkpoint value 10 (not the post-checkpoint 99, not lost).
	_ok(PrayerService.get_standing("ossric") == 10.0,
		"death restores checkpoint prayer standing 10 (got %.1f)" % PrayerService.get_standing("ossric"))
	# The pre-checkpoint deed latch survives; the post-checkpoint one is undone.
	_ok(int(DeedRunner._fired.get("morning_deed", -1)) == 2,
		"death keeps the deed latch set before the checkpoint")
	_ok(int(DeedRunner._fired.get("evening_deed", -1)) == -1,
		"death drops the deed latch set AFTER the checkpoint (the lost day)")
	# The terminal-death latch must be re-armed after a checkpoint restore, so the player can be
	# downed again on the retried day (otherwise a second death would be silently ignored).
	var eg: Object = root.get_node_or_null("/root/EndGame")
	if eg != null and "_player_downed_shown" in eg:
		_ok(eg._player_downed_shown == false,
			"death restore re-arms EndGame's terminal-death latch (player can die again)")

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
