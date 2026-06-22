extends Node
## DEV CONVENIENCE (autoload `StandaloneBoot`).
##
## When you run a gameplay world scene on its own — Godot's "Run Current Scene" (F6) on
## City.tscn, IntroRoom.tscn, an interior, etc. — there is no Main.tscn around it, so none of
## the HUD panels or controls exist (the HUD + GameController live in Main). This stands in for
## Main in that case: it instances the persistent HUD, feeds the live player position to
## AgentRuntime so the District-map dot tracks, and turns door transitions into whole-scene
## swaps so you can walk between scenes. The HUD is parented to this autoload, so it survives
## those swaps exactly as Main's HUD survives a World swap.
##
## It is a deliberate no-op when it is not needed:
##   * the real game (F5) — Main already provides a GameController (group "game_controller"),
##   * headless test / -s runs — there is no current_scene,
##   * non-gameplay scenes — those with no Player in group "player".

var _hud_layer: CanvasLayer

func _ready() -> void:
	# Autoloads are ready before the main scene is in the tree; wait a couple of frames so
	# current_scene and its player exist, then decide once.
	await get_tree().process_frame
	await get_tree().process_frame
	_maybe_bootstrap()

func _maybe_bootstrap() -> void:
	var tree := get_tree()
	if tree.current_scene == null:
		return  # the -s test runner (and any no-scene boot): never bootstrap
	if not tree.get_nodes_in_group("game_controller").is_empty():
		return  # the real game: Main already supplies the HUD + controller
	if tree.get_nodes_in_group("player").is_empty():
		return  # not a gameplay world scene (menu, etc.)
	_install()

func _install() -> void:
	print("[StandaloneBoot] No Main/HUD detected — instancing the dev HUD for scene '%s'."
		% get_tree().current_scene.name)
	_hud_layer = CanvasLayer.new()
	_hud_layer.add_child(load("res://ui/HUD.tscn").instantiate())
	add_child(_hud_layer)  # parented to this autoload, so it survives change_scene_to_file
	WorldState.transition_requested.connect(_on_transition)

## Standalone doors swap the whole scene (the HUD persists here, on the autoload).
func _on_transition(scene_path: String, _lead: String) -> void:
	get_tree().change_scene_to_file(scene_path)

func _process(_delta: float) -> void:
	# Stand in for GameController: keep AgentRuntime pointed at the live player so the map dot
	# tracks. Inert until the dev HUD is actually installed (so the real game is unaffected).
	if _hud_layer == null:
		return
	var players := get_tree().get_nodes_in_group("player")
	if not players.is_empty():
		AgentRuntime.player_position = players[0].global_position
