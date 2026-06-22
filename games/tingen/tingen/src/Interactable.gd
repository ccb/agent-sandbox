extends Area2D
## A world object the player can examine, a person they can talk to, or a door that
## loads another scene.
##
## Shows a floating prompt while the player is nearby. On `interact`:
##   - if `dialogue_id` is set  -> opens that dialogue tree
##   - else if `target_scene`   -> requests a scene transition
##   - else                     -> surfaces an internal-thought line
## In the examine case, if `clue_id` is set the clue is collected (once).

@export_multiline var thought: String = ""
@export var prompt_text: String = "Examine"
@export var tint: Color = Color.WHITE
## Optional real art; when set it replaces the placeholder tint-square and is feet-anchored.
@export var icon: Texture2D
## Target on-screen height in pixels for the icon art.
@export var icon_px: float = 56.0
@export_file("*.tscn") var target_scene: String = ""
@export var lead_on_use: String = ""
## When true, interacting strips one gathered ingredient from the cult's rite cache instead of
## examining/talking/transitioning — the warehouse "spoil the cache" point the player walks up to.
@export var sabotage_cache: bool = false
## Clue collected on first examine (must match an id in data/clues.json).
@export var clue_id: String = ""
## NPC dialogue tree to open (must match a key in data/dialogue.json).
@export var dialogue_id: String = ""
## When set, LEFT-CLICKING this object opens the matching Agent's inspect card
## (WorldState.inspect_requested -> CharacterCard) — surfaces the agent's goal + live thought.
@export var agent_id: String = ""
## When true, interacting (E) toggles the host room's RoomState (normal <-> 失控), via the
## node in group "room_state". Used by the in-room ritual trigger in Old Neil's home.
@export var room_state_toggle: bool = false

@onready var _prompt: Label = $Prompt
@onready var _sprite: Sprite2D = $Sprite2D

var _player_near: bool = false

func _ready() -> void:
	if icon:
		_sprite.texture = icon
		_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		_sprite.modulate = Color.WHITE
		var h := float(icon.get_height())
		var s: float = icon_px / h if h > 0.0 else 1.0
		_sprite.scale = Vector2(s, s)
		_sprite.offset = Vector2(0, -h * 0.5)   # feet-anchor for Y-sort
	else:
		_sprite.modulate = tint
	_prompt.text = prompt_text
	_prompt.visible = false
	body_entered.connect(_on_body_entered)
	body_exited.connect(_on_body_exited)
	if agent_id != "":
		input_pickable = true
		input_event.connect(_on_input_event)

func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player"):
		_player_near = true
		_prompt.visible = true

func _on_body_exited(body: Node) -> void:
	if body.is_in_group("player"):
		_player_near = false
		_prompt.visible = false

## Left-click while `agent_id` is set: open that agent's inspect card (its goal + thought).
func _on_input_event(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		WorldState.inspect_requested.emit(agent_id)

func _unhandled_input(event: InputEvent) -> void:
	if not _player_near:
		return
	if event.is_action_pressed("interact"):
		_use()
		get_viewport().set_input_as_handled()

func _use() -> void:
	if room_state_toggle:
		var rs: Node = get_tree().get_first_node_in_group("room_state")
		if rs and rs.has_method("toggle"):
			rs.toggle()
		return
	if sabotage_cache:
		_sabotage_rite_cache()
		return
	if dialogue_id != "":
		DialogueManager.start(dialogue_id)
		return
	if target_scene != "":
		SceneFade.go(target_scene, lead_on_use)
		return
	if clue_id != "":
		ClueDB.collect(clue_id)
	if thought != "":
		WorldState.thought_requested.emit(thought)
	if lead_on_use != "":
		WorldState.set_lead(lead_on_use)

## Strip one gathered ingredient from the cult's rite cache (PlayerActions.sabotage_any) and
## narrate the result, so the player feels the rite set back. When the cache is already bare the
## prompt still works but reports there is nothing left to spoil.
func _sabotage_rite_cache() -> void:
	var stripped := PlayerActions.sabotage_any()
	if stripped != "":
		WorldState.thought_requested.emit(
			"I scattered their %s. The rite will have to gather it again." % stripped.replace("_", " "))
	else:
		WorldState.thought_requested.emit("Nothing left here worth spoiling — the cache is bare.")
