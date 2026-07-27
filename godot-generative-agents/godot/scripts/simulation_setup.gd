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

# The curated sim knobs this scene exposes, each mapped to its nested path into
# GET /config's `knobs` block. Temperature (game.agent.temperature) is the live
# sampling temperature honored by the brain (#564); the rest are retrieval
# weights + vision + conversation pacing. `path` lets a knob reach any depth.
const KNOBS := [
	{"label": "Temperature (llm brain)", "path": ["game", "agent", "temperature"], "kind": "float"},
	{"label": "Recency weight", "path": ["retrieval", "alpha_recency"], "kind": "float"},
	{"label": "Importance weight", "path": ["retrieval", "alpha_importance"], "kind": "float"},
	{"label": "Relevance weight", "path": ["retrieval", "alpha_relevance"], "kind": "float"},
	{"label": "Vision radius (tiles)", "path": ["cognition", "vision_r"], "kind": "int"},
	{"label": "Conversation cooldown (steps)", "path": ["cognition", "conversation_cooldown_steps"], "kind": "int"},
	{"label": "Max exchanges / conversation", "path": ["cognition", "conversation_max_exchanges"], "kind": "int"},
]

var _url := ""
var _token := ""
var _http: HTTPRequest = null
var _pending := ""  # "" idle | "load" | "config" | "resume"
var _switching := false
var _seed := {}  # a "Re-run with this setup" config block (#734), consumed once

# UI, built once GET /config arrives.
var _form_box: VBoxContainer = null
var _status: Label = null
var _start_btn: Button = null
var _persona_checks: Array = []  # [{id, cb}]
var _knob_rows: Array = []       # [{section, key, kind, spin, initial}]
var _brain_opt: OptionButton = null
var _plan_opt: OptionButton = null
var _plan_hint: Label = null
var _steps_spin: SpinBox = null
var _tick_spin: SpinBox = null
var _cost_spin: SpinBox = null

# Server state captured from GET /config, needed to build the POST body.
var _brains: Array = []
var _plans: Array = []
var _knobs_current: Dictionary = {}
var _knobs_defaults: Dictionary = {}
var _initial := {"brain": "mock", "plan": "auto", "steps": 0, "tick_seconds": 0.0, "max_cost": 0.0}


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_url = LaunchConfig.last_live_url.rstrip("/")
	_token = LaunchConfig.live_token
	# A "Re-run with this setup" hand-off (#734), consumed once: capture then
	# clear, so a later fresh entry from the menu starts from server defaults.
	_seed = LaunchConfig.setup_seed
	LaunchConfig.setup_seed = {}
	_build_shell()
	_http = HTTPRequest.new()
	# 30s, not 10: a POST /config that switches to the llm brain rebuilds the
	# world and does a network check_anthropic_key() before responding.
	_http.timeout = 30.0
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
	if _plan_opt != null:
		_plan_opt.disabled = busy
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
	_plans = data.get("plans", [])
	var knobs: Dictionary = data.get("knobs", {})
	_knobs_current = knobs.get("current", {})
	_knobs_defaults = knobs.get("defaults", {})
	var run: Dictionary = data.get("run", {})
	_initial = {
		"brain": str(run.get("brain", "mock")),
		"plan": str(run.get("plan_request", "auto")),
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
			spin.rounded = true
			spin.max_value = 10000
		spin.min_value = 0
		spin.value = float(_knob_value(spec.path))
		row.add_child(spin)
		_form_box.add_child(row)
		_knob_rows.append({
			"label": spec.label, "path": spec.path, "kind": spec.kind, "spin": spin, "initial": spin.value,
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

	# The planner row (#791): which day planner the run will use. Populated
	# from GET /config's `plans` vocabulary and defaulting to the ASKED-FOR
	# value (run.plan_request) -- never the resolved run.plan -- so an
	# untouched dropdown truthfully means "keep the session's request" under
	# build_post_body's only-send-changed contract. Feature-detected: a
	# pre-#790 backend serves no `plans`, so it gets no row (and Start sends
	# no plan field at all).
	_plan_opt = null
	_plan_hint = null
	if not _plans.is_empty():
		var plan_row := HBoxContainer.new()
		plan_row.add_theme_constant_override("separation", 8)
		var plan_cap := Label.new()
		plan_cap.text = "Planner"
		plan_cap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		plan_row.add_child(plan_cap)
		_plan_opt = OptionButton.new()
		for p in _plans:
			_plan_opt.add_item(str(p))
		var pi := (_plans as Array).find(_initial.plan)
		_plan_opt.select(pi if pi >= 0 else 0)
		plan_row.add_child(_plan_opt)
		_form_box.add_child(plan_row)
		_plan_hint = Label.new()
		_plan_hint.add_theme_color_override("font_color", HINT_COLOR)
		_plan_hint.add_theme_font_size_override("font_size", 12)
		_form_box.add_child(_plan_hint)
		# Both pickers re-render the hint; _render_config rebuilds these
		# controls on every load, so the connects can't double up.
		_plan_opt.item_selected.connect(_on_planner_inputs_changed)
		_brain_opt.item_selected.connect(_on_planner_inputs_changed)
		_update_plan_row()

	_steps_spin = _spin_row("Steps", 1, 1000000, 1, float(_initial.steps))
	# Floor > 0: POST /config's tick_seconds is Field(gt=0), so a 0 would 422.
	# step 0.05 (not 0.1): a SpinBox snaps to `min + round((v-min)/step)*step`, and
	# with min 0.05 a step of 0.1 makes the grid {0.05, 0.15, 0.25, ...} -- every
	# round tick (0.1, 0.5, 1.0) gets bumped +0.05 and POSTed as a spurious edit
	# (base #733 flow and #734 re-run alike). step 0.05 puts those values on-grid.
	_tick_spin = _spin_row("Tick seconds", 0.05, 60.0, 0.05, float(_initial.tick_seconds))
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
	if not _seed.is_empty():
		_apply_seed(_seed)
		_seed = {}  # consumed once (#734): a re-render starts from server values


func _selected_brain() -> String:
	if _brain_opt == null or _brain_opt.selected < 0:
		return str(_initial.brain)
	return str(_brains[_brain_opt.selected])


func _selected_plan() -> String:
	if _plan_opt == null or _plan_opt.selected < 0:
		return str(_initial.plan)
	return str(_plans[_plan_opt.selected])


func _on_planner_inputs_changed(_index: int) -> void:
	_update_plan_row()


# Keep the planner row consistent with the selected brain (#791): the `llm`
# planner needs the llm brain (the server 400s the combination), so grey it
# out under a free brain -- snapping a stranded selection back to auto --
# then re-render the hint with the planner this selection will actually run.
# The hint is cosmetic; the server's validation stays the backstop.
func _update_plan_row() -> void:
	if _plan_opt == null:
		return
	var brain := _selected_brain()
	var llm_idx := (_plans as Array).find("llm")
	if llm_idx >= 0:
		_plan_opt.set_item_disabled(llm_idx, brain != "llm")
		if brain != "llm" and _plan_opt.selected == llm_idx:
			var auto_idx := (_plans as Array).find("auto")
			_plan_opt.select(auto_idx if auto_idx >= 0 else 0)
	if _plan_hint != null:
		var eff := ConfigBody.effective_plan(_selected_plan(), brain)
		_plan_hint.text = (
			"Day plan: model-authored (llm)"
			if eff == "llm"
			else "Day plan: authored schedule (schedule)"
		)


func _apply_seed(seed: Dictionary) -> void:
	# Pre-fill the form from a saved run's applied `config` block (#734). Widget
	# values move to the seed's; each knob row's `initial` (and the run-control
	# initials in `_initial`) stay at the server value, so build_post_body sends
	# the seed values as edits and the re-run reproduces the saved setup on this
	# fresh backend. Knobs this scene does not expose aren't reproduced -- this is
	# "same setup", not the byte-identical re-run #715 owns.
	#
	# A re-run can target a backend serving a different world/brains than the saved
	# run, so a saved cast member or brain may not exist here. Rather than silently
	# drop it (mock instead of the saved llm; an empty cast), collect what can't be
	# honored into `unmet` and warn -- the user just clicked "re-run THIS setup".
	var unmet: Array = []
	var cast: Variant = seed.get("cast")
	if typeof(cast) == TYPE_ARRAY:
		var available := {}
		for p in _persona_checks:
			p.cb.button_pressed = p.id in (cast as Array)
			available[p.id] = true
		var missing_cast := []
		for cid in (cast as Array):
			if not available.has(str(cid)):
				missing_cast.append(str(cid))
		if not missing_cast.is_empty():
			unmet.append("cast not on this backend: %s" % ", ".join(missing_cast))
	var sim_config: Variant = seed.get("sim_config")
	if typeof(sim_config) == TYPE_DICTIONARY:
		for row in _knob_rows:
			var v: Variant = _walk(sim_config, row.path)
			if v != null:
				_seed_spin(row.spin, float(v), str(row.label), unmet)
	var brain := str(seed.get("brain", ""))
	if brain != "" and _brain_opt != null:
		var bi := (_brains as Array).find(brain)
		if bi >= 0:
			_brain_opt.select(bi)
		else:
			unmet.append("brain '%s' not offered here" % brain)
	var plan := ConfigBody.seed_plan(seed)
	if plan != "":
		var pidx := (_plans as Array).find(plan)
		if _plan_opt != null and pidx >= 0:
			_plan_opt.select(pidx)
			_update_plan_row()
		else:
			# This backend has no planner row (pre-#790) or doesn't offer the
			# saved value -- warn like a missing brain, don't silently drop.
			unmet.append("planner '%s' not offered here" % plan)
	var run: Variant = seed.get("run")
	if typeof(run) == TYPE_DICTIONARY:
		var r := run as Dictionary
		if r.get("steps") != null and _steps_spin != null:
			_seed_spin(_steps_spin, float(r["steps"]), "steps", unmet)
		if r.get("tick_seconds") != null and _tick_spin != null:
			_seed_spin(_tick_spin, float(r["tick_seconds"]), "tick seconds", unmet)
		if r.get("max_cost") != null and _cost_spin != null:
			_seed_spin(_cost_spin, float(r["max_cost"]), "cost budget", unmet)
	if unmet.is_empty():
		_set_status("Pre-filled from a saved run. Adjust anything, then Start.", false)
	else:
		_set_status(
			"Pre-filled from a saved run, but this backend can't match: %s. Adjust, then Start."
			% "; ".join(unmet),
			true,
		)


# Assign a seeded value onto a SpinBox and, if the box's step grid or min/max
# snapped it away from the saved value, record that in `unmet` so the re-run
# warns instead of silently pacing/sampling differently than the run it claims
# to reproduce (#734 review follow-up). A SpinBox snaps to `min + round((v-min)
# /step)*step` then clamps to [min, max], so an off-grid temperature (0.72->0.70)
# or a below-floor tick (0.02->0.05) would otherwise slip through unflagged --
# unlike a missing cast member or brain, which already warn.
static func _seed_spin(spin: SpinBox, requested: float, label: String, unmet: Array) -> void:
	spin.value = requested
	if not is_equal_approx(spin.value, requested):
		unmet.append("%s %s adjusted to %s" % [label, requested, spin.value])


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


func _knob_value(path: Array) -> Variant:
	var v: Variant = _walk(_knobs_current, path)
	if v != null:
		return v
	v = _walk(_knobs_defaults, path)
	return v if v != null else 0


func _walk(d: Variant, path: Array) -> Variant:
	var cur: Variant = d
	for k in path:
		if typeof(cur) != TYPE_DICTIONARY or not (cur as Dictionary).has(k):
			return null
		cur = (cur as Dictionary)[k]
	return cur


func _checked_ids() -> Array:
	var ids := []
	for p in _persona_checks:
		if p.cb.button_pressed:
			ids.append(p.id)
	return ids


func _knob_edits() -> Dictionary:
	# Only knobs the user actually moved off their server value are edits, keyed
	# by their nested path so merge_knobs overlays just that leaf.
	var edits := {}
	for row in _knob_rows:
		var v: Variant = int(row.spin.value) if row.kind == "int" else float(row.spin.value)
		var changed := false
		if row.kind == "int":
			changed = int(v) != int(row.initial)
		else:
			changed = not is_equal_approx(float(v), float(row.initial))
		if changed:
			_set_path(edits, row.path, v)
	return edits


func _set_path(d: Dictionary, path: Array, value: Variant) -> void:
	var cur := d
	for i in range(path.size() - 1):
		var k: Variant = path[i]
		if not cur.has(k) or typeof(cur[k]) != TYPE_DICTIONARY:
			cur[k] = {}
		cur = cur[k]
	cur[path[path.size() - 1]] = value


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
		"plan": _selected_plan() if _plan_opt != null else "",
		"initial_plan": str(_initial.plan) if _plan_opt != null else "",
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
