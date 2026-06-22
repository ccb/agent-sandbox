extends SceneTree
## Headless wiring check for the Old Neil home (normal state) slice. Mirrors
## test_nighthawks_hq.gd: baked room photo, wall/furniture colliders, player + room cam,
## Old Neil (talk) + four examine hotspots, the door back to the city, plus the data edits
## (old_neil dialogue tree + four clues) and the City -> NeilHome door.
##   <godot> --headless --path tingen -s tests/test_neil_home.gd

var _passed := 0
var _failed := 0

func _init() -> void:
	await process_frame
	var packed: PackedScene = load("res://scenes/NeilHome.tscn")
	if packed == null:
		_ok(false, "NeilHome.tscn loads")
		_finish()
		return
	var room: Node = packed.instantiate()
	root.add_child(room)
	await process_frame
	await process_frame

	var photo: Sprite2D = room.get_node_or_null("RoomPhoto")
	_ok(photo != null and photo.texture != null
		and photo.texture.resource_path.ends_with("neil_home_normal.png"),
		"RoomPhoto -> neil_home_normal.png")

	var solids: Node = room.get_node_or_null("Solids")
	_ok(solids is StaticBody2D, "Solids is a StaticBody2D")
	var shape_count := 0
	if solids:
		for c in solids.get_children():
			if c is CollisionShape2D and c.shape != null:
				shape_count += 1
	_ok(shape_count >= 8, "Solids has >=8 collision shapes (got %d)" % shape_count)

	var psprite: Sprite2D = room.get_node_or_null("Player/Sprite2D")
	_ok(psprite != null and psprite.texture != null
		and psprite.texture.resource_path.ends_with("klein_down.png"),
		"Player sprite -> klein_down.png")

	_ok(room.get_node_or_null("RoomCam") is Camera2D, "RoomCam is a Camera2D")

	var neil: Node = room.get_node_or_null("OldNeil")
	_ok(neil != null and neil.get("dialogue_id") == "old_neil",
		"OldNeil.dialogue_id == old_neil")

	_check_hotspot(room, "PianoPortrait", "celeste_grief")
	_check_hotspot(room, "VialCabinet", "stored_blood")
	_check_hotspot(room, "Worktable", "alchemical_life_ritual")
	_check_hotspot(room, "LettersDesk", "neils_obsession")

	var door: Node = room.get_node_or_null("Door")
	_ok(door != null and door.get("target_scene") == "res://scenes/City.tscn",
		"Door -> City.tscn")

	_check_json_has_key("res://data/dialogue.json", "old_neil", "dialogue.json has 'old_neil' tree")
	for cid in ["celeste_grief", "stored_blood", "alchemical_life_ritual", "neils_obsession"]:
		_check_clue_exists(cid)

	# --- Agent intelligence: Old Neil registered as an agent + left-click inspectable ---
	_ok(neil != null and neil.get("agent_id") == "old_neil", "OldNeil.agent_id == old_neil")
	_check_json_has_key("res://data/npcs.json", "old_neil", "npcs.json has 'old_neil' agent")

	# --- RoomState swap: trigger flips normal <-> 失控 (bg swap + hide Neil) ---
	var trig: Node = room.get_node_or_null("RitualTrigger")
	_ok(trig != null and bool(trig.get("room_state_toggle")), "RitualTrigger toggles room state")
	var rs: Node = room.get_node_or_null("RoomState")
	_ok(rs != null and rs.has_method("toggle"), "RoomState present")
	if rs != null:
		rs.call("set_state", "lost_control")
		_ok(photo != null and photo.texture != null
			and photo.texture.resource_path.ends_with("neil_home_lost_control.png"),
			"lost_control -> RoomPhoto = neil_home_lost_control.png")
		_ok(neil != null and neil.visible == false, "lost_control -> Old Neil hidden")
		rs.call("set_state", "normal")
		_ok(photo != null and photo.texture != null
			and photo.texture.resource_path.ends_with("neil_home_normal.png"),
			"normal -> RoomPhoto = neil_home_normal.png")
		_ok(neil != null and neil.visible == true, "normal -> Old Neil visible")

	_check_city_neil_door()
	_finish()

func _check_hotspot(room: Node, node_name: String, clue: String) -> void:
	var n: Node = room.get_node_or_null(node_name)
	_ok(n != null and n.get("clue_id") == clue, "%s.clue_id == %s" % [node_name, clue])

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

func _check_city_neil_door() -> void:
	var packed: PackedScene = load("res://scenes/City.tscn")
	if packed == null:
		_ok(false, "City.tscn loads")
		return
	var city: Node = packed.instantiate()
	var found := false
	for c in city.get_children():
		if c.get("target_scene") == "res://scenes/NeilHome.tscn":
			found = true
			break
	city.free()
	_ok(found, "City has a door -> NeilHome.tscn")

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
