extends RefCounted
## Pure marker collection for the timeline scrubber (issue #249): scan a loaded
## replay once and return the "interesting moments" as marker dictionaries
## {step, kind, agent, label}, sorted by step. Four sources, four kinds:
##   event      — the #476 game-event run record (replay top-level `events`)
##   chat       — a conversation onset (an agent's `chat` goes empty -> non-empty)
##   reflection — a reflection forming (memory_streams, kind == "reflection")
##   arrival    — a travel leg ending (the "walking to " act prefix disappears;
##                during travel the act address is already the DESTINATION's, so
##                an address change marks departure — the prefix is the signal,
##                same convention serve_penn.py keys on)
## Pure functions over plain Arrays/Dictionaries — no scene nodes, so the whole
## file is unit-testable headlessly (tests/test_replay_markers.gd).

# A travel-leg act reads "walking to <place> @ <destination address>"
# (run_simulation.py step()); everything else is "<activity> @ <address>".
const WALKING_PREFIX := "walking to "


static func collect(frames: Array, names: Array, memory_streams: Dictionary,
		events: Array) -> Array:
	var markers: Array = []
	var last := frames.size() - 1
	if last < 0:
		return markers

	# Game events: one marker per record; the record's `turn` is the frame index.
	for rec in events:
		var step := int((rec as Dictionary).get("turn", -1))
		if step < 0 or step > last:
			continue
		# World-level stimuli (ambient sound, POST /world/event, the boil arc's
		# `boiled` event) carry actor=null/"": label them "world". The raw value
		# was crashing here -- String(null) has no constructor -- so the whole
		# marker strip failed to build on any replay with a world event (#631).
		var actor_raw: Variant = (rec as Dictionary).get("actor", "")
		var actor := "world" if actor_raw == null or String(actor_raw).is_empty() \
			else String(actor_raw)
		# Carry the event `action` (sickness/boiled/recovery/...) so the strip can
		# style each type distinctly (#593); the label stays "actor: summary".
		markers.append({"step": step, "kind": "event", "agent": actor,
			"action": String((rec as Dictionary).get("action", "")),
			"label": "%s: %s" % [actor, String((rec as Dictionary).get("summary", ""))]})

	# Reflections: from each persona's full memory stream, at the step it formed.
	for name in memory_streams:
		for rec in (memory_streams[name] as Array):
			if String((rec as Dictionary).get("kind", "")) != "reflection":
				continue
			var step := int((rec as Dictionary).get("created_turn", -1))
			if step < 0 or step > last:
				continue
			markers.append({"step": step, "kind": "reflection", "agent": String(name),
				"label": "%s reflects: %s" % [name, _trim(String((rec as Dictionary).get("text", "")))]})

	# Chat onsets + arrivals need frame-to-frame comparison per agent.
	for name in names:
		var was_chatting := false
		var was_walking := false
		for i in frames.size():
			var agent: Dictionary = (frames[i] as Dictionary).get(name, {})
			var act := String(agent.get("act", ""))
			var chat: Variant = agent.get("chat")
			var chatting := chat is Array and not (chat as Array).is_empty()
			if chatting and not was_chatting:
				markers.append({"step": i, "kind": "chat", "agent": String(name),
					"label": "%s starts a conversation" % name})
			var walking := act.begins_with(WALKING_PREFIX)
			if was_walking and not walking:
				var building := building_of(act)
				var where := " at %s" % building if building != "" else ""
				markers.append({"step": i, "kind": "arrival", "agent": String(name),
					"label": "%s arrives%s" % [name, where]})
			was_chatting = chatting
			was_walking = walking

	markers.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return int(a["step"]) < int(b["step"]))
	return markers


static func building_of(act: String) -> String:
	# The building an agent is in, from its `act` string. `act` is
	# "<activity> @ UPenn:<Building>:<area>"; we want the middle "<Building>"
	# segment. Returns "" if the address is missing or malformed. (Moved from
	# viewer.gd so marker labels and the viewer share one definition.)
	var halves := act.split(" @ ")
	if halves.size() < 2:
		return ""
	var addr := halves[1].split(":")
	return addr[1] if addr.size() > 1 else ""


static func _trim(text: String) -> String:
	# Keep tooltip lines readable: first 57 chars + ellipsis.
	return text if text.length() <= 58 else text.substr(0, 57) + "…"
