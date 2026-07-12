extends SceneTree
## M10 polish harness — pause menu, settings, HUD legend, spark_burst VFX fix.
## Run headless (NOT part of the main suite; a subset is mirrored into run_tests.gd):
##   godot --headless --path tingen -s tests/test_polish.gd
##
## Covers, per the M10 TDD spec:
##   (a) the pause action pauses the tree + shows the menu; resume unpauses; quit-to-title ends the
##       run + returns to title (no softlock, meta preserved); pause is inert during ending/boot.
##   (b) each settings toggle PERSISTS (save->reload) and TAKES EFFECT (shake-off => shake helper is
##       a no-op; text-size scales a probe label; colorblind swaps the palette constant).
##   (c) the HUD legend opens/closes.
##   (d) the spark_burst FX resolves to a non-boxy visual (animated/keyed form, not the raw sheet).
##   (e) determinism: none of this alters the combat_sim transcript (the guard lives in run_tests.gd).

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	root.get_node("/root/RunManager").set("meta_path", "user://meta_test.json")
	root.get_node("/root/RunManager").reload_meta()

	await _test_settings_persist_and_take_effect()
	await _test_pause_menu_lifecycle()
	await _test_hud_legend_toggle()
	_test_spark_burst_not_boxy()

	print("\n=== test_polish: %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)

# --- (b) Settings ---------------------------------------------------------------------------------
func _test_settings_persist_and_take_effect() -> void:
	print("[polish: settings persist + take effect]")
	var S: Object = root.get_node_or_null("/root/Settings")
	_ok(S != null, "Settings autoload is registered")
	if S == null:
		return
	# Defaults: cosmetic effects on, no colorblind, text scale 1.0.
	S.reset_defaults()
	_ok(S.get_bool("screen_shake"), "screen_shake defaults on")
	_ok(S.get_bool("hit_flash"), "hit_flash defaults on")
	_ok(not S.get_bool("colorblind"), "colorblind defaults off")
	_ok(abs(S.get_number("text_scale") - 1.0) < 0.001, "text_scale defaults to 1.0")
	_ok(abs(S.get_number("master_volume") - 1.0) < 0.001, "master_volume defaults to 1.0")

	# TAKES EFFECT: shake-off makes the CombatFeedback shake helper a no-op.
	var FB: Object = root.get_node_or_null("/root/CombatFeedback")
	_ok(FB != null, "CombatFeedback autoload is registered")
	if FB != null:
		S.set_value("screen_shake", true)
		FB.reset_probe()
		FB.shake(8.0)
		_ok(FB.last_shake_amplitude() > 0.0, "shake ON -> the shake helper produces amplitude")
		S.set_value("screen_shake", false)
		FB.reset_probe()
		FB.shake(8.0)
		_ok(FB.last_shake_amplitude() == 0.0, "shake OFF -> the shake helper is a no-op")
		# hit_flash gate
		S.set_value("hit_flash", true)
		FB.reset_probe()
		FB.flash()
		_ok(FB.last_flash_alpha() > 0.0, "hit_flash ON -> the flash helper produces a flash")
		S.set_value("hit_flash", false)
		FB.reset_probe()
		FB.flash()
		_ok(FB.last_flash_alpha() == 0.0, "hit_flash OFF -> the flash helper is a no-op")

	# TAKES EFFECT: master_volume drives the master audio bus (wired even though audio is deferred).
	S.set_value("master_volume", 0.5)
	var bus := AudioServer.get_bus_index("Master")
	var expect_db := linear_to_db(0.5)
	_ok(abs(AudioServer.get_bus_volume_db(bus) - expect_db) < 0.5,
		"master_volume drives the Master bus volume (db)")
	# mute at 0
	S.set_value("master_volume", 0.0)
	_ok(AudioServer.is_bus_mute(bus), "master_volume 0 mutes the Master bus")
	S.set_value("master_volume", 1.0)

	# TAKES EFFECT: text_scale scales a probe label's font size.
	var probe := Label.new()
	probe.add_theme_font_size_override("font_size", 20)
	root.add_child(probe)
	S.set_value("text_scale", 1.5)
	S.apply_text_scale(probe, 20)
	_ok(probe.get_theme_font_size("font_size") == 30, "text_scale 1.5 scales a 20px probe label to 30px")
	probe.queue_free()

	# TAKES EFFECT: colorblind swaps the meter/telegraph palette constant to the safe set.
	S.set_value("colorblind", false)
	var normal_doom: Color = S.meter_color("doom")
	S.set_value("colorblind", true)
	var cb_doom: Color = S.meter_color("doom")
	_ok(cb_doom != normal_doom, "colorblind ON swaps the doom meter color to the safe palette")
	var cb_telegraph: Color = S.telegraph_color()
	S.set_value("colorblind", false)
	var normal_telegraph: Color = S.telegraph_color()
	_ok(cb_telegraph != normal_telegraph, "colorblind ON swaps the telegraph color too")

	# PERSISTS: save -> mutate live -> reload restores the saved values.
	S.reset_defaults()
	S.set_value("screen_shake", false)
	S.set_value("hit_flash", false)
	S.set_value("colorblind", true)
	S.set_value("text_scale", 1.25)
	S.set_value("master_volume", 0.3)
	var tmp := "user://test_settings.json"
	_ok(S.save_to(tmp), "settings save writes a file")
	# Corrupt the live values, then reload from disk.
	S.reset_defaults()
	_ok(S.get_bool("screen_shake"), "defaults restored before reload (screen_shake back on)")
	_ok(S.load_from(tmp), "settings load reads the file")
	_ok(not S.get_bool("screen_shake"), "screen_shake persisted OFF across reload")
	_ok(not S.get_bool("hit_flash"), "hit_flash persisted OFF across reload")
	_ok(S.get_bool("colorblind"), "colorblind persisted ON across reload")
	_ok(abs(S.get_number("text_scale") - 1.25) < 0.001, "text_scale persisted (1.25) across reload")
	_ok(abs(S.get_number("master_volume") - 0.3) < 0.001, "master_volume persisted (0.3) across reload")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
	S.reset_defaults()

# --- (a) Pause menu -------------------------------------------------------------------------------
func _test_pause_menu_lifecycle() -> void:
	print("[polish: pause menu pauses/resumes + quit-to-title]")
	# Mount a minimal BootController-as-game-controller so quit-to-title + run lifecycle are real.
	var RM: Object = root.get_node("/root/RunManager")
	var EG: Object = root.get_node("/root/EndGame")
	var boot: Node = (load("res://src/BootController.gd") as GDScript).new()
	root.add_child(boot)
	await process_frame

	var PM: Object = root.get_node_or_null("/root/PauseMenu")
	_ok(PM != null, "PauseMenu autoload is registered")
	if PM == null:
		boot.free()
		return

	# Start a real run so quit-to-title has something to abandon.
	boot.start_new_run()
	await process_frame
	_ok(RM.run_active(), "a run is active after start_new_run")
	var runs_before := int(RM.meta_runs_played())

	# Pause: tree paused + menu shown.
	paused = false
	PM.open()
	_ok(paused, "open() pauses the SceneTree")
	_ok(PM.is_open(), "open() shows the pause menu")

	# Resume: unpauses + menu gone.
	PM.resume()
	_ok(not paused, "resume() unpauses the SceneTree")
	_ok(not PM.is_open(), "resume() hides the pause menu")

	# Quit to title: ends the current run, returns to the title, no softlock, meta preserved.
	PM.open()
	PM.quit_to_title()
	_ok(not paused, "quit_to_title lifts the pause (no softlock)")
	_ok(not PM.is_open(), "quit_to_title closes the pause menu")
	_ok(not RM.run_active(), "quit_to_title ends the active run")
	_ok(boot.has_method("is_at_title") and boot.is_at_title(), "quit_to_title returns to the title screen")
	_ok(int(RM.meta_runs_played()) >= runs_before, "meta (runs_played) is preserved across quit-to-title")

	# Inert during an ending: EndGame owns the freeze; pause must NOT open over an ending overlay.
	boot.start_new_run()
	await process_frame
	EG.player_downed()   # raises the terminal ending overlay + pauses the tree
	_ok(paused, "an ending pauses the tree")
	PM.open()
	_ok(not PM.is_open(), "pause is INERT while an ending overlay is up (does not open)")
	# Clean up the ending overlay + latch.
	EG.dismiss()
	paused = false
	if EG.has_method("rearm"):
		EG.rearm()

	# Inert during boot (no active run, sitting at title): pausing the title is a no-op.
	RM.end_run("win")   # ensure inactive
	await process_frame
	PM.open()
	_ok(not PM.is_open(), "pause is INERT at the title / boot (no run to pause)")

	boot.free()
	await process_frame

# --- (c) HUD legend -------------------------------------------------------------------------------
func _test_hud_legend_toggle() -> void:
	print("[polish: HUD legend opens/closes]")
	var hl_script := load("res://src/HudLegend.gd") as GDScript
	_ok(hl_script != null, "HudLegend.gd script exists")
	if hl_script == null:
		return
	var HL: Object = hl_script.new()
	root.add_child(HL)
	await process_frame
	_ok(not HL.is_open(), "the legend starts closed (unobtrusive)")
	HL.toggle()
	_ok(HL.is_open(), "toggle opens the legend")
	# The legend must actually explain the four meters + the combat readout.
	var body := String(HL.legend_text())
	for token in ["Doom", "Madness", "Notice", "Heat", "ammo", "cooldown", "telegraph"]:
		_ok(token.to_lower() in body.to_lower(), "the legend explains '%s'" % token)
	HL.toggle()
	_ok(not HL.is_open(), "toggle again closes the legend")
	HL.free()

# --- (d) spark_burst VFX fix ----------------------------------------------------------------------
func _test_spark_burst_not_boxy() -> void:
	print("[polish: spark_burst FX is not a boxy black panel]")
	# The keyed cutout sheet must exist on disk with an ALPHA channel (the raw sheet is opaque RGB).
	var keyed := "res://assets/fx/flipbooks/spark_burst_keyed.png"
	_ok(ResourceLoader.exists(keyed), "a keyed (alpha-trimmed) spark_burst cutout exists on disk")
	if ResourceLoader.exists(keyed):
		var tex := load(keyed) as Texture2D
		var img := tex.get_image()
		_ok(img.detect_alpha() != Image.ALPHA_NONE,
			"the keyed spark_burst has transparency (not an opaque box)")
		# The black background must be keyed out: the corner pixels are fully transparent.
		var w := img.get_width()
		var h := img.get_height()
		var corner := img.get_pixel(1, 1)
		_ok(corner.a < 0.1, "the sheet's black background is keyed to transparent at the corner")
		# And there is real burst content somewhere (not fully transparent everywhere).
		var mid := img.get_pixel(w / 2, h / 2)
		_ok(mid.a > 0.0 or img.get_pixel(w / 8, h / 8).a > 0.0 or img.detect_alpha() == Image.ALPHA_BLEND,
			"the keyed sheet still carries visible burst pixels")

	# CombatFx must resolve the transform burst to the ANIMATED/keyed form, not the raw opaque sheet.
	var FX: Object = root.get_node_or_null("/root/CombatFx")
	_ok(FX != null and FX.has_method("spark_burst_is_animated"),
		"CombatFx exposes the spark_burst-is-animated seam")
	if FX != null and FX.has_method("spark_burst_is_animated"):
		_ok(FX.spark_burst_is_animated(),
			"the transform burst uses the animated/keyed form (not the raw 1024^2 sheet drawn whole)")
	# is-using, not would-use: the SPAWNED burst node is a real AnimatedSprite2D (review finding #2).
	if FX != null and FX.has_method("spawn_spark_burst_probe"):
		var burst_node: Node = FX.spawn_spark_burst_probe()
		_ok(burst_node is AnimatedSprite2D,
			"the SPAWNED transform burst is a real AnimatedSprite2D (not the raw sheet Sprite2D)")
		if FX.has_method("clear_transients"):
			FX.clear_transients()
