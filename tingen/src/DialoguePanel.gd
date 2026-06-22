extends Control
## On-screen dialogue panel. Renders the current DialogueManager node + gated options
## as buttons. Pauses player movement while open. Lives inside the HUD.

@onready var _speaker: Label = $Box/Margin/Body/Speaker
@onready var _text: Label = $Box/Margin/Body/Text
@onready var _options: VBoxContainer = $Box/Margin/Body/Options

func _ready() -> void:
	visible = false
	DialogueManager.dialogue_started.connect(_on_started)
	DialogueManager.node_changed.connect(_on_node_changed)
	DialogueManager.dialogue_ended.connect(_on_ended)

func _on_started(_npc_id: String) -> void:
	visible = true
	get_tree().paused = false  # we don't pause the whole tree; gate the player instead

func _on_node_changed(speaker: String, text: String, options: Array) -> void:
	_speaker.text = speaker
	_speaker.visible = speaker != ""
	_text.text = text
	for c in _options.get_children():
		c.queue_free()
	var node_id := DialogueManager.current_node_id()
	for i in options.size():
		var opt: Dictionary = options[i]
		var b := Button.new()
		var label := String(opt.get("label", "..."))
		if bool(opt.get("contradiction", false)):
			label = "[!] " + label
			b.add_theme_color_override("font_color", Color(0.95, 0.7, 0.5))
		b.text = label
		b.pressed.connect(DialogueManager.choose.bind(node_id, i))
		_options.add_child(b)

func _on_ended() -> void:
	visible = false
