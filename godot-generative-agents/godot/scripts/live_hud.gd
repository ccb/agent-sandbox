extends PanelContainer
## Top-right run monitor: cost meter + backend health + Emergency Stop (issue #264).
##
## A live real-LLM run spends money every step and can stall on the provider;
## this small HUD makes spend and liveness visible and gives the operator a
## one-click stop. It is pure UI, in the same shape as agent_panel.gd and
## minimap.gd: it knows nothing about backends or replays. viewer.gd wires
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

const Money := preload("res://scripts/money.gd")

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
# The request log under the meter rows: one compact line per LLM call, newest
# at the bottom -- the in-viewer twin of backend/llm_monitor.py's terminal
# rows. The panel is narrow, so each row keeps only timestamp, role, actor and
# tokens/cost; hovering a row shows the full terminal-style detail.
const LOG_HEIGHT := 108.0
const LOG_MAX_ROWS := 40
const LOG_FONT_SIZE := 12
# The terminal monitor's role colours (cyan/magenta/blue/green), darkened to
# stay readable on the parchment theme.
const LOG_ROLE_TINTS := {
	"decide": Color(0.10, 0.42, 0.48),
	"converse": Color(0.55, 0.18, 0.45),
	"plan": Color(0.17, 0.29, 0.56),
	"reflect": Color(0.18, 0.45, 0.18),
}
# The wish row's tint (#622, surfaced #625): the same rose-pink as
# timeline_markers.gd's KIND_COLORS["wish"], so a demand-signal record reads
# as the same color in both the live request log and the baked-replay strip.
const WISH_TINT := Color("d9569f")

var _dot: ColorRect
var _status: Label
var _source_line: Label
var _body: VBoxContainer  # everything below the header; hidden when collapsed
var _collapse: Button     # the header's collapse/expand toggle
var _values := {}       # row key -> value Label (see _add_row)
var _budget_row: HBoxContainer
var _log: RichTextLabel
var _log_rows := PackedStringArray()  # formatted bbcode rows, capped
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

	# The request log: every llm_call record the source emits becomes one row
	# (see add_llm_call). It lives inside _body, so the collapse toggle folds
	# it away with the rest of the meter.
	var log_caption := Label.new()
	log_caption.text = "LLM requests"
	log_caption.add_theme_font_size_override("font_size", 16)
	log_caption.add_theme_color_override("font_color", MUTED_COLOR)
	_body.add_child(log_caption)

	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.scroll_active = true
	_log.scroll_following = true  # stick to the newest row, like a terminal
	_log.autowrap_mode = TextServer.AUTOWRAP_OFF  # one call = one (clipped) line
	_log.clip_contents = true
	_log.fit_content = false
	_log.custom_minimum_size = Vector2(0, LOG_HEIGHT)
	_log.add_theme_font_size_override("normal_font_size", LOG_FONT_SIZE)
	# The Cute Fantasy theme styles Labels but not RichTextLabel, whose default
	# font colour is white -- unreadable on the parchment panel.
	_log.add_theme_color_override("default_color", Color(0.24, 0.18, 0.12))
	_log.text = "[color=#8a7660]no requests yet[/color]"
	_body.add_child(_log)

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
	_values["cost"].text = Money.usd(cost)
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
			_values["budget"].text = "%s left" % Money.usd(maxf(0.0, ceiling - cost))
			_values["budget"].remove_theme_color_override("font_color")
	else:
		_budget_row.visible = false


func add_llm_call(rec: Dictionary) -> void:
	## Append one row to the request log: an llm_call record from the source
	## (see hud_source.gd for the shape -- the same record the backend's
	## terminal monitor prints). The row keeps only what fits the narrow panel
	## (timestamp, role, actor, tokens in→out, cost); hover it for the full
	## detail (call #, sim turn, model, cache split, latency, cumulative spend).
	var role := String(rec.get("role", "?"))
	var actor: String = (
		String(rec.get("actor")) if rec.get("actor") != null else "-"
	)
	# Surname only in the row ("Diego Torres" -> "Torres"): the full name is
	# one hover away, and the column must fit next to the token counts.
	var short_actor := actor.get_slice(" ", actor.get_slice_count(" ") - 1)
	var tokens_in := (
		_log_int(rec.get("input_tokens"))
		+ _log_int(rec.get("cache_creation_input_tokens"))
		+ _log_int(rec.get("cache_read_input_tokens"))
	)
	var tokens_out := _log_int(rec.get("output_tokens"))
	var cost := _log_float(rec.get("cost_usd"))
	var tint: Color = LOG_ROLE_TINTS.get(role, MUTED_COLOR)
	var hint := "call %d · t %s · %s · in %d (%dw/%dr cache) · out %d · %s · $%.6f this call · Σ $%.4f" % [
		_log_int(rec.get("call_no")),
		str(_log_int(rec.get("turn"))) if rec.get("turn") != null else "-",
		"%s · %s" % [actor, String(rec.get("model", "?"))],
		tokens_in,
		_log_int(rec.get("cache_creation_input_tokens")),
		_log_int(rec.get("cache_read_input_tokens")),
		tokens_out,
		(
			"%.0f ms" % _log_float(rec.get("latency_ms"))
			if rec.get("latency_ms") != null
			else "- ms"
		),
		cost,
		_log_float(rec.get("cum_cost_usd")),
	]
	# Timestamp (muted) leads each row, like the terminal monitor; the call
	# number is hover detail only.
	var line := "[hint=%s][color=#8a7660]%s[/color] [color=#%s]%s[/color] %s %s→%s $%.4f[/hint]" % [
		hint,
		String(rec.get("time", "-")),
		tint.to_html(false),
		role,
		short_actor,
		_fmt_tok(tokens_in),
		_fmt_tok(tokens_out),
		cost,
	]
	_push_row(line)


func add_engine_event(event: Dictionary) -> void:
	## Append one row for a non-`llm_call` engine change-feed record (#394): the
	## JSONRenderer events serve_penn drains (narration, blocked, ...) that ride
	## the same feed as llm_calls but the viewer used to drop on the floor. Renders
	## a compact "turn · channel · text" row in the same event log. bbcode in the
	## prose is neutralized so a stray "[" can't corrupt the RichTextLabel.
	var text := String(event.get("text", "")).strip_edges().replace("\n", " ")
	if text.is_empty():
		# game_event rows (#467) carry their prose in `summary`, not `text` —
		# fall back so the run record renders instead of vanishing (#502).
		text = String(event.get("summary", "")).strip_edges().replace("\n", " ")
	if text.is_empty():
		return
	if text.length() > 80:
		text = text.substr(0, 79) + "…"
	text = text.replace("[", "[lb]")
	# game_event rows carry no `channel`; label them by their record kind so the
	# row reads "t42 · game_event · <summary>" rather than a generic "event".
	var channel := String(event.get("channel", event.get("kind", "event")))
	var turn: Variant = event.get("turn")
	var when := "t%s" % str(turn) if turn != null else "-"
	_push_row(
		(
			"[hint=%s · %s][color=#8a7660]%s[/color] [color=#%s]%s[/color] %s[/hint]"
			% [channel, when, when, MUTED_COLOR.to_html(false), channel, text]
		)
	)


func add_wish(rec: Dictionary) -> void:
	## Append one row for an ActionWish demand-signal record (#622, surfaced
	## #625): the actor wanted an action the game doesn't have (a deliberate
	## `propose`, or an unparsed command). The compact row shows the 💭 marker
	## + actor + a clipped `desired`; hovering reveals desired + reason +
	## trigger in full -- the same "hint = full detail" idiom add_llm_call and
	## add_engine_event use. desired/reason are free text (an LLM composed
	## them), so brackets are neutralized before either lands in bbcode: a
	## stray "[" in the row, or a stray "]" in the hint attribute (which would
	## close the `[hint=...]` tag early), must not corrupt the RichTextLabel.
	var desired := _wish_field(rec, "desired")
	if desired.is_empty():
		return
	var reason := _wish_field(rec, "reason")
	var trigger := String(rec.get("trigger", "")).strip_edges()
	var actor := String(rec.get("actor")) if rec.get("actor") != null else "-"
	var turn: Variant = rec.get("turn")
	var when := "t%s" % str(turn) if turn != null else "-"
	var clipped := desired if desired.length() <= 60 else desired.substr(0, 59) + "…"
	var hint := "%s wishes (%s) · %s: %s" % [actor, trigger, when, desired]
	if not reason.is_empty():
		hint += " — because %s" % reason
	_push_row(
		(
			"[hint=%s][color=#8a7660]%s[/color] [color=#%s]💭 wish[/color] %s: %s[/hint]"
			% [_bracket_safe(hint), when, WISH_TINT.to_html(false), actor, clipped.replace("[", "[lb]")]
		)
	)


func _wish_field(rec: Dictionary, key: String) -> String:
	return String(rec.get(key, "")).strip_edges().replace("\n", " ")


func _bracket_safe(text: String) -> String:
	# Free text embedded in a [hint=...] attribute value must not carry an
	# unescaped "]" -- it would close the tag early, garbling the row.
	return text.replace("[", "(").replace("]", ")")


func _push_row(line: String) -> void:
	## Append a formatted bbcode row to the event log — newest at the bottom,
	## capped at LOG_MAX_ROWS. Shared by add_llm_call and add_engine_event (#394).
	_log_rows.append(line)
	if _log_rows.size() > LOG_MAX_ROWS:
		_log_rows = _log_rows.slice(_log_rows.size() - LOG_MAX_ROWS)
	_log.text = "\n".join(_log_rows)


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


func _fmt_tok(n: int) -> String:
	# 12345 -> "12.3k": log-row token counts must fit the narrow panel.
	return str(n) if n < 1000 else "%.1fk" % (n / 1000.0)


func _log_int(v: Variant) -> int:
	# JSON numbers arrive as floats and optional fields as null -- never feed
	# int() a null.
	return int(v) if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT else 0


func _log_float(v: Variant) -> float:
	return float(v) if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT else 0.0
