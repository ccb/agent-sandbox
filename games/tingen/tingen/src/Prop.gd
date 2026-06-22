extends StaticBody2D
## Reusable set-dressing prop: a feet-anchored sprite with an optional solid footprint.
## Placed as a direct child of a Y-sorted parent so the player occludes correctly by depth.

@export var icon: Texture2D
@export var icon_px: float = 96.0                 # target on-screen height in px
@export var solid: bool = true                    # blocks movement?
@export var footprint: Vector2 = Vector2(48, 18)  # collider size at the feet

@onready var _sprite: Sprite2D = $Sprite2D
@onready var _shape: CollisionShape2D = $CollisionShape2D

func _ready() -> void:
	if icon:
		_sprite.texture = icon
		_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		var h := float(icon.get_height())
		var s: float = icon_px / h if h > 0.0 else 1.0
		_sprite.scale = Vector2(s, s)
		_sprite.offset = Vector2(0, -h * 0.5)       # feet at node origin
	var rect := RectangleShape2D.new()
	rect.size = footprint
	_shape.shape = rect
	_shape.disabled = not solid
	set_collision_layer_value(1, solid)
