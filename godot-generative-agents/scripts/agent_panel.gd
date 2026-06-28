extends PanelContainer
## A left sidebar listing the replay's characters, each with a "Track" button.
##
## This panel is pure UI — it knows nothing about the camera or the agent nodes. The
## replay viewer (penn_replay.gd) fills it via add_character() and listens for the
## signals below to drive the camera; it also calls clear_active() when the camera
## stops following on its own (e.g. the user panned the map), so the highlight stays
## in sync. Rows are built in code (matching penn_replay's build-nodes-in-code style)
## so the scene file only needs the empty PanelContainer.

# A row's Track button was pressed and that character is not already being tracked.
signal track_requested(name: String)
# The currently-tracked character's button was pressed again (toggle off).
signal stop_requested

# Tint applied to the active row so the tracked character is obvious at a glance.
const ACTIVE_TINT := Color(1.0, 0.95, 0.6)

var _list: VBoxContainer            # holds one row per character
var _rows := {}                     # name -> {row: HBoxContainer, button: Button}
var _active := ""                   # name of the tracked character, or "" when free


func _ready() -> void:
	custom_minimum_size = Vector2(220, 0)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 10)
	add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	margin.add_child(col)

	var title := Label.new()
	title.text = "CHARACTERS"
	title.add_theme_font_size_override("font_size", 18)
	col.add_child(title)

	# Scroll the list if the cast outgrows the window height.
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	col.add_child(scroll)

	_list = VBoxContainer.new()
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_list.add_theme_constant_override("separation", 6)
	scroll.add_child(_list)


func add_character(name: String, thumb: Texture2D, tint: Color) -> void:
	# One row: sprite thumbnail + name + a Track button.
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)

	var icon := TextureRect.new()
	icon.texture = thumb
	icon.modulate = tint  # same per-persona tint as the world sprite
	icon.custom_minimum_size = Vector2(48, 48)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	row.add_child(icon)

	var label := Label.new()
	label.text = name
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL  # pushes the button right
	row.add_child(label)

	var button := Button.new()
	button.text = "Track"
	button.pressed.connect(_on_pressed.bind(name))
	row.add_child(button)

	_list.add_child(row)
	_rows[name] = {"row": row, "button": button}


func clear_active() -> void:
	# Drop the highlight without emitting (the camera already stopped on its own).
	if _active == "":
		return
	_active = ""
	_refresh()


func _on_pressed(name: String) -> void:
	if _active == name:
		_active = ""
		_refresh()
		stop_requested.emit()
	else:
		_active = name
		_refresh()
		track_requested.emit(name)


func _refresh() -> void:
	# Reflect _active in every row: the tracked one reads "Tracking" and is tinted.
	for n in _rows:
		var r: Dictionary = _rows[n]
		var is_active: bool = n == _active
		r["button"].text = "Tracking" if is_active else "Track"
		r["row"].modulate = ACTIVE_TINT if is_active else Color.WHITE
