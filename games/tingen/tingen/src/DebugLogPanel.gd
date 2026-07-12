extends Panel
## Developer event log (toggle: L — the `toggle_debug` input action). It shows the EventBus, but unlike the raw firehose it once was,
## it now reads like a story beat sheet: the cult's secret deliberation noise (the raw "agent action —
## actor : verb" lines) is HIDDEN, and in its place we render human-readable consequences — NPCs walking
## between scenes, NPC dialogue, things picked up or laid down, blows landed, and tracked world variables
## shifting. The schema rejections / critic vetoes / player verbs / sidecar proposals + errors still show,
## so it stays the window into what the agent-sim and its brain are doing.

const SHOWN: int = 50   # most-recent events rendered (EventBus keeps up to MAX_EVENTS)

## The raw agent-deliberation events. Their bare "agent action — actor : verb" rendering is HIDDEN from
## this overlay (the after-game PlayLog .md still records every one of them in full). What the player
## sees instead is the readable CONSEQUENCE events these actions emit downstream — agent_moved_room,
## item_gathered, agent_attacked, world_var_changed, npc_said — rendered below.
const AGENT_ACTION_TYPES: Array = ["agent_action", "agent_action_amended", "overseer_directive"]

# Color by category so the log scans at a glance.
const TYPE_COLORS: Dictionary = {
	"agent_action": Color(0.6, 0.85, 0.6),
	"agent_action_amended": Color(0.72, 0.85, 0.5),
	"agent_moved_room": Color(0.6, 0.85, 0.7),
	"npc_said": Color(0.7, 0.88, 0.95),
	"item_gathered": Color(0.78, 0.82, 0.6),
	"material_deposited": Color(0.78, 0.82, 0.6),
	"agent_attacked": Color(0.95, 0.55, 0.45),
	"agent_downed": Color(0.95, 0.4, 0.4),
	"world_var_changed": Color(0.85, 0.78, 0.6),
	"overseer_directive": Color(0.8, 0.6, 0.9),
	"action_rejected": Color(0.9, 0.5, 0.45),
	"action_vetoed": Color(0.9, 0.55, 0.4),
	"directive_rejected": Color(0.9, 0.5, 0.45),
	"player_prayer": Color(0.55, 0.75, 0.9),
	"player_sabotage": Color(0.55, 0.75, 0.9),
	"player_social": Color(0.55, 0.75, 0.9),
	"player_occult": Color(0.55, 0.75, 0.9),
	"player_struck_down": Color(0.95, 0.4, 0.4),
	"endgame": Color(0.95, 0.8, 0.4),
	"summoning_climax": Color(0.95, 0.4, 0.4),
	"sidecar_error": Color(0.95, 0.5, 0.5),
	"sidecar_proposed": Color(0.5, 0.82, 0.85),
}

@onready var _brain: Label = $Margin/Body/Brain
@onready var _summary: Label = $Margin/Body/Summary
@onready var _list: VBoxContainer = $Margin/Body/Scroll/List

func _ready() -> void:
	visible = false
	EventBus.event_logged.connect(func(_e): if visible: refresh())

func toggle() -> void:
	visible = not visible
	if visible:
		refresh()

func refresh() -> void:
	_brain.text = _brain_line()
	var events: Array = EventBus.events()
	# The per-beat agent-deliberation events (move_to/idle/perform_ritual_step …) are the firehose and are
	# NOT shown in the panel — PlayLog still records them in the .md. The panel shows only the meaningful
	# CONSEQUENCES: scene transitions, dialogue, inventory / HP / world-var changes.
	var shown: Array = events.filter(func(e): return not (String(e.get("type", "")) in AGENT_ACTION_TYPES))
	_summary.text = "%d events · showing last %d meaningful (newest first)" % [events.size(), mini(SHOWN, shown.size())]
	var recent: Array = shown.slice(maxi(0, shown.size() - SHOWN))
	recent.reverse()
	# free() synchronously (not queue_free): event_logged can fire several times in one frame,
	# and a deferred free would let a second refresh stack duplicates onto unreaped children.
	for c in _list.get_children():
		c.free()
	if recent.is_empty():
		var empty := Label.new()
		empty.text = "No events yet. Wait for a beat (~15s) or take an action."
		empty.modulate = Color(0.6, 0.6, 0.65)
		_list.add_child(empty)
		return
	for e in recent:
		var l := Label.new()
		l.text = _format(e)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		var t := String(e.get("type", ""))
		if TYPE_COLORS.has(t):
			l.modulate = TYPE_COLORS[t]
		_list.add_child(l)

## The current brain: which SidecarClient subclass is serving proposals, plus the clock.
func _brain_line() -> String:
	var client: Object = SidecarBridge.client
	var brain := "none"
	if client != null and client.get_script() != null:
		brain = String(client.get_script().resource_path).get_file().get_basename()
	return "Brain: %s   ·   beat %d   ·   %s" % [brain, Clock.beat_index, Clock.hhmm()]

func _format(e: Dictionary) -> String:
	var data: Dictionary = e.get("data", {})
	var minute := int(e.get("minute", 0))
	var stamp := "d%d %02d:%02d b%d #%d" % [int(e.get("day", 1)), minute / 60, minute % 60, int(e.get("beat", 0)), int(e.get("seq", 0))]
	var t := String(e.get("type", ""))
	# Human-readable consequence/dialogue/world-var line, if this is one of the events we narrate.
	var story := _story_line(t, data)
	if story != "":
		return "%s  %s" % [stamp, story]
	# Everything else keeps the raw "type — actor : verb (detail)" rendering.
	var head := "%s  %s" % [stamp, t.replace("_", " ")]
	var who := String(data.get("actor", ""))
	if who != "":
		head += " — " + who
	var verb := String(data.get("verb", ""))
	if verb != "":
		head += " : " + verb
	var detail := _detail(data)
	if detail != "":
		head += "  (" + detail + ")"
	return head

## The narrated lines: NPC scene transitions, dialogue, inventory / HP / world-var changes, and the
## now-hidden raw agent action rendered (if at all) as its readable consequence. Returns "" for events
## that should keep the raw rendering. These are the lines that make the overlay read like a story.
func _story_line(t: String, data: Dictionary) -> String:
	match t:
		"agent_moved_room":
			return "%s moved from the %s to the %s." % [
				_name(String(data.get("actor", ""))), _room(String(data.get("from", ""))), _room(String(data.get("to", "")))]
		"npc_said":
			return '%s: "%s"' % [_name(String(data.get("agent", ""))), String(data.get("text", ""))]
		"item_gathered":
			return "%s picked up %s" % [_name(String(data.get("actor", ""))), _item(String(data.get("item_id", "")))]
		"material_deposited":
			return "%s laid %s at the altar" % [_name(String(data.get("actor", ""))), _item(String(data.get("item_id", "")))]
		"agent_attacked":
			return "%s struck (hp %d)" % [_name(String(data.get("target", ""))), int(data.get("target_hp", 0))]
		"agent_downed":
			return "%s downed" % _name(String(data.get("target", "")))
		"world_var_changed":
			return "%s %s → %s" % [_room(String(data.get("var", ""))), str(data.get("from", "")), str(data.get("to", ""))]
	return ""

## Surface the most useful field(s) per event without dumping the whole dict.
func _detail(data: Dictionary) -> String:
	if data.has("reason"):
		return "reason: " + String(data["reason"])
	var bits: PackedStringArray = []
	if data.has("god"):
		bits.append("god=" + String(data["god"]))
	var args: Variant = data.get("args", {})
	if args is Dictionary and not (args as Dictionary).is_empty():
		for k in (args as Dictionary).keys():
			bits.append("%s=%s" % [k, str((args as Dictionary)[k])])
	if data.get("outcome", null) is String:
		bits.append("outcome=" + String(data["outcome"]))
	if data.has("severity"):
		bits.append("sev=" + str(data["severity"]))
	return ", ".join(bits)

# --- readable-name helpers --------------------------------------------------------------------------
## An agent id -> a short readable name. Prefers the live agent's display_name; otherwise titlecases the
## last id segment ("fishwife_dalia" -> "Dalia", "clerk_voss" -> "Voss") to match the in-fiction voice.
func _name(agent_id: String) -> String:
	if agent_id == "":
		return "Someone"
	var ag := _al("Agents")
	if ag != null and ag.has_method("get_agent"):
		var a: Object = ag.get_agent(agent_id)
		if a != null and String(a.display_name) != "":
			return String(a.display_name)
	var seg := agent_id.get_slice("_", agent_id.get_slice_count("_") - 1)
	return seg.capitalize() if seg != "" else agent_id.capitalize()

## A room id -> readable words ("cathedral_crypt" -> "cathedral crypt").
func _room(room_id: String) -> String:
	return room_id.replace("_", " ") if room_id != "" else "?"

## An item id -> readable words ("ritual_salt" -> "ritual salt").
func _item(item_id: String) -> String:
	return item_id.replace("_", " ") if item_id != "" else "?"

## A move target (a site, an agent id, or "x,y") -> something readable.
func _humanize(target: String) -> String:
	if target == "":
		return "?"
	if "," in target:
		return "a spot"
	return target.replace("_", " ")

func _al(autoload_name: String) -> Node:
	var tree := get_tree()
	return tree.root.get_node_or_null("/root/" + autoload_name) if tree != null else null

# --- Test/debug seams -------------------------------------------------------------------
func line_count() -> int:
	return _list.get_children().size()

func newest_line() -> String:
	var kids: Array = _list.get_children()
	return (kids[0] as Label).text if not kids.is_empty() else ""

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		visible = false
		get_viewport().set_input_as_handled()
