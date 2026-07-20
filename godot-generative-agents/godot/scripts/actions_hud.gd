extends PanelContainer
## Top-right most-taken-actions panel (issue #700): a small ranked tally of the
## actions the cast has executed up to the current playhead. Pure UI, the same
## shape as live_hud.gd / minimap.gd -- viewer.gd computes the ranking
## (action_tally.gd) and pushes it here via set_rows(); this file only renders.
##
## In baked-replay mode it sits in the top-right corner, where the run monitor
## (live_hud.gd) would be -- but that panel is hidden without a live backend, so
## the corner is never double-booked. viewer.gd hides THIS panel in live mode
## for the same reason (see the v1 scope note on issue #700).

# Same footprint idiom as live_hud.gd: hug the top-right corner and grow
# downward as rows appear.
const PANEL_WIDTH := 210.0
const MARGIN := 16.0
# Muted small-print colour, matching the sidebar's status lines (readable on the
# Cute Fantasy parchment) -- same value live_hud.gd uses.
const MUTED_COLOR := Color(0.42, 0.32, 0.24)

var _rows_box: VBoxContainer


func _ready() -> void:
	# Pin to the top-right corner, growing downward as rows appear -- the same
	# anchor recipe as live_hud.gd. Anchors at (1, 0) make the offsets
	# corner-relative; the left/right pair fixes the width; the zero-height
	# top/bottom pair lets the content's minimum size (grow_vertical = END)
	# decide the height.
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

	var title := Label.new()
	title.text = "TOP ACTIONS"
	title.theme_type_variation = "TitleRibbon"  # the sidebar's ribbon banner
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 22)
	col.add_child(title)

	_rows_box = VBoxContainer.new()
	_rows_box.add_theme_constant_override("separation", 4)
	col.add_child(_rows_box)

	set_rows([])  # seed the empty state so the panel isn't blank before first data


func set_rows(rows: Array) -> void:
	## Render ranked [{action, count}, ...] as "verb ....... count" lines, or an
	## empty-state caption when there's nothing tallied yet. Rebuilds from scratch
	## each call -- the row set is tiny (top-N) and this only fires on a step
	## change, so a clean rebuild is simpler than diffing. free() is immediate, so
	## the old rows are gone before the new ones are added (no one-frame doubling).
	if _rows_box == null:
		_ready()
	for child in _rows_box.get_children():
		child.free()
	if rows.is_empty():
		var empty := Label.new()
		empty.text = "no actions yet"
		empty.add_theme_font_size_override("font_size", 14)
		empty.add_theme_color_override("font_color", MUTED_COLOR)
		_rows_box.add_child(empty)
		return
	for row in rows:
		var entry := row as Dictionary
		var line := HBoxContainer.new()
		var verb := Label.new()
		verb.text = String(entry.get("action", "?"))
		verb.add_theme_font_size_override("font_size", 16)
		verb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		line.add_child(verb)
		var count := Label.new()
		count.text = str(int(entry.get("count", 0)))
		count.add_theme_font_size_override("font_size", 16)
		line.add_child(count)
		_rows_box.add_child(line)
