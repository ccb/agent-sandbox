extends SceneTree
## Headless smoke test for the boot controller (M2). Loads Main.tscn, asserts it instances
## without error and exposes the "New Run" entry point (a title screen with a working
## start_new_run() seam that hands off to RunManager.start_run()).
## Run:  <godot> --headless --path tingen -s tests/boot_smoke.gd

var _passed := 0
var _failed := 0

func _init() -> void:
	await process_frame
	await process_frame
	# B3 (retro): NEVER touch the player's REAL persistent profile (user://meta.json) — redirect
	# the meta slot to a test-scoped file before anything drives RunManager (tests/test_meta_isolation.gd).
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)

	var packed: PackedScene = load("res://scenes/Main.tscn")
	_ok(packed != null, "Main.tscn loads as a PackedScene")
	if packed == null:
		print("\n=== %d passed, %d failed ===" % [_passed, _failed])
		quit(1)
		return

	var main: Node = packed.instantiate()
	_ok(main != null, "Main.tscn instances without error")
	root.add_child(main)
	await process_frame
	await process_frame

	# The boot controller exposes a Title screen with the New Run entry.
	_ok(main.has_method("start_new_run"),
		"boot controller exposes start_new_run() (the New Run entry)")
	_ok(main.has_method("has_continue"),
		"boot controller exposes has_continue() (Continue-if-checkpoint gating)")

	# A New Run entry point must exist as UI too (a button labelled New Run somewhere in the tree).
	_ok(_find_new_run_label(main), "a 'New Run' control is present in the boot UI")

	# Driving start_new_run() must start a run and swap into the lodging (IntroRoom) world.
	if main.has_method("start_new_run"):
		main.start_new_run()
		await process_frame
		await process_frame
		var RM: Object = root.get_node_or_null("/root/RunManager")
		_ok(RM != null and RM.current_day() == 1,
			"start_new_run() -> RunManager.start_run() (day 1)")

	main.queue_free()
	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _find_new_run_label(node: Node) -> bool:
	if node is Button and String((node as Button).text).to_lower().contains("new run"):
		return true
	if node is Label and String((node as Label).text).to_lower().contains("new run"):
		return true
	for c in node.get_children():
		if _find_new_run_label(c):
			return true
	return false

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
