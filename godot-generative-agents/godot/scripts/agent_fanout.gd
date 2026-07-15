extends RefCounted
## Pure helpers for spreading co-located agent sprites so stacks stay visible
## (issue #560). No scene/node state, so tests/test_agent_fanout.gd exercises
## them headless. VIEW-ONLY: these offsets nudge where a sprite is DRAWN; an
## agent's logical tile is unchanged (see the viewer.gd wiring).

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


static func offset(index: int, count: int, spacing_px: float) -> Vector2:
	# Displacement for agent `index` of `count` co-located agents, arranged on a
	# ring. count <= 1 -> ZERO (the common case, no cost). The ring radius is
	# chosen so ADJACENT agents are always ~spacing_px apart regardless of count
	# (chord = 2*r*sin(PI/count) = spacing), so the cluster reads consistently
	# whether it's 2 or 6 agents. Callers pass a spacing tied to the on-screen
	# sprite size (viewer: SPRITE_HALF_PX) so the sprites visibly clear each other
	# -- the campus sprites are ~4x the tile, so a tile-sized offset is too tight.
	if count <= 1:
		return Vector2.ZERO
	var radius := spacing_px / (2.0 * sin(PI / float(count)))
	var angle := TAU * float(index) / float(count)
	return Vector2(cos(angle), sin(angle)) * radius
