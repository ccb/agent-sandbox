class_name ActionSchema
extends RefCounted
## The one source of truth for the constrained agent action vocabulary. Loads
## data/action_schema.json (shared verbatim with the Python sidecar) and validates that
## a proposed action is (1) well-formed and (2) uses a known verb with its required args.
## This is the "legality: valid schema" half of the critic's legality axis (the
## "possible in current world state" half is checked at commit time, later).
##
## Action shape: { "actor": "<agent_id>", "verb": "<verb>", "args": { ... } }

const SCHEMA_PATH: String = "res://data/action_schema.json"

static var _verbs: Dictionary = {}   # verb -> Array[String] required arg names
static var _loaded: bool = false

static func _ensure_loaded() -> void:
	if _loaded:
		return
	_loaded = true
	if not FileAccess.file_exists(SCHEMA_PATH):
		push_error("ActionSchema: missing %s" % SCHEMA_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCHEMA_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("ActionSchema: %s is not a JSON object" % SCHEMA_PATH)
		return
	var verbs: Variant = parsed.get("verbs", {})
	if typeof(verbs) == TYPE_DICTIONARY:
		for v in verbs.keys():
			_verbs[String(v)] = (verbs[v] as Array).duplicate()

static func verbs() -> Array:
	_ensure_loaded()
	return _verbs.keys()

static func is_verb(verb: String) -> bool:
	_ensure_loaded()
	return _verbs.has(verb)

## Required arg names for a verb (empty Array if unknown or argless). Exposed so the
## cross-language parity test can compare the engine's *loaded* schema against the
## sidecar's, and so a future prompt-builder can describe each verb's arguments.
static func required_args(verb: String) -> Array:
	_ensure_loaded()
	return (_verbs.get(verb, []) as Array).duplicate()

## Returns { "ok": bool, "reason": String }. `reason` is "" when ok.
static func validate(action: Dictionary) -> Dictionary:
	_ensure_loaded()
	if String(action.get("actor", "")) == "":
		return {"ok": false, "reason": "missing actor"}
	var verb := String(action.get("verb", ""))
	if not _verbs.has(verb):
		return {"ok": false, "reason": "unknown verb '%s'" % verb}
	var args: Variant = action.get("args", {})
	if typeof(args) != TYPE_DICTIONARY:
		return {"ok": false, "reason": "args must be an object"}
	for required in _verbs[verb]:
		if not (args as Dictionary).has(required):
			return {"ok": false, "reason": "verb '%s' missing arg '%s'" % [verb, required]}
	return {"ok": true, "reason": ""}
