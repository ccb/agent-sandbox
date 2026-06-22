extends SceneTree
## Scene transitions must work from anywhere: under Main (a GameController is mounted ->
## emit the World-swap signal so the persistent HUD survives) AND standalone (no
## GameController, e.g. running a single scene with F6 -> full change_scene_to_file).
## Guards WorldState.request_transition.
##   godot --headless --path tingen -s tests/test_transition_anywhere.gd

var _signalled: bool = false
var _passed: int = 0
var _failed: int = 0

func _on_transition(_path: String, _lead: String) -> void:
	_signalled = true

func _init() -> void:
	await process_frame
	var WS: Object = root.get_node("/root/WorldState")
	WS.transition_requested.connect(_on_transition)

	# --- Branch A: GameController mounted -> emits the signal, no full scene change ---
	var gc := Node.new()
	gc.add_to_group("game_controller")
	root.add_child(gc)
	_signalled = false
	WS.request_transition("res://scenes/CathedralNave.tscn", "")
	await process_frame
	_ok(_signalled, "GameController present -> transition_requested emitted")
	_ok(current_scene == null or current_scene.scene_file_path != "res://scenes/CathedralNave.tscn",
		"GameController present -> no full scene change")
	gc.free()
	await process_frame

	# --- Branch B: standalone (no GameController) -> full scene change ---
	_signalled = false
	WS.request_transition("res://scenes/CathedralNave.tscn", "")
	await process_frame
	await process_frame
	_ok(not _signalled, "standalone -> did NOT emit the World-swap signal")
	var cur := current_scene
	_ok(cur != null and cur.scene_file_path == "res://scenes/CathedralNave.tscn",
		"standalone -> change_scene_to_file loaded CathedralNave")

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		print("  FAIL  %s" % label)
