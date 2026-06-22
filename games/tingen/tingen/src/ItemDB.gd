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
