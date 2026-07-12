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

# --- Event ear (player-involved combat + the signature beats) ---------------------------------
func _on_event(ev: Dictionary) -> void:
	var d: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	match String(ev.get("type", "")):
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
