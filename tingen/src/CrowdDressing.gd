extends Node2D
## Ambient CROWD DRESSING for the live City (P5 experiential wave) — small standee clusters
## (a market knot, dock idlers, drinkers outside the tavern) so the streets read INHABITED in
## the space between real agents.
##
## DRESSING, NOT PEOPLE. Plain Sprite2D standees: no agents, no schedules, no collision, no
## "npc" group, no prompts, nothing interactive — the LLM roster, the schedule load and the
## deterministic sims never know these exist.
##
## LIVE-ONLY (the CombatFeedback._is_live pattern): headless this node mounts NOTHING, pinned by
## tests/test_city_place.gd; the rendered standees are proven by tests/screenshot_probe.gd.
##
## DATA-DRIVEN: clusters live in data/city_layout.json under "crowds" — cluster `pos` in the
## canonical map-image space, per-figure `dx/dy` offsets in world px, and `art` naming an
## existing assets/characters/<art>.png (the same convention NPC bodies resolve, reused at
## BACKGROUND scale — a shade smaller and dimmer than the live cast, so the real people read in
## front). Placement legality (inside the world, clear of building colliders, clear of every
## scheduled waypoint and door) is pinned by the tests exactly like the fill-blocks buildout.

const LAYOUT_PATH: String = "res://data/city_layout.json"
const CHAR_DIR: String = "res://assets/characters/"
## Background scale: a shade under the live NPC bodies' 48 px silhouette.
const FIGURE_TARGET_H: float = 44.0
## Sit the standees back into the street (slightly dimmed, never repainted).
const FIGURE_MODULATE := Color(0.86, 0.84, 0.82, 1.0)

var _figures: Array = []   # mounted standee sprites (live only)

## Pure data read: the authored clusters ([] when unauthored).
static func load_clusters() -> Array:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT_PATH))
	if not (parsed is Dictionary):
		return []
	return ((parsed as Dictionary).get("crowds", []) as Array)

## A cluster's world-space centre from the data (works headless — the probe's camera anchor);
## Vector2.INF when the id is unauthored.
static func cluster_center_for(clusters: Array, id: String) -> Vector2:
	for cl in clusters:
		var cd := cl as Dictionary
		if String(cd.get("id", "")) == id and cd.get("pos") is Array:
			return MapProjection.map_to_world(Vector2(float(cd["pos"][0]), float(cd["pos"][1])))
	return Vector2.INF

func cluster_center(id: String) -> Vector2:
	return cluster_center_for(load_clusters(), id)

func _ready() -> void:
	# Nested y-sort: with the City root also y-sorting, standees occlude / are occluded by
	# buildings and walkers per their street position, exactly like real bodies.
	y_sort_enabled = true
	if DisplayServer.get_name() == "headless":
		return   # live-only dressing — the deterministic gates never see a standee
	for cl in load_clusters():
		var cd := cl as Dictionary
		if not (cd.get("pos") is Array):
			continue
		var base: Vector2 = MapProjection.map_to_world(Vector2(float(cd["pos"][0]), float(cd["pos"][1])))
		for fig in (cd.get("figures", []) as Array):
			var fd := fig as Dictionary
			var s := _make_standee(fd)
			if s != null:
				s.position = base + Vector2(float(fd.get("dx", 0)), float(fd.get("dy", 0)))
				add_child(s)
				_figures.append(s)

## One standee: the character art at background scale, FEET at its position (the y-sort anchor).
## Defensive — missing/bogus art returns null and the cluster simply stands one figure short.
func _make_standee(fd: Dictionary) -> Sprite2D:
	var art := String(fd.get("art", ""))
	var path := "%s%s.png" % [CHAR_DIR, art]
	if art == "" or not ResourceLoader.exists(path):
		return null
	var tex: Texture2D = load(path)
	if tex == null:
		return null
	var s := Sprite2D.new()
	s.texture = tex
	s.centered = false
	s.offset = Vector2(-tex.get_width() * 0.5, -float(tex.get_height()))   # feet at position
	s.scale = Vector2.ONE * (FIGURE_TARGET_H / float(tex.get_height()))
	s.flip_h = bool(fd.get("flip", false))
	s.modulate = FIGURE_MODULATE
	s.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	return s

# --- probe/test seam -------------------------------------------------------------------------
## How many standees are mounted (0 headless — pinned; the live count is probe-proven).
func figure_count() -> int:
	return _figures.size()
