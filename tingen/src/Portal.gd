extends Area2D
## Walk-into portal: when the Player enters this area, request a transition to
## `target_scene`. Routes through WorldState.transition_requested so GameController
## swaps only the `World` subtree and Main's persistent HUD survives the change.
## Reusable for building doors and stairs on the walkable maps (City <-> interiors).

@export_file("*.tscn") var target_scene: String = ""
## Optional lead/objective text surfaced on the HUD when this portal is used.
@export var lead_on_use: String = ""
var _used := false

func _ready() -> void:
	body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node) -> void:
	if _used or target_scene == "":
		return
	if body.is_in_group("player"):
		_used = true
		call_deferred("_change")

func _change() -> void:
	SceneFade.go(target_scene, lead_on_use)
