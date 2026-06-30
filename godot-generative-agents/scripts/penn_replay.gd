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
# A distinct tint per persona so they're easy to tell apart at a glance. Indexed by
# persona order (modulo length), shared by the world sprite, the sidebar row, and the
# minimap dot. Seven tints keep the current Penn cast each a different colour.
const TINTS := [
	Color(1.0, 0.95, 0.95),  # Maya    - warm white
	Color(0.70, 0.82, 1.0),  # Ellis   - blue
	Color(0.80, 1.0, 0.78),  # Diego   - green
	Color(1.0, 0.86, 0.70),  # Priya   - amber
	Color(1.0, 0.95, 0.55),  # Marcus  - yellow
	Color(1.0, 0.78, 0.92),  # Tanaka  - pink
	Color(0.70, 1.0, 0.97),  # Sofia   - cyan
]
const MONTHS := [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]

# Speech bubbles float above the nameplate. ONLY dialogue gets a bubble (there are
# no activity/goal bubbles) -- a visible bubble means "this agent is speaking right
# now". A bubble is this wide (its text wraps and centres inside); position.x =
# -half that centres it over the sprite.
const BUBBLE_WIDTH := 210.0
# Bubble text size, and how far the bubble's top sits above the nameplate.
const BUBBLE_FONT_SIZE := 18
const BUBBLE_Y_OFFSET := 78.0
# A conversation plays back as staggered turn-taking: each line is shown for this
# many sim steps, by ONLY its speaker, before the reply takes over -- so a
# back-and-forth reads as a real exchange, not both agents talking at once. Each
# line fades over its last FADE steps.
const DIALOGUE_LINE_STEPS := 14.0
const DIALOGUE_FADE_STEPS := 2.0
# Long utterances are clipped so a bubble stays a couple of lines tall.
const BUBBLE_MAX_CHARS := 120
# Near-black dialogue text on the white speech bubble.
const SPEECH_TEXT_COLOR := Color(0.10, 0.10, 0.12)

# Perception fog: while you Track an agent, the campus OUTSIDE their perception
# radius is dimmed under a translucent grey cover, leaving a clear circle around
# them -- so you see what that agent can actually perceive (the same vision_r tiles
# the sim uses to gate sight and conversation). Cleared when not tracking anyone.
# The radius comes from the replay meta (`vision_r`, in tiles); this is the fallback
# if an older replay omits it. The feather is the soft edge width (screen pixels),
# and the colour is the grey wash applied at full strength outside the circle.
const FOG_FALLBACK_VISION_R := 8
const FOG_FEATHER_PX := 64.0
const FOG_COLOR := Color(0.16, 0.17, 0.21, 0.72)

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

# In-world dialogue: when two agents converse, the shared transcript is played back
# above their heads one line at a time -- only the current speaker shows a bubble --
# with a link drawn between the pair for the length of the exchange. See
# _update_agent_speech / _refresh_bubble / _refresh_links.
var _last_chat := {}        # name -> the `chat` value seen last step (for onset diff)
var _convo_lines := {}      # name -> the transcript [[speaker, line], ...] being played
var _convo_start := {}      # name -> sim step (float) the exchange began playing
var _convo_partner := {}    # name -> the other speaker's name, for the link
var _bubble_idx := {}       # name -> transcript line currently in its bubble (-1 = none)
var _links_node: Node2D     # parents one Line2D per active conversation pair
var _link_lines := {}       # sorted "A\nB" pair key -> Line2D
var _speech_style: StyleBoxFlat

# Perception fog (see FOG_* above). `_tracked_name` is the agent the camera is
# following (set on Track, cleared on release), or "" when free -- the fog only
# shows while it's set. `_vision_r` is the radius in tiles, read from the replay
# meta. The fog is a screen-space ColorRect (on its own CanvasLayer, below the UI)
# whose shader clears a circle around the tracked agent each frame.
var _tracked_name := ""
var _vision_r := FOG_FALLBACK_VISION_R
var _fog: CanvasLayer
var _fog_rect: ColorRect
var _fog_mat: ShaderMaterial

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
	# The fog tracks whoever the camera is following; when the follow is released
	# (Stop, a manual pan, Reset, or tracking a different agent), clear the target so
	# the fog lifts. `_on_track_requested` sets it when a new follow begins.
	_camera.follow_stopped.connect(_on_follow_stopped)

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

	# Dialogue bubble: a bright white speech bubble with a blue outline and a
	# squared-off bottom-left corner (a pointer down toward the speaker).
	_speech_style = _make_bubble_style(Color(1.0, 1.0, 1.0, 0.95), Color(0.25, 0.52, 0.85), 3, true)

	# Holds the per-agent breadcrumb Line2Ds. Added here, before the agent sprites are
	# spawned during load, so the trails always draw underneath the sprites they trail
	# (same z, earlier in the tree) yet above the campus map.
	_trails = Node2D.new()
	add_child(_trails)

	# Conversation links live above the campus (runtime children draw over the tscn's
	# map) but below the agent sprites (added later still), so a line sits under the
	# people it connects.
	_links_node = Node2D.new()
	add_child(_links_node)

	_setup_fog()

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
	# Perception radius for the tracking fog -- the sim's vision_r, falling back to
	# the Smallville default for older replays that don't record it.
	_vision_r = int(meta.get("vision_r", FOG_FALLBACK_VISION_R))
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

	# A dialogue speech bubble parked above the nameplate; hidden until this agent is
	# the one speaking. _refresh_bubble fills it and fades it per spoken line.
	var bubble := Label.new()
	bubble.add_theme_font_size_override("font_size", BUBBLE_FONT_SIZE)
	bubble.add_theme_stylebox_override("normal", _speech_style)
	bubble.add_theme_color_override("font_color", SPEECH_TEXT_COLOR)
	bubble.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	bubble.custom_minimum_size = Vector2(BUBBLE_WIDTH, 0)
	# Centre it over the sprite and park it above the nameplate (which sits at
	# -(half + 50)); it grows downward from here but the clip keeps it short.
	bubble.position = Vector2(-BUBBLE_WIDTH / 2.0, -(SPRITE_HALF_PX + 50.0 + BUBBLE_Y_OFFSET))
	bubble.visible = false
	node.add_child(bubble)

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

	_agents[name] = {"node": node, "sprite": spr, "label": label, "bubble": bubble, "trail": trail}


func _make_bubble_style(bg: Color, border_col: Color, border_w: int, tail: bool) -> StyleBoxFlat:
	# A rounded card behind the bubble text. `tail` squares off the bottom-left
	# corner so a speech bubble reads as pointing down toward the speaker.
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.set_corner_radius_all(9)
	if tail:
		sb.corner_radius_bottom_left = 0
	sb.set_content_margin_all(6.0)
	sb.set_border_width_all(border_w)
	sb.border_color = border_col
	return sb


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
		# Remember who we're tracking so the perception fog can centre on them. Set it
		# before follow() so a switch from agent A to B doesn't briefly clear it (B's
		# follow() doesn't emit follow_stopped, so _on_follow_stopped won't fire here).
		_tracked_name = name
		_camera.follow(_agents[name]["node"])


func _on_stop_requested() -> void:
	# Releasing the camera emits follow_stopped, which clears _tracked_name (and so
	# lifts the fog) via _on_follow_stopped.
	_camera.stop_following()


func _on_follow_stopped() -> void:
	# The camera stopped following (Stop button, manual pan, Reset). Drop the tracked
	# agent so the perception fog lifts on the next frame.
	_tracked_name = ""


func _setup_fog() -> void:
	# Build the perception-fog overlay: a full-screen grey ColorRect, driven by
	# perception_fog.gdshader, on its own CanvasLayer. Layer 1 sits it ABOVE the
	# world (the root canvas, layer 0 -- map, sprites, trails, links) yet BELOW the
	# UI (the tscn's UI CanvasLayer is layer 10), so the fog dims the campus but never
	# the sidebar or minimap. Hidden until you Track an agent; _update_fog drives it.
	_fog = CanvasLayer.new()
	_fog.layer = 1
	add_child(_fog)

	_fog_mat = ShaderMaterial.new()
	_fog_mat.shader = load("res://shaders/perception_fog.gdshader")
	_fog_mat.set_shader_parameter("feather", FOG_FEATHER_PX)
	_fog_mat.set_shader_parameter("cover_color", FOG_COLOR)

	_fog_rect = ColorRect.new()
	_fog_rect.material = _fog_mat
	_fog_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	# Let clicks, drags and hovers pass straight through to the map and the agents
	# beneath -- the fog is a visual wash, not an input catcher.
	_fog_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_fog_rect.visible = false
	_fog.add_child(_fog_rect)


func _update_fog() -> void:
	# Centre the clear circle on the tracked agent each frame (it walks, the camera
	# follows, and the window can resize), or hide the whole overlay when nothing is
	# tracked. Everything is computed in the overlay's own screen pixels: the canvas
	# transform maps the agent's world position to the screen and carries the camera
	# zoom, so the radius (vision_r tiles, in world pixels) scales with how far you're
	# zoomed in -- the fog's clear circle always covers exactly the agent's perception.
	if _fog == null:
		return
	if _tracked_name == "" or not _agents.has(_tracked_name):
		_fog_rect.visible = false
		return

	var node: Node2D = _agents[_tracked_name]["node"]
	var xform := get_viewport().get_canvas_transform()
	var center: Vector2 = xform * node.global_position
	var zoom := xform.get_scale().x
	var radius := float(_vision_r) * float(_tile_px) * zoom
	var size := get_viewport().get_visible_rect().size

	_fog_rect.size = size
	_fog_rect.visible = true
	_fog_mat.set_shader_parameter("rect_size", size)
	_fog_mat.set_shader_parameter("center", center)
	_fog_mat.set_shader_parameter("radius", radius)


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
			# The current activity shows in the sidebar row (not as a map bubble).
			var act := String(a["act"]).split(" @ ")[0]
			_panel.set_character_status(name, "%s %s" % [a["e"], act])
			_update_agent_speech(name, a, i)

	# Bubbles + links refresh every frame (not just on a step change) so the
	# turn-taking + fade play out smoothly as the playhead advances within a step.
	for name in _names:
		_refresh_bubble(name, fpos)
	_refresh_links(fpos)

	# Dim everything outside the tracked agent's perception radius (no-op when free).
	_update_fog()

	# Web: tell the React companion panel which step we're showing, so its agent
	# card + memory list track the canvas. Godot is the clock; we push only on a
	# step change. `window.__pennReplayStep` is registered by the web shell and is
	# simply absent on a plain export, where this whole call is a harmless no-op.
	if _is_web and i != _last_step:
		_last_step = i
		JavaScriptBridge.eval(
			"window.__pennReplayStep && window.__pennReplayStep(%d)" % i, true
		)


func _update_agent_speech(name: String, frame: Dictionary, step: int) -> void:
	# Detect the start of a conversation by diffing this agent's `chat` against last
	# step's. `chat` is a list of [speaker, line] pairs shared by both talkers (or
	# null/absent when silent), and it lingers after the talk ends — so we react only
	# to a *change*, then show the bubble for a fixed, fading window. The mock brain
	# never fills `chat`, so this is a no-op there (activity bubbles still show).
	var chat: Variant = frame.get("chat")
	if chat != null and chat is Array and not (chat as Array).is_empty() \
			and chat != _last_chat.get(name):
		# A new exchange: keep the whole transcript and start playing it from now,
		# one line at a time (see _refresh_bubble). `chat` is sticky in the replay,
		# so the `!=` guard starts the playback once, not every step.
		var lines: Array = []
		for pair in chat:
			if pair is Array and (pair as Array).size() >= 2:
				lines.append([String(pair[0]), _clip(String(pair[1]))])
		_convo_lines[name] = lines
		_convo_start[name] = float(step)
		_convo_partner[name] = _other_speaker(chat, name)
		_bubble_idx[name] = -1
	_last_chat[name] = chat


func _other_speaker(chat: Array, name: String) -> String:
	# The first speaker in the transcript who isn't this agent — their conversation
	# partner, used to draw the link.
	for pair in chat:
		if pair is Array and pair.size() >= 1 and String(pair[0]) != name:
			return String(pair[0])
	return ""


func _clip(text: String) -> String:
	if text.length() <= BUBBLE_MAX_CHARS:
		return text
	return text.substr(0, BUBBLE_MAX_CHARS - 1).strip_edges() + "…"


func _refresh_bubble(name: String, fpos: float) -> void:
	# Play this agent's conversation back one line at a time: show its bubble only
	# during the slots where IT is the speaker (with that line's text), and hide it
	# on the partner's turns and once the exchange is over -- so the dialogue reads
	# as staggered turn-taking rather than both agents speaking at once.
	var bubble: Label = _agents[name]["bubble"]
	var lines: Array = _convo_lines.get(name, [])
	if lines.is_empty():
		bubble.visible = false
		return
	var elapsed := fpos - float(_convo_start.get(name, 0.0))
	var total := float(lines.size()) * DIALOGUE_LINE_STEPS
	if elapsed < 0.0 or elapsed >= total:
		bubble.visible = false
		return

	var idx := int(elapsed / DIALOGUE_LINE_STEPS)  # whose turn it is right now
	var pair: Array = lines[idx]
	if String(pair[0]) != name:
		bubble.visible = false  # the partner is speaking this turn
		return

	if _bubble_idx.get(name, -1) != idx:
		_bubble_idx[name] = idx
		bubble.text = String(pair[1])
	bubble.visible = true
	# Ease in at the start of the line and out at its end, for a spoken beat.
	var within := elapsed - float(idx) * DIALOGUE_LINE_STEPS
	var fade_in := clampf(within, 0.0, 1.0)
	var fade_out := clampf((DIALOGUE_LINE_STEPS - within) / DIALOGUE_FADE_STEPS, 0.0, 1.0)
	bubble.modulate.a = minf(fade_in, fade_out)


func _refresh_links(fpos: float) -> void:
	# A link joins a pair for the whole length of their exchange (across both turns),
	# even though only one of them shows a bubble at a time. Lines are pooled by pair
	# key and just hidden when idle, so a replay never churns Line2D nodes.
	var active := {}
	for name in _names:
		var lines: Array = _convo_lines.get(name, [])
		if lines.is_empty():
			continue
		var elapsed := fpos - float(_convo_start.get(name, 0.0))
		var total := float(lines.size()) * DIALOGUE_LINE_STEPS
		if elapsed < 0.0 or elapsed >= total:
			continue
		var partner := String(_convo_partner.get(name, ""))
		if partner == "" or not _agents.has(partner):
			continue
		var key: String = (name + "\n" + partner) if name < partner else (partner + "\n" + name)
		active[key] = [name, partner, total - elapsed]

	for key in _link_lines:
		(_link_lines[key] as Line2D).visible = active.has(key)

	for key in active:
		var entry: Array = active[key]
		var line := _link_line(key)
		line.visible = true
		line.points = PackedVector2Array(
			[
				_agents[entry[0]]["node"].position,
				_agents[entry[1]]["node"].position,
			]
		)
		line.modulate.a = clampf(float(entry[2]) / DIALOGUE_FADE_STEPS, 0.0, 1.0)


func _link_line(key: String) -> Line2D:
	# Lazily create (then reuse) the Line2D for a conversation pair.
	if _link_lines.has(key):
		return _link_lines[key]
	var line := Line2D.new()
	line.width = 6.0
	line.default_color = Color(1.0, 0.78, 0.30, 0.9)  # warm, like a chat highlight
	line.begin_cap_mode = Line2D.LINE_CAP_ROUND
	line.end_cap_mode = Line2D.LINE_CAP_ROUND
	line.antialiased = true
	_links_node.add_child(line)
	_link_lines[key] = line
	return line
