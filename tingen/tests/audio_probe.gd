extends SceneTree
## AUDIO SMOKE PROBE (P2 experiential wave) — proves REAL sound reaches the audio bus in a live
## boot, not just that the routing data is green. Run WINDOWED (never --headless):
##   GODOT --path tingen --resolution 1280x720 -s tests/audio_probe.gd
## Brief audible output on the machine running it is expected and fine.
##
## For each representative beat it fires the REAL event (through the real EventBus / the cue seam /
## actual player movement) and asserts BOTH:
##   * the AudioManager played-log recorded the mapped stream name (routing fired), and
##   * AudioServer.get_bus_peak_volume_left_db on the Master bus rose above -60 dB within a few
##     frames (real signal reached the bus — the sound is AUDIBLE, not just resolved).
## Finally it proves the Settings master-volume slider at 0 SILENCES the bus (peak stays below
## -60 dB for a full window while a mapped sound plays) and that restoring the volume restores sound.
## NOT registered in run_tests.gd — this is a live verification tool, not a headless test.

const AUDIBLE_DB: float = -60.0

var _passed := 0
var _failed := 0

func _init() -> void:
	_run()

func _assert(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
	else:
		_failed += 1
	print("[audioprobe][assert] %s %s" % ["PASS" if cond else "FAIL", label])

func _wait(frames: int) -> void:
	for i in frames:
		await process_frame

func _peak_db() -> float:
	return AudioServer.get_bus_peak_volume_left_db(0, 0)   # Master bus, channel 0

## Poll up to `frames` for the Master peak to rise above the audible floor; -200 if it never does.
func _peak_rise(frames: int = 30) -> float:
	var best := -200.0
	for i in frames:
		await process_frame
		best = maxf(best, _peak_db())
		if best > AUDIBLE_DB:
			break
	return best

## The maximum peak seen across a full window (for the "stays silent" assert).
func _peak_max_over(frames: int) -> float:
	var best := -200.0
	for i in frames:
		await process_frame
		best = maxf(best, _peak_db())
	return best

## Bounded wait for the bus to fall quiet between beats (long stings need a moment).
func _wait_quiet(max_frames: int = 360) -> void:
	for i in max_frames:
		await process_frame
		if _peak_db() <= AUDIBLE_DB:
			return

func _wait_intro_card_gone(main: Node, max_frames: int = 900) -> void:
	var waited := 0
	while waited < max_frames:
		var card: Node = main.find_child("IntroCard", true, false)
		if card == null or not is_instance_valid(card):
			break
		await process_frame
		waited += 1
	await _wait(10)

## Fire one beat: reset the played log, run `fire`, then assert the mapped stream was recorded AND
## audible signal reached the Master bus. `refire` > 0 re-fires the event every few frames while
## polling — needed for ULTRA-SHORT samples (ui_click is ~5 ms: it can start and finish inside one
## audio mix block between two rendered frames, so a single shot can slip past the block-peak
## meter; a human clicking a menu produces exactly this repeated pattern anyway).
func _beat(am: Node, label: String, expect_stream: String, fire: Callable, refire: int = 0) -> void:
	am.reset_played_log()
	fire.call()
	var best := -200.0
	for i in 30:
		await process_frame
		best = maxf(best, _peak_db())
		if best > AUDIBLE_DB:
			break
		if refire > 0 and (i % 3) == 2:
			refire -= 1
			fire.call()
	var log: Array = am.played_log()
	# Prefix match so pooled sounds (hit_flesh_1/2) pass regardless of the round-robin cursor.
	var found := false
	for s in log:
		if String(s).begins_with(expect_stream):
			found = true
	_assert(found, "%s -> played-log records '%s' (log: %s)" % [label, expect_stream, log])
	_assert(best > AUDIBLE_DB, "%s -> Master bus peak rose to %.1f dB (> %.0f)" % [label, best, AUDIBLE_DB])
	await _wait_quiet()

func _run() -> void:
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ so a probe run can never stomp the real player profile.
	preload("res://src/TestSandbox.gd").activate(root)
	if DisplayServer.get_name() == "headless":
		print("[audioprobe] refusing to run headless — this probe must hear a real audio device")
		quit(1)
		return

	var main: Node = (load("res://scenes/Main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await _wait(30)

	var am: Node = root.get_node_or_null("/root/AudioManager")
	var eb: Node = root.get_node_or_null("/root/EventBus")
	var settings: Node = root.get_node_or_null("/root/Settings")
	_assert(am != null, "AudioManager autoload present")
	_assert(eb != null, "EventBus autoload present")
	if am == null or eb == null or settings == null:
		quit(1)
		return

	# Remember the REAL user's persisted volume — this probe must leave it exactly as found.
	var original_volume: float = settings.get_number("master_volume")
	settings.set_value("master_volume", 1.0)

	_assert(am.get_child_count() > 0, "live: AudioStreamPlayer pool built (%d children)" % am.get_child_count())

	# --- Ambience: the night bed must already be sounding on its looping player -----------------
	_assert(bool(am.ambience_playing()), "live: ambience_night looping player is playing")
	var amb_peak: float = await _peak_rise(60)
	_assert(amb_peak > AUDIBLE_DB, "ambience reaches the Master bus (peak %.1f dB)" % amb_peak)
	# Silence the bed so each event beat below is measured against a quiet floor.
	am.set_ambience_enabled(false)
	await _wait_quiet()

	# --- New Run through the REAL flow (windowed live boot) --------------------------------------
	if main.has_method("start_new_run"):
		main.start_new_run()
		await _wait(10)
		if main.has_method("pathway_picker_active") and main.pathway_picker_active():
			main.choose_pathway("hunter")
		await _wait_intro_card_gone(main)
	await _wait_quiet()

	# --- Representative events through the REAL EventBus -----------------------------------------
	await _beat(am, "player revolver_shot cast-finished", "shot_revolver",
		func() -> void: eb.emit_event("ability_cast_finished", {"caster": "player", "ability": "revolver_shot"}))
	await _beat(am, "weapon_empty (dry fire)", "shot_dry",
		func() -> void: eb.emit_event("weapon_empty", {"caster": "player", "ammo": 0}))
	await _beat(am, "light hit (damage 8)", "hit_flesh",
		func() -> void: eb.emit_event("agent_attacked", {"actor": "player", "target": "probe_dummy", "damage": 8.0, "target_hp": 50.0, "downed": false}))
	await _beat(am, "heavy hit (damage 40)", "hit_hard",
		func() -> void: eb.emit_event("agent_attacked", {"actor": "probe_dummy", "target": "player", "damage": 40.0, "target_hp": 10.0, "downed": false}))
	await _beat(am, "agent_downed", "body_fall",
		func() -> void: eb.emit_event("agent_downed", {"actor": "player", "target": "probe_dummy"}))
	await _beat(am, "transformed (mask-drop slam)", "slam_mask_drop",
		func() -> void: eb.emit_event("transformed", {"agent": "probe_dummy", "form": "hog_butcher"}))
	await _beat(am, "item_picked_up", "pickup_item",
		func() -> void: eb.emit_event("item_picked_up", {"caster": "player", "item": "bandage"}))
	await _beat(am, "hint_shown", "hint_chime",
		func() -> void: eb.emit_event("hint_shown", {"key": "probe_hint"}))

	# --- Cue seams (non-EventBus presentation beats) ----------------------------------------------
	await _beat(am, "ui_click cue", "ui_click",
		func() -> void: am.cue("ui_click"), 8)
	await _beat(am, "room transition cue", "door_open",
		func() -> void: am.cue("room_changed", {"room": "probe_room"}))
	var toasts: Array = get_nodes_in_group("toasts")
	if toasts.size() > 0:
		await _beat(am, "a real Toasts.push card", "ui_toast",
			func() -> void: toasts[0].push("Audio probe", "toast chime check", "system"))
	else:
		print("[audioprobe] no toasts layer mounted — skipping the toast beat")

	# --- Footsteps off ACTUAL player movement ------------------------------------------------------
	var players: Array = get_nodes_in_group("player")
	if players.size() > 0 and players[0] is Node2D:
		am.reset_played_log()
		var rig: Node2D = players[0]
		for i in 40:   # walk ~240 px in small real steps (below the teleport guard)
			rig.global_position += Vector2(6, 0)
			await process_frame
		var log: Array = am.played_log()
		var steps := 0
		for s in log:
			if String(s).begins_with("step_"):
				steps += 1
		_assert(steps >= 3, "footsteps: ~240 px of real movement played %d step sounds (log: %s)" % [steps, log])
		await _wait_quiet()
	else:
		_assert(false, "player rig present for the footstep beat")

	# --- The Settings master-volume slider at 0 SILENCES the bus ----------------------------------
	settings.set_value("master_volume", 0.0)
	await _wait(5)
	eb.emit_event("agent_downed", {"actor": "player", "target": "probe_dummy_2"})
	var muted_peak: float = await _peak_max_over(40)
	_assert(muted_peak <= AUDIBLE_DB,
		"master_volume 0 -> Master bus stays SILENT while a mapped sound plays (max peak %.1f dB)" % muted_peak)
	# And turning it back up is audible again (the slider controls the bus both ways).
	settings.set_value("master_volume", 1.0)
	await _wait(5)
	eb.emit_event("agent_downed", {"actor": "player", "target": "probe_dummy_3"})
	var restored_peak: float = await _peak_rise(30)
	_assert(restored_peak > AUDIBLE_DB,
		"master_volume 1 -> sound is audible again (peak %.1f dB)" % restored_peak)

	# Leave the machine as found: the user's persisted volume, ambience back on.
	settings.set_value("master_volume", original_volume)
	am.set_ambience_enabled(true)

	print("\n[audioprobe] === %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)
