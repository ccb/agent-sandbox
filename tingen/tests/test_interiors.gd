extends SceneTree
## Headless wiring check for the 7 painted interior rooms (butcher shop, Klein parlor,
## Laughing Eel taproom, Mr Franky's hall, police station front office, Selena almshouse
## ward, dockside warehouse floor). Mirrors test_neil_home.gd for per-scene wiring (room
## photo, Solids colliders, player, camera, walk-in Portal areas) and follows the
## test_transition_anywhere.gd / _test_room_traversal round-trip conventions for the
## RoomGraph data walks (portal in -> room id correct -> portal back -> city).
## Deliberately does NOT instantiate City.tscn: the city-side door pins live in
## run_tests.gd::_test_interior_rooms so this file stays runnable while the city buildout
## churns.
##   <godot> --headless --path tingen -s tests/test_interiors.gd

var _passed := 0
var _failed := 0

## Per-room contract. w/h = the world size the background sprite must span (scale-aware
## grounds: warehouse VAST ~3x a Klein house room, tavern/police/butcher mid, almshouse +
## Franky's modest). exit = the walk-in Portal back out; spawn = the authored Player pos.
const SPECS := [
	{"room": "klein_living_room", "scene": "res://scenes/KleinLivingRoom.tscn",
		"bg": "klein_living_room.png", "w": 896.0, "solids": 12,
		"exit_to": "res://scenes/City.tscn", "exit_pos": Vector2(448, 627)},
	{"room": "butcher_shop_inner", "scene": "res://scenes/ButcherShopInner.tscn",
		"bg": "butcher_shop_inner.png", "w": 1305.6, "solids": 10,
		"exit_to": "res://scenes/City.tscn", "exit_pos": Vector2(653, 900)},
	{"room": "laughing_eel_tavern", "scene": "res://scenes/LaughingEelTavern.tscn",
		"bg": "laughing_eel_tavern.png", "w": 1536.0, "solids": 14,
		"exit_to": "res://scenes/City.tscn", "exit_pos": Vector2(783, 1054)},
	{"room": "police_station_inner", "scene": "res://scenes/PoliceStationInner.tscn",
		"bg": "police_station_inner.png", "w": 1459.2, "solids": 10,
		"exit_to": "res://scenes/City.tscn", "exit_pos": Vector2(700, 1003)},
	{"room": "selena_almshouse_inner", "scene": "res://scenes/SelenaAlmshouseInner.tscn",
		"bg": "selena_almshouse_inner.png", "w": 1152.0, "solids": 9,
		"exit_to": "res://scenes/City.tscn", "exit_pos": Vector2(576, 798)},
	{"room": "mr_frankys_inner", "scene": "res://scenes/MrFrankysInner.tscn",
		"bg": "mr_frankys_inner.png", "w": 1075.2, "solids": 10,
		"exit_to": "res://scenes/City.tscn", "exit_pos": Vector2(511, 693)},
	{"room": "warehouse_inner", "scene": "res://scenes/WarehouseInner.tscn",
		"bg": "warehouse_inner.png", "w": 2688.0, "solids": 14,
		"exit_to": "res://scenes/City.tscn", "exit_pos": Vector2(1398, 1822)},
]

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)

	for spec in SPECS:
		_check_room(spec)
	_check_scale_awareness()
	_check_klein_layering()
	_check_cathedral_untouched()
	_check_round_trips()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)

func _check_room(spec: Dictionary) -> void:
	var room_id: String = spec["room"]
	print("[%s]" % room_id)
	_ok(RoomGraph.has_room(room_id), "%s registered in RoomGraph.ROOMS" % room_id)
	_ok(RoomGraph.scene_for(room_id) == spec["scene"],
		"RoomGraph maps %s -> %s" % [room_id, spec["scene"]])
	# Two-way portal pair with the city (Klein parlor additionally chains to the bedroom;
	# checked in _check_klein_layering).
	_ok(not RoomGraph.portal("city", room_id).is_empty(), "portal city -> %s" % room_id)
	_ok(not RoomGraph.portal(room_id, "city").is_empty(), "portal %s -> city" % room_id)

	var packed: PackedScene = load(spec["scene"])
	if packed == null:
		_ok(false, "%s loads" % spec["scene"])
		return
	var room: Node = packed.instantiate()
	root.add_child(room)

	# Baked room photo at the scale that sets the room's WORLD size (bigger room = bigger
	# world-units extent, never a stretched collider box).
	var photo: Sprite2D = room.get_node_or_null("RoomPhoto")
	_ok(photo != null and photo.texture != null
		and photo.texture.resource_path.ends_with(spec["bg"]),
		"RoomPhoto -> %s" % spec["bg"])
	if photo != null and photo.texture != null:
		var world_w: float = photo.texture.get_size().x * photo.scale.x
		_ok(absf(world_w - float(spec["w"])) < 5.0,
			"room world width ~%.0f (got %.1f)" % [float(spec["w"]), world_w])

	# Walls + furniture blobs on one Solids StaticBody2D.
	var solids: Node = room.get_node_or_null("Solids")
	_ok(solids is StaticBody2D, "Solids is a StaticBody2D")
	var shapes: Array = _solid_shapes(solids)
	_ok(shapes.size() >= int(spec["solids"]),
		"Solids has >=%d collision shapes (got %d)" % [int(spec["solids"]), shapes.size()])

	# Player + camera.
	var player: Node2D = room.get_node_or_null("Player")
	var psprite: AnimatedSprite2D = room.get_node_or_null("Player/Sprite")
	_ok(psprite != null and psprite.sprite_frames != null
		and psprite.sprite_frames.has_animation("idle_s"),
		"Player sprite -> AnimatedSprite2D (idle_s)")
	var room_cam: Node = room.get_node_or_null("RoomCam")
	var player_cam: Camera2D = room.get_node_or_null("Player/Camera2D")
	_ok(room_cam is Camera2D or (player_cam != null and player_cam.enabled),
		"a camera covers the room (RoomCam or player-follow)")

	# The walk-in exit Portal back to where the player came from, standing where the
	# RoomGraph says the data-agents' portal is (same doorway for player and cult).
	var exit_area: Area2D = _find_portal(room, spec["exit_to"])
	_ok(exit_area != null, "walk-in Portal -> %s" % spec["exit_to"])
	if exit_area != null:
		var gp: Vector2 = exit_area.global_position
		_ok(gp.distance_to(spec["exit_pos"]) < 1.0,
			"exit portal at %s (got %s)" % [str(spec["exit_pos"]), str(gp)])
		var graph_from: Vector2 = RoomGraph.portal(room_id, "city").get("from_pos", Vector2.INF)
		_ok(gp.distance_to(graph_from) <= 40.0,
			"scene exit and RoomGraph from_pos agree within the crossing radius")
		# Door mouth clear: the straight walk from the player spawn out the door crosses
		# no wall/furniture collider.
		if player != null:
			_ok(_segment_clear(player.position, gp, shapes),
				"no collider blocks the door mouth (spawn -> exit)")

	room.free()

## The warehouse floor must read VAST: ~3x a Klein house room in linear extent, and
## clearly bigger than the mid-sized venues.
func _check_scale_awareness() -> void:
	print("[scale-aware grounds]")
	var klein_w := _world_width("res://scenes/KleinLivingRoom.tscn")
	var tavern_w := _world_width("res://scenes/LaughingEelTavern.tscn")
	var warehouse_w := _world_width("res://scenes/WarehouseInner.tscn")
	_ok(klein_w > 0.0 and tavern_w > 0.0 and warehouse_w > 0.0, "room widths resolve")
	_ok(warehouse_w >= 2.9 * klein_w,
		"warehouse ~3x Klein's rooms (%.0f vs %.0f)" % [warehouse_w, klein_w])
	_ok(warehouse_w >= 1.6 * tavern_w,
		"warehouse dwarfs the mid venues (%.0f vs tavern %.0f)" % [warehouse_w, tavern_w])
	_ok(tavern_w > 1.3 * klein_w, "tavern is mid-sized, bigger than a house room")

## Layered Klein house: city door -> parlor (klein_living_room) -> inner door -> the
## existing bedroom scene (IntroRoom.tscn as room 'klein_room'), and back out the same way.
func _check_klein_layering() -> void:
	print("[klein house layering]")
	_ok(RoomGraph.has_room("klein_room"), "klein_room (IntroRoom.tscn) registered")
	_ok(RoomGraph.scene_for("klein_room") == "res://scenes/IntroRoom.tscn",
		"klein_room -> IntroRoom.tscn")
	_ok(not RoomGraph.portal("klein_living_room", "klein_room").is_empty(),
		"portal parlor -> bedroom")
	_ok(not RoomGraph.portal("klein_room", "klein_living_room").is_empty(),
		"portal bedroom -> parlor")
	_ok(RoomGraph.portal("city", "klein_room").is_empty(),
		"no direct city -> bedroom edge (must pass through the parlor)")
	_ok(RoomGraph.next_hop("city", "klein_room") == "klein_living_room",
		"first hop city -> bedroom is the parlor")
	_ok(RoomGraph.next_hop("klein_room", "city") == "klein_living_room",
		"first hop bedroom -> city is the parlor")

	# The bedroom's E-door now leads deeper INTO the house, not straight to the street,
	# and it stands where the RoomGraph's bedroom->parlor edge crosses.
	var packed: PackedScene = load("res://scenes/IntroRoom.tscn")
	var bedroom: Node = packed.instantiate()
	root.add_child(bedroom)
	var door: Node2D = bedroom.get_node_or_null("Door")
	_ok(door != null and door.get("target_scene") == "res://scenes/KleinLivingRoom.tscn",
		"bedroom Door -> KleinLivingRoom.tscn")
	if door != null:
		var graph_from: Vector2 = RoomGraph.portal("klein_room", "klein_living_room") \
			.get("from_pos", Vector2.INF)
		_ok(door.global_position.distance_to(graph_from) <= 40.0,
			"bedroom door and RoomGraph from_pos agree")
	bedroom.free()

	# And the parlor has the matching inner door up to the bedroom.
	var parlor_scene: PackedScene = load("res://scenes/KleinLivingRoom.tscn")
	if parlor_scene != null:
		var parlor: Node = parlor_scene.instantiate()
		root.add_child(parlor)
		var inner: Area2D = _find_portal(parlor, "res://scenes/IntroRoom.tscn")
		_ok(inner != null, "parlor has the inner door -> IntroRoom.tscn")
		parlor.free()
	else:
		_ok(false, "KleinLivingRoom.tscn loads (for the inner-door check)")

## Chapel -> crypt layering predates this work and must not drift.
func _check_cathedral_untouched() -> void:
	print("[cathedral layering untouched]")
	var p: Dictionary = RoomGraph.portal("city", "cathedral_nave")
	_ok(not p.is_empty() and (p["from_pos"] as Vector2) == Vector2(2172, 5284),
		"city -> nave portal still at the chapel door")
	_ok(not RoomGraph.portal("cathedral_nave", "cathedral_crypt").is_empty()
		and not RoomGraph.portal("cathedral_crypt", "cathedral_nave").is_empty(),
		"nave <-> crypt edges intact")

## Data-agent round trips through the real crossing code (ActionCommit._move_to):
## start in the city near the door, walk IN (room flips to the interior), then walk back
## OUT (room flips to city) — for every new room, plus the two-hop Klein chain.
func _check_round_trips() -> void:
	print("[round trips: portal in -> room id -> portal back -> city]")
	for spec in SPECS:
		_round_trip(String(spec["room"]))
	# The layered chain: city -> parlor -> bedroom and all the way back.
	var a := Agent.new("rt_klein_chain")
	a.room = "city"
	var door_in: Dictionary = RoomGraph.portal("city", "klein_living_room")
	if door_in.is_empty():
		_ok(false, "klein chain: no city -> parlor portal")
		return
	a.position = (door_in["from_pos"] as Vector2) + Vector2(0, -120)
	ActionCommit.set_nav_site("rt_dest_klein_chain", Vector2(415, 470), "klein_room")
	var rooms_seen := {}
	for i in 400:
		rooms_seen[a.room] = true
		ActionCommit.commit({"verb": "move_to", "args": {"target": "rt_dest_klein_chain"}}, a)
		if a.room == "klein_room" \
				and a.position.distance_to(Vector2(415, 470)) <= 40.0:
			break
	_ok(rooms_seen.has("city") and rooms_seen.has("klein_living_room")
		and a.room == "klein_room",
		"chain walks city -> parlor -> bedroom (saw %s)" % [str(rooms_seen.keys())])
	ActionCommit.set_nav_site("rt_home_klein_chain",
		(door_in["from_pos"] as Vector2), "city")
	for i in 400:
		rooms_seen[a.room] = true
		ActionCommit.commit({"verb": "move_to", "args": {"target": "rt_home_klein_chain"}}, a)
		if a.room == "city":
			break
	_ok(a.room == "city", "chain returns bedroom -> parlor -> city")
	ActionCommit.NAV_SITES.erase("rt_dest_klein_chain")
	ActionCommit.NAV_SITES.erase("rt_home_klein_chain")

func _round_trip(room_id: String) -> void:
	var door_in: Dictionary = RoomGraph.portal("city", room_id)
	var door_out: Dictionary = RoomGraph.portal(room_id, "city")
	if door_in.is_empty() or door_out.is_empty():
		_ok(false, "%s: two-way portal pair missing, cannot round-trip" % room_id)
		return
	var a := Agent.new("rt_" + room_id)
	a.room = "city"
	a.position = (door_in["from_pos"] as Vector2) + Vector2(0, -120)
	var dest: Vector2 = door_in["to_pos"]
	ActionCommit.set_nav_site("rt_dest_" + room_id, dest, room_id)
	var crossed := false
	for i in 400:
		ActionCommit.commit({"verb": "move_to", "args": {"target": "rt_dest_" + room_id}}, a)
		if a.room == room_id:
			crossed = true
			break
	_ok(crossed, "%s: agent crossed in (room id correct)" % room_id)
	ActionCommit.set_nav_site("rt_home_" + room_id, door_in["from_pos"], "city")
	var back := false
	for i in 400:
		ActionCommit.commit({"verb": "move_to", "args": {"target": "rt_home_" + room_id}}, a)
		if a.room == "city":
			back = true
			break
	_ok(back and a.position.distance_to(door_out["to_pos"]) <= 80.0,
		"%s: agent crossed back out to the city door" % room_id)
	ActionCommit.NAV_SITES.erase("rt_dest_" + room_id)
	ActionCommit.NAV_SITES.erase("rt_home_" + room_id)

# ---------------------------------------------------------------- helpers

func _solid_shapes(solids: Node) -> Array:
	var out: Array = []
	if solids != null:
		for c in solids.get_children():
			if c is CollisionShape2D and (c as CollisionShape2D).shape is RectangleShape2D:
				out.append(c)
	return out

## First direct-child Area2D whose target_scene names `target` (the Portal.gd walk-in
## doors; Interactable doors also expose target_scene and count).
func _find_portal(room: Node, target: String) -> Area2D:
	for c in room.get_children():
		if c is Area2D and String(c.get("target_scene")) == target:
			return c
	return null

## True when no sampled point of segment a->b falls inside any Solids rect collider.
func _segment_clear(a: Vector2, b: Vector2, shapes: Array) -> bool:
	var steps: int = maxi(2, int(a.distance_to(b) / 15.0))
	for i in steps + 1:
		var p: Vector2 = a.lerp(b, float(i) / float(steps))
		for c in shapes:
			var cs := c as CollisionShape2D
			var local: Vector2 = cs.global_transform.affine_inverse() * p
			var half: Vector2 = (cs.shape as RectangleShape2D).size * 0.5
			if absf(local.x) <= half.x and absf(local.y) <= half.y:
				return false
	return true

func _world_width(scene_path: String) -> float:
	var packed: PackedScene = load(scene_path)
	if packed == null:
		return 0.0
	var n: Node = packed.instantiate()
	var photo: Sprite2D = n.get_node_or_null("RoomPhoto")
	var w: float = 0.0
	if photo != null and photo.texture != null:
		w = photo.texture.get_size().x * photo.scale.x
	n.free()
	return w

func _ok(cond: bool, label: String) -> void:
	if cond:
		_passed += 1
		print("  PASS  %s" % label)
	else:
		_failed += 1
		printerr("  FAIL  %s" % label)
