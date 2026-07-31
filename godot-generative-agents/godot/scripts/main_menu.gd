extends Control
## The game's front door (issue #399): a landing page that lets you choose how to
## enter the viewer instead of baking the choice into the launch command.
##
## The ways in, all handed to the viewer via the LaunchConfig autoload and then
## `scenes/viewer.tscn`. Live is the primary path so it leads; every replay entry
## (baked, on-disk, or pulled from a backend) is grouped below it:
##   • Run a live simulation          — connect to a running backend/penn/serve_penn.py
##   • Play the bundled replay        — res://maps/penn_replay.json
##   • Play the boil-water demo        — res://maps/penn_replay_boil.json (#592; only
##                                       shown once baked with --scenario boil)
##   • Open a local replay file…      — any replay .json on disk (desktop only)
##   • Past runs ▸                     — browse a backend's stored runs (#716) and
##                                       open / resume / export / delete each
##
## On the web export (#903) the panel is instead reduced to the title and one
## "▶  Start replay" button: there the canvas is embedded in the public landing
## page as the demo, and the live-backend / past-runs controls stay out of
## public navigation (#879) — but the reader still gets an explicit start gate
## rather than landing mid-scene.
##
## Everything is built in code in _ready() (matching agent_panel.gd's house style),
## so the .tscn only carries the themed root. The backdrop is the REAL campus,
## rendered once into an off-screen SubViewport the same way minimap.gd builds its
## overview, dimmed under a translucent wash so the parchment panel stays readable.
##
## This scene is the boot scene on both desktop (project.godot run/main_scene) and
## web (web/scripts/export-godot.sh points the export at it). It never talks to the
## sim itself beyond a one-shot GET /live handshake to confirm a live backend is
## reachable before handing off — the viewer owns every connection after that.

const VIEWER_SCENE := "res://scenes/viewer.tscn"
const BUNDLED_REPLAY := "res://maps/penn_replay.json"
# The de-clumped boil-water demo (#592): a short, single-persona replay of the
# drink -> sicken -> boil -> recover arc, baked by
# `generate_penn_replay.py --scenario boil`. Like the bundled replay it's a
# git-ignored artifact, so its button self-hides until it's been baked.
const BOIL_REPLAY := "res://maps/penn_replay_boil.json"
const SETUP_SCENE := "res://scenes/simulation_setup.tscn"
const BACKDROP_MAP := "res://maps/upenn_core_urban.tmj"
const DEFAULT_LIVE_URL := "http://127.0.0.1:8080"  # serve_penn.py's default

# Dark-brown that stays legible on the parchment panel (matches agent_panel's
# STATUS_COLOR); errors go a muted dark red so they read as a problem, not decor.
const HINT_COLOR := Color(0.42, 0.32, 0.24)
const ERROR_COLOR := Color(0.82, 0.20, 0.15)

# Give up on the handshake probe after this long so a wrong URL fails fast with a
# clear message instead of hanging the Connect button.
const PROBE_TIMEOUT := 4.0

var _open_file_dialog: FileDialog = null
var _probe: HTTPRequest = null

var _url_edit: LineEdit = null
var _token_edit: LineEdit = null
var _connect_btn: Button = null
var _live_status: Label = null
var _replay_hint: Label = null

# One-shot latch: once we've committed to a scene switch, ignore every other
# button so a fast double-click can't fire change_scene_to_file twice.
var _switching := false

# The connect flow probes GET /live, then (only if the backend is paused) GET
# /config to decide setup-vs-viewer. This tracks which reply we're expecting.
var _probe_stage := "live"  # "live" | "config"


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_build_backdrop()
	_build_panel()
	if not OS.has_feature("web"):
		_build_file_dialog()
	_probe = HTTPRequest.new()
	_probe.timeout = PROBE_TIMEOUT
	_probe.request_completed.connect(_on_probe_completed)
	add_child(_probe)


# --- Backdrop ---------------------------------------------------------------


func _build_backdrop() -> void:
	# A solid base first, so the menu still has a sensible background if the campus
	# fails to render (a broken .tmj shouldn't leave the panel floating on nothing).
	var base := ColorRect.new()
	base.color = Color(0.18, 0.20, 0.24)
	base.set_anchors_preset(Control.PRESET_FULL_RECT)
	base.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(base)

	# Render the real campus once into an off-screen SubViewport (the same trick
	# minimap.gd uses for its overview): a TileMapLayer running tiled_map.gd paints
	# the map synchronously in its _ready, so its used cells are ready to measure
	# immediately, and UPDATE_ONCE renders a single frame — the campus never moves.
	var sv := SubViewport.new()
	sv.disable_3d = true
	sv.gui_disable_input = true
	sv.size = Vector2i(1920, 1080)  # the design resolution; the wash hides any softness

	var layer := TileMapLayer.new()
	layer.set_script(load("res://scripts/tiled_map.gd"))
	layer.set("map_path", BACKDROP_MAP)  # set() because the var lives on the runtime script
	sv.add_child(layer)

	var cam := Camera2D.new()
	cam.enabled = true
	sv.add_child(cam)

	add_child(sv)

	if layer.tile_set == null:
		# Map didn't load; the base ColorRect stands in and we skip the campus.
		sv.queue_free()
		return

	var used := layer.get_used_rect()
	var ts := Vector2(layer.tile_set.tile_size)
	var bounds := Rect2(Vector2(used.position) * ts, Vector2(used.size) * ts)
	if bounds.size.x <= 0.0 or bounds.size.y <= 0.0:
		sv.queue_free()
		return

	# Cover-zoom: fill the whole 1920x1080 frame (the larger scale wins, so no
	# letterbox bars), centred on the campus. maxf mirrors CSS `background-size: cover`.
	cam.zoom = Vector2.ONE * maxf(
		float(sv.size.x) / bounds.size.x, float(sv.size.y) / bounds.size.y
	)
	cam.position = bounds.get_center()
	cam.make_current()
	sv.render_target_update_mode = SubViewport.UPDATE_ONCE

	var campus := TextureRect.new()
	campus.texture = sv.get_texture()
	campus.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	campus.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	campus.set_anchors_preset(Control.PRESET_FULL_RECT)
	campus.mouse_filter = Control.MOUSE_FILTER_IGNORE
	campus.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR  # smooth the minified campus
	add_child(campus)

	# Dark wash so the bright parchment panel and its dark-brown text pop off the map.
	var wash := ColorRect.new()
	wash.color = Color(0.16, 0.17, 0.21, 0.55)
	wash.set_anchors_preset(Control.PRESET_FULL_RECT)
	wash.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(wash)


# --- The menu panel ---------------------------------------------------------


func _build_panel() -> void:
	# Centre a fixed-width parchment card over the backdrop.
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)

	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(520, 0)
	center.add_child(panel)

	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	panel.add_child(margin)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	margin.add_child(col)

	var title := Label.new()
	title.text = "GENERATIVE AGENTS"
	title.theme_type_variation = "TitleRibbon"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_font_size_override("font_size", 34)
	col.add_child(title)

	# On web the menu is the public demo's start gate and nothing else (#903):
	# the title and a single "Start replay" button, none of the live-backend /
	# past-runs controls #879 keeps out of public navigation. Desktop builds the
	# full menu below.
	var web := OS.has_feature("web")

	if not web:
		# --- Run a live simulation (the primary path, so it leads the menu) ---
		col.add_child(_ribbon("RUN A LIVE SIMULATION"))

		var url_row := HBoxContainer.new()
		url_row.add_theme_constant_override("separation", 8)
		col.add_child(url_row)
		var url_cap := Label.new()
		url_cap.text = "Backend"
		url_cap.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		url_row.add_child(url_cap)
		_url_edit = LineEdit.new()
		_url_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_url_edit.text = _default_url()
		_url_edit.text_submitted.connect(func(_t: String) -> void: _on_connect_pressed())
		url_row.add_child(_url_edit)

		var token_row := HBoxContainer.new()
		token_row.add_theme_constant_override("separation", 8)
		col.add_child(token_row)
		var token_cap := Label.new()
		token_cap.text = "Token"
		token_cap.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		token_row.add_child(token_cap)
		_token_edit = LineEdit.new()
		_token_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_token_edit.secret = true
		_token_edit.placeholder_text = "optional"
		_token_edit.text = _default_token()
		_token_edit.text_submitted.connect(func(_t: String) -> void: _on_connect_pressed())
		token_row.add_child(_token_edit)

		_connect_btn = Button.new()
		_connect_btn.text = "Connect to the backend"
		_connect_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_connect_btn.pressed.connect(_on_connect_pressed)
		col.add_child(_connect_btn)

		_live_status = _muted_label("")
		_live_status.visible = false
		col.add_child(_live_status)

		# --- Watch a replay (every path that opens a stored/baked run) ---
		col.add_child(_ribbon("WATCH A REPLAY"))

	var bundled_btn := Button.new()
	# The one web-visible control carries the showcase copy; desktop keeps the
	# fuller label since it sits among the other replay sources.
	bundled_btn.text = "▶  Start replay" if web else "▶  Play the bundled replay"
	bundled_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bundled_btn.pressed.connect(_on_bundled_pressed)
	col.add_child(bundled_btn)

	if not web:
		# The boil-water demo (#592) is an optional extra bake, so its button only
		# appears once that replay has been generated — otherwise it'd be a button
		# that can only error. (The bundled replay above always shows and explains
		# how to bake it, because it's the primary entry point.)
		if FileAccess.file_exists(BOIL_REPLAY):
			var boil_btn := Button.new()
			boil_btn.text = "▶  Play the boil-water demo"
			boil_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			boil_btn.pressed.connect(_on_boil_pressed)
			col.add_child(boil_btn)

		# The file picker is a native desktop dialog; there's no filesystem to
		# browse in the browser anyway.
		var open_btn := Button.new()
		open_btn.text = "Open a local replay file…"
		open_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		open_btn.pressed.connect(_on_open_file_pressed)
		col.add_child(open_btn)

		# Past runs (#716): open a run stored on a backend as a replay, so it
		# belongs with the other replay entries. It reads the backend URL/token
		# from the live form above and stashes the normalized values (via
		# _on_past_runs_pressed) for past_runs.gd to read back after the scene
		# swap. GET /runs works on any persisted-store backend (even one with no
		# live loop), so it doesn't probe /live first -- it just needs a URL
		# entered above.
		var past_btn := Button.new()
		past_btn.text = "Past runs ▸"
		past_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		past_btn.pressed.connect(_on_past_runs_pressed)
		col.add_child(past_btn)

	_replay_hint = _muted_label("")
	_replay_hint.visible = false
	col.add_child(_replay_hint)

	# Live is the primary path on desktop, so land the keyboard in the backend
	# field: typing a URL and pressing Enter connects (text_submitted ->
	# _on_connect_pressed). On web the field doesn't exist at all (see above) —
	# which also retires the old focus hazard here: a focused LineEdit switches
	# on Godot's browser IME shim, which kept re-focusing a hidden contenteditable
	# <div> and stealing focus from the landing page embedding the canvas
	# (web/src/components/home/HomeView.tsx).
	if not web:
		_url_edit.grab_focus()


func _ribbon(text: String) -> Label:
	# A small section banner on the same Cute Fantasy ribbon the sidebar title uses.
	var label := Label.new()
	label.text = text
	label.theme_type_variation = "TitleRibbon"
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_font_size_override("font_size", 20)
	return label


func _muted_label(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", HINT_COLOR)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return label


func _build_file_dialog() -> void:
	var dialog := FileDialog.new()
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	dialog.filters = PackedStringArray(["*.json ; Replay JSON"])
	dialog.title = "Open a replay JSON"
	dialog.use_native_dialog = true  # the OS picker on desktop
	dialog.min_size = Vector2i(700, 450)  # fallback (non-native) dialog size
	dialog.file_selected.connect(_on_file_selected)
	add_child(dialog)
	_open_file_dialog = dialog


# --- Replay actions ---------------------------------------------------------


func _on_bundled_pressed() -> void:
	if _switching:
		return
	# On desktop the replay is read straight off disk; it's git-ignored, so a fresh
	# checkout may not have it yet — say how to make one instead of failing silently.
	# On web it isn't packed into the build at all: the viewer fetches it over HTTP
	# (web_replay_url), so we always proceed and let that path handle a missing file.
	if not OS.has_feature("web") and not FileAccess.file_exists(BUNDLED_REPLAY):
		_show_replay_hint(
			"No bundled replay yet. Generate one with backend/penn/generate_penn_replay.py, "
			+ "or use “Open a local replay file…”.", true)
		return
	LaunchConfig.set_replay(BUNDLED_REPLAY)
	_go_to_viewer()


func _on_boil_pressed() -> void:
	if _switching:
		return
	# The button only exists when the file is present (see _build_panel), but guard
	# anyway so a race (deleted between build and click) fails with a clear hint
	# rather than a blank viewer.
	if not FileAccess.file_exists(BOIL_REPLAY):
		_show_replay_hint(
			"No boil-water demo yet. Bake it with "
			+ "backend/penn/generate_penn_replay.py --scenario boil.", true)
		return
	LaunchConfig.set_replay(BOIL_REPLAY)
	_go_to_viewer()


func _on_open_file_pressed() -> void:
	if _switching or _open_file_dialog == null:
		return
	_open_file_dialog.popup_centered_ratio(0.6)


func _on_file_selected(path: String) -> void:
	if _switching:
		return
	# FileAccess.open() (the desktop loader) takes an absolute OS path as-is, so the
	# picked file goes straight through — no res:// rewrite needed.
	LaunchConfig.set_replay(path)
	_go_to_viewer()


func _show_replay_hint(text: String, is_error: bool) -> void:
	_replay_hint.text = text
	_replay_hint.add_theme_color_override(
		"font_color", ERROR_COLOR if is_error else HINT_COLOR)
	_replay_hint.visible = true


# --- Live actions -----------------------------------------------------------


func _default_url() -> String:
	# Prefill for the least surprise: the URL we last connected to (survives a
	# back-to-menu), then the SIM_API_URL env var, then serve_penn's default.
	if LaunchConfig.last_live_url != "":
		return LaunchConfig.last_live_url
	var env := OS.get_environment("SIM_API_URL")
	return env if env != "" else DEFAULT_LIVE_URL


func _default_token() -> String:
	if LaunchConfig.live_token != "":
		return LaunchConfig.live_token
	return OS.get_environment("SIM_API_TOKEN")


func _normalize_url(raw: String) -> String:
	# A user types "localhost:8080" or "127.0.0.1:8080/"; make it a real base URL:
	# default to http:// when no scheme is given, and drop any trailing slash so
	# "%s/live" doesn't double up.
	var url := raw.strip_edges()
	if url != "" and not (url.begins_with("http://") or url.begins_with("https://")):
		url = "http://" + url
	return url.rstrip("/")


func _on_connect_pressed() -> void:
	if _switching:
		return
	_probe_stage = "live"
	var url := _normalize_url(_url_edit.text)
	if url == "":
		_show_live_status("Enter the backend's URL first.", true)
		return
	# Probe GET /live before switching, so a bad URL / stopped backend / missing
	# live loop is reported here rather than the viewer silently retrying forever.
	_connect_btn.disabled = true
	_show_live_status("Connecting to %s…" % url, false)
	var headers := PackedStringArray()
	var token := _token_edit.text.strip_edges()
	if token != "":
		headers.append("Authorization: Bearer %s" % token)
	var err := _probe.request("%s/live" % url, headers)
	if err != OK:
		_connect_btn.disabled = false
		_show_live_status("Couldn't start the request (error %d)." % err, true)


func _on_probe_completed(
	result: int, code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	if _switching:
		return
	var url := _normalize_url(_url_edit.text)
	# Stage 2: the GET /config reply -- decide setup scene vs. viewer.
	if _probe_stage == "config":
		_connect_btn.disabled = false
		if _config_is_configurable(result, code, body):
			# Stash the connection the same way Past runs does, then hand off to
			# the setup scene (it fetches GET /config itself and owns the run
			# from Start onward).
			LaunchConfig.last_live_url = url
			LaunchConfig.live_token = _token_edit.text.strip_edges()
			_switching = true
			get_tree().change_scene_to_file.call_deferred(SETUP_SCENE)
			return
		# Not configurable (no config surface, or already locked): fall back to
		# today's paused-backend behavior -- into the viewer, Start there.
		LaunchConfig.set_live(url, _token_edit.text.strip_edges())
		_show_live_status("Connected — press ▶ Start in the viewer to begin.", false)
		_go_to_viewer()
		return

	# Stage 1: the GET /live reply (today's probe).
	if result != HTTPRequest.RESULT_SUCCESS:
		_connect_btn.disabled = false
		_show_live_status(
			"Can't reach %s — is the backend running? (backend/penn/serve_penn.py)" % url, true)
		return
	if code == 401 or code == 403:
		_connect_btn.disabled = false
		_show_live_status("HTTP %d — check the token." % code, true)
		return
	if code != 200:
		_connect_btn.disabled = false
		_show_live_status("Backend returned HTTP %d." % code, true)
		return
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(data) != TYPE_DICTIONARY or not bool((data as Dictionary).get("enabled", false)):
		_connect_btn.disabled = false
		_show_live_status(
			"Backend has no live loop — start it with a stepper (backend/penn/serve_penn.py).", true)
		return

	# Reachable and live. A running backend goes straight to the viewer (today's
	# flow, untouched). A PAUSED backend might be configurable -- probe GET
	# /config before deciding, keeping the Connect button disabled meanwhile.
	if not bool((data as Dictionary).get("paused", false)):
		_connect_btn.disabled = false
		LaunchConfig.set_live(url, _token_edit.text.strip_edges())
		_show_live_status("Connected — following the running sim…", false)
		_go_to_viewer()
		return

	_probe_stage = "config"
	_show_live_status("Connected — checking for a setup screen…", false)
	var headers := PackedStringArray()
	var token := _token_edit.text.strip_edges()
	if token != "":
		headers.append("Authorization: Bearer %s" % token)
	var err := _probe.request("%s/config" % url, headers)
	if err != OK:
		# Couldn't even ask -- treat as not-configurable and go to the viewer.
		_connect_btn.disabled = false
		LaunchConfig.set_live(url, token)
		_show_live_status("Connected — press ▶ Start in the viewer to begin.", false)
		_go_to_viewer()
		return


func _config_is_configurable(result: int, code: int, body: PackedByteArray) -> bool:
	# The GET /config verdict: only a reachable, 200, status=="configurable"
	# backend routes to the setup scene. A 404 (no config surface), a "locked"
	# status (run already started), or any transport error -> false -> viewer.
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		return false
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	return typeof(data) == TYPE_DICTIONARY \
		and str((data as Dictionary).get("status", "")) == "configurable"


func _on_past_runs_pressed() -> void:
	if _switching:
		return
	var url := _normalize_url(_url_edit.text)
	if url == "":
		_show_live_status("Enter the backend's URL first.", true)
		return
	# Stash for past_runs.gd (last_live_url survives; live_token too). No /live probe:
	# GET /runs answers even on a store-only backend.
	LaunchConfig.last_live_url = url
	LaunchConfig.live_token = _token_edit.text.strip_edges()
	_switching = true
	get_tree().change_scene_to_file.call_deferred("res://scenes/past_runs.tscn")


func _show_live_status(text: String, is_error: bool) -> void:
	_live_status.text = text
	_live_status.add_theme_color_override(
		"font_color", ERROR_COLOR if is_error else HINT_COLOR)
	_live_status.visible = true


# --- Hand-off ---------------------------------------------------------------


func _go_to_viewer() -> void:
	if _switching:
		return
	_switching = true
	# Deferred: we may be inside a signal handler (button press / dialog callback),
	# and swapping the scene tears down the node that emitted it.
	get_tree().change_scene_to_file.call_deferred(VIEWER_SCENE)
