class_name GodDB
extends RefCounted
## Read-only loader for the focused Tingen pantheon (data/gods.json). Pure data access,
## shared by the prayer adjudicator (MockSidecar) and the prayer panel. Mirrors the
## ActionSchema static-loader pattern, so no extra autoload is needed and a class_name
## script can read it without the _al() dance.

const PATH: String = "res://data/gods.json"

static var _defs: Dictionary = {}
static var _loaded: bool = false

static func _ensure_loaded() -> void:
	if _loaded:
		return
	_loaded = true
	if not FileAccess.file_exists(PATH):
		push_error("GodDB: missing %s" % PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	if typeof(parsed) == TYPE_DICTIONARY:
		_defs = parsed

## Sorted god ids (stable order for the panel).
static func ids() -> Array:
	_ensure_loaded()
	var k: Array = _defs.keys()
	k.sort()
	return k

static func has(id: String) -> bool:
	_ensure_loaded()
	return _defs.has(id)

## A copy of one god's def ({} if unknown).
static func get_def(id: String) -> Dictionary:
	_ensure_loaded()
	return (_defs.get(id, {}) as Dictionary).duplicate(true)

## Every god as a def dict with its "id" folded in, in sorted-id order.
static func all() -> Array:
	_ensure_loaded()
	var out: Array = []
	for id in ids():
		var d: Dictionary = get_def(id)
		d["id"] = id
		out.append(d)
	return out
