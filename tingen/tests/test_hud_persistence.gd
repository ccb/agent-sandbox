extends SceneTree
## Headless smoke test: the persistent HUD (Main/UI/HUD) survives world transitions,
## and every door/stair (now routed through WorldState.transition_requested) swaps only
## the World subtree. Guards the "HUD live across scenes" requirement.
##   godot --headless --path tingen -s tests/test_hud_persistence.gd

var _passed: int = 0
var _failed: int = 0

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)

	var WS: Object = root.get_node("/root/WorldState")
	var main: Node = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	await process_frame

	# N1 repair (stale boot expectation): since the M2 boot controller the game boots to a TITLE
	# screen — no HUD, no world until New Run (boot_smoke.gd pins that title). The persistent-HUD
	# contract this harness guards only STARTS once a run begins, so drive the REAL New Run entry
	# first (fresh sandbox meta = single pathway = starts directly, no M30 G1 picker), then assert
	# the HUD exists and the run wakes in the lodging (RunManager.LODGING_SCENE = IntroRoom reused).
	_ok(main.has_method("start_new_run"), "the boot controller exposes start_new_run()")
	main.start_new_run()
	await process_frame
	await process_frame

	var hud: Node = main.get_node_or_null("UI/HUD")
	_ok(hud != null, "HUD present once a run starts")
	_ok(main.get("current_scene_path") == "res://scenes/IntroRoom.tscn",
		"a new run wakes in the lodging (IntroRoom)")

	# Interactable door (IntroRoom -> City) already used this path.
	WS.transition_requested.emit("res://scenes/City.tscn", "")
	await process_frame
	await process_frame
	_ok(main.get("current_scene_path") == "res://scenes/City.tscn", "world swapped to City")
	_ok(main.get_node_or_null("UI/HUD") == hud, "HUD instance survives IntroRoom -> City")

	# Portal door/stair (chapel -> cathedral) — the case that used to full-swap and drop the HUD.
	WS.transition_requested.emit("res://scenes/CathedralNave.tscn", "")
	await process_frame
	await process_frame
	_ok(main.get("current_scene_path") == "res://scenes/CathedralNave.tscn",
		"world swapped to CathedralNave")
	_ok(main.get_node_or_null("UI/HUD") == hud, "HUD instance survives City -> CathedralNave")

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		print("  FAIL  %s" % label)
