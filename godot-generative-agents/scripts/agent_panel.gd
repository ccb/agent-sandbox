extends PanelContainer
## A left sidebar with the sim clock, zoom controls, and a character list (each
## row has a "Track" button).
##
## This panel is pure UI — it knows nothing about the camera or the agent nodes. The
## replay viewer (penn_replay.gd) fills it via add_character(), drives the clock via
## set_clock_text(), and listens for the signals below to drive the camera; it also
## calls clear_active() when the camera stops following on its own (e.g. the user
## panned the map), so the highlight stays in sync. Rows are built in code (matching
## penn_replay's build-nodes-in-code style) so the scene file only needs the empty
## PanelContainer.

# A row's Track button was pressed and that character is not already being tracked.
signal track_requested(name: String)
# The currently-tracked character's button was pressed again (toggle off).
signal stop_requested
signal zoom_in_requested
signal zoom_out_requested
# The play/pause button was pressed (the viewer owns the playing/paused state and
# pushes it back via set_playing).
signal play_pause_requested
# The user dragged the timeline scrubber to `step` (0-based frame index).
signal seek_requested(step: int)
# The user picked a playback speed (1.0 = real-time per the replay's step rate).
signal speed_changed(multiplier: float)
# The "Reset view" button was pressed.
signal reset_requested

# Tint applied to the active row so the tracked character is obvious at a glance.
const ACTIVE_TINT := Color(1.0, 0.95, 0.6)
# Greyed status line under each character's name.
const STATUS_COLOR := Color(0.75, 0.75, 0.75)
# Playback speeds offered in the Speed dropdown.
const SPEEDS := [0.5, 1.0, 2.0, 4.0]

var _clock: Label
var _play: Button                   # play/pause toggle (glyph set by set_playing)
var _scrubber: HSlider              # timeline; value is the current frame index
var _step_label: Label              # "step N / total"
var _updating_scrubber := false     # true while we set the scrubber from playback
var _list: VBoxContainer            # holds one row per character
var _rows := {}                     # name -> {row, button, status: Label}
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

	var clock_row := HBoxContainer.new()
	clock_row.add_theme_constant_override("separation", 6)
	col.add_child(clock_row)

	var clock_icon := Label.new()
	clock_icon.text = "🕗"
	clock_icon.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	clock_row.add_child(clock_icon)

	_clock = Label.new()
	_clock.text = "—"
	_clock.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_clock.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_clock.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	clock_row.add_child(_clock)

	var zoom_row := HBoxContainer.new()
	zoom_row.add_theme_constant_override("separation", 6)
	col.add_child(zoom_row)

	var zoom_out := Button.new()
	zoom_out.text = "−"
	zoom_out.tooltip_text = "Zoom out"
	zoom_out.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	zoom_out.pressed.connect(func() -> void: zoom_out_requested.emit())
	zoom_row.add_child(zoom_out)

	var zoom_in := Button.new()
	zoom_in.text = "+"
	zoom_in.tooltip_text = "Zoom in"
	zoom_in.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	zoom_in.pressed.connect(func() -> void: zoom_in_requested.emit())
	zoom_row.add_child(zoom_in)

	var reset := Button.new()
	reset.text = "Reset view"
	reset.tooltip_text = "Frame the whole campus (R / Home)"
	reset.pressed.connect(func() -> void: reset_requested.emit())
	col.add_child(reset)

	# Playback controls: pause/resume, a seekable timeline, and a speed picker.
	_play = Button.new()
	_play.text = "⏸ Pause"
	_play.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_play.pressed.connect(func() -> void: play_pause_requested.emit())
	col.add_child(_play)

	_step_label = Label.new()
	_step_label.text = "step — / —"
	col.add_child(_step_label)

	_scrubber = HSlider.new()
	_scrubber.min_value = 0
	_scrubber.max_value = 0
	_scrubber.step = 1
	_scrubber.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scrubber.value_changed.connect(_on_scrubber_changed)
	col.add_child(_scrubber)

	var speed_row := HBoxContainer.new()
	speed_row.add_theme_constant_override("separation", 6)
	col.add_child(speed_row)

	var speed_label := Label.new()
	speed_label.text = "Speed"
	speed_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	speed_row.add_child(speed_label)

	var speed := OptionButton.new()
	speed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for i in SPEEDS.size():
		speed.add_item("%s×" % _trim_speed(SPEEDS[i]), i)
		if SPEEDS[i] == 1.0:
			speed.select(i)  # default to real-time
	speed.item_selected.connect(func(i: int) -> void: speed_changed.emit(SPEEDS[i]))
	speed_row.add_child(speed)

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


func set_clock_text(text: String) -> void:
	_clock.text = text


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

	# Name on top, a small greyed status line (current activity) beneath it.
	var text_col := VBoxContainer.new()
	text_col.size_flags_horizontal = Control.SIZE_EXPAND_FILL  # pushes the button right
	text_col.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(text_col)

	var label := Label.new()
	label.text = name
	text_col.add_child(label)

	var status := Label.new()
	status.text = ""
	status.add_theme_font_size_override("font_size", 12)
	status.add_theme_color_override("font_color", STATUS_COLOR)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text_col.add_child(status)

	var button := Button.new()
	button.text = "Track"
	button.pressed.connect(_on_pressed.bind(name))
	row.add_child(button)

	_list.add_child(row)
	_rows[name] = {"row": row, "button": button, "status": status}


func set_character_status(name: String, text: String) -> void:
	# Update a character row's activity line (no-op if the name isn't present).
	if _rows.has(name):
		_rows[name]["status"].text = text


func set_playing(playing: bool) -> void:
	_play.text = "⏸ Pause" if playing else "▶ Play"


func set_progress(step: int, total: int) -> void:
	# Reflect playback position in the scrubber + step label. The guard stops our own
	# write from firing value_changed and looking like a user seek.
	_updating_scrubber = true
	if _scrubber.max_value != total:
		_scrubber.max_value = total
	_scrubber.value = step
	_updating_scrubber = false
	_step_label.text = "step %d / %d" % [step, total]


func _on_scrubber_changed(value: float) -> void:
	if _updating_scrubber:
		return  # playback moved the slider, not the user
	seek_requested.emit(int(value))


func _trim_speed(s: float) -> String:
	# "0.5" / "1" / "2" — drop a trailing ".0" so whole speeds read cleanly.
	return ("%.1f" % s).trim_suffix(".0")


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
	# Reflect _active in every row: the tracked one is tinted and its button reads
	# "Untrack" (press it to stop), the rest read "Track".
	for n in _rows:
		var r: Dictionary = _rows[n]
		var is_active: bool = n == _active
		r["button"].text = "Untrack" if is_active else "Track"
		r["row"].modulate = ACTIVE_TINT if is_active else Color.WHITE
