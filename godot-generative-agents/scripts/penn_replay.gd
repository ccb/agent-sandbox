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

# Speech/thought bubbles float above the nameplate. A bubble is this wide (its
# text wraps and centres inside); position.x = -half that centres it over the sprite.
const BUBBLE_WIDTH := 280.0
# A conversation bubble (and its link) shows for this many sim steps from the moment
# the dialogue first appears, fading out over the last FADE steps. The replay's
# `chat` field is *sticky* (it lingers on an agent until their next conversation),
# so we time-box the bubble ourselves rather than leave it up forever.
const BUBBLE_HOLD_STEPS := 6.0
const BUBBLE_FADE_STEPS := 2.0
# Long utterances are clipped so a bubble stays a couple of lines tall.
const BUBBLE_MAX_CHARS := 140

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
# Web only: push the current step to the page so the React companion panel can
# follow the replay. `_is_web` gates the JS calls to web exports; `_last_step`
# (-1 = none pushed yet) lets us call out only when the integer step changes.
var _is_web := false
var _last_step := -1

# In-world expressiveness: a bubble above each agent (their latest line while in a
# conversation, otherwise their current activity) plus a link between two agents who
# are talking. See _refresh_bubble / _refresh_links.
var _show_activity_bubbles := true
var _last_chat := {}        # name -> the `chat` value seen last step (for onset diff)
var _speech_text := {}      # name -> the line to show in the speech bubble
var _activity_text := {}    # name -> "emoji activity" for the activity bubble
var _bubble_until := {}     # name -> sim step (float) the speech bubble fades out at
var _convo_partner := {}    # name -> the other speaker's name, for the link
var _bubble_mode := {}      # name -> "speech" | "activity" | "" (so we restyle only on change)
var _links_node: Node2D     # parents one Line2D per active conversation pair
var _link_lines := {}       # sorted "A\nB" pair key -> Line2D
var _speech_style: StyleBoxFlat
var _thought_style: StyleBoxFlat

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

	# The sidebar overlays the left edge; tell the camera its width so the pan/zoom
	# clamp frames the map into the open area to its right (campus never hides under
	# the bar). Seed from custom_minimum_size (set in the panel's _ready, which runs
	# first) and follow any later layout/theme resize.
	_camera.set_left_inset(_panel.custom_minimum_size.x)
	_panel.resized.connect(func() -> void: _camera.set_left_inset(_panel.size.x))

	# Playback controls: pause/resume, seek along the timeline, change speed.
	_panel.play_pause_requested.connect(_on_play_pause)
	_panel.seek_requested.connect(_on_seek)
	_panel.speed_changed.connect(func(m: float) -> void: _speed = m)
	_panel.set_playing(not _paused)

	# A clock-driven tint over the 2D world (the screen-space UI layer is unaffected),
	# so the campus warms/dims with the in-game time of day.
	_sky = CanvasModulate.new()
	add_child(_sky)

	# In-world bubbles: the sidebar can hide the always-on activity bubbles (handy
	# once the cast grows and they overlap); speech bubbles for live conversations
	# always show. The checkbox defaults on, matching _show_activity_bubbles.
	_panel.bubbles_toggled.connect(func(on: bool) -> void: _show_activity_bubbles = on)
	_speech_style = _make_bubble_style(Color(1.0, 1.0, 1.0, 0.92))
	_thought_style = _make_bubble_style(Color(0.96, 0.97, 1.0, 0.78))
	# Conversation links live above the campus (runtime children draw over the tscn's
	# map) but below the agent sprites (added later still), so a line sits under the
	# people it connects.
	_links_node = Node2D.new()
	add_child(_links_node)

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
	# Park the single-line nameplate just above the sprite's head (the ~50px covers
	# the one text line), so it tracks the sprite size instead of overlapping it.
	# The current activity lives in the sidebar, so the label only shows the name.
	label.position = Vector2(-110, -(SPRITE_HALF_PX + 50.0))
	label.custom_minimum_size = Vector2(220, 0)
	node.add_child(label)

	# A speech/thought bubble parked above the nameplate; hidden until there's
	# something to show. _refresh_bubble fills it and fades it per step.
	var bubble := Label.new()
	bubble.add_theme_font_size_override("font_size", 24)
	bubble.add_theme_color_override("font_color", Color(0.12, 0.10, 0.08))
	bubble.add_theme_stylebox_override("normal", _thought_style)
	bubble.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	bubble.custom_minimum_size = Vector2(BUBBLE_WIDTH, 0)
	# Centre it over the sprite and park it above the nameplate (which sits at
	# -(half + 50)); it grows downward from here but the clip keeps it short.
	bubble.position = Vector2(-BUBBLE_WIDTH / 2.0, -(SPRITE_HALF_PX + 50.0 + 110.0))
	bubble.visible = false
	node.add_child(bubble)

	_agents[name] = {"node": node, "sprite": spr, "label": label, "bubble": bubble}


func _make_bubble_style(bg: Color) -> StyleBoxFlat:
	# A soft rounded card behind the bubble text — speech (opaque white) and thought
	# (paler) reuse this with different fills.
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.set_corner_radius_all(12)
	sb.set_content_margin_all(8.0)
	sb.set_border_width_all(2)
	sb.border_color = Color(0.0, 0.0, 0.0, 0.25)
	return sb


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
			_activity_text[name] = "%s %s" % [a["e"], act]
			_panel.set_character_status(name, _activity_text[name])
			_update_agent_speech(name, a, i)
			# Keep an already-showing activity bubble's text current for this step.
			if _bubble_mode.get(name, "") == "activity":
				(_agents[name]["bubble"] as Label).text = _activity_text[name]

	# Bubbles + links refresh every frame (not just on a step change) so the fade is
	# smooth as the playhead advances within a step.
	for name in _names:
		_refresh_bubble(name, fpos)
	_refresh_links(fpos)

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
		_speech_text[name] = _clip(_latest_line_by(chat, name))
		_convo_partner[name] = _other_speaker(chat, name)
		_bubble_until[name] = float(step) + BUBBLE_HOLD_STEPS
	_last_chat[name] = chat


func _latest_line_by(chat: Array, name: String) -> String:
	# The agent's own most recent utterance in the transcript (falling back to the
	# last line if they somehow never speak in it).
	var line := ""
	for pair in chat:
		if pair is Array and pair.size() >= 2 and String(pair[0]) == name:
			line = String(pair[1])
	if line == "" and not chat.is_empty():
		var last_pair: Variant = chat[chat.size() - 1]
		if last_pair is Array and (last_pair as Array).size() >= 2:
			line = String(last_pair[1])
	return line


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
	# Pick the bubble's mode for the current playhead: a speech bubble while the
	# agent is inside its conversation window, else the activity bubble (if enabled),
	# else hidden. Text + stylebox change only when the mode flips; alpha animates.
	var bubble: Label = _agents[name]["bubble"]
	var until: float = _bubble_until.get(name, -1.0)
	var activity: String = String(_activity_text.get(name, ""))
	var mode := ""
	if fpos <= until:
		mode = "speech"
	elif _show_activity_bubbles and activity != "":
		mode = "activity"

	if mode == "":
		bubble.visible = false
		_bubble_mode[name] = ""
		return

	if _bubble_mode.get(name, "") != mode:
		_bubble_mode[name] = mode
		if mode == "speech":
			bubble.text = String(_speech_text.get(name, ""))
			bubble.add_theme_stylebox_override("normal", _speech_style)
		else:
			bubble.text = activity
			bubble.add_theme_stylebox_override("normal", _thought_style)

	bubble.visible = true
	bubble.modulate.a = (
		clampf((until - fpos) / BUBBLE_FADE_STEPS, 0.0, 1.0) if mode == "speech" else 1.0
	)


func _refresh_links(fpos: float) -> void:
	# Draw a line between each pair mid-conversation right now (this agent inside its
	# speech window with a known, present partner). Lines are pooled by pair key and
	# just hidden when idle, so a replay never churns Line2D nodes.
	var active := {}
	for name in _names:
		var until: float = _bubble_until.get(name, -1.0)
		if fpos > until:
			continue
		var partner := String(_convo_partner.get(name, ""))
		if partner == "" or not _agents.has(partner):
			continue
		var key: String = (name + "\n" + partner) if name < partner else (partner + "\n" + name)
		var rem_other: float = _bubble_until.get(partner, -1.0) - fpos
		active[key] = [name, partner, minf(until - fpos, rem_other)]

	for key in _link_lines:
		(_link_lines[key] as Line2D).visible = active.has(key)

	for key in active:
		var entry: Array = active[key]
		var line := _link_line(key)
		line.visible = true
		line.points = PackedVector2Array([
			_agents[entry[0]]["node"].position,
			_agents[entry[1]]["node"].position,
		])
		line.modulate.a = clampf(float(entry[2]) / BUBBLE_FADE_STEPS, 0.0, 1.0)


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
