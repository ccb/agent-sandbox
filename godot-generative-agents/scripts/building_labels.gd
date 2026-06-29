extends Node2D
## Floating building name-plates over the campus: shown when you're zoomed all the
## way out (so you can read the campus at a glance) and faded out as you zoom in
## (once buildings are big enough to recognise on their own, and the agent
## name-plates are what you want to read).
##
## The names + centres come from maps/building_labels.json, precomputed by
## sim/generate_building_labels.py from the sim's sector matrix. Each entry is a
## tile (x, y) in the very grid the agents walk, so we drop a centred Label over
## each building with the same tile->world transform penn_replay.gd uses for
## sprites. The labels live in world space (children of this node), so the camera
## pans and zooms them with the map; _process only dials their opacity by zoom.

@export_file("*.json") var labels_path: String = "res://maps/building_labels.json"
## Name-plates are fully opaque at/below `fade_start_zoom` (the whole-campus view)
## and fully gone at/above `fade_end_zoom`, cross-fading between. `Camera2D.zoom`
## is magnification: the home view is ~0.242 and you can zoom in to 4.0, so these
## defaults keep the names on screen only in the most zoomed-out band.
@export var fade_start_zoom: float = 0.28
@export var fade_end_zoom: float = 0.5
@export var font_size: int = 56
@export var outline_size: int = 14
@export var label_color: Color = Color(1.0, 0.97, 0.86)  # warm off-white
## Width the name wraps within (world px); also how far left of centre the plate
## starts, so the text box stays centred over the building.
@export var label_width: float = 360.0

# The sibling camera whose zoom drives the fade, found in _ready.
var _camera: Camera2D = null
var _labels: Array[Label] = []
# Last opacity pushed to the labels (-1 = none yet) so we only touch them on change.
var _last_alpha := -1.0


func _ready() -> void:
	_camera = _find_camera()
	_build_labels()


func _find_camera() -> Camera2D:
	# The camera is a sibling under the scene root (same place penn_replay.gd adds
	# the agent sprites), so scan our parent's children for it.
	var parent := get_parent()
	if parent != null:
		for child in parent.get_children():
			if child is Camera2D:
				return child
	return null


func _build_labels() -> void:
	var f := FileAccess.open(labels_path, FileAccess.READ)
	if f == null:
		push_error("building_labels: cannot open %s" % labels_path)
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	if typeof(data) != TYPE_DICTIONARY:
		push_error("building_labels: %s is not valid JSON" % labels_path)
		return
	var tile_px := float(data.get("tile_px", 16))
	for b in data.get("buildings", []):
		_add_label(String(b["name"]), float(b["x"]), float(b["y"]), tile_px)


func _add_label(name: String, tile_x: float, tile_y: float, tile_px: float) -> void:
	var label := Label.new()
	label.text = name
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", label_color)
	label.add_theme_color_override("font_outline_color", Color.BLACK)
	label.add_theme_constant_override("outline_size", outline_size)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.custom_minimum_size = Vector2(label_width, 0)
	# Tile centre in world px (matches penn_replay.gd's _tile_to_world), then shift
	# the text box so it's centred over that point instead of starting there.
	var world := Vector2((tile_x + 0.5) * tile_px, (tile_y + 0.5) * tile_px)
	label.position = world - Vector2(label_width * 0.5, float(font_size) * 0.5)
	add_child(label)
	_labels.append(label)


func _process(_delta: float) -> void:
	if _camera == null or _labels.is_empty():
		return
	# Linear cross-fade across the zoom band; clamp so we're solid when zoomed out
	# and fully transparent once zoomed past fade_end_zoom.
	var z := _camera.zoom.x
	var span: float = maxf(fade_end_zoom - fade_start_zoom, 0.0001)
	var alpha := clampf((fade_end_zoom - z) / span, 0.0, 1.0)
	if is_equal_approx(alpha, _last_alpha):
		return
	_last_alpha = alpha
	# Hide outright at zero so fully-zoomed-in frames skip drawing the labels.
	visible = alpha > 0.0
	for label in _labels:
		label.modulate.a = alpha
