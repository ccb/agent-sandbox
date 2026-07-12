extends Node
## Per-room ground items (autoload `RoomItems`) — tingen_scene_graph_design.md §6.
##
## Items lie in a room at a local position, as DATA, independent of whether that scene is loaded.
## NPCs gather them off the ground (ActionCommit.gather_item); the crypt altar's deposited materials
## are just ground items placed at the altar. RoomView renders the ground items of whatever room the
## player is currently in. Pure data + a `changed` signal so the renderer can refresh.

signal changed

const MERGE_DIST := 8.0   # items dropped within this distance stack instead of duplicating

var _rooms: Dictionary = {}   # room_id -> Array[ {item_id:String, pos:Vector2, qty:int} ]

## Drop `qty` of `item_id` on the ground at `pos` in `room`, stacking onto a nearby like item.
## `gatherable` false marks a pile that renders but can't be picked back up — e.g. materials laid
## at the altar, so a cultist with a spare hand doesn't undo a deposit by re-gathering it.
func place(room: String, item_id: String, pos: Vector2, qty: int = 1, gatherable: bool = true) -> void:
	var arr: Array = _rooms.get(room, [])
	for e in arr:
		if String(e["item_id"]) == item_id and bool(e.get("gatherable", true)) == gatherable \
				and (e["pos"] as Vector2).distance_to(pos) < MERGE_DIST:
			e["qty"] = int(e["qty"]) + qty
			_rooms[room] = arr
			changed.emit()
			return
	arr.append({"item_id": item_id, "pos": pos, "qty": qty, "gatherable": gatherable})
	_rooms[room] = arr
	changed.emit()

## The ground items in a room (live array; treat as read-only).
func items_in(room: String) -> Array:
	return _rooms.get(room, [])

## Total count of an item in a room ("" = any item).
func count(room: String, item_id: String = "") -> int:
	var n := 0
	for e in _rooms.get(room, []):
		if item_id == "" or String(e["item_id"]) == item_id:
			n += int(e["qty"])
	return n

## Take ONE unit of `item_id` ("" = any) from `room`, the nearest within `radius` of `pos`.
## Returns the item id taken, or "" if nothing matched in range.
func take_near(room: String, item_id: String, pos: Vector2, radius: float) -> String:
	var arr: Array = _rooms.get(room, [])
	var best := -1
	var best_d := radius
	for i in arr.size():
		var e: Dictionary = arr[i]
		if (item_id == "" or String(e["item_id"]) == item_id) and int(e["qty"]) > 0 \
				and bool(e.get("gatherable", true)):
			var d: float = pos.distance_to(e["pos"])
			if d <= best_d:
				best_d = d
				best = i
	if best < 0:
		return ""
	var taken := String(arr[best]["item_id"])
	arr[best]["qty"] = int(arr[best]["qty"]) - 1
	if int(arr[best]["qty"]) <= 0:
		arr.remove_at(best)
	_rooms[room] = arr
	changed.emit()
	return taken

func clear() -> void:
	_rooms.clear()
	changed.emit()
