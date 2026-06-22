extends Panel
## Investigation Board modal. Renders collected clues dynamically, grouped by evidence
## type, plus open threads driven by the active lead. (Flat gallery — the drag-connect
## node graph is deferred per the design docs.)

const TYPE_ORDER: Array = ["physical", "behavioral", "occult", "testimony"]
const TYPE_LABEL: Dictionary = {
	"physical": "Physical Evidence",
	"behavioral": "Behavioural Evidence",
	"occult": "Occult Evidence",
	"testimony": "Testimony",
}
const TYPE_COLOR: Dictionary = {
	"physical": Color(0.7, 0.7, 0.74),
	"behavioral": Color(0.5, 0.75, 0.85),
	"occult": Color(0.7, 0.45, 0.85),
	"testimony": Color(0.45, 0.55, 0.8),
}

@onready var _list: VBoxContainer = $Margin/Body/Scroll/List

func _ready() -> void:
	ClueDB.clue_collected.connect(func(_id): _rebuild())
	WorldState.lead_changed.connect(func(_t): _rebuild())
	visibility_changed.connect(func(): if visible: _rebuild())
	_rebuild()

func _rebuild() -> void:
	if not is_instance_valid(_list):
		return
	for c in _list.get_children():
		c.queue_free()

	var groups := ClueDB.collected_by_type()
	if groups.is_empty():
		_add_label("No clues collected yet. Examine the scene (E).", Color(0.8, 0.8, 0.8), true)
	else:
		for t in TYPE_ORDER:
			if not groups.has(t):
				continue
			_add_label(TYPE_LABEL.get(t, t), TYPE_COLOR.get(t, Color.WHITE), false, 16)
			for clue in groups[t]:
				var imp := String(clue.get("importance", "flavor"))
				var mark := "*" if imp == "pivotal" else "-"
				_add_label("  %s %s" % [mark, clue.get("name", "?")], Color.WHITE)
				_add_label("      %s" % clue.get("description", ""), Color(0.72, 0.72, 0.76))

	_add_spacer()
	_add_label("Open threads", Color(0.85, 0.8, 0.6), false, 16)
	_add_label("  - " + WorldState.current_lead, Color(0.9, 0.9, 0.78))

func _add_label(text: String, color: Color, italic: bool = false, font_size: int = 0) -> void:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", color)
	if font_size > 0:
		l.add_theme_font_size_override("font_size", font_size)
	if italic:
		l.add_theme_color_override("font_color", color.darkened(0.1))
	_list.add_child(l)

func _add_spacer() -> void:
	var s := Control.new()
	s.custom_minimum_size = Vector2(0, 10)
	_list.add_child(s)
