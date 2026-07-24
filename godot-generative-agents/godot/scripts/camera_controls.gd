extends Camera2D
## Pan + zoom for the campus view, layered on top of the scene's default framing.
##
## The scene file sets this camera's starting `position` and `zoom` to contain-fit
## the whole block — that's the default view. This script records that starting
## view as "home" in _ready(), so the default is whatever the scene chose and is
## never changed; everything below just lets you explore away from it and snap
## back:
##
##   Zoom : mouse wheel, trackpad pinch, or the +/- keys  (zooms toward the cursor)
##          — zooming OUT stops at the default view, so the whole block is the
##          most you can ever see; you only zoom IN from there.
##   Pan  : drag with the left or middle mouse button, a two-finger trackpad
##          swipe, or the arrow keys / WASD. The view is always kept INSIDE the
##          map, so you can never scroll past an edge — there's never grey at the
##          top or bottom. When an axis already fits the screen (e.g. at the
##          default view) it's centre-locked, so the map can't drift off.
##   Reset: press R (or Home) to glide back to the default view
##
## Attach it to any Camera2D — it reads its own default and the sibling
## TileMapLayer's size, so every scene keeps its own framing and bounds.

# Each wheel notch / key press multiplies the zoom by this (1.1 = 10% per step).
@export var zoom_step: float = 1.1
# How far you may zoom IN. `zoom` is magnification: bigger = closer in. Zooming
# OUT is floored at the scene's default view (the contain-fit framing captured as
# _home_zoom in _ready), so the whole block is the furthest out you can go.
@export var max_zoom: float = 4.0
# Keyboard pan speed, in screen-pixels per second (kept constant at any zoom).
@export var key_pan_speed: float = 1200.0
# Trackpad two-finger-swipe pan sensitivity.
@export var gesture_pan_speed: float = 12.0
# Seconds for the "reset to default view" glide.
@export var reset_time: float = 0.25
# Magnification used while tracking an agent (see follow). Stays within
# _home_zoom..max_zoom so the usual zoom rules still hold.
@export var follow_zoom: float = 1.6
# Easing rate for the minimap click-to-recentre glide (see move_to). Higher is
# snappier — the camera closes most of the remaining gap each frame.
@export var pan_glide_speed: float = 12.0

# Emitted when agent-follow is cleared (by stop_following, a manual pan, or Reset),
# so a UI panel can drop its "tracking" highlight.
signal follow_stopped

# A press that moves less than this many screen-pixels before release is treated as
# a click, not a drag — so we never pan (or drop an agent-follow) for it. This is
# what lets "click an agent to track them" survive the tiny cursor jitter of a real
# click: without it, any motion while the button is down cancels the follow the
# click just started, and you'd zoom in on the agent but not actually follow.
const DRAG_THRESHOLD_PX := 6.0

# The scene's starting view, captured in _ready() — what Reset returns to.
var _home_position: Vector2
var _home_zoom: Vector2
# A left/middle button is held, so a drag MIGHT start — but it's still just a click
# until the cursor moves past DRAG_THRESHOLD_PX (see _unhandled_input).
var _press_armed := false
var _press_pos := Vector2.ZERO
# True once an armed press has moved far enough to count as a drag-pan in progress.
var _dragging := false
# True while the Reset glide is running (we leave the tween alone, no clamping).
var _resetting := false
# The agent node the camera is centring on each frame, or null when free.
var _follow_target: Node2D = null
# A world point the camera is gliding toward after a minimap click/drag (see
# move_to); _pan_active is false when no such glide is in progress.
var _pan_target := Vector2.ZERO
var _pan_active := false
# The map's world bounds, computed once on first use (see _map_bounds).
var _bounds := Rect2()
var _have_bounds := false
# Screen-pixels down the LEFT edge hidden behind the on-screen sidebar
# (agent_panel.gd, in the UI CanvasLayer). The clamp frames the map into the
# UNCOVERED part of the window so the bar never permanently hides campus you
# can't pan to. 0 = no sidebar. Set by viewer.gd via set_left_inset().
var _left_inset := 0.0
# When false, the arrow/WASD keyboard pan is ignored (mouse drag/zoom still work). The
# heatmap pop-up sets this while open so LEFT/RIGHT switch its view instead of panning.
var keyboard_enabled := true


func _ready() -> void:
	# Whatever framing the scene set is the default; remember it for Reset.
	_home_position = global_position
	_home_zoom = zoom


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_zoom_at_mouse(zoom_step)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_zoom_at_mouse(1.0 / zoom_step)

	# Hold the left or middle mouse button to drag the map around. A press only ARMS a
	# drag; it doesn't pan (or take control back from an agent-follow) until the cursor
	# moves past DRAG_THRESHOLD_PX. That tolerance is what keeps a click — e.g. clicking
	# an agent to track them — from being read as a tiny pan that cancels the follow.
	if event is InputEventMouseButton and (
			event.button_index == MOUSE_BUTTON_LEFT
			or event.button_index == MOUSE_BUTTON_MIDDLE):
		_press_armed = event.pressed
		_press_pos = event.position
		_dragging = false
	elif event is InputEventMouseMotion and _press_armed:
		# Ignore the jitter of a click; only once we've moved past the threshold does
		# this become a real pan. Move the world with the cursor: shift the camera
		# opposite the drag, converting screen pixels to world units through the current
		# zoom. Panning by hand takes control back from any agent-follow (the sidebar
		# clears via the follow_stopped signal).
		if _dragging or event.position.distance_to(_press_pos) >= DRAG_THRESHOLD_PX:
			_dragging = true
			stop_following()
			_pan_active = false  # a hand-drag cancels any minimap glide
			global_position -= event.relative / zoom
			_clamp_position()

	# Trackpad gestures (macOS): pinch to zoom, two-finger swipe to pan.
	elif event is InputEventMagnifyGesture:
		_zoom_at_mouse(event.factor)
	elif event is InputEventPanGesture:
		stop_following()  # a two-finger swipe is a manual pan
		_pan_active = false
		global_position += event.delta * gesture_pan_speed / zoom
		_clamp_position()

	# Keyboard: +/- zoom (about the centre), R / Home reset.
	elif event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_EQUAL, KEY_PLUS, KEY_KP_ADD:
				_zoom_keep_centre(zoom_step)
			KEY_MINUS, KEY_KP_SUBTRACT:
				_zoom_keep_centre(1.0 / zoom_step)
			KEY_R, KEY_HOME:
				_reset_view()


func _process(delta: float) -> void:
	if _resetting:
		return
	# Arrow keys / WASD pan, at a constant on-screen speed (divide by zoom so a
	# key-press moves the same number of screen pixels however far you're zoomed).
	var dir := Vector2.ZERO
	if keyboard_enabled:
		if Input.is_key_pressed(KEY_LEFT) or Input.is_key_pressed(KEY_A):
			dir.x -= 1.0
		if Input.is_key_pressed(KEY_RIGHT) or Input.is_key_pressed(KEY_D):
			dir.x += 1.0
		if Input.is_key_pressed(KEY_UP) or Input.is_key_pressed(KEY_W):
			dir.y -= 1.0
		if Input.is_key_pressed(KEY_DOWN) or Input.is_key_pressed(KEY_S):
			dir.y += 1.0
	if dir != Vector2.ZERO:
		stop_following()  # arrow / WASD pan takes manual control back
		_pan_active = false  # ...and cancels any minimap glide
		global_position += dir.normalized() * key_pan_speed * delta / zoom.x
		_clamp_position()
		return

	# A minimap click/drag asked us to glide to a world point: ease toward it each
	# frame, clamped to the map. One easing rule serves both gestures — a single click
	# animates over a few frames, and a drag (which keeps moving the target) is chased
	# smoothly. Stop once we've essentially arrived, or settled against a clamped edge.
	if _pan_active:
		var before := global_position
		global_position = global_position.lerp(_pan_target, 1.0 - exp(-pan_glide_speed * delta))
		_clamp_position()
		if global_position.distance_to(before) < 0.25:
			_pan_active = false
		return

	# Otherwise, if we're tracking an agent, glue the view to it each frame.
	if _follow_target != null and is_instance_valid(_follow_target):
		global_position = _follow_target.global_position
		_clamp_position()


func follow(target: Node2D) -> void:
	# Start centring the view on `target` every frame and glide the zoom in to the
	# tracking level. Position is handled in _process (so it keeps up as the agent
	# walks); only the zoom needs a tween here.
	_follow_target = target
	_resetting = false  # cancel any in-flight Reset glide so following can take over
	var tw := create_tween()
	tw.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	tw.tween_property(self, "zoom", Vector2(follow_zoom, follow_zoom), reset_time)


func stop_following() -> void:
	# Release the camera; leave it wherever it is (Reset / R returns to the default).
	if _follow_target == null:
		return
	_follow_target = null
	follow_stopped.emit()


func move_to(world_pos: Vector2) -> void:
	# Glide the view to centre on a world point — the minimap's click-to-recentre.
	# Takes manual control back from any agent-follow and cancels a Reset glide;
	# _process eases us there (and keeps easing as the point moves during a drag).
	stop_following()
	_resetting = false
	_pan_target = world_pos
	_pan_active = true


func reset_view() -> void:
	# Public entry point for a UI button: glide back to the scene's default framing
	# (same as pressing R / Home). Releases any agent-follow on the way.
	_reset_view()


func set_left_inset(px: float) -> void:
	# Tell the camera how many screen-pixels the sidebar covers down the left edge.
	# Re-frame immediately so the change (or the initial seed) takes effect at once.
	_left_inset = maxf(px, 0.0)
	_clamp_position()


func zoom_in() -> void:
	_zoom_keep_centre(zoom_step)


func zoom_out() -> void:
	_zoom_keep_centre(1.0 / zoom_step)


func _zoom_at_mouse(factor: float) -> void:
	# Zoom while keeping the world point under the cursor pinned in place.
	var world_before := get_global_mouse_position()
	var new_zoom := _clamp_zoom(zoom * factor)
	if new_zoom == zoom:
		return
	var ratio := zoom.x / new_zoom.x
	zoom = new_zoom
	global_position = world_before - (world_before - global_position) * ratio
	_clamp_position()


func _zoom_keep_centre(factor: float) -> void:
	# Zoom about the screen centre (the camera position doesn't move).
	zoom = _clamp_zoom(zoom * factor)
	_clamp_position()


func _clamp_zoom(z: Vector2) -> Vector2:
	# Floor at the default view (_home_zoom) so you can't zoom out past the whole
	# block; ceiling at max_zoom for the closest zoom-in.
	return z.clamp(_home_zoom, Vector2(max_zoom, max_zoom))


func _clamp_position() -> void:
	# Keep the visible rectangle inside the map so no edge shows grey, working one
	# axis at a time. `lo`/`hi` are the closest the camera centre may sit to each
	# map edge while the view stays inside.
	var b := _map_bounds()
	var half := get_viewport().get_visible_rect().size * 0.5 / zoom
	var home := _home_target()
	# The sidebar hides _left_inset screen-pixels down the left, so the map only has
	# to fill the window to its right; this is that strip's width in world units.
	var inset_world := _left_inset / zoom.x
	var p := global_position
	for axis in 2:
		var lo := b.position[axis] + half[axis]
		var hi := b.end[axis] - half[axis]
		if axis == 0:
			# Let the camera travel further left by the sidebar width, so the map's
			# left edge can slide out from under the bar (its grey is hidden anyway).
			# Only the X low bound moves; every other edge stays flush with the map.
			lo -= inset_world
		if lo > hi:
			# The map is smaller than the (uncovered) view on this axis — e.g. the
			# default view, where the whole block already fits. Lock to the home
			# frame so it can't drift and uncover grey.
			p[axis] = home[axis]
		else:
			# Keep the view inside the map, but never refuse the home frame, so a
			# scene whose default deliberately shows a margin still opens on its
			# intended frame (we only stop it from revealing *more* than that).
			p[axis] = clampf(p[axis], minf(lo, home[axis]), maxf(hi, home[axis]))
	global_position = p


func _home_target() -> Vector2:
	# The scene's default frame, shifted right by half the sidebar (in world units at
	# the home zoom) so the bar sits over the grey margin and covers no campus. With
	# no sidebar (_left_inset 0) this is just the scene's home position.
	return Vector2(_home_position.x - _left_inset * 0.5 / _home_zoom.x, _home_position.y)


func _map_bounds() -> Rect2:
	# The map's footprint in world coordinates, found once from the sibling
	# TileMapLayer (used tiles x tile size, through its transform — which carries
	# any layer scale). Falls back to the contain-fit home view if none is found.
	if _have_bounds:
		return _bounds
	var layer := _find_tilemap()
	if layer != null and layer.tile_set != null:
		var used := layer.get_used_rect()
		var ts := Vector2(layer.tile_set.tile_size)
		var xf := layer.global_transform
		var p0: Vector2 = xf * (Vector2(used.position) * ts)
		var p1: Vector2 = xf * (Vector2(used.end) * ts)
		_bounds = Rect2(p0, p1 - p0).abs()
	else:
		var vp := get_viewport().get_visible_rect().size / _home_zoom
		_bounds = Rect2(_home_position - vp * 0.5, vp)
	_have_bounds = true
	return _bounds


func _find_tilemap() -> TileMapLayer:
	var parent := get_parent()
	if parent != null:
		for child in parent.get_children():
			if child is TileMapLayer:
				return child
	return null


func _reset_view() -> void:
	stop_following()  # Reset means "back to the default view", not "keep tracking"
	_pan_active = false  # ...and drops any in-flight minimap glide
	_resetting = true
	var tw := create_tween().set_parallel(true)
	tw.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	tw.tween_property(self, "global_position", _home_target(), reset_time)
	tw.tween_property(self, "zoom", _home_zoom, reset_time)
	tw.finished.connect(func() -> void: _resetting = false)
