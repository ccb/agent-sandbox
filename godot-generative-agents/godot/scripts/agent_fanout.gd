extends RefCounted
## Pure helpers for spreading co-located agent sprites so stacks stay visible
## (issue #560). No scene/node state, so tests/test_agent_fanout.gd exercises
## them headless. VIEW-ONLY: these offsets nudge where a sprite is DRAWN; an
## agent's logical tile is unchanged (see the viewer.gd wiring).

# Ring geometry as fractions of the tile size, so it scales with tile_px and the
# sprites stay on/near the tile.
const _RADIUS_BASE := 0.15
const _RADIUS_STEP := 0.06
const _RADIUS_CAP := 0.36


static func groups(tiles: Dictionary) -> Dictionary:
	# tiles: {name(String): Vector2i}. Returns {Vector2i: Array[String]} of the
	# names sharing each tile, sorted by name so an agent's index within its group
	# is stable frame-to-frame (independent of iteration order).
	var by_tile := {}
	for name in tiles:
		var t: Vector2i = tiles[name]
		if not by_tile.has(t):
			by_tile[t] = []
		by_tile[t].append(name)
	for t in by_tile:
		by_tile[t].sort()
	return by_tile


static func offset(index: int, count: int, tile_px: float) -> Vector2:
	# Sub-tile displacement for agent `index` of `count` co-located agents.
	# count <= 1 -> ZERO (the common case, no cost). Otherwise a point on a ring:
	# angle TAU*index/count, radius scaling gently with count and capped near the
	# tile edge so the sprite stays on/around the tile.
	if count <= 1:
		return Vector2.ZERO
	var radius := minf(
		tile_px * (_RADIUS_BASE + _RADIUS_STEP * count), tile_px * _RADIUS_CAP
	)
	var angle := TAU * float(index) / float(count)
	return Vector2(cos(angle), sin(angle)) * radius
