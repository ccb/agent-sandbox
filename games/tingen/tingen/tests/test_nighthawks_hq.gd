extends SceneTree
## Headless wiring check for the Nighthawks HQ slice (flat-image + colliders build).
## Mirrors test_intro_room.gd: asserts the baked room photo as a Sprite2D background,
## furniture/wall colliders on a Solids StaticBody2D, the player + room camera, the
## captain (talk) / case board (examine) / door (transition) interactables, and the two
## data edits (captain dialogue tree + captain_briefing clue) plus the CityBlocks -> HQ door.
## Run:  <godot> --headless --path tingen -s tests/test_nighthawks_hq.gd

var _passed := 0
var _failed := 0

func _init() -> void:
	await process_frame
	var packed: PackedScene = load("res://scenes/NighthawksHQ.tscn")
	if packed == null:
		_ok(false, "NighthawksHQ.tscn loads")
		_finish()
		return
	var room: Node = packed.instantiate()
	root.add_child(room)
	await process_frame
	await process_frame

	# Real room art as the flat background sprite.
	var photo: Sprite2D = room.get_node_or_null("RoomPhoto")
	_ok(photo != null and photo.texture != null
		and photo.texture.resource_path.ends_with("hq_interior.png"),
		"RoomPhoto -> hq_interior.png")

	# Furniture + wall colliders live on one Solids StaticBody2D.
	var solids: Node = room.get_node_or_null("Solids")
	_ok(solids is StaticBody2D, "Solids is a StaticBody2D")
	var shape_count := 0
	if solids:
		for c in solids.get_children():
			if c is CollisionShape2D and c.shape != null:
				shape_count += 1
	_ok(shape_count >= 8, "Solids has >=8 collision shapes (got %d)" % shape_count)

	# Player wiring (asset owned elsewhere; just verify the sprite path).
	var psprite: Sprite2D = room.get_node_or_null("Player/Sprite2D")
	_ok(psprite != null and psprite.texture != null
		and psprite.texture.resource_path.ends_with("klein_down.png"),
		"Player sprite -> klein_down.png")

	_ok(room.get_node_or_null("RoomCam") is Camera2D, "RoomCam is a Camera2D")

	# Captain: lightweight talking-NPC interactable (dialogue_id + real art, not icon.svg).
	var captain: Node = room.get_node_or_null("Captain")
	_ok(captain != null and captain.get("dialogue_id") == "captain",
		"Captain.dialogue_id == captain")
	var cap_spr: Sprite2D = room.get_node_or_null("Captain/Sprite2D")
	_ok(cap_spr != null and cap_spr.texture != null
		and cap_spr.texture.resource_path.ends_with("nighthawk_captain.png"),
		"Captain sprite -> nighthawk_captain.png")

	# Atmosphere examine point present.
	_ok(room.get_node_or_null("CaseBoard") != null, "CaseBoard present")

	# Door is an invisible hotspot back to the city map (no sprite of its own).
	var door: Node = room.get_node_or_null("Door")
	_ok(door != null and door.get("icon") == null,
		"Door is an invisible hotspot (no icon)")
	_ok(door != null and door.get("target_scene") == "res://scenes/CityBlocks.tscn",
		"Door -> CityBlocks.tscn")

	# Data edits: dialogue tree + clue.
	_check_json_has_key("res://data/dialogue.json", "captain", "dialogue.json has 'captain' tree")
	_check_clue_exists("captain_briefing")

	# CityBlocks hub wiring: a door interactable targets the HQ.
	_check_city_hq_door()

	_finish()

func _finish() -> void:
	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _check_json_has_key(path: String, key: String, label: String) -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_ok(typeof(parsed) == TYPE_DICTIONARY and parsed.has(key), label)

func _check_clue_exists(clue_id: String) -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/clues.json"))
	var found := false
	if typeof(parsed) == TYPE_ARRAY:
		for c in parsed:
			if typeof(c) == TYPE_DICTIONARY and String(c.get("id", "")) == clue_id:
				found = true
				break
	_ok(found, "clues.json has '%s'" % clue_id)

func _check_city_hq_door() -> void:
	var packed: PackedScene = load("res://scenes/CityBlocks.tscn")
	if packed == null:
		_ok(false, "CityBlocks.tscn loads")
		return
	var city: Node = packed.instantiate()
	var found := false
	for c in city.get_children():
		if c.get("target_scene") == "res://scenes/NighthawksHQ.tscn":
			found = true
			break
	city.free()
	_ok(found, "CityBlocks has a door -> NighthawksHQ.tscn")

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
