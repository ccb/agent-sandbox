class_name CombatZone
extends Area2D
## One persistent ground effect (combat plan §M2): radius, duration, tick cadence, named
## statuses (e.g. paper_charm's slow + silence). On spawn and then every tick_ms it applies
## its statuses to each non-owner agent standing inside, routed through the target's
## executor (receive_status re-stamps them onto the TARGET's clock — every executor keeps
## its own). Standing inside keeps a status refreshed; stepping out lets it lapse. Silence
## blocks windup start — the executor's try_cast checks.
##
## Stepped by its OWNING executor (never self-stepped), geometric detection at
## agent.position — deterministic, no physics-server dependency. An executor-less agent
## inside the zone is unaffected (nowhere for the status to live; documented M2 limit).
## Zone statuses deliberately BYPASS i-frames (reviewed M2, intended): a dash through charm
## smoke still breathes it — i-frames dodge HITS (apply_ability), not the air you stand in.

var source: Agent = null
var pos: Vector2 = Vector2.ZERO
var radius: float = 90.0
var duration_ms: int = 4000
var tick_ms: int = 500
var status_names: Array = []
var room: String = ""
var alive: bool = true

var _age_s: float = 0.0
var _last_tick_ms: int = 0
## Optional cosmetic fx id (stamped by the spawning executor from the ability's fx field).
var _fx_id: String = ""

func setup(source_in: Agent, effect: Dictionary, center: Vector2) -> void:
	source = source_in
	pos = center
	radius = float(effect.get("radius", 90.0))
	duration_ms = int(round(float(effect.get("duration", 4.0)) * 1000.0))
	tick_ms = maxi(1, int(round(float(effect.get("tick", 0.5)) * 1000.0)))
	status_names = (effect.get("statuses", []) as Array).duplicate()
	var fx_raw: Variant = effect.get("fx", "")
	_fx_id = fx_raw if fx_raw is String else ""   # type-guard: non-string fx degrades to default
	room = source_in.room if source_in != null else ""
	_last_tick_ms = -tick_ms   # first application lands the moment the zone exists
	_apply_fx()
	_mirror()

## Cosmetic only (combat plan §M1): the ground glyph sized so its on-screen radius tracks the
## zone's effect radius. Reads only the effect's `fx`/`radius` (already parsed), writes only the
## Visual sprite — the tick geometry and status routing never see any of this.
func _apply_fx() -> void:
	var vis := get_node_or_null("Visual") as Sprite2D
	if vis == null:
		return
	var tex := CombatFxLib.texture_for(_fx_id, CombatFxLib.DEFAULT_ZONE)
	if tex != null:
		vis.texture = tex
	if vis.texture != null:
		var h := float(vis.texture.get_height())
		if h > 0.0:
			vis.scale = Vector2.ONE * (2.0 * radius / h)

func step(dt: float) -> void:
	if not alive:
		return
	_age_s += dt
	var now := int(round(_age_s * 1000.0))
	var stop := mini(now, duration_ms)
	while _last_tick_ms + tick_ms <= stop:
		_last_tick_ms += tick_ms
		_apply_tick()
	if now >= duration_ms:
		alive = false

## One tick: every non-owner agent standing inside gets each named status (resolver-shaped
## via status_from_name), routed through ITS executor.
func _apply_tick() -> void:
	var reg := _agents()
	if reg == null:
		return
	for a_v in reg.all():
		var a: Agent = a_v
		if source != null and a.id == source.id:
			continue
		if a.downed or String(a.room) != room:
			continue
		if pos.distance_to(a.position) > radius:
			continue
		var ex := CombatExecutor.for_agent(a.id)
		if ex == null:
			continue
		for name_v in status_names:
			var st := CombatResolver.status_from_name(String(name_v), 0,
				source.id if source != null else "")
			if not st.is_empty():
				ex.receive_status(st)

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
