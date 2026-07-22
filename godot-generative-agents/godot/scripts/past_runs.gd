extends Control
## Past-runs browser (issue #716): a landing-menu screen that lists the backend's
## stored runs (GET /runs) and offers per-row open / resume / export / delete.
##
## Reached from main_menu.gd's "Past runs ▸" button, which stashes the backend URL
## + token in LaunchConfig (last_live_url / live_token) before switching here. Row
## actions hand off through LaunchConfig the same way the menu does:
##   open   -> GET /runs/{id}/replay -> LaunchConfig.set_replay_text -> viewer
##   resume -> POST /runs/{id}/resume -> LaunchConfig.set_live -> viewer (follow live)
##   export -> GET /runs/{id}/replay -> ReplaySave.save (disk / download)
##   delete -> DELETE /runs/{id} -> re-list
##
## One HTTPRequest node, one request at a time: while a request is in flight every
## row button is disabled (_set_busy), so a Godot one-shot HTTPRequest is never
## asked to run two overlapping calls.

const VIEWER_SCENE := "res://scenes/viewer.tscn"
const MENU_SCENE := "res://scenes/main_menu.tscn"
const RunRow := preload("res://scripts/run_row.gd")
const ReplaySave := preload("res://scripts/replay_save.gd")

const HINT_COLOR := Color(0.42, 0.32, 0.24)
const ERROR_COLOR := Color(0.82, 0.20, 0.15)

var _url := ""
var _token := ""
var _http: HTTPRequest = null
var _pending := ""       # "" idle | "list" | "open" | "export" | "resume" | "delete"
var _pending_id := ""
var _rows_box: VBoxContainer = null
var _status: Label = null
var _row_buttons: Array[Button] = []  # every row-action button, for _set_busy
var _switching := false


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_url = LaunchConfig.last_live_url.rstrip("/")
	_token = LaunchConfig.live_token
	_build_ui()
	_http = HTTPRequest.new()
	_http.timeout = 10.0
	_http.request_completed.connect(_on_http_completed)
	add_child(_http)
	_fetch_runs()


func _build_ui() -> void:
	var base := ColorRect.new()
	base.color = Color(0.18, 0.20, 0.24)
	base.set_anchors_preset(Control.PRESET_FULL_RECT)
	base.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(base)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(center)

	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(640, 0)
	center.add_child(panel)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	panel.add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	margin.add_child(col)

	var title := Label.new()
	title.text = "PAST RUNS"
	title.theme_type_variation = "TitleRibbon"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_font_size_override("font_size", 30)
	col.add_child(title)

	var backend := Label.new()
	backend.text = _url if _url != "" else "(no backend URL — go back and connect first)"
	backend.add_theme_color_override("font_color", HINT_COLOR)
	backend.add_theme_font_size_override("font_size", 14)
	col.add_child(backend)

	# The scrolling list of rows, capped so a long history stays on screen.
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(0, 360)
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_child(scroll)
	_rows_box = VBoxContainer.new()
	_rows_box.add_theme_constant_override("separation", 6)
	_rows_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_rows_box)

	_status = Label.new()
	_status.text = ""
	_status.add_theme_color_override("font_color", HINT_COLOR)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	col.add_child(_status)

	var back := Button.new()
	back.text = "‹ Back to menu"
	back.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	back.pressed.connect(_on_back_pressed)
	col.add_child(back)


func _set_status(text: String, is_error: bool) -> void:
	_status.text = text
	_status.add_theme_color_override("font_color", ERROR_COLOR if is_error else HINT_COLOR)


func _set_busy(busy: bool) -> void:
	# One request at a time: freeze every row action while one is in flight.
	for b in _row_buttons:
		b.disabled = busy


func _headers() -> PackedStringArray:
	var h := PackedStringArray(["Content-Type: application/json"])
	if _token != "":
		h.append("Authorization: Bearer %s" % _token)
	return h


func _fetch_runs() -> void:
	if _url == "":
		_set_status("No backend URL. Go back, enter one under “Run a live simulation”, then reopen Past runs.", true)
		return
	if _pending != "":
		return
	_pending = "list"
	_set_status("Loading runs from %s…" % _url, false)
	_set_busy(true)
	var err := _http.request("%s/runs" % _url, _headers())
	if err != OK:
		_pending = ""
		_set_status("Couldn't start the request (error %d)." % err, true)


func _render(runs: Array) -> void:
	for child in _rows_box.get_children():
		child.queue_free()
	_row_buttons.clear()
	if runs.is_empty():
		_set_status("No stored runs on this backend yet.", false)
		return
	_set_status("%d run(s)." % runs.size(), false)
	for entry in runs:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		_rows_box.add_child(_build_row(entry as Dictionary))


func _build_row(entry: Dictionary) -> Control:
	# One row: the formatted label on its own line, the four actions below it.
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)

	var label := Label.new()
	label.text = RunRow.label(entry)
	label.add_theme_font_size_override("font_size", 14)
	box.add_child(label)

	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 6)
	box.add_child(actions)
	var id := String(entry.get("id", ""))
	# Row-action buttons are wired in Task 7; here they exist (so the scene builds
	# and the smoke test sees buttons) but only report "not wired yet".
	for spec in [["Open", "open"], ["Resume", "resume"], ["Export", "export"], ["Delete", "delete"]]:
		var b := Button.new()
		b.text = spec[0]
		b.focus_mode = Control.FOCUS_NONE
		var op: String = spec[1]
		b.pressed.connect(func() -> void: _on_row_action(op, id))
		actions.add_child(b)
		_row_buttons.append(b)

	var sep := HSeparator.new()
	box.add_child(sep)
	return box


func _on_row_action(_op: String, _id: String) -> void:
	# Filled in Task 7.
	_set_status("(action wiring lands in Task 7)", false)


func _on_http_completed(
	_result: int, code: int, _headers_in: PackedStringArray, body: PackedByteArray
) -> void:
	var stage := _pending
	_pending = ""
	match stage:
		"list":
			_set_busy(false)
			if code != 200:
				_set_status("GET /runs failed (HTTP %d)." % code, true)
				return
			var data: Variant = JSON.parse_string(body.get_string_from_utf8())
			if typeof(data) != TYPE_DICTIONARY:
				_set_status("GET /runs returned an unexpected body.", true)
				return
			if not bool((data as Dictionary).get("available", false)):
				_render([])
				_set_status("This backend isn't persisting runs (start it without --no-persist).", true)
				return
			_render((data as Dictionary).get("runs", []))
		_:
			pass  # other stages handled in Task 7


func _on_back_pressed() -> void:
	if _switching:
		return
	_switching = true
	get_tree().change_scene_to_file.call_deferred(MENU_SCENE)
