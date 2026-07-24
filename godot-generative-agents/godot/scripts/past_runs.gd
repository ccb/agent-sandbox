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
const SETUP_SCENE := "res://scenes/simulation_setup.tscn"
const RunRow := preload("res://scripts/run_row.gd")
const ReplaySave := preload("res://scripts/replay_save.gd")

const HINT_COLOR := Color(0.42, 0.32, 0.24)
const ERROR_COLOR := Color(0.82, 0.20, 0.15)

var _url := ""
var _token := ""
var _http: HTTPRequest = null
var _pending := ""       # "" idle | "list" | "open" | "export" | "resume" | "delete" | "rerun"
var _pending_id := ""
var _pending_config := {}  # the saved config block for a pending "rerun" (#734)
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
		_set_busy(false)
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
	# One row: the summary label, the applied-config summary, the actions, and a
	# collapsible full-config detail (#734), then a separator.
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)

	var label := Label.new()
	label.text = RunRow.label(entry)
	label.add_theme_font_size_override("font_size", 14)
	box.add_child(label)

	# The run's applied config (#734): a compact summary always on the row, the
	# full block behind a toggle. `config` rides each GET /runs row (backend E5).
	var summary := Label.new()
	summary.text = RunRow.config_summary(entry)
	summary.add_theme_color_override("font_color", HINT_COLOR)
	summary.add_theme_font_size_override("font_size", 12)
	box.add_child(summary)

	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 6)
	box.add_child(actions)
	var id := String(entry.get("id", ""))
	# Each button routes through _on_row_action(op, id), which drives the shared
	# _http (one request at a time; see _set_busy).
	for spec in [["Open", "open"], ["Resume", "resume"], ["Export", "export"], ["Delete", "delete"]]:
		var b := Button.new()
		b.text = spec[0]
		b.focus_mode = Control.FOCUS_NONE
		var op: String = spec[1]
		b.pressed.connect(func() -> void: _on_row_action(op, id))
		actions.add_child(b)
		_row_buttons.append(b)

	# Config-bearing runs get "Re-run with this setup" + a detail toggle; a run
	# no one configured shows only the "no config recorded" summary above.
	if typeof(entry.get("config")) == TYPE_DICTIONARY:
		var config: Dictionary = entry["config"]
		var rerun := Button.new()
		rerun.text = "Re-run"
		rerun.focus_mode = Control.FOCUS_NONE
		rerun.pressed.connect(func() -> void: _on_rerun_pressed(id, config))
		actions.add_child(rerun)
		_row_buttons.append(rerun)

		var detail := Label.new()
		# Pretty-printed lazily on first reveal (#734 review follow-up): most rows
		# in a long history are never expanded, so don't stringify JSON up front.
		detail.add_theme_color_override("font_color", HINT_COLOR)
		detail.add_theme_font_size_override("font_size", 12)
		detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		detail.visible = false
		var toggle := Button.new()
		toggle.text = "Config ▾"
		toggle.focus_mode = Control.FOCUS_NONE
		# A local reveal, not a network action, so it stays clickable while a
		# request is in flight (kept out of _row_buttons / _set_busy).
		toggle.pressed.connect(func() -> void:
			if detail.text == "":
				detail.text = RunRow.config_detail(entry)
			detail.visible = not detail.visible
			toggle.text = "Config ▴" if detail.visible else "Config ▾")
		actions.add_child(toggle)
		box.add_child(detail)

	var sep := HSeparator.new()
	box.add_child(sep)
	return box


func _on_row_action(op: String, id: String) -> void:
	if _pending != "" or _switching or id == "":
		return
	_pending = op
	_pending_id = id
	_set_busy(true)
	var err := OK
	match op:
		"open", "export":
			_set_status("Fetching replay for %s…" % id, false)
			err = _http.request("%s/runs/%s/replay" % [_url, id], _headers())
		"resume":
			_set_status("Resuming %s…" % id, false)
			err = _http.request("%s/runs/%s/resume" % [_url, id], _headers(),
				HTTPClient.METHOD_POST, "{}")
		"delete":
			_set_status("Deleting %s…" % id, false)
			err = _http.request("%s/runs/%s" % [_url, id], _headers(),
				HTTPClient.METHOD_DELETE)
	if err != OK:
		_pending = ""
		_set_busy(false)
		_set_status("Couldn't start the %s request (error %d)." % [op, err], true)


func _on_rerun_pressed(id: String, config: Dictionary) -> void:
	# "Re-run with this setup" (#734): confirm the connected backend is a fresh,
	# configurable one (paused at tick 0), then hand the saved config to the
	# Simulation Setup scene as a seed. Same inline-error UX as the row actions:
	# a non-configurable backend reports and stays put.
	if _pending != "" or _switching or id == "":
		return
	_pending = "rerun"
	_pending_id = id
	_pending_config = config
	_set_busy(true)
	_set_status("Checking %s can start a fresh run…" % _url, false)
	var err := _http.request("%s/config" % _url, _headers())
	if err != OK:
		_pending = ""
		_set_busy(false)
		_set_status("Couldn't start the re-run request (error %d)." % err, true)


func _on_http_completed(
	result: int, code: int, _headers_in: PackedStringArray, body: PackedByteArray
) -> void:
	var stage := _pending
	var id := _pending_id
	_pending = ""
	_pending_id = ""
	# A transport failure (unreachable backend, timeout) arrives with code == 0.
	# No stage has switched scenes yet, so uniformly unfreeze + report and stop.
	if result != HTTPRequest.RESULT_SUCCESS:
		_set_busy(false)
		_set_status("Couldn't reach the backend (down or timed out).", true)
		return
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
		"open":
			if code != 200:
				_set_busy(false)
				_set_status("Open failed (HTTP %d)." % code, true)
				return
			# Hand the RAW replay body to the viewer (byte-preserving); the scene
			# swap tears us down, so no need to clear _busy.
			LaunchConfig.set_replay_text(body.get_string_from_utf8())
			_switching = true
			get_tree().change_scene_to_file.call_deferred(VIEWER_SCENE)
		"export":
			_set_busy(false)
			if code != 200:
				_set_status("Export failed (HTTP %d)." % code, true)
				return
			var path := ReplaySave.save(body.get_string_from_utf8(), id)
			if path == "":
				_set_status("Export failed — see console.", true)
			elif OS.has_feature("web"):
				_set_status("Downloaded %s." % path, false)
			else:
				_set_status("Exported → %s" % path, false)
		"resume":
			if code >= 200 and code < 300:
				# Adopted as the live run: follow it live, exactly like the menu's
				# Connect flow. LaunchConfig keeps the URL + token we came in with.
				LaunchConfig.set_live(_url, _token)
				_switching = true
				get_tree().change_scene_to_file.call_deferred(VIEWER_SCENE)
			else:
				_set_busy(false)
				var why := "already live" if code == 409 else "HTTP %d" % code
				_set_status("Resume failed (%s)." % why, true)
		"delete":
			_set_busy(false)
			if code >= 200 and code < 300:
				_set_status("Deleted %s." % id, false)
				_fetch_runs()  # refresh the list
			elif code == 409:
				_set_status("Can't delete %s — it's the live run; stop it first." % id, true)
			else:
				_set_status("Delete failed (HTTP %d)." % code, true)
		"rerun":
			if code != 200:
				_set_busy(false)
				var why := "no config surface" if code == 404 else "HTTP %d" % code
				_set_status("Can't re-run here — this backend has %s. Connect to a fresh paused backend." % why, true)
				return
			var data: Variant = JSON.parse_string(body.get_string_from_utf8())
			if typeof(data) != TYPE_DICTIONARY \
					or str((data as Dictionary).get("status", "")) != "configurable":
				_set_busy(false)
				_set_status("Can't re-run here — this backend already started its run. Connect to a fresh paused backend.", true)
				return
			# Configurable: seed the setup scene and hand off. The scene swap
			# tears us down, so no need to clear _busy.
			LaunchConfig.setup_seed = _pending_config
			_switching = true
			get_tree().change_scene_to_file.call_deferred(SETUP_SCENE)
		_:
			_set_busy(false)


func _on_back_pressed() -> void:
	if _switching:
		return
	_switching = true
	get_tree().change_scene_to_file.call_deferred(MENU_SCENE)
