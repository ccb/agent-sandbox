extends Panel
## Inspect card for one Agent (GDD §15). Opened by clicking an NPC
## (WorldState.inspect_requested). Shows the agent's live thought, current goal (its
## long-horizon intent) and recent actions, refreshing while open as beats advance.

@onready var _name: Label = $Margin/Body/Name
@onready var _sub: Label = $Margin/Body/Sub
@onready var _thought: Label = $Margin/Body/Thought
@onready var _goal: Label = $Margin/Body/Goal
@onready var _actions: VBoxContainer = $Margin/Body/Actions

var _agent_id: String = ""
## Agents whose /decide is currently in flight (P3): tracked off the typed `deciding` lifecycle
## fact, so the card can show a live THINKING tell instead of a stale thought while the LLM call
## runs, and restore the real thought the moment the decide lands.
var _thinking: Dictionary = {}

func _ready() -> void:
	visible = false
	WorldState.inspect_requested.connect(_open)
	EventBus.event_logged.connect(_on_event_logged)

func _on_event_logged(e: Dictionary) -> void:
	if String(e.get("type", "")) == "deciding":
		var d: Dictionary = e.get("data", {})
		var aid := String(d.get("agent", ""))
		if String(d.get("phase", "")) == "begin":
			_thinking[aid] = true
		else:
			_thinking.erase(aid)
	if visible:
		_refresh()

func shows_agent(id: String) -> bool:
	return visible and _agent_id == id

func _open(agent_id: String) -> void:
	_agent_id = agent_id
	visible = true
	_refresh()

func close() -> void:
	visible = false

func _refresh() -> void:
	var a: Agent = Agents.get_agent(_agent_id)
	if a == null:
		visible = false
		return
	_name.text = a.display_name
	_sub.text = String(a.role).capitalize()
	# P3 thinking tell: an in-flight decide (the `deciding begin` fact) shows as visible
	# deliberation; the end fact restores the live thought.
	_thought.text = "( thinking… )" if _thinking.has(_agent_id) else "\"%s\"" % a.describe_thought()
	_goal.text = a.intent
	# Free synchronously, not queue_free: several agents can act on one beat, so
	# event_logged may fire _refresh() twice in a single frame. queue_free defers
	# removal to end-of-frame, so the second pass would stack a duplicate action
	# list on top of children not yet reaped. free() clears them now.
	for c in _actions.get_children():
		c.free()
	var recent: Array = a.short_memory.slice(maxi(0, a.short_memory.size() - 5))
	if recent.is_empty():
		_add_action("(nothing yet)")
	else:
		for entry in recent:
			_add_action("• " + Agent.mem_text(entry))   # scored dict rows (P1) render their text

func _add_action(text: String) -> void:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", Color(0.78, 0.78, 0.82))
	_actions.add_child(l)

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_cancel"):
		close()
		get_viewport().set_input_as_handled()
