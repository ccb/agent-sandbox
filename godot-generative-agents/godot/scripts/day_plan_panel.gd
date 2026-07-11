extends Control
## The day-plans pop-up (issue #251): each agent's authored day as a "plan"
## ribbon beside an "actual" ribbon on one shared time axis, so plan-vs-reality
## drift (travel time, contention, detours) is visible at a glance. The actual
## ribbon fills only up to the current playback step — same "up to now"
## philosophy as the heatmap, and spoiler-free; a faded slot is transit toward
## that place, grey is off-plan. Click a ribbon to seek (the viewer ignores it
## in live mode). Like the other pop-ups this is pure UI: viewer.gd hands it
## the replay via set_replay() (frames BY REFERENCE, so live appends flow in)
## and drives it with show_up_to(step).

## Emitted when the user asks to close (the Close button or a backdrop click).
signal close_requested
## The user clicked a ribbon: seek to `step`. Routed to viewer's _on_seek,
## which guards live mode.
signal seek_requested(step: int)

const DayPlanModel := preload("res://scripts/day_plan_model.gd")

# Same modal wash as the heatmap/social-graph pop-ups.
const BACKDROP_COLOR := Color(0.06, 0.07, 0.10, 0.82)
# Colors assigned to scheduled places in order of first appearance — hues that
# stay apart on the parchment panel (pack blue/green + warm accents).
const PLACE_PALETTE := [
	Color("0099db"), Color("3e8948"), Color("feae34"), Color("7b4fbe"),
	Color("f77622"), Color("2c6e8f"), Color("b13e53"), Color("5d853a"),
]
const OTHER_COLOR := Color(0.55, 0.53, 0.50)   # off-plan / unscheduled
const TRANSIT_ALPHA := 0.45                     # faded destination color
const BAR_H := 14        # ribbon height, px
const BAR_GAP := 4       # gap between an agent's plan and actual bars
const ROW_GAP := 14      # gap between agents
const NAME_W := 150.0    # left column for agent names
const CURSOR_COLOR := Color(0.95, 0.30, 0.20)

var _frames: Array = []          # by reference from the viewer
var _names: Array = []
var _detail := {}                # name -> persona meta (schedule lives here)
var _step := 0                   # current playback step (show_up_to)
var _place_color := {}           # place name -> Color, from schedule order
var _planned := {}               # name -> Array of planned segments
var _planned_axis := -1          # axis the _planned cache was built at (invalidate when it grows)
var _slots := {}                 # name -> cached actual_slots
var _slots_at := -1              # _frames.size() the cache was built at
var _panel: PanelContainer
var _canvas: Control
var _legend: Label


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)

	var backdrop := ColorRect.new()
	backdrop.color = BACKDROP_COLOR
	backdrop.set_anchors_preset(Control.PRESET_FULL_RECT)
	backdrop.gui_input.connect(_on_backdrop_input)
	add_child(backdrop)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	# Clicks in the margin around the panel fall through to the backdrop.
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)

	_panel = PanelContainer.new()
	center.add_child(_panel)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 14)
	_panel.add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	margin.add_child(col)

	var title := Label.new()
	title.text = "Day plans — planned vs. actual, up to now"
	title.theme_type_variation = "TitleRibbon"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(title)

	_canvas = Control.new()
	_canvas.draw.connect(_draw_canvas)
	_canvas.gui_input.connect(_on_canvas_input)
	col.add_child(_canvas)

	_legend = Label.new()
	_legend.add_theme_font_size_override("font_size", 16)
	_legend.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	col.add_child(_legend)

	var close := Button.new()
	close.text = "Close"
	close.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	close.pressed.connect(func() -> void: close_requested.emit())
	col.add_child(close)


func set_replay(frames: Array, names: Array, persona_detail: Dictionary) -> void:
	# Hand-off from the viewer (baked load, live handshake, or reset respawn).
	# frames is held BY REFERENCE so live appends flow into the actual ribbons.
	_frames = frames
	_names = names
	_detail = persona_detail
	_slots.clear()
	_slots_at = -1
	# Palette: place -> color in order of first appearance across schedules,
	# shared by planned segments and actual slots so pairs read instantly.
	_place_color.clear()
	_planned.clear()
	_planned_axis = -1
	for name in _names:
		for stop in _schedule_of(String(name)):
			var place := String((stop as Dictionary).get("place", ""))
			if not _place_color.has(place):
				_place_color[place] = PLACE_PALETTE[_place_color.size() % PLACE_PALETTE.size()]
	var legend := PackedStringArray()
	for place in _place_color:
		legend.append("■ %s" % place)
	legend.append("■ off-plan / other (grey); faded = walking there")
	_legend.text = "   ".join(legend)
	# Height: one name line + two bars per agent. Width: a wide fixed canvas
	# (the panel centers on screen; the campus window is 1280+ wide).
	var row_h := BAR_H * 2 + BAR_GAP + ROW_GAP + 18
	_canvas.custom_minimum_size = Vector2(860, _names.size() * row_h)
	queue_redraw_all()


func show_up_to(step: int) -> void:
	_step = step
	queue_redraw_all()


func queue_redraw_all() -> void:
	if _canvas != null:
		_canvas.queue_redraw()


func _schedule_of(name: String) -> Array:
	return (_detail.get(name, {}) as Dictionary).get("schedule", []) as Array


func _axis() -> int:
	var schedules: Array = []
	for name in _names:
		schedules.append(_schedule_of(String(name)))
	return maxi(DayPlanModel.axis_len(_frames.size(), schedules), 1)


func _bars_x() -> float:
	return NAME_W


func _bars_w() -> float:
	return maxf(_canvas.size.x - NAME_W, 1.0)


func _row_top(idx: int) -> float:
	var row_h := BAR_H * 2 + BAR_GAP + ROW_GAP + 18
	return idx * row_h


func _ensure_slots() -> void:
	# Cache actual_slots per agent; rebuild only when the frame buffer grew
	# (live) or was swapped (reset) — the pass over frames is cheap but not
	# free at every redraw.
	if _slots_at == _frames.size():
		return
	_slots_at = _frames.size()
	for name in _names:
		_slots[name] = DayPlanModel.actual_slots(_frames, String(name))


func _draw_canvas() -> void:
	if _names.is_empty():
		return
	_ensure_slots()
	var axis := _axis()
	var font := get_theme_default_font()
	var font_size := get_theme_default_font_size()
	for idx in _names.size():
		var name := String(_names[idx])
		var top := _row_top(idx)
		_canvas.draw_string(font, Vector2(0, top + 14), name,
			HORIZONTAL_ALIGNMENT_LEFT, NAME_W - 8, font_size)
		var plan_y := top + 18
		var actual_y := plan_y + BAR_H + BAR_GAP
		# Planned ribbon: full width, known up front.
		var segs: Array = _planned_of(name, axis)
		if segs.is_empty():
			_canvas.draw_rect(Rect2(_bars_x(), plan_y, _bars_w(), BAR_H),
				Color(OTHER_COLOR, 0.5))
			_canvas.draw_string(font, Vector2(_bars_x() + 6, plan_y + 12),
				"no authored plan", HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
		for seg in segs:
			var x := _bars_x() + int(seg["start"]) / float(axis) * _bars_w()
			var w := int(seg["len"]) / float(axis) * _bars_w()
			_canvas.draw_rect(Rect2(x, plan_y, w, BAR_H),
				_color_for(String(seg["place"])))
		# Actual ribbon: only up to the current step, batched into runs of the
		# same color so a 1200-step day is a handful of rects, not 1200.
		var slots: Array = _slots.get(name, [])
		var upto := mini(_step, slots.size() - 1)
		var run_start := 0
		while run_start <= upto:
			var run_color := _slot_color(slots[run_start])
			var run_end := run_start
			while run_end + 1 <= upto and _slot_color(slots[run_end + 1]) == run_color:
				run_end += 1
			var x := _bars_x() + run_start / float(axis) * _bars_w()
			var w := (run_end - run_start + 1) / float(axis) * _bars_w()
			_canvas.draw_rect(Rect2(x, actual_y, w, BAR_H), run_color)
			run_start = run_end + 1
		# Now-cursor across both bars.
		var cx := _bars_x() + _step / float(axis) * _bars_w()
		_canvas.draw_rect(Rect2(cx - 1, plan_y - 2, 2, BAR_H * 2 + BAR_GAP + 4),
			CURSOR_COLOR)


func _planned_of(name: String, axis: int) -> Array:
	# The axis grows in live mode (axis_len tracks the frame count), and the
	# segments' start/len are laid out against it — a cache built for an older,
	# smaller axis would draw shrunken ribbons, so re-lay-out on any change.
	if axis != _planned_axis:
		_planned.clear()
		_planned_axis = axis
	if not _planned.has(name):
		_planned[name] = DayPlanModel.planned_segments(_schedule_of(name), axis)
	return _planned[name]


func _color_for(place: String) -> Color:
	return _place_color.get(place, OTHER_COLOR)


func _slot_color(slot: Dictionary) -> Color:
	match String(slot["kind"]):
		"at":
			return _color_for(String(slot["place"]))
		"transit":
			var c: Color = _color_for(String(slot["place"]))
			return Color(c, TRANSIT_ALPHA)
		_:
			return OTHER_COLOR


func _on_canvas_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton and event.pressed
			and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT):
		return
	var x := (event as InputEventMouseButton).position.x
	if x < _bars_x():
		return
	var step := clampi(roundi((x - _bars_x()) / _bars_w() * _axis()), 0,
		maxi(_frames.size() - 1, 0))
	seek_requested.emit(step)
	_canvas.accept_event()


func _get_tooltip(at_position: Vector2) -> String:
	# Anchored on the whole pop-up Control; translate into canvas space.
	var pos := at_position - _canvas.get_global_rect().position + get_global_rect().position
	return _canvas_tooltip(pos)


func _canvas_tooltip(pos: Vector2) -> String:
	if _names.is_empty() or pos.x < _bars_x():
		return ""
	_ensure_slots()
	var axis := _axis()
	var step := clampi(int((pos.x - _bars_x()) / _bars_w() * axis), 0, axis - 1)
	for idx in _names.size():
		var name := String(_names[idx])
		var top := _row_top(idx)
		var plan_y := top + 18
		var actual_y := plan_y + BAR_H + BAR_GAP
		if pos.y >= plan_y and pos.y < plan_y + BAR_H:
			var segs: Array = _planned_of(name, axis)
			for i in segs.size():
				var seg: Dictionary = segs[i]
				if step >= int(seg["start"]) and step < int(seg["start"]) + int(seg["len"]):
					return "%d. %s @ %s — %d steps" % [i + 1,
						String(seg["activity"]), String(seg["place"]), int(seg["len"])]
			return ""
		if pos.y >= actual_y and pos.y < actual_y + BAR_H:
			var slots: Array = _slots.get(name, [])
			if step >= slots.size() or step > _step:
				return ""
			var slot: Dictionary = slots[step]
			match String(slot["kind"]):
				"transit":
					return "walking to %s" % String(slot["place"])
				"at":
					return "at %s" % String(slot["place"])
				_:
					var b := String(slot["place"])
					return "off-plan: %s" % b if b != "" else "off-plan"
	return ""


func _on_backdrop_input(event: InputEvent) -> void:
	# A click on the dim outside the panel closes the pop-up (same contract as
	# the heatmap/social-graph backdrops).
	if event is InputEventMouseButton and event.pressed:
		close_requested.emit()
