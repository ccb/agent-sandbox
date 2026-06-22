extends Node
## Occult toolkit coordinator (autoload `OccultToolManager`). Builds the tool instances
## from data/occult_tools.json, owns the SEEDED RNG (from WorldManager.seed_value) so risk
## rolls are deterministic, gates/uses tools, and surfaces directional leads through
## WorldState. The only thing the HUD talks to.

const TOOLS_PATH: String = "res://data/occult_tools.json"

## Maps a tool id to its subclass script.
const TOOL_SCRIPTS: Dictionary = {
	"divination": "res://src/DivinationTool.gd",
	"residue_sight": "res://src/ResidueSightTool.gd",
	"dream_fragments": "res://src/DreamFragmentsTool.gd",
	"gray_fog": "res://src/GrayFogTool.gd",
}

var _tools: Dictionary = {}   # id -> OccultTool
var _rng := RandomNumberGenerator.new()

func _ready() -> void:
	rebuild()

func rebuild() -> void:
	_tools.clear()
	_rng.seed = WorldManager.seed_value
	if not FileAccess.file_exists(TOOLS_PATH):
		push_error("OccultToolManager: missing %s" % TOOLS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(TOOLS_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("OccultToolManager: %s is not a JSON object" % TOOLS_PATH)
		return
	for id in parsed.keys():
		var script_path := String(TOOL_SCRIPTS.get(id, ""))
		if script_path == "" or not ResourceLoader.exists(script_path):
			continue
		var script: GDScript = load(script_path)
		_tools[id] = script.new(String(id), parsed[id])

func has_tool(id: String) -> bool:
	return _tools.has(id)

func can_use(id: String) -> bool:
	var t: OccultTool = _tools.get(id, null)
	return t != null and t.can_use()

## Use a tool; returns its result dict and surfaces any lead through WorldState.
func use(id: String) -> Dictionary:
	var t: OccultTool = _tools.get(id, null)
	if t == null:
		return {"ok": false, "kind": "unknown", "text": "No such tool.", "lead": "", "mislead": false}
	var res: Dictionary = t.use(_rng, WorldState.corruption)
	if res.get("ok", false) and String(res.get("lead", "")) != "":
		WorldState.set_lead(String(res["lead"]))
		EventBus.emit_event("player_occult", {"actor": "player", "tool": id, "mislead": res.get("mislead", false)})
	return res

## UI-facing snapshot of every tool: name, usage text, what it requires and costs, how many
## uses remain and whether it can be used right now. Sorted by name for a stable panel.
func tool_views() -> Array:
	var out: Array = []
	for id in _tools.keys():
		var t: OccultTool = _tools[id]
		out.append({
			"id": id,
			"name": String(t.def.get("name", id)),
			"description": String(t.def.get("description", "")),
			"requires_item": String(t.def.get("item_id", "")),
			"cost": t.compute_cost(),
			"produces": (t.def.get("produces", {}) as Dictionary).duplicate(true),
			"uses_left": t.uses_left,
			"can_use": t.can_use(),
		})
	out.sort_custom(func(a, b): return String(a["name"]) < String(b["name"]))
	return out

func to_dict() -> Dictionary:
	var uses: Dictionary = {}
	for id in _tools.keys():
		uses[id] = (_tools[id] as OccultTool).uses_left
	return {"uses_left": uses}

func from_dict(d: Dictionary) -> void:
	var uses: Dictionary = d.get("uses_left", {})
	for id in uses.keys():
		if _tools.has(id):
			(_tools[id] as OccultTool).uses_left = int(uses[id])
