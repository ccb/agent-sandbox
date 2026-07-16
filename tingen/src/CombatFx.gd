extends Node
## Cosmetic combat FX spawner (autoload `CombatFx`) — combat plan §M1, "make a fight legible".
##
## A PURELY COSMETIC, READ-ONLY listener on the EventBus. It subscribes to the combat lifecycle
## events the executor already emits and spawns a short-lived visual at the event's world
## position: a hit spark on a landed strike, an ichor splatter on damage dealt, a dash afterimage
## on a movement cast, a spark burst on a transform. Nothing here mutates combat/agent/world
## state or feeds back into the executor — it only READS agent positions (to place a sprite) and
## writes into its OWN detached FX layer. Combat determinism (the sim's byte-identical transcript,
## the combat vectors) is therefore untouched: with FX on or off the executor sees the same world.
##
## Transients self-expire (a fade tween on the still art) and are freed — pooled bookkeeping keeps
## the layer from leaking. The whole thing is a no-op when disabled or when no SceneTree exists.

## Transient lifetimes (seconds) — short, legible flashes.
const HIT_LIFETIME: float = 0.35
const SPLATTER_LIFETIME: float = 0.6
const DASH_LIFETIME: float = 0.4
const TRANSFORM_LIFETIME: float = 0.7

## On-screen sizes (px, target height) the giant source art is scaled down to.
const HIT_TARGET_H: float = 40.0
const SPLATTER_TARGET_H: float = 48.0
const DASH_TARGET_H: float = 56.0
const TRANSFORM_TARGET_H: float = 72.0

const FX_LAYER_NAME: String = "CombatFxLayer"

## P3: the muzzle flash — brief, small, just ahead of the barrel along the cached aim.
const MUZZLE_LIFETIME: float = 0.12
const MUZZLE_TARGET_H: float = 26.0
const MUZZLE_OFFSET: float = 26.0
## The three authored flash stills, cycled DETERMINISTICALLY (a counter — no RNG anywhere near combat).
const MUZZLE_FRAMES: Array = ["muzzle_flash_1", "muzzle_flash_2", "muzzle_flash_3"]

## Cosmetic master switch (the determinism test flips it; live play leaves it on).
var enabled: bool = true

## caster id -> {ability, dir} — the aim each telegraph carried, consumed at the strike moment.
var _cast_aims: Dictionary = {}
## Probe: what the LAST muzzle flash recorded {caster, ability, at, fx} — headless-assertable.
var _last_muzzle: Dictionary = {}
var _muzzle_seq: int = 0

## Live transients: [{node, age, lifetime}] — stepped by _process (live) or step_fx (headless).
var _transients: Array = []
var _layer: Node2D = null

func _ready() -> void:
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)

## The cosmetic layer nodes never block gameplay; process only advances the fade/free bookkeeping.
func _process(delta: float) -> void:
	_advance(delta)

func set_enabled(on: bool) -> void:
	enabled = on

## READ-ONLY event ear. Never mutates the payload, the agents, or the executor — it only reads a
## position and spawns art. An unknown/off event is ignored.
func _on_event(ev: Dictionary) -> void:
	if not enabled:
		return
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	match String(ev.get("type", "")):
		"agent_attacked":
			# A landed strike: a spark at the target, plus a splatter when damage was dealt.
			var at := _agent_pos(String(d.get("target", "")))
			_spawn(CombatFxLib.DEFAULT_HIT, at, HIT_LIFETIME, HIT_TARGET_H)
			if float(d.get("damage", 0.0)) > 0.0:
				_spawn(CombatFxLib.DEFAULT_SPLATTER, at, SPLATTER_LIFETIME, SPLATTER_TARGET_H)
		"ability_cast_started":
			# P3: remember the telegraph's aim so the strike moment knows where the barrel points.
			_cast_aims[String(d.get("caster", ""))] = {
				"ability": String(d.get("ability", "")), "dir": _dir_of(d)}
			# A dash (movement) leaving the caster: an afterimage wisp at the caster.
			if _is_movement(String(d.get("ability", ""))):
				var at2 := _agent_pos(String(d.get("caster", "")))
				var fx := _fx_of(String(d.get("ability", "")), CombatFxLib.DEFAULT_DASH)
				_spawn(fx, at2, DASH_LIFETIME, DASH_TARGET_H)
		"ability_cast_finished":
			# P3: the strike moment of an AMMO-COSTING art = the round leaving the barrel — flash it.
			_muzzle_for(d)
		"ability_cast_interrupted":
			_cast_aims.erase(String(d.get("caster", "")))
		"transformed":
			# The monstrous reveal: a burst at the transforming body. M10 fix: the spark_burst source is
			# a 1024^2 flipbook SHEET that, drawn whole, reads as an opaque boxy black panel. Spawn it as
			# a per-frame ANIMATED burst off the alpha-keyed cutout so it reads as a burst, not a box.
			var at3 := _agent_pos(String(d.get("agent", "")))
			var fx2 := _fx_of_ability_by_class("transform", CombatFxLib.DEFAULT_TRANSFORM)
			if fx2 == CombatFxLib.DEFAULT_TRANSFORM and CombatFxLib.has_keyed_spark_burst():
				_spawn_spark_burst(at3, TRANSFORM_LIFETIME, TRANSFORM_TARGET_H)
			else:
				_spawn(fx2, at3, TRANSFORM_LIFETIME, TRANSFORM_TARGET_H)

## P3: the muzzle flash. Data-driven off the art's authored cost (cost.ammo > 0 — ANY gun user,
## the player or an NPC gunman, no identity branch): its cast_finished spawns ONE brief flash
## transient just ahead of the caster along the aim the telegraph cached, rotated to it. A free
## art finishing spawns nothing. Cosmetic like every spawn here — reads positions, writes only
## the FX layer.
func _muzzle_for(d: Dictionary) -> void:
	var caster := String(d.get("caster", ""))
	var ability := String(d.get("ability", ""))
	var cached_v: Variant = _cast_aims.get(caster, {})
	var cached: Dictionary = cached_v if cached_v is Dictionary else {}
	_cast_aims.erase(caster)
	if not _costs_ammo(ability):
		return
	var dir_v: Variant = cached.get("dir", Vector2.RIGHT)
	var dir: Vector2 = dir_v if dir_v is Vector2 else Vector2.RIGHT
	if dir.length() <= 0.001:
		dir = Vector2.RIGHT
	dir = dir.normalized()
	var at := _agent_pos(caster) + dir * MUZZLE_OFFSET
	var fx_id := String(MUZZLE_FRAMES[_muzzle_seq % MUZZLE_FRAMES.size()])
	_muzzle_seq += 1
	var before := _transients.size()
	_spawn(fx_id, at, MUZZLE_LIFETIME, MUZZLE_TARGET_H)
	if _transients.size() > before:
		var node: Node = (_transients[_transients.size() - 1] as Dictionary).get("node")
		if node is Node2D:
			(node as Node2D).rotation = dir.angle()
	_last_muzzle = {"caster": caster, "ability": ability, "at": at, "fx": fx_id}

## Probe: the last muzzle flash's record (headless tests assert the wiring on it).
func last_muzzle() -> Dictionary:
	return _last_muzzle

## Does this art's authored cost pay ammo? Pure DATA — the one rule that makes something a gun.
func _costs_ammo(ability_id: String) -> bool:
	var db := _al("AbilityDB")
	if db == null or ability_id == "":
		return false
	var cost: Variant = (db.ability_for(ability_id) as Dictionary).get("cost", {})
	return cost is Dictionary and int((cost as Dictionary).get("ammo", 0)) > 0

## The telegraph's JSON-safe [x, y] aim as a Vector2 (RIGHT when absent/degenerate).
func _dir_of(d: Dictionary) -> Vector2:
	var v: Variant = d.get("dir", null)
	if v is Array and (v as Array).size() >= 2:
		return Vector2(float((v as Array)[0]), float((v as Array)[1]))
	return Vector2.RIGHT

## Spawn one transient sprite at a world position, scaled to a target height, on the FX layer.
func _spawn(fx_id: String, at: Vector2, lifetime: float, target_h: float) -> void:
	var layer := _fx_layer()
	if layer == null:
		return
	var tex := CombatFxLib.texture_for(fx_id, CombatFxLib.DEFAULT_HIT)
	if tex == null:
		return
	var s := Sprite2D.new()
	s.texture = tex
	s.global_position = at
	var h := float(tex.get_height())
	if h > 0.0:
		s.scale = Vector2.ONE * (target_h / h)
	layer.add_child(s)
	_transients.append({"node": s, "age": 0.0, "lifetime": maxf(0.01, lifetime)})

## M10: spawn the transform burst as an ANIMATED sprite off the alpha-keyed flipbook cutout — a
## per-frame burst instead of the raw 1024^2 sheet drawn whole (which read as an opaque boxy panel).
func _spawn_spark_burst(at: Vector2, lifetime: float, target_h: float) -> void:
	var layer := _fx_layer()
	if layer == null:
		return
	var frames := CombatFxLib.spark_burst_frames()
	if frames == null:
		# Keyed sheet vanished after the has_keyed guard — degrade to the flat still, never nothing.
		_spawn(CombatFxLib.DEFAULT_TRANSFORM, at, lifetime, target_h)
		return
	var a := AnimatedSprite2D.new()
	a.sprite_frames = frames
	a.global_position = at
	# Scale a single CELL (not the whole sheet) to the target height.
	var cell_h := float(frames.get_frame_texture("default", 0).get_height())
	if cell_h > 0.0:
		a.scale = Vector2.ONE * (target_h / cell_h)
	layer.add_child(a)
	a.play("default")
	_transients.append({"node": a, "age": 0.0, "lifetime": maxf(0.01, lifetime)})

## True when the transform burst uses the ANIMATED/keyed form (the M10 fix), false when it would
## still fall back to the raw sheet. Read-only CAPABILITY probe (does the keyed cutout exist?) —
## for proof the SPAWNED node is genuinely animated, see spawn_spark_burst_probe() below.
func spark_burst_is_animated() -> bool:
	return CombatFxLib.has_keyed_spark_burst()

## Test seam: actually SPAWN a transform burst (as _on_event("transformed") would) at the origin
## and return the live node so the harness can assert its concrete type — an AnimatedSprite2D when
## the keyed cutout drives the animated form, a plain Sprite2D on the degraded still. Proves the
## fix is "is-using", not merely "would-use". The spawned transient is tracked/expired as usual.
func spawn_spark_burst_probe() -> Node:
	if CombatFxLib.has_keyed_spark_burst():
		_spawn_spark_burst(Vector2.ZERO, TRANSFORM_LIFETIME, TRANSFORM_TARGET_H)
	else:
		_spawn(CombatFxLib.DEFAULT_TRANSFORM, Vector2.ZERO, TRANSFORM_LIFETIME, TRANSFORM_TARGET_H)
	if _transients.is_empty():
		return null
	return (_transients[_transients.size() - 1] as Dictionary).get("node")

## Advance every transient's fade and free the expired ones. COSMETIC time only — the alpha
## fade is a visual tween, never touched by (or touching) the combat clock or the sim.
func _advance(delta: float) -> void:
	if _transients.is_empty():
		return
	var keep: Array = []
	for t_v in _transients:
		var t: Dictionary = t_v
		var node: Node = t.get("node")
		if not is_instance_valid(node):
			continue
		var age := float(t.get("age", 0.0)) + delta
		var life := float(t.get("lifetime", 0.35))
		if age >= life:
			_free(node)
			continue
		var fade := clampf(1.0 - age / life, 0.0, 1.0)
		if node is Sprite2D:
			(node as Sprite2D).modulate.a = fade
		elif node is AnimatedSprite2D:
			# Fade the animated burst too, and hand-advance its frame under the headless harness
			# (no automatic _process ticks under -s) so step_fx drives the flipbook forward.
			var an := node as AnimatedSprite2D
			an.modulate.a = fade
			_step_anim(an, delta)
		t["age"] = age
		keep.append(t)
	_transients = keep

## Headless step for the test harness (no _process ticks under -s). Same bookkeeping.
func step_fx(delta: float) -> void:
	_advance(delta)

## Hand-advance an AnimatedSprite2D's flipbook frame by wall-time (headless-safe). Accumulates the
## frame time on the node's own meta so step_fx can drive the burst forward without a _process tick.
func _step_anim(an: AnimatedSprite2D, delta: float) -> void:
	var frames := an.sprite_frames
	if frames == null:
		return
	var count := frames.get_frame_count("default")
	if count <= 0:
		return
	var fps := maxf(1.0, frames.get_animation_speed("default"))
	var acc := float(an.get_meta("fx_frame_acc", 0.0)) + delta
	while acc >= 1.0 / fps:
		acc -= 1.0 / fps
		an.frame = mini(an.frame + 1, count - 1)
	an.set_meta("fx_frame_acc", acc)

func transient_count() -> int:
	return _transients.size()

func has_fx_layer() -> bool:
	return _layer != null and is_instance_valid(_layer)

func clear_transients() -> void:
	for t_v in _transients:
		var node: Node = (t_v as Dictionary).get("node")
		if is_instance_valid(node):
			_free(node)
	_transients = []

## ---- internals (all read-only against the world) ----

func _free(n: Node) -> void:
	if n.is_inside_tree():
		n.queue_free()
	else:
		n.free()

## The detached cosmetic layer, created on demand under the tree root — never under an Agent,
## an executor, or a combat node, so it can never be walked by combat code.
func _fx_layer() -> Node2D:
	if _layer != null and is_instance_valid(_layer):
		return _layer
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	var root := (ml as SceneTree).root
	var existing := root.get_node_or_null(FX_LAYER_NAME)
	if existing is Node2D:
		_layer = existing
		return _layer
	_layer = Node2D.new()
	_layer.name = FX_LAYER_NAME
	root.add_child(_layer)
	return _layer

## READ-ONLY: the agent's world position from the registry, ZERO when absent (a test id, a
## cross-room ghost). Never touches the agent.
func _agent_pos(id: String) -> Vector2:
	if id == "":
		return Vector2.ZERO
	var reg := _al("Agents")
	if reg == null:
		return Vector2.ZERO
	var a: Object = reg.get_agent(id) if reg.has_method("get_agent") else null
	return a.position if a != null else Vector2.ZERO

func _is_movement(ability_id: String) -> bool:
	var db := _al("AbilityDB")
	if db == null or ability_id == "":
		return false
	return String((db.ability_for(ability_id) as Dictionary).get("class", "")) == "movement"

## The ability's own fx id (default-guarded) — cosmetic lookup, read-only.
func _fx_of(ability_id: String, fallback: String) -> String:
	var db := _al("AbilityDB")
	if db == null or ability_id == "":
		return fallback
	var fx := CombatFxLib.fx_id_of(db.ability_for(ability_id) as Dictionary)
	return fx if fx != "" else fallback

## The fx id of the first ability of a class (transform → assume_form's spark_burst), read-only.
func _fx_of_ability_by_class(klass: String, fallback: String) -> String:
	var db := _al("AbilityDB")
	if db == null:
		return fallback
	for aid in db.all_ability_ids():
		var def: Dictionary = db.ability_for(String(aid))
		if String(def.get("class", "")) == klass:
			var fx := CombatFxLib.fx_id_of(def)
			if fx != "":
				return fx
	return fallback

func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
