extends Node
## Dialogue system (autoload singleton `DialogueManager`).
##
## Loads branching, topic/clue-aware dialogue trees from data/dialogue.json and drives
## the on-screen DialoguePanel (which registers itself at runtime). Options can be gated
## behind unlocked topics/clues (layered questioning), can carry effects, and can be
## flagged as `contradiction` to render a clue call-out differently.
##
## Tree shape (per npc id):
##   { "start": "<node id>", "nodes": {
##       "<id>": { "speaker": "...", "text": "...", "options": [
##           { "label": "...", "goto": "<id>|end",
##             "requires_topic": "...", "requires_clue": "...",
##             "contradiction": true,
##             "effects": [ {type:"pressure",target,delta} | {type:"lead",text}
##                          | {type:"collect",clue} ] } ] } } }

signal dialogue_started(npc_id: String)
signal node_changed(speaker: String, text: String, options: Array)
signal dialogue_ended

const DIALOGUE_PATH: String = "res://data/dialogue.json"

var trees: Dictionary = {}
var _active_npc: String = ""
var _active_tree: Dictionary = {}
var active: bool = false

func _ready() -> void:
	_load()

func _load() -> void:
	if not FileAccess.file_exists(DIALOGUE_PATH):
		push_error("DialogueManager: missing %s" % DIALOGUE_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(DIALOGUE_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("DialogueManager: %s is not a JSON object" % DIALOGUE_PATH)
		return
	trees = parsed

func start(npc_id: String) -> void:
	if not trees.has(npc_id):
		push_warning("DialogueManager: no dialogue for '%s'" % npc_id)
		return
	_active_npc = npc_id
	_active_tree = trees[npc_id]
	active = true
	dialogue_started.emit(npc_id)
	_goto(String(_active_tree.get("start", "root")))

## Choose option `index` from the options last surfaced via node_changed.
func choose(node_id: String, option_index: int) -> void:
	var node: Dictionary = _active_tree.get("nodes", {}).get(node_id, {})
	var options := _visible_options(node)
	if option_index < 0 or option_index >= options.size():
		return
	var opt: Dictionary = options[option_index]
	for e in opt.get("effects", []):
		_apply_effect(e)
	var goto := String(opt.get("goto", "end"))
	if goto == "end" or goto == "":
		_end()
	else:
		_goto(goto)

func _goto(node_id: String) -> void:
	var nodes: Dictionary = _active_tree.get("nodes", {})
	if not nodes.has(node_id):
		_end()
		return
	var node: Dictionary = nodes[node_id]
	# Node-enter effects (optional).
	for e in node.get("effects", []):
		_apply_effect(e)
	_current_node_id = node_id
	node_changed.emit(String(node.get("speaker", "")), String(node.get("text", "")), _visible_options(node))

var _current_node_id: String = ""

func current_node_id() -> String:
	return _current_node_id

## Filter options by topic/clue gates so locked questions stay hidden.
func _visible_options(node: Dictionary) -> Array:
	var out: Array = []
	for opt in node.get("options", []):
		var req_topic := String(opt.get("requires_topic", ""))
		if req_topic != "" and not ClueDB.topic_unlocked(req_topic):
			continue
		var req_clue := String(opt.get("requires_clue", ""))
		if req_clue != "" and not ClueDB.is_collected(req_clue):
			continue
		# Gate on a live agent's current faction so options track the world's state, not just
		# the player's clue log. Orin's "persuade" line stays on offer while he's still "cult"
		# and vanishes the instant he's turned — you can't re-persuade someone already won over.
		var req_agent_faction: Dictionary = opt.get("requires_agent_faction", {})
		if not req_agent_faction.is_empty():
			var gated: Variant = Agents.get_agent(String(req_agent_faction.get("agent", "")))
			if gated == null or String(gated.faction) != String(req_agent_faction.get("faction", "")):
				continue
		out.append(opt)
	return out

func _apply_effect(e: Dictionary) -> void:
	match String(e.get("type", "")):
		"pressure":
			WorldState.adjust(StringName(e.get("target", "")), float(e.get("delta", 0.0)))
		"lead":
			WorldState.set_lead(String(e.get("text", "")))
		"collect":
			ClueDB.collect(String(e.get("clue", "")))
		"thought":
			WorldState.thought_requested.emit(String(e.get("text", "")))
		"social_influence":
			# Persuasion in conversation routes through the same player verb the console/world
			# use, so a wavering cultist talked round actually flips faction and adds impede.
			PlayerActions.social_influence(String(e.get("agent", "")))

func _end() -> void:
	active = false
	_active_npc = ""
	_active_tree = {}
	_current_node_id = ""
	dialogue_ended.emit()
