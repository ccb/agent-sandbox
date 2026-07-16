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

## N1 (sprint safety): the ACTIVE save slot — REDIRECTABLE so test harnesses never overwrite the
## real player's user://save.json (the nightly-checkpoint disk save used to stomp it on every
## harness run). Live play never touches this default; every harness redirects it into
## user://test_sandbox/<run>/ via src/TestSandbox.gd `activate()`, whose write guard also REFUSES
## any out-of-sandbox write while a harness is running.
var save_path: String = SAVE_PATH
const _TSandbox := preload("res://src/TestSandbox.gd")

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
	# N3 (B-F2): the RUN SESSION block — day / live flag / ritual latch / checkpoint day / run
	# knowledge ledger (RunManager.to_dict, deliberately WITHOUT the checkpoint payload: the disk
	# save IS the nightly checkpoint mirror, so RunManager.resume_from_save rebuilds the in-memory
	# checkpoint from this whole payload instead of nesting snapshots inside snapshots). LAST so
	# its from_dict can lean on the already-restored Clock.
	["run_manager", "RunManager"],
]

func has_save() -> bool:
	return FileAccess.file_exists(save_path)

## N3 (B-F5): a run that ENDED (win / lose / final death) must not leave a resumable ghost —
## RunManager's full-run-end finalizer deletes the save slot so the title's Continue greys out.
## Routed through the sandbox write guard like every persistent mutation; idempotent (a missing
## file is already invalid).
func invalidate_save(path: String = "") -> void:
	if path.is_empty():
		path = save_path
	if not _TSandbox.guard_write(path):
		return
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))

## N3 — the payload of the most recent successful load_game() (a deep copy). The seam
## RunManager.resume_from_save() reads to rebuild the in-memory nightly checkpoint after a
## cross-session Continue (the disk save IS the checkpoint mirror). {} until a load succeeds.
var _last_loaded: Dictionary = {}

func last_loaded_payload() -> Dictionary:
	return _last_loaded.duplicate(true)

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

func save_game(path: String = "") -> bool:
	if path.is_empty():
		path = save_path
	# N1: under an active test sandbox, a save targeted outside user://test_sandbox/ is refused.
	if not _TSandbox.guard_write(path):
		return false
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

func load_game(path: String = "") -> bool:
	if path.is_empty():
		path = save_path
	if not FileAccess.file_exists(path):
		push_warning("SaveManager: no save at %s" % path)
		return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("SaveManager: %s is not a JSON object" % path)
		return false
	var data: Dictionary = parsed
	_last_loaded = data.duplicate(true)

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
