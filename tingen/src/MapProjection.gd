class_name MapProjection
extends RefCounted
## Pure, static, node-free coordinate math. Three spaces:
##   • World space     — the streetscape coords the player/agents live in.
##   • Map-image space — map_v3.png pixels (MAP_SIZE). The single canonical authoring space:
##     city_layout.json, district map_polygons, and the player tracker are all expressed here.
##   • Canvas space    — the map panel's Map control pixels (runtime-sized).
## ONE global uniform transform links world and map space (CITY_SCALE), so the map tracker is
## accurate everywhere, not just inside one district. image_to_canvas / canvas_to_image are the
## panel's aspect-fit letterbox and are independent of CITY_SCALE.

const MAP_SIZE := Vector2(1254.0, 1254.0)
## World units per map pixel — UNIFIED with the live scene (coordinate-unification pass):
## City.tscn's ground is city_ground.png (2508px, a 2x render of the 1254 map) at node scale 2.5,
## i.e. a (0,0)..(6270,6270) world = exactly 5.0 world units per map pixel. Under the old 3.5 the
## southern city (Chapel, player start) projected off the map image and the rite anchor landed
## inside the wrong building. A full-city walk is ~52 s at the player's 120 u/s.
const CITY_SCALE := 5.0
## The 降临 / rite site, in the canonical map-image space. Its world position =
## map_to_world(WAREHOUSE_MAP) = ~(5366.65, 2378.09) — the sabotage cache (Warehouse/RiteCache)
## at the REAL Warehouse building in City.tscn; its map marker is itself.
const WAREHOUSE_MAP := Vector2(1073.33, 475.618)

## Map-image space -> world space.
static func map_to_world(map_pos: Vector2) -> Vector2:
	return map_pos * CITY_SCALE

## World space -> map-image space (exact inverse of map_to_world).
static func world_to_map(world_pos: Vector2) -> Vector2:
	return world_pos / CITY_SCALE

## Map-image -> canvas: aspect-preserving (letterbox) fit of MAP_SIZE into canvas_size.
## Uniform scale, centered; never distorts the art, so every overlay stays aligned to it.
static func image_to_canvas(canvas_size: Vector2, p: Vector2) -> Vector2:
	var scale: float = minf(canvas_size.x / MAP_SIZE.x, canvas_size.y / MAP_SIZE.y)
	var offset: Vector2 = (canvas_size - MAP_SIZE * scale) * 0.5
	return offset + p * scale

## Canvas -> map-image: the exact inverse of image_to_canvas (for hover hit-testing).
## A zero/negative-size canvas (e.g. before first layout) has no valid inverse; pass the
## point through unchanged rather than dividing by zero into inf/nan.
static func canvas_to_image(canvas_size: Vector2, p: Vector2) -> Vector2:
	var scale: float = minf(canvas_size.x / MAP_SIZE.x, canvas_size.y / MAP_SIZE.y)
	if scale <= 0.0:
		return p
	var offset: Vector2 = (canvas_size - MAP_SIZE * scale) * 0.5
	return (p - offset) / scale
