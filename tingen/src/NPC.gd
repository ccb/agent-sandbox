extends CharacterBody2D
## Stub NPC agent (GDD §15 / §22.3). Reads its definition + phase schedule from NpcDB,
## re-targets its waypoint on Clock.phase_changed, and paths toward it along the city
## navmesh via a NavigationAgent2D, falling back to straight-line steering when no path
## exists (an NPC spawned outside the live district, or before the nav map has synced).
## The schedule/binding logic is the art-agnostic part.
##
## If its definition has a dialogue_id, the player can talk to it (E when near).

@export var npc_id: String = ""
@export var move_speed: float = 60.0
@export var arrive_radius: float = 8.0

@onready var _sprite: Sprite2D = $Sprite2D
@onready var _name_label: Label = $Name
@onready var _prompt: Label = $TalkArea/Prompt
@onready var _nav: NavigationAgent2D = $NavigationAgent2D

var _def: Dictionary = {}
var _target: Vector2
var _player_near: bool = false
var _agent = null   # bound Agent (from the registry) or null = schedule fallback

func _ready() -> void:
	_def = NpcDB.get_def(npc_id)
	if _def.is_empty():
		push_warning("NPC: no def for '%s'" % npc_id)
	var tint: Array = _def.get("tint", [1, 1, 1])
	if tint.size() >= 3:
		_sprite.modulate = Color(tint[0], tint[1], tint[2])
	_name_label.text = String(_def.get("name", npc_id))
	_prompt.visible = false
	_prompt.text = "Talk"
	_target = global_position
	if Clock.phase != "":
		_retarget(Clock.phase)
	Clock.phase_changed.connect(func(p, _d): _retarget(p))
	var area: Area2D = $TalkArea
	area.body_entered.connect(_on_body_entered)
	area.body_exited.connect(_on_body_exited)
	area.input_pickable = true
	area.input_event.connect(_on_talk_area_input)
	_agent = Agents.get_agent(npc_id)

## True when this node is the rendered body of a live registry Agent.
func is_bound() -> bool:
	return _agent != null

## Where the node should walk this frame: its Agent's beat-driven position when bound,
## otherwise its scheduled waypoint.
func steer_goal() -> Vector2:
	return _agent.position if _agent != null else _target

func _on_talk_area_input(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		if Agents.get_agent(npc_id) != null:
			WorldState.inspect_requested.emit(npc_id)

func _retarget(phase: String) -> void:
	var wp := NpcDB.waypoint_for(npc_id, phase)
	if wp != Vector2.ZERO:
		_target = wp

func _physics_process(_delta: float) -> void:
	if DialogueManager.active:
		velocity = Vector2.ZERO
		return
	var goal := steer_goal()
	if global_position.distance_to(goal) <= arrive_radius:
		velocity = Vector2.ZERO
		return
	# Path around the city's buildings/water on the baked navmesh. Fall back to straight-line
	# steering when there is no usable path — an NPC instantiated outside the live district (e.g.
	# the bind unit-test), or before the nav map has synced — so isolated behavior still holds.
	_nav.target_position = goal
	var steer_point := goal
	if not _nav.is_navigation_finished() and _nav.is_target_reachable():
		steer_point = _nav.get_next_path_position()
	velocity = (steer_point - global_position).normalized() * move_speed
	move_and_slide()

func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player") and _can_talk():
		_player_near = true
		_prompt.visible = true

func _on_body_exited(body: Node) -> void:
	if body.is_in_group("player"):
		_player_near = false
		_prompt.visible = false

func _can_talk() -> bool:
	return String(_def.get("dialogue_id", "")) != ""

func _unhandled_input(event: InputEvent) -> void:
	if not _player_near or not _can_talk():
		return
	if event.is_action_pressed("interact"):
		DialogueManager.start(String(_def["dialogue_id"]))
		get_viewport().set_input_as_handled()
