extends Node
## Clue / evidence model (autoload singleton `ClueDB`).
##
## Loads the clue library from data/clues.json and tracks which clues the player has
## collected and which dialogue topics they have unlocked as a result. Examining a
## world object collects its clue; the Investigation Board and dialogue system read
## from here.
##
## Canonical Clue shape (GDD §11 evidence layers + testimony):
##   { id, name, description, type, importance, location, topics[], linked_entities[] }
##   type       ∈ { physical, behavioral, occult, testimony }
##   importance ∈ { pivotal, supporting, flavor }

signal clue_collected(clue_id: String)
signal topics_changed

const CLUES_PATH: String = "res://data/clues.json"

var library: Dictionary = {}             # id -> clue def
var _collected: Dictionary = {}          # id -> discovered_at (refresh count)
var _unlocked_topics: Dictionary = {}    # topic -> true

func _ready() -> void:
	_load_library()

func _load_library() -> void:
	var defs := _read_json_array(CLUES_PATH)
	for d in defs:
		library[String(d["id"])] = d

## Collect a clue by id. Unlocks its topics and notifies listeners. No-op if unknown
## or already collected.
func collect(clue_id: String) -> bool:
	if not library.has(clue_id):
		push_warning("ClueDB.collect: unknown clue '%s'" % clue_id)
		return false
	if _collected.has(clue_id):
		return false
	_collected[clue_id] = WorldManager.refresh_count
	var topics: Array = library[clue_id].get("topics", [])
	var topic_added := false
	for t in topics:
		if not _unlocked_topics.has(String(t)):
			_unlocked_topics[String(t)] = true
			topic_added = true
	clue_collected.emit(clue_id)
	if topic_added:
		topics_changed.emit()
	return true

func is_collected(clue_id: String) -> bool:
	return _collected.has(clue_id)

func collected_count() -> int:
	return _collected.size()

func collected_clues() -> Array:
	var out: Array = []
	for id in _collected.keys():
		if library.has(id):
			out.append(library[id])
	return out

## Collected clues grouped by type, for the board.
func collected_by_type() -> Dictionary:
	var groups: Dictionary = {}
	for clue in collected_clues():
		var t := String(clue.get("type", "physical"))
		if not groups.has(t):
			groups[t] = []
		groups[t].append(clue)
	return groups

func topic_unlocked(topic: String) -> bool:
	return _unlocked_topics.has(topic)

func unlocked_topics() -> Array:
	return _unlocked_topics.keys()

func _read_json_array(path: String) -> Array:
	if not FileAccess.file_exists(path):
		push_error("ClueDB: missing data file %s" % path)
		return []
	var text := FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_ARRAY:
		push_error("ClueDB: %s is not a JSON array" % path)
		return []
	return parsed

func to_dict() -> Dictionary:
	return {
		"collected": _collected.duplicate(true),
		"topics": _unlocked_topics.keys(),
	}

func from_dict(d: Dictionary) -> void:
	_collected = (d.get("collected", {}) as Dictionary).duplicate(true)
	_unlocked_topics.clear()
	for t in d.get("topics", []):
		_unlocked_topics[String(t)] = true
	topics_changed.emit()
