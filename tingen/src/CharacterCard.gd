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

func _ready() -> void:
	visible = false
	WorldState.inspect_requested.connect(_open)
	EventBus.event_logged.connect(func(_e): if visible: _refresh())

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
	_sub.text = "%s · %s" % [String(a.faction).capitalize(), String(a.role).capitalize()]
	_thought.text = "\"%s\"" % a.describe_thought()
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
			_add_action("• " + String(entry))

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
