extends CanvasLayer
## Cathedral establishing-shot cinematic (chapel-only; lives in CathedralNave.tscn). The
## cinematic image lights up from black over LIGHT_UP_SECS, stays fully lit for HOLD_SECS, then
## dissolves to reveal the playable nave -- and only then does the player get control
## ("transition into scene"). It sits ABOVE SceneFade (layer 128) so the cinematic owns the
## screen during the entry instead of fighting the generic between-scene fade.

const LIGHT_UP_SECS: float = 2.0   # cinematic lights up from black
const HOLD_SECS: float = 1.5       # stays fully lit
const REVEAL_SECS: float = 0.5     # dissolves to the nave

var _player: Node

func _ready() -> void:
	layer = 200
	var tr: TextureRect = $TextureRect
	# Black backdrop behind the cinematic so it lights up FROM black, not over the live nave.
	var backdrop := ColorRect.new()
	backdrop.color = Color.BLACK
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(backdrop)
	move_child(backdrop, 0)  # draw it behind the TextureRect
	tr.modulate.a = 0.0      # cinematic starts black (invisible)
	# Freeze the player so it can't wander blindly during the cinematic; released on finish.
	_player = get_parent().get_node_or_null("Player")
	if _player:
		_player.process_mode = Node.PROCESS_MODE_DISABLED
	var t := create_tween()
	t.tween_property(tr, "modulate:a", 1.0, LIGHT_UP_SECS)                 # 1) light up over 2s
	t.tween_interval(HOLD_SECS)                                            # 2) stay fully lit 2s
	t.tween_property(tr, "modulate:a", 0.0, REVEAL_SECS)                   # 3) dissolve cinematic...
	t.parallel().tween_property(backdrop, "modulate:a", 0.0, REVEAL_SECS)  # ...and the black -> nave
	t.tween_callback(_finish)

func _finish() -> void:
	if is_instance_valid(_player):
		_player.process_mode = Node.PROCESS_MODE_INHERIT  # 4) hand control to the player
	queue_free()

# --- test seam: the cinematic's TextureRect alpha (0=black, 1=fully lit) ---
func cinematic_alpha() -> float:
	return $TextureRect.modulate.a
