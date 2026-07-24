extends Control
## Simulation Setup scene (issue #733): the pre-run config screen. Reached from
## main_menu.gd when its connect probe finds a backend paused at tick 0 that
## reports GET /config status "configurable". Pick the cast, tweak sim knobs,
## set run controls, then Start -- POST /config, POST /resume, into the viewer
## following the now-running sim.
##
## Patterns from past_runs.gd (#716): LaunchConfig hand-off (last_live_url /
## live_token in, set_live out), ONE HTTPRequest driven as a small state machine
## (_pending), every control frozen while a request is in flight (_set_busy),
## back-to-menu via a scene swap.
##
## The form is populated ENTIRELY from GET /config -- persona catalog, knob
## defaults/current, advertised brains and run defaults all come from the
## server, so this scene hard-codes no cast and no brain list. The POST body is
## built by config_body.gd (unit-tested in tests/test_simulation_setup.gd).

const VIEWER_SCENE := "res://scenes/viewer.tscn"
const MENU_SCENE := "res://scenes/main_menu.tscn"
const ConfigBody := preload("res://scripts/config_body.gd")

const HINT_COLOR := Color(0.42, 0.32, 0.24)
const ERROR_COLOR := Color(0.82, 0.20, 0.15)

# The curated sim knobs this scene exposes, mapped to their (section, key) path
# in GET /config's `knobs` block: retrieval weights, vision, conversation
# pacing -- the subset the issue calls out. (Temperature lives under game.llm,
# which the config surface strips as key-bearing, so it isn't offered here;
# exposing it would be a #732 backend follow-up.)
const KNOBS := [
	{"label": "Recency weight", "section": "retrieval", "key": "alpha_recency", "kind": "float"},
	{"label": "Importance weight", "section": "retrieval", "key": "alpha_importance", "kind": "float"},
	{"label": "Relevance weight", "section": "retrieval", "key": "alpha_relevance", "kind": "float"},
	{"label": "Vision radius (tiles)", "section": "cognition", "key": "vision_r", "kind": "int"},
	{"label": "Conversation cooldown (steps)", "section": "cognition", "key": "conversation_cooldown_steps", "kind": "int"},
	{"label": "Max exchanges / conversation", "section": "cognition", "key": "conversation_max_exchanges", "kind": "int"},
]

var _url := ""
var _token := ""
var _http: HTTPRequest = null
var _pending := ""  # "" idle | "load" | "config" | "resume"
var _switching := false

# UI, built once GET /config arrives.
var _form_box: VBoxContainer = null
var _status: Label = null
var _start_btn: Button = null
var _persona_checks: Array = []  # [{id, cb}]
var _knob_rows: Array = []       # [{section, key, kind, spin, initial}]
var _brain_opt: OptionButton = null
var _steps_spin: SpinBox = null
var _tick_spin: SpinBox = null
var _cost_spin: SpinBox = null

# Server state captured from GET /config, needed to build the POST body.
var _brains: Array = []
var _knobs_current: Dictionary = {}
var _knobs_defaults: Dictionary = {}
var _initial := {"brain": "mock", "steps": 0, "tick_seconds": 0.0, "max_cost": 0.0}


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_url = LaunchConfig.last_live_url.rstrip("/")
	_token = LaunchConfig.live_token
	_build_shell()
	_http = HTTPRequest.new()
	_http.timeout = 10.0
	_http.request_completed.connect(_on_http_completed)
	add_child(_http)
	_fetch_config()


func _build_shell() -> void:
	var base := ColorRect.new()
	base.color = Color(0.18, 0.20, 0.24)
	base.set_anchors_preset(Control.PRESET_FULL_RECT)
	base.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(base)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(center)

	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(560, 0)
	center.add_child(panel)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	panel.add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	margin.add_child(col)

	var title := Label.new()
	title.text = "SIMULATION SETUP"
	title.theme_type_variation = "TitleRibbon"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_font_size_override("font_size", 30)
	col.add_child(title)

	var backend := Label.new()
	backend.text = _url if _url != "" else "(no backend URL -- go back and connect first)"
	backend.add_theme_color_override("font_color", HINT_COLOR)
	backend.add_theme_font_size_override("font_size", 14)
	col.add_child(backend)

	# The form (personas + knobs + run controls) is filled once GET /config
	# lands; a ScrollContainer keeps a full cast + knob list on screen.
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(0, 360)
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_child(scroll)
	_form_box = VBoxContainer.new()
	_form_box.add_theme_constant_override("separation", 6)
	_form_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_form_box)

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.add_theme_color_override("font_color", HINT_COLOR)
	col.add_child(_status)

	_start_btn = Button.new()
	_start_btn.text = "▶  Start the simulation"
	_start_btn.disabled = true  # enabled once a configurable /config lands
	_start_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_start_btn.pressed.connect(_on_start_pressed)
	col.add_child(_start_btn)

	var back := Button.new()
	back.text = "‹ Back to menu"
	back.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	back.pressed.connect(_on_back_pressed)
	col.add_child(back)


func _section_label(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.theme_type_variation = "TitleRibbon"
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.add_theme_font_size_override("font_size", 18)
	return l


func _set_status(text: String, is_error: bool) -> void:
	_status.text = text
	_status.add_theme_color_override("font_color", ERROR_COLOR if is_error else HINT_COLOR)


func _set_busy(busy: bool) -> void:
	# One request at a time: freeze every control while a request is in flight.
	# Start stays disabled until a configurable /config has built the cast.
	_start_btn.disabled = busy or _persona_checks.is_empty()
	for row in _knob_rows:
		row.spin.editable = not busy
	for p in _persona_checks:
		p.cb.disabled = busy
	if _brain_opt != null:
		_brain_opt.disabled = busy
	if _steps_spin != null:
		_steps_spin.editable = not busy
	if _tick_spin != null:
		_tick_spin.editable = not busy
	if _cost_spin != null:
		_cost_spin.editable = not busy


func _headers() -> PackedStringArray:
	var h := PackedStringArray(["Content-Type: application/json"])
	if _token != "":
		h.append("Authorization: Bearer %s" % _token)
	return h


func _fetch_config() -> void:
	if _url == "":
		_set_status("No backend URL. Go back, connect under “Run a live simulation”, then reconnect.", true)
		return
	_pending = "load"
	_set_status("Loading configuration from %s…" % _url, false)
	var err := _http.request("%s/config" % _url, _headers())
	if err != OK:
		_pending = ""
		_set_status("Couldn't start the request (error %d)." % err, true)


func _on_http_completed(
	result: int, code: int, _headers_in: PackedStringArray, body: PackedByteArray
) -> void:
	if _switching:
		return
	var stage := _pending
	_pending = ""
	# A transport failure (unreachable backend, timeout) arrives with code == 0.
	if result != HTTPRequest.RESULT_SUCCESS:
		_set_busy(false)
		_set_status("Couldn't reach the backend (down or timed out).", true)
		return
	match stage:
		"load":
			if code == 404:
				_set_status("This backend has no config surface -- go back and open it in the viewer.", true)
				return
			if code != 200:
				_set_status("GET /config failed (HTTP %d)." % code, true)
				return
			var data: Variant = JSON.parse_string(body.get_string_from_utf8())
			if typeof(data) != TYPE_DICTIONARY:
				_set_status("GET /config returned an unexpected body.", true)
				return
			if str((data as Dictionary).get("status", "")) != "configurable":
				_set_status("This run has already started -- go back and connect to a fresh paused backend.", true)
				return
			_render_config(data as Dictionary)
		"config":
			var detail := _detail(body)
			if code >= 200 and code < 300:
				# Config applied; now start the run.
				_pending = "resume"
				_set_status("Starting the run…", false)
				var err := _http.request("%s/resume" % _url, _headers(), HTTPClient.METHOD_POST, "{}")
				if err != OK:
					_pending = ""
					_set_busy(false)
					_set_status("Couldn't start the resume request (error %d)." % err, true)
				return
			_set_busy(false)
			if code == 400:
				_set_status("Invalid setup: %s" % (detail if detail != "" else "check the values"), true)
			elif code == 409:
				_set_status("This run already started elsewhere -- go back and reconnect.", true)
			else:
				_set_status("POST /config failed (HTTP %d).%s" % [code, (" " + detail) if detail != "" else ""], true)
		"resume":
			if code >= 200 and code < 300:
				# Follow the now-running sim, exactly like the menu's Connect path.
				LaunchConfig.set_live(_url, _token)
				_switching = true
				get_tree().change_scene_to_file.call_deferred(VIEWER_SCENE)
			else:
				_set_busy(false)
				_set_status("Resume failed (HTTP %d) -- the run may already be live." % code, true)
		_:
			_set_busy(false)


func _render_config(data: Dictionary) -> void:
	_brains = data.get("brains", [])
	var knobs: Dictionary = data.get("knobs", {})
	_knobs_current = knobs.get("current", {})
	_knobs_defaults = knobs.get("defaults", {})
	var run: Dictionary = data.get("run", {})
	_initial = {
		"brain": str(run.get("brain", "mock")),
		"steps": int(run.get("steps", 0)),
		"tick_seconds": float(run.get("tick_seconds", 0.0)),
		# `max_cost` is null on a free brain; get()'s default only applies to a
		# MISSING key, so null must be handled explicitly (float(null) errors).
		"max_cost": float(run.get("max_cost", 0.0)) if run.get("max_cost") != null else 0.0,
	}

	for child in _form_box.get_children():
		child.queue_free()
	_persona_checks.clear()
	_knob_rows.clear()

	# --- Cast ---
	_form_box.add_child(_section_label("CAST"))
	var cast: Array = data.get("cast", [])
	for entry in data.get("personas", []):
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		var cb := CheckBox.new()
		var pname := str(entry.get("name", entry.get("id", "?")))
		var blurb := str(entry.get("blurb", ""))
		if blurb.length() > 70:
			blurb = blurb.substr(0, 70) + "…"
		if blurb != "":
			cb.text = "%s -- %s" % [pname, blurb]
		else:
			cb.text = pname
		cb.button_pressed = str(entry.get("id", "")) in cast
		_form_box.add_child(cb)
		_persona_checks.append({"id": str(entry.get("id", "")), "cb": cb})

	# --- Sim knobs ---
	_form_box.add_child(_section_label("SIM KNOBS"))
	for spec in KNOBS:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		var cap := Label.new()
		cap.text = spec.label
		cap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(cap)
		var spin := SpinBox.new()
		if spec.kind == "float":
			spin.step = 0.05
			spin.max_value = 100.0
		else:
			spin.step = 1
			spin.max_value = 10000
		spin.min_value = 0
		spin.value = float(_knob_value(spec.section, spec.key))
		row.add_child(spin)
		_form_box.add_child(row)
		_knob_rows.append({
			"section": spec.section, "key": spec.key, "kind": spec.kind,
			"spin": spin, "initial": spin.value,
		})

	# --- Run controls ---
	_form_box.add_child(_section_label("RUN"))
	var brain_row := HBoxContainer.new()
	brain_row.add_theme_constant_override("separation", 8)
	var brain_cap := Label.new()
	brain_cap.text = "Brain"
	brain_cap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	brain_row.add_child(brain_cap)
	_brain_opt = OptionButton.new()
	for b in _brains:
		_brain_opt.add_item(str(b))
	var bi := (_brains as Array).find(_initial.brain)
	_brain_opt.select(bi if bi >= 0 else 0)
	brain_row.add_child(_brain_opt)
	_form_box.add_child(brain_row)

	_steps_spin = _spin_row("Steps", 1, 1000000, 1, float(_initial.steps))
	_tick_spin = _spin_row("Tick seconds", 0.0, 60.0, 0.1, float(_initial.tick_seconds))
	_cost_spin = _spin_row("Cost budget (USD, llm only)", 0.0, 1000.0, 0.5, float(_initial.max_cost))

	var stop := str(run.get("stop_time", ""))
	if stop != "":
		var hint := Label.new()
		hint.text = "Ends about %s at the current step budget." % stop
		hint.add_theme_color_override("font_color", HINT_COLOR)
		hint.add_theme_font_size_override("font_size", 12)
		_form_box.add_child(hint)

	_start_btn.disabled = _persona_checks.is_empty()
	_set_status("%d persona(s) available. Pick a cast, tweak knobs, then Start." % _persona_checks.size(), false)


func _spin_row(label: String, lo: float, hi: float, step: float, value: float) -> SpinBox:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var cap := Label.new()
	cap.text = label
	cap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(cap)
	var spin := SpinBox.new()
	spin.min_value = lo
	spin.max_value = hi
	spin.step = step
	spin.value = value
	row.add_child(spin)
	_form_box.add_child(row)
	return spin


func _knob_value(section: String, key: String) -> Variant:
	var cur: Variant = _knobs_current.get(section, {})
	if typeof(cur) == TYPE_DICTIONARY and (cur as Dictionary).has(key):
		return (cur as Dictionary)[key]
	var dz: Variant = _knobs_defaults.get(section, {})
	if typeof(dz) == TYPE_DICTIONARY and (dz as Dictionary).has(key):
		return (dz as Dictionary)[key]
	return 0


func _checked_ids() -> Array:
	var ids := []
	for p in _persona_checks:
		if p.cb.button_pressed:
			ids.append(p.id)
	return ids


func _knob_edits() -> Dictionary:
	# Only knobs the user actually moved off their server value are edits.
	var edits := {}
	for row in _knob_rows:
		var v: Variant = int(row.spin.value) if row.kind == "int" else float(row.spin.value)
		var changed := false
		if row.kind == "int":
			changed = int(v) != int(row.initial)
		else:
			changed = not is_equal_approx(float(v), float(row.initial))
		if changed:
			if not edits.has(row.section):
				edits[row.section] = {}
			edits[row.section][row.key] = v
	return edits


func _on_start_pressed() -> void:
	if _pending != "" or _switching:
		return
	var cast := _checked_ids()
	if cast.is_empty():
		_set_status("Pick at least one persona for the cast.", true)
		return
	var brain := str(_brains[_brain_opt.selected]) if _brain_opt.selected >= 0 else str(_initial.brain)
	var body: Dictionary = ConfigBody.build_post_body({
		"cast": cast,
		"brain": brain,
		"initial_brain": _initial.brain,
		"steps": int(_steps_spin.value),
		"initial_steps": int(_initial.steps),
		"tick": float(_tick_spin.value),
		"initial_tick": float(_initial.tick_seconds),
		"max_cost": float(_cost_spin.value),
		"knobs_current": _knobs_current,
		"knob_edits": _knob_edits(),
	})
	_pending = "config"
	_set_busy(true)
	_set_status("Applying configuration…", false)
	var err := _http.request("%s/config" % _url, _headers(), HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_pending = ""
		_set_busy(false)
		_set_status("Couldn't start the request (error %d)." % err, true)


func _detail(body: PackedByteArray) -> String:
	# Pull FastAPI's {"detail": "..."} message for an inline error, when present.
	var d: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(d) == TYPE_DICTIONARY and (d as Dictionary).has("detail"):
		return str((d as Dictionary)["detail"])
	return ""


func _on_back_pressed() -> void:
	if _switching:
		return
	_switching = true
	get_tree().change_scene_to_file.call_deferred(MENU_SCENE)
