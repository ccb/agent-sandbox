extends Node2D
## Plays a UPenn agent-simulation replay on the campus map.
##
## The Python sim (sim/generate_penn_replay.py) writes maps/penn_replay.json:
## per step, each persona's tile (x, y) + current activity + emoji. This scene
## renders the campus (a sibling TileMapLayer running tiled_map.gd) and animates
## one Cute Fantasy sprite per persona, easing it tile-to-tile along its path —
## so you watch Maya, Professor Ellis and Diego walk the real campus. No agent
## logic here; this is purely the viewer (the sim already decided everything).

@export_file("*.json") var replay_path: String = "res://maps/penn_replay.json"
## On web exports the replay is NOT packed into the build; it's fetched over HTTP
## from this URL (relative to the page the build is embedded in). That way a new
## sim only needs the JSON file replaced — no Godot re-export. Ignored on desktop,
## which reads `replay_path` from disk instead. See godot-generative-agents/web/.
@export var web_replay_url: String = "replay/penn_replay.json"
@export var player_sheet: Texture2D  # Cute_Fantasy_Free/Player/Player.png
## Real seconds spent replaying one sim step (smaller = faster playback).
@export var step_seconds: float = 0.10
## Start the clock this many steps in — handy for screenshots mid-walk. 0 = start.
@export var preview_step: int = 0
## In-game time at step 0 (overridden by replay meta["start"] when present).
@export var sim_start: String = "2023-02-13 08:00:00"

# The Cute Fantasy player sheet is a 6x10 grid; row 0 is a 6-frame walk cycle.
const SHEET_HFRAMES := 6
const SHEET_VFRAMES := 10
const WALK_ROW := 0
const WALK_LEN := 6
const ANIM_FPS := 8.0
# A 32px character frame at this scale is ~4 tiles tall, so a person reads as
# clearly smaller than a campus building (which span ~10-20 tiles) rather than
# towering over it. The whole-campus camera (zoom ~0.5) still keeps it visible,
# and the name label above each sprite makes agents easy to find regardless.
const SPRITE_SCALE := 2.0
# The character art is centred in its frame, so the sprite's head sits this far
# above the node origin; the nameplate is parked just above that.
const SPRITE_HALF_PX := 16.0 * SPRITE_SCALE
# A distinct tint per persona so they're easy to tell apart at a glance.
const TINTS := [
	Color(1.0, 0.95, 0.95),  # Maya  - warm white
	Color(0.70, 0.82, 1.0),  # Ellis - blue
	Color(0.80, 1.0, 0.78),  # Diego - green
	Color(1.0, 0.86, 0.70),  # spare - orange
]
const MONTHS := [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]

var _tile_px := 16
var _sec_per_step := 10
var _start_unix := 0
var _frames: Array = []
var _names: Array = []
var _agents := {}  # name -> {sprite, label}
var _t := 0.0
var _anim_t := 0.0
var _paused := false
var _speed := 1.0
var _last_status_step := -1         # last frame index pushed to the sidebar rows
var _sky: CanvasModulate            # clock-driven day-night tint over the campus

@onready var _camera: Camera2D = $Camera2D
@onready var _panel = $UI/AgentPanel  # agent_panel.gd sidebar


func _ready() -> void:
	# The sidebar drives the camera: Track a character to follow them, toggle off (or
	# pan the map) to release. The panel emits requests; we translate them to camera
	# calls and keep its highlight in sync when the camera releases on its own.
	_panel.track_requested.connect(_on_track_requested)
	_panel.stop_requested.connect(_on_stop_requested)
	_panel.zoom_in_requested.connect(_camera.zoom_in)
	_panel.zoom_out_requested.connect(_camera.zoom_out)
	_panel.reset_requested.connect(_camera.reset_view)
	_camera.follow_stopped.connect(_panel.clear_active)

	# Playback controls: pause/resume, seek along the timeline, change speed.
	_panel.play_pause_requested.connect(_on_play_pause)
	_panel.seek_requested.connect(_on_seek)
	_panel.speed_changed.connect(func(m: float) -> void: _speed = m)
	_panel.set_playing(not _paused)

	# A clock-driven tint over the 2D world (the screen-space UI layer is unaffected),
	# so the campus warms/dims with the in-game time of day.
	_sky = CanvasModulate.new()
	add_child(_sky)

	# Desktop reads the replay straight off disk; web fetches it over HTTP so a new
	# sim never needs a re-export (the JSON lives next to the page, not in the .pck).
	if OS.has_feature("web"):
		_load_replay_web()
	else:
		_load_replay_desktop()


func _load_replay_desktop() -> void:
	var f := FileAccess.open(replay_path, FileAccess.READ)
	if f == null:
		push_error("penn_replay: cannot open %s" % replay_path)
		return
	_load_replay_from_text(f.get_as_text())


func _load_replay_web() -> void:
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(_on_replay_request_completed)
	# Godot's HTTPRequest needs an absolute URL (with a scheme) — unlike the
	# browser's fetch(), it won't resolve a relative path itself. Resolve the
	# configured URL against the page that hosts the build.
	var url := web_replay_url
	if not (url.begins_with("http://") or url.begins_with("https://")):
		url = str(JavaScriptBridge.eval("new URL('%s', window.location.href).href" % web_replay_url, true))
	var err := http.request(url)
	if err != OK:
		push_error("penn_replay: could not start HTTP request for %s (%d)" % [url, err])


func _on_replay_request_completed(
	_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	if code != 200:
		push_error("penn_replay: fetching %s returned HTTP %d" % [web_replay_url, code])
		return
	_load_replay_from_text(body.get_string_from_utf8())


func _load_replay_from_text(text: String) -> void:
	var data: Variant = JSON.parse_string(text)
	if typeof(data) != TYPE_DICTIONARY:
		push_error("penn_replay: replay payload is not valid replay JSON")
		return

	var meta: Dictionary = data["meta"]
	_tile_px = int(meta["tile_px"])
	_sec_per_step = int(meta.get("sec_per_step", 10))
	_start_unix = _parse_sim_start(String(meta.get("start", sim_start)))
	_frames = data["frames"]
	var thumb := _make_thumbnail()
	for i in meta["personas"].size():
		_names.append(meta["personas"][i]["name"])
		_spawn_agent(meta["personas"][i]["name"], i)
		# Mirror the world sprite's tint in the sidebar so the two agree at a glance.
		_panel.add_character(meta["personas"][i]["name"], thumb, TINTS[i % TINTS.size()])

	# Size the timeline to the replay (frames are 0..last) and seed the readout.
	var last := maxi(_frames.size() - 1, 0)
	_panel.set_progress(preview_step, last)

	# Place everyone on their first frame, then optionally fast-forward the clock.
	_t = preview_step * step_seconds
	_anim_t = 0.0
	_update_clock()
	print("penn_replay: %d steps, %d personas" % [_frames.size(), _names.size()])


func _parse_sim_start(text: String) -> int:
	# "2023-02-13 08:00:00" -> unix seconds for the in-game clock anchor.
	var parts := text.strip_edges().split(" ", false)
	if parts.size() != 2:
		push_warning("penn_replay: bad sim start %r, using epoch" % text)
		return 0
	var date := parts[0].split("-", false)
	var clock := parts[1].split(":", false)
	if date.size() != 3 or clock.size() != 3:
		push_warning("penn_replay: bad sim start %r, using epoch" % text)
		return 0
	return int(Time.get_unix_time_from_datetime_dict({
		"year": int(date[0]),
		"month": int(date[1]),
		"day": int(date[2]),
		"hour": int(clock[0]),
		"minute": int(clock[1]),
		"second": int(clock[2]),
	}))


func _format_sim_time(sim_seconds: int) -> String:
	var dt: Dictionary = Time.get_datetime_dict_from_unix_time(_start_unix + sim_seconds)
	return "%s %d, %d, %02d:%02d:%02d" % [
		MONTHS[dt["month"] - 1], dt["day"], dt["year"], dt["hour"], dt["minute"], dt["second"]
	]


func _update_clock() -> void:
	var sim_seconds := int((_t / step_seconds) * float(_sec_per_step))
	_panel.set_clock_text(_format_sim_time(sim_seconds))
	if _sky != null:
		var dt: Dictionary = Time.get_datetime_dict_from_unix_time(_start_unix + sim_seconds)
		_sky.color = _time_of_day_color(float(dt["hour"]) + float(dt["minute"]) / 60.0)


func _time_of_day_color(hour: float) -> Color:
	# A gentle wash: cool/dim overnight, neutral at midday, warm at dawn & dusk.
	# `t` is a daylight factor (0 = deep night, 1 = full day) that ramps over the
	# 5–8h and 17–20h transitions; `warm` peaks during those same transitions.
	var night := Color(0.55, 0.6, 0.78)
	var day := Color(1.0, 1.0, 1.0)
	var dusk := Color(1.0, 0.82, 0.62)
	var t: float
	if hour < 5.0 or hour >= 20.0:
		t = 0.0
	elif hour < 8.0:
		t = (hour - 5.0) / 3.0
	elif hour < 17.0:
		t = 1.0
	else:
		t = (20.0 - hour) / 3.0
	var warm := clampf(1.0 - absf(t - 0.5) * 2.0, 0.0, 1.0)
	return night.lerp(day, t).lerp(dusk, warm * 0.35)


func _spawn_agent(name: String, index: int) -> void:
	# One container per agent (moved as a unit); the sprite is scaled up inside it
	# while the name label stays at normal size above it.
	var node := Node2D.new()
	add_child(node)

	var spr := Sprite2D.new()
	spr.texture = player_sheet
	spr.hframes = SHEET_HFRAMES
	spr.vframes = SHEET_VFRAMES
	spr.frame = WALK_ROW * SHEET_HFRAMES
	spr.scale = Vector2(SPRITE_SCALE, SPRITE_SCALE)
	spr.modulate = TINTS[index % TINTS.size()]
	node.add_child(spr)

	var label := Label.new()
	label.text = name
	label.add_theme_font_size_override("font_size", 32)
	label.add_theme_color_override("font_color", Color.WHITE)
	label.add_theme_color_override("font_outline_color", Color.BLACK)
	label.add_theme_constant_override("outline_size", 10)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	# Park the two-line nameplate just above the sprite's head (the ~90px covers
	# the two text lines), so it tracks the sprite size instead of overlapping it.
	label.position = Vector2(-110, -(SPRITE_HALF_PX + 90.0))
	label.custom_minimum_size = Vector2(220, 0)
	node.add_child(label)

	_agents[name] = {"node": node, "sprite": spr, "label": label}


func _tile_to_world(x: int, y: int) -> Vector2:
	# Tile centre in the map's pixel space (the campus TileMapLayer is unscaled).
	return Vector2((x + 0.5) * _tile_px, (y + 0.5) * _tile_px)


func _make_thumbnail() -> AtlasTexture:
	# The row-0 / column-0 standing frame of the shared player sheet, reused (tinted
	# per row by the panel) as every sidebar icon — one instance is fine for all rows.
	var at := AtlasTexture.new()
	at.atlas = player_sheet
	var fw := float(player_sheet.get_width()) / SHEET_HFRAMES
	var fh := float(player_sheet.get_height()) / SHEET_VFRAMES
	at.region = Rect2(0.0, 0.0, fw, fh)
	return at


func _on_track_requested(name: String) -> void:
	if _agents.has(name):
		_camera.follow(_agents[name]["node"])


func _on_stop_requested() -> void:
	_camera.stop_following()


func _on_play_pause() -> void:
	_paused = not _paused
	_panel.set_playing(not _paused)


func _on_seek(step: int) -> void:
	# Jump the playhead; _process re-renders from _t every frame, so the seek shows
	# even while paused.
	_t = float(step) * step_seconds
	_anim_t = 0.0


func _process(delta: float) -> void:
	if _frames.is_empty():
		return
	# Advance only while playing; the render below always runs from _t, so a seek (or
	# the day-night tint) still updates the view while paused.
	if not _paused:
		_t += delta * _speed
		_anim_t += delta * _speed
	_update_clock()

	var last := _frames.size() - 1
	var fpos := _t / step_seconds
	var i := int(fpos)
	var looped := false
	if i >= last:
		i = last
		looped = true
	var frac: float = 0.0 if looped else fpos - float(i)
	var j: int = i if looped else i + 1
	_panel.set_progress(i, last)

	for name in _names:
		var a: Dictionary = _frames[i][name]
		var b: Dictionary = _frames[j][name]
		var pa := _tile_to_world(int(a["x"]), int(a["y"]))
		var pb := _tile_to_world(int(b["x"]), int(b["y"]))
		var agent: Dictionary = _agents[name]
		agent["node"].position = pa.lerp(pb, frac)

		var moving: bool = a["x"] != b["x"] or a["y"] != b["y"]
		if moving and b["x"] != a["x"]:
			agent["sprite"].flip_h = int(b["x"]) < int(a["x"])
		var frame_in_row: int = (int(_anim_t * ANIM_FPS) % WALK_LEN) if moving else 0
		agent["sprite"].frame = WALK_ROW * SHEET_HFRAMES + frame_in_row

		# "<activity> @ UPenn:Building:grounds" -> just the activity for the label.
		var act := String(a["act"]).split(" @ ")[0]
		agent["label"].text = "%s\n%s %s" % [name, a["e"], act]

	# Mirror each agent's current activity into the sidebar, only when the frame index
	# changes (per-frame work is wasted — the text is identical within a step).
	if i != _last_status_step:
		_last_status_step = i
		for name in _names:
			var a: Dictionary = _frames[i][name]
			var act := String(a["act"]).split(" @ ")[0]
			_panel.set_character_status(name, "%s %s" % [a["e"], act])
