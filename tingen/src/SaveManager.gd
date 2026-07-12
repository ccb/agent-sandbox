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

## THE single source of truth for which run-scoped subsystems get persisted, and in what RESTORE
## order (each entry: [json_key, autoload_name]). BOTH the disk save (save_game/load_game) AND the
## in-memory checkpoint (RunManager._snapshot/_restore) build their subsystem payload from THIS list,
## so the two paths can never drift on membership again (B3, M21 — they had silently diverged:
## meters/progression/leads/shop rode the in-memory snapshot but were dropped from the disk save,
## so a cross-session Continue lost them). Ordering constraints baked into the list:
##   * Meters AFTER WorldState — Meters.from_dict re-derives Doom/Notice from the restored pressures.
##   * everything else is independent, so the order is otherwise the historical disk order.
## /root lookups keep it tolerant of a subsystem absent under a partial test harness (e.g. Shop).
const SUBSYSTEMS: Array = [
	["world_manager", "WorldManager"],
	["clues", "ClueDB"],
	["clock", "Clock"],
	["world_state", "WorldState"],
	["meters", "Meters"],
	["summoning_plan", "SummoningPlan"],
	["overseer", "Overseer"],
	["occult_tools", "OccultToolManager"],
	["prayer", "PrayerService"],
	["deeds", "DeedRunner"],
	["inventory", "Inventory"],
	["agents", "Agents"],
	["event_bus", "EventBus"],
	["progression", "Progression"],
	["leads", "LeadSystem"],
	["shop", "Shop"],
]

func has_save() -> bool:
	return FileAccess.file_exists(SAVE_PATH)

## Build {json_key: subsystem.to_dict()} for every present subsystem in the manifest. The ONE seam
## the disk save and the in-memory checkpoint share, so their key sets are identical by construction.
func subsystem_dump() -> Dictionary:
	var out: Dictionary = {}
	for entry in SUBSYSTEMS:
		var node := _subsystem(String(entry[1]))
		if node != null and node.has_method("to_dict"):
			out[String(entry[0])] = node.to_dict()
	return out

## Apply a saved payload back onto the subsystems, in manifest (restore) order. Absent keys fall
## through to each from_dict's own defaults (older saves that predate a subsystem).
func apply_subsystem_dump(data: Dictionary) -> void:
	for entry in SUBSYSTEMS:
		var node := _subsystem(String(entry[1]))
		if node != null and node.has_method("from_dict"):
			node.from_dict(data.get(String(entry[0]), {}))

func save_game(path: String = SAVE_PATH) -> bool:
	var gc := _game_controller()
	var data: Dictionary = subsystem_dump()
	data["version"] = SAVE_VERSION
	data["scene_path"] = gc.current_scene_path if gc else ""
	data["player_pos"] = _vec_to_arr(gc.player_position() if gc else Vector2.ZERO)
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

	# Restore data-only subsystems first (manifest order); the scene swap below reads from them.
	apply_subsystem_dump(data)

	var gc := _game_controller()
	var scene_path := String(data.get("scene_path", ""))
	if gc and scene_path != "":
		gc.load_world_at(scene_path, _arr_to_vec(data.get("player_pos", [0, 0])))
	loaded.emit(path)
	return true

## Resolve a subsystem autoload by name via /root — class_name-safe under the headless -s harness
## and tolerant of an autoload absent under a partial harness (returns null).
func _subsystem(name: String) -> Node:
	var tree := get_tree()
	return tree.root.get_node_or_null("/root/" + name) if tree != null else null

func _game_controller() -> Node:
	var nodes := get_tree().get_nodes_in_group("game_controller")
	return nodes[0] if nodes.size() > 0 else null

func _vec_to_arr(v: Vector2) -> Array:
	return [v.x, v.y]

func _arr_to_vec(a: Variant) -> Vector2:
	if typeof(a) == TYPE_ARRAY and (a as Array).size() >= 2:
		return Vector2(float(a[0]), float(a[1]))
	return Vector2.ZERO
