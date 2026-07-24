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


func _far(a: Color, b: Color, thresh: float) -> bool:
	# Manhattan distance in RGB; a cheap perceptual "these read as different".
	return absf(a.r - b.r) + absf(a.g - b.g) + absf(a.b - b.b) > thresh


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

	# --- actor-less world events get a "world" fallback label (#631) ---
	# Ambient sound, POST /world/event, the boil arc's `boiled` event carry
	# actor=None (or ""); the tooltip must read "world: summary", not the broken
	# "<null>: ..." / ": ..." the raw actor produced.
	var world_events := [
		{"turn": 3, "actor": null, "action": "boiled",
			"summary": "the pot is boiled clear on the stove", "payload": {}},
		{"turn": 3, "actor": "", "action": "world_event",
			"summary": "a siren wails", "payload": {}},
	]
	var world_evts := _of_kind(
		ReplayMarkers.collect(frames, names, {}, world_events), "event")
	_check(world_evts.size() == 2, "actor-less world events still produce markers")
	_check(String(world_evts[0]["label"]) == "world: the pot is boiled clear on the stove",
		"a null-actor event labels as 'world: summary' (#631)")
	_check(String(world_evts[0]["agent"]) == "world",
		"a null-actor event's agent is 'world' (#631)")
	_check(String(world_evts[1]["label"]) == "world: a siren wails",
		"an empty-actor event also labels as 'world' (#631)")

	# --- wishes (#622 demand-signal record, surfaced #625) ---
	var wishes := [
		{"turn": 1, "actor": "Ada", "location": "UPenn:X", "desired": "a bike rack",
			"reason": "mine got stolen", "trigger": "proposed", "goals": [], "scope": [],
			"raw_command": "propose a bike rack because mine got stolen", "meta": {}},
		{"turn": 99, "actor": "Ada", "location": "UPenn:X", "desired": "out of range",
			"reason": "", "trigger": "proposed", "goals": [], "scope": [],
			"raw_command": "propose out of range", "meta": {}},
	]
	var wish_markers := _of_kind(ReplayMarkers.collect(frames, names, {}, [], wishes), "wish")
	_check(wish_markers.size() == 1 and wish_markers[0]["step"] == 1,
		"in-range wish kept, out-of-range dropped")
	_check(String(wish_markers[0]["agent"]) == "Ada", "wish marker carries the actor")
	_check("💭" in String(wish_markers[0]["label"]) and "a bike rack" in String(wish_markers[0]["label"]),
		"wish label carries the 💭 marker and the desired action")
	# wishes defaults to [] when a caller (or an older code path) omits it --
	# no wish markers appear, and the call doesn't crash for lack of the arg.
	_check(_of_kind(ReplayMarkers.collect(frames, names, {}, events), "wish").is_empty(),
		"collect() without a wishes arg produces no wish markers (default [])")

	# actor-less wishes get the same "world" fallback as actor-less events (#631) --
	# ActionWish.actor is only null when no actor resolved, but guard it the same way.
	var world_wishes := [
		{"turn": 1, "actor": null, "location": null, "desired": "a working printer",
			"reason": "", "trigger": "parse_gap", "goals": [], "scope": [],
			"raw_command": "print the essay", "meta": {}},
	]
	var world_wish_markers := _of_kind(
		ReplayMarkers.collect(frames, names, {}, [], world_wishes), "wish")
	_check(world_wish_markers.size() == 1 and String(world_wish_markers[0]["agent"]) == "world",
		"an actor-less wish still produces a marker, labeled 'world'")

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
	# Collision guards (#596 review): the strip already paints every lifecycle
	# event (go/perform/travel) in the default event red and arrivals in green,
	# so sickness must not read as an ordinary event tick and recovery must not
	# read as an arrival. Perceptual distance, not mere != inequality.
	_check(_far(c_sick, c_default, 0.15),
		"sickness color is perceptually distinct from the default event red")
	_check(_far(c_rec, TimelineMarkers.KIND_COLORS["arrival"], 0.15),
		"recovery color is perceptually distinct from the arrival green")
	# wish (#622/#625) gets its own KIND_COLORS entry, distinct from every other
	# tick kind already on the strip (not just event/chat/reflection/arrival, but
	# also the #593 event sub-styles it shares the strip with).
	var c_wish := TimelineMarkers.color_for("wish", "")
	_check(c_wish == TimelineMarkers.KIND_COLORS["wish"], "wish resolves via KIND_COLORS")
	for other in [c_default, TimelineMarkers.KIND_COLORS["chat"],
			TimelineMarkers.KIND_COLORS["reflection"], TimelineMarkers.KIND_COLORS["arrival"],
			c_sick, c_boil, c_rec]:
		_check(_far(c_wish, other, 0.15), "wish color is perceptually distinct from every other tick")

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
	var wish_tip := TimelineMarkers.tooltip_line(
		{"step": 1, "kind": "wish", "label": "💭 Ada wishes: a bike rack"})
	_check(wish_tip == "step 1 — 💭 Ada wishes: a bike rack",
		"wish keeps the plain tooltip (the 💭 marker lives in the label, not EVENT_STYLE)")

	# --- robustness + ordering ---
	var all := ReplayMarkers.collect(frames, names, streams, events, wishes)
	var steps := all.map(func(m: Dictionary) -> int: return m["step"])
	var steps_sorted: Array = steps.duplicate()
	steps_sorted.sort()
	_check(steps == steps_sorted, "markers are sorted by step")
	_check(ReplayMarkers.collect([], [], {}, []).is_empty(), "empty replay -> no markers, no crash")
	_check(ReplayMarkers.collect([], [], {}, [], wishes).is_empty(),
		"empty replay -> no markers even with wishes present, no crash")

	if _failures == 0:
		print("test_replay_markers: all checks passed")
	quit(1 if _failures > 0 else 0)
