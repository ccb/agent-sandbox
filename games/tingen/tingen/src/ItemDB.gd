extends Node
## Item definitions (autoload singleton `ItemDB`). Loads data/items.json once into
## an id -> ItemDef map for read-only lookup. Definitions are static content; they are
## never saved (the Inventory saves only counts and re-resolves defs from here).

const ITEMS_PATH: String = "res://data/items.json"

var _defs: Dictionary = {}  # id -> ItemDef

func _ready() -> void:
	_load()

func _load() -> void:
	if not FileAccess.file_exists(ITEMS_PATH):
		push_error("ItemDB: missing %s" % ITEMS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ITEMS_PATH))
	if typeof(parsed) != TYPE_ARRAY:
		push_error("ItemDB: %s is not a JSON array" % ITEMS_PATH)
		return
	for entry in parsed:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		var it: ItemDef = ItemDef.from_json(entry)
		if it.id == "":
			push_warning("ItemDB: item with no id skipped")
			continue
		_defs[it.id] = it

func has_def(id: String) -> bool:
	return _defs.has(id)

func get_def(id: String) -> ItemDef:
	return _defs.get(id, null)

func all_ids() -> Array:
	return _defs.keys()

## All item ids whose authored `tags` include `tag` — e.g. "gatherable", the player's walk-over
## ground-gather set (PlayerCombat). Sorted ascending so per-frame scans are deterministic. Pure
## data read: the set is exactly what items.json tags, never an engine list.
func ids_with_tag(tag: String) -> Array:
	var out: Array = []
	for id in _defs:
		if ((_defs[id] as ItemDef).tags as Array).has(tag):
			out.append(String(id))
	out.sort()
	return out

## The ONE resolution the executor cost seam needs: the item def (plain dict) of a CARRIED
## weapon — inventory count > 0 on `agent` — whose `grants` includes ability_id. `ammo` is not
## a built-in pool: the seam pays the cost in this weapon's `ammo_item` from the SAME per-agent
## inventory NPCs use, so any provider (player proxy today, an NPC provider later) resolves
## identically here. {} when no granting weapon is carried. Deterministic when several qualify:
## stable ascending item-id order picks the same weapon every time.
func weapon_for_ability(agent: Object, ability_id: String) -> Dictionary:
	if agent == null or ability_id == "" or not agent.has_method("item_count"):
		return {}   # duck-type guard: a count-less Object resolves to {}, never a call error
	var ids: Array = _defs.keys()
	ids.sort()
	for id in ids:
		var d: ItemDef = _defs[id]
		if d.category != "weapon" or not d.grants.has(ability_id):
			continue
		if int(agent.call("item_count", String(id))) > 0:
			return {
				"id": d.id,
				"name": d.name,
				"category": d.category,
				"grants": d.grants.duplicate(),
				"ammo_item": d.ammo_item,
			}
	return {}
