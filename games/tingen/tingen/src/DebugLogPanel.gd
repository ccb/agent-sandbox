extends Panel
## Developer event log (toggle: F1). Where CultProgressPanel allow-lists only the events a
## player would plausibly know, this overlay shows EVERYTHING on the EventBus: every committed
## NPC action, every schema rejection / critic veto / overseer directive, the player's own
## verbs, and — once the LLM brain is wired — sidecar proposals and errors. It is the window
## into what the agent-sim and its brain are actually doing each beat.

const SHOWN: int = 50   # most-recent events rendered (EventBus keeps up to MAX_EVENTS)

# Color by category so the log scans at a glance.
const TYPE_COLORS: Dictionary = {
	"agent_action": Color(0.6, 0.85, 0.6),
	"agent_action_amended": Color(0.72, 0.85, 0.5),
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
	_summary.text = "%d events logged · showing last %d (newest first)" % [events.size(), mini(SHOWN, events.size())]
	var recent: Array = events.slice(maxi(0, events.size() - SHOWN))
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
	var head := "%s  %s" % [stamp, String(e.get("type", "")).replace("_", " ")]
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
