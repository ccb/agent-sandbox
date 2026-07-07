extends Control
## A pop-up movement heatmap: WHERE the agents spend their time, up to the current
## playback step. Open it at any point (the H key or the sidebar "Heatmap" button) and
## it overlays a dimmed copy of the campus with a per-tile "dwell" heat painted on top.
##
## Two things make it more than a static overlay:
##   * Live — the viewer pushes the current step in as playback advances, so the heat
##     keeps accumulating while the sim plays on behind the pop-up (no pause).
##   * Switchable — LEFT / RIGHT cycle the view between "All agents" (a combined warm
##     ramp) and each individual persona (drawn in that persona's own tint), so you can
##     compare who lingers where.
##
## Like agent_panel.gd and minimap.gd this is pure UI: it knows nothing about the sim
## until viewer.gd hands it the replay via set_replay(), then drives it with
## show_up_to(step) and cycle_view(delta). It renders the campus a second time into an
## off-screen SubViewport (exactly like minimap.gd) so the heat sits over the real map.

## The campus map to draw under the heat -- the same .tmj the main scene renders.
@export_file("*.tmj") var map_path: String = "res://maps/upenn_core_urban.tmj"
## The heat picture is sized to the map's shape (so it isn't stretched) within this
## fraction of the viewport's smaller side. The Penn campus is a tall portrait block.
@export var max_viewport_fraction: float = 0.78
## Render the off-screen campus this many times larger than it's shown, then shrink it,
## so the heavily-minified map reads as a smooth picture (matches minimap's supersample).
@export var supersample: int = 2

## Emitted when the user asks to close the pop-up (the close button, or a click on the
## dimmed backdrop outside the panel). viewer.gd hides us and restores the camera.
signal close_requested

# Dark translucent wash over the whole screen behind the panel (the fog's tone), so the
# pop-up reads as a modal window and the campus/heat pop against it.
const BACKDROP_COLOR := Color(0.06, 0.07, 0.10, 0.82)
# A second dim, drawn over the campus picture but UNDER the heat, so faint heat still
# reads against the bright daytime map.
const MAP_DIM := Color(0.05, 0.05, 0.08, 0.55)
# Per-persona tints, kept in step with viewer.gd's TINTS (shared by the sprite, the
# sidebar row and the minimap dot) so an agent's heat matches its dot colour.
const TINTS := [
	Color(1.0, 0.95, 0.95),  # Maya    - warm white
	Color(0.70, 0.82, 1.0),  # Ellis   - blue
	Color(0.80, 1.0, 0.78),  # Diego   - green
	Color(1.0, 0.86, 0.70),  # Priya   - amber
	Color(1.0, 0.95, 0.55),  # Marcus  - yellow
	Color(1.0, 0.78, 0.92),  # Tanaka  - pink
	Color(0.70, 1.0, 0.97),  # Sofia   - cyan
]
# Ink that stays legible on the dark panel.
const INK := Color(0.94, 0.92, 0.88)
const INK_DIM := Color(0.74, 0.72, 0.68)
# Alpha range for a single agent's tint: faintest (few visits) -> solid (most time).
const AGENT_ALPHA_LOW := 0.15
const AGENT_ALPHA_HIGH := 0.92

# The replay, handed over by set_replay(); until then we draw nothing.
var _frames: Array = []
var _names: Array = []
var _tile_px := 16
# The map's footprint in world pixels -- the single source of truth for the
# world->canvas transform (same idea as minimap._bounds).
var _bounds := Rect2()
var _subviewport: SubViewport = null
# The dwell grid for the shown view: tile (Vector2i) -> visit count, plus the largest
# count in it (to normalise the colour ramp). Rebuilt by _recompute().
var _grid := {}
var _max_count := 1
# The playhead the heat is accumulated up to, and which view is shown (0 = all agents
# combined, 1..N = persona _names[view - 1]).
var _step := -1
var _view_index := 0
# The combined-view colour ramp (warm "ember": dark/faint at low dwell -> bright/opaque).
var _gradient: Gradient = null

# Widgets, built in code in _ready() (agent_panel.gd style).
var _panel: PanelContainer
var _canvas: Control
var _title: Label
var _legend: TextureRect
var _hint: Label


func _ready() -> void:
	# Fill the screen so the backdrop can dim everything and catch a click-outside;
	# start hidden (viewer.gd flips us visible on open). A hidden Control neither
	# draws nor handles input, so this is inert until opened. Use the ..._and_offsets_...
	# variant so the offsets are zeroed too -- anchors alone leave a 0-size rect.
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	visible = false
	_build_gradient()

	# The dark wash over the whole screen. STOP so a click on it (outside the panel)
	# closes, and so clicks don't fall through to the camera drag/zoom behind us.
	var backdrop := ColorRect.new()
	backdrop.color = BACKDROP_COLOR
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	backdrop.mouse_filter = Control.MOUSE_FILTER_STOP
	backdrop.gui_input.connect(_on_backdrop_input)
	add_child(backdrop)

	# A full-screen CenterContainer centres the window at whatever size its content
	# settles to (more robust than anchor offsets computed before layout). IGNORE mouse
	# so clicks outside the panel fall through to the backdrop (which closes us).
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)

	# The floating window. A dark rounded StyleBoxFlat built in code (like
	# viewer._make_bubble_style) rather than the light parchment theme.
	_panel = PanelContainer.new()
	_panel.mouse_filter = Control.MOUSE_FILTER_STOP  # eat clicks so they don't pan
	_panel.add_theme_stylebox_override("panel", _make_panel_style())
	center.add_child(_panel)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 14)
	_panel.add_child(margin)

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
	# No focus, so LEFT / RIGHT switch views instead of being eaten by focus navigation.
	close_btn.focus_mode = Control.FOCUS_NONE
	close_btn.pressed.connect(func() -> void: close_requested.emit())
	title_row.add_child(close_btn)

	# The heat picture (campus + dwell), custom-drawn. SHRINK_CENTER keeps its exact
	# map aspect (the VBox would otherwise stretch it to the panel width). Size is set
	# from the map bounds in set_replay(). We draw via the `draw` signal so no subclass
	# is needed; IGNORE mouse so the backdrop still gets click-outside behind it.
	_canvas = Control.new()
	_canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_canvas.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	_canvas.draw.connect(_draw_canvas)
	col.add_child(_canvas)

	# Legend: the colour ramp as a bar, less-time (left) -> more-time (right).
	var legend_row := HBoxContainer.new()
	legend_row.add_theme_constant_override("separation", 8)
	col.add_child(legend_row)

	var less := Label.new()
	less.text = "Less time"
	less.add_theme_color_override("font_color", INK_DIM)
	legend_row.add_child(less)

	_legend = TextureRect.new()
	_legend.custom_minimum_size = Vector2(0, 14)
	_legend.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_legend.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_legend.stretch_mode = TextureRect.STRETCH_SCALE
	legend_row.add_child(_legend)

	var more := Label.new()
	more.text = "More time"
	more.add_theme_color_override("font_color", INK_DIM)
	legend_row.add_child(more)

	_hint = Label.new()
	_hint.text = "←  →  switch view      ·      H / Esc to close"
	_hint.add_theme_color_override("font_color", INK_DIM)
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_child(_hint)

	_update_title()


## Hand over the loaded replay (called once by viewer.gd after it loads). Builds
## the off-screen campus picture eagerly -- like minimap.configure() at _ready time --
## so its UPDATE_ONCE texture is long rendered by the time the user first opens us (a
## lazy build would show a blank campus for the first frame). _frames/_names are read
## on demand in _recompute(), so this is cheap.
func set_replay(frames: Array, names: Array, tile_px: int) -> void:
	_frames = frames
	_names = names
	_tile_px = tile_px
	_build_overview()
	if _bounds.size.x <= 0.0 or _bounds.size.y <= 0.0:
		push_error("heatmap_panel: could not size the campus overview (no map painted?)")
		return
	_canvas.custom_minimum_size = _overview_size()
	_refresh_legend()
	_update_title()


## Accumulate + show the heat for every step from 0 up to `step`, in the current view.
## Called on open and again each time the playhead advances while we're visible.
func show_up_to(step: int) -> void:
	if _frames.is_empty():
		return
	_step = clampi(step, 0, _frames.size() - 1)
	_recompute()
	_canvas.queue_redraw()


## Cycle the shown view: 0 = all agents combined, 1..N = one persona each; wraps.
func cycle_view(delta: int) -> void:
	if _names.is_empty():
		return
	var count := _names.size() + 1  # "All agents", then one view per persona
	_view_index = (_view_index + delta + count) % count
	_update_title()
	_refresh_legend()
	_recompute()
	_canvas.queue_redraw()


func _build_overview() -> void:
	# Render the campus a second time into an off-screen SubViewport (verbatim to
	# minimap._build_overview): a self-contained TileMapLayer on tiled_map.gd, framed by
	# an inner Camera2D, rendered once (the campus never changes).
	var sv := SubViewport.new()
	sv.disable_3d = true
	sv.gui_disable_input = true

	var layer := TileMapLayer.new()
	layer.set_script(load("res://scripts/tiled_map.gd"))
	layer.set("map_path", map_path)  # set() because the var is on the runtime script
	sv.add_child(layer)

	var cam := Camera2D.new()
	cam.enabled = true
	sv.add_child(cam)

	# Adding the viewport to the tree runs the layer's _ready, which paints the map
	# synchronously -- so its used cells are ready to measure immediately after.
	add_child(sv)
	_subviewport = sv

	if layer.tile_set == null:
		return  # map failed to load; set_replay() will report and bail
	var used := layer.get_used_rect()
	var ts := Vector2(layer.tile_set.tile_size)
	_bounds = Rect2(Vector2(used.position) * ts, Vector2(used.size) * ts)

	# Size the off-screen picture to the shown size times the supersample, and frame the
	# whole map into it. UPDATE_ONCE: render one frame and stop.
	var on_screen := _overview_size()
	var ss: int = maxi(supersample, 1)
	sv.size = Vector2i(int(round(on_screen.x)) * ss, int(round(on_screen.y)) * ss)
	cam.zoom = Vector2(float(sv.size.x) / _bounds.size.x, float(sv.size.y) / _bounds.size.y)
	cam.position = _bounds.get_center()
	cam.make_current()
	sv.render_target_update_mode = SubViewport.UPDATE_ONCE


func _overview_size() -> Vector2:
	# Fit the map's aspect within a fraction of the viewport (the campus is portrait, so
	# the height usually binds; also cap the width so a wide map can't overflow).
	var vp := get_viewport().get_visible_rect().size
	var aspect := _bounds.size.x / _bounds.size.y
	var h: float = min(vp.x, vp.y) * max_viewport_fraction
	var w := h * aspect
	var w_max := vp.x * max_viewport_fraction
	if w > w_max:
		w = w_max
		h = w / aspect
	return Vector2(w, h)


func _recompute() -> void:
	# Rebuild the dwell grid for the shown view, tallying every step 0.._step. Reading
	# straight from _frames (like _update_trail) keeps this correct after a seek. At most
	# ~personas x steps increments (a few thousand) -- sub-millisecond, so a full rebuild
	# on each step / view change stays simple and fast.
	_grid = {}
	_max_count = 1
	if _frames.is_empty() or _step < 0:
		return
	if _view_index == 0:
		for name in _names:
			_tally(name)
	else:
		_tally(_names[_view_index - 1])


func _tally(name: String) -> void:
	for k in range(0, _step + 1):
		var f: Variant = _frames[k].get(name)
		if typeof(f) != TYPE_DICTIONARY:
			continue
		var key := Vector2i(int(f["x"]), int(f["y"]))
		var c: int = int(_grid.get(key, 0)) + 1
		_grid[key] = c
		if c > _max_count:
			_max_count = c


func _draw_canvas() -> void:
	# The `draw` signal fires during _canvas's draw pass, so draw commands issued on it
	# here paint onto the canvas. We read _canvas.size (the laid-out size) so the campus
	# texture and the heat rects share one transform and stay aligned.
	if _subviewport == null or _bounds.size.x <= 0.0:
		return
	var sz := _canvas.size
	if sz.x <= 0.0 or sz.y <= 0.0:
		return

	# 1. The campus underneath, then a dim so faint heat still reads over it.
	_canvas.draw_texture_rect(_subviewport.get_texture(), Rect2(Vector2.ZERO, sz), false)
	_canvas.draw_rect(Rect2(Vector2.ZERO, sz), MAP_DIM)

	# 2. The heat: one rect per visited tile, coloured by (log-compressed) dwell so the
	# very peaky counts -- agents idle at a building for many steps -- don't wash out the
	# thin paths between them.
	var s := sz.x / _bounds.size.x
	var cell := Vector2(_tile_px, _tile_px) * s
	var denom := log(1.0 + float(_max_count))
	var tint := Color.WHITE
	if _view_index > 0:
		tint = TINTS[(_view_index - 1) % TINTS.size()]
	for key in _grid:
		var count: int = _grid[key]
		var t: float = (log(1.0 + float(count)) / denom) if denom > 0.0 else 0.0
		var col: Color
		if _view_index == 0:
			col = _gradient.sample(t)
		else:
			col = Color(tint.r, tint.g, tint.b, lerpf(AGENT_ALPHA_LOW, AGENT_ALPHA_HIGH, t))
		var pos := (Vector2(key) * float(_tile_px) - _bounds.position) * s
		_canvas.draw_rect(Rect2(pos, cell), col)

	# 3. A frame around the picture.
	_canvas.draw_rect(Rect2(Vector2.ZERO, sz), Color(1.0, 0.97, 0.86, 0.5), false, 2.0)


func _build_gradient() -> void:
	# Warm single-hue "ember" ramp: monotonic dark->bright with rising alpha, so low
	# dwell recedes into the (dark, cool) night campus and peak dwell reads hot + opaque.
	# A rainbow/jet ramp would fight the green lawns; one warm hue keeps it legible.
	_gradient = Gradient.new()
	_gradient.offsets = PackedFloat32Array([0.0, 0.25, 0.5, 0.75, 1.0])
	_gradient.colors = PackedColorArray([
		Color(0.45, 0.22, 0.05, 0.20),
		Color(0.72, 0.35, 0.08, 0.45),
		Color(0.90, 0.52, 0.12, 0.68),
		Color(0.98, 0.70, 0.25, 0.85),
		Color(1.00, 0.90, 0.55, 0.95),
	])


func _refresh_legend() -> void:
	if _legend == null:
		return
	var g: Gradient
	if _view_index == 0:
		g = _gradient
	else:
		# The current persona's tint, fading faint -> solid to match the per-agent heat.
		var tint: Color = TINTS[(_view_index - 1) % TINTS.size()]
		g = Gradient.new()
		g.offsets = PackedFloat32Array([0.0, 1.0])
		g.colors = PackedColorArray([
			Color(tint.r, tint.g, tint.b, AGENT_ALPHA_LOW),
			Color(tint.r, tint.g, tint.b, AGENT_ALPHA_HIGH),
		])
	var tex := GradientTexture2D.new()
	tex.gradient = g
	tex.width = 128
	tex.height = 1
	_legend.texture = tex


func _update_title() -> void:
	if _title == null:
		return
	if _view_index == 0 or _names.is_empty():
		_title.text = "Movement Heatmap — All agents"
	else:
		_title.text = "Movement Heatmap — %s" % _names[_view_index - 1]


func _on_backdrop_input(event: InputEvent) -> void:
	# A click on the dimmed area outside the panel closes the pop-up.
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
