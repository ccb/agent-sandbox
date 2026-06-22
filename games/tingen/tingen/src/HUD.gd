extends Control
## Main exploration HUD (GDD §19.2): time phase + active lead along the top,
## stability/corruption/panic meters at the right, a bottom internal-thought
## panel, and a toggleable Investigation Board modal (Tab).

@onready var _time: Label = $Top/Bar/Time
@onready var _lead: Label = $Top/Bar/Lead
@onready var _stability: ProgressBar = $Meters/Stability/Bar
@onready var _corruption: ProgressBar = $Meters/Corruption/Bar
@onready var _panic: ProgressBar = $Meters/Panic/Bar
@onready var _thought_panel: Panel = $ThoughtPanel
@onready var _thought: Label = $ThoughtPanel/Margin/Text
@onready var _thought_timer: Timer = $ThoughtTimer
@onready var _board: Control = $InvestigationBoard
@onready var _map: Control = $DistrictMap
@onready var _cult: Control = $CultProgress
@onready var _rituals: Control = $RitualPanel
@onready var _prayer: Control = $PrayerPanel
@onready var _debug: Control = $DebugLogPanel
@onready var _inventory: Control = $InventoryPanel

func _ready() -> void:
	WorldState.thought_requested.connect(_on_thought)
	WorldState.state_changed.connect(_refresh)
	WorldState.lead_changed.connect(_on_lead_changed)
	_thought_timer.timeout.connect(_thought_panel.hide)
	_thought_panel.visible = false
	_board.visible = false
	_on_lead_changed(WorldState.current_lead)
	_refresh()

func _refresh() -> void:
	_time.text = WorldState.time_phase
	_stability.value = WorldState.stability()
	_corruption.value = WorldState.corruption
	_panic.value = WorldState.panic

func _on_lead_changed(text: String) -> void:
	_lead.text = "Lead: " + text

func _on_thought(text: String) -> void:
	_thought.text = text
	_thought_panel.visible = true
	_thought_timer.start(4.5)

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_board"):
		_board.visible = not _board.visible
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("toggle_map"):
		_map.toggle()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("toggle_cult"):
		_cult.toggle()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("toggle_rituals"):
		_rituals.toggle()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("toggle_prayer"):
		_prayer.toggle()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("toggle_debug"):
		_debug.toggle()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("toggle_inventory"):
		_inventory.toggle()
		get_viewport().set_input_as_handled()
