extends Control
## P4 (experiential wave) — the HARVEST FORK as a real 3-choice panel (digest / sell / keep).
##
## The audit found the famous fork was delivered as a thought-panel string with no choice UI. This
## panel presents it properly: GMOpening requests it (harvest_fork_ui_requested) ONCE per run when
## the FIRST Characteristic lands in the player's hands, with the authored scenario copy
## (opening.fork_ui — title/prompt/options, all DATA). The choice sets GUIDANCE ONLY:
##   * it routes to GMOpening.choose_harvest(id) — records the intent, marks the plan on the HUD
##     lead line, surfaces the sell hint for "sell";
##   * it NEVER executes the verbs — the lodging digest spot and Franky's counter remain the real
##     world seams (test_opener_staging (g) pins no-execution).
## Once ANSWERED the fork never re-opens (GMOpening.harvest_choice() is the per-run latch).
##
## Mounted by HUD.gd in code (the HudLegend pattern — the persistent HUD scene keeps one writer).
## Pure presentation + one logic seam (choose_harvest); safe headless (it is only ever mounted by
## the live HUD, and its logic methods are driven directly by the harness).

var _open: bool = false
var _panel: Control = null   # the full-rect overlay (CenterContainer) holding the ForkCard
var _ui: Dictionary = {}

func _ready() -> void:
	# anchors AND offsets — anchors alone leave this root zero-sized (the P4 probe layout lesson).
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	# Wire to the GM's request seam (idempotent — survives world swaps).
	var gm := get_node_or_null("/root/GMOpening")
	if gm != null and gm.has_signal("harvest_fork_ui_requested") \
			and not gm.harvest_fork_ui_requested.is_connected(present):
		gm.harvest_fork_ui_requested.connect(present)

func is_open() -> bool:
	return _open

## How many choices the open panel offers (0 when closed).
func option_count() -> int:
	return (_ui.get("options", []) as Array).size() if _open else 0

## Present the authored fork. Refuses when already open or when the fork was ALREADY ANSWERED this
## run (the once-answered contract — GMOpening.harvest_choice() is the latch).
func present(ui: Dictionary) -> void:
	if _open or ui.is_empty():
		return
	var gm := get_node_or_null("/root/GMOpening")
	if gm != null and String(gm.harvest_choice()) != "":
		return
	_ui = ui.duplicate(true)
	_open = true
	_build()

## The player picks a fork word: route it to the ONE logic seam (GMOpening.choose_harvest — records
## intent + marks the plan on the lead line), narrate the chosen line (authored data) on the built
## thought channel, and close. Guidance only — nothing is digested/sold/consumed here.
func choose(option_id: String) -> void:
	var gm := get_node_or_null("/root/GMOpening")
	if gm != null:
		var r: Dictionary = gm.choose_harvest(option_id)
		if bool(r.get("ok", false)):
			var line := _option_line(option_id)
			if line != "":
				var ws := get_node_or_null("/root/WorldState")
				if ws != null:
					ws.emit_signal("thought_requested", line)
	_close()

func _option_line(option_id: String) -> String:
	for o in (_ui.get("options", []) as Array):
		if o is Dictionary and String((o as Dictionary).get("id", "")) == option_id:
			return String((o as Dictionary).get("line", ""))
	return ""

func _close() -> void:
	_open = false
	if is_instance_valid(_panel):
		_panel.queue_free()
	_panel = null

# --- the panel build (dark noir card, centered, unmistakably a CHOICE) ---------------------------
## Layout lesson (P4 probe): Control.position is PARENT-relative — setting it after an anchor
## preset shoves the card off-screen. Center with containers instead: a full-rect CenterContainer
## (mouse-transparent) centers a PanelContainer that sizes itself to its content.
func _build() -> void:
	if is_instance_valid(_panel):
		_panel.queue_free()
	var s := get_node_or_null("/root/Settings")

	var overlay := CenterContainer.new()
	overlay.name = "ForkOverlay"
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE

	var panel := PanelContainer.new()
	panel.name = "ForkCard"
	panel.custom_minimum_size = Vector2(520, 0)
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.09, 0.085, 0.11, 0.96)
	sb.border_color = Color(0.55, 0.47, 0.30, 0.9)
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(6)
	panel.add_theme_stylebox_override("panel", sb)
	overlay.add_child(panel)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 20)
	margin.add_theme_constant_override("margin_right", 20)
	margin.add_theme_constant_override("margin_top", 16)
	margin.add_theme_constant_override("margin_bottom", 16)
	panel.add_child(margin)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	margin.add_child(box)

	var title := Label.new()
	title.text = String(_ui.get("title", ""))
	title.add_theme_color_override("font_color", Color(0.85, 0.76, 0.55))
	if s != null:
		s.apply_text_scale(title, 20)
	else:
		title.add_theme_font_size_override("font_size", 20)
	box.add_child(title)

	var prompt := Label.new()
	prompt.text = String(_ui.get("prompt", ""))
	prompt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	prompt.custom_minimum_size = Vector2(460, 0)
	if s != null:
		s.apply_text_scale(prompt, 14)
	box.add_child(prompt)

	box.add_child(HSeparator.new())

	for o in (_ui.get("options", []) as Array):
		if not (o is Dictionary):
			continue
		var od: Dictionary = o
		var id := String(od.get("id", ""))
		var btn := Button.new()
		btn.text = String(od.get("label", id))
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		if s != null:
			s.apply_text_scale(btn, 16)
		btn.pressed.connect(func() -> void: choose(id))
		box.add_child(btn)
		var line := Label.new()
		line.text = String(od.get("line", ""))
		line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		line.custom_minimum_size = Vector2(460, 0)
		line.add_theme_color_override("font_color", Color(0.62, 0.62, 0.66))
		if s != null:
			s.apply_text_scale(line, 12)
		else:
			line.add_theme_font_size_override("font_size", 12)
		box.add_child(line)

	add_child(overlay)
	_panel = overlay