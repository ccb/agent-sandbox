extends Node
## Sound (autoload `AudioManager`) — P2 of the experiential wave: the game's FIRST audio.
##
## PURELY PRESENTATION, exactly like CombatFeedback: this node never mutates combat/agent/world
## state and never feeds the executor. Under --headless (every pinned harness: combat_sim,
## run_combat_vectors, full_run, run_tests) `_ready` bails BEFORE subscribing to anything or
## building any player — the sims stay byte-identical by construction, not by discipline.
##
## Routing is DATA (engine neutrality): data/audio_map.json maps EventBus vocabulary (and a small
## set of cue names for non-EventBus presentation beats) to stream names; assets/audio/README.md
## documents provenance (all CC0). Repeated events (flesh hits, footsteps) draw from ROUND-ROBIN
## pools so they never machine-gun one sample. Everything plays on the Master bus, which the
## Settings master_volume slider drives (Settings._apply_master_volume) — the slider finally
## controls something audible.
##
## Live wiring (all subscriptions made only when a real display exists):
##   * EventBus.event_logged            -> the mapped combat/pickup/hint vocabulary
##   * WorldState.room_changed          -> door creak (+ the delayed shut behind you)
##   * Meters.madness/threat_threshold  -> the threshold sting
##   * SceneTree.node_added (BaseButton)-> every button press clicks, no per-panel wiring
##   * Toasts.push                      -> cue("toast_shown") (the one engine-side cue call)
##   * the player rig's actual movement -> footsteps every stride_px of real travel
##   * ambience_night                   -> its own dedicated looping player
##
## Headless-observable probe surface: played_count()/played_log() record what WOULD have been
## audible (always 0 headless — tests/test_audio_map.gd pins exactly that).

const MAP_PATH: String = "res://data/audio_map.json"
const POOL_SIZE: int = 8
const PLAYED_LOG_CAP: int = 64
## A player position jump bigger than this in one frame is a teleport (room change, probe nudge),
## not walking — footsteps must not fire a burst for it.
const TELEPORT_PX: float = 80.0

var _map: Dictionary = {}
var _streams: Dictionary = {}          # stream name -> AudioStream (preloaded, live only)
var _pool: Array = []                  # of AudioStreamPlayer (live only)
var _pool_idx: int = 0
var _rr: Dictionary = {}               # rule index -> round-robin cursor
var _step_rr: int = 0                  # footstep pool cursor
var _ambience: AudioStreamPlayer = null
var _played: Array = []                # probe: stream names played, newest last (capped)
var _warned_missing: Dictionary = {}   # stream name -> true (warn once, not per shot)

## Footstep odometer: accumulated real travel of the player rig since the last step sound.
var _step_accum: float = 0.0
var _step_last_pos: Vector2 = Vector2.ZERO
var _step_has_pos: bool = false

func _ready() -> void:
	if not _is_live():
		# HEADLESS: fully inert. No map players, no subscriptions, no processing — the pinned
		# deterministic harnesses run headless and must never observe this node.
		set_process(false)
		return
	_map = load_map()
	if _map.is_empty():
		push_warning("AudioManager: %s missing/invalid — sound disabled" % MAP_PATH)
		set_process(false)
		return
	_preload_streams()
	_build_pool()
	_subscribe()
	_start_ambience()

# --- Data (headless-safe, static: the tests drive these directly) ------------------------------
## Parse data/audio_map.json. Pure data — no players, no side effects. {} on any error.
static func load_map(path: String = MAP_PATH) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (parsed is Dictionary):
		return {}
	var map: Dictionary = parsed
	if not (map.get("streams") is Dictionary) or not (map.get("rules") is Array):
		return {}
	return map

## Route one event through the map: every matching rule contributes ONE pick (a pool rule picks
## round-robin via the caller-owned `rr` cursor dict). Returns [{stream, volume_db[, then]}].
## Pure data->names — the headless tests pin the manifest mapping through this exact seam.
static func resolve(map: Dictionary, event_type: String, data: Dictionary, rr: Dictionary) -> Array:
	var picks: Array = []
	var rules: Array = map.get("rules", [])
	for i in rules.size():
		var rule: Dictionary = rules[i]
		if String(rule.get("event", "")) != event_type:
			continue
		if not _matches(rule, data):
			continue
		var sounds: Array = rule.get("sounds", [])
		if sounds.is_empty():
			continue
		var cursor := int(rr.get(i, 0))
		rr[i] = cursor + 1
		var pick := {
			"stream": String(sounds[cursor % sounds.size()]),
			"volume_db": float(rule.get("volume_db", 0.0)),
		}
		if rule.get("then") is Dictionary:
			pick["then"] = rule["then"]
		picks.append(pick)
	return picks

## Rule guards: `when` exact-matches (string compare), `min`/`max` band numeric data fields
## (min inclusive, max exclusive). A field missing from the event data fails the guard.
static func _matches(rule: Dictionary, data: Dictionary) -> bool:
	var when: Dictionary = rule.get("when", {})
	for k in when:
		if String(data.get(k, "__MISSING__")) != String(when[k]):
			return false
	var mins: Dictionary = rule.get("min", {})
	for k in mins:
		if not data.has(k) or float(data.get(k)) < float(mins[k]):
			return false
	var maxs: Dictionary = rule.get("max", {})
	for k in maxs:
		if not data.has(k) or float(data.get(k)) >= float(maxs[k]):
			return false
	return true

# --- The one playback seam ----------------------------------------------------------------------
## Cue a mapped event by name. EventBus events funnel here via _on_event; non-EventBus presentation
## beats (toast_shown, ui_click, room_changed, the meter stings) call it directly. Headless (or with
## no map) this is a no-op — played_count() stays 0.
func cue(event_type: String, data: Dictionary = {}) -> void:
	if not _is_live() or _map.is_empty():
		return
	for pick in resolve(_map, event_type, data, _rr):
		var p: Dictionary = pick
		_play(String(p["stream"]), float(p["volume_db"]))
		if p.get("then") is Dictionary:
			_play_later(p["then"])

func _on_event(ev: Dictionary) -> void:
	var data: Dictionary = ev.get("data", {}) if ev.get("data") is Dictionary else {}
	cue(String(ev.get("type", "")), data)

## The delayed follow-up (the door shuts behind you). Real-time timer: immune to pause and to the
## combat hit-stop's time_scale dip.
func _play_later(follow: Dictionary) -> void:
	var sound := String(follow.get("sound", ""))
	if sound == "":
		return
	var delay := maxf(0.05, float(follow.get("delay", 0.5)))
	var vol := float(follow.get("volume_db", 0.0))
	get_tree().create_timer(delay, true, false, true).timeout.connect(
		func() -> void: _play(sound, vol))

func _play(stream_name: String, volume_db: float = 0.0) -> void:
	var stream: AudioStream = _streams.get(stream_name)
	if stream == null:
		if not _warned_missing.has(stream_name):
			_warned_missing[stream_name] = true
			push_warning("AudioManager: unknown stream '%s'" % stream_name)
		return
	var player := _next_player()
	if player == null:
		return
	player.stream = stream
	player.volume_db = volume_db
	player.play()
	_played.append(stream_name)
	if _played.size() > PLAYED_LOG_CAP:
		_played = _played.slice(_played.size() - PLAYED_LOG_CAP)

## Prefer an idle pool player; when all are busy, steal round-robin (oldest voice drops).
func _next_player() -> AudioStreamPlayer:
	if _pool.is_empty():
		return null
	for i in _pool.size():
		var p: AudioStreamPlayer = _pool[(_pool_idx + i) % _pool.size()]
		if not p.playing:
			_pool_idx = (_pool_idx + i + 1) % _pool.size()
			return p
	var stolen: AudioStreamPlayer = _pool[_pool_idx]
	_pool_idx = (_pool_idx + 1) % _pool.size()
	return stolen

# --- Live wiring --------------------------------------------------------------------------------
func _preload_streams() -> void:
	var table: Dictionary = _map.get("streams", {})
	for stream_name in table:
		var path := String(table[stream_name])
		if ResourceLoader.exists(path):
			_streams[stream_name] = load(path)
		else:
			push_warning("AudioManager: stream file missing: %s -> %s" % [stream_name, path])

func _build_pool() -> void:
	for i in POOL_SIZE:
		var p := AudioStreamPlayer.new()
		p.name = "Voice%d" % i
		p.bus = "Master"
		# Keep playing while the tree is paused (pause menu clicks must still click).
		p.process_mode = Node.PROCESS_MODE_ALWAYS
		add_child(p)
		_pool.append(p)

func _subscribe() -> void:
	var eb := _al("EventBus")
	if eb != null and not eb.event_logged.is_connected(_on_event):
		eb.event_logged.connect(_on_event)
	var ws := _al("WorldState")
	if ws != null and ws.has_signal("room_changed"):
		ws.room_changed.connect(func(room_id: String, _scene_path: String) -> void:
			cue("room_changed", {"room": room_id}))
	var meters := _al("Meters")
	if meters != null:
		if meters.has_signal("madness_threshold"):
			meters.madness_threshold.connect(func(level: int) -> void:
				cue("madness_threshold", {"level": level}))
		if meters.has_signal("threat_threshold"):
			meters.threat_threshold.connect(func(meter: String, level: int) -> void:
				cue("threat_threshold", {"meter": meter, "level": level}))
	# Every BaseButton anywhere (title, pause, panels, shop) clicks — no per-panel wiring.
	var tree := get_tree()
	tree.node_added.connect(_hook_button)
	_sweep_buttons(tree.root)

func _hook_button(node: Node) -> void:
	if node is BaseButton:
		var b := node as BaseButton
		if not b.pressed.is_connected(_on_ui_click):
			b.pressed.connect(_on_ui_click)

func _on_ui_click() -> void:
	cue("ui_click")

func _sweep_buttons(node: Node) -> void:
	_hook_button(node)
	for child in node.get_children():
		_sweep_buttons(child)

# --- Ambience (its own dedicated looping player) -------------------------------------------------
func _start_ambience() -> void:
	var amb: Dictionary = _map.get("ambience", {})
	var stream: AudioStream = _streams.get(String(amb.get("sound", "")))
	if stream == null:
		return
	if bool(amb.get("loop", true)) and stream is AudioStreamWAV:
		# The imported WAV carries no loop points — force a full-file forward loop on a private
		# copy (the file itself is authored as a seamless loop via tail-head crossfade).
		var wav := (stream as AudioStreamWAV).duplicate() as AudioStreamWAV
		var bytes_per_frame := (2 if wav.format == AudioStreamWAV.FORMAT_16_BITS else 1) \
			* (2 if wav.stereo else 1)
		wav.loop_mode = AudioStreamWAV.LOOP_FORWARD
		wav.loop_begin = 0
		wav.loop_end = wav.data.size() / bytes_per_frame
		stream = wav
	_ambience = AudioStreamPlayer.new()
	_ambience.name = "Ambience"
	_ambience.bus = "Master"
	_ambience.process_mode = Node.PROCESS_MODE_ALWAYS
	_ambience.stream = stream
	_ambience.volume_db = float(amb.get("volume_db", -18.0))
	add_child(_ambience)
	_ambience.play()
	# Belt and braces: if the loop flags ever fail to take, restart on finish.
	_ambience.finished.connect(func() -> void:
		if _ambience != null and is_instance_valid(_ambience):
			_ambience.play())

## Probe/QA seam: silence or resume the ambience bed (the audio probe isolates per-event peaks).
func set_ambience_enabled(on: bool) -> void:
	if _ambience == null or not is_instance_valid(_ambience):
		return
	if on and not _ambience.playing:
		_ambience.play()
	elif not on and _ambience.playing:
		_ambience.stop()

func ambience_playing() -> bool:
	return _ambience != null and is_instance_valid(_ambience) and _ambience.playing

# --- Footsteps (driven off the player rig's ACTUAL movement, not input) --------------------------
func _process(_delta: float) -> void:
	var steps: Dictionary = _map.get("footsteps", {})
	var pool: Array = steps.get("sounds", [])
	if pool.is_empty():
		return
	var players := get_tree().get_nodes_in_group("player")
	if players.is_empty() or not (players[0] is Node2D):
		_step_has_pos = false
		return
	var pos: Vector2 = (players[0] as Node2D).global_position
	if not _step_has_pos:
		_step_last_pos = pos
		_step_has_pos = true
		return
	var moved := pos.distance_to(_step_last_pos)
	_step_last_pos = pos
	if moved <= 0.0:
		return
	if moved > TELEPORT_PX:
		_step_accum = 0.0   # a teleport is not walking
		return
	_step_accum += moved
	var stride := maxf(8.0, float(steps.get("stride_px", 44.0)))
	if _step_accum >= stride:
		_step_accum = fmod(_step_accum, stride)
		var pick := String(pool[_step_rr % pool.size()])
		_step_rr += 1
		_play(pick, float(steps.get("volume_db", -16.0)))

# --- Probe surface (headless-observable) ----------------------------------------------------------
func played_count() -> int:
	return _played.size()

func played_log() -> Array:
	return _played.duplicate()

func reset_played_log() -> void:
	_played.clear()

# --- Gates ----------------------------------------------------------------------------------------
## True only when a real display is attached (live play). False under --headless — where this node
## must be provably inert (the CombatFeedback._is_live pattern).
func _is_live() -> bool:
	return DisplayServer.get_name() != "headless"

func _al(autoload_name: String) -> Node:
	var ml := Engine.get_main_loop()
	if ml == null or not (ml is SceneTree):
		return null
	return (ml as SceneTree).root.get_node_or_null(autoload_name)
