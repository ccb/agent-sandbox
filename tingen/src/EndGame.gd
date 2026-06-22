extends CanvasLayer
## End-game shell (autoload `EndGame`). Listens for the one moment the doomsday clock runs out
## (`SummoningPlan.summoning_climax`), asks `EndGameResolver` which of the three endings the run
## reached, freezes the world, and raises a win/lose screen with Restart / Quit. It is a thin
## UI + pause shell: all the branching lives in the pure resolver, so this stays trivial to read.
##
## process_mode = ALWAYS (like DevConsole) so the overlay's buttons still respond once the tree
## is paused. Restart resets the handful of stateful singletons and reloads the world scene.

signal ending_reached(outcome: String, result: Dictionary)

var _overlay: Control = null
var _last_result: Dictionary = {}

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	# Idempotent connect guard: keep the headless suite (which can fire the climax many times)
	# and any re-add from a world swap from double-connecting.
	if not SummoningPlan.summoning_climax.is_connected(_on_climax):
		SummoningPlan.summoning_climax.connect(_on_climax)

## The single climax handler. Resolve the ending, announce it, log it, freeze the world, show it.
func _on_climax(strength: float) -> void:
	_last_result = EndGameResolver.resolve(strength)
	ending_reached.emit(String(_last_result["outcome"]), _last_result)
	EventBus.emit_event("endgame", _last_result)
	get_tree().paused = true
	_show_overlay(_last_result)

## Reset the stateful singletons so a restart begins a clean run. Autoloads persist across a
## scene reload, so they must be reset explicitly (the reload alone won't clear them).
func _reset_world_state() -> void:
	SummoningPlan.reset()
	Overseer.reset()
	OccultToolManager.rebuild()
	Agents.rebuild()
	Clock.set_time(1, 480)
	EventBus.clear()

## Restart: drop the overlay, lift the freeze, reset state, reload the world. The reload is
## guarded so restart() is safe to call from the headless harness (which has no current scene).
func restart() -> void:
	_hide_overlay()
	get_tree().paused = false
	_reset_world_state()
	if get_tree().current_scene != null:
		get_tree().reload_current_scene()

# --- Overlay ----------------------------------------------------------------------------------
func _hide_overlay() -> void:
	if is_instance_valid(_overlay):
		_overlay.queue_free()
	_overlay = null

func _show_overlay(result: Dictionary) -> void:
	_hide_overlay()
	var copy: Dictionary = _ending_copy(result)

	var overlay := Control.new()
	overlay.name = "EndOverlay"
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.02, 0.04, 0.9)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(dim)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(center)

	var box := VBoxContainer.new()
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.add_theme_constant_override("separation", 18)
	center.add_child(box)

	var title := Label.new()
	title.text = String(copy["title"])
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 48)
	box.add_child(title)

	var body := Label.new()
	body.text = String(copy["body"])
	body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.custom_minimum_size = Vector2(760, 0)
	box.add_child(body)

	var buttons := HBoxContainer.new()
	buttons.alignment = BoxContainer.ALIGNMENT_CENTER
	buttons.add_theme_constant_override("separation", 24)
	box.add_child(buttons)

	var restart_btn := Button.new()
	restart_btn.text = "Restart"
	restart_btn.custom_minimum_size = Vector2(160, 44)
	restart_btn.pressed.connect(restart)
	buttons.add_child(restart_btn)

	var quit_btn := Button.new()
	quit_btn.text = "Quit"
	quit_btn.custom_minimum_size = Vector2(160, 44)
	quit_btn.pressed.connect(func() -> void: get_tree().quit())
	buttons.add_child(quit_btn)

	add_child(overlay)
	_overlay = overlay

## Per-ending title + body. Keeps the canon beats: a completed descent (降临) is total; a stopped
## descent either kills the player (near-good) or lets them walk away (all-good).
func _ending_copy(result: Dictionary) -> Dictionary:
	match String(result.get("outcome", "")):
		"city_dies":
			return {
				"title": "Tingen Falls",
				"body": "The descent (降临) completes. A light that is not light blooms over the Iron Cross warehouse, and the city is unmade. No one was left to stop it.",
			}
		"near_good":
			return {
				"title": "The Line Holds",
				"body": "You break the summoning — but the backlash takes you with it. Tingen wakes to a grey dawn; you do not see it.\n(%d rounds fought)" % int(result.get("rounds", 0)),
			}
		"all_good":
			return {
				"title": "Dawn Over Tingen",
				"body": "The rite shatters and the descending god (外神) is denied. You walk out of the warehouse alive, into a city that will never know how close it came.\n(%d HP remaining)" % int(result.get("player_hp_left", 0)),
			}
		_:
			return {"title": "The End", "body": ""}
