extends SceneTree
## Headless wiring check for the Klein's-bedroom slice (flat-image + colliders build).
## Asserts the placeholder flats were replaced with the real room photo as a Sprite2D
## background, furniture/wall collision shapes on a Solids StaticBody2D, the repointed
## player, the room camera, and the 4 interactables with their clue/door logic intact.
## Run:  <godot> --headless --path tingen -s tests/test_intro_room.gd

var _passed := 0
var _failed := 0

func _init() -> void:
	await process_frame
	var packed: PackedScene = load("res://scenes/IntroRoom.tscn")
	var room: Node = packed.instantiate()
	root.add_child(room)
	await process_frame
	await process_frame

	# Real room art as the flat background sprite (replaces the TileMapLayer + props).
	var photo: Sprite2D = room.get_node_or_null("RoomPhoto")
	_ok(photo != null and photo.texture != null
		and photo.texture.resource_path.ends_with("klein_room.png"),
		"RoomPhoto -> klein_room.png")

	# Furniture + wall colliders live on one Solids StaticBody2D.
	var solids: Node = room.get_node_or_null("Solids")
	_ok(solids is StaticBody2D, "Solids is a StaticBody2D")
	var shape_count := 0
	if solids:
		for c in solids.get_children():
			if c is CollisionShape2D and c.shape != null:
				shape_count += 1
	_ok(shape_count >= 10, "Solids has >=10 collision shapes (got %d)" % shape_count)

	# Player uses the bespoke 4-way Klein sprite (asset owned elsewhere; just verify wiring).
	var psprite: Sprite2D = room.get_node_or_null("Player/Sprite2D")
	_ok(psprite != null and psprite.texture != null
		and psprite.texture.resource_path.ends_with("klein_down.png"),
		"Player sprite -> klein_down.png")

	_ok(room.get_node_or_null("RoomCam") is Camera2D, "RoomCam is a Camera2D")

	# Interactable logic intact: clue ids + door target unchanged by the art pivot.
	_check_clue(room, "Notebook", "antigonus_notebook")
	_check_clue(room, "Gun", "spent_revolver")
	_check_clue(room, "Mirror", "wrong_reflection")
	_check_icon(room, "Gun", "revolver_0.png")

	# Door is an invisible hotspot over the painted right-wall door (no sprite of its own).
	var door: Node = room.get_node_or_null("Door")
	_ok(door != null and door.get("icon") == null,
		"Door is an invisible hotspot (no icon)")
	_ok(door != null and door.get("target_scene") == "res://scenes/City.tscn",
		"Door -> City.tscn")

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _check_clue(room: Node, node_name: String, expect_clue: String) -> void:
	var n: Node = room.get_node_or_null(node_name)
	_ok(n != null and n.get("clue_id") == expect_clue,
		"%s clue_id == %s" % [node_name, expect_clue])

func _check_icon(room: Node, node_name: String, expect_suffix: String) -> void:
	var spr: Sprite2D = room.get_node_or_null("%s/Sprite2D" % node_name)
	var ok := spr != null and spr.texture != null and spr.texture.resource_path.ends_with(expect_suffix)
	_ok(ok, "%s sprite -> %s" % [node_name, expect_suffix])

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
