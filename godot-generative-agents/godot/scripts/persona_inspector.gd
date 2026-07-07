extends Control
## A pop-up "State Details" inspector for one persona (issue #408): the per-agent
## structure the old Django/Phaser replay surfaced, brought across to the Godot
## viewer. Open it for a character (the sidebar's ⓘ Details button, or the P key
## for the tracked agent) and it overlays a dimmed campus with a scrollable card of
## that persona's identity, cognition knobs, daily schedule, current action,
## reasoning, and memory stream.
##
## Two halves of the card:
##   * Static (built on open) — the persona's identity/personality, cognition
##     settings, and full daily schedule. These come from the replay/live `meta`
##     (see backend penn_world.persona_meta_entry), so they don't change per step.
##   * Dynamic (refreshed each step while open) — the current action, the agent's
##     reasoning, and the memories (retrieved this step + the running stream). The
##     viewer pushes these in via set_step_state as playback advances behind us, so
##     the panel ticks live like the heatmap pop-up does.
##
## Like heatmap_panel.gd this is pure UI + a modal: it knows nothing about the sim
## until viewer.gd calls open() / set_step_state(), and emits close_requested for
## the viewer to hide us and restore the camera. The Penn persona schema is flat --
## no innate/learned/currently/lifestyle and no per-persona att_bandwidth/retention;
## vision_r is a global -- so the Smallville-only fields degrade to "n/a" rather
## than showing blank (the panel structure is preserved either way).

## Emitted when the user asks to close (the close button, Esc, or a click on the
## dimmed backdrop outside the card). viewer.gd hides us and restores the camera.
signal close_requested

# The card's fixed width; its height is capped to a fraction of the viewport and the
# body scrolls inside that. A comfortable reading width for the persona blurb.
const CARD_WIDTH := 760.0
const MAX_HEIGHT_FRACTION := 0.84
# Dark translucent wash over the whole screen behind the card (matches the heatmap
# pop-up's tone), so the card reads as a modal window and the campus recedes.
const BACKDROP_COLOR := Color(0.06, 0.07, 0.10, 0.82)
# Ink that stays legible on the dark card (shared look with heatmap_panel.gd).
const INK := Color(0.94, 0.92, 0.88)
const INK_DIM := Color(0.74, 0.72, 0.68)
# Section headings sit a touch brighter/bolder than body text.
const HEADING := Color(1.0, 0.90, 0.62)
# Accent for the current schedule stop / current action, so "where they are now"
# pops out of the day's plan.
const NOW_ACCENT := Color(1.0, 0.82, 0.35)
# Memory rows are tinted by kind, matching the Phaser panel's accent colours so an
# observation, plan, reflection or chat memory reads at a glance.
const MEM_COLORS := {
	"observation": Color(0.55, 0.75, 1.0),   # blue
	"plan": Color(1.0, 0.82, 0.45),          # amber
	"reflection": Color(0.80, 0.65, 1.0),    # purple
	"chat": Color(0.55, 0.90, 0.75),         # teal
}
# The full memory stream can grow to hundreds of entries; render only the most
# recent this many (newest first) so the card stays responsive, and SAY when the
# rest are hidden rather than silently truncating.
const MEM_STREAM_CAP := 40

# The persona being shown and the live state pushed in by the viewer.
var _detail := {}          # the meta persona entry + vision_r/sec_per_step (see open)
var _frame := {}           # this step's per-agent frame (x/y/act/e/reasoning/chat/memories)
var _mem_stream: Array = []  # the persona's full memory stream (replay only; [] live)
var _step := 0

# Widgets, built in code in _ready() (heatmap_panel.gd style).
var _panel: PanelContainer
var _scroll: ScrollContainer
var _title: Label          # emoji + name
var _subtitle: Label       # home · current time
var _body: VBoxContainer   # every section, rebuilt on open / step change


func _ready() -> void:
	# Fill the screen so the backdrop can dim everything and catch a click-outside;
	# start hidden (viewer.gd flips us visible on open). A hidden Control neither
	# draws nor handles input, so this is inert until opened.
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	visible = false

	# The dark wash over the whole screen. STOP so a click on it (outside the card)
	# closes, and so clicks don't fall through to the camera drag/zoom behind us.
	var backdrop := ColorRect.new()
	backdrop.color = BACKDROP_COLOR
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	backdrop.mouse_filter = Control.MOUSE_FILTER_STOP
	backdrop.gui_input.connect(_on_backdrop_input)
	add_child(backdrop)

	# A full-screen CenterContainer centres the card at whatever size it settles to.
	# IGNORE mouse so clicks outside the card fall through to the backdrop (closes us).
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)

	# The floating card: a dark rounded panel built in code (like the heatmap pop-up),
	# not the light parchment theme, so the two modals read as a matched pair.
	_panel = PanelContainer.new()
	_panel.mouse_filter = Control.MOUSE_FILTER_STOP  # eat clicks so they don't pan
	_panel.add_theme_stylebox_override("panel", _make_panel_style())
	center.add_child(_panel)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	_panel.add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	margin.add_child(col)

	# Title row: emoji + name on the left, a close button on the right.
	var title_row := HBoxContainer.new()
	title_row.add_theme_constant_override("separation", 8)
	col.add_child(title_row)

	var title_col := VBoxContainer.new()
	title_col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_col.add_theme_constant_override("separation", 2)
	title_row.add_child(title_col)

	_title = Label.new()
	_title.add_theme_color_override("font_color", INK)
	_title.add_theme_font_size_override("font_size", 26)
	title_col.add_child(_title)

	_subtitle = Label.new()
	_subtitle.add_theme_color_override("font_color", INK_DIM)
	_subtitle.add_theme_font_size_override("font_size", 15)
	title_col.add_child(_subtitle)

	var close_btn := Button.new()
	close_btn.text = "Close  ✕"
	close_btn.tooltip_text = "Close (Esc)"
	close_btn.focus_mode = Control.FOCUS_NONE
	close_btn.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	close_btn.pressed.connect(func() -> void: close_requested.emit())
	title_row.add_child(close_btn)

	# The scrollable body: every section lives in _body inside this scroller, so a
	# long persona blurb + schedule + memory stream never overflows the screen.
	_scroll = ScrollContainer.new()
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	col.add_child(_scroll)

	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 12)
	_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scroll.add_child(_body)

	var hint := Label.new()
	hint.text = "P / Esc to close"
	hint.add_theme_color_override("font_color", INK_DIM)
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(hint)


## Open the inspector for a persona. `detail` is the replay/live meta persona entry
## ({name, emoji, persona, home, schedule}) with the world's `vision_r` and
## `sec_per_step` folded in by the viewer. The viewer follows this immediately with
## set_step_state() to fill the dynamic sections for the current step.
func open(detail: Dictionary) -> void:
	_detail = detail
	# Size the scroller now (the viewport may have resized since _ready).
	var vp := get_viewport().get_visible_rect().size
	_scroll.custom_minimum_size = Vector2(CARD_WIDTH, vp.y * MAX_HEIGHT_FRACTION)
	_title.text = "%s  %s" % [String(detail.get("emoji", "")), String(detail.get("name", "?"))]
	visible = true
	_rebuild()


## Push the current step's state (called on open and again each time the playhead
## advances while we're visible). `frame` is this agent's per-step dict; `mem_stream`
## is its full memory history (empty in live mode -> the stream section degrades to
## just the retrieved-this-step memories); `clock_text` is the sim's wall-clock label.
func set_step_state(frame: Dictionary, mem_stream: Array, step: int, clock_text: String) -> void:
	_frame = frame
	_mem_stream = mem_stream
	_step = step
	var home := String(_detail.get("home", ""))
	_subtitle.text = ("%s  ·  %s" % [home, clock_text]) if home != "" else clock_text
	if visible:
		_rebuild()


func close() -> void:
	visible = false


func _rebuild() -> void:
	# Clear and repaint every section. The card is a screenful of small labels, and a
	# step only changes ~10x/sec while we're open, so a full rebuild stays cheap and
	# keeps the code simple (no per-widget diffing).
	for child in _body.get_children():
		child.queue_free()

	_build_personality()
	_build_settings()
	_build_schedule()
	_build_current_action()
	_build_reasoning()
	_build_memory()


func _build_personality() -> void:
	_add_heading("Personality & identity")
	var blurb := String(_detail.get("persona", "")).strip_edges()
	if blurb != "":
		_add_wrapped(blurb)
	# innate/learned/currently/lifestyle are Smallville-only; render each ONLY if the
	# world authored it (Penn has none -> nothing added here, a graceful degrade to
	# just the free-text blurb above rather than four blank rows).
	for field in ["innate", "learned", "currently", "lifestyle"]:
		var val := String(_detail.get(field, "")).strip_edges()
		if val != "":
			_add_kv(field.capitalize(), val)


func _build_settings() -> void:
	# The cognition knobs. vision_r is a real world value (a global for Penn);
	# att_bandwidth/retention are Smallville-only and unauthored here, so they show
	# "n/a" (dimmed) -- preserving the old panel's structure without faking numbers.
	_add_heading("Settings")
	_add_kv("Vision radius", "%d tiles" % int(_detail.get("vision_r", 0)))
	_add_kv("Attention bandwidth", "n/a", true)
	_add_kv("Retention", "n/a", true)


func _build_schedule() -> void:
	var schedule: Array = _detail.get("schedule", [])
	if schedule.is_empty():
		return
	_add_heading("Daily schedule")
	var current := _current_stop_index()
	var sec_per_step := int(_detail.get("sec_per_step", 10))
	for i in schedule.size():
		var stop: Dictionary = schedule[i]
		var steps: Variant = stop.get("steps")
		var dur := "rest of day"
		if steps != null:
			dur = "%d steps (~%d min)" % [int(steps), int(round(float(steps) * sec_per_step / 60.0))]
		var line := "%s  %s — %s  ·  %s" % [
			String(stop.get("emoji", "")), String(stop.get("place", "")),
			String(stop.get("activity", "")), dur,
		]
		var label := _add_wrapped(line)
		if i == current:
			# Mark where they are in the day right now.
			label.text = "▸ " + label.text
			label.add_theme_color_override("font_color", NOW_ACCENT)


func _build_current_action() -> void:
	_add_heading("Current action")
	var act := String(_frame.get("act", ""))
	# `act` is "<description> @ UPenn:<Building>:<area>" -- split it into the
	# description (what they're doing) and the address (where), like the Phaser
	# panel's act_description / act_address. Either half may be absent.
	var halves := act.split(" @ ")
	var desc := halves[0] if halves.size() > 0 else act
	var addr := halves[1] if halves.size() > 1 else ""
	_add_kv("Doing", desc if desc != "" else "—")
	_add_kv("Address", addr if addr != "" else "—", addr == "")
	_add_kv("Expression", String(_frame.get("e", "")))


func _build_reasoning() -> void:
	_add_heading("Reasoning")
	var reasoning: Variant = _frame.get("reasoning")
	if reasoning != null and String(reasoning).strip_edges() != "":
		_add_wrapped(String(reasoning))
	else:
		# The mock brain leaves reasoning a stub; a real-LLM run fills it in.
		_add_wrapped("(no reasoning recorded this step)").add_theme_color_override(
			"font_color", INK_DIM
		)


func _build_memory() -> void:
	# Retrieved for THIS step (what the agent pulled up when deciding) -- straight
	# from the frame, so this works in both replay and live mode.
	var retrieved: Array = _frame.get("memories", []) if _frame.get("memories") != null else []
	_add_heading("Memories retrieved this step (%d)" % retrieved.size())
	if retrieved.is_empty():
		_add_wrapped("(none retrieved)").add_theme_color_override("font_color", INK_DIM)
	for mem in retrieved:
		if mem is Dictionary:
			_add_memory_row(mem)

	# The full running stream, newest first, filtered to what has happened by now.
	# Empty in live mode (the live feed carries no stream) -> this whole section is
	# simply skipped, a graceful degrade to the retrieved-this-step list above.
	if _mem_stream.is_empty():
		return
	var so_far: Array = []
	for mem in _mem_stream:
		if mem is Dictionary and int(mem.get("created_turn", 0)) <= _step:
			so_far.append(mem)
	# Newest first (the stream is stored oldest->newest).
	so_far.reverse()
	var shown: int = mini(so_far.size(), MEM_STREAM_CAP)
	var heading := "Memory stream (%d)" % so_far.size()
	if shown < so_far.size():
		heading = "Memory stream (showing latest %d of %d)" % [shown, so_far.size()]
	_add_heading(heading)
	for i in shown:
		_add_memory_row(so_far[i])


# --- small builder helpers -------------------------------------------------


func _add_heading(text: String) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", HEADING)
	label.add_theme_font_size_override("font_size", 18)
	_body.add_child(label)


func _add_wrapped(text: String) -> Label:
	# A body paragraph that wraps to the card width (returned so the caller can tint it).
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", INK)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.custom_minimum_size = Vector2(CARD_WIDTH - 40.0, 0)
	_body.add_child(label)
	return label


func _add_kv(key: String, value: String, dim := false) -> void:
	# A "Key: value" row -- the key greyed, the value in ink (dimmed when it's a
	# placeholder like "n/a"/"—" so a real value stands out from a missing one).
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)

	var k := Label.new()
	k.text = key
	k.add_theme_color_override("font_color", INK_DIM)
	k.custom_minimum_size = Vector2(150, 0)
	row.add_child(k)

	var v := Label.new()
	v.text = value
	v.add_theme_color_override("font_color", INK_DIM if dim else INK)
	v.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.custom_minimum_size = Vector2(CARD_WIDTH - 200.0, 0)
	row.add_child(v)

	_body.add_child(row)


func _add_memory_row(mem: Dictionary) -> void:
	# One memory: a kind badge (coloured by kind) + importance, then the text beneath.
	var kind := String(mem.get("kind", "observation"))
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)

	var meta := Label.new()
	meta.text = "%s · importance %.1f" % [kind, float(mem.get("importance", 0.0))]
	meta.add_theme_font_size_override("font_size", 13)
	meta.add_theme_color_override("font_color", MEM_COLORS.get(kind, INK_DIM))
	box.add_child(meta)

	var text := Label.new()
	text.text = String(mem.get("text", ""))
	text.add_theme_color_override("font_color", INK)
	text.add_theme_font_size_override("font_size", 15)
	text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text.custom_minimum_size = Vector2(CARD_WIDTH - 40.0, 0)
	box.add_child(text)

	_body.add_child(box)


func _current_stop_index() -> int:
	# Best-effort "which stop are they on right now": the schedule stop whose place or
	# activity appears in the current action string. Returns -1 while walking between
	# stops (the walk action matches no stop), so nothing is highlighted then.
	var act := String(_frame.get("act", ""))
	if act == "":
		return -1
	var schedule: Array = _detail.get("schedule", [])
	for i in schedule.size():
		var stop: Dictionary = schedule[i]
		var activity := String(stop.get("activity", ""))
		if activity != "" and act.contains(activity):
			return i
	# Fall back to matching the place (the address half of the action).
	for i in schedule.size():
		var place := String(schedule[i].get("place", ""))
		if place != "" and act.contains(place):
			return i
	return -1


func _on_backdrop_input(event: InputEvent) -> void:
	# A click on the dimmed area outside the card closes the inspector.
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		close_requested.emit()
		accept_event()


func _make_panel_style() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.13, 0.17, 0.98)
	sb.set_corner_radius_all(10)
	sb.set_content_margin_all(4.0)
	sb.set_border_width_all(2)
	sb.border_color = Color(1.0, 0.97, 0.86, 0.35)
	return sb
