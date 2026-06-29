extends Control
## A bottom-right minimap: a super-zoomed-out overview of the campus with one
## coloured dot per agent and a box showing the slice of campus currently on screen.
##
## The overview is the REAL map, not a sketch: we render the same .tmj campus a
## second time into an off-screen SubViewport (reusing tiled_map.gd) and draw that
## little picture in the corner. On top of it, _draw() paints the live camera frame
## box and the agent dots every frame, and clicking (or dragging) on the minimap
## glides the main view to that spot.
##
## This panel is pure UI, like agent_panel.gd: it knows nothing about the agents or
## the camera until penn_replay.gd hands them over. The viewer calls configure() once
## with the camera, add_agent() per persona after the replay loads, and wires our
## recenter_requested signal to the camera so a click moves the main view.

## The campus map to draw — the same .tmj the main scene renders. tiled_map.gd reads
## this and paints it for us in the off-screen viewport.
@export_file("*.tmj") var map_path: String = "res://maps/upenn_core_urban.tmj"
## The minimap is sized to the map's shape so dots aren't stretched: it's at most
## this tall and this wide (the smaller limit wins), keeping aspect.
@export var max_height: float = 260.0
@export var max_width: float = 300.0
## Gap (screen px) between the minimap and the bottom-right screen corner.
@export var margin: float = 16.0
## Render the overview this many times larger than it's shown, then shrink it down,
## so the heavily-minified campus reads as a smooth picture instead of sparse noise.
@export var supersample: int = 3
## Radius (screen px) of each agent's dot.
@export var dot_radius: float = 4.0
## Outline around the minimap and around the live camera-frame box.
@export var border_color: Color = Color(1.0, 0.97, 0.86, 0.9)  # warm off-white
@export var frustum_color: Color = Color(1.0, 1.0, 1.0, 0.95)

## Emitted on a click or drag inside the minimap, with the world point under the
## cursor; penn_replay.gd routes this to the camera's move_to() to glide the view.
signal recenter_requested(world_pos: Vector2)

# Set once configure() has built the overview and learned the map's world bounds;
# until then _draw()/_gui_input() are no-ops (the node has no size or picture yet).
var _configured := false
# The main camera, whose position + zoom we read each frame to draw the frame box.
var _camera: Camera2D = null
# The map's footprint in world pixels (origin + size), the single source of truth for
# the world<->minimap transform AND the frame box (so the box lines up with how the
# camera clamps to the same bounds).
var _bounds := Rect2()
# The off-screen viewport holding the second copy of the campus; its texture is the
# overview picture we draw in the corner.
var _subviewport: SubViewport = null
# One {node, tint} per agent; the dots track each node's live position.
var _agents: Array = []


func configure(camera: Camera2D) -> void:
	# Hand the minimap the main camera and build its overview. Called once from
	# penn_replay.gd._ready(), after the scene (this node included) is in the tree.
	_camera = camera
	_build_overview()
	if _bounds.size.x <= 0.0 or _bounds.size.y <= 0.0:
		push_error("minimap: could not size the overview (no map painted?)")
		return
	_layout()
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR  # smooth the shrunk-down picture
	_configured = true
	queue_redraw()


func add_agent(name: String, node: Node2D, tint: Color) -> void:
	# Register an agent to draw as a dot. We hold the node (not a copy of its
	# position) so the dot tracks it as the viewer walks it each frame.
	_agents.append({"name": name, "node": node, "tint": tint})


func _build_overview() -> void:
	# Render the campus a second time into an off-screen SubViewport so we have a tiny
	# picture of the whole map to show. The inner TileMapLayer runs tiled_map.gd (same
	# as the main Map) and is fully self-contained, so it paints independently here.
	var sv := SubViewport.new()
	sv.disable_3d = true
	sv.gui_disable_input = true

	var layer := TileMapLayer.new()
	layer.set_script(load("res://scripts/tiled_map.gd"))
	layer.set("map_path", map_path)  # set() because the var is on the runtime script
	sv.add_child(layer)

	# A camera inside the viewport framing the whole map (set below, once we know the
	# map's bounds from the painted layer).
	var cam := Camera2D.new()
	cam.enabled = true
	sv.add_child(cam)

	# Adding the viewport to the tree runs the layer's _ready, which paints the map
	# synchronously — so its used cells are ready to measure immediately after.
	add_child(sv)
	_subviewport = sv

	if layer.tile_set == null:
		return  # map failed to load; configure() will report and bail
	var used := layer.get_used_rect()
	var ts := Vector2(layer.tile_set.tile_size)
	_bounds = Rect2(Vector2(used.position) * ts, Vector2(used.size) * ts)

	# Size the off-screen picture to the on-screen minimap times the supersample, and
	# frame the whole map into it (zoom = pixels-across / world-across, centred on the
	# map). UPDATE_ONCE: the campus never changes, so render a single frame and stop.
	var on_screen := _overview_size()
	var ss: int = maxi(supersample, 1)
	sv.size = Vector2i(int(round(on_screen.x)) * ss, int(round(on_screen.y)) * ss)
	cam.zoom = Vector2(float(sv.size.x) / _bounds.size.x, float(sv.size.y) / _bounds.size.y)
	cam.position = _bounds.get_center()
	cam.make_current()
	sv.render_target_update_mode = SubViewport.UPDATE_ONCE


func _overview_size() -> Vector2:
	# The on-screen minimap size, fit to the map's aspect within max_width/max_height.
	var aspect := _bounds.size.x / _bounds.size.y
	var h := max_height
	var w := h * aspect
	if w > max_width:
		w = max_width
		h = w / aspect
	return Vector2(w, h)


func _layout() -> void:
	# Pin a fixed-size box to the bottom-right corner; anchors at (1,1) mean the
	# offsets are measured from that corner, so it tracks any window resize for free.
	var s := _overview_size()
	anchor_left = 1.0
	anchor_top = 1.0
	anchor_right = 1.0
	anchor_bottom = 1.0
	offset_left = -(s.x + margin)
	offset_top = -(s.y + margin)
	offset_right = -margin
	offset_bottom = -margin


func _process(_delta: float) -> void:
	# Agents and the camera move every frame, so redraw the dots + frame box.
	if _configured:
		queue_redraw()


func _draw() -> void:
	if not _configured:
		return
	# World px -> minimap px. We sized the box to the map's aspect, so one scale fits
	# both axes; the overview picture fills the box, so the same scale places dots and
	# the frame box correctly on top of it.
	var s := size.x / _bounds.size.x

	# 1. The campus overview underneath everything.
	if _subviewport != null:
		draw_texture_rect(_subviewport.get_texture(), Rect2(Vector2.ZERO, size), false)

	# 2. The live camera frame: the world rectangle the main view shows, clipped to the
	# map (when zoomed all the way out the view is wider than the campus, so this fills
	# the minimap). Lets you see at a glance which slice of campus is on screen.
	if _camera != null:
		var vp := get_viewport().get_visible_rect().size
		var half := vp * 0.5 / _camera.zoom
		var view := Rect2(_camera.global_position - half, vp / _camera.zoom).intersection(_bounds)
		if view.size.x > 0.0 and view.size.y > 0.0:
			var box := Rect2((view.position - _bounds.position) * s, view.size * s)
			draw_rect(box, frustum_color, false, 2.0)

	# 3. One dot per agent, with a dark backing so light dots stay visible on the map.
	for a in _agents:
		var node: Node2D = a["node"]
		if not is_instance_valid(node):
			continue
		var p := (node.global_position - _bounds.position) * s
		draw_circle(p, dot_radius + 1.5, Color(0.0, 0.0, 0.0, 0.55))
		draw_circle(p, dot_radius, a["tint"])

	# 4. A frame around the whole minimap.
	draw_rect(Rect2(Vector2.ZERO, size), border_color, false, 2.0)


func _gui_input(event: InputEvent) -> void:
	# Click (or drag with the button held) to glide the main view to that spot. Because
	# this is a Control with the default MOUSE_FILTER_STOP, the event is consumed here
	# and never reaches camera_controls.gd's drag-pan, so the minimap and the map don't
	# fight over the same click.
	if not _configured:
		return
	var act := false
	var local := Vector2.ZERO
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		local = event.position
		act = true
	elif event is InputEventMouseMotion and (event.button_mask & MOUSE_BUTTON_MASK_LEFT) != 0:
		local = event.position
		act = true
	if act:
		var s := size.x / _bounds.size.x
		recenter_requested.emit(_bounds.position + local / s)
		accept_event()
