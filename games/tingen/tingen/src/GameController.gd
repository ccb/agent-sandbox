extends Node2D
## Root controller. Owns the swappable `World` subtree and the persistent UI layer,
## performs scene transitions requested via WorldState, and tracks the current scene +
## player position so SaveManager can serialize and restore them.

@onready var _world: Node2D = get_node_or_null("World")

var current_scene_path: String = ""

func _ready() -> void:
	add_to_group("game_controller")
	WorldState.transition_requested.connect(_on_transition_requested)
	# Record the scene that was instanced directly in Main.tscn.
	var first := _world.get_child(0) if _world and _world.get_child_count() > 0 else null
	if first and first.scene_file_path != "":
		current_scene_path = first.scene_file_path

func _process(_delta: float) -> void:
	# Keep AgentRuntime pointed at the real player every frame. player_position has no
	# other live writer, so without this the District map's player dot (and, once the
	# agent brain is un-deferred, the near-player active set) would sit at a fixed default.
	sync_player_position()

## Push the live player position into the AgentRuntime autoload. Public and side-effect-only
## so a headless test can drive it without instancing the whole Main scene.
func sync_player_position() -> void:
	var p := get_player()
	if p:
		AgentRuntime.player_position = p.global_position

func _on_transition_requested(scene_path: String, lead: String) -> void:
	if _swap_world(scene_path):
		if lead != "":
			WorldState.set_lead(lead)

## Swap the active world scene. Returns true on success.
func _swap_world(scene_path: String) -> bool:
	var packed: PackedScene = load(scene_path)
	if packed == null:
		push_error("GameController: could not load scene %s" % scene_path)
		return false
	for child in _world.get_children():
		child.queue_free()
	_world.add_child(packed.instantiate())
	current_scene_path = scene_path
	return true

func get_player() -> Node2D:
	var players := get_tree().get_nodes_in_group("player")
	return players[0] if players.size() > 0 else null

func player_position() -> Vector2:
	var p := get_player()
	return p.global_position if p else Vector2.ZERO

## Load a scene and drop the player at `pos` (used by SaveManager). Deferred so the
## newly instanced player exists before we move it.
func load_world_at(scene_path: String, pos: Vector2) -> void:
	if not _swap_world(scene_path):
		return
	await get_tree().process_frame
	var p := get_player()
	if p:
		p.global_position = pos
