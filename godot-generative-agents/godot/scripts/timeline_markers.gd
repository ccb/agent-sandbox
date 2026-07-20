extends Control
## The event-marker strip above the timeline scrubber (issue #249): one thin
## colored tick per "interesting moment" (game event / chat onset / reflection /
## arrival / wish), aligned to the scrubber's 0..total frame axis. Clicking seeks
## (the panel routes marker_clicked into its seek_requested); hovering names the
## nearest moments via the dynamic tooltip. Pure UI: agent_panel.gd feeds it via
## set_markers()/set_filter() and it knows nothing about the sim.

## The user clicked the strip: seek to `step` (nearest marker within SNAP_PX,
## else the step under the cursor).
signal marker_clicked(step: int)

# Tick colors by marker kind. Red matches the sidebar's LIVE-badge red; blue and
# green are the Cute Fantasy pack's own (the graph glyph's node blue, the gallery
# glyph's hill green) so the strip doesn't look foreign on the parchment theme.
# wish (#622, surfaced #625) gets its own rose-pink -- distinct from every other
# tick color already on the strip (see test_replay_markers.gd's _far checks).
const KIND_COLORS := {
	"event": Color(0.82, 0.20, 0.15),
	"chat": Color("0099db"),
	"reflection": Color("7b4fbe"),
	"arrival": Color("3e8948"),
	"wish": Color("d9569f"),
}
# Per-event-type signature (issue #593): a game event's `action` picks a color +
# a hover emoji so the boil-water arc reads at a glance. The colors are chosen to
# stay clear of the other tick kinds already on the strip: sickness is a deep
# crimson (NOT the default event red the lifecycle go/perform/travel ticks use),
# boiled is amber, recovery is a teal (NOT the arrival green). Unknown action
# types still fall back to the default event red so new events render. (#302,
# still unbuilt as of #625, would add `code_rewrite` here.)
const EVENT_STYLE := {
	"sickness": {"color": Color("b3122b"), "emoji": "🤢"},   # crimson
	"boiled": {"color": Color(0.95, 0.65, 0.15), "emoji": "🍵"},  # amber
	"recovery": {"color": Color("1fa8a0"), "emoji": "💚"},   # teal
}


## The tick color for a marker of the given kind/action. Events resolve by
## action via EVENT_STYLE (default event red for unknown types); every other
## kind resolves by KIND_COLORS (white for an unknown kind). Static + pure so
## the mapping is unit-testable without a scene (tests/test_replay_markers.gd).
static func color_for(kind: String, action: String) -> Color:
	if kind == "event":
		return EVENT_STYLE.get(action, {}).get("color", KIND_COLORS["event"])
	return KIND_COLORS.get(kind, Color.WHITE)


## The hover tooltip line for one marker. A known event type is prefixed with
## its emoji + type name ("step 945 — 🤢 sickness — Sofia: got sick"); every
## other marker keeps the plain "step N — <label>". Static + pure (testable).
static func tooltip_line(marker: Dictionary) -> String:
	var step := int(marker.get("step", 0))
	var label := String(marker.get("label", ""))
	if String(marker.get("kind", "")) == "event":
		var action := String(marker.get("action", ""))
		if EVENT_STYLE.has(action):
			return "step %d — %s %s — %s" % [step, EVENT_STYLE[action]["emoji"], action, label]
	return "step %d — %s" % [step, label]
const STRIP_HEIGHT := 10       # px; thin, sits directly above the HSlider
const TICK_HALF_WIDTH := 1     # ticks are 2px wide
const SNAP_PX := 4.0           # click/hover snap radius to the nearest marker

var _markers: Array = []       # all collected markers (replay_markers.gd shape)
var _visible_markers: Array = []  # after the agent filter
var _total := 0                # last frame index (the scrubber's max_value)
var _filter := ""              # "" = all agents; else only this agent's markers
var _clip_a := -1              # marked clip span (issue #488); -1 = unset
var _clip_b := -1


func _ready() -> void:
	custom_minimum_size = Vector2(0, STRIP_HEIGHT)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND


func set_markers(markers: Array, total: int) -> void:
	_markers = markers
	_total = total
	_apply_filter()


func set_filter(agent: String) -> void:
	if agent == _filter:
		return
	_filter = agent
	_apply_filter()


func set_clip_span(a: int, b: int) -> void:
	_clip_a = a
	_clip_b = b
	queue_redraw()


func _apply_filter() -> void:
	if _filter == "":
		_visible_markers = _markers
	else:
		_visible_markers = _markers.filter(func(m: Dictionary) -> bool:
			return String(m["agent"]) == _filter)
	queue_redraw()


func _draw() -> void:
	if _total <= 0:
		return
	if _clip_a >= 0 and _clip_b >= _clip_a:
		var x0 := _step_to_x(_clip_a)
		var x1 := _step_to_x(_clip_b)
		draw_rect(Rect2(x0, 0, maxf(x1 - x0, 2.0), size.y), Color(1.0, 0.85, 0.30, 0.35))
	for m in _visible_markers:
		var x := _step_to_x(int(m["step"]))
		draw_rect(Rect2(x - TICK_HALF_WIDTH, 0, TICK_HALF_WIDTH * 2, size.y),
			color_for(String(m["kind"]), String(m.get("action", ""))))


func _gui_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton and event.pressed
			and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT):
		return
	if _total <= 0:
		return
	var x := (event as InputEventMouseButton).position.x
	var nearest := _nearest_markers(x, 1)
	var step := int(nearest[0]["step"]) if not nearest.is_empty() \
		else clampi(roundi(x / size.x * _total), 0, _total)
	marker_clicked.emit(step)
	accept_event()


func _get_tooltip(at_position: Vector2) -> String:
	# Dynamic tooltip: the labels of up to 3 markers within snap range.
	var lines := PackedStringArray()
	for m in _nearest_markers(at_position.x, 3):
		lines.append(tooltip_line(m))
	return "\n".join(lines)


func _step_to_x(step: int) -> float:
	return step / float(_total) * size.x


func _nearest_markers(x: float, count: int) -> Array:
	# The visible markers within SNAP_PX of x, nearest first, at most `count`.
	var near := _visible_markers.filter(func(m: Dictionary) -> bool:
		return absf(_step_to_x(int(m["step"])) - x) <= SNAP_PX)
	near.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return absf(_step_to_x(int(a["step"])) - x) < absf(_step_to_x(int(b["step"])) - x))
	return near.slice(0, count)
