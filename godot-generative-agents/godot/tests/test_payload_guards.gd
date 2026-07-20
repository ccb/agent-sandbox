extends SceneTree
## Headless unit tests for scripts/payload_guards.gd (issue #638). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_payload_guards.gd
## Exit 0 = all checks pass; 1 = at least one failed (run_smoke_test.sh runs
## this before the scene smoke).

const PayloadGuards := preload("res://scripts/payload_guards.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	var frames := [
		{"Ada": {"x": 3, "y": 4, "act": "studying @ X", "e": "📖"}},
		{"Ada": {"x": 5, "y": 6}},  # a partial entry: no act/e
		{"Bob": {"x": 1, "y": 1}},  # Ada absent this frame (partial frame, #605)
		"not-a-dict",  # a version-skewed frame that isn't an object
	]

	# --- agent_entry: the hot-loop lookup never hard-indexes null ---
	_check(PayloadGuards.agent_entry(frames, 0, "Ada")["x"] == 3,
		"agent_entry returns the entry when present")
	_check(PayloadGuards.agent_entry(frames, 2, "Ada").is_empty(),
		"agent_entry -> {} when the persona is absent from the frame")
	_check(PayloadGuards.agent_entry(frames, 3, "Ada").is_empty(),
		"agent_entry -> {} when the frame is not a dict")
	_check(PayloadGuards.agent_entry(frames, 99, "Ada").is_empty(),
		"agent_entry -> {} when the frame index is out of range")
	_check(PayloadGuards.agent_entry(frames, -1, "Ada").is_empty(),
		"agent_entry -> {} on a negative index")

	# --- field readers default instead of crashing ---
	_check(PayloadGuards.tile_of(frames[0]["Ada"]) == Vector2i(3, 4),
		"tile_of reads x/y")
	_check(PayloadGuards.tile_of(frames[1]["Ada"]) == Vector2i(5, 6),
		"tile_of reads a partial entry (x/y present)")
	_check(PayloadGuards.tile_of({}) == Vector2i.ZERO,
		"tile_of -> (0,0) when x/y are missing")
	_check(PayloadGuards.act_of(frames[0]["Ada"]) == "studying @ X",
		"act_of reads act")
	_check(PayloadGuards.act_of(frames[1]["Ada"]) == "",
		"act_of -> '' when act is missing")
	_check(PayloadGuards.emoji_of(frames[1]["Ada"]) == "",
		"emoji_of -> '' when e is missing")

	# --- replay_load_error: one push_error + graceful abort, not a crash ---
	var good := {"meta": {"tile_px": 16, "personas": [{"name": "Ada"}]}, "frames": []}
	_check(PayloadGuards.replay_load_error(good) == "",
		"a structurally-complete replay has no load error")
	_check(PayloadGuards.replay_load_error(42) != "",
		"a non-object payload is a load error")
	_check(PayloadGuards.replay_load_error({"frames": []}) != "",
		"a payload missing meta is a load error")
	_check(PayloadGuards.replay_load_error({"meta": {"tile_px": 16, "personas": []}}) != "",
		"a payload missing frames is a load error")
	_check(PayloadGuards.replay_load_error({"meta": {"personas": []}, "frames": []}) != "",
		"meta missing tile_px is a load error")
	_check(PayloadGuards.replay_load_error({"meta": {"tile_px": 16}, "frames": []}) != "",
		"meta missing personas is a load error")
	_check(
		PayloadGuards.replay_load_error(
			{"meta": {"tile_px": 16, "personas": "nope"}, "frames": []}) != "",
		"meta.personas that isn't an array is a load error")

	# --- schema_ok: a version rail that tolerates absent/unknown, flags drift ---
	_check(PayloadGuards.schema_ok({"schema_version": "1"}, "1"),
		"matching schema_version is ok")
	_check(PayloadGuards.schema_ok({}, "1"),
		"absent schema_version is tolerated (older payloads)")
	_check(not PayloadGuards.schema_ok({"schema_version": "2"}, "1"),
		"a different schema_version is flagged")

	# --- is_known_kind: unknown feed kinds are detectable (to warn, not drop silently) ---
	_check(PayloadGuards.is_known_kind("frame"), "frame is a known kind")
	_check(PayloadGuards.is_known_kind("status"), "status is a known kind")
	_check(PayloadGuards.is_known_kind("engine"), "engine is a known kind")
	_check(PayloadGuards.is_known_kind("wish"), "wish is a known kind (#625)")
	_check(not PayloadGuards.is_known_kind("intervention"),
		"a newer backend's 'intervention' is still unknown")
	_check(not PayloadGuards.is_known_kind(""), "empty kind is unknown")

	# --- gap_too_large: a corrupt step can't allocate unboundedly ---
	_check(not PayloadGuards.gap_too_large(5, 3), "a small gap is allowed")
	_check(PayloadGuards.gap_too_large(1_000_000, 3), "a huge gap is rejected")

	if _failures == 0:
		print("test_payload_guards: all checks passed")
	quit(1 if _failures > 0 else 0)
