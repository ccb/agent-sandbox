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
# The "Heatmap" button was pressed (open/close the movement-heatmap pop-up). The viewer
# owns the pop-up's visibility; this is just a request to toggle it (H does the same).
signal heatmap_requested
# The Focus dropdown changed: spotlight only agents in this building ("" = All, no
# filter). The viewer dims everyone elsewhere and glides the camera to the building.
signal filter_changed(location: String)
# The live Start/Stop button was pressed (live mode only). The viewer owns the
# backend's run state and pushes it back via set_live_run — the button flips
# when the backend confirms, not when clicked.
signal live_run_toggle_requested

# Tint applied to the active row so the tracked character is obvious at a glance.
const ACTIVE_TINT := Color(1.0, 0.95, 0.6)
# Non-matching rows fade to this alpha while a location filter is active, so the
# agents at the focused building stand out without the others vanishing entirely.
const ROW_DIM_ALPHA := 0.55
# Muted status line under each character's name — a soft brown that stays legible
# on the Cute Fantasy theme's light parchment panel (plain grey would wash out).
const STATUS_COLOR := Color(0.42, 0.32, 0.24)
# Playback speeds offered in the Speed dropdown.
const SPEEDS := [0.5, 1.0, 2.0, 4.0]

var _clock: Label
var _play: Button                   # play/pause toggle (label set by set_playing)
var _scrubber: HSlider              # timeline; value is the current frame index
var _step_label: Label              # "step N / total"
var _updating_scrubber := false     # true while we set the scrubber from playback
var _list: VBoxContainer            # holds one row per character
var _rows := {}                     # name -> {row, button, status: Label}
var _active := ""                   # name of the tracked character, or "" when free
var _filter_option: OptionButton    # the Focus (filter-by-location) dropdown
var _filter_locations: Array = []   # item index -> building name ("" = All locations)
var _dimmed := {}                   # names the filter has dimmed (set: name -> true)
# Live mode (issue #263): a red badge in the clock row plus a one-line status
# under the step label ("following backend" / "reconnecting…"); both built
# lazily on the first set_live(true). The scrubber locks -- you can't seek a
# live stream -- but keeps moving as a read-only progress bar.
var _live_badge: Label = null
var _live_status: Label = null
var _live_run_btn: Button = null    # backend Start/Stop toggle (set_live_run)


func _ready() -> void:
	custom_minimum_size = Vector2(300, 0)

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

	# A small "Time" caption stands in for a clock glyph — the Cute Fantasy pixel
	# font has no emoji, so an 🕗 would render as an empty box.
	var clock_icon := Label.new()
	clock_icon.text = "Time"
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
	zoom_out.text = "-"
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

	var heatmap := Button.new()
	heatmap.text = "Heatmap"
	heatmap.tooltip_text = "Where agents spend their time, up to now (H)"
	heatmap.pressed.connect(func() -> void: heatmap_requested.emit())
	col.add_child(heatmap)

	# Playback controls: pause/resume, a seekable timeline, and a speed picker.
	_play = Button.new()
	_play.text = "Pause"
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
		speed.add_item("%sx" % _trim_speed(SPEEDS[i]), i)
		if SPEEDS[i] == 1.0:
			speed.select(i)  # default to real-time
	speed.item_selected.connect(func(i: int) -> void: speed_changed.emit(SPEEDS[i]))
	speed_row.add_child(speed)

	# Focus: spotlight only the agents currently in a chosen building (everyone else
	# dims). The viewer fills the buildings via set_locations() after the replay loads;
	# until then it just offers "All locations" (no filter).
	var filter_row := HBoxContainer.new()
	filter_row.add_theme_constant_override("separation", 6)
	col.add_child(filter_row)

	var filter_label := Label.new()
	filter_label.text = "Focus"
	filter_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	filter_row.add_child(filter_label)

	_filter_option = OptionButton.new()
	_filter_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_filter_locations = [""]  # index 0 = "All locations" -> "" (no filter)
	_filter_option.add_item("All locations", 0)
	_filter_option.item_selected.connect(_on_filter_selected)
	filter_row.add_child(_filter_option)

	var title := Label.new()
	title.text = "CHARACTERS"
	# Sits on a Cute Fantasy ribbon banner (TitleRibbon variation in the theme),
	# centred across the sidebar width.
	title.theme_type_variation = "TitleRibbon"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_font_size_override("font_size", 30)
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
	status.add_theme_font_size_override("font_size", 16)
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


func set_locations(buildings: PackedStringArray) -> void:
	# Populate the Focus dropdown: "All locations" (no filter) plus one entry per
	# building the cast visits. The baked viewer calls this once after load; live
	# mode re-calls it as agents reach new buildings, so a current selection is
	# preserved when it's still in the list (select() doesn't re-emit the filter).
	var current := ""
	if _filter_option.selected >= 0 and _filter_option.selected < _filter_locations.size():
		current = _filter_locations[_filter_option.selected]
	_filter_option.clear()
	_filter_locations = [""]
	_filter_option.add_item("All locations", 0)
	for b in buildings:
		_filter_locations.append(b)
		_filter_option.add_item(b, _filter_locations.size() - 1)
	_filter_option.select(maxi(_filter_locations.find(current), 0))


func set_dimmed_rows(dimmed: PackedStringArray) -> void:
	# Which character rows the location filter has dimmed; rebuilt as a set each call
	# (empty = no filter). _refresh() folds this into the row tint alongside tracking.
	_dimmed.clear()
	for n in dimmed:
		_dimmed[n] = true
	_refresh()


func _on_filter_selected(idx: int) -> void:
	filter_changed.emit(_filter_locations[idx] if idx < _filter_locations.size() else "")


func set_playing(playing: bool) -> void:
	_play.text = "Pause" if playing else "Play"


func set_live(live: bool) -> void:
	# Live-follow mode (issue #263): lock the timeline (there's no future to
	# scrub to; set_progress still moves it as a read-only progress bar thanks
	# to the _updating_scrubber guard) and show the LIVE badge + status line.
	_scrubber.editable = not live
	if live and _live_badge == null:
		_live_badge = Label.new()
		_live_badge.text = "● LIVE"
		_live_badge.add_theme_color_override("font_color", Color(0.82, 0.20, 0.15))
		_live_badge.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		_clock.get_parent().add_child(_live_badge)
		_live_status = Label.new()
		_live_status.text = "connecting…"
		_live_status.add_theme_color_override("font_color", STATUS_COLOR)
		_live_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		var col := _step_label.get_parent()
		col.add_child(_live_status)
		col.move_child(_live_status, _step_label.get_index() + 1)
		# The backend Start/Stop toggle lives right above the status line; it
		# stays hidden until the viewer learns the backend's run state.
		_live_run_btn = Button.new()
		_live_run_btn.visible = false
		_live_run_btn.pressed.connect(func(): live_run_toggle_requested.emit())
		col.add_child(_live_run_btn)
		col.move_child(_live_run_btn, _live_status.get_index())
	if _live_badge != null:
		_live_badge.visible = live
		_live_status.visible = live
		_live_run_btn.visible = _live_run_btn.visible and live


func set_live_status(text: String) -> void:
	# One line of live-connection state ("following backend", "reconnecting…"),
	# driven by the viewer's socket + the feed's status records.
	if _live_status != null:
		_live_status.text = text


func set_live_run(state: String) -> void:
	## Reflect the BACKEND's run state on the sidebar Start/Stop toggle:
	## "waiting" = armed but never ticked (a --start-paused boot: the whole day
	## — and, with a real brain, the first paid model call — sits behind this
	## button), "running"/"paused" = the mid-day toggle, anything else (e.g.
	## "finished": resume can't restart a finished day; POST /reset can) hides
	## it. The viewer drives this from the feed's status records.
	if _live_run_btn == null:
		return
	match state:
		"waiting":
			_live_run_btn.visible = true
			_live_run_btn.text = "▶  Start simulation"
		"running":
			_live_run_btn.visible = true
			_live_run_btn.text = "⏹  Stop simulation"
		"paused":
			_live_run_btn.visible = true
			_live_run_btn.text = "▶  Resume simulation"
		_:
			_live_run_btn.visible = false


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


func toggle_track(name: String) -> void:
	# Public entry point for an out-of-panel trigger — e.g. clicking the agent's
	# sprite on the map. Behaves exactly like pressing that character's Track button
	# (toggles tracking + the row highlight and emits track/stop), so the two ways in
	# stay in lock-step. No-op for an unknown name.
	if _rows.has(name):
		_on_pressed(name)


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
	# Reflect _active + the location filter in every row (this is the single writer of
	# row.modulate): the tracked one is tinted and its button reads "Untrack", the rest
	# read "Track"; a row the filter dimmed fades out. Dim wins over the track tint, so a
	# tracked agent who is filtered out still reads as "not in the focused building".
	for n in _rows:
		var r: Dictionary = _rows[n]
		var is_active: bool = n == _active
		r["button"].text = "Untrack" if is_active else "Track"
		if _dimmed.has(n):
			r["row"].modulate = Color(1.0, 1.0, 1.0, ROW_DIM_ALPHA)
		else:
			r["row"].modulate = ACTIVE_TINT if is_active else Color.WHITE
