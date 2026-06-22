extends Node
## Drives a room between its 'normal' and 'lost_control' (失控) states. For Old Neil's home:
## swaps the room background and HIDES Old Neil (whose monster form is painted into the 失控
## background art), so the room visibly transforms in place.
##
## Two ways to flip it:
##   - the in-room RitualTrigger (an Interactable with room_state_toggle) calls toggle()
##   - it auto-flips to lost_control once WorldState.corruption crosses `corruption_threshold`
## Registered in group "room_state" so the trigger can find it without a hard reference.

@export var room_photo_path: NodePath
@export var old_neil_path: NodePath
@export var normal_texture: Texture2D
@export var lost_texture: Texture2D
## Sim hook: corruption at/above this flips the room to 失控 (dev console can drive corruption).
@export var corruption_threshold: float = 60.0

var state: String = "normal"

func _ready() -> void:
	add_to_group("room_state")
	WorldState.state_changed.connect(_on_state_changed)
	_apply()

func _on_state_changed() -> void:
	if state == "normal" and WorldState.corruption >= corruption_threshold:
		set_state("lost_control")

func toggle() -> void:
	set_state("normal" if state == "lost_control" else "lost_control")

func set_state(s: String) -> void:
	state = s
	_apply()

func _apply() -> void:
	var photo := get_node_or_null(room_photo_path) as Sprite2D
	if photo != null:
		var tex := lost_texture if state == "lost_control" else normal_texture
		if tex != null:
			photo.texture = tex
	var neil := get_node_or_null(old_neil_path)
	if neil != null and "visible" in neil:
		neil.visible = state != "lost_control"
