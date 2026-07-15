extends Control
## A small "thinking…" pill shown at the top of the view while a live decision
## tick stalls (issue #372) -- tells the user the sim is working, not frozen.
## Global, not per-agent (per-agent bubbles are #551). Styled distinctly from the
## #245 speech bubbles (a dark status pill, not a white speech balloon). Pure UI,
## live-only; viewer.gd flips it via set_active(). Only ticks while active.

const ThinkingIndicator := preload("res://scripts/thinking_indicator.gd")

const INK := Color(0.96, 0.95, 0.90)

var _label: Label


func _ready() -> void:
	# Top of the view, above the world; ignore mouse so it never eats a pan/click;
	# start hidden and inert (set_active(true) wakes it).
	set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visible = false

	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	center.offset_top = 12
	add_child(center)

	var pill := PanelContainer.new()
	pill.mouse_filter = Control.MOUSE_FILTER_IGNORE
	pill.add_theme_stylebox_override("panel", _pill_style())
	center.add_child(pill)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 14)
	margin.add_theme_constant_override("margin_right", 14)
	margin.add_theme_constant_override("margin_top", 6)
	margin.add_theme_constant_override("margin_bottom", 6)
	pill.add_child(margin)

	_label = Label.new()
	_label.add_theme_color_override("font_color", INK)
	_label.add_theme_font_size_override("font_size", 15)
	_label.text = "thinking"
	margin.add_child(_label)

	set_process(false)  # only animate while active


func set_active(active: bool) -> void:
	visible = active
	set_process(active)
	if active:
		_label.text = ThinkingIndicator.ellipsis(Time.get_ticks_msec())


func _process(_delta: float) -> void:
	_label.text = ThinkingIndicator.ellipsis(Time.get_ticks_msec())


func _pill_style() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.10, 0.11, 0.15, 0.88)
	sb.set_corner_radius_all(12)
	sb.set_border_width_all(1)
	sb.border_color = Color(1.0, 0.97, 0.86, 0.30)
	return sb
