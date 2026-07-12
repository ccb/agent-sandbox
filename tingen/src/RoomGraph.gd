class_name RoomGraph
extends RefCounted
## The room/portal graph for cross-scene NPC traversal (tingen_scene_graph_design.md §3).
##
## Rooms ARE scenes; portals are directed edges carrying the portal's position in the FROM room and
## the arrival position in the TO room. An agent's logical position is (room, local_pos); crossing a
## portal is a pure data update (set room + reposition), never a scene load — so an NPC can be deep in
## the crypt while the player is in the City. Hardcodes the cathedral path (City <-> Nave <-> Crypt),
## the seven painted interiors off their city buildings, and the LAYERED Klein house (city -> parlor ->
## bedroom; the bedroom hangs off the parlor, never off the street). Later this is derived by scanning
## Portal nodes in each scene. Pure static data + BFS — unit-testable with no scene tree.

const DEFAULT_ROOM := "city"

static var ROOMS: Dictionary = {
	"city": "res://scenes/City.tscn",
	"cathedral_nave": "res://scenes/CathedralNave.tscn",
	"cathedral_crypt": "res://scenes/CathedralCrypt.tscn",
	# The layered Klein house: the parlor fronts the street; the existing bedroom scene
	# (IntroRoom.tscn) is reached through it.
	"klein_living_room": "res://scenes/KleinLivingRoom.tscn",
	"klein_room": "res://scenes/IntroRoom.tscn",
	# The painted interiors (scale-aware: the warehouse floor is ~3x a Klein house room).
	"butcher_shop_inner": "res://scenes/ButcherShopInner.tscn",
	"laughing_eel_tavern": "res://scenes/LaughingEelTavern.tscn",
	"police_station_inner": "res://scenes/PoliceStationInner.tscn",
	"selena_almshouse_inner": "res://scenes/SelenaAlmshouseInner.tscn",
	"mr_frankys_inner": "res://scenes/MrFrankysInner.tscn",
	"warehouse_inner": "res://scenes/WarehouseInner.tscn",
}

## Directed portals. from_pos is in the FROM room's space; to_pos is where the agent arrives in the TO
## room. The City-side coordinate is the actual ChapelDoor trigger the player walks through —
## Chapel origin (2118, 5015) + ChapelDoor (-159, 242) + DoorShape (213.5, 27.5) = world (2172, 5284) —
## NOT the chapel body origin, so the cult walks to the same doorway the player uses and crosses there.
static var PORTALS: Array = [
	{"from": "city", "to": "cathedral_nave", "from_pos": Vector2(2172, 5284), "to_pos": Vector2(920, 1180)},
	{"from": "cathedral_nave", "to": "city", "from_pos": Vector2(920, 1200), "to_pos": Vector2(2172, 5284)},
	{"from": "cathedral_nave", "to": "cathedral_crypt", "from_pos": Vector2(1680, 160), "to_pos": Vector2(1260, 200)},
	{"from": "cathedral_crypt", "to": "cathedral_nave", "from_pos": Vector2(1260, 120), "to_pos": Vector2(1680, 320)},
	# --- The layered Klein house: street -> parlor -> bedroom, and back the same way. City-side
	# from_pos is the existing KleinHouse/KleinHouseDoor world position (retargeted to the parlor).
	{"from": "city", "to": "klein_living_room", "from_pos": Vector2(3070, 2655), "to_pos": Vector2(448, 520)},
	{"from": "klein_living_room", "to": "city", "from_pos": Vector2(448, 627), "to_pos": Vector2(3070, 2655)},
	{"from": "klein_living_room", "to": "klein_room", "from_pos": Vector2(430, -30), "to_pos": Vector2(760, 400)},
	{"from": "klein_room", "to": "klein_living_room", "from_pos": Vector2(845, 400), "to_pos": Vector2(430, 60)},
	# --- The painted interiors, one two-way pair each. Every city-side from_pos is the door
	# Area2D's world position on its building's street-facing edge in City.tscn; every interior
	# from_pos is that scene's walk-in exit Portal, just past the painted door mouth.
	# Kell's butcher shop fronts the Iron Cross Market's east face (his stall waypoints stand there).
	{"from": "city", "to": "butcher_shop_inner", "from_pos": Vector2(3590, 3650), "to_pos": Vector2(653, 780)},
	{"from": "butcher_shop_inner", "to": "city", "from_pos": Vector2(653, 900), "to_pos": Vector2(3590, 3650)},
	{"from": "city", "to": "laughing_eel_tavern", "from_pos": Vector2(2157.5, 4170.5), "to_pos": Vector2(783, 920)},
	{"from": "laughing_eel_tavern", "to": "city", "from_pos": Vector2(783, 1054), "to_pos": Vector2(2157.5, 4170.5)},
	{"from": "city", "to": "police_station_inner", "from_pos": Vector2(3885, 4735), "to_pos": Vector2(700, 870)},
	{"from": "police_station_inner", "to": "city", "from_pos": Vector2(700, 1003), "to_pos": Vector2(3885, 4735)},
	{"from": "city", "to": "selena_almshouse_inner", "from_pos": Vector2(4260, 1831.75), "to_pos": Vector2(570, 680)},
	{"from": "selena_almshouse_inner", "to": "city", "from_pos": Vector2(576, 798), "to_pos": Vector2(4260, 1831.75)},
	{"from": "city", "to": "mr_frankys_inner", "from_pos": Vector2(4735, 3645), "to_pos": Vector2(511, 580)},
	{"from": "mr_frankys_inner", "to": "city", "from_pos": Vector2(511, 693), "to_pos": Vector2(4735, 3645)},
	# The warehouse cargo door (bottom-center of the VAST floor); the painted west side door is a
	# player-only convenience exit in the scene — the graph carries the one canonical pair.
	{"from": "city", "to": "warehouse_inner", "from_pos": Vector2(5129.6, 2321.8), "to_pos": Vector2(1350, 1640)},
	{"from": "warehouse_inner", "to": "city", "from_pos": Vector2(1398, 1822), "to_pos": Vector2(5129.6, 2321.8)},
]

static func scene_for(room: String) -> String:
	return String(ROOMS.get(room, ""))

static func room_for_scene(scene_path: String) -> String:
	for r in ROOMS:
		if ROOMS[r] == scene_path:
			return r
	return ""

static func has_room(room: String) -> bool:
	return ROOMS.has(room)

## The directed portal from -> to, or {} if there is no direct edge.
static func portal(from_room: String, to_room: String) -> Dictionary:
	for p in PORTALS:
		if p["from"] == from_room and p["to"] == to_room:
			return p
	return {}

## BFS for the FIRST room to step into when traveling from_room -> to_room. Returns "" if already
## there or unreachable.
static func next_hop(from_room: String, to_room: String) -> String:
	if from_room == to_room or from_room == "" or to_room == "":
		return ""
	var queue: Array = [from_room]
	var prev: Dictionary = {from_room: ""}
	while not queue.is_empty():
		var cur: String = queue.pop_front()
		if cur == to_room:
			var node := to_room
			while prev[node] != from_room:
				node = prev[node]
			return node
		for p in PORTALS:
			if p["from"] == cur and not prev.has(p["to"]):
				prev[p["to"]] = cur
				queue.append(p["to"])
	return ""
