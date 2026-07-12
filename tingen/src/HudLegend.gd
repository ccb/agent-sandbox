extends Control
## Combat/meter HUD legend (M10 polish) — a compact, always-available reference panel.
##
## The game teaches its meters and combat readout in-play (progressive disclosure), but a reference
## helps. This is an UNOBTRUSIVE, toggleable card (bound to a corner hint + the 'H' key via the HUD)
## that explains the four meters (Doom/Madness/Notice/Heat) and the combat readout (ammo, cooldown
## pips, telegraph line). Pure read-out — it mutates nothing. Starts CLOSED so it never covers play.
##
## Colors on the meter swatches follow the ACTIVE palette (Settings.meter_color), so the legend and
## the live meters agree even under the colorblind-safe palette.

var _open: bool = false
var _panel: Panel = null
var _hint: Label = null

func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_build_hint()
	_open = false
	var s := get_node_or_null("/root/Settings")
	if s != null and not s.changed.is_connected(_on_settings_changed):
		s.changed.connect(_on_settings_changed)

func _on_settings_changed(_key: String) -> void:
	# Re-skin swatches + re-scale text if the panel is currently up.
	if _open:
		_rebuild_panel()

## The corner hint that tells the player the legend exists ("[H] Legend").
func _build_hint() -> void:
	_hint = Label.new()
	_hint.name = "LegendHint"
	_hint.text = "[H] Legend"
	_hint.add_theme_color_override("font_color", Color(0.75, 0.75, 0.8, 0.7))
	_hint.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_hint.position = Vector2(12, -28)
	_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_hint)

func is_open() -> bool:
	return _open

func toggle() -> void:
	if _open:
		_close()
	else:
		_show_panel()

func _show_panel() -> void:
	_open = true
	_rebuild_panel()

func _close() -> void:
	_open = false
	if is_instance_valid(_panel):
		_panel.queue_free()
	_panel = null

func _rebuild_panel() -> void:
	if is_instance_valid(_panel):
		_panel.queue_free()
		_panel = null
	var s := get_node_or_null("/root/Settings")

	var panel := Panel.new()
	panel.name = "LegendPanel"
	panel.set_anchors_preset(Control.PRESET_CENTER_RIGHT)
	panel.position = Vector2(-360, -220)
	panel.custom_minimum_size = Vector2(340, 380)
	panel.mouse_filter = Control.MOUSE_FILTER_STOP

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 16)
	margin.add_theme_constant_override("margin_right", 16)
	margin.add_theme_constant_override("margin_top", 14)
	margin.add_theme_constant_override("margin_bottom", 14)
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.add_child(margin)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	margin.add_child(box)

	var title := Label.new()
	title.text = "LEGEND"
	if s != null:
		s.apply_text_scale(title, 20)
	else:
		title.add_theme_font_size_override("font_size", 20)
	box.add_child(title)

	# Four meter rows with a color swatch each (palette-aware).
	for row in _meter_rows():
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 8)
		var sw := ColorRect.new()
		sw.custom_minimum_size = Vector2(14, 14)
		sw.color = s.meter_color(row[0]) if s != null else Color.WHITE
		h.add_child(sw)
		var lbl := Label.new()
		lbl.text = row[1]
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lbl.custom_minimum_size = Vector2(280, 0)
		if s != null:
			s.apply_text_scale(lbl, 14)
		h.add_child(lbl)
		box.add_child(h)

	var sep := HSeparator.new()
	box.add_child(sep)

	var combat := Label.new()
	combat.text = _combat_readout_text()
	combat.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	combat.custom_minimum_size = Vector2(300, 0)
	if s != null:
		s.apply_text_scale(combat, 14)
	box.add_child(combat)

	add_child(panel)
	_panel = panel

func _meter_rows() -> Array:
	return [
		["doom", "Doom — the descent's clock. Fills as the cult's rite advances; at 100 it triggers Ritual Night."],
		["madness", "Madness — occult strain. Climbs the 50/75/100 ladder; topping out risks LOSS OF CONTROL (a rampage)."],
		["notice", "Notice — how seen you are. Witnessed occult acts raise it and draw the wrong attention."],
		["heat", "Heat — the law closing in. Violence and exposure raise it; high Heat brings the authorities down."],
	]

func _combat_readout_text() -> String:
	return ("COMBAT READOUT\n"
		+ "• ammo — rounds left in the carried weapon (— when none is carried).\n"
		+ "• cooldown pips — dash / charm recharge (full = ready).\n"
		+ "• telegraph line — an enemy is winding up a strike you can see; dodge or interrupt it.")

## The full legend text (test seam: proves the panel explains the meters + readout).
func legend_text() -> String:
	var parts: Array = []
	for row in _meter_rows():
		parts.append(String(row[1]))
	parts.append(_combat_readout_text())
	return "\n".join(parts)
