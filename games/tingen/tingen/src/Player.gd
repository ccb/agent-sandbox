extends CharacterBody2D
## Top-down protagonist. 8-direction movement; the child Camera2D follows
## automatically. Movement is frozen while a dialogue is open. The sprite swaps
## among four directional textures (down/left/right/up) to face the way it moves.
## Double-tapping "up" (W) engages a sprint (faster movement) that drains a stamina
## pool; stamina regenerates while not sprinting, and once drained to empty must
## recover past sprint_recharge_threshold before sprint can re-engage.

@export var speed: float = 120.0
@export var sprint_multiplier: float = 1.8
## Stamina pool (0..max_stamina). Sprinting drains it; it regenerates otherwise.
@export var max_stamina: float = 100.0
@export var stamina_drain: float = 30.0          # per second while sprinting
@export var stamina_regen: float = 45.0          # per second while not sprinting
## After draining to empty, stamina must recover to this before sprint re-engages.
@export var sprint_recharge_threshold: float = 20.0
## Max seconds between two "up" taps to engage a sprint.
@export var double_tap_window: float = 0.28

var stamina: float = max_stamina

const _TEX := {
	"down": preload("res://assets/characters/klein_down.png"),
	"left": preload("res://assets/characters/klein_left.png"),
	"right": preload("res://assets/characters/klein_right.png"),
	"up": preload("res://assets/characters/klein_up.png"),
}

@onready var _sprite: Sprite2D = $Sprite2D
var _facing: String = "down"
var _last_up_tap: float = -1000.0
var _sprinting: bool = false
var _exhausted: bool = false
## Floating stamina bar drawn beside Klein: fades in when a sprint begins, shows the pool
## draining white -> red, and fades out once stamina is full again.
const _BAR_SIZE := Vector2(5.0, 26.0)
const _BAR_CENTER := Vector2(16.0, -34.0)
const _BAR_FADE := 6.0          # alpha units per second
var _bar_alpha: float = 0.0

func _ready() -> void:
	stamina = max_stamina
	_sprite.texture = _TEX[_facing]

func _physics_process(delta: float) -> void:
	if DialogueManager.active:
		velocity = Vector2.ZERO
		step_stamina(delta, false)  # recover while a conversation holds you still
		_update_stamina_bar(delta, false)
		return
	# Double-tap "up" (W) within the window engages sprint, unless exhausted.
	if Input.is_action_just_pressed("move_up"):
		var now := Time.get_ticks_msec() / 1000.0
		if now - _last_up_tap <= double_tap_window and not _exhausted:
			_sprinting = true
		_last_up_tap = now
	var direction := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	var sprinting := _resolve_sprint(direction)
	step_stamina(delta, sprinting)
	_update_stamina_bar(delta, sprinting)
	velocity = direction * (speed * sprint_multiplier if sprinting else speed)
	move_and_slide()
	_face(direction)

## Sprint holds only while armed, actually moving, and not exhausted. Hitting empty sets
## the exhausted latch (cleared once stamina recovers past sprint_recharge_threshold), so a
## drained player cannot stutter-sprint. Returns whether this frame is a sprint.
func _resolve_sprint(direction: Vector2) -> bool:
	if stamina <= 0.0:
		_exhausted = true
	elif stamina >= sprint_recharge_threshold:
		_exhausted = false
	if _sprinting and (direction == Vector2.ZERO or _exhausted):
		_sprinting = false
	return _sprinting

## Advance stamina one frame: drain while sprinting, regenerate otherwise; clamp to
## [0, max_stamina]. Pure (no Input/tree) so it is unit-testable headless.
func step_stamina(delta: float, sprinting: bool) -> void:
	if sprinting:
		stamina = maxf(0.0, stamina - stamina_drain * delta)
	else:
		stamina = minf(max_stamina, stamina + stamina_regen * delta)

## Fade the floating bar toward shown (alpha 1) while sprinting or recovering, and toward
## hidden (alpha 0) once the pool is full again, then request a redraw.
func _update_stamina_bar(delta: float, sprinting: bool) -> void:
	var want_shown: bool = sprinting or stamina < max_stamina
	_bar_alpha = move_toward(_bar_alpha, 1.0 if want_shown else 0.0, _BAR_FADE * delta)
	queue_redraw()

## Draw the small vertical stamina bar beside Klein: a dark track with a bottom-anchored
## fill that lerps white (full) -> red (empty); the whole thing is modulated by _bar_alpha.
func _draw() -> void:
	if _bar_alpha <= 0.001:
		return
	var ratio: float = clampf(stamina / max_stamina, 0.0, 1.0)
	var tl: Vector2 = _BAR_CENTER - _BAR_SIZE * 0.5
	draw_rect(Rect2(tl - Vector2.ONE, _BAR_SIZE + Vector2(2, 2)), Color(0.05, 0.05, 0.07, 0.7 * _bar_alpha))
	var fill_h: float = _BAR_SIZE.y * ratio
	var fill_col: Color = Color(1, 1, 1).lerp(Color(0.9, 0.15, 0.15), 1.0 - ratio)
	fill_col.a = _bar_alpha
	draw_rect(Rect2(tl.x, tl.y + (_BAR_SIZE.y - fill_h), _BAR_SIZE.x, fill_h), fill_col)

## Pick the directional texture from the dominant movement axis; keep the last
## facing while idle so the player stays oriented where they stopped.
func _face(direction: Vector2) -> void:
	if direction == Vector2.ZERO:
		return
	var f := _facing
	if absf(direction.x) > absf(direction.y):
		f = "right" if direction.x > 0.0 else "left"
	else:
		f = "down" if direction.y > 0.0 else "up"
	if f != _facing:
		_facing = f
		_sprite.texture = _TEX[f]
