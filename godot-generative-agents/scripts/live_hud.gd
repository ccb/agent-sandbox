extends PanelContainer
## Top-right run monitor: cost meter + backend health + Emergency Stop (issue #264).
##
## A live real-LLM run spends money every step and can stall on the provider;
## this small HUD makes spend and liveness visible and gives the operator a
## one-click stop. It is pure UI, in the same shape as agent_panel.gd and
## minimap.gd: it knows nothing about backends or replays. penn_replay.gd wires
## a *source* (hud_source_replay.gd today, hud_source_live.gd when a backend is
## running) whose signals drive the setters below, and routes our
## `stop_requested` back to that source -- so switching from simulated to real
## data changes nothing here.
##
## The usage dict rendered by set_usage() is the engine's UsageLedger.summary()
## shape (text_adventure_games/usage.py) -- what the backend's `GET /usage`
## serves. Tokens/min is derived HERE from successive summaries (wall-clock
## deltas), so no source has to compute a rate.

## The Emergency Stop button. The viewer routes this to the active source
## (freeze the replay / POST /pause); the source confirms via halted_changed,
## which comes back through set_halted() -- the HUD never assumes the stop
## worked just because the button was pressed.
signal stop_requested

# Same footprint idiom as the sidebar (agent_panel sets 300); the HUD hugs the
# top-right corner with this width and grows downward as rows appear.
const PANEL_WIDTH := 250.0
const MARGIN := 16.0
# Tokens/min is measured over this sliding window of usage samples. Long enough
# to smooth poll jitter, short enough to react when a run stalls or speeds up.
const RATE_WINDOW_MS := 60000
# ...but don't show a rate until the window spans this much time (a rate from
# two samples 50ms apart is noise).
const RATE_MIN_SPAN_MS := 2000

# Status-dot colours per hud_source.gd Health state, + the halted override.
const DOT_COLORS := {
	0: Color(0.45, 0.55, 0.75),  # SIMULATED - calm blue-grey
	1: Color(0.30, 0.65, 0.30),  # OK        - green
	2: Color(0.85, 0.62, 0.15),  # DEGRADED  - amber
	3: Color(0.78, 0.22, 0.18),  # DOWN      - red
}
const STATE_NAMES := {0: "Simulated", 1: "Live", 2: "Degraded", 3: "Offline"}
const HALT_COLOR := Color(0.78, 0.22, 0.18)
# Muted small-print colour, matching the sidebar's status lines (readable on
# the Cute Fantasy parchment).
const MUTED_COLOR := Color(0.42, 0.32, 0.24)
const TRIPPED_COLOR := Color(0.72, 0.16, 0.12)

var _dot: ColorRect
var _status: Label
var _source_line: Label
var _body: VBoxContainer  # everything below the header; hidden when collapsed
var _collapse: Button     # the header's collapse/expand toggle
var _values := {}       # row key -> value Label (see _add_row)
var _budget_row: HBoxContainer
var _stop: Button
var _halted := false
var _health_state := 0
var _health_detail := ""
# (ticks_msec, cumulative total tokens) samples for the tokens/min readout.
var _samples: Array = []


func _ready() -> void:
	# Pin to the top-right corner and grow downward as rows appear, so the panel
	# tracks window resizes for free (same trick as the minimap, other corner).
	# Anchors + all four offsets are set explicitly: anchors at (1, 0) make the
	# offsets corner-relative, the left/right pair fixes the width, and the
	# zero-height top/bottom pair lets the content's minimum size (with
	# grow_vertical = END) decide how tall the panel is.
	custom_minimum_size = Vector2(PANEL_WIDTH, 0)
	anchor_left = 1.0
	anchor_top = 0.0
	anchor_right = 1.0
	anchor_bottom = 0.0
	offset_left = -(PANEL_WIDTH + MARGIN)
	offset_top = MARGIN
	offset_right = -MARGIN
	offset_bottom = MARGIN
	grow_horizontal = Control.GROW_DIRECTION_BEGIN
	grow_vertical = Control.GROW_DIRECTION_END

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 10)
	add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	margin.add_child(col)

	# Header: health dot + title + a collapse toggle. This row survives a
	# collapse, so the monitor stays discoverable AND its most safety-critical
	# bit -- the dot's colour (health, or red for HALTED) -- stays glanceable
	# even with the details folded away.
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 8)
	col.add_child(header)

	_dot = ColorRect.new()
	_dot.custom_minimum_size = Vector2(12, 12)
	_dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_dot.color = DOT_COLORS[0]
	header.add_child(_dot)

	var title := Label.new()
	title.text = "RUN MONITOR"
	title.theme_type_variation = "TitleRibbon"  # the sidebar's ribbon banner
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_font_size_override("font_size", 22)
	header.add_child(title)

	_collapse = Button.new()
	_collapse.text = "-"
	_collapse.tooltip_text = "Collapse the run monitor"
	# A fixed footprint (clip_text makes the minimum width exactly this box):
	# "-" and "+" have different glyph widths, and without this the swap would
	# nudge the header's minimum width — visibly shifting the whole panel.
	_collapse.custom_minimum_size = Vector2(40, 0)
	_collapse.clip_text = true
	_collapse.pressed.connect(_on_collapse_pressed)
	header.add_child(_collapse)

	# Everything below the header lives in _body so the collapse toggle can
	# hide it in one go; the panel then shrinks to just the header, because its
	# height comes from the content's minimum size (see the anchors above).
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 6)
	col.add_child(_body)

	# The status line ("Live · turn 42") the header dot is coloured for.
	_status = Label.new()
	_status.text = "starting…"
	_status.add_theme_font_size_override("font_size", 16)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_body.add_child(_status)

	# Small print naming the data source ("simulated (baked replay)" / the live
	# URL), so mock dollars are never mistaken for a real bill.
	_source_line = Label.new()
	_source_line.text = ""
	_source_line.add_theme_font_size_override("font_size", 14)
	_source_line.add_theme_color_override("font_color", MUTED_COLOR)
	_source_line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_body.add_child(_source_line)

	# The meter rows. Keys match what set_usage() computes.
	_add_row(_body, "calls", "Calls")
	_add_row(_body, "tokens_in", "Tokens in")
	_add_row(_body, "tokens_out", "Tokens out")
	_add_row(_body, "rate", "Tokens/min")
	_add_row(_body, "cost", "Cost")
	_budget_row = _add_row(_body, "budget", "Budget")
	_budget_row.visible = false  # only shown once a ceiling (#183) is reported

	_stop = Button.new()
	_stop.text = "Emergency stop"
	_stop.tooltip_text = "Pause the run and trip the cost kill-switch"
	_stop.add_theme_color_override("font_color", TRIPPED_COLOR)
	_stop.pressed.connect(func() -> void: stop_requested.emit())
	_body.add_child(_stop)


func _add_row(col: VBoxContainer, key: String, caption: String) -> HBoxContainer:
	# One "Caption ......... value" line; the value label is kept in _values.
	var row := HBoxContainer.new()
	var cap := Label.new()
	cap.text = caption
	cap.add_theme_font_size_override("font_size", 16)
	cap.add_theme_color_override("font_color", MUTED_COLOR)
	cap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(cap)
	var value := Label.new()
	value.text = "—"
	value.add_theme_font_size_override("font_size", 16)
	row.add_child(value)
	col.add_child(row)
	_values[key] = value
	return row


func _on_collapse_pressed() -> void:
	# Fold the details away (or bring them back): the header row -- dot, title,
	# this toggle -- is all that remains while collapsed, and the panel shrinks
	# to fit it. State keeps flowing into the hidden rows meanwhile, so
	# expanding again shows current numbers, not stale ones.
	_body.visible = not _body.visible
	_collapse.text = "-" if _body.visible else "+"
	_collapse.tooltip_text = (
		"Collapse the run monitor" if _body.visible else "Expand the run monitor"
	)


func set_source_label(text: String) -> void:
	## Name the feed ("simulated (baked replay)" or "live: <url>").
	_source_line.text = text


func set_health(state: int, detail: String) -> void:
	## Reflect the source's liveness (a hud_source.gd Health value + one line).
	_health_state = state
	_health_detail = detail
	_refresh_status()


func set_usage(summary: Dictionary) -> void:
	## Render a UsageLedger.summary()-shaped dict (see hud_source.gd for the
	## exact keys). Every read is defensive so a leaner /usage payload -- or a
	## richer future one -- degrades to "—" rather than a script error.
	var input := int(summary.get("input_tokens", 0))
	var output := int(summary.get("output_tokens", 0))
	var cache_write := int(summary.get("cache_creation_input_tokens", 0))
	var cache_read := int(summary.get("cache_read_input_tokens", 0))
	var prompt_total := input + cache_write + cache_read  # full prompt size
	var cost := float(summary.get("total_cost_usd", 0.0))

	_values["calls"].text = _fmt_int(int(summary.get("calls", 0)))
	_values["tokens_in"].text = _fmt_int(prompt_total)
	_values["tokens_out"].text = _fmt_int(output)
	_values["cost"].text = _fmt_usd(cost)
	_update_rate(prompt_total + output)

	# The ledger's cost ceiling (#183), when the source reports one. TRIPPED is
	# the kill-switch state -- spend has hit the ceiling (or Stop forced it).
	if summary.has("max_cost_usd") and summary["max_cost_usd"] != null:
		_budget_row.visible = true
		var ceiling := float(summary["max_cost_usd"])
		if bool(summary.get("over_budget", false)):
			_values["budget"].text = "TRIPPED"
			_values["budget"].add_theme_color_override("font_color", TRIPPED_COLOR)
		else:
			_values["budget"].text = "%s left" % _fmt_usd(maxf(0.0, ceiling - cost))
			_values["budget"].remove_theme_color_override("font_color")
	else:
		_budget_row.visible = false


func set_halted(halted: bool) -> void:
	## The source confirmed a stop (or a resume). The button disables while
	## halted -- there is nothing further to stop -- and Play (or the backend
	## resuming) brings it back.
	_halted = halted
	_stop.disabled = halted
	_stop.text = "Halted" if halted else "Emergency stop"
	_refresh_status()


func _refresh_status() -> void:
	if _halted:
		_dot.color = HALT_COLOR
		_status.text = "HALTED — run paused"
		return
	_dot.color = DOT_COLORS.get(_health_state, DOT_COLORS[3])
	var name: String = STATE_NAMES.get(_health_state, "?")
	_status.text = name if _health_detail == "" else "%s · %s" % [name, _health_detail]


func _update_rate(total_tokens: int) -> void:
	# Tokens/min over a sliding window of (time, cumulative-total) samples.
	# Derived here from whatever cadence the source updates at, so both the
	# simulated ticker and the live 2s poll get a rate for free.
	var now := Time.get_ticks_msec()
	_samples.append([now, total_tokens])
	while _samples.size() > 1 and now - _samples[0][0] > RATE_WINDOW_MS:
		_samples.pop_front()
	var span: int = now - _samples[0][0]
	if span < RATE_MIN_SPAN_MS:
		return  # keep the previous reading until the window is meaningful
	var delta: int = total_tokens - _samples[0][1]
	_values["rate"].text = _fmt_int(int(delta * 60000.0 / span))


func _fmt_int(n: int) -> String:
	# 1234567 -> "1,234,567" (Godot has no locale-aware number formatting).
	var s := str(n)
	var out := ""
	while s.length() > 3:
		out = "," + s.right(3) + out
		s = s.substr(0, s.length() - 3)
	return s + out


func _fmt_usd(x: float) -> String:
	# Four decimals below $10 (early-run costs are fractions of a cent), two
	# above (where the tail digits stop mattering).
	return ("$%.4f" if x < 10.0 else "$%.2f") % x
