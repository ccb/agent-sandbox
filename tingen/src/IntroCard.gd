extends CanvasLayer
func _ready() -> void:
	var tr := $TextureRect
	var t := create_tween()
	t.tween_interval(1.2)
	t.tween_property(tr, "modulate:a", 0.0, 1.0)
	t.tween_callback(queue_free)
