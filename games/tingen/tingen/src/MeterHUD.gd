extends Control
## The four-meter readout on the persistent HUD (direction v2 §3 progressive disclosure + §4).
##
## Shows Doom/Madness/Notice/Heat as small labelled bars. PROGRESSIVE DISCLOSURE: Doom is always
## visible (the world clock the player feels from 0:00); Madness/Notice/Heat stay HIDDEN until their
## first trigger reveals them (the Meters authority tracks the `revealed` flag; this widget mirrors
## it). Madness additionally shows the telegraphed ladder ticks (50/75/100) so the player can read
## how close they are to losing control. Pure read-out — nothing here mutates a meter.
##
## Event-driven like the rest of the HUD: refreshes on Meters.meter_changed (and on the ladder
## crossing, so a reveal lands the same frame), with a _process poll as the safety net.

@onready var _doom: Control = $Doom
@onready var _madness: Control = $Madness
@onready var _notice: Control = $Notice
@onready var _heat: Control = $Heat
@onready var _rampage: Label = $Rampage

## The Sequence rank read-out (M5, direction v2 §6): a legible "Hunter · Seq 9" line so the rank the
## player has climbed is always on screen. Created in code (no .tscn edit — one HUD writer) and named
## "Sequence" so the harness can find it. Always shown while a run is live.
var _sequence: Label = null

func _ready() -> void:
	var m := get_node_or_null("/root/Meters")
	if m != null:
		if not m.meter_changed.is_connected(_on_meter_changed):
			m.meter_changed.connect(_on_meter_changed)
		if not m.madness_threshold.is_connected(_on_madness_threshold):
			m.madness_threshold.connect(_on_madness_threshold)
	# Add the Sequence line once (code-authored so the persistent HUD scene stays a single writer).
	_sequence = get_node_or_null("Sequence") as Label
	if _sequence == null:
		_sequence = Label.new()
		_sequence.name = "Sequence"
		add_child(_sequence)
	# Refresh the rank line whenever the ladder advances (event-driven like the meters).
	var prog := get_node_or_null("/root/Progression")
	if prog != null and not prog.advanced.is_connected(_on_advanced):
		prog.advanced.connect(_on_advanced)
	# M10: re-skin the meter bars when the colorblind-safe palette (or any setting) changes.
	var s := get_node_or_null("/root/Settings")
	if s != null and not s.changed.is_connected(_on_settings_changed):
		s.changed.connect(_on_settings_changed)
	refresh()

## M10: re-apply the active palette to the meter bars (called on Settings.changed).
func _on_settings_changed(_key: String) -> void:
	refresh()

## Tint a meter row's ProgressBar fill to the active palette (colorblind-safe when enabled).
func _apply_meter_color(meter: String, row: Control) -> void:
	if row == null:
		return
	var s := get_node_or_null("/root/Settings")
	if s == null:
		return
	var bar := row.get_node_or_null("Bar") as ProgressBar
	if bar == null:
		return
	var sb := StyleBoxFlat.new()
	sb.bg_color = s.meter_color(meter)
	bar.add_theme_stylebox_override("fill", sb)

func _on_advanced(_pathway: String, _sequence_rank: int) -> void:
	refresh()

func _process(_delta: float) -> void:
	# Fully event-wired via meter_changed / madness_threshold — the ONLY value no signal covers is
	# the live rampage countdown, so poll only while a rampage is running (idle frames do no work).
	var m := get_node_or_null("/root/Meters")
	if m != null and bool(m.in_rampage()):
		refresh()

func _on_meter_changed(_meter: String, _value: float) -> void:
	refresh()

func _on_madness_threshold(_level: int) -> void:
	refresh()

## Pull every bar's value + visibility from the Meters authority (idempotent; tests call it directly).
func refresh() -> void:
	var m := get_node_or_null("/root/Meters")
	if m == null:
		return
	_bind("doom", _doom, m)
	_bind("madness", _madness, m)
	_bind("notice", _notice, m)
	_bind("heat", _heat, m)
	# The loss-of-control rampage countdown (§13 decision #5): a visible timer while the creature
	# form has taken over. Hidden otherwise.
	if _rampage != null:
		_rampage.visible = bool(m.in_rampage())
		if _rampage.visible:
			_rampage.text = "LOSS OF CONTROL — %ds" % int(ceil(m.rampage_remaining_s()))
	# The Sequence rank line (M5): "Hunter · Seq 9". Reads the Progression authority; hidden only when
	# progression is somehow absent (unit contexts).
	if _sequence != null:
		var prog := get_node_or_null("/root/Progression")
		_sequence.visible = prog != null
		if prog != null:
			_sequence.text = prog.label()

func _bind(meter: String, row: Control, m: Node) -> void:
	if row == null:
		return
	# Progressive disclosure: a meter that hasn't been triggered stays hidden (Doom is always
	# revealed by the Meters authority, so it always shows).
	row.visible = bool(m.is_revealed(meter))
	if not row.visible:
		return
	var bar := row.get_node_or_null("Bar") as ProgressBar
	if bar != null:
		bar.value = m.get_meter(meter)
	# M10: tint the fill to the active (colorblind-aware) palette.
	_apply_meter_color(meter, row)
