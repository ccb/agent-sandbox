class_name CityLayout
extends RefCounted
## Pure, node-free loader for the canonical city authoring data (data/city_layout.json).
## Parses the map-pixel-space JSON, applies MapProjection.map_to_world so callers receive
## WORLD-space geometry, and exposes typed getters. This is the headless-testable seam for the
## city authoring data (mirrors MapProjection / EndGameResolver). Also hosts the navmesh bake
## helper so the outline-minus-obstacles math lives next to the data that feeds it.

const LAYOUT_PATH := "res://data/city_layout.json"

var _outline: PackedVector2Array
var _water: Array          # Array[PackedVector2Array]
var _blocks: Array         # Array[PackedVector2Array]
var _landmarks: Array      # Array[Dictionary] { pos: Vector2 (world), label: String }

## Load + parse the default data file. Returns a populated CityLayout (empty on missing/bad file).
static func load_default() -> CityLayout:
	if not FileAccess.file_exists(LAYOUT_PATH):
		push_warning("CityLayout: missing %s" % LAYOUT_PATH)
		return CityLayout.new()
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT_PATH))
	return from_dict(parsed if typeof(parsed) == TYPE_DICTIONARY else {})

## Build from an already-parsed Dictionary (no file I/O) — the seam headless tests drive directly.
static func from_dict(data: Dictionary) -> CityLayout:
	var c := CityLayout.new()
	c._outline = _to_world_poly(data.get("city_outline", []))
	for w in data.get("water", []):
		c._water.append(_to_world_poly(w))
	for b in data.get("blocks", []):
		c._blocks.append(_to_world_poly(b))
	for lm in data.get("landmarks", []):
		var p: Array = (lm as Dictionary).get("pos", [0, 0])
		c._landmarks.append({
			"pos": MapProjection.map_to_world(Vector2(float(p[0]), float(p[1]))),
			"label": String((lm as Dictionary).get("label", "")),
		})
	return c

func outline() -> PackedVector2Array: return _outline
func water() -> Array: return _water
func blocks() -> Array: return _blocks
func landmarks() -> Array: return _landmarks

## --- Room affordance TAGS (lab pull-in P2) --------------------------------------------------
## The room half of the declarative-affordance contract (verb half: action_schema.json
## `affordances`). Pure data from this file's `room_affordances` section; cached once. An unknown
## or untagged room yields [] — its menu curates down to the universal verbs.
static var _room_tags: Dictionary = {}
static var _room_tags_loaded: bool = false

static func room_affordances(room: String) -> Array:
	if not _room_tags_loaded:
		_room_tags_loaded = true
		if FileAccess.file_exists(LAYOUT_PATH):
			var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT_PATH))
			if parsed is Dictionary and (parsed as Dictionary).get("room_affordances") is Dictionary:
				_room_tags = (parsed as Dictionary)["room_affordances"]
	var tags: Variant = _room_tags.get(room, [])
	return (tags as Array).duplicate() if tags is Array else []

## Flat [x,y,x,y,...] map-pixel array -> world-space PackedVector2Array.
static func _to_world_poly(raw: Array) -> PackedVector2Array:
	var pts := PackedVector2Array()
	for i in range(0, raw.size() - 1, 2):
		pts.append(MapProjection.map_to_world(Vector2(float(raw[i]), float(raw[i + 1]))))
	return pts

## Bake a NavigationPolygon whose walkable area is `outline_world` minus every polygon in
## `holes_world` (blocks + water). Modern source-geometry API — NO deprecated
## make_polygons_from_outlines, so output stays warning-free. agent_radius 0 keeps the narrow
## alleys between blocks walkable. Pure: returns the resource; the caller owns map registration.
static func build_nav_polygon(outline_world: PackedVector2Array, holes_world: Array) -> NavigationPolygon:
	var nav := NavigationPolygon.new()
	nav.agent_radius = 0.0
	var src := NavigationMeshSourceGeometryData2D.new()
	src.add_traversable_outline(outline_world)
	for h in holes_world:
		src.add_obstruction_outline(h as PackedVector2Array)
	NavigationServer2D.bake_from_source_geometry_data(nav, src)
	return nav
