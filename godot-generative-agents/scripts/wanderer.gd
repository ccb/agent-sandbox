extends Sprite2D
## Makes a Cute Fantasy sprite wander the screen on its own — no player input.
##
## A sprite sheet is just a grid of little pictures (frames). We tell the
## Sprite2D how many frames go across (hframes) and down (vframes), then play
## an animation by stepping the `frame` property along one row over time.
##
## Meanwhile the node glides toward a random point; when it arrives, it picks a
## new one. That random target is the only "brain" here — later, an LLM-driven
## agent could choose the destination instead, and the rest still works.

## Sprite-sheet grid: how many frames across (columns) and down (rows).
@export var sheet_hframes: int = 6
@export var sheet_vframes: int = 10

## Which row of the sheet holds the walk cycle, and how many frames long it is.
@export var walk_row: int = 0
@export var walk_len: int = 6

## Animation speed, in frames per second.
@export var anim_fps: float = 8.0

## Movement speed, in pixels per second.
@export var move_speed: float = 60.0

## How close (in pixels) counts as "arrived" before picking a new target.
@export var arrive_dist: float = 8.0

# How far from the window edge the sprite is allowed to roam.
const EDGE_MARGIN := 48.0

var _target: Vector2        # the point we are currently walking toward
var _anim_time: float = 0.0 # accumulates time to advance the walk animation
var _bounds: Rect2          # the rectangle we are allowed to wander inside


func _ready() -> void:
	# Slice the texture into its grid of frames and start on the first one.
	hframes = sheet_hframes
	vframes = sheet_vframes
	frame = walk_row * sheet_hframes

	# Keep a margin inside the visible window so nobody walks off-screen.
	var view: Vector2 = get_viewport_rect().size
	_bounds = Rect2(
		EDGE_MARGIN,
		EDGE_MARGIN,
		view.x - 2.0 * EDGE_MARGIN,
		view.y - 2.0 * EDGE_MARGIN)

	_target = _pick_target()
	print("%s spawned at %s" % [name, position])


func _process(delta: float) -> void:
	# Step toward the target; re-roll a new one once we reach it.
	var to_target: Vector2 = _target - position
	if to_target.length() <= arrive_dist:
		_target = _pick_target()
		to_target = _target - position

	var step: Vector2 = to_target.normalized() * move_speed * delta
	position += step

	# Face the way we're heading (sheets are drawn facing right by default).
	if absf(step.x) > 0.01:
		flip_h = step.x < 0.0

	# Advance the walk animation by stepping along the chosen row.
	_anim_time += delta
	var frame_in_row: int = int(_anim_time * anim_fps) % walk_len
	frame = walk_row * sheet_hframes + frame_in_row


func _pick_target() -> Vector2:
	return Vector2(
		randf_range(_bounds.position.x, _bounds.end.x),
		randf_range(_bounds.position.y, _bounds.end.y))
