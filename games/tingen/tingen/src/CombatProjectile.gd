class_name CombatProjectile
extends Area2D
## One in-flight combat projectile (combat plan §M2): speed, direction, owner, ability ref.
## Travels every combat step along a straight line LOCKED at spawn — dodgeable purely by
## geometry (move out of the path) or by i-frames (the target's resolver zeroes the hit and
## the round flies on). Despawns on the first CONNECTING non-owner contact or at max range.
##
## Stepped by its OWNING executor (never self-stepped) with a data-authoritative `pos`, so
## live tree runs and headless manual stepping advance it identically; the node position
## only mirrors the data for visuals. Hit detection is geometric against hurtbox radii at
## agent.position — same-room only (rooms are separate coordinate spaces).

var source: Agent = null
var ability: Dictionary = {}
var dir: Vector2 = Vector2.RIGHT
var speed: float = 700.0
var max_range: float = 520.0
var travelled: float = 0.0
## Data-authoritative world position.
var pos: Vector2 = Vector2.ZERO
var room: String = ""
var alive: bool = true

## On-screen length the (horizontal) tracer strip is scaled to — a readable dart, not a mural.
const TRACER_TARGET_LEN: float = 44.0

func setup(source_in: Agent, ability_in: Dictionary, origin: Vector2, dir_in: Vector2) -> void:
	source = source_in
	ability = ability_in
	pos = origin
	dir = dir_in.normalized() if dir_in.length() > 0.0 else Vector2.RIGHT
	speed = float((ability_in.get("projectile", {}) as Dictionary).get("speed", 700.0))
	max_range = float(ability_in.get("range", 520.0))
	room = source_in.room if source_in != null else ""
	_apply_fx()
	_mirror()

## Cosmetic only (combat plan §M1): resolve the ability's optional fx to a tracer texture and
## orient it along the LOCKED travel direction. Touches nothing but the Visual sprite — the
## flight geometry (pos/dir/speed) is already set and the sim never reads any of this.
func _apply_fx() -> void:
	var vis := get_node_or_null("Visual") as Sprite2D
	if vis == null:
		return
	var tex := CombatFxLib.texture_for(CombatFxLib.fx_id_of(ability), CombatFxLib.DEFAULT_PROJECTILE)
	if tex != null:
		vis.texture = tex
		var w := float(tex.get_width())
		if w > 0.0:
			vis.scale = Vector2.ONE * (TRACER_TARGET_LEN / w)
	vis.rotation = dir.angle()

func step(dt: float) -> void:
	if not alive:
		return
	var step_len := speed * dt
	pos += dir * step_len
	travelled += step_len
	_mirror()
	var victim := _overlapping_agent()
	if victim != null:
		var deltas := CombatExecutor.route_hit(source, victim, ability, dir)
		# An i-frame dodge (or a vanished target) never consumes the round — it flies on.
		if not deltas.is_empty() and not bool(deltas.get("dodged", false)):
			alive = false
			return
	if travelled >= max_range:
		alive = false

## Nearest non-owner, non-downed agent whose hurtbox the round overlaps this step.
func _overlapping_agent() -> Agent:
	var reg := _agents()
	if reg == null:
		return null
	var best: Agent = null
	var best_d := INF
	for a_v in reg.all():
		var a: Agent = a_v
		if source != null and a.id == source.id:
			continue
		if a.downed or String(a.room) != room:
			continue
		var d := pos.distance_to(a.position)
		if d <= CombatExecutor.radius_of(a.id) and d < best_d:
			best = a
			best_d = d
	return best

func _mirror() -> void:
	if is_inside_tree():
		global_position = pos
	else:
		position = pos

func _agents() -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null("Agents")
