extends SceneTree
## SceneFade.go() fades, still performs the transition (from anywhere), and leaves the
## overlay transparent. The fade is visual; this guards that it doesn't break or block the
## transition and cleans up after itself.
##   godot --headless --path tingen -s tests/test_scene_fade.gd

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	var SF: Object = root.get_node_or_null("/root/SceneFade")
	_ok(SF != null, "SceneFade autoload present")
	if SF == null:
		_done()
		return
	_ok(SF.has_method("go"), "SceneFade has go()")

	# Standalone (no GameController): go() fades, then change_scene_to_file to the target.
	await SF.go("res://scenes/CathedralCrypt.tscn")
	var cur: Node = current_scene
	_ok(cur != null and cur.scene_file_path == "res://scenes/CathedralCrypt.tscn",
		"go() transitioned to CathedralCrypt (standalone path)")
	var rect: Object = SF.get_child(0)
	_ok(rect != null and rect.color.a < 0.02, "fade overlay returned to transparent")
	_done()

func _done() -> void:
	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		print("  FAIL  %s" % label)
