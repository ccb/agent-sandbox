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
## Draw a short breadcrumb trail behind each agent so you can see where they just
## came from. Set false to hide every trail.
@export var show_trail: bool = true

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
# Breadcrumb trail: how many past tile steps trail behind each agent, and how
# opaque its freshest (head) end is — the tail fades to fully transparent with age.
const TRAIL_LEN := 8
const TRAIL_HEAD_ALPHA := 0.7
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
var _trails: Node2D                 # parent of the per-agent breadcrumb Line2Ds
# Web only: push the current step to the page so the React companion panel can
# follow the replay. `_is_web` gates the JS calls to web exports; `_last_step`
# (-1 = none pushed yet) lets us call out only when the integer step changes.
var _is_web := false
var _last_step := -1

@onready var _camera: Camera2D = $Camera2D
@onready var _panel = $UI/AgentPanel  # agent_panel.gd sidebar
@onready var _minimap = $UI/Minimap  # minimap.gd bottom-right overview


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

	# The sidebar overlays the left edge; tell the camera its width so the pan/zoom
	# clamp frames the map into the open area to its right (campus never hides under
	# the bar). Seed from custom_minimum_size (set in the panel's _ready, which runs
	# first) and follow any later layout/theme resize.
	_camera.set_left_inset(_panel.custom_minimum_size.x)
	_panel.resized.connect(func() -> void: _camera.set_left_inset(_panel.size.x))

	# The bottom-right minimap: a campus overview with an agent dot each and a box for
	# the on-screen slice. Like the sidebar it's pure UI — we hand it the camera (to
	# draw the frame box and learn the map), add the agents after load, and route its
	# click-to-recentre back to the camera so a click glides the main view there.
	_minimap.configure(_camera)
	_minimap.recenter_requested.connect(_camera.move_to)

	# Playback controls: pause/resume, seek along the timeline, change speed.
	_panel.play_pause_requested.connect(_on_play_pause)
	_panel.seek_requested.connect(_on_seek)
	_panel.speed_changed.connect(func(m: float) -> void: _speed = m)
	_panel.set_playing(not _paused)

	# A clock-driven tint over the 2D world (the screen-space UI layer is unaffected),
	# so the campus warms/dims with the in-game time of day.
	_sky = CanvasModulate.new()
	add_child(_sky)

	# Holds the per-agent breadcrumb Line2Ds. Added here, before the agent sprites are
	# spawned during load, so the trails always draw underneath the sprites they trail
	# (same z, earlier in the tree) yet above the campus map.
	_trails = Node2D.new()
	add_child(_trails)

	# Let agents be picked by clicking their sprite (see _spawn_agent's Area2D). Mouse
	# picking on 2D physics bodies/areas is off by default, so the per-agent click
	# pick is dead until we switch it on for this scene's viewport.
	get_viewport().physics_object_picking = true

	_is_web = OS.has_feature("web")
	# Desktop reads the replay straight off disk; web fetches it over HTTP so a new
	# sim never needs a re-export (the JSON lives next to the page, not in the .pck).
	if _is_web:
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
		var pname: String = meta["personas"][i]["name"]
		var tint: Color = TINTS[i % TINTS.size()]
		_names.append(pname)
		_spawn_agent(pname, i)
		# Mirror the world sprite's tint in the sidebar and on the minimap dot, so the
		# three views of each character all agree at a glance.
		_panel.add_character(pname, thumb, tint)
		_minimap.add_agent(pname, _agents[pname]["node"], tint)

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
	# Park the single-line nameplate just above the sprite's head (the ~50px covers
	# the one text line), so it tracks the sprite size instead of overlapping it.
	# The current activity lives in the sidebar, so the label only shows the name.
	label.position = Vector2(-110, -(SPRITE_HALF_PX + 50.0))
	label.custom_minimum_size = Vector2(220, 0)
	node.add_child(label)

	# A click target over the sprite, so you can track an agent by clicking them on
	# the map (not just via the sidebar's Track button). The box roughly covers the
	# scaled character; clicking it toggles tracking through the same panel path the
	# sidebar uses. A pointing-hand cursor on hover advertises that they're clickable.
	var area := Area2D.new()
	area.input_pickable = true
	var collider := CollisionShape2D.new()
	var box := RectangleShape2D.new()
	box.size = Vector2(SPRITE_HALF_PX * 1.5, SPRITE_HALF_PX * 2.0)
	collider.shape = box
	area.add_child(collider)
	area.input_event.connect(_on_agent_input.bind(name))
	area.mouse_entered.connect(
		func() -> void: Input.set_default_cursor_shape(Input.CURSOR_POINTING_HAND)
	)
	area.mouse_exited.connect(
		func() -> void: Input.set_default_cursor_shape(Input.CURSOR_ARROW)
	)
	node.add_child(area)

	# A breadcrumb trail behind this agent: a polyline through its recent tile centres,
	# tinted like the sprite and fading from opaque at the head (where the sprite is) to
	# transparent at the tail (oldest step). Lives under _trails in world space — the
	# points carry absolute positions, so the line itself stays at the origin.
	var tint: Color = TINTS[index % TINTS.size()]
	var trail := Line2D.new()
	trail.width = float(_tile_px) * 0.45
	trail.joint_mode = Line2D.LINE_JOINT_ROUND
	trail.begin_cap_mode = Line2D.LINE_CAP_ROUND
	trail.end_cap_mode = Line2D.LINE_CAP_ROUND
	var grad := Gradient.new()
	grad.set_color(0, Color(tint.r, tint.g, tint.b, 0.0))            # tail: oldest, clear
	grad.set_color(1, Color(tint.r, tint.g, tint.b, TRAIL_HEAD_ALPHA))  # head: newest
	trail.gradient = grad
	trail.visible = show_trail
	_trails.add_child(trail)

	_agents[name] = {"node": node, "sprite": spr, "label": label, "trail": trail}


func _on_agent_input(
	_viewport: Node, event: InputEvent, _shape_idx: int, name: String
) -> void:
	# A left-click on an agent's sprite tracks them (or untracks if already tracked) —
	# the same toggle as the sidebar's Track button, driven through the panel so the
	# highlight and camera-follow stay consistent. Mark the pick handled so a click on
	# two overlapping agents doesn't fall through and toggle the one behind as well.
	# (Keeping the click from being read as a map drag-pan is the camera's job — see
	# camera_controls.gd's DRAG_THRESHOLD_PX — because physics picking runs after the
	# camera's _unhandled_input, so consuming it here is too late to stop that.)
	if (
		event is InputEventMouseButton
		and event.pressed
		and event.button_index == MOUSE_BUTTON_LEFT
	):
		get_viewport().set_input_as_handled()
		_panel.toggle_track(name)


func _tile_to_world(x: int, y: int) -> Vector2:
	# Tile centre in the map's pixel space (the campus TileMapLayer is unscaled).
	return Vector2((x + 0.5) * _tile_px, (y + 0.5) * _tile_px)


func _update_trail(trail: Line2D, name: String, step: int, head: Vector2) -> void:
	# Rebuild the breadcrumb as the tile centres for the last TRAIL_LEN steps up to
	# `step`, tipped with the sprite's live eased position so the head stays glued to
	# the agent between tiles. Reading straight from _frames (rather than buffering as
	# we go) keeps the trail correct after a seek or scrub, backwards as well as
	# forwards. The gradient maps tail→head along the line, so older points fade out.
	var pts := PackedVector2Array()
	var start := maxi(0, step - TRAIL_LEN + 1)
	for k in range(start, step + 1):
		var f: Dictionary = _frames[k][name]
		pts.append(_tile_to_world(int(f["x"]), int(f["y"])))
	pts.append(head)
	trail.points = pts


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
	var last := _frames.size() - 1
	if not _paused:
		_t += delta * _speed
		_anim_t += delta * _speed
		# Hold the playhead at the final step: the replay has no more frames, so the
		# clock must stop here rather than tick on past the end of the simulation.
		_t = min(_t, float(last) * step_seconds)
	_update_clock()

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
		if show_trail:
			_update_trail(agent["trail"], name, i, agent["node"].position)

		var moving: bool = a["x"] != b["x"] or a["y"] != b["y"]
		if moving and b["x"] != a["x"]:
			agent["sprite"].flip_h = int(b["x"]) < int(a["x"])
		var frame_in_row: int = (int(_anim_t * ANIM_FPS) % WALK_LEN) if moving else 0
		agent["sprite"].frame = WALK_ROW * SHEET_HFRAMES + frame_in_row

	# Mirror each agent's current activity into the sidebar, only when the frame index
	# changes (per-frame work is wasted — the text is identical within a step).
	if i != _last_status_step:
		_last_status_step = i
		for name in _names:
			var a: Dictionary = _frames[i][name]
			var act := String(a["act"]).split(" @ ")[0]
			_panel.set_character_status(name, "%s %s" % [a["e"], act])

	# Web: tell the React companion panel which step we're showing, so its agent
	# card + memory list track the canvas. Godot is the clock; we push only on a
	# step change. `window.__pennReplayStep` is registered by the web shell and is
	# simply absent on a plain export, where this whole call is a harmless no-op.
	if _is_web and i != _last_step:
		_last_step = i
		JavaScriptBridge.eval(
			"window.__pennReplayStep && window.__pennReplayStep(%d)" % i, true
		)
