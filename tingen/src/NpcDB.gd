extends Node
## NPC data (autoload singleton `NpcDB`). Loads data/npcs.json: per-NPC display name,
## tint, dialogue link, and a phase->waypoint schedule (positions in the host scene's
## coordinate space). NPCs read their definition from here at runtime.
##
## Shape (per npc id):
##   { "name": "...", "dialogue_id": "...", "tint": [r,g,b],
##     "schedule": { "morning": [x,y], "night": [x,y], ... } }

const NPCS_PATH: String = "res://data/npcs.json"

var defs: Dictionary = {}

func _ready() -> void:
	if not FileAccess.file_exists(NPCS_PATH):
		push_error("NpcDB: missing %s" % NPCS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(NPCS_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("NpcDB: %s is not a JSON object" % NPCS_PATH)
		return
	defs = parsed

func get_def(npc_id: String) -> Dictionary:
	return defs.get(npc_id, {})

## Resolve the waypoint for a phase, falling back to the nearest earlier phase that
## has one (so a sparse schedule still works), else Vector2.ZERO.
func waypoint_for(npc_id: String, phase: String) -> Vector2:
	var sched: Dictionary = get_def(npc_id).get("schedule", {})
	if sched.has(phase):
		return _to_vec(sched[phase])
	# Fall back along the phase order.
	var order := ["late-night", "early-morning", "morning", "afternoon", "dusk", "night"]
	var idx := order.find(phase)
	for i in range(idx, -1, -1):
		if sched.has(order[i]):
			return _to_vec(sched[order[i]])
	# Or any defined entry.
	for k in sched.keys():
		return _to_vec(sched[k])
	return Vector2.ZERO

func _to_vec(arr: Variant) -> Vector2:
	if typeof(arr) == TYPE_ARRAY and arr.size() >= 2:
		return Vector2(float(arr[0]), float(arr[1]))
	return Vector2.ZERO
