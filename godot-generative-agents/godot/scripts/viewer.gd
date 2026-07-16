extends Node2D
## Plays a UPenn agent-simulation replay on the campus map.
##
## The Python sim (backend/penn/generate_penn_replay.py) writes maps/penn_replay.json:
## per step, each persona's tile (x, y) + current activity + emoji. This scene
## renders the campus (a sibling TileMapLayer running tiled_map.gd) and animates
## one Cute Fantasy sprite per persona, easing it tile-to-tile along its path —
## so you watch Maya, Professor Ellis and Diego walk the real campus. No agent
## logic here; this is purely the viewer (the sim already decided everything).
##
## With a backend URL configured (live_backend_url / SIM_API_URL), the same
## scene instead FOLLOWS a running sim live (issue #263): a GET /live handshake
## spawns the cast, GET /events backfills history, and a WebSocket to /ws
## streams each new step (backend/penn/serve_penn.py is the matching server). Frames
## land in the same _frames array, so playback and every feature work
## unchanged; only the scrubber locks (you can't seek a live stream).

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
## Run-monitor HUD (issue #264): base URL of a RUNNING backend (backend/api.py),
## e.g. "http://127.0.0.1:8000". Empty (the default) = baked-replay mode, where
## the top-right monitor shows clearly-labeled SIMULATED usage so the HUD is
## demoable without spending money. Set a URL (or the SIM_API_URL env var, which
## needs no editor visit) and the same HUD polls the real GET /usage + /health
## and drives POST /pause — nothing else changes when real LLMs arrive.
@export var live_backend_url: String = ""
## Bearer token for the live backend (its SIM_API_TOKEN, issue #186); falls back
## to the SIM_API_TOKEN env var when empty. Ignored in baked-replay mode.
@export var live_api_token: String = ""

## Take the backend down when this window closes (live mode): POST /shutdown,
## so a paying real-LLM sim never keeps running — or spending — unwatched.
@export var shutdown_backend_on_exit := true

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

# Location spotlight (sidebar "Focus" dropdown, issue #250): pick a building and every
# agent NOT currently in it fades out. The sprite (and its nameplate/bubble, which ride
# its node.modulate) drop to this alpha; the trail (parented separately under _trails)
# fades harder so it doesn't clutter the dimmed background.
const SPOTLIGHT_DIM_ALPHA := 0.35
const TRAIL_DIM_ALPHA := 0.18

# Marker collection for the timeline strip (issue #249) — also the single home
# of the act-address building parser (_building_of delegates to it).
const ReplayMarkers := preload("res://scripts/replay_markers.gd")
const GifEncoder := preload("res://scripts/gif_encoder.gd")
const ClipExport := preload("res://scripts/clip_export.gd")
const ThinkingIndicator := preload("res://scripts/thinking_indicator.gd")
const LivePacer := preload("res://scripts/live_pacer.gd")

var _tile_px := 16
var _sec_per_step := 10
var _start_unix := 0
var _frames: Array = []
var _names: Array = []
var _agents := {}  # name -> {sprite, label}
# Persona "State Details" inspector (issue #408). `_persona_detail` is the static
# per-agent detail from the replay/live meta (name/emoji/persona/home/schedule),
# keyed by name; `_memory_streams` is each persona's full memory history (baked
# replay only -- empty in live mode, where the inspector falls back to the
# retrieved-this-step memories in the frame). `_inspector_name` is the persona the
# modal is currently showing ("" = closed).
var _persona_detail := {}
var _memory_streams := {}
var _inspector_name := ""
var _t := 0.0
var _anim_t := 0.0
var _paused := false
var _speed := 1.0
var _last_status_step := -1         # last frame index pushed to the sidebar rows
# Location spotlight (see SPOTLIGHT_DIM_ALPHA). `_filter_location` is the building the
# sidebar Focus dropdown selected ("" = All, no filter); `_agent_location` caches each
# agent's building for the current step (parsed from its `act`), so the spotlight and
# the dropdown agree on where everyone is.
var _filter_location := ""
var _agent_location := {}           # name -> building this step
var _sky: CanvasModulate            # clock-driven day-night tint over the campus
var _trails: Node2D                 # parent of the per-agent breadcrumb Line2Ds
# Web only: push the current step to the page so the React companion panel can
# follow the replay. `_is_web` gates the JS calls to web exports; `_last_step`
# (-1 = none pushed yet) lets us call out only when the integer step changes.
var _is_web := false
var _last_step := -1
# Heatmap pop-up: the last step pushed into it, so we only recompute the (live) heat
# when the integer step actually changes while it's open (see _process).
var _last_heat_step := -1
# Social-graph pop-up (issue #252): same push-on-step-change guard as the heatmap,
# plus the seed relationships from the replay/live meta (meta.relationships; [] for
# a pre-#252 replay or backend, which the panel renders as an empty seed view).
var _last_graph_step := -1
var _relationships: Array = []

# Step the day-plans pop-up last drew (same push-on-change contract as the
# heatmap/social graph, issue #251).
var _last_plan_step := -1

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
# Clip export (issue #488): the marked in/out step span, -1 = unset. [ sets in,
# ] sets out; the panel highlights the span and enables Export when both are set.
var _clip_in := -1
var _clip_out := -1
var _fog: CanvasLayer
var _fog_rect: ColorRect
var _fog_mat: ShaderMaterial

# Run-monitor HUD (issue #264): `_hud_source` feeds the top-right monitor —
# hud_source_replay.gd (simulated spend) in baked-replay mode, hud_source_live.gd
# (real GET /usage + /health polls) when live_backend_url points at a backend.
# `_run_halted` mirrors the source's halted state (Emergency Stop pressed);
# `_hud_running` is the last is-playback-advancing value pushed to the source,
# so the simulated meter only accrues while the replay actually plays.
var _hud_source: Node
var _run_halted := false
var _hud_running := false

# Live-client mode (issue #263): with a backend URL configured (the same
# live_backend_url / SIM_API_URL the run monitor uses), the viewer follows the
# backend's RUNNING sim instead of loading a baked file: one GET /live handshake
# (meta -> spawn agents), one GET /events backfill (history so far), then a
# WebSocket to /ws applying each pushed record as it lands. Frames land in the
# same _frames array the baked path fills, so the clock, bubbles, links, trails,
# minimap, heatmap and fog all work unchanged -- playback simply chases the
# growing array (the _t clamp in _process). `_last_cursor` is the change-feed
# cursor of the newest record applied; the socket reconnects with ?since= it,
# so a drop loses nothing and re-applies nothing (records at or below it are
# skipped as duplicates).
var _is_live := false
# Live "thinking" cue (issue #372): wall-clock ms when the live head last grew,
# and whether the cue is currently showing (so the sidebar text flips on edges).
const THINKING_STALL_MS := 1500
# Live interpolation buffer (issue #372): hold ~LEAD_TARGET ticks of lead so
# motion stays smooth across irregular arrivals; drain a post-stall backlog at
# up to CATCHUP_MAX x the normal rate rather than teleporting. See LivePacer.
const LEAD_TARGET := 2.0
const CATCHUP_MAX := 3.0
var _last_frame_ms := 0
var _thinking := false
var _thinking_badge: Control
var _live_url := ""
var _live_token := ""
var _ws: WebSocketPeer = null
var _ws_open := false
var _last_cursor := -1
var _live_started := false          # first backfill applied -> jump to the live head
var _reconnect_delay := 1.0         # doubles per failure, capped; reset on connect
var _retry_pending := false
var _handshake_http: HTTPRequest    # GET /live (its own node: HTTPRequest is one-shot)
var _events_http: HTTPRequest       # GET /events backfill
var _reset_http: HTTPRequest = null
var _live_buildings := {}           # Focus-dropdown entries discovered so far (a set)
var _backend_run_state := ""        # ""/waiting/running/paused/finished/stopped
var _quitting := false              # window close in progress (shutdown then quit)

@onready var _camera: Camera2D = $Camera2D
@onready var _panel = $UI/AgentPanel  # agent_panel.gd sidebar
@onready var _minimap = $UI/Minimap  # minimap.gd bottom-right overview
@onready var _hud = $UI/LiveHud  # live_hud.gd top-right run monitor
@onready var _heatmap = $HeatmapLayer/HeatmapPanel  # heatmap_panel.gd heatmap pop-up
@onready var _inspector = $PersonaInspectorLayer/PersonaInspector  # persona_inspector.gd
@onready var _social_graph = $SocialGraphLayer/SocialGraphPanel  # social_graph_panel.gd
@onready var _gallery = $SnapshotLayer/SnapshotGallery  # snapshot_gallery.gd snapshot pop-up
@onready var _day_plans = $DayPlanLayer/DayPlanPanel  # day_plan_panel.gd pop-up (#251)
@onready var _building_labels = $BuildingLabels  # building_labels.gd (for center_of)


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
	_panel.clip_export_requested.connect(_export_clip)
	_panel.speed_changed.connect(func(m: float) -> void: _speed = m)
	_panel.set_playing(not _paused)

	# Movement-heatmap pop-up: the sidebar button (or the H key) opens it; its own close
	# button / a click outside / Esc closes it. It's fed the replay after load.
	_panel.heatmap_requested.connect(_toggle_heatmap)
	_heatmap.close_requested.connect(_close_heatmap)

	# Social-graph pop-up (issue #252): same contract as the heatmap — the sidebar
	# button (or the G key) toggles it, and it's fed the replay + seed edges after load.
	_panel.social_graph_requested.connect(_toggle_social_graph)
	_social_graph.close_requested.connect(_close_social_graph)

	# Day-plans pop-up (issue #251): the sidebar calendar button (or T) toggles
	# it; ribbon clicks seek through the same path as the scrubber (_on_seek
	# already ignores seeks in live mode).
	_panel.day_plans_requested.connect(_toggle_day_plans)
	_day_plans.close_requested.connect(_close_day_plans)
	_day_plans.seek_requested.connect(_on_seek)

	# Snapshot capture + gallery pop-up (issue #253): the camera button (or C) captures
	# the current campus view into the gallery; the gallery button toggles the pop-up of
	# captures taken this session. Both live only in memory (no file export yet).
	_panel.snapshot_requested.connect(_take_snapshot)
	# The live "thinking…" overlay (issue #372) lives on the same UI layer as the
	# sidebar so it draws in screen space above the world; hidden until a stall.
	_thinking_badge = preload("res://scripts/thinking_badge.gd").new()
	$UI.add_child(_thinking_badge)
	_panel.gallery_requested.connect(_toggle_gallery)
	_gallery.close_requested.connect(_close_gallery)

	# Persona State Details inspector (issue #408): the sidebar's ⓘ button opens it
	# per agent; the P key opens it for whoever's tracked; its close button / a click
	# outside / Esc closes it. Fed the persona detail + the live step by the viewer.
	_panel.inspect_requested.connect(_open_inspector)
	_inspector.close_requested.connect(_close_inspector)

	# Location spotlight: the sidebar's Focus dropdown picks a building; we dim everyone
	# not there and glide the view to it. The dropdown's building list is filled after
	# the replay loads (see _load_replay_from_text).
	_panel.filter_changed.connect(_on_filter_changed)

	# The sidebar's back button returns to the landing menu (issue #399). Unlike a
	# window close it leaves any live backend running (see _on_back_to_menu).
	_panel.back_to_menu_requested.connect(_on_back_to_menu)

	# The top-right run monitor and its data source (simulated or live).
	_setup_hud()

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

	# A replay picked on the landing menu (bundled or a local file, issue #399)
	# overrides the exported default path. Live and direct launches leave it be.
	if LaunchConfig.mode == LaunchConfig.Mode.REPLAY and LaunchConfig.replay_path != "":
		replay_path = LaunchConfig.replay_path

	_is_web = OS.has_feature("web")
	# With a backend configured, follow its live sim (issue #263) -- the same
	# setting that put the run-monitor HUD in live mode, so one URL flips the
	# whole scene. Otherwise: desktop reads the replay straight off disk; web
	# fetches it over HTTP so a new sim never needs a re-export.
	if _resolve_backend_url() != "":
		_start_live()
	elif _is_web:
		_load_replay_web()
	else:
		_load_replay_desktop()


func _setup_hud() -> void:
	# Pick the run monitor's data feed (issue #264). Both sources speak the same
	# contract (hud_source.gd), so this is the ONLY place that knows which mode
	# we're in — the HUD and the wiring below are identical either way, which is
	# what makes the switch to a real-LLM backend a one-line configuration.
	var url := _resolve_backend_url()
	if url != "":
		_hud_source = preload("res://scripts/hud_source_live.gd").new()
		_hud.set_source_label("live: %s" % url)
	else:
		# Baked-replay mode: there's no live run to watch and no real money
		# spent, so hide the whole run monitor (cost meter + LLM request log)
		# rather than show synthesized figures that read like a real bill. The
		# replay source is still created and wired below so the viewer's
		# unconditional _hud_source calls (set_cast, set_running) stay valid —
		# it just feeds a hidden panel.
		_hud_source = preload("res://scripts/hud_source_replay.gd").new()
		_hud.visible = false

	# Connect BEFORE add_child: a source seeds the HUD (initial health + zeroed
	# meter) from its _ready, which runs inside add_child — connect after and
	# those first emissions are lost, leaving the status row blank.
	_hud_source.usage_updated.connect(_hud.set_usage)
	_hud_source.health_changed.connect(_hud.set_health)
	_hud_source.halted_changed.connect(_on_run_halted)
	_hud_source.llm_call.connect(_hud.add_llm_call)
	_hud_source.engine_event.connect(_hud.add_engine_event)
	_hud.stop_requested.connect(_hud_source.request_stop)
	add_child(_hud_source)

	if url != "":
		_hud_source.configure(url, _resolve_backend_token())
		# The sidebar's Start/Stop toggle shares the same control path as the
		# HUD's Emergency stop; both states sync via the feed's status records.
		_panel.live_run_toggle_requested.connect(_on_live_run_toggle)


func _resolve_backend_url() -> String:
	# The one switch between baked-replay and live mode, shared by the HUD and
	# the live client. The landing menu's explicit choice (LaunchConfig) wins when
	# set — a menu-chosen replay must stay a replay even if SIM_API_URL is exported
	# in the shell, and a menu-chosen live URL beats the (unset) export. With no
	# menu choice (mode NONE: a direct launch), fall back to the export, then the
	# SIM_API_URL env var. Empty = baked replay.
	if LaunchConfig.mode == LaunchConfig.Mode.REPLAY:
		return ""
	if LaunchConfig.mode == LaunchConfig.Mode.LIVE:
		return LaunchConfig.live_url.rstrip("/")
	var url := live_backend_url
	if url == "":
		url = OS.get_environment("SIM_API_URL")
	return url.rstrip("/")


func _resolve_backend_token() -> String:
	if LaunchConfig.mode == LaunchConfig.Mode.LIVE:
		return LaunchConfig.live_token
	var token := live_api_token
	if token == "":
		token = OS.get_environment("SIM_API_TOKEN")
	return token


func _on_run_halted(halted: bool) -> void:
	# The source confirmed an Emergency Stop (or a resume) — reflect it in the
	# HUD, and freeze the replay playback too so the whole scene reads as halted
	# (in live mode the backend loop is what actually paused; stopping the local
	# playback as well keeps the picture consistent).
	_run_halted = halted
	_hud.set_halted(halted)
	if halted and not _paused:
		_paused = true
		_panel.set_playing(false)


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

	_apply_meta(data["meta"])
	_frames = data["frames"]
	# The per-persona full memory history, for the State Details inspector's memory
	# stream (issue #408). Baked replays carry it; a payload without it (or the live
	# feed) leaves this empty and the inspector shows only the retrieved-this-step set.
	_memory_streams = data.get("memory_streams", {})

	# The timeline's "interesting moments" (issue #249): game events (#476 —
	# this is the baked events key's first consumer), chat onsets, reflections,
	# arrivals. One scan at load; live mode never gets here (no scrubber).
	_panel.set_timeline_markers(
		ReplayMarkers.collect(_frames, _names, _memory_streams, data.get("events", [])),
		maxi(_frames.size() - 1, 0))

	# Fill the sidebar's Focus dropdown with every building the cast visits over the whole
	# replay (a one-time scan of all frames), sorted, so the option list is stable as the
	# sim plays. The building is the middle segment of each `act` address (see _building_of).
	var buildings := {}  # used as a set
	for frame in _frames:
		for name in _names:
			var b := _building_of(String((frame[name] as Dictionary)["act"]))
			if b != "":
				buildings[b] = true
	var sorted_buildings := buildings.keys()
	sorted_buildings.sort()
	_panel.set_locations(PackedStringArray(sorted_buildings))

	# Size the timeline to the replay (frames are 0..last) and seed the readout.
	var last := maxi(_frames.size() - 1, 0)
	_panel.set_progress(preview_step, last)

	# Place everyone on their first frame, then optionally fast-forward the clock.
	_t = preview_step * step_seconds
	_anim_t = 0.0
	_update_clock()

	# Hand the whole replay to the heatmap pop-up so it can build its campus picture now
	# (avoiding a blank first-open frame) and tally dwell up to any step on demand.
	_heatmap.set_replay(_frames, _names, _tile_px)
	# And to the social-graph pop-up (issue #252), with the seed relationships the
	# meta carried, so it can accumulate conversations up to any step on demand.
	_social_graph.set_replay(_frames, _names, _relationships)

	# And to the day-plans pop-up (issue #251): schedules from the meta's
	# persona detail, actuals derived from the same by-reference frame buffer.
	_day_plans.set_replay(_frames, _names, _persona_detail)

	# Tell the run monitor's source who the cast is, so its per-actor spend
	# attribution matches the real ledger's by_actor rollup.
	_hud_source.set_cast(_names)
	print("penn_replay: %d steps, %d personas" % [_frames.size(), _names.size()])


func _apply_meta(meta: Dictionary) -> void:
	# World shape + cast, shared verbatim by the baked loader and the live
	# handshake (issue #263) -- so an agent spawns identically either way.
	_tile_px = int(meta["tile_px"])
	_sec_per_step = int(meta.get("sec_per_step", 10))
	# Perception radius for the tracking fog -- the sim's vision_r, falling back to
	# the Smallville default for older replays that don't record it.
	_vision_r = int(meta.get("vision_r", FOG_FALLBACK_VISION_R))
	_start_unix = _parse_sim_start(String(meta.get("start", sim_start)))
	# The authored t=0 seed social graph for the social-graph pop-up (issue #252).
	# Older replays/backends don't carry the key; [] just means an empty seed view.
	_relationships = meta.get("relationships", [])
	var thumb := _make_thumbnail()
	for i in meta["personas"].size():
		var persona: Dictionary = meta["personas"][i]
		var pname: String = persona["name"]
		var tint: Color = TINTS[i % TINTS.size()]
		_names.append(pname)
		# Keep the full persona entry for the State Details inspector (issue #408).
		# Newer metas carry persona/home/schedule; an older/minimal meta with just
		# name/emoji still spawns fine and the inspector degrades on the missing keys.
		_persona_detail[pname] = persona
		_spawn_agent(pname, i)
		# Mirror the world sprite's tint in the sidebar and on the minimap dot, so the
		# three views of each character all agree at a glance.
		_panel.add_character(pname, thumb, tint)
		_minimap.add_agent(pname, _agents[pname]["node"], tint)


func _spawn_from_meta(meta: Dictionary) -> void:
	# Spawn the cast + hand the (by-reference) frame buffer to the heatmap and
	# social graph, then seed the run monitor + clock. Shared by the initial live
	# handshake and the reset-follow path (#393) so a reset spawns identically.
	_apply_meta(meta)
	# The heatmap holds _frames BY REFERENCE, so the live appends flow into it --
	# same hand-off the baked path does, just with an empty array now.
	_heatmap.set_replay(_frames, _names, _tile_px)
	# Same by-reference hand-off for the social graph; its seed view is meaningful
	# right away, before the first frame ever arrives.
	_social_graph.set_replay(_frames, _names, _relationships)
	# Day-plans pop-up: same by-reference hand-off, so live frames flow into
	# the actual ribbons as they arrive (planned is known from the meta now).
	_day_plans.set_replay(_frames, _names, _persona_detail)
	_hud_source.set_cast(_names)
	_update_clock()


# --- Live-client mode (issue #263) -----------------------------------------


func _start_live() -> void:
	# Follow the backend's running sim: handshake -> backfill -> socket. The
	# scene stays healthy with NO backend running -- every step below only
	# warns and retries with backoff, so the campus still paints (and the smoke
	# test still passes) while the viewer waits for a server to appear.
	_is_live = true
	_live_url = _resolve_backend_url()
	_live_token = _resolve_backend_token()
	_panel.set_live(true)
	_panel.set_live_status("connecting to %s…" % _live_url)
	# Closing the window should take the backend down with us (see
	# _shutdown_and_quit): hold the auto-quit so the POST gets out first.
	get_tree().set_auto_accept_quit(false)
	# One HTTPRequest node per concern (they're one-request-at-a-time), the same
	# split hud_source_live.gd uses for its polls.
	_handshake_http = HTTPRequest.new()
	add_child(_handshake_http)
	_handshake_http.request_completed.connect(_on_live_handshake_completed)
	_events_http = HTTPRequest.new()
	add_child(_events_http)
	_events_http.request_completed.connect(_on_events_completed)
	_reset_http = HTTPRequest.new()
	add_child(_reset_http)
	_reset_http.request_completed.connect(_on_reset_meta_completed)
	_request_handshake()


func _live_headers() -> PackedStringArray:
	var headers := PackedStringArray()
	if _live_token != "":
		headers.append("Authorization: Bearer %s" % _live_token)
	return headers


func _request_handshake() -> void:
	var err := _handshake_http.request("%s/live" % _live_url, _live_headers())
	if err != OK and err != ERR_BUSY:
		push_warning("penn_replay: live handshake request failed (%d); retrying" % err)
		_schedule_retry(_request_handshake)


func _on_live_handshake_completed(
	_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	if code != 200:
		push_warning("penn_replay: GET /live returned HTTP %d; retrying" % code)
		_panel.set_live_status("waiting for backend…")
		_schedule_retry(_request_handshake)
		return
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(data) != TYPE_DICTIONARY or not bool((data as Dictionary).get("enabled", false)):
		push_warning("penn_replay: backend has no live loop (serve with a stepper); retrying")
		_panel.set_live_status("backend has no live loop…")
		_schedule_retry(_request_handshake)
		return
	var meta: Variant = (data as Dictionary).get("meta")
	if typeof(meta) != TYPE_DICTIONARY:
		push_warning("penn_replay: live handshake carried no meta; retrying")
		_schedule_retry(_request_handshake)
		return

	# A handshake cursor below the newest we've applied can only mean the
	# backend *restarted* — the feed cursor is in-memory and only climbs
	# within one server lifetime, even across resets (#549). Rejoin from
	# scratch: drop the dead run's cast and refetch the new run's history,
	# exactly like a fresh join (the emptied _names respawns below). Default the
	# cursor to _last_cursor so a backend that omits the field (an older server
	# during mixed-version dev) reads as "no rewind", not a rewind to 0.
	if _last_cursor > int((data as Dictionary).get("cursor", _last_cursor)):
		_teardown_cast()
		_last_cursor = -1

	# Spawn the cast once (a handshake retry after a hiccup must not re-spawn).
	if _names.is_empty():
		_spawn_from_meta(meta)
	_panel.set_live_status("catching up…")
	# Seed the sidebar's Start/Stop toggle from the handshake. A backend booted
	# with --start-paused (the --brain llm default) is armed but has never
	# ticked: the day — and its spend — waits behind "▶ Start simulation".
	if bool((data as Dictionary).get("paused", false)):
		_set_backend_run_state(
			"waiting" if int((data as Dictionary).get("step", 0)) == 0 else "paused"
		)
	else:
		_set_backend_run_state("running")
	# The HTTP backfill only earns its double-fetch (the socket's ?since= replay
	# covers the same window) when it still has to place the playhead: the first
	# join and a re-anchor, both of which have _live_started false (a re-anchor's
	# _teardown_cast clears it). A plain reconnect keeps its playhead and lets the
	# socket alone catch up, halving the transfer (#549).
	if not _live_started:
		_request_backfill()
	_connect_ws()


func _request_backfill() -> void:
	# The HTTP catch-up door: everything after the newest record we've applied.
	# ERR_BUSY (a backfill already in flight) is fine to drop -- the socket's
	# ?since= replay covers the same records.
	var err := _events_http.request(
		"%s/events?since=%d" % [_live_url, maxi(_last_cursor, 0)], _live_headers()
	)
	if err != OK and err != ERR_BUSY:
		push_warning("penn_replay: events backfill request failed (%d)" % err)


func _on_events_completed(
	_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	if code != 200:
		push_warning("penn_replay: GET /events returned HTTP %d" % code)
		return
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(data) != TYPE_DICTIONARY:
		return
	for rec in (data as Dictionary).get("events", []):
		_apply_record(rec)
	# A late joiner starts at "now": once the first backfill lands, jump the
	# playhead to the live head (history stays in _frames behind the clamp).
	if not _live_started and not _frames.is_empty():
		_live_started = true
		_t = float(maxi(_frames.size() - 1, 0)) * step_seconds


func _apply_record(rec: Variant) -> void:
	# One change-feed record (either door). The cursor guard makes the socket's
	# replay window and the HTTP backfill overlap-safe: whatever arrives twice
	# is skipped, whatever is newer advances the cursor.
	if typeof(rec) != TYPE_DICTIONARY:
		return
	var record := rec as Dictionary
	var cursor := int(record.get("cursor", -1))
	if cursor >= 0 and cursor <= _last_cursor:
		return  # already applied
	_last_cursor = maxi(_last_cursor, cursor)
	match String(record.get("kind", "")):
		"frame":
			_apply_live_frame(int(record.get("step", -1)), record.get("agents"))
		"status":
			_on_live_status(record)
		"engine":
			# Engine change-feed records ride the same log as frames. The
			# request monitor's llm_call rows (serve_penn's drain_events, #398)
			# go to the HUD's request log; the *other* JSONRenderer events
			# (narration, blocked, ...) rode the same feed but were dropped —
			# they now land in the same event feed too (#394).
			var event: Variant = record.get("event")
			if typeof(event) == TYPE_DICTIONARY and _hud_source != null:
				var ev := event as Dictionary
				if String(ev.get("kind", "")) == "llm_call":
					_hud_source.note_llm_call(ev)
				else:
					_hud_source.note_engine_event(ev)


func _apply_live_frame(step: int, agents: Variant) -> void:
	if step < 0 or typeof(agents) != TYPE_DICTIONARY:
		return
	if _backend_run_state != "running":
		_set_backend_run_state("running")  # frames flowing = the day is on
	# Index-addressed: frame N lands at _frames[N] exactly, so the clock, the
	# trails and the heatmap index the live array the same way they index a
	# baked one. A gap (shouldn't happen -- cursors are contiguous) is padded by
	# holding the previous pose rather than crashing the renderer.
	var prev_size := _frames.size()
	while _frames.size() < step:
		_frames.append(_frames[-1] if not _frames.is_empty() else agents)
	if step == _frames.size():
		_frames.append(agents)
	else:
		_frames[step] = agents
	# A genuinely new step (the head grew) resets the stall clock; a backfill
	# rewrite of an existing index does not (issue #372).
	if _frames.size() > prev_size:
		_last_frame_ms = Time.get_ticks_msec()
	_register_frame_buildings(agents as Dictionary)


func _register_frame_buildings(frame: Dictionary) -> void:
	# The baked loader scans the whole replay once for the Focus dropdown; live
	# mode grows the list as agents reach new buildings.
	var changed := false
	for name in _names:
		if not frame.has(name):
			continue
		var b := _building_of(String((frame[name] as Dictionary).get("act", "")))
		if b != "" and not _live_buildings.has(b):
			_live_buildings[b] = true
			changed = true
	if changed:
		var sorted_buildings := _live_buildings.keys()
		sorted_buildings.sort()
		_panel.set_locations(PackedStringArray(sorted_buildings))


func _on_live_status(record: Dictionary) -> void:
	# Run-state changes ride the same feed as frames; surface them in the
	# sidebar. (The HUD's health dot has its own view via the socket signals.)
	match String(record.get("reason", "")):
		"started", "resumed":
			# "started" can carry paused=true (a --start-paused boot): the day
			# is still behind the sidebar's ▶ Start button.
			if bool(record.get("paused", false)):
				_set_backend_run_state(
					"waiting" if int(record.get("step", 0)) == 0 else "paused"
				)
			else:
				_set_backend_run_state("running")
				_panel.set_live_status("following backend")
		"paused":
			_set_backend_run_state("paused")
			_panel.set_live_status("backend paused")
		"finished":
			_set_backend_run_state("finished")
			_panel.set_live_status("run finished (POST /reset for a new day)")
		"reset":
			_reset_for_new_run()
		"stopped":
			_set_backend_run_state("stopped")
			_panel.set_live_status("backend stopped")


func _reset_for_new_run() -> void:
	# The backend reset into a new day (POST /reset appended a reason:"reset"
	# record). Follow it in place: re-fetch the new run's meta, then (in the
	# callback) tear down the old cast/frames and respawn. _last_cursor and the
	# open socket stay put, so new-run frames (cursor > the reset record) keep
	# flowing into the freshly-cleared _frames from step 0.
	_panel.set_live_status("backend reset — following the new run…")
	var err := _reset_http.request("%s/live" % _live_url, _live_headers())
	if err != OK and err != ERR_BUSY:
		push_warning("penn_replay: reset /live request failed (%d); retrying" % err)
		_schedule_retry(_reset_for_new_run)


func _on_reset_meta_completed(
	_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	if code != 200:
		push_warning("penn_replay: reset GET /live returned HTTP %d; retrying" % code)
		_schedule_retry(_reset_for_new_run)
		return
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(data) != TYPE_DICTIONARY:
		_schedule_retry(_reset_for_new_run)
		return
	var meta: Variant = (data as Dictionary).get("meta")
	if typeof(meta) != TYPE_DICTIONARY:
		push_warning("penn_replay: reset handshake carried no meta; retrying")
		_schedule_retry(_reset_for_new_run)
		return
	_teardown_cast()
	_spawn_from_meta(meta as Dictionary)
	# Re-run the catch-up door so the playhead jumps to the new run's head, exactly
	# as the initial join does (?since=_last_cursor is overlap-safe).
	_request_backfill()
	_panel.set_live_status("following the new run")
	# Normally the socket rides through a reset untouched. But if it dropped while
	# this reset retry was pending, _schedule_retry's single-flight swallowed the
	# socket's own reconnect (#549) — leaving no socket and no rewind detection.
	# The handshake is the one path that both reconnects and re-anchors a stale
	# cursor (a restart coincident with the reset), so re-run it when none is open.
	if _ws == null:
		_request_handshake()


func _teardown_cast() -> void:
	# Free the current cast and reset the per-run view so a fresh meta respawns
	# cleanly. Release the camera BEFORE freeing its target -- stop_following()
	# clears _tracked_name via the follow_stopped signal. _last_cursor and the
	# socket are intentionally left untouched.
	_camera.stop_following()
	for name in _names:
		_agents[name]["node"].queue_free()
		_agents[name]["trail"].queue_free()  # trail is parented to _trails, not node
	_agents.clear()
	_names.clear()
	_persona_detail.clear()
	_relationships = []
	_minimap.clear()
	_panel.clear_characters()
	_frames.clear()  # in place -- keeps the heatmap/social by-reference handoff valid
	_live_buildings.clear()
	_live_started = false
	_t = 0.0
	_last_status_step = -1


func _set_backend_run_state(state: String) -> void:
	# Backend run state -> the sidebar Start/Stop toggle + status line. Driven
	# only by the handshake and the feed's status records — never by button
	# clicks — so a failed control request leaves the UI truthful.
	if state == _backend_run_state:
		return
	_backend_run_state = state
	_panel.set_live_run(state)
	if state == "waiting":
		_panel.set_live_status("waiting — press ▶ Start to begin the day")


func _on_live_run_toggle() -> void:
	# The sidebar Start/Stop drives backend run control through the HUD's live
	# source (POST /resume|/pause, bearer token included). The button flips on
	# the backend's answering status record, not on the click.
	if _hud_source == null:
		return
	if _backend_run_state == "running":
		_hud_source.request_stop()
	elif _hud_source.has_method("request_resume"):
		_hud_source.request_resume()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_shutdown_and_quit()


func _shutdown_and_quit() -> void:
	# Live mode holds the window close (set_auto_accept_quit(false) in
	# _start_live) just long enough to take the backend down with it: closing
	# the viewer must also stop the sim — and its spend. Quit proceeds either
	# way; a dead backend can't answer and shouldn't block the close.
	if _quitting:
		return
	_quitting = true
	if (
		_is_live
		and shutdown_backend_on_exit
		and _hud_source != null
		and _hud_source.has_method("request_shutdown")
	):
		_hud_source.request_shutdown()
		await get_tree().create_timer(0.6).timeout
	get_tree().quit()


func _on_back_to_menu() -> void:
	# Return to the landing menu (issue #399). Deliberately NOT a shutdown: unlike
	# closing the window (_shutdown_and_quit), going back leaves a live backend
	# running so you can reconnect to the same sim — the menu prefills the URL we
	# stash here (WS ?since= then resumes the stream gap-free on reconnect).
	if _quitting:
		return  # a window close is already tearing this scene down; let it finish
	if _is_live:
		LaunchConfig.last_live_url = _live_url
		LaunchConfig.live_token = _live_token
		# The socket is a RefCounted WebSocketPeer (not a scene child), so hang it up
		# ourselves — freeing the scene wouldn't close it cleanly on its own.
		if _ws != null:
			_ws.close()
			_ws = null
	# Undo _start_live's hold on the window close (harmless in replay mode): the menu
	# is a plain scene with no backend to take down.
	get_tree().set_auto_accept_quit(true)
	LaunchConfig.reset()
	get_tree().change_scene_to_file("res://scenes/main_menu.tscn")


func _connect_ws() -> void:
	# The push door. ?since= makes the attach gap-free: the server replays every
	# retained record after the newest one we've applied, then tails -- so a
	# reconnect IS the backfill, and the cursor guard drops any overlap. Auth:
	# desktop sends the Bearer handshake header; a browser WebSocket can't set
	# headers, so web exports pass ?token= instead (the backend accepts both).
	_ws = WebSocketPeer.new()
	var ws_url := _live_url.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
	ws_url += "?since=%d" % maxi(_last_cursor, 0)
	if _live_token != "":
		if _is_web:
			ws_url += "&token=%s" % _live_token.uri_encode()
		else:
			_ws.handshake_headers = PackedStringArray(
				["Authorization: Bearer %s" % _live_token]
			)
	if _ws.connect_to_url(ws_url) != OK:
		_ws = null
		_note_socket(false)
		_schedule_retry(_connect_ws)


func _poll_ws() -> void:
	# WebSocketPeer is poll-driven: pump it every frame, drain whatever arrived,
	# and watch for state changes (its docs' prescribed usage).
	if _ws == null:
		return
	_ws.poll()
	match _ws.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			if not _ws_open:
				_ws_open = true
				_reconnect_delay = 1.0
				_note_socket(true)
				_panel.set_live_status("following backend")
			while _ws.get_available_packet_count() > 0:
				_apply_record(JSON.parse_string(_ws.get_packet().get_string_from_utf8()))
				if _hud_source != null and _hud_source.has_method("note_socket_event"):
					_hud_source.note_socket_event()
		WebSocketPeer.STATE_CLOSED:
			var code := _ws.get_close_code()
			if code == 1011:
				# We fell behind the backend's event retention; the ?since=
				# reconnect below re-syncs from what it still has.
				push_warning("penn_replay: fell behind the live feed; re-syncing")
			_ws = null
			if _ws_open:
				_note_socket(false)
			_ws_open = false
			_panel.set_live_status("reconnecting…")
			# Reconnect through the handshake, not straight to the socket: its
			# callback re-runs the backfill and — if the cursor came back below
			# ours — re-anchors after a backend restart (#549).
			_schedule_retry(_request_handshake)
		_:
			pass  # CONNECTING / CLOSING: keep polling


func _note_socket(open: bool) -> void:
	# Feed the HUD's socket-primary health view (hud_source_live.gd anticipates
	# these; the simulated source simply doesn't implement them).
	if _hud_source != null and _hud_source.has_method("note_socket_state"):
		_hud_source.note_socket_state(open)


func _schedule_retry(retry: Callable) -> void:
	# Single-flight exponential backoff (1s doubling to 15s) shared by the
	# handshake and the socket -- whichever step failed is retried; success
	# resets the delay (see _poll_ws's OPEN transition).
	if _retry_pending:
		return
	_retry_pending = true
	get_tree().create_timer(_reconnect_delay).timeout.connect(
		func() -> void:
			# The timer is owned by the tree, not this node, so it can still fire
			# after a back-to-menu freed the scene (issue #399). Bail if so — the
			# retry would poke a dangling viewer and its now-null socket.
			if not is_instance_valid(self):
				return
			_retry_pending = false
			retry.call()
	)
	_reconnect_delay = minf(_reconnect_delay * 2.0, 15.0)


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


func _building_of(act: String) -> String:
	# The building an agent is in, from its `act` string. The parsing moved to
	# replay_markers.gd (issue #249) so marker labels and the viewer can't drift.
	return ReplayMarkers.building_of(act)


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
	# Pressing Play after an Emergency Stop also lifts the halt: the source
	# un-trips (replay mode) or POSTs /resume (live mode) and confirms back
	# through halted_changed -> _on_run_halted.
	if not _paused and _run_halted:
		_hud_source.request_resume()


func _on_seek(step: int) -> void:
	# Jump the playhead; _process re-renders from _t every frame, so the seek shows
	# even while paused. You can't seek a live stream -- the panel disables its
	# scrubber in live mode, and this guard is the belt-and-braces behind it.
	if _is_live:
		return
	_t = float(step) * step_seconds
	_anim_t = 0.0


func _unhandled_input(event: InputEvent) -> void:
	# Keyboard shortcuts for the pop-up modals (this scene has no other key handling;
	# camera_controls.gd owns zoom/pan keys). Same guard idiom as camera_controls.
	if not (event is InputEventKey and event.pressed and not event.echo):
		return
	match event.keycode:
		KEY_H:
			_toggle_heatmap()
			get_viewport().set_input_as_handled()
		KEY_G:
			# Toggle the social-graph pop-up (issue #252).
			_toggle_social_graph()
			get_viewport().set_input_as_handled()
		KEY_T:
			# Toggle the day-plans pop-up (issue #251).
			_toggle_day_plans()
			get_viewport().set_input_as_handled()
		KEY_C:
			# Capture the current campus view into the snapshot gallery (issue #253).
			# _take_snapshot no-ops if a modal is open, so this is safe to fire always.
			_take_snapshot()
			get_viewport().set_input_as_handled()
		KEY_P:
			# Toggle the State Details inspector for the tracked agent (issue #408) --
			# unless the social graph is above it (layer 13 > 12): opening a modal
			# UNDER another modal's backdrop would just be confusing.
			if _inspector.visible:
				_close_inspector()
				get_viewport().set_input_as_handled()
			elif _tracked_name != "" and not _social_graph.visible:
				_open_inspector(_tracked_name)
				get_viewport().set_input_as_handled()
		KEY_ESCAPE:
			# Close the topmost open modal first (their CanvasLayer stacking order:
			# day plans 15 > gallery 14 > social graph 13 > inspector 12 > heatmap 11).
			if _day_plans.visible:
				_close_day_plans()
				get_viewport().set_input_as_handled()
			elif _gallery.visible:
				_close_gallery()
				get_viewport().set_input_as_handled()
			elif _social_graph.visible:
				_close_social_graph()
				get_viewport().set_input_as_handled()
			elif _inspector.visible:
				_close_inspector()
				get_viewport().set_input_as_handled()
			elif _heatmap.visible:
				_close_heatmap()
				get_viewport().set_input_as_handled()
		KEY_LEFT, KEY_RIGHT:
			# While a pop-up is open, LEFT/RIGHT cycle its view (camera keyboard-pan is
			# suppressed meanwhile, so the arrows don't also scroll the map). The
			# topmost view-cycling modal wins, matching the Esc order above.
			if _gallery.visible:
				# Browse snapshots when enlarged; a no-op in the grid view.
				_gallery.nav_detail(-1 if event.keycode == KEY_LEFT else 1)
				get_viewport().set_input_as_handled()
			elif _social_graph.visible:
				_social_graph.cycle_view(-1 if event.keycode == KEY_LEFT else 1)
				get_viewport().set_input_as_handled()
			elif _heatmap.visible:
				_heatmap.cycle_view(-1 if event.keycode == KEY_LEFT else 1)
				get_viewport().set_input_as_handled()
		KEY_BRACKETLEFT:
			_set_clip_marker(true)
			get_viewport().set_input_as_handled()
		KEY_BRACKETRIGHT:
			_set_clip_marker(false)
			get_viewport().set_input_as_handled()


func _toggle_heatmap() -> void:
	if _heatmap.visible:
		_close_heatmap()
	else:
		_open_heatmap()


func _open_heatmap() -> void:
	# Show the heat accumulated up to the step on screen right now; playback keeps
	# running behind the pop-up (it live-updates via _process). Suppress the camera's
	# keyboard pan so the arrow keys switch views instead of scrolling the map.
	if _frames.is_empty():
		return  # live mode before the first frame: nothing to tally yet
	var last := maxi(_frames.size() - 1, 0)
	var i := mini(int(_t / step_seconds), last)
	_last_heat_step = i
	_heatmap.show_up_to(i)
	_heatmap.visible = true
	_camera.keyboard_enabled = false


func _close_heatmap() -> void:
	_heatmap.visible = false
	# Restore keyboard pan unless another arrow-stealing modal is still open.
	_camera.keyboard_enabled = not _social_graph.visible


func _toggle_social_graph() -> void:
	if _social_graph.visible:
		_close_social_graph()
	else:
		_open_social_graph()


func _open_social_graph() -> void:
	# Show the conversations accumulated up to the step on screen right now; playback
	# keeps running behind the pop-up (it live-updates via _process). Unlike the
	# heatmap, don't bail while _frames is still empty (live mode before the first
	# frame): the SEED view is already meaningful, and show_up_to guards internally.
	# Suppress the camera's keyboard pan so the arrow keys switch views instead.
	if not _frames.is_empty():
		var last := maxi(_frames.size() - 1, 0)
		var i := mini(int(_t / step_seconds), last)
		_last_graph_step = i
		_social_graph.show_up_to(i)
	_social_graph.visible = true
	_camera.keyboard_enabled = false


func _close_social_graph() -> void:
	_social_graph.visible = false
	# Restore keyboard pan unless another arrow-stealing modal is still open.
	_camera.keyboard_enabled = not _heatmap.visible


func _toggle_day_plans() -> void:
	if _day_plans.visible:
		_close_day_plans()
	else:
		_open_day_plans()


func _open_day_plans() -> void:
	# Show plans against progress up to the step on screen right now; playback
	# keeps running behind the pop-up (it live-updates via _process). No
	# camera-keyboard suppression: this pop-up has no arrow-key views.
	if not _frames.is_empty():
		var last := maxi(_frames.size() - 1, 0)
		var i := mini(int(_t / step_seconds), last)
		_last_plan_step = i
		_day_plans.show_up_to(i)
	_day_plans.visible = true


func _close_day_plans() -> void:
	_day_plans.visible = false


func _take_snapshot() -> void:
	# Capture the current campus view into the gallery (issue #253). Skip while a modal is
	# open: its full-screen dim would darken the shot, and the C hotkey fires even when a
	# modal's backdrop has swallowed the sidebar button.
	if _heatmap.visible or _inspector.visible or _social_graph.visible \
			or _gallery.visible or _day_plans.visible:
		return
	# Label it with the world time on screen right now (the sidebar clock's value).
	var label := _format_sim_time(int(_t / step_seconds) * _sec_per_step)
	# Hide the UI chrome (sidebar + minimap + run-monitor HUD) so the shot is the bare
	# campus + agents; the world overlays (fog, name-plates, bubbles, trails) stay put.
	# Wait one drawn frame so the hidden chrome is out of the framebuffer before read-back.
	$UI.visible = false
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	$UI.visible = true
	_gallery.add_snapshot(ImageTexture.create_from_image(img), label)
	_flash()


func _current_step() -> int:
	if step_seconds <= 0.0 or _frames.is_empty():
		return 0
	return clampi(int(_t / step_seconds), 0, maxi(_frames.size() - 1, 0))


func _set_clip_marker(is_in: bool) -> void:
	# [ marks the span start at the playhead, ] marks the end. Baked replay only.
	if _is_live or _frames.is_empty():
		return
	if is_in:
		_clip_in = _current_step()
	else:
		_clip_out = _current_step()
	_panel.set_clip_span(_clip_in, _clip_out)


func _downscale(img: Image) -> Image:
	# Cap GIF frames at 960px wide (a clean 2x decimation from the 1920 viewport;
	# full-res is enormous and slow to encode). NEAREST, not bilinear: the campus
	# is pixel art, so nearest keeps edges crisp where bilinear muddied them. (#488)
	var maxw := 960
	if img.get_width() <= maxw:
		return img
	var out := img.duplicate()
	var h := int(round(img.get_height() * maxw / float(img.get_width())))
	out.resize(maxw, h, Image.INTERPOLATE_NEAREST)
	return out


func _capture_span(from_step: int, to_step: int, sink: Callable) -> void:
	# Render each step in [from,to] offscreen and hand (seq_index, Image) to sink.
	# _paused stops _process advancing _t, so setting _t to an exact step multiple
	# renders that step with zero interpolation (see _process). UI chrome is hidden
	# so grabs are the bare campus; everything is restored on the way out.
	var last := maxi(_frames.size() - 1, 0)
	from_step = clampi(from_step, 0, last)
	to_step = clampi(to_step, from_step, last)
	var saved_t := _t
	var saved_paused := _paused
	_paused = true
	$UI.visible = false
	for step in range(from_step, to_step + 1):
		_t = float(step) * step_seconds
		await RenderingServer.frame_post_draw
		sink.call(step - from_step, get_viewport().get_texture().get_image())
	$UI.visible = true
	_t = saved_t
	_paused = saved_paused


func _export_clip(kind: String) -> void:
	# Dispatch the marked span to the GIF or the PNG-frames path (issue #488).
	if _is_live or _frames.is_empty():
		return
	if _clip_in < 0 or _clip_out < 0:
		_panel.set_clip_status("Mark a clip span first: [ sets start, ] sets end.", "")
		return
	var a := mini(_clip_in, _clip_out)
	var b := maxi(_clip_in, _clip_out)
	_panel.set_clip_status("Exporting %d frames…" % (b - a + 1), "")
	if kind == "gif":
		var frames: Array = []
		await _capture_span(a, b, func(_i: int, img: Image) -> void:
			frames.append(_downscale(img)))
		var bytes := GifEncoder.encode(frames, 10)
		var path := ClipExport.save_gif(bytes, a, b)
		if path == "":
			_panel.set_clip_status("GIF export failed — see console.", "")
		else:
			_panel.set_clip_status("saved → %s" % path,
				"" if OS.has_feature("web") else path)
	else:  # "frames"
		var dir := ClipExport.make_frame_dir(a, b)
		if dir == "":
			_panel.set_clip_status("Frame export failed — see console.", "")
			return
		var count := [0]
		await _capture_span(a, b, func(i: int, img: Image) -> void:
			if ClipExport.save_frame(img, dir, i):
				count[0] += 1)
		var gdir := ProjectSettings.globalize_path(dir)
		# Encode the frames to mp4 + a high-quality gif with ffmpeg so the user
		# gets finished files. Paint the status first (the encode blocks a few
		# seconds); fall back to the copy-paste command if ffmpeg isn't found.
		_panel.set_clip_status("Encoding %d frames with ffmpeg…" % count[0], "")
		await get_tree().process_frame
		var res := ClipExport.run_ffmpeg(dir)
		if res.get("ok", false):
			_panel.set_clip_status("saved → %s\n(+ clip.gif in the same folder)" % res["mp4"], gdir)
		elif String(res.get("error", "")) == "ffmpeg not found":
			_panel.set_clip_status("%d frames → %s\nffmpeg not found — run:\n%s" % [
				count[0], gdir, ClipExport.ffmpeg_command(dir)], gdir)
		else:
			_panel.set_clip_status("ffmpeg failed — see console; frames → %s" % gdir, gdir)


func _flash() -> void:
	# A brief white flash — the "photo taken" cue. Added AFTER the capture, on the
	# top-most layer, so it never lands in the shot itself; fades out then frees itself.
	var flash := ColorRect.new()
	flash.color = Color(1, 1, 1, 0.5)
	flash.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	flash.mouse_filter = Control.MOUSE_FILTER_IGNORE
	$SnapshotLayer.add_child(flash)
	var tween := create_tween()
	tween.tween_property(flash, "modulate:a", 0.0, 0.25)
	tween.tween_callback(flash.queue_free)


func _toggle_gallery() -> void:
	if _gallery.visible:
		_close_gallery()
	else:
		_open_gallery()


func _open_gallery() -> void:
	# Open on the grid view (reset so it never reopens mid-detail). Suppress the camera's
	# keyboard pan so LEFT/RIGHT browse snapshots instead of scrolling the map.
	_gallery.reset()
	_gallery.visible = true
	_camera.keyboard_enabled = false


func _close_gallery() -> void:
	_gallery.visible = false
	# Restore keyboard pan unless another modal that steals it is still open.
	_camera.keyboard_enabled = not (_heatmap.visible or _social_graph.visible or _inspector.visible)


func _open_inspector(name: String) -> void:
	# Open the State Details modal for a persona (issue #408). Fold the world globals
	# (vision_r, sec_per_step) into the persona's static detail so the panel has
	# everything it needs, then push the current step's dynamic state. Suppress the
	# camera's keyboard pan so arrow keys don't scroll the map behind the modal.
	if not _persona_detail.has(name):
		return
	_inspector_name = name
	var detail: Dictionary = (_persona_detail[name] as Dictionary).duplicate(true)
	detail["vision_r"] = _vision_r
	detail["sec_per_step"] = _sec_per_step
	_inspector.open(detail)
	_camera.keyboard_enabled = false
	if not _frames.is_empty():
		var last := _frames.size() - 1
		_push_inspector_step(clampi(int(_t / step_seconds), 0, last))


func _close_inspector() -> void:
	_inspector.close()
	_inspector_name = ""
	# Restore keyboard pan unless another modal is still holding it.
	_camera.keyboard_enabled = not (_heatmap.visible or _social_graph.visible)


func _push_inspector_step(step: int) -> void:
	# Hand the inspector this step's frame + the persona's memory stream + a wall-clock
	# label, so its current-action / reasoning / memory sections match the playhead.
	if _inspector_name == "" or _frames.is_empty():
		return
	var frame: Dictionary = (_frames[step] as Dictionary).get(_inspector_name, {})
	var stream: Array = _memory_streams.get(_inspector_name, [])
	_inspector.set_step_state(frame, stream, step, _format_sim_time(step * _sec_per_step))


func _on_filter_changed(location: String) -> void:
	# The sidebar Focus dropdown picked a building ("" = All). Store it, force the
	# spotlight to re-apply next frame (works while paused — _process always runs), and
	# glide the view to that building so its agents are actually on screen.
	_filter_location = location
	_last_status_step = -1  # make the per-step block (which calls _apply_spotlight) re-run
	if location != "":
		var c: Vector2 = _building_labels.center_of(location)
		if c.is_finite():
			_camera.move_to(c)  # same gentle pan the minimap click uses (keeps zoom)


func _apply_spotlight() -> void:
	# Fade every agent NOT in the focused building; when no filter is set everyone is
	# restored to full. Drives all three views (world sprite via node.modulate, the
	# trail, the sidebar row, and the minimap dot) so they stay in agreement.
	var dimmed := PackedStringArray()
	for name in _names:
		var agent: Dictionary = _agents[name]
		var matches: bool = (
			_filter_location == "" or _agent_location.get(name, "") == _filter_location
		)
		agent["node"].modulate = (
			Color.WHITE if matches else Color(1.0, 1.0, 1.0, SPOTLIGHT_DIM_ALPHA)
		)
		agent["trail"].modulate = (
			Color.WHITE if matches else Color(1.0, 1.0, 1.0, TRAIL_DIM_ALPHA)
		)
		if not matches:
			dimmed.append(name)
	_panel.set_dimmed_rows(dimmed)
	_minimap.set_dimmed(dimmed)


func _process(delta: float) -> void:
	# Live mode: pump the socket first, so records that just arrived render in
	# this same frame. Everything below is mode-agnostic -- live just means
	# _frames is still growing, and the _t clamp keeps playback at its head.
	if _is_live:
		_poll_ws()
	if _frames.is_empty():
		return
	# Advance only while playing; the render below always runs from _t, so a seek (or
	# the day-night tint) still updates the view while paused.
	var last := _frames.size() - 1
	if not _paused:
		# Live mode paces the clock by how many ticks are buffered ahead (issue
		# #372): hold a small lead, decelerate to a stop into a stall, and drain a
		# backlog at a bounded catch-up. Baked replay keeps pace == 1.0, so the
		# advance below is arithmetically identical to before -- byte-identical playback.
		var pace := 1.0
		if _is_live:
			var lead := float(last) - _t / step_seconds
			pace = LivePacer.factor(lead, LEAD_TARGET, CATCHUP_MAX)
		_t += delta * _speed * pace
		_anim_t += delta * _speed * pace
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

	# Live "thinking" cue (issue #372): while the backend is running but the head
	# hasn't grown for a beat and we've caught it, flag that it's deciding. Gated
	# on _is_live, so baked replay never shows it. Edge-triggered so the sidebar
	# text is only rewritten on change.
	if _is_live:
		var stalled := ThinkingIndicator.should_show(
			_is_live, _backend_run_state, i >= last,
			Time.get_ticks_msec() - _last_frame_ms, THINKING_STALL_MS)
		if stalled != _thinking:
			_thinking = stalled
			_thinking_badge.set_active(stalled)
			if _backend_run_state == "running":
				_panel.set_live_status("thinking…" if stalled else "following backend")

	# Keep the run monitor honest about whether the "run" is advancing: the
	# simulated meter accrues spend only while the replay actually plays (not
	# paused, not halted, not pinned at the final frame). Pushed only on change;
	# the live source ignores it (a real backend spends on its own clock).
	var advancing := not _paused and not looped
	if advancing != _hud_running:
		_hud_running = advancing
		_hud_source.set_running(advancing)

	# Keep the heatmap pop-up current: while it's open, re-tally the dwell up to the new
	# step whenever the playhead crosses into it, so the heat grows live as the sim runs.
	if _heatmap.visible and i != _last_heat_step:
		_last_heat_step = i
		_heatmap.show_up_to(i)

	# Same for the social-graph pop-up: new conversations appear (and edge weights
	# shift with recency) as the playhead crosses each step while it's open.
	if _social_graph.visible and i != _last_graph_step:
		_last_graph_step = i
		_social_graph.show_up_to(i)

	# Same for the day-plans pop-up: the actual ribbons + cursor advance as the
	# playhead crosses each step while it's open.
	if _day_plans.visible and i != _last_plan_step:
		_last_plan_step = i
		_day_plans.show_up_to(i)

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
			# The current activity shows in the sidebar row (not as a map bubble); the
			# location half of the same string feeds the Focus spotlight below.
			var full := String(a["act"])
			_panel.set_character_status(name, "%s %s" % [a["e"], full.split(" @ ")[0]])
			_agent_location[name] = _building_of(full)
			_update_agent_speech(name, a, i)
		# Re-evaluate the location spotlight now that everyone's building is up to date.
		_apply_spotlight()
		# Tick the State Details inspector's dynamic sections (current action,
		# reasoning, memories) if it's open -- like the heatmap, it live-updates
		# behind its own dim as playback advances.
		if _inspector.visible:
			_push_inspector_step(i)

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
