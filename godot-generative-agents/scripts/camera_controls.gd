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

# Emitted when agent-follow is cleared (by stop_following, a manual pan, or Reset),
# so a UI panel can drop its "tracking" highlight.
signal follow_stopped

# The scene's starting view, captured in _ready() — what Reset returns to.
var _home_position: Vector2
var _home_zoom: Vector2
# True while a mouse-button drag-pan is in progress.
var _dragging := false
# True while the Reset glide is running (we leave the tween alone, no clamping).
var _resetting := false
# The agent node the camera is centring on each frame, or null when free.
var _follow_target: Node2D = null
# The map's world bounds, computed once on first use (see _map_bounds).
var _bounds := Rect2()
var _have_bounds := false


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

	# Hold the left or middle mouse button to drag the map around.
	if event is InputEventMouseButton and (
			event.button_index == MOUSE_BUTTON_LEFT
			or event.button_index == MOUSE_BUTTON_MIDDLE):
		_dragging = event.pressed
	elif event is InputEventMouseMotion and _dragging:
		# Move the world with the cursor: shift the camera opposite the drag,
		# converting screen pixels to world units through the current zoom. Moving the
		# camera by hand takes control back from any agent-follow (the sidebar clears
		# via the follow_stopped signal).
		stop_following()
		global_position -= event.relative / zoom
		_clamp_position()

	# Trackpad gestures (macOS): pinch to zoom, two-finger swipe to pan.
	elif event is InputEventMagnifyGesture:
		_zoom_at_mouse(event.factor)
	elif event is InputEventPanGesture:
		stop_following()  # a two-finger swipe is a manual pan
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
		global_position += dir.normalized() * key_pan_speed * delta / zoom.x
		_clamp_position()
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
	var lo := b.position + half
	var hi := b.end - half
	var p := global_position
	for axis in 2:
		if lo[axis] > hi[axis]:
			# The map is smaller than the view on this axis — e.g. the default
			# view, where the whole block already fits the height. Lock to the
			# home position so it can't drift and uncover grey.
			p[axis] = _home_position[axis]
		else:
			# Keep the view inside the map, but never refuse the home position, so
			# a scene whose default deliberately shows a margin still opens on its
			# intended frame (we only stop it from revealing *more* than that).
			var a_lo: float = minf(lo[axis], _home_position[axis])
			var a_hi: float = maxf(hi[axis], _home_position[axis])
			p[axis] = clampf(p[axis], a_lo, a_hi)
	global_position = p


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
	_resetting = true
	var tw := create_tween().set_parallel(true)
	tw.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	tw.tween_property(self, "global_position", _home_position, reset_time)
	tw.tween_property(self, "zoom", _home_zoom, reset_time)
	tw.finished.connect(func() -> void: _resetting = false)
