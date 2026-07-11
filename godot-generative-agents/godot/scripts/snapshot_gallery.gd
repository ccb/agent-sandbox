extends Control
## A pop-up gallery of frame snapshots taken this session (issue #253). The sidebar's
## camera button (or the C key) captures the current campus view; viewer.gd hands each
## capture here via add_snapshot(texture, world_time). This panel just lists them:
## a scrollable grid of thumbnails, each captioned with the world timestamp it was
## taken at, and a click enlarges one to fill the panel (Back returns to the grid).
##
## Pure UI, built in code, modelled on social_graph_panel.gd / heatmap_panel.gd -- it
## knows nothing about the sim. Snapshots live in memory for the session; the detail
## view's Save PNG (and the grid's desktop-only Save all) export them via
## scripts/snapshot_export.gd (issue #488 -- desktop writes to Pictures/penn-snapshots,
## the web build downloads). Clip export (GIF/MP4) stays a #488 follow-up.

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

const SnapshotExport := preload("res://scripts/snapshot_export.gd")

# One entry per capture: {texture: Texture2D, label: String}. Full-resolution textures
# kept in memory; a demo takes a handful.
# ponytail: unbounded session list; cap or downscale if a long demo run bloats memory.
var _shots: Array = []
var _detail_index := -1  # which snapshot the detail view shows, or -1 in the grid view
var _last_saved_path := ""  # the detail view's last successful save, for Reveal

# Widgets, built in _ready().
var _title: Label
var _grid_scroll: ScrollContainer
var _grid: GridContainer
var _empty: Label
var _detail: VBoxContainer
var _detail_image: TextureRect
var _detail_caption: Label
var _save_btn: Button
var _reveal_btn: Button
var _save_status: Label
var _save_all_btn: Button
var _grid_status: Label


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

	# Grid-view export status ("3 saved -> ...") sits left of the buttons.
	_grid_status = Label.new()
	_grid_status.add_theme_color_override("font_color", INK_DIM)
	_grid_status.add_theme_font_size_override("font_size", 13)
	title_row.add_child(_grid_status)

	_save_all_btn = Button.new()
	_save_all_btn.text = "Save all"
	_save_all_btn.tooltip_text = "Save every snapshot as a PNG (Pictures/penn-snapshots)"
	_save_all_btn.focus_mode = Control.FOCUS_NONE
	_save_all_btn.pressed.connect(_save_all)
	title_row.add_child(_save_all_btn)

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

	# Save / Reveal / Back on one centered row; the status line under it says
	# where the PNG went (issue #488).
	var btn_row := HBoxContainer.new()
	btn_row.add_theme_constant_override("separation", 8)
	btn_row.alignment = BoxContainer.ALIGNMENT_CENTER
	_detail.add_child(btn_row)

	_save_btn = Button.new()
	_save_btn.text = "Save PNG"
	_save_btn.focus_mode = Control.FOCUS_NONE
	_save_btn.pressed.connect(_save_current)
	btn_row.add_child(_save_btn)

	_reveal_btn = Button.new()
	_reveal_btn.text = "Reveal in Finder"
	_reveal_btn.focus_mode = Control.FOCUS_NONE
	_reveal_btn.visible = false
	_reveal_btn.pressed.connect(_reveal_last)
	btn_row.add_child(_reveal_btn)

	var back_btn := Button.new()
	back_btn.text = "‹  Back to all"
	back_btn.focus_mode = Control.FOCUS_NONE
	back_btn.pressed.connect(_show_grid)
	btn_row.add_child(back_btn)

	_save_status = Label.new()
	_save_status.add_theme_color_override("font_color", INK_DIM)
	_save_status.add_theme_font_size_override("font_size", 13)
	_save_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_save_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_detail.add_child(_save_status)

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
	# Save all is a grid-view, desktop-only affordance (N programmatic browser
	# downloads trip popup blockers). Statuses reset on every view switch and
	# new capture so a stale "saved" claim never lingers over a different shot.
	_save_all_btn.visible = not _shots.is_empty() and not OS.has_feature("web")
	_grid_status.text = ""
	_save_status.text = ""
	_reveal_btn.visible = false


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
	# Entering the detail view (or arrowing to a different shot) drops any
	# stale save status: it described a different snapshot.
	_save_all_btn.visible = false
	_grid_status.text = ""
	_save_status.text = ""
	_reveal_btn.visible = false


func _on_backdrop_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		close_requested.emit()
		accept_event()


func _save_current() -> void:
	# Export the shown snapshot (issue #488). The capture index keeps the file
	# name deterministic, so re-saving a shot overwrites its earlier file.
	if _detail_index == -1:
		return
	var shot: Dictionary = _shots[_detail_index]
	var path: String = SnapshotExport.save(
		shot["texture"], _detail_index, shot["label"])
	if path == "":
		_save_status.text = "save failed — see console"
		_reveal_btn.visible = false
		return
	_last_saved_path = path
	_save_status.text = "saved → %s" % path
	# The browser surfaces its own download UI; revealing is a desktop thing.
	_reveal_btn.visible = not OS.has_feature("web")


func _reveal_last() -> void:
	if _last_saved_path != "":
		OS.shell_show_in_file_manager(_last_saved_path)


func _save_all() -> void:
	# Export every shot through the same helper (desktop only; the button is
	# hidden on web). Partial failure names the count; details are on the
	# console via the helper's push_error.
	var saved := 0
	var dir := ""
	for i in _shots.size():
		var shot: Dictionary = _shots[i]
		var path: String = SnapshotExport.save(shot["texture"], i, shot["label"])
		if path != "":
			saved += 1
			dir = path.get_base_dir()
	if saved == _shots.size() and saved > 0:
		_grid_status.text = "%d saved → %s" % [saved, dir]
	else:
		_grid_status.text = "%d of %d saved — see console" % [saved, _shots.size()]


func _make_panel_style() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.13, 0.17, 0.98)
	sb.set_corner_radius_all(10)
	sb.set_content_margin_all(4.0)
	sb.set_border_width_all(2)
	sb.border_color = Color(1.0, 0.97, 0.86, 0.35)
	return sb
