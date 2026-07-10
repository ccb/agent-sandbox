extends Control
## A pop-up gallery of frame snapshots taken this session (issue #253). The sidebar's
## camera button (or the C key) captures the current campus view; viewer.gd hands each
## capture here via add_snapshot(texture, world_time). This panel just lists them:
## a scrollable grid of thumbnails, each captioned with the world timestamp it was
## taken at, and a click enlarges one to fill the panel (Back returns to the grid).
##
## Pure UI, built in code, modelled on social_graph_panel.gd / heatmap_panel.gd -- it
## knows nothing about the sim. Snapshots live only in memory for the session (there's
## no file export yet -- that's a separate, lower-priority follow-up).

## Emitted when the user asks to close the pop-up (the close button, or a click on the
## dimmed backdrop outside the panel). viewer.gd hides us and restores the camera.
signal close_requested

# Dark translucent wash over the whole screen behind the panel (matches the other
# modals), so the pop-up reads as a window.
const BACKDROP_COLOR := Color(0.06, 0.07, 0.10, 0.82)
const INK := Color(0.94, 0.92, 0.88)
const INK_DIM := Color(0.74, 0.72, 0.68)
# Grid thumbnail size (16:9, the window's aspect) and how many per row.
const THUMB := Vector2(340, 191)
const COLUMNS := 3

# One entry per capture: {texture: Texture2D, label: String}. Full-resolution textures
# kept in memory; a demo takes a handful.
# ponytail: unbounded session list; cap or downscale if a long demo run bloats memory.
var _shots: Array = []
var _detail_index := -1  # which snapshot the detail view shows, or -1 in the grid view

# Widgets, built in _ready().
var _title: Label
var _grid_scroll: ScrollContainer
var _grid: GridContainer
var _empty: Label
var _detail: VBoxContainer
var _detail_image: TextureRect
var _detail_caption: Label


func _ready() -> void:
	# Fill the screen so the backdrop can dim everything and catch a click-outside; start
	# hidden (viewer.gd flips us visible on open). A hidden Control is inert.
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	visible = false

	var backdrop := ColorRect.new()
	backdrop.color = BACKDROP_COLOR
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	backdrop.mouse_filter = Control.MOUSE_FILTER_STOP
	backdrop.gui_input.connect(_on_backdrop_input)
	add_child(backdrop)

	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)

	var panel := PanelContainer.new()
	panel.mouse_filter = Control.MOUSE_FILTER_STOP  # eat clicks so they don't pan the map
	panel.add_theme_stylebox_override("panel", _make_panel_style())
	center.add_child(panel)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 14)
	panel.add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	margin.add_child(col)

	# Title row: heading on the left, a close button on the right.
	var title_row := HBoxContainer.new()
	title_row.add_theme_constant_override("separation", 8)
	col.add_child(title_row)

	_title = Label.new()
	_title.add_theme_color_override("font_color", INK)
	_title.add_theme_font_size_override("font_size", 24)
	_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_row.add_child(_title)

	var close_btn := Button.new()
	close_btn.text = "Close  ✕"
	close_btn.tooltip_text = "Close (Esc)"
	close_btn.focus_mode = Control.FOCUS_NONE
	close_btn.pressed.connect(func() -> void: close_requested.emit())
	title_row.add_child(close_btn)

	# Grid view: a scrollable grid of thumbnails (vertical scroll only).
	_grid_scroll = ScrollContainer.new()
	_grid_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_grid_scroll.custom_minimum_size = Vector2(
		COLUMNS * THUMB.x + (COLUMNS + 1) * 10, 2.3 * (THUMB.y + 28))
	col.add_child(_grid_scroll)

	_grid = GridContainer.new()
	_grid.columns = COLUMNS
	_grid.add_theme_constant_override("h_separation", 10)
	_grid.add_theme_constant_override("v_separation", 10)
	_grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_grid_scroll.add_child(_grid)

	# Empty state (shown until the first capture), sized to match the grid area.
	_empty = Label.new()
	_empty.text = "No snapshots yet — press the camera button (or C) to capture the campus."
	_empty.add_theme_color_override("font_color", INK_DIM)
	_empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_empty.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_empty.custom_minimum_size = _grid_scroll.custom_minimum_size
	col.add_child(_empty)

	# Detail view: one snapshot enlarged, with a caption and a Back button. Hidden until
	# a thumbnail is clicked.
	_detail = VBoxContainer.new()
	_detail.add_theme_constant_override("separation", 8)
	_detail.visible = false
	col.add_child(_detail)

	_detail_image = TextureRect.new()
	_detail_image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_detail_image.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_detail_image.custom_minimum_size = Vector2(1280, 720)
	_detail.add_child(_detail_image)

	_detail_caption = Label.new()
	_detail_caption.add_theme_color_override("font_color", INK)
	_detail_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_detail_caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_detail.add_child(_detail_caption)

	var back_btn := Button.new()
	back_btn.text = "‹  Back to all"
	back_btn.focus_mode = Control.FOCUS_NONE
	back_btn.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	back_btn.pressed.connect(_show_grid)
	_detail.add_child(back_btn)

	_show_grid()


## Add a captured frame to the gallery (called by viewer.gd after each capture).
func add_snapshot(texture: Texture2D, label: String) -> void:
	var idx := _shots.size()
	_shots.append({"texture": texture, "label": label})

	var cell := VBoxContainer.new()
	cell.add_theme_constant_override("separation", 4)

	var thumb := TextureButton.new()
	thumb.texture_normal = texture
	thumb.ignore_texture_size = true
	thumb.stretch_mode = TextureButton.STRETCH_KEEP_ASPECT_CENTERED
	thumb.custom_minimum_size = THUMB
	thumb.tooltip_text = "Enlarge"
	thumb.pressed.connect(func() -> void: _show_detail(idx))
	cell.add_child(thumb)

	var caption := Label.new()
	caption.text = label
	caption.add_theme_color_override("font_color", INK_DIM)
	caption.add_theme_font_size_override("font_size", 13)
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	caption.custom_minimum_size = Vector2(THUMB.x, 0)
	cell.add_child(caption)

	_grid.add_child(cell)
	if _detail_index == -1:  # only refresh the grid framing while it's the shown view
		_show_grid()


## Reset to the grid view. viewer.gd calls this on open so we never reopen mid-detail.
func reset() -> void:
	_show_grid()


## Total snapshots taken (used by the headless smoke test).
func count() -> int:
	return _shots.size()


## Is the detail (enlarged) view showing? viewer.gd routes LEFT/RIGHT to us only then.
func in_detail() -> bool:
	return _detail_index != -1


## Step to the previous/next snapshot while in the detail view (wraps).
func nav_detail(delta: int) -> void:
	if _detail_index == -1 or _shots.is_empty():
		return
	_show_detail((_detail_index + delta + _shots.size()) % _shots.size())


func _show_grid() -> void:
	_detail_index = -1
	_detail.visible = false
	_grid_scroll.visible = not _shots.is_empty()
	_empty.visible = _shots.is_empty()
	_title.text = "Snapshots  (%d)" % _shots.size()


func _show_detail(i: int) -> void:
	if i < 0 or i >= _shots.size():
		return
	_detail_index = i
	var shot: Dictionary = _shots[i]
	_detail_image.texture = shot["texture"]
	_detail_caption.text = "%d / %d      ·      %s      ·      ← → browse" % [
		i + 1, _shots.size(), shot["label"]]
	_grid_scroll.visible = false
	_empty.visible = false
	_detail.visible = true
	_title.text = "Snapshot  %d / %d" % [i + 1, _shots.size()]


func _on_backdrop_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		close_requested.emit()
		accept_event()


func _make_panel_style() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.13, 0.17, 0.98)
	sb.set_corner_radius_all(10)
	sb.set_content_margin_all(4.0)
	sb.set_border_width_all(2)
	sb.border_color = Color(1.0, 0.97, 0.86, 0.35)
	return sb
