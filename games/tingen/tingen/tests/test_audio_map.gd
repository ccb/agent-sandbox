extends SceneTree
## P2 (experiential wave) — AUDIO: the data-driven event->sound map + the AudioManager autoload.
## Standalone: godot --headless --path tingen -s tests/test_audio_map.gd
## Also folded into the main suite (run_tests.gd `_test_audio_map`) via the SAME run_all() entry.
##
## The pins (all headless-safe — routing is PURE DATA, playback is live-only):
##  (a) data/audio_map.json loads and is well-formed (streams / rules / footsteps / ambience)
##  (b) every stream a rule (or footsteps/ambience) references exists as a real res:// file,
##      and ALL 22 shipped WAVs are referenced (no dead assets)
##  (c) resolve() routes the representative EventBus vocabulary to the RIGHT stream names
##      (manifest mapping), with round-robin pools for repeated events (hits, footsteps)
##  (d) headless inertness: the AudioManager autoload subscribes NOTHING and plays NOTHING
##      under --headless — the pinned sims stay byte-identical by construction

func _init() -> void:
	await process_frame
	await process_frame
	# N1 (sprint safety): sandbox EVERY persistent path (meta/save/settings/hints/playlog) into
	# user://test_sandbox/<run>/ and arm the write guard — see src/TestSandbox.gd.
	preload("res://src/TestSandbox.gd").activate(root)
	var r: Dictionary = run_all()
	print("\n=== test_audio_map: %d passed, %d failed ===" % [int(r["passed"]), int(r["failed"])])
	quit(1 if int(r["failed"]) > 0 else 0)

## The one entry point (returns {passed, failed}); folded into run_tests.gd.
static func run_all() -> Dictionary:
	var c := {"passed": 0, "failed": 0}
	var root: Node = (Engine.get_main_loop() as SceneTree).root
	_a_map_loads(c)
	_b_every_referenced_stream_exists(c)
	_c_events_resolve_to_the_right_streams(c)
	_d_headless_emits_nothing(c, root)
	return c

static func _check(c: Dictionary, cond: bool, label: String) -> void:
	if cond:
		c["passed"] = int(c["passed"]) + 1
		print("  PASS  %s" % label)
	else:
		c["failed"] = int(c["failed"]) + 1
		printerr("  FAIL  %s" % label)

static func _am_script() -> GDScript:
	if not ResourceLoader.exists("res://src/AudioManager.gd"):
		return null
	return load("res://src/AudioManager.gd") as GDScript

# (a) --------------------------------------------------------------------------------------------
static func _a_map_loads(c: Dictionary) -> void:
	print("[audio map (a): data/audio_map.json loads and is well-formed]")
	var AM := _am_script()
	_check(c, AM != null, "src/AudioManager.gd exists")
	if AM == null:
		return
	var map: Dictionary = AM.load_map()
	_check(c, not map.is_empty(), "audio_map.json parses to a non-empty map")
	if map.is_empty():
		return
	_check(c, map.get("streams") is Dictionary and not (map["streams"] as Dictionary).is_empty(),
		"map has a streams table")
	_check(c, map.get("rules") is Array and not (map["rules"] as Array).is_empty(),
		"map has an event-rule list")
	_check(c, map.get("footsteps") is Dictionary, "map has a footsteps block")
	_check(c, map.get("ambience") is Dictionary, "map has an ambience block")

# (b) --------------------------------------------------------------------------------------------
static func _b_every_referenced_stream_exists(c: Dictionary) -> void:
	print("[audio map (b): every referenced stream file exists; all 22 shipped WAVs referenced]")
	var AM := _am_script()
	if AM == null:
		_check(c, false, "AudioManager script missing — cannot check streams")
		return
	var map: Dictionary = AM.load_map()
	if map.is_empty():
		_check(c, false, "map missing — cannot check streams")
		return
	var streams: Dictionary = map.get("streams", {})
	var all_exist := true
	for stream_name in streams.keys():
		if not ResourceLoader.exists(String(streams[stream_name])):
			all_exist = false
			printerr("    missing stream file: %s -> %s" % [stream_name, streams[stream_name]])
	_check(c, all_exist, "every stream path in the map exists on disk (%d streams)" % streams.size())
	_check(c, streams.size() == 22, "all 22 curated WAVs are in the streams table (got %d)" % streams.size())
	# Every sound a rule names must be a known stream — a typo'd rule must not fail silently at play time.
	var referenced := {}
	var all_known := true
	for rule in (map.get("rules", []) as Array):
		var sounds: Array = (rule as Dictionary).get("sounds", [])
		var follow: Dictionary = (rule as Dictionary).get("then", {})
		if follow.has("sound"):
			sounds = sounds + [follow["sound"]]
		for s in sounds:
			referenced[String(s)] = true
			if not streams.has(String(s)):
				all_known = false
				printerr("    rule references unknown stream: %s" % s)
	for s in (map.get("footsteps", {}) as Dictionary).get("sounds", []):
		referenced[String(s)] = true
		if not streams.has(String(s)):
			all_known = false
	var amb := String((map.get("ambience", {}) as Dictionary).get("sound", ""))
	referenced[amb] = true
	_check(c, all_known and streams.has(amb), "every rule/footstep/ambience sound name is a known stream")
	# No dead assets: every shipped stream is reachable from some rule, the footstep pool, or ambience.
	var unreferenced := []
	for stream_name in streams.keys():
		if not referenced.has(String(stream_name)):
			unreferenced.append(stream_name)
	_check(c, unreferenced.is_empty(), "no dead assets — every stream is referenced (%s)" % [unreferenced])

# (c) --------------------------------------------------------------------------------------------
## Resolve the representative EventBus vocabulary through the REAL map (not a fixture) and pin the
## manifest's mapping. resolve() is pure data->names, so this runs headless.
static func _c_events_resolve_to_the_right_streams(c: Dictionary) -> void:
	print("[audio map (c): events resolve to the manifest's stream names, pools round-robin]")
	var AM := _am_script()
	if AM == null:
		_check(c, false, "AudioManager script missing — cannot resolve")
		return
	var map: Dictionary = AM.load_map()
	if map.is_empty():
		_check(c, false, "map missing — cannot resolve")
		return
	var rr := {}   # round-robin cursor state, owned by the caller (the manager keeps its own)
	_check(c, _names(AM.resolve(map, "ability_cast_finished",
		{"caster": "player", "ability": "revolver_shot"}, rr)) == ["shot_revolver"],
		"player revolver_shot cast-finished -> shot_revolver")
	_check(c, _names(AM.resolve(map, "ability_cast_finished",
		{"caster": "butcher_grett", "ability": "cleaver_swipe"}, rr)).is_empty(),
		"an NPC cast-finished maps to NO player-shot sound (when-match gates by caster)")
	_check(c, _names(AM.resolve(map, "ability_cast_finished",
		{"caster": "player", "ability": "dash"}, rr)) == ["dash_whoosh"],
		"player dash -> dash_whoosh")
	_check(c, _names(AM.resolve(map, "weapon_empty", {"caster": "player"}, rr)) == ["shot_dry"],
		"weapon_empty (dry fire) -> shot_dry")
	_check(c, _names(AM.resolve(map, "spirit_empty", {"caster": "player"}, rr)) == ["ui_error"],
		"spirit_empty (refusal cue) -> ui_error")
	# Flesh hits are a round-robin pool of 2 — consecutive hits must alternate, never machine-gun.
	var h1 := _names(AM.resolve(map, "agent_attacked", {"actor": "player", "target": "x", "damage": 8.0}, rr))
	var h2 := _names(AM.resolve(map, "agent_attacked", {"actor": "player", "target": "x", "damage": 8.0}, rr))
	_check(c, h1.size() == 1 and h2.size() == 1 and String(h1[0]).begins_with("hit_flesh")
		and String(h2[0]).begins_with("hit_flesh") and h1[0] != h2[0],
		"light hits alternate the hit_flesh pool (%s then %s)" % [h1, h2])
	_check(c, _names(AM.resolve(map, "agent_attacked",
		{"actor": "x", "target": "player", "damage": 40.0}, rr)) == ["hit_hard"],
		"a heavy hit (damage >= heavy threshold) -> hit_hard")
	_check(c, _names(AM.resolve(map, "agent_downed", {"actor": "player", "target": "x"}, rr)) == ["body_fall"],
		"agent_downed -> body_fall")
	var tf := _names(AM.resolve(map, "transformed", {"agent": "butcher_grett", "form": "hog_butcher"}, rr))
	tf.sort()
	_check(c, tf == ["slam_mask_drop", "sting_mask_drop"],
		"transformed (mask-drop) layers slam + sting (%s)" % [tf])
	_check(c, _names(AM.resolve(map, "item_picked_up", {"caster": "player", "item": "bandage"}, rr)) == ["pickup_item"],
		"item_picked_up -> pickup_item")
	_check(c, _names(AM.resolve(map, "ammo_picked_up", {"caster": "player", "ammo": 6}, rr)) == ["pickup_metal"],
		"ammo_picked_up -> pickup_metal")
	_check(c, _names(AM.resolve(map, "hint_shown", {"key": "rest_hint"}, rr)) == ["hint_chime"],
		"hint_shown -> hint_chime")
	# Cue vocabulary (non-EventBus presentation beats routed through the SAME map).
	var door: Array = AM.resolve(map, "room_changed", {"room": "lodging"}, rr)
	_check(c, _names(door) == ["door_open"],
		"room transition -> door_open")
	var follow: Dictionary = (door[0] as Dictionary).get("then", {}) if door.size() > 0 else {}
	_check(c, String(follow.get("sound", "")) == "door_close" and float(follow.get("delay", 0.0)) > 0.0,
		"the door shuts behind you (delayed door_close follow-up)")
	_check(c, _names(AM.resolve(map, "toast_shown", {}, rr)) == ["ui_toast"], "toast_shown -> ui_toast")
	_check(c, _names(AM.resolve(map, "ui_click", {}, rr)) == ["ui_click"], "ui_click -> ui_click")
	_check(c, _names(AM.resolve(map, "madness_threshold", {"level": 40}, rr)) == ["sting_threshold"],
		"madness_threshold -> sting_threshold")
	_check(c, _names(AM.resolve(map, "threat_threshold", {"meter": "notice", "level": 70}, rr)) == ["sting_threshold"],
		"threat_threshold -> sting_threshold")
	_check(c, _names(AM.resolve(map, "no_such_event", {}, rr)).is_empty(),
		"an unmapped event resolves to nothing (silence, no crash)")

static func _names(picks: Array) -> Array:
	var out := []
	for p in picks:
		out.append(String((p as Dictionary).get("stream", "")))
	return out

# (d) --------------------------------------------------------------------------------------------
## Headless the AudioManager autoload must be INERT: no players built, no EventBus subscription,
## nothing recorded as played even when the real EventBus fires mapped events. This is the
## determinism gate — the pinned sims run headless, so byte-identical is guaranteed by construction.
static func _d_headless_emits_nothing(c: Dictionary, root: Node) -> void:
	print("[audio map (d): headless AudioManager is inert — no subscription, no playback]")
	var am: Node = root.get_node_or_null("/root/AudioManager")
	_check(c, am != null, "AudioManager autoload registered")
	if am == null:
		return
	_check(c, am.get_child_count() == 0, "headless: no AudioStreamPlayer pool built (0 children)")
	var eb: Node = root.get_node_or_null("/root/EventBus")
	var subscribed := false
	if eb != null:
		for conn in eb.event_logged.get_connections():
			if (conn["callable"] as Callable).get_object() == am:
				subscribed = true
	_check(c, not subscribed, "headless: AudioManager is NOT connected to EventBus.event_logged")
	# Fire the loudest mapped events through the REAL EventBus + the cue seam: still nothing plays.
	if eb != null:
		eb.emit_event("agent_downed", {"actor": "player", "target": "test_dummy"})
		eb.emit_event("transformed", {"agent": "test_dummy", "form": "hog_butcher"})
	am.cue("ui_click")
	am.cue("room_changed", {"room": "lodging"})
	_check(c, int(am.played_count()) == 0, "headless: played_count stays 0 after mapped events + cues")
