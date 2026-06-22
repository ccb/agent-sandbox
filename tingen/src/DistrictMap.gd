extends Control
## Modal city map (toggle: M). Renders the real tingen_map.png city map, overlaid with live
## risk-tinted district regions, point markers for the key sites, and a live player-position
## tracker — all on a map-image-anchored coordinate layer (see MapProjection). The old abstract
## `polygon` field still drives the streetscape elsewhere; here we read each district's
## `map_polygon` (map-image space) so every overlay lines up with the printed map art.

const DISTRICTS_PATH: String = "res://data/districts.json"
const MAP_TEXTURE_PATH: String = "res://assets/maps/map_v3.png"
const LOW_RISK := Color(0.25, 0.55, 0.35)
const HIGH_RISK := Color(0.85, 0.25, 0.25)

var districts: Array = []
var _hover_index: int = -1
var _map_tex: Texture2D = null
var _pulse: float = 0.0

@onready var _canvas: Control = $Center/Frame/VBox/Map
@onready var _readout: Label = $Center/Frame/VBox/Readout

func _ready() -> void:
	_load()
	_map_tex = load(MAP_TEXTURE_PATH) as Texture2D
	visible = false
	_canvas.draw.connect(_draw_map)
	_canvas.gui_input.connect(_on_map_input)
	_canvas.mouse_exited.connect(func():
		_hover_index = -1
		_canvas.queue_redraw())
	WorldState.state_changed.connect(_canvas.queue_redraw)

## While the map is open, redraw every frame so the player tracker follows the live position.
## Trivial cost, and only while the modal is visible.
func _process(delta: float) -> void:
	if visible:
		# Wrap at TAU (an exact multiple of the sin(_pulse*4) period) so the tracker pulse
		# is unchanged visually but _pulse never grows unbounded over a long session.
		_pulse = fmod(_pulse + delta, TAU)
		_canvas.queue_redraw()

func _load() -> void:
	if not FileAccess.file_exists(DISTRICTS_PATH):
		push_error("DistrictMap: missing %s" % DISTRICTS_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(DISTRICTS_PATH))
	if typeof(parsed) == TYPE_ARRAY:
		districts = parsed

func toggle() -> void:
	visible = not visible
	if visible:
		_canvas.queue_redraw()

func _risk_for(d: Dictionary) -> float:
	var base: float = float(d.get("base_risk", 0.0))
	var pname := String(d.get("risk_pressure", ""))
	var pressure: float = WorldState.get_pressure(StringName(pname)) / 100.0 if pname != "" else 0.0
	return clampf(base + pressure * (1.0 - base), 0.0, 1.0)

## Map-image-space polygon (the printed-map coords) for a district's `map_polygon`.
func _map_poly_of(d: Dictionary) -> PackedVector2Array:
	var pts := PackedVector2Array()
	var raw: Array = d.get("map_polygon", [])
	for i in range(0, raw.size() - 1, 2):
		pts.append(Vector2(float(raw[i]), float(raw[i + 1])))
	return pts

## Project a map-image-space polygon into canvas space via the shared aspect-fit transform.
func _to_canvas_poly(image_poly: PackedVector2Array) -> PackedVector2Array:
	var out := PackedVector2Array()
	for p in image_poly:
		out.append(MapProjection.image_to_canvas(_canvas.size, p))
	return out

func _draw_map() -> void:
	var size: Vector2 = _canvas.size
	# 1) Letterboxed backdrop + the map art, aspect-fit (never distorted).
	_canvas.draw_rect(Rect2(Vector2.ZERO, size), Color(0.05, 0.06, 0.09))
	var fit_tl: Vector2 = MapProjection.image_to_canvas(size, Vector2.ZERO)
	var fit_br: Vector2 = MapProjection.image_to_canvas(size, MapProjection.MAP_SIZE)
	var fit := Rect2(fit_tl, fit_br - fit_tl)
	if _map_tex != null:
		_canvas.draw_texture_rect(_map_tex, fit, false)
	else:
		_canvas.draw_rect(fit, Color(0.10, 0.11, 0.14))
	# 2) Live risk-tinted district regions, translucent so the map reads through.
	for i in districts.size():
		var d: Dictionary = districts[i]
		var poly := _to_canvas_poly(_map_poly_of(d))
		if poly.size() < 3:
			continue
		var risk := _risk_for(d)
		var fill := LOW_RISK.lerp(HIGH_RISK, risk)
		fill.a = 0.30 if i != _hover_index else 0.55
		_canvas.draw_colored_polygon(poly, fill)
		var outline := poly
		outline.append(poly[0])
		_canvas.draw_polyline(outline, Color(0.95, 0.95, 1.0, 0.7), 1.5)
		var center := _centroid(poly)
		_canvas.draw_string(ThemeDB.fallback_font, center - Vector2(46, 0),
			String(d.get("name", d.get("id", "?"))), HORIZONTAL_ALIGNMENT_CENTER, 92, 12)
		# 3a) A focal dot at each district centroid (named just above by the label).
		_canvas.draw_circle(center, 3.0, Color(0.95, 0.95, 1.0, 0.85))
	# 3b) The warehouse rite-site marker, in canonical map space (same space as the district dots).
	var rite: Vector2 = MapProjection.image_to_canvas(size, MapProjection.WAREHOUSE_MAP)
	_canvas.draw_circle(rite, 4.0, Color(0.95, 0.55, 0.2))
	_canvas.draw_string(ThemeDB.fallback_font, rite + Vector2(7, 4),
		"Rite Site", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.97, 0.7, 0.4))
	# 4) Player tracker — a bright pulsing dot, drawn last (on top of everything).
	var player_pos: Vector2 = MapProjection.image_to_canvas(size, MapProjection.world_to_map(AgentRuntime.player_position))
	var t: float = 0.5 + 0.5 * sin(_pulse * 4.0)
	_canvas.draw_circle(player_pos, 7.0 + 2.0 * t, Color(0.40, 0.85, 1.0, 0.25))
	_canvas.draw_circle(player_pos, 4.0, Color(0.45, 0.9, 1.0))
	_canvas.draw_string(ThemeDB.fallback_font, player_pos + Vector2(8, 4),
		"You", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.6, 0.92, 1.0))

func _centroid(poly: PackedVector2Array) -> Vector2:
	var c := Vector2.ZERO
	for p in poly:
		c += p
	return c / poly.size()

func _on_map_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		var prev := _hover_index
		var image_pos: Vector2 = MapProjection.canvas_to_image(_canvas.size, event.position)
		_hover_index = -1
		for i in districts.size():
			if Geometry2D.is_point_in_polygon(image_pos, _map_poly_of(districts[i])):
				_hover_index = i
				break
		if _hover_index != prev:
			_update_readout()
			_canvas.queue_redraw()

func _update_readout() -> void:
	if _hover_index < 0:
		_readout.text = "Hover a district to read its risk."
		return
	var d: Dictionary = districts[_hover_index]
	_readout.text = "%s — risk %d%% (%s)" % [
		String(d.get("name", "?")), int(_risk_for(d) * 100.0),
		String(d.get("risk_pressure", "—")),
	]

# --- Test/debug seam ---------------------------------------------------------------------
func has_map_texture() -> bool:
	return _map_tex != null
