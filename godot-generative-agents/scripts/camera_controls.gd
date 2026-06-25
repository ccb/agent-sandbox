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
##   Pan  : drag with the left or middle mouse button, a two-finger trackpad
##          swipe, or the arrow keys / WASD
##   Reset: press R (or Home) to glide back to the default view
##
## Attach it to any Camera2D — it adapts to that camera's own default, so every
## scene keeps its own framing.

# Each wheel notch / key press multiplies the zoom by this (1.1 = 10% per step).
@export var zoom_step: float = 1.1
# How far you may zoom. `zoom` is magnification: bigger = closer in. The scene
# defaults (~0.18–0.25) frame the whole block, so allow a little further out and
# a lot further in.
@export var min_zoom: float = 0.08
@export var max_zoom: float = 4.0
# Keyboard pan speed, in screen-pixels per second (kept constant at any zoom).
@export var key_pan_speed: float = 1200.0
# Trackpad two-finger-swipe pan sensitivity.
@export var gesture_pan_speed: float = 12.0
# Seconds for the "reset to default view" glide.
@export var reset_time: float = 0.25

# The scene's starting view, captured in _ready() — what Reset returns to.
var _home_position: Vector2
var _home_zoom: Vector2
# True while a mouse-button drag-pan is in progress.
var _dragging := false


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
		# converting screen pixels to world units through the current zoom.
		global_position -= event.relative / zoom

	# Trackpad gestures (macOS): pinch to zoom, two-finger swipe to pan.
	elif event is InputEventMagnifyGesture:
		_zoom_at_mouse(event.factor)
	elif event is InputEventPanGesture:
		global_position += event.delta * gesture_pan_speed / zoom

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
		global_position += dir.normalized() * key_pan_speed * delta / zoom.x


func _zoom_at_mouse(factor: float) -> void:
	# Zoom while keeping the world point under the cursor pinned in place.
	var world_before := get_global_mouse_position()
	var new_zoom := (zoom * factor).clamp(
			Vector2(min_zoom, min_zoom), Vector2(max_zoom, max_zoom))
	if new_zoom == zoom:
		return
	var ratio := zoom.x / new_zoom.x
	zoom = new_zoom
	global_position = world_before - (world_before - global_position) * ratio


func _zoom_keep_centre(factor: float) -> void:
	# Zoom about the screen centre (the camera position doesn't move).
	zoom = (zoom * factor).clamp(
			Vector2(min_zoom, min_zoom), Vector2(max_zoom, max_zoom))


func _reset_view() -> void:
	var tw := create_tween().set_parallel(true)
	tw.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	tw.tween_property(self, "global_position", _home_position, reset_time)
	tw.tween_property(self, "zoom", _home_zoom, reset_time)
