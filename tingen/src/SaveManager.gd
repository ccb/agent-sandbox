extends Node
## Save / load (autoload singleton `SaveManager`).
##
## Serializes the whole simulation — pressures + lead (WorldState), the clock,
## the hidden director (WorldManager), collected clues/topics (ClueDB) — plus the
## active scene path and the player's position, to a single JSON file in user://.
## Loading restores each subsystem via its from_dict() then asks GameController to
## swap to the saved scene and drop the player back where they were.
##
## Every persistent subsystem exposes the same to_dict()/from_dict() contract so the
## save format is just a dictionary of their dumps; adding a system means adding a key.

signal saved(path: String)
signal loaded(path: String)

const SAVE_PATH: String = "user://save.json"
const SAVE_VERSION: int = 1

func has_save() -> bool:
	return FileAccess.file_exists(SAVE_PATH)

func save_game(path: String = SAVE_PATH) -> bool:
	var gc := _game_controller()
	var data: Dictionary = {
		"version": SAVE_VERSION,
		"world_state": WorldState.to_dict(),
		"clock": Clock.to_dict(),
		"world_manager": WorldManager.to_dict(),
		"clues": ClueDB.to_dict(),
		"inventory": Inventory.to_dict(),
		"summoning_plan": SummoningPlan.to_dict(),
		"overseer": Overseer.to_dict(),
		"occult_tools": OccultToolManager.to_dict(),
		"prayer": PrayerService.to_dict(),
		"event_bus": EventBus.to_dict(),
		"agents": Agents.to_dict(),
		"scene_path": gc.current_scene_path if gc else "",
		"player_pos": _vec_to_arr(gc.player_position() if gc else Vector2.ZERO),
	}
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		push_error("SaveManager: cannot open %s for write (%d)" % [path, FileAccess.get_open_error()])
		return false
	f.store_string(JSON.stringify(data, "\t"))
	f.close()
	saved.emit(path)
	return true

func load_game(path: String = SAVE_PATH) -> bool:
	if not FileAccess.file_exists(path):
		push_warning("SaveManager: no save at %s" % path)
		return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("SaveManager: %s is not a JSON object" % path)
		return false
	var data: Dictionary = parsed

	# Restore data-only subsystems first; the scene swap reads from them.
	WorldManager.from_dict(data.get("world_manager", {}))
	ClueDB.from_dict(data.get("clues", {}))
	Clock.from_dict(data.get("clock", {}))
	WorldState.from_dict(data.get("world_state", {}))
	SummoningPlan.from_dict(data.get("summoning_plan", {}))
	Overseer.from_dict(data.get("overseer", {}))
	OccultToolManager.from_dict(data.get("occult_tools", {}))
	PrayerService.from_dict(data.get("prayer", {}))
	Inventory.from_dict(data.get("inventory", {}))
	EventBus.from_dict(data.get("event_bus", {}))
	Agents.from_dict(data.get("agents", {}))

	var gc := _game_controller()
	var scene_path := String(data.get("scene_path", ""))
	if gc and scene_path != "":
		gc.load_world_at(scene_path, _arr_to_vec(data.get("player_pos", [0, 0])))
	loaded.emit(path)
	return true

func _game_controller() -> Node:
	var nodes := get_tree().get_nodes_in_group("game_controller")
	return nodes[0] if nodes.size() > 0 else null

func _vec_to_arr(v: Vector2) -> Array:
	return [v.x, v.y]

func _arr_to_vec(a: Variant) -> Vector2:
	if typeof(a) == TYPE_ARRAY and (a as Array).size() >= 2:
		return Vector2(float(a[0]), float(a[1]))
	return Vector2.ZERO
