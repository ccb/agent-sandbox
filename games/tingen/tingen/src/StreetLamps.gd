extends Node2D
## Street-lamp glows for the live City (P5 experiential wave — the city reads as a PLACE).
##
## PRESENTATION ONLY + LIVE-ONLY. Under a real display this node mounts a handful of additive
## glow sprites — a soft warm halo with a bright core, gaslight against the painted streets — at
## the DATA-authored lamp spots near the doors and waypoints players actually visit. Headless
## (`--headless`, every deterministic gate) it mounts NOTHING (the CombatFeedback._is_live
## pattern), so the pinned sims stay byte-identical by construction.
##
## DATA-DRIVEN: the spots live in data/city_layout.json under "lamps", authored in the canonical
## MAP-IMAGE space (MapProjection: world = map px * CITY_SCALE) like every other map-anchored
## point. Phase-gated: lamps burn from dusk through late-night (the lamplighter's hours) and are
## cold by day — lit_for_phase() is the pure seam tests/test_city_place.gd pins.
##
## CHEAP: every sprite is created ONCE in _ready and only `visible` flips on Clock.phase_changed;
## the glow textures are two shared GradientTexture2Ds (no art files, no per-frame allocation).

const LAYOUT_PATH: String = "res://data/city_layout.json"
## The phases the lamps burn — the truth table the tests pin.
const LIT_PHASES: Dictionary = {"dusk": true, "night": true, "late-night": true}
const HALO_COLOR := Color(1.0, 0.72, 0.38, 0.42)
const CORE_COLOR := Color(1.0, 0.88, 0.62, 0.9)
const HALO_RADIUS_PX: float = 175.0   # world px — a soft pool of gaslight
const CORE_RADIUS_PX: float = 22.0    # world px — the burning mantle itself

var _glows: Array = []   # per-lamp root nodes (live only)
var _lit: bool = false

## Pure: is a lamp burning in this phase? (dusk/night/late-night on; the day phases off)
static func lit_for_phase(phase: String) -> bool:
	return bool(LIT_PHASES.get(phase, false))

## The authored lamp spots in map-image px (pure data read; [] when unauthored).
static func lamp_map_points() -> Array:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT_PATH))
	if not (parsed is Dictionary):
		return []
	var out: Array = []
	for lp in ((parsed as Dictionary).get("lamps", []) as Array):
		if lp is Array and (lp as Array).size() >= 2:
			out.append(Vector2(float(lp[0]), float(lp[1])))
	return out

func _ready() -> void:
	if DisplayServer.get_name() == "headless":
		return   # live-only presentation — the deterministic gates never see a glow node
	_spawn_glows()
	_apply_phase(Clock.phase)
	Clock.phase_changed.connect(_on_phase_changed)

func _on_phase_changed(phase: String, _day: int) -> void:
	_apply_phase(phase)

func _apply_phase(phase: String) -> void:
	_lit = lit_for_phase(phase)
	for g in _glows:
		(g as CanvasItem).visible = _lit

func _spawn_glows() -> void:
	var mat := CanvasItemMaterial.new()
	mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	var halo_tex := _radial_texture(HALO_COLOR)
	var core_tex := _radial_texture(CORE_COLOR)
	for p in lamp_map_points():
		var lamp := Node2D.new()
		lamp.position = MapProjection.map_to_world(p)
		lamp.z_index = 20   # light paints OVER the y-sorted streetscape, under the HUD layer
		var halo := Sprite2D.new()
		halo.texture = halo_tex
		halo.material = mat
		halo.scale = Vector2.ONE * (HALO_RADIUS_PX * 2.0 / float(halo_tex.get_width()))
		lamp.add_child(halo)
		var core := Sprite2D.new()
		core.texture = core_tex
		core.material = mat
		core.scale = Vector2.ONE * (CORE_RADIUS_PX * 2.0 / float(core_tex.get_width()))
		lamp.add_child(core)
		add_child(lamp)
		_glows.append(lamp)

## A soft radial disc (centre colour easing to a transparent edge), generated once — no art file.
static func _radial_texture(centre: Color) -> GradientTexture2D:
	var grad := Gradient.new()
	var mid := Color(centre.r, centre.g, centre.b, centre.a * 0.45)
	var edge := Color(centre.r, centre.g, centre.b, 0.0)
	grad.colors = PackedColorArray([centre, mid, edge])
	grad.offsets = PackedFloat32Array([0.0, 0.4, 1.0])
	var tex := GradientTexture2D.new()
	tex.gradient = grad
	tex.fill = GradientTexture2D.FILL_RADIAL
	tex.fill_from = Vector2(0.5, 0.5)
	tex.fill_to = Vector2(0.5, 0.0)
	tex.width = 128
	tex.height = 128
	return tex

# --- probe/test seams ----------------------------------------------------------------------------
## How many lamp glows are mounted (0 headless — pinned; the live count is probe-proven).
func glow_count() -> int:
	return _glows.size()

## Are the lamps burning right now?
func lit_now() -> bool:
	return _lit

## The nearest mounted glow's world position to `from` (the probe walks the rig here), or INF.
func nearest_glow_pos(from: Vector2) -> Vector2:
	var best := Vector2.INF
	var best_d := INF
	for g in _glows:
		var d: float = (g as Node2D).global_position.distance_to(from)
		if d < best_d:
			best_d = d
			best = (g as Node2D).global_position
	return best
