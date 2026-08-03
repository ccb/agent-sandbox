extends PanelContainer
## Right-docked dialogue-log panel (#963): a scrollable, persistent history of
## every line spoken up to the playhead, so dialogue stays readable without
## slowing the bubbles (whose pacing the sim mirrors) or the agents. Pure UI,
## the same shape as actions_hud.gd -- viewer.gd extracts the rows
## (dialogue_log.gd) and pushes them here via set_rows(); this file only
## renders. Toggled with L or the sidebar's speech-bubble button; hidden by
## default. Works unchanged in replay, live, and the web export.

# A reading column against the right edge, between the top-right panel slot
# (actions_hud in replay / live_hud live) and the bottom-right minimap.
# ponytail: fixed clearances tuned to the 1920x1080 design canvas; compute
# from the neighbours' live rects if those panels ever grow.
const PANEL_WIDTH := 360.0
const MARGIN := 16.0
const TOP_CLEARANCE := 320.0
const BOTTOM_CLEARANCE := 260.0
# Muted small-print colour for the timestamps -- the shared parchment brown
# (see agent_panel.gd's STATUS_COLOR for why this exact value; contrast is
# pinned by tests/test_ui_contrast.gd).
const MUTED_COLOR := Color(0.32, 0.24, 0.17)

var _log: RichTextLabel
var _rows: Array = []  # the rows currently rendered


func _init() -> void:
	# Pin to the right edge, full height minus the corner neighbours' slots.
	anchor_left = 1.0
	anchor_top = 0.0
	anchor_right = 1.0
	anchor_bottom = 1.0
	offset_left = -(PANEL_WIDTH + MARGIN)
	offset_right = -MARGIN
	offset_top = TOP_CLEARANCE
	offset_bottom = -BOTTOM_CLEARANCE
	grow_horizontal = Control.GROW_DIRECTION_BEGIN

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 10)
	add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	margin.add_child(col)

	var title := Label.new()
	title.text = "DIALOGUE"
	title.theme_type_variation = "TitleRibbon"  # the sidebar's ribbon banner
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 22)
	col.add_child(title)

	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.scroll_active = true
	# Stick to the newest line UNLESS the reader has scrolled up -- Godot only
	# follows while the scrollbar sits at the end, so "pause on scrollback,
	# resume at the bottom" comes for free.
	_log.scroll_following = true
	_log.selection_enabled = true  # let the reader copy a quote
	_log.fit_content = false
	_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_log.add_theme_font_size_override("normal_font_size", 15)
	# Body colour comes from the theme's RichTextLabel/colors/default_color
	# (Godot's own default is white, invisible on the parchment panel).
	col.add_child(_log)

	set_rows([])  # seed the empty state so the panel isn't blank before data


func set_rows(rows: Array) -> void:
	## Render chronological [{time, speaker, line}, ...]. extract() output is
	## prefix-stable as the playhead advances, so the common step-change is an
	## append of the tail; anything else (backward scrub, a live backfill
	## rewriting frames) fails the prefix check and rebuilds from scratch --
	## the same rescan-truncation semantics the other accumulate-up-to panels
	## have ("the log DROPS when you scrub backward").
	if not _rows.is_empty() and rows.size() >= _rows.size() \
			and rows.slice(0, _rows.size()) == _rows:
		for i in range(_rows.size(), rows.size()):
			_append_row(rows[i])
	else:
		_log.clear()
		if rows.is_empty():
			_log.append_text(
				"[color=#%s]No dialogue yet.[/color]" % MUTED_COLOR.to_html(false))
		for r in rows:
			_append_row(r)
	_rows = rows.duplicate()


func _append_row(row: Dictionary) -> void:
	# "time  Speaker: line", one paragraph per utterance. speaker/line are LLM
	# prose -- neutralize "[" so a stray bracket can't corrupt the bbcode (the
	# live_hud request-log idiom).
	var speaker := String(row.get("speaker", "?")).replace("[", "[lb]")
	var line := String(row.get("line", "")).replace("[", "[lb]")
	_log.append_text(
		"[color=#%s]%s[/color]  [b]%s:[/b] %s\n"
		% [MUTED_COLOR.to_html(false), String(row.get("time", "")), speaker, line])
