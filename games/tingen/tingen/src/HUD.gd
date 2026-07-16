extends Control
## Main exploration HUD (GDD §19.2): time phase + active lead along the top, the M4 MeterHUD
## (Doom/Madness/Notice/Heat) at the right, a bottom internal-thought panel, and a toggleable
## Investigation Board modal (Tab).

@onready var _time: Label = $Top/Bar/Time
@onready var _lead: Label = $Top/Bar/Lead
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

## The combat/meter legend (M10) — code-authored so the persistent HUD scene stays a single writer.
var _legend: Control = null
## P4: the harvest-fork 3-choice panel (digest / sell / keep) — code-authored, same pattern. It
## self-wires to GMOpening.harvest_fork_ui_requested and presents ONCE per run at the first
## Characteristic pickup.
var _fork: Control = null

func _ready() -> void:
	WorldState.thought_requested.connect(_on_thought)
	WorldState.state_changed.connect(_refresh)
	WorldState.lead_changed.connect(_on_lead_changed)
	# P5: the top-bar clock FOLLOWS the live Clock. It used to refresh only on world
	# state_changed, so it froze at the boot string ("Morning - 08:00") for the whole run —
	# the day/night pass is unreadable without a moving clock. Presentation only.
	Clock.minute_ticked.connect(_on_clock_minute)
	Clock.phase_changed.connect(_on_clock_phase)
	_thought_timer.timeout.connect(_thought_panel.hide)
	_thought_panel.visible = false
	_board.visible = false
	# Mount the always-available combat/meter legend (M10). Unobtrusive: a corner hint + an 'H' toggle.
	_legend = (load("res://src/HudLegend.gd") as GDScript).new()
	_legend.name = "HudLegend"
	add_child(_legend)
	# P4: the harvest-fork choice panel (presented once per run by GMOpening's pickup trigger).
	_fork = (load("res://src/HarvestForkPanel.gd") as GDScript).new()
	_fork.name = "HarvestForkPanel"
	add_child(_fork)
	_on_lead_changed(WorldState.current_lead)
	_refresh()

func _refresh() -> void:
	# B10 (M23): the legacy Stability/Corruption/Panic panel was removed — it mirrored the M4 MeterHUD
	# (Corruption aliases Doom), stacking a second, redundant meter panel on the right. MeterHUD is now
	# the sole meter readout (it drives itself off Meters.meter_changed); the HUD only refreshes the top bar.
	# P5: read the LIVE Clock, not WorldState.time_phase — that string only re-renders per phase
	# change, so the label used to show the phase's START minute for hours of play.
	_time.text = "%s - %s" % [String(Clock.phase).capitalize(), Clock.hhmm()]

func _on_clock_minute(_minute: int, _day: int) -> void:
	_refresh()

func _on_clock_phase(_phase: String, _day: int) -> void:
	_refresh()

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
	elif event.is_action_pressed("toggle_legend"):
		if _legend != null:
			_legend.toggle()
		get_viewport().set_input_as_handled()
