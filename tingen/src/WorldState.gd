extends Node
## Global game state (autoload singleton `WorldState`).
##
## Holds the five canonical citywide "pressure" variables (GDD §8.3) plus the
## current time phase and active lead, and acts as a lightweight signal bus so any
## scene can surface an internal-thought line, change the active lead, or request a
## scene transition without holding direct references to the HUD or controller.
##
## Pressure variables are the single source of truth; WorldManager mutates them via
## `adjust()` so the HUD, save system and dev console all stay in sync.

signal state_changed
signal lead_changed(text: String)
signal thought_requested(text: String)
signal transition_requested(scene_path: String, lead: String)
signal inspect_requested(agent_id: String)

## Canonical §8.3 pressures (0..100). `stability` is NOT here — it is derived.
const PRESSURE_VARS: Array[StringName] = [
	&"corruption", &"panic", &"fatigue", &"cult_readiness", &"attention",
]

# Starting values reflect the opening: the city is mostly calm, corruption has only
# just begun to seep in, the investigator is freshly awake.
var corruption: float = 5.0
var panic: float = 5.0
var fatigue: float = 10.0
var cult_readiness: float = 0.0
var attention: float = 0.0

var time_phase: String = "Morning"
var current_lead: String = "A cult races to summon the descending god. Find their warehouse on Iron Cross Street and stop the rite."

## Derived, player-facing summary meter. Not stored, not saved.
func stability() -> float:
	return clampf(100.0 - (corruption * 0.5 + panic * 0.3 + cult_readiness * 0.2), 0.0, 100.0)

func get_pressure(var_name: StringName) -> float:
	if var_name in PRESSURE_VARS:
		return float(get(var_name))
	return 0.0

func set_lead(text: String) -> void:
	current_lead = text
	lead_changed.emit(text)

## Route a scene transition so doors/stairs work from anywhere. When a GameController is
## mounted (the game is running from Main) emit transition_requested, so it swaps only the
## World subtree and the persistent HUD survives. Otherwise (a single scene run on its own,
## e.g. F6 in the editor) fall back to a full scene change so the transition still happens.
func request_transition(scene_path: String, lead: String = "") -> void:
	if scene_path == "":
		return
	if get_tree().get_first_node_in_group("game_controller") != null:
		transition_requested.emit(scene_path, lead)
	else:
		get_tree().change_scene_to_file(scene_path)

## Nudge a pressure variable and notify listeners. Clamped to 0..100.
func adjust(var_name: StringName, delta: float) -> void:
	if not (var_name in PRESSURE_VARS):
		push_warning("WorldState.adjust: unknown pressure variable %s" % var_name)
		return
	set(var_name, clampf(float(get(var_name)) + delta, 0.0, 100.0))
	state_changed.emit()

## Directly set a pressure (used by save/load and the dev console).
func set_pressure(var_name: StringName, value: float) -> void:
	if not (var_name in PRESSURE_VARS):
		push_warning("WorldState.set_pressure: unknown pressure variable %s" % var_name)
		return
	set(var_name, clampf(value, 0.0, 100.0))
	state_changed.emit()

func to_dict() -> Dictionary:
	var d: Dictionary = {"lead": current_lead}
	for v in PRESSURE_VARS:
		d[String(v)] = float(get(v))
	return d

func from_dict(d: Dictionary) -> void:
	for v in PRESSURE_VARS:
		if d.has(String(v)):
			set(v, clampf(float(d[String(v)]), 0.0, 100.0))
	if d.has("lead"):
		set_lead(String(d["lead"]))
	state_changed.emit()
