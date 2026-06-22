extends SceneTree
## Headless wiring check for the University Archive slice (flat-image + colliders build).
## Mirrors test_nighthawks_hq.gd: asserts the baked room photo as a Sprite2D background,
## furniture/wall colliders on a Solids StaticBody2D, the player + room camera, Finch (talk),
## the three examine hotspots (each with its clue_id), the door (transition), and the data
## edits (finch dialogue tree + four clues) plus the CityBlocks -> UniversityArchive door.
## Run:  <godot> --headless --path tingen -s tests/test_university_archive.gd

var _passed := 0
var _failed := 0

func _init() -> void:
	await process_frame
	var packed: PackedScene = load("res://scenes/UniversityArchive.tscn")
	if packed == null:
		_ok(false, "UniversityArchive.tscn loads")
		_finish()
		return
	var room: Node = packed.instantiate()
	root.add_child(room)
	await process_frame
	await process_frame

	# Real room art as the flat background sprite.
	var photo: Sprite2D = room.get_node_or_null("RoomPhoto")
	_ok(photo != null and photo.texture != null
		and photo.texture.resource_path.ends_with("university_archive.png"),
		"RoomPhoto -> university_archive.png")

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

	# Finch: lightweight talking-NPC interactable (dialogue_id + real art, not icon.svg).
	var finch: Node = room.get_node_or_null("Finch")
	_ok(finch != null and finch.get("dialogue_id") == "finch",
		"Finch.dialogue_id == finch")
	var finch_spr: Sprite2D = room.get_node_or_null("Finch/Sprite2D")
	_ok(finch_spr != null and finch_spr.texture != null
		and finch_spr.texture.resource_path.ends_with("archive_clerk_finch.png"),
		"Finch sprite -> archive_clerk_finch.png")

	# Three examine hotspots, each carrying its clue_id.
	_check_examine(room, "CardCatalog", "archive_antigonus")
	_check_examine(room, "RestrictedShelf", "restricted_volume_missing")
	_check_examine(room, "ReadingDeskNotes", "contamination_chain")

	# Door is an invisible hotspot back to the city map (no sprite of its own).
	var door: Node = room.get_node_or_null("Door")
	_ok(door != null and door.get("icon") == null,
		"Door is an invisible hotspot (no icon)")
	_ok(door != null and door.get("target_scene") == "res://scenes/CityBlocks.tscn",
		"Door -> CityBlocks.tscn")

	# Simulation framing: the room must NOT overwrite the player's lead. No interactable
	# in the room sets lead_on_use (the Welch thread is a thought, not an objective).
	var leads := 0
	for n in room.get_children():
		if n.get("lead_on_use") != null and String(n.get("lead_on_use")) != "":
			leads += 1
	_ok(leads == 0, "no Interactable sets a lead (surface, never command)")

	# Data edits: finch dialogue tree + four clues.
	_check_json_has_key("res://data/dialogue.json", "finch", "dialogue.json has 'finch' tree")
	for cid in ["archive_antigonus", "restricted_volume_missing", "contamination_chain", "finch_cover"]:
		_check_clue_exists(cid)

	# CityBlocks hub wiring: a door interactable targets the archive.
	_check_city_archive_door()

	_finish()

func _finish() -> void:
	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _check_examine(room: Node, node_name: String, clue_id: String) -> void:
	var n: Node = room.get_node_or_null(node_name)
	_ok(n != null and String(n.get("clue_id")) == clue_id,
		"%s.clue_id == %s" % [node_name, clue_id])

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

func _check_city_archive_door() -> void:
	var packed: PackedScene = load("res://scenes/CityBlocks.tscn")
	if packed == null:
		_ok(false, "CityBlocks.tscn loads")
		return
	var city: Node = packed.instantiate()
	var found := false
	for c in city.get_children():
		if c.get("target_scene") == "res://scenes/UniversityArchive.tscn":
			found = true
			break
	city.free()
	_ok(found, "CityBlocks has a door -> UniversityArchive.tscn")

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
