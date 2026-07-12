extends Node
## World ammo pickup placement (autoload `AmmoSpawn`) — M13.
##
## Places revolver_round pickups into RoomItems at the start of every run using the
## deterministic spawn table in data/scenario.json `ammo_spawn.spawns`. The spawn
## positions are fixed data; the selection of which spawns to activate is optionally
## seeded (by WorldManager.seed_value via RunManager._reset_run_world) so the same
## run seed always produces the same pickup layout — no RNG in combat, run-seeded
## world placement is fine (CLAUDE.md constraint).
##
## Reset seam: RunManager._reset_run_world calls RoomItems.clear() then AmmoSpawn.seed_run()
## so a fresh run places a clean set with no carry from the previous run (the sprint leak lesson).
##
## Mr Franky buy source: franky_buy() delegates to the Shop autoload (M15) — costed in coin and
## capped by a per-run stock latch, so the old free-grant tap is gone. Engine-neutral: no NPC-id
## branch — the shop prices/stock are data (scenario.json `shop`).

const SCENARIO_PATH := "res://data/scenario.json"
## Cache the spawn table once at load (static init), so tests that call seed_run()
## repeatedly don't parse JSON on every call.
static var _spawn_table: Array = _load_spawn_table()

static func _load_spawn_table() -> Array:
	if not FileAccess.file_exists(SCENARIO_PATH):
		push_warning("AmmoSpawn: missing %s" % SCENARIO_PATH)
		return []
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
	if not (parsed is Dictionary):
		return []
	var block: Variant = (parsed as Dictionary).get("ammo_spawn", {})
	if not (block is Dictionary):
		return []
	var raw: Variant = (block as Dictionary).get("spawns", [])
	return raw if raw is Array else []

## Place the full spawn table into RoomItems for a run seeded by `seed`. All listed
## spawns are placed (the table is designed so the total is balanced — TUNING: 24 rounds
## across 8 piles). The seed parameter is reserved for a future partial-table selection;
## today every entry is placed (the table itself is small and balanced).
func seed_run(seed: int = 0) -> void:
	var ri := _al("RoomItems")
	if ri == null:
		return
	for entry in _spawn_table:
		if not (entry is Dictionary):
			continue
		var room_id := String((entry as Dictionary).get("room", ""))
		var pos_arr: Variant = (entry as Dictionary).get("pos", [0, 0])
		var qty := int((entry as Dictionary).get("qty", 1))
		if room_id == "" or qty <= 0:
			continue
		var pos := Vector2.ZERO
		if pos_arr is Array and (pos_arr as Array).size() >= 2:
			pos = Vector2(float((pos_arr as Array)[0]), float((pos_arr as Array)[1]))
		ri.place(room_id, "revolver_round", pos, qty)
	# Unused seed parameter — reserved for future partial selection.
	# No-op today (all spawns always active, table is balanced).
	if seed == 0:
		pass   # silence the "unused" GDScript warning

## Place spawn entries for ONE specific room only. Used by CitySummoning._bootstrap to
## re-seed city ammo after clearing city-only ground items, without touching cathedral rooms.
func seed_run_room(room_id: String, seed: int = 0) -> void:
	var ri := _al("RoomItems")
	if ri == null:
		return
	for entry in _spawn_table:
		if not (entry is Dictionary):
			continue
		if String((entry as Dictionary).get("room", "")) != room_id:
			continue
		var pos_arr: Variant = (entry as Dictionary).get("pos", [0, 0])
		var qty := int((entry as Dictionary).get("qty", 1))
		if qty <= 0:
			continue
		var pos := Vector2.ZERO
		if pos_arr is Array and (pos_arr as Array).size() >= 2:
			pos = Vector2(float((pos_arr as Array)[0]), float((pos_arr as Array)[1]))
		ri.place(room_id, "revolver_round", pos, qty)
	if seed == 0:
		pass   # silence the "unused" GDScript warning

## All room ids that have ammo spawn entries (for test iteration).
func spawn_rooms() -> Array:
	var rooms: Array = []
	for entry in _spawn_table:
		if not (entry is Dictionary):
			continue
		var r := String((entry as Dictionary).get("room", ""))
		if r != "" and not rooms.has(r):
			rooms.append(r)
	return rooms

## Mr Franky interactable verb — M15: delegate to the Shop autoload's costed, stock-latched buy.
## The old cost-0 grant (a free infinite tap if wired naively — the M13 review warning) is GONE:
## this now refuses without coin and after the per-run restock cap. Returns the Shop verdict.
func franky_buy() -> Dictionary:
	var shop := _al("Shop")
	if shop == null:
		return {"ok": false, "reason": "no_shop"}
	return shop.buy_ammo()

func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
