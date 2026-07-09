extends Control
## A pop-up social graph: WHO has talked to WHOM, up to the current playback step
## (issue #252). Open it at any point (the G key or the sidebar "Social graph" button)
## and it draws the cast in a circle with an edge per pair that has conversed, the
## edge growing thicker the more (and the more recently) that pair has talked.
##
## Two views, cycled with LEFT / RIGHT (the heatmap pop-up's idiom):
##   * Conversations — edges accumulated from the replay's per-frame `chat`
##     transcripts, so what you see is what actually happened up to this step.
##     Thickness folds recency in (see HALF_LIFE_STEPS); stale edges also fade.
##   * Seed — the authored t=0 relationships from meta.relationships (the world
##     YAML `relationships:` block, #409): who already knew whom before the sim
##     began. Flipping between the views is the seed-vs-actual comparison.
##
## Like heatmap_panel.gd this is pure UI: it knows nothing about the sim until
## viewer.gd hands it the replay via set_replay(), then drives it with
## show_up_to(step) and cycle_view(delta). It works identically on a baked replay
## and a live run (frames are held by reference, so live appends flow in), and the
## seed view is meaningful even before a live run's first frame arrives.

## Emitted when the user asks to close the pop-up (the close button, or a click on
## the dimmed backdrop outside the panel). viewer.gd hides us and restores the camera.
signal close_requested

## The graph square's share of the viewport's smaller side.
@export var max_viewport_fraction: float = 0.62

# Dark translucent wash over the whole screen behind the panel (matches the other
# modals), so the pop-up reads as a window and the graph pops against it.
const BACKDROP_COLOR := Color(0.06, 0.07, 0.10, 0.82)
# Per-persona tints, kept in step with viewer.gd's TINTS (shared by the sprite, the
# sidebar row, the minimap dot and the heatmap) so a node's colour matches its agent.
const TINTS := [
	Color(1.0, 0.95, 0.95),  # Maya    - warm white
	Color(0.70, 0.82, 1.0),  # Ellis   - blue
	Color(0.80, 1.0, 0.78),  # Diego   - green
	Color(1.0, 0.86, 0.70),  # Priya   - amber
	Color(1.0, 0.95, 0.55),  # Marcus  - yellow
	Color(1.0, 0.78, 0.92),  # Tanaka  - pink
	Color(0.70, 1.0, 0.97),  # Sofia   - cyan
]
# Ink that stays legible on the dark panel.
const INK := Color(0.94, 0.92, 0.88)
const INK_DIM := Color(0.74, 0.72, 0.68)
# Conversation edges: the warm amber of the in-world conversation links
# (viewer._link_line), so "these two talked" reads the same in both places.
const CONVO_COLOR := Color(1.0, 0.78, 0.30)
# Seed edges: a cool slate blue, deliberately NOT the conversation amber -- seed
# edges are what agents start knowing, not something that happened on screen.
const SEED_COLOR := Color(0.55, 0.65, 0.90)
# A conversation this many steps ago counts half as much as one happening now; its
# weight keeps halving every further HALF_LIFE_STEPS. 300 = a quarter of the
# 1200-step campus day, so "this morning" still shows while yesterday would fade.
const HALF_LIFE_STEPS := 300.0
# Edge width range (conversations view: recency-weighted mass, log-compressed like
# the heatmap; seed view: closeness 1..5).
const EDGE_W_MIN := 2.5
const EDGE_W_MAX := 10.0
# How far a stale edge fades: alpha of an edge whose last talk was ages ago -> just now.
const EDGE_ALPHA_MIN := 0.30
const EDGE_ALPHA_MAX := 0.95
const NODE_RADIUS := 22.0

# The replay, handed over by set_replay(); until then we draw nothing. _frames is
# held BY REFERENCE (like the heatmap), so a live run's appended frames flow in.
var _frames: Array = []
var _names: Array = []
# meta.relationships edges ({a, b, kind, closeness, description}), filtered to the
# names actually in the cast -- an old replay/backend without the key just yields [].
var _relationships: Array = []
# The playhead conversations are accumulated up to, and which view is shown.
var _step := -1
var _view_index := 0  # 0 = conversations up to _step, 1 = seed relationships
# Sorted-pair key "A\nB" -> Array of onset steps (one entry per conversation), the
# scan product _recompute() rebuilds; _draw_canvas turns it into widths/alphas.
var _pair_onsets := {}

# Widgets, built in code in _ready() (heatmap_panel.gd style).
var _panel: PanelContainer
var _canvas: Control
var _title: Label
var _legend: Label
var _hint: Label


func _ready() -> void:
	# Fill the screen so the backdrop can dim everything and catch a click-outside;
	# start hidden (viewer.gd flips us visible on open). A hidden Control neither
	# draws nor handles input, so this is inert until opened.
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	visible = false

	# The dark wash over the whole screen. STOP so a click on it (outside the panel)
	# closes, and so clicks don't fall through to the camera drag/zoom behind us.
	var backdrop := ColorRect.new()
	backdrop.color = BACKDROP_COLOR
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	backdrop.mouse_filter = Control.MOUSE_FILTER_STOP
	backdrop.gui_input.connect(_on_backdrop_input)
	add_child(backdrop)

	# A full-screen CenterContainer centres the window at whatever size its content
	# settles to. IGNORE mouse so clicks outside the panel fall through to the
	# backdrop (which closes us).
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)

	_panel = PanelContainer.new()
	_panel.mouse_filter = Control.MOUSE_FILTER_STOP  # eat clicks so they don't pan
	_panel.add_theme_stylebox_override("panel", _make_panel_style())
	center.add_child(_panel)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 14)
	_panel.add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	margin.add_child(col)

	# Title row: heading on the left, a close button on the right.
	var title_row := HBoxContainer.new()
	title_row.add_theme_constant_override("separation", 8)
	col.add_child(title_row)

	_title = Label.new()
	_title.add_theme_color_override("font_color", INK)
	_title.add_theme_font_size_override("font_size", 24)
	_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_row.add_child(_title)

	var close_btn := Button.new()
	close_btn.text = "Close  ✕"
	close_btn.tooltip_text = "Close (Esc)"
	# No focus, so LEFT / RIGHT switch views instead of being eaten by focus navigation.
	close_btn.focus_mode = Control.FOCUS_NONE
	close_btn.pressed.connect(func() -> void: close_requested.emit())
	title_row.add_child(close_btn)

	# The graph square, custom-drawn via the `draw` signal (no subclass needed).
	# IGNORE mouse so the backdrop still gets click-outside behind it.
	_canvas = Control.new()
	_canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_canvas.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	_canvas.draw.connect(_draw_canvas)
	col.add_child(_canvas)

	# Legend: one line explaining what the current view's edges encode.
	_legend = Label.new()
	_legend.add_theme_color_override("font_color", INK_DIM)
	_legend.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_legend.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_child(_legend)

	_hint = Label.new()
	_hint.text = "←  →  switch view      ·      G / Esc to close"
	_hint.add_theme_color_override("font_color", INK_DIM)
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_child(_hint)

	_update_title()


## Hand over the loaded replay + the seed graph (called once by viewer.gd after it
## loads a baked file or completes the live handshake). Unknown names in the seed
## edges are dropped rather than drawn: an old backend or a cast change should
## degrade to a sparser graph, never to a node that matches no agent.
func set_replay(frames: Array, names: Array, relationships: Array) -> void:
	_frames = frames
	_names = names
	_relationships = []
	for rel in relationships:
		if rel is Dictionary and _names.has(String(rel.get("a", ""))) and _names.has(String(rel.get("b", ""))):
			_relationships.append(rel)
	var vp := get_viewport().get_visible_rect().size
	var side: float = min(vp.x, vp.y) * max_viewport_fraction
	_canvas.custom_minimum_size = Vector2(side, side)
	_update_title()
	_update_legend()


## Accumulate + show the conversations from step 0 up to `step`. Called on open and
## again each time the playhead advances while we're visible (also after a seek --
## the full re-scan keeps the graph honest when the user scrubs backwards).
func show_up_to(step: int) -> void:
	if _frames.is_empty():
		return
	_step = clampi(step, 0, _frames.size() - 1)
	_recompute()
	_update_title()
	_canvas.queue_redraw()


## Cycle the shown view: conversations <-> seed; wraps either way.
func cycle_view(delta: int) -> void:
	_view_index = (_view_index + delta + 2) % 2
	_update_title()
	_update_legend()
	_canvas.queue_redraw()


func _recompute() -> void:
	# Rebuild the pair -> onset-steps map by scanning every frame 0.._step (the
	# heatmap's accumulate-by-rescan idiom: at most ~personas x steps checks, cheap
	# enough to redo per step, and trivially correct after a seek in either
	# direction). A conversation appears in the frames as the SAME transcript
	# stamped on every participant's `chat` for the whole co-located window, so:
	#   * an onset is "chat present and different from this agent's previous step"
	#     (Array != is deep value comparison), like viewer._update_agent_speech;
	#   * to count each conversation ONCE (not once per participant), only the
	#     transcript's opening speaker's frame records it;
	#   * the edge(s) connect every pair of distinct speakers in the transcript,
	#     so a future 3-way meeting yields all three edges.
	_pair_onsets = {}
	if _frames.is_empty() or _step < 0:
		return
	for name in _names:
		var prev: Variant = null
		for k in range(0, _step + 1):
			var frame: Variant = _frames[k]
			if typeof(frame) != TYPE_DICTIONARY:
				continue  # live mode can leave holes; skip them
			var f: Variant = (frame as Dictionary).get(name)
			if typeof(f) != TYPE_DICTIONARY:
				continue
			var chat: Variant = (f as Dictionary).get("chat")
			var is_onset: bool = (
				chat is Array and not (chat as Array).is_empty() and chat != prev
			)
			prev = chat
			if not is_onset:
				continue
			var opener: Variant = (chat as Array)[0]
			if not (opener is Array) or (opener as Array).is_empty() \
					or String((opener as Array)[0]) != String(name):
				continue  # not the opening speaker: the opener's own pass counts it
			var speakers := _speakers_in(chat)
			for i in range(speakers.size()):
				for j in range(i + 1, speakers.size()):
					var key := _pair_key(speakers[i], speakers[j])
					var onsets: Array = _pair_onsets.get(key, [])
					onsets.append(k)
					_pair_onsets[key] = onsets


func _speakers_in(chat: Variant) -> Array:
	# The distinct cast members who speak in a transcript, in first-line order.
	var speakers: Array = []
	for pair in chat:
		if pair is Array and not (pair as Array).is_empty():
			var who := String((pair as Array)[0])
			if _names.has(who) and not speakers.has(who):
				speakers.append(who)
	return speakers


func _pair_key(a: String, b: String) -> String:
	# Same sorted-pair key idiom as viewer._refresh_links.
	return a + "\n" + b if a < b else b + "\n" + a


func _edge_mass(onsets: Array) -> float:
	# Recency-weighted interaction mass: each conversation contributes 1 when it
	# just happened, decaying by half every HALF_LIFE_STEPS -- so thickness itself
	# encodes "how much and how recently", not just a raw count.
	var mass := 0.0
	for s in onsets:
		mass += pow(0.5, float(_step - int(s)) / HALF_LIFE_STEPS)
	return mass


func _draw_canvas() -> void:
	var sz := _canvas.size
	if sz.x <= 0.0 or sz.y <= 0.0 or _names.is_empty():
		return
	var font := get_theme_default_font()
	var font_size := get_theme_default_font_size()

	# The graph's own dark backdrop, so edges read against a consistent ground
	# whatever the campus behind the modal is doing.
	_canvas.draw_rect(Rect2(Vector2.ZERO, sz), Color(0.09, 0.10, 0.14, 1.0))

	# Node layout: the cast in a circle (top first, clockwise), leaving room for
	# the name labels under each node.
	var n := _names.size()
	var center := sz / 2.0
	var radius: float = min(sz.x, sz.y) / 2.0 - NODE_RADIUS - 34.0
	var pos := {}
	for i in range(n):
		pos[_names[i]] = center + Vector2.from_angle(-PI / 2.0 + TAU * float(i) / float(n)) * radius

	# 1. Edges (under the nodes), then their labels.
	if _view_index == 0:
		_draw_conversation_edges(pos, font, font_size)
	else:
		_draw_seed_edges(pos, font, font_size)

	# 2. Nodes: a dark backing ring, the persona's tint disc, the name below.
	for i in range(n):
		var name: String = _names[i]
		var p: Vector2 = pos[name]
		var tint: Color = TINTS[i % TINTS.size()]
		_canvas.draw_circle(p, NODE_RADIUS + 3.0, Color(0.05, 0.05, 0.08, 1.0))
		_canvas.draw_circle(p, NODE_RADIUS, tint)
		var label_pos := Vector2(p.x - 100.0, p.y + NODE_RADIUS + 18.0)
		_canvas.draw_string(
			font, label_pos, name, HORIZONTAL_ALIGNMENT_CENTER, 200.0, font_size, INK
		)

	# 3. A frame around the picture (the other modals' trim colour).
	_canvas.draw_rect(Rect2(Vector2.ZERO, sz), Color(1.0, 0.97, 0.86, 0.5), false, 2.0)


func _draw_conversation_edges(pos: Dictionary, font: Font, font_size: int) -> void:
	if _pair_onsets.is_empty():
		var msg := "No conversations yet — nobody has met."
		if _frames.is_empty():
			msg = "Waiting for the first live frame…"
		_draw_empty_state(msg, font, font_size)
		return
	# Log-compress the masses (the heatmap's ramp idiom) so one chatty pair can't
	# flatten every other edge to the minimum width.
	var max_mass := 0.0
	for key in _pair_onsets:
		max_mass = maxf(max_mass, _edge_mass(_pair_onsets[key]))
	var denom := log(1.0 + max_mass)
	for key in _pair_onsets:
		var names: PackedStringArray = String(key).split("\n")
		if not (pos.has(names[0]) and pos.has(names[1])):
			continue
		var onsets: Array = _pair_onsets[key]
		var t: float = (log(1.0 + _edge_mass(onsets)) / denom) if denom > 0.0 else 0.0
		var width := lerpf(EDGE_W_MIN, EDGE_W_MAX, t)
		# Staleness fade: how long ago this pair LAST talked (onsets are in scan
		# order, so the last entry is the most recent).
		var age := float(_step - int(onsets[onsets.size() - 1]))
		var alpha := lerpf(EDGE_ALPHA_MIN, EDGE_ALPHA_MAX, pow(0.5, age / HALF_LIFE_STEPS))
		var a: Vector2 = pos[names[0]]
		var b: Vector2 = pos[names[1]]
		_canvas.draw_line(a, b, Color(CONVO_COLOR.r, CONVO_COLOR.g, CONVO_COLOR.b, alpha), width)
		if onsets.size() >= 2:
			_draw_edge_label("×%d" % onsets.size(), (a + b) / 2.0, font, font_size)


func _draw_seed_edges(pos: Dictionary, font: Font, font_size: int) -> void:
	if _relationships.is_empty():
		_draw_empty_state("No seed relationships in this replay.", font, font_size)
		return
	for rel in _relationships:
		var a_name := String(rel.get("a", ""))
		var b_name := String(rel.get("b", ""))
		if not (pos.has(a_name) and pos.has(b_name)):
			continue
		var closeness := clampi(int(rel.get("closeness", 1)), 1, 5)
		var a: Vector2 = pos[a_name]
		var b: Vector2 = pos[b_name]
		_canvas.draw_line(a, b, SEED_COLOR, 1.5 + 1.5 * float(closeness))
		var kind := String(rel.get("kind", ""))
		if kind != "":
			_draw_edge_label(kind, (a + b) / 2.0, font, font_size)


func _draw_edge_label(text: String, at: Vector2, font: Font, font_size: int) -> void:
	# A small inked label on a dark pill, so it stays readable on top of its edge.
	var size := font.get_string_size(text, HORIZONTAL_ALIGNMENT_CENTER, -1.0, font_size)
	var pad := Vector2(6.0, 3.0)
	var rect := Rect2(at - size / 2.0 - pad, size + pad * 2.0)
	_canvas.draw_rect(rect, Color(0.05, 0.05, 0.08, 0.85))
	_canvas.draw_string(
		font,
		Vector2(at.x - size.x / 2.0, at.y + size.y / 2.0 - font.get_descent(font_size) / 2.0),
		text,
		HORIZONTAL_ALIGNMENT_CENTER,
		-1.0,
		font_size,
		INK,
	)


func _draw_empty_state(text: String, font: Font, font_size: int) -> void:
	var sz := _canvas.size
	_canvas.draw_string(
		font,
		Vector2(0.0, sz.y / 2.0),
		text,
		HORIZONTAL_ALIGNMENT_CENTER,
		sz.x,
		font_size,
		INK_DIM,
	)


func _update_title() -> void:
	if _title == null:
		return
	if _view_index == 0:
		_title.text = (
			"Social Graph — Conversations · step %d" % maxi(_step, 0)
			if _step >= 0
			else "Social Graph — Conversations"
		)
	else:
		_title.text = "Social Graph — Seed relationships (t = 0)"


func _update_legend() -> void:
	if _legend == null:
		return
	if _view_index == 0:
		_legend.text = "thicker = more & recent talks   ·   faded = long ago   ·   ×k = conversations"
	else:
		_legend.text = "authored t=0 edges   ·   thicker = closer (closeness 1–5)"


func _on_backdrop_input(event: InputEvent) -> void:
	# A click on the dimmed area outside the panel closes the pop-up.
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
