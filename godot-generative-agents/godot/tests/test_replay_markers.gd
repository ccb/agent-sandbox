extends SceneTree
## Headless unit tests for scripts/replay_markers.gd (issue #249). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_replay_markers.gd
## Exit 0 = all checks pass; 1 = at least one failed (run_smoke_test.sh runs
## this before the scene smoke).

const ReplayMarkers := preload("res://scripts/replay_markers.gd")
const TimelineMarkers := preload("res://scripts/timeline_markers.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _frame(act_by_name: Dictionary, chat_by_name := {}) -> Dictionary:
	# Build one replay frame: name -> AgentFrame (only the fields collect reads).
	var frame := {}
	for name in act_by_name:
		frame[name] = {"x": 0, "y": 0, "act": act_by_name[name], "e": "🙂",
			"chat": chat_by_name.get(name)}
	return frame


func _of_kind(markers: Array, kind: String) -> Array:
	return markers.filter(func(m: Dictionary) -> bool: return m["kind"] == kind)


func _initialize() -> void:
	var names := ["Ada"]
	# A 4-step day: walk to the library (0), study there (1, 2), walk off (3).
	var frames := [
		_frame({"Ada": "walking to Van Pelt — Kamin Gallery @ UPenn:Van Pelt Library:Kamin Gallery"}),
		_frame({"Ada": "studying @ UPenn:Van Pelt Library:Kamin Gallery"}),
		_frame({"Ada": "studying @ UPenn:Van Pelt Library:Kamin Gallery"},
			{"Ada": [["Ada", "hello"]]}),
		_frame({"Ada": "walking to Houston Hall @ UPenn:Houston Hall:lobby"}),
	]

	# --- building_of ---
	_check(ReplayMarkers.building_of("studying @ UPenn:Van Pelt Library:lobby")
		== "Van Pelt Library", "building_of extracts the middle segment")
	_check(ReplayMarkers.building_of("gibberish") == "", "building_of malformed -> empty")

	# --- arrivals: the 'walking to ' prefix DISAPPEARING marks arrival ---
	var markers: Array = ReplayMarkers.collect(frames, names, {}, [])
	var arrivals := _of_kind(markers, "arrival")
	_check(arrivals.size() == 1, "exactly one arrival (step 3 is a departure, not an arrival)")
	_check(arrivals[0]["step"] == 1, "arrival at the first non-walking step")
	_check(arrivals[0]["agent"] == "Ada", "arrival carries the agent")
	_check("Van Pelt Library" in String(arrivals[0]["label"]), "arrival label names the building")

	# --- chat onsets: null -> non-empty is an onset; continuation is not ---
	var chats := _of_kind(markers, "chat")
	_check(chats.size() == 1 and chats[0]["step"] == 2, "one chat onset at step 2")
	var frames_chat0 := [
		_frame({"Ada": "a @ UPenn:X:y"}, {"Ada": [["Ada", "hi"]]}),
		_frame({"Ada": "a @ UPenn:X:y"}, {"Ada": [["Ada", "hi"], ["Bo", "yo"]]}),
	]
	var chats0 := _of_kind(ReplayMarkers.collect(frames_chat0, names, {}, []), "chat")
	_check(chats0.size() == 1 and chats0[0]["step"] == 0, "chat already active at step 0 is one onset at 0")

	# --- reflections come from memory_streams ---
	var streams := {"Ada": [
		{"kind": "reflection", "importance": 8, "text": "I study best in the morning.", "created_turn": 2},
		{"kind": "observation", "importance": 2, "text": "saw a bird", "created_turn": 1},
	]}
	var refl := _of_kind(ReplayMarkers.collect(frames, names, streams, []), "reflection")
	_check(refl.size() == 1 and refl[0]["step"] == 2, "one reflection marker at created_turn")

	# --- game events (the #476 run record) ---
	var events := [
		{"turn": 3, "actor": "Ada", "action": "drink", "summary": "drank unboiled water", "payload": {}},
		{"turn": 99, "actor": "Ada", "action": "x", "summary": "out of range", "payload": {}},
	]
	var evts := _of_kind(ReplayMarkers.collect(frames, names, {}, events), "event")
	_check(evts.size() == 1 and evts[0]["step"] == 3, "in-range event kept, out-of-range dropped")
	_check(String(evts[0]["label"]) == "Ada: drank unboiled water", "event label is 'actor: summary'")
	_check(String(evts[0]["action"]) == "drink", "event marker carries the action type (#593)")

	# --- per-event-type styling (timeline_markers.gd), #593 ---
	var c_sick := TimelineMarkers.color_for("event", "sickness")
	var c_boil := TimelineMarkers.color_for("event", "boiled")
	var c_rec := TimelineMarkers.color_for("event", "recovery")
	_check(c_sick != c_boil and c_boil != c_rec and c_sick != c_rec,
		"sickness/boiled/recovery get three distinct colors")
	var c_default: Color = TimelineMarkers.KIND_COLORS["event"]
	_check(TimelineMarkers.color_for("event", "mystery") == c_default,
		"unknown event type falls back to the default event color")
	_check(TimelineMarkers.color_for("event", "") == c_default,
		"missing action falls back to the default event color")
	_check(TimelineMarkers.color_for("chat", "") == TimelineMarkers.KIND_COLORS["chat"],
		"non-event kinds keep their KIND_COLORS color")
	_check(TimelineMarkers.color_for("weird", "") == Color.WHITE,
		"unknown kind falls back to white")

	# tooltip_line prefixes known event types with an emoji + the type name.
	var sick_tip := TimelineMarkers.tooltip_line(
		{"step": 945, "kind": "event", "action": "sickness", "label": "Sofia: got sick"})
	_check("🤢" in sick_tip and "sickness" in sick_tip and "Sofia: got sick" in sick_tip,
		"tooltip enriches a known event with emoji + type + label")
	_check("945" in sick_tip, "tooltip keeps the step number")
	var plain_tip := TimelineMarkers.tooltip_line(
		{"step": 3, "kind": "event", "action": "drink", "label": "Ada: drank"})
	_check(plain_tip == "step 3 — Ada: drank",
		"unknown event type keeps the plain 'step N — label' tooltip")
	var chat_tip := TimelineMarkers.tooltip_line(
		{"step": 2, "kind": "chat", "label": "Ada starts a conversation"})
	_check(chat_tip == "step 2 — Ada starts a conversation",
		"non-event kinds keep the plain tooltip")

	# --- robustness + ordering ---
	var all := ReplayMarkers.collect(frames, names, streams, events)
	var steps := all.map(func(m: Dictionary) -> int: return m["step"])
	var steps_sorted: Array = steps.duplicate()
	steps_sorted.sort()
	_check(steps == steps_sorted, "markers are sorted by step")
	_check(ReplayMarkers.collect([], [], {}, []).is_empty(), "empty replay -> no markers, no crash")

	if _failures == 0:
		print("test_replay_markers: all checks passed")
	quit(1 if _failures > 0 else 0)
