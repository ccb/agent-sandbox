extends Node
## Cosmetic combat feedback (autoload `CombatFeedback`) — M10 polish: screen-shake + hit-flash.
##
## A PURELY COSMETIC, READ-ONLY companion to CombatFx. It listens to the same combat lifecycle
## events and, when the PLAYER is involved, produces two juice cues: a brief CAMERA SHAKE (an offset
## on the active Camera2D) and a full-screen HIT FLASH (a red vignette on a detached CanvasLayer).
## Both are GATED by the Settings toggles — with a toggle off, the corresponding helper is a
## verified no-op (it produces zero amplitude / zero alpha and touches nothing).
##
## Determinism: like CombatFx this NEVER mutates combat/agent/world state and never feeds the
## executor. The combat_sim transcript is byte-identical with feedback on or off — the toggles gate
## a camera offset and an overlay alpha, nothing the sim can observe. The whole node is a no-op when
## no SceneTree / camera exists (headless), so the harness drives shake()/flash() directly and reads
## the probe fields (last_shake_amplitude / last_flash_alpha) to assert the gate.

const SHAKE_DURATION: float = 0.25
const SHAKE_DEFAULT_AMPLITUDE: float = 6.0
const FLASH_DURATION: float = 0.18
const FLASH_MAX_ALPHA: float = 0.35
const FLASH_LAYER_NAME: String = "HitFlashLayer"

## M24 Tier-1 combat JUICE tiers (all cosmetic, all Settings-gated). The shake amplitudes form the
## kinesthetic ladder: a small KICK when the player lands a hit, a MEDIUM jolt on a kill, a BIG
## slam on the mask-drop (transform). The hit-stop is a brief global time-scale dip on a landed
## player hit / a kill — LIVE-ONLY (see hitstop()), so the headless fixed-dt sim never feels it.
const SHAKE_HIT_KICK: float = 3.0        # player lands a hit — a light punch
const SHAKE_DOWNED: float = 8.0          # a kill — a medium jolt
const SHAKE_TRANSFORM: float = 14.0      # the mask-drop signature — a big slam
const HITSTOP_HIT_MS: float = 50.0       # ~a couple frames of stutter on a landed hit
const HITSTOP_DOWNED_MS: float = 75.0    # a slightly longer beat on the kill
const HITSTOP_SCALE: float = 0.05        # how far time_scale dips during a hit-stop (live only)

## Probe fields (headless-observable): the amplitude/alpha the LAST helper call committed. A gated-off
## call commits 0.0 — the tests assert exactly this to prove the toggle takes effect (not dead UI).
var _last_shake_amplitude: float = 0.0
var _last_flash_alpha: float = 0.0
## The hit-stop duration (ms) the LAST hitstop() call committed — 0.0 when gated off.
var _last_hitstop_ms: float = 0.0

## Live hit-stop state: a real-wall-clock recovery of Engine.time_scale (never used headless).
var _hitstop_active: bool = false
var _hitstop_until_ms: int = 0

## Live shake state (a decaying offset applied to the active camera each frame).
var _shake_amp: float = 0.0
var _shake_t: float = 0.0
var _shake_base: Vector2 = Vector2.ZERO
var _shaken_cam: Camera2D = null

## Live flash state (a fading red overlay).
var _flash_rect: ColorRect = null
var _flash_t: float = 0.0

func _ready() -> void:
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)

func _process(delta: float) -> void:
	_advance(delta)
	_advance_hitstop()
	_advance_tells()
	if _is_live():
		_ensure_reticle()
		_pulse_casters()

# --- Event ear (player-involved combat + the signature beats) ---------------------------------
func _on_event(ev: Dictionary) -> void:
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	match String(ev.get("type", "")):
		"ability_cast_started":
			# P3: the on-enemy tell — the SAME telegraph event the HUD text keys on.
			_record_tell(d)
		"ability_cast_finished", "ability_cast_interrupted":
			_clear_tell(String(d.get("caster", "")))
		"agent_attacked":
			var target_id := String(d.get("target", ""))
			var actor_id := String(d.get("actor", ""))
			# The player takes a hit -> shake + flash (a landed strike ON the player).
			if target_id == "player":
				shake(SHAKE_DEFAULT_AMPLITUDE)
				if float(d.get("damage", 0.0)) > 0.0:
					flash()
			# M24 (a): the PLAYER lands a hit -> a global HIT-STOP + a small kick (the outgoing punch).
			if actor_id == "player":
				hitstop(HITSTOP_HIT_MS)
				shake(SHAKE_HIT_KICK)
			# M24 (b): whiten the STRUCK enemy body for a beat (never the player proxy).
			if target_id != "" and target_id != "player":
				_whiten_target(target_id)
		"transformed":
			# M24 (c): the mask-drop signature beat — a BIG shake as the monstrous form lands.
			shake(SHAKE_TRANSFORM)
		"agent_downed":
			# M24 (c): the kill punch — a MEDIUM shake + a beat of hit-stop.
			shake(SHAKE_DOWNED)
			hitstop(HITSTOP_DOWNED_MS)

# --- Public helpers (gated) -------------------------------------------------------------------
## Kick a camera shake of the given amplitude. GATED: with screen_shake OFF this is a no-op and
## commits amplitude 0.0. Cosmetic only.
func shake(amplitude: float = SHAKE_DEFAULT_AMPLITUDE) -> void:
	if not _shake_enabled():
		_last_shake_amplitude = 0.0
		return
	_last_shake_amplitude = amplitude
	_shake_amp = amplitude
	_shake_t = SHAKE_DURATION
	# Latch onto the active camera (if any). Remember its base offset so we restore it cleanly.
	var cam := _active_camera()
	if cam != null and cam != _shaken_cam:
		_shaken_cam = cam
		_shake_base = cam.offset

## Trigger a full-screen hit flash. GATED: with hit_flash OFF this is a no-op and commits alpha 0.0.
func flash(max_alpha: float = FLASH_MAX_ALPHA) -> void:
	if not _flash_enabled():
		_last_flash_alpha = 0.0
		return
	_last_flash_alpha = max_alpha
	_flash_t = FLASH_DURATION
	var rect := _flash_overlay()
	if rect != null:
		rect.color = Color(rect.color.r, rect.color.g, rect.color.b, max_alpha)

## M24: kick a brief GLOBAL HIT-STOP — a short dip in Engine.time_scale that recovers on its own.
## GATED: with hit_stop OFF this is a no-op and commits 0.0. LIVE-ONLY: the time_scale write happens
## ONLY when a real display exists (live play). Under --headless (every test harness: combat_sim,
## run_combat_vectors, full_run, run_tests) we record the probe field but NEVER touch time_scale, so
## the deterministic fixed-dt sim — which steps step_combat(1.0/60.0) on its OWN accumulated clock and
## never reads the scaled frame delta — is provably untouched. Recovery is timed off the REAL wall
## clock (Time.get_ticks_msec), immune to the very time-scale it sets.
func hitstop(ms: float = HITSTOP_HIT_MS) -> void:
	if not _hitstop_enabled():
		_last_hitstop_ms = 0.0
		return
	_last_hitstop_ms = ms
	if _is_live():
		Engine.time_scale = HITSTOP_SCALE
		_hitstop_active = true
		_hitstop_until_ms = Time.get_ticks_msec() + int(maxf(0.0, ms))

# --- Probe (test-observable) ------------------------------------------------------------------
func reset_probe() -> void:
	_last_shake_amplitude = 0.0
	_last_flash_alpha = 0.0
	_last_hitstop_ms = 0.0

func last_shake_amplitude() -> float:
	return _last_shake_amplitude

func last_flash_alpha() -> float:
	return _last_flash_alpha

func last_hitstop_ms() -> float:
	return _last_hitstop_ms

# --- Per-frame decay --------------------------------------------------------------------------
func _advance(delta: float) -> void:
	# Shake decay.
	if _shake_t > 0.0:
		_shake_t = maxf(0.0, _shake_t - delta)
		var frac := _shake_t / SHAKE_DURATION
		var mag := _shake_amp * frac
		if _shaken_cam != null and is_instance_valid(_shaken_cam):
			var jitter := Vector2(randf_range(-mag, mag), randf_range(-mag, mag))
			_shaken_cam.offset = _shake_base + jitter
			if _shake_t <= 0.0:
				_shaken_cam.offset = _shake_base
				_shaken_cam = null
	# Flash decay.
	if _flash_t > 0.0 and _flash_rect != null and is_instance_valid(_flash_rect):
		_flash_t = maxf(0.0, _flash_t - delta)
		var a := _last_flash_alpha * (_flash_t / FLASH_DURATION)
		_flash_rect.color = Color(_flash_rect.color.r, _flash_rect.color.g, _flash_rect.color.b, a)

# --- Hit-stop recovery (live only) ------------------------------------------------------------
## Restore Engine.time_scale to 1.0 once the real-time hit-stop window elapses. Runs every frame in
## live play; a no-op headless (a hit-stop is never armed there). Timed off the wall clock so the
## dipped time_scale can't stall its own recovery.
func _advance_hitstop() -> void:
	if _hitstop_active and Time.get_ticks_msec() >= _hitstop_until_ms:
		Engine.time_scale = 1.0
		_hitstop_active = false

# --- Enemy whiten (M24 (b)) -------------------------------------------------------------------
## Whiten the STRUCK enemy body for a beat, then let it restore itself. GATED under hit_flash. READ-
## ONLY on combat state — it only writes the body's cosmetic Sprite2D modulate (via NPC.flash_hit),
## never agent/world state. Engine-neutral: finds the body by the "npc" group + its npc_id, no id
## branch. A missing body (a headless id with no scene node) is simply skipped.
func _whiten_target(id: String) -> void:
	if not _flash_enabled():
		return
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return
	for body in (ml as SceneTree).get_nodes_in_group("npc"):
		if body != null and String(body.get("npc_id")) == id and body.has_method("flash_hit"):
			body.flash_hit()
			return

# --- P3 combat readability: on-enemy tells + hp-pip support + the combat reticle ---------------
## The tell LEDGER is deterministic state (recorded headless too — tests pin the wiring on it);
## every NODE it drives is live-only (_is_live), so the headless sims spawn nothing and stay
## byte-identical. Engine-neutral: kind/range/dir come from the ability DATA on the telegraph
## event, never from who is casting.
const TELL_LAYER_NAME: String = "CombatTellLayer"
const RETICLE_LAYER_NAME: String = "CombatReticleLayer"
## UI safety net: a tell whose finish/interrupt event was never heard still expires this long
## (wall-clock ms) past its telegraphed cast_time — mirrors the HUD text's prune rule.
const TELL_GRACE_MS: int = 500
## Windup pulse on the caster's sprite: pace (Hz) + how deep the blend toward the telegraph color goes.
const TELL_PULSE_HZ: float = 5.0
const TELL_PULSE_DEPTH: float = 0.55

## caster id -> {kind: arc|circle, ability, range, dir, until_ms} — the live wind-ups.
var _tells: Dictionary = {}
## caster id -> {sprite, base} — self_modulate restore ledger for the windup pulse (the hit-flash
## whiten writes `modulate`; the pulse rides `self_modulate`, so the two never fight).
var _pulsed: Dictionary = {}
var _tell_layer: Node2D = null
var _reticle: CanvasLayer = null

## The tell ledger (read-only probe: tests + the tell layer draw from it).
func active_tells() -> Dictionary:
	return _tells.duplicate()

func clear_tells() -> void:
	for caster in _tells.keys().duplicate():
		_clear_tell(String(caster))

## Record a wind-up as an on-enemy tell. The PLAYER's own casts never tell (mirrors the HUD text
## rule); kind is pure ability DATA — a strike sweeps an ARC, everything else marks a CIRCLE.
func _record_tell(d: Dictionary) -> void:
	var caster := String(d.get("caster", ""))
	if caster == "" or caster == "player":
		return
	var ability := String(d.get("ability", ""))
	var klass := ""
	var reach := 0.0
	var adb := _al("AbilityDB")
	if adb != null:
		var adef: Dictionary = adb.ability_for(ability)
		klass = String(adef.get("class", ""))
		reach = float(adef.get("range", 0.0))
	var dir := Vector2.RIGHT
	var dir_v: Variant = d.get("dir", null)
	if dir_v is Array and (dir_v as Array).size() >= 2:
		var dv := Vector2(float((dir_v as Array)[0]), float((dir_v as Array)[1]))
		if dv.length() > 0.001:
			dir = dv.normalized()
	_tells[caster] = {
		"kind": "arc" if klass == "strike" else "circle",
		"ability": ability,
		"range": reach,
		"dir": dir,
		"until_ms": Time.get_ticks_msec()
			+ int(round(float(d.get("cast_time", 0.0)) * 1000.0)) + TELL_GRACE_MS,
	}
	if _is_live():
		_ensure_tell_layer()

func _clear_tell(caster: String) -> void:
	_tells.erase(caster)
	_restore_pulse(caster)

## Wall-clock prune (UI net only — the ledger is presentation state, never combat state).
func _advance_tells() -> void:
	if _tells.is_empty():
		return
	var now := Time.get_ticks_msec()
	for caster in _tells.keys().duplicate():
		if now >= int((_tells[caster] as Dictionary).get("until_ms", 0)):
			_clear_tell(String(caster))

## The windup color-pulse ON the caster sprite (live only): blend self_modulate toward the
## telegraph color at TELL_PULSE_HZ while the tell stands; restored exactly on clear.
func _pulse_casters() -> void:
	if _tells.is_empty():
		return
	var wave := 0.5 + 0.5 * sin(float(Time.get_ticks_msec()) / 1000.0 * TAU * TELL_PULSE_HZ)
	var color := _telegraph_color()
	for caster in _tells.keys():
		var spr := _body_sprite_of(String(caster))
		if spr == null:
			continue
		if not _pulsed.has(caster):
			_pulsed[caster] = {"sprite": spr, "base": spr.self_modulate}
		var base: Color = (_pulsed[caster] as Dictionary).get("base", Color.WHITE)
		spr.self_modulate = base.lerp(color, TELL_PULSE_DEPTH * wave)

func _restore_pulse(caster: String) -> void:
	if not _pulsed.has(caster):
		return
	var rec: Dictionary = _pulsed[caster]
	var spr: Variant = rec.get("sprite")
	if spr is CanvasItem and is_instance_valid(spr):
		(spr as CanvasItem).self_modulate = rec.get("base", Color.WHITE)
	_pulsed.erase(caster)

## The caster's rendered body sprite (group "npc" + npc_id — the same identity-free lookup the
## whiten uses), or null when no body is in the scene (out of room / headless).
func _body_sprite_of(id: String) -> CanvasItem:
	var body := _body_of(id)
	if body == null:
		return null
	for child in body.get_children():
		if child is Sprite2D or child is AnimatedSprite2D:
			return child
	return null

func _body_of(id: String) -> Node2D:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	for body in (ml as SceneTree).get_nodes_in_group("npc"):
		if body != null and String(body.get("npc_id")) == id and body is Node2D:
			return body
	return null

## The colorblind-aware wind-up color (the same Settings palette the HUD text uses).
func _telegraph_color() -> Color:
	var s := _al("Settings")
	if s != null and s.has_method("telegraph_color"):
		return s.telegraph_color()
	return Color(0.95, 0.35, 0.2)

## The ground-indicator layer (LIVE ONLY — never exists headless).
func _ensure_tell_layer() -> void:
	if _tell_layer != null and is_instance_valid(_tell_layer):
		return
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return
	var root := (ml as SceneTree).root
	var existing := root.get_node_or_null(TELL_LAYER_NAME)
	if existing is Node2D:
		_tell_layer = existing
		return
	var layer := TellLayer.new()
	layer.name = TELL_LAYER_NAME
	layer.fb = self
	root.add_child(layer)
	_tell_layer = layer

## Draws every active tell at its caster's BODY position (world canvas, like CombatFxLayer):
## a pulsing ground ARC along the swing for a strike, a pulsing danger RING + aim stub for
## everything else. Redraws each frame while tells stand; skips casters with no body on stage.
class TellLayer:
	extends Node2D
	var fb: Node = null

	func _process(_delta: float) -> void:
		queue_redraw()

	func _draw() -> void:
		if fb == null:
			return
		var tells: Dictionary = fb.active_tells()
		if tells.is_empty():
			return
		var wave: float = 0.5 + 0.5 * sin(float(Time.get_ticks_msec()) / 1000.0 * TAU * 5.0)
		var color: Color = fb._telegraph_color()
		var fill := Color(color.r, color.g, color.b, 0.14 + 0.14 * wave)
		var line := Color(color.r, color.g, color.b, 0.55 + 0.35 * wave)
		for caster in tells.keys():
			var body: Node2D = fb._body_of(String(caster))
			if body == null:
				continue
			var t: Dictionary = tells[caster]
			var at := to_local(body.global_position) + Vector2(0, 14)
			var dir: Vector2 = t.get("dir", Vector2.RIGHT)
			if String(t.get("kind", "")) == "arc":
				# The melee sweep footprint: ~120° fan along the cast dir, radius = the art's reach.
				var reach := clampf(float(t.get("range", 48.0)), 24.0, 160.0)
				var a0 := dir.angle() - PI / 3.0
				var a1 := dir.angle() + PI / 3.0
				var pts := PackedVector2Array([at])
				for i in 13:
					var ang := a0 + (a1 - a0) * float(i) / 12.0
					pts.append(at + Vector2.from_angle(ang) * reach)
				draw_colored_polygon(pts, fill)
				draw_arc(at, reach, a0, a1, 24, line, 2.0, true)
				draw_line(at, at + Vector2.from_angle(a0) * reach, line, 2.0, true)
				draw_line(at, at + Vector2.from_angle(a1) * reach, line, 2.0, true)
			else:
				# A ranged/spell wind-up: a danger ring at the caster's feet + a short aim stub.
				draw_circle(at, 20.0, fill)
				draw_arc(at, 20.0, 0.0, TAU, 32, line, 2.0, true)
				draw_line(at + dir * 22.0, at + dir * 46.0, line, 2.0, true)

## ---- The combat reticle ------------------------------------------------------------------------
## ACTIVE exactly while a live non-player combatant shares the player proxy's room — the state
## rule tests pin headless; the crosshair NODE is live-only.
func reticle_active() -> bool:
	var reg := _al("Agents")
	if reg == null:
		return false
	var proxy: Object = reg.get_agent("player") if reg.has_method("get_agent") else null
	if proxy == null:
		return false
	for a in reg.all():
		if String(a.id) == "player":
			continue
		if bool(a.in_combat) and not bool(a.downed) and String(a.room) == String(proxy.room):
			return true
	return false

## The reticle layer (LIVE ONLY — never exists headless). A screen-space crosshair that rides
## the mouse and shows itself only while reticle_active().
func _ensure_reticle() -> void:
	if _reticle != null and is_instance_valid(_reticle):
		return
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return
	var root := (ml as SceneTree).root
	var existing := root.get_node_or_null(RETICLE_LAYER_NAME)
	if existing is CanvasLayer:
		_reticle = existing
		return
	var layer := CanvasLayer.new()
	layer.name = RETICLE_LAYER_NAME
	layer.layer = 60
	var cross := ReticleCross.new()
	cross.name = "Cross"
	cross.fb = self
	layer.add_child(cross)
	root.add_child(layer)
	_reticle = layer

## The subtle crosshair: a thin bone-white ring + four ticks + a center dot at the OS cursor.
class ReticleCross:
	extends Node2D
	var fb: Node = null

	func _process(_delta: float) -> void:
		var on: bool = fb != null and bool(fb.call("reticle_active"))
		visible = on
		if on:
			position = get_viewport().get_mouse_position()
			queue_redraw()

	func _draw() -> void:
		var c := Color(0.93, 0.89, 0.78, 0.85)
		draw_arc(Vector2.ZERO, 7.0, 0.0, TAU, 24, c, 1.2, true)
		for dirv in [Vector2.RIGHT, Vector2.LEFT, Vector2.UP, Vector2.DOWN]:
			draw_line((dirv as Vector2) * 4.0, (dirv as Vector2) * 10.0, c, 1.2, true)
		draw_circle(Vector2.ZERO, 1.1, c)

# --- Gates (read the Settings authority) ------------------------------------------------------
func _shake_enabled() -> bool:
	var s := _al("Settings")
	return s == null or bool(s.get_bool("screen_shake"))

func _flash_enabled() -> bool:
	var s := _al("Settings")
	return s == null or bool(s.get_bool("hit_flash"))

func _hitstop_enabled() -> bool:
	var s := _al("Settings")
	return s == null or bool(s.get_bool("hit_stop"))

## True only when a real display is attached (live play). False under --headless — where we must
## NEVER write Engine.time_scale, keeping every deterministic harness byte-identical.
func _is_live() -> bool:
	return DisplayServer.get_name() != "headless"

# --- Scene lookups (read-only) ----------------------------------------------------------------
func _active_camera() -> Camera2D:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	var vp := (ml as SceneTree).root.get_viewport()
	return vp.get_camera_2d() if vp != null else null

func _flash_overlay() -> ColorRect:
	if _flash_rect != null and is_instance_valid(_flash_rect):
		return _flash_rect
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	var root := (ml as SceneTree).root
	var existing := root.get_node_or_null(FLASH_LAYER_NAME)
	var layer: CanvasLayer
	if existing is CanvasLayer:
		layer = existing
	else:
		layer = CanvasLayer.new()
		layer.name = FLASH_LAYER_NAME
		layer.layer = 5
		root.add_child(layer)
	var rect := ColorRect.new()
	rect.color = Color(0.9, 0.05, 0.05, 0.0)
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(rect)
	_flash_rect = rect
	return _flash_rect

func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
