extends Control
## Settings panel (M10 polish) — reachable from BOTH the pause menu and the title screen.
##
## A small but REAL settings UI: every control is wired to the Settings authority, which persists the
## value and pushes the side-effect immediately (Settings.set_value applies audio/palette/text on the
## spot and emits `changed`). Nothing here is dead UI:
##   * Master Volume slider  -> drives the Master audio bus (audio deferred; bus wiring ready).
##   * Screen Shake toggle   -> gates CombatFeedback.shake().
##   * Hit Flash toggle      -> gates CombatFeedback.flash().
##   * Text Size option      -> scales HUD/dialogue fonts (this very panel re-scales live too).
##   * Colorblind-safe toggle-> swaps the meter/telegraph palette to the safe set.
##
## process_mode = ALWAYS so it works while the tree is paused (opened from the pause menu). It is a
## self-contained overlay; the caller owns mounting/freeing it.

var _open: bool = false
var _card: Control = null

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE

func is_open() -> bool:
	return _open

func open() -> void:
	if _open:
		return
	_fit_to_viewport()
	_build()
	_open = true

## Pin this root overlay to the WHOLE viewport (the CastPanel fix). A runtime-built Control
## mounted under a CanvasLayer — BOTH real callers: BootController's Title layer AND the PauseMenu
## autoload — is NOT sized by anchors applied after add_child, so the card collapsed to content
## size at top-left. Set the rect explicitly and track window resizes.
func _fit_to_viewport() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	if not is_inside_tree():
		return
	position = Vector2.ZERO
	size = get_viewport_rect().size
	var vp := get_viewport()
	if vp != null and not vp.size_changed.is_connected(_on_viewport_resized):
		vp.size_changed.connect(_on_viewport_resized)

func _on_viewport_resized() -> void:
	if is_inside_tree():
		position = Vector2.ZERO
		size = get_viewport_rect().size

func close() -> void:
	if is_instance_valid(_card):
		_card.queue_free()
	_card = null
	_open = false

func _settings() -> Node:
	return get_node_or_null("/root/Settings")

func _build() -> void:
	var s := _settings()

	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.02, 0.04, 0.6)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(dim)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.add_child(center)

	var panel := Panel.new()
	panel.custom_minimum_size = Vector2(460, 460)
	center.add_child(panel)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for m in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		margin.add_theme_constant_override(m, 22)
	panel.add_child(margin)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 14)
	margin.add_child(box)

	var title := Label.new()
	title.text = "SETTINGS"
	if s != null:
		s.apply_text_scale(title, 28)
	box.add_child(title)

	# Master volume slider.
	box.add_child(_label("Master Volume", s))
	var vol := HSlider.new()
	vol.min_value = 0.0
	vol.max_value = 1.0
	vol.step = 0.05
	vol.value = s.get_number("master_volume") if s != null else 1.0
	vol.custom_minimum_size = Vector2(400, 24)
	vol.value_changed.connect(func(v: float) -> void:
		if s != null:
			s.set_value("master_volume", v))
	box.add_child(vol)

	# Screen shake toggle.
	box.add_child(_toggle_row("Screen Shake", "screen_shake", s))
	# Hit flash toggle.
	box.add_child(_toggle_row("Hit Flash", "hit_flash", s))
	# Colorblind-safe palette toggle.
	box.add_child(_toggle_row("Colorblind-safe Palette", "colorblind", s))

	# Text size option.
	box.add_child(_label("Text Size", s))
	var sizes := OptionButton.new()
	sizes.add_item("Small (0.85x)")
	sizes.add_item("Normal (1.0x)")
	sizes.add_item("Large (1.25x)")
	sizes.add_item("Huge (1.5x)")
	var scales := [0.85, 1.0, 1.25, 1.5]
	# Explicit float: `:=` cannot infer from the unsafe (Variant) get_number call — a parse error
	# that left the whole panel unloadable (the title/pause Settings buttons silently dead).
	var cur: float = s.get_number("text_scale") if s != null else 1.0
	var sel := 1
	for i in scales.size():
		if abs(float(scales[i]) - cur) < 0.001:
			sel = i
	sizes.select(sel)
	sizes.item_selected.connect(func(idx: int) -> void:
		if s != null:
			s.set_value("text_scale", scales[idx])
			# Re-scale THIS panel live so the change is visible immediately.
			close()
			open())
	box.add_child(sizes)

	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(0, 8)
	box.add_child(spacer)

	var back := Button.new()
	back.text = "Back"
	back.custom_minimum_size = Vector2(200, 40)
	if s != null:
		s.apply_text_scale(back, 18)
	back.pressed.connect(close)
	box.add_child(back)

	_card = dim

func _label(text: String, s: Node) -> Label:
	var l := Label.new()
	l.text = text
	if s != null:
		s.apply_text_scale(l, 16)
	return l

func _toggle_row(text: String, key: String, s: Node) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 12)
	var cb := CheckBox.new()
	cb.button_pressed = s.get_bool(key) if s != null else true
	cb.toggled.connect(func(on: bool) -> void:
		if s != null:
			s.set_value(key, on))
	h.add_child(cb)
	var l := _label(text, s)
	h.add_child(l)
	return h
