extends PanelContainer
## A left sidebar with the sim clock, a row of view controls (zoom out/in,
## reset view, heatmap — icon buttons cut from the Cute Fantasy UI pack's
## glyph sheets), playback controls, and a character list (each row has a
## "Track" button).
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
# The "Back to menu" button was pressed: return to the landing page (issue #399).
# The viewer handles it without shutting a live backend down (see _on_back_to_menu).
signal back_to_menu_requested

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

# The Cute Fantasy UI pack's glyph sheets (16 px grid). _pack_icon() slices one
# cell out and upscales it 2x so the pixel art stays crisp at button size; the
# column/row picked for each button is noted where it's used. The pack has no
# zoom glyph, so zoom borrows its plus/minus.
const BUTTON_GLYPHS := preload("res://Cute_Fantasy_UI/UI/UI_Button_Icons.png")
const MISC_GLYPHS := preload("res://Cute_Fantasy_UI/UI/UI_Icons.png")
const GLYPH_CELL := 16   # the sheets' cell size, px
const GLYPH_SCALE := 2   # 16 px cells → 32 px button icons

# The pack has no flame either, so Heatmap's glyph is drawn here pixel by pixel
# in the pack's own palette (its dark outline + its orange→yellow ramp, sampled
# from the plus/bolt glyphs), one string per row, so it sits next to the sheet
# icons without looking foreign.
const FLAME_PALETTE := {
	"#": Color("181425"),  # outline
	"o": Color("f77622"),  # orange rim
	"a": Color("feae34"),  # amber
	"y": Color("fee761"),  # yellow
	"w": Color("fff4b8"),  # white-hot core
}
const FLAME_ROWS: PackedStringArray = [
	"................",
	".......#........",
	"......#o#.......",
	"......#oo#......",
	".....#ooo#......",
	"....#ooooo#.....",
	"...#ooooooo#....",
	"..#oooaaaooo#...",
	"..#ooaayyaoo#...",
	".#ooaayyyyaoo#..",
	".#oaayywwyyao#..",
	".#oaaywwwyyao#..",
	".#oaayywyyyao#..",
	"..#oaayyyyao#...",
	"...##oaaao##....",
	".....#####......",
]

var _clock: Label
var _play: Button                   # play/pause toggle (icon set by set_playing)
# Pause/play glyphs, dark-brown row of the sheet (matches the theme's text).
var _icon_pause := _pack_icon(BUTTON_GLYPHS, 0, 1)
var _icon_play := _pack_icon(BUTTON_GLYPHS, 1, 1)
var _scrubber: HSlider              # timeline; value is the current frame index
var _speed_row: HBoxContainer       # the Speed picker row (hidden in live mode)
var _col: VBoxContainer             # the sidebar's main column (set_live adds rows)
var _transport_row: HBoxContainer   # pause/resume toggle + the step counter
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
# lazily on the first set_live(true). The timeline scrubber and the Speed
# picker leave the panel entirely -- there's no future to seek to and the
# backend sets the pace -- while the status line above them stays.
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
	_col = col

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

	# One toolbar row of icon buttons for the view controls: zoom out/in, reset
	# view, heatmap. Tooltips carry the words (and keyboard shortcuts) the old
	# text labels used to.
	var view_row := HBoxContainer.new()
	view_row.add_theme_constant_override("separation", 6)
	col.add_child(view_row)

	# Back to the landing menu (issue #399): the pack's house glyph — "home". Leads
	# the row so it reads as leaving the viewer, not a view control. A live sim keeps
	# running when you go back (the viewer doesn't shut the backend down).
	view_row.add_child(_icon_button(
		_pack_icon(BUTTON_GLYPHS, 6, 1), "Back to menu — a live simulation keeps running",
		func() -> void: back_to_menu_requested.emit()))

	# Zoom: the pack's outlined plus/minus (white row) — the neutral pair, so
	# they read as map controls rather than the green/red pickup variants.
	view_row.add_child(_icon_button(
		_pack_icon(MISC_GLYPHS, 6, 2), "Zoom out",
		func() -> void: zoom_out_requested.emit()))
	view_row.add_child(_icon_button(
		_pack_icon(MISC_GLYPHS, 0, 2), "Zoom in",
		func() -> void: zoom_in_requested.emit()))
	# Reset view: the pack's circular arrow — "put the view back".
	view_row.add_child(_icon_button(
		_pack_icon(BUTTON_GLYPHS, 30, 1), "Reset view — frame the whole campus (R / Home)",
		func() -> void: reset_requested.emit()))
	# Heatmap: the hand-drawn flame (see FLAME_ROWS).
	view_row.add_child(_icon_button(
		_flame_icon(), "Heatmap — where agents spend their time, up to now (H)",
		func() -> void: heatmap_requested.emit()))

	# Playback controls: a transport row (pause/resume beside the step counter),
	# a seekable timeline, and a speed picker.
	_transport_row = HBoxContainer.new()
	_transport_row.add_theme_constant_override("separation", 6)
	col.add_child(_transport_row)

	_play = _icon_button(_icon_pause, "Pause playback",
		func() -> void: play_pause_requested.emit())
	_play.size_flags_horizontal = Control.SIZE_FILL  # compact, not full-width
	_transport_row.add_child(_play)

	_step_label = Label.new()
	_step_label.text = "step — / —"
	_step_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_step_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_transport_row.add_child(_step_label)

	_scrubber = HSlider.new()
	_scrubber.min_value = 0
	_scrubber.max_value = 0
	_scrubber.step = 1
	_scrubber.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scrubber.value_changed.connect(_on_scrubber_changed)
	col.add_child(_scrubber)

	_speed_row = HBoxContainer.new()
	_speed_row.add_theme_constant_override("separation", 6)
	col.add_child(_speed_row)

	var speed_label := Label.new()
	speed_label.text = "Speed"
	speed_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_speed_row.add_child(speed_label)

	var speed := OptionButton.new()
	speed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for i in SPEEDS.size():
		speed.add_item("%sx" % _trim_speed(SPEEDS[i]), i)
		if SPEEDS[i] == 1.0:
			speed.select(i)  # default to real-time
	speed.item_selected.connect(func(i: int) -> void: speed_changed.emit(SPEEDS[i]))
	_speed_row.add_child(speed)

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


static func _pack_icon(sheet: Texture2D, glyph_col: int, glyph_row: int) -> Texture2D:
	# Cut one 16x16 cell out of a Cute Fantasy glyph sheet and upscale it with
	# nearest-neighbour, so buttons get a crisp 32 px pixel-art icon.
	var cell := sheet.get_image().get_region(Rect2i(
		glyph_col * GLYPH_CELL, glyph_row * GLYPH_CELL, GLYPH_CELL, GLYPH_CELL))
	cell.resize(GLYPH_CELL * GLYPH_SCALE, GLYPH_CELL * GLYPH_SCALE, Image.INTERPOLATE_NEAREST)
	return ImageTexture.create_from_image(cell)


static func _flame_icon() -> Texture2D:
	# Rasterize the FLAME_ROWS bitmap at the same size/scale as the sheet glyphs.
	var img := Image.create_empty(GLYPH_CELL, GLYPH_CELL, false, Image.FORMAT_RGBA8)
	for y in FLAME_ROWS.size():
		var row := FLAME_ROWS[y]
		for x in row.length():
			if FLAME_PALETTE.has(row[x]):
				img.set_pixel(x, y, FLAME_PALETTE[row[x]])
	img.resize(GLYPH_CELL * GLYPH_SCALE, GLYPH_CELL * GLYPH_SCALE, Image.INTERPOLATE_NEAREST)
	return ImageTexture.create_from_image(img)


func _icon_button(icon: Texture2D, tooltip: String, on_pressed: Callable) -> Button:
	# An icon-only button (the words live in the tooltip), sharing a row equally
	# with its siblings.
	var button := Button.new()
	button.icon = icon
	button.tooltip_text = tooltip
	button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.pressed.connect(on_pressed)
	return button


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
	_play.icon = _icon_pause if playing else _icon_play
	_play.tooltip_text = "Pause playback" if playing else "Resume playback"


func set_live(live: bool) -> void:
	# Live-follow mode (issue #263): show the LIVE badge + status line, and
	# drop the replay-only playback controls -- the timeline slider (no future
	# to scrub to; set_progress keeps the step label current instead) and the
	# Speed picker (the backend sets the pace, not the viewer).
	_scrubber.visible = not live
	_speed_row.visible = not live
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
		_col.add_child(_live_status)
		_col.move_child(_live_status, _transport_row.get_index() + 1)
		# The backend Start/Stop toggle lives right above the status line; it
		# stays hidden until the viewer learns the backend's run state.
		_live_run_btn = Button.new()
		_live_run_btn.visible = false
		_live_run_btn.pressed.connect(func(): live_run_toggle_requested.emit())
		_col.add_child(_live_run_btn)
		_col.move_child(_live_run_btn, _live_status.get_index())
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
