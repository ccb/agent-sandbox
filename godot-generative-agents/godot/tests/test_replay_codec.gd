extends SceneTree
## Headless unit tests for scripts/replay_codec.gd (#941 slim-file rehydration).
## Mirrors the Python round-trip cases in tests/test_replay_codec.py. Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_replay_codec.gd
## Exit 0 = all checks pass; run_smoke_test.sh also greps for the sentinel line
## (a script parse error can exit 0 under --script).

const ReplayCodec := preload("res://scripts/replay_codec.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _entry(x: int, extra: Dictionary = {}) -> Dictionary:
	var e := {"x": x, "y": 2, "act": "reading", "e": "📖"}
	e.merge(extra)
	return e


func _initialize() -> void:
	var lines := [["Ada", "hello"], ["Bob", "hi"]]
	var mems := [{"kind": "event", "importance": 1.0, "text": "saw Bob", "created_turn": 0}]

	# A slim frames array: explicit on change (including explicit null), absent
	# when carried — the shape backend.replay_codec.slim_frames writes.
	var slim := [
		{"Ada": _entry(1, {"reasoning": null, "chat": null, "memories": mems, "trace": []})},
		{"Ada": _entry(2, {"chat": lines})},  # chat starts; the rest carried
		{"Ada": _entry(3)},  # everything carried
		{"Ada": _entry(4, {"chat": null})},  # chat explicitly cleared
	]
	# Positive control FIRST: prove the input really lacks the carried keys, so
	# a fatten_frames that silently became a no-op cannot fake the checks below.
	_check(not (slim[2]["Ada"] as Dictionary).has("chat"),
		"positive control: the carried frame starts without 'chat'")

	var fat := ReplayCodec.fatten_frames(slim)
	_check(fat[1]["Ada"]["memories"] == mems, "memories carried onto the chat frame")
	_check(fat[2]["Ada"]["chat"] == lines, "chat carried forward while unchanged")
	_check(fat[2]["Ada"]["reasoning"] == null, "an explicit null carries forward too")
	_check(fat[2]["Ada"]["trace"] == [], "trace carried forward")
	_check(fat[3]["Ada"]["chat"] == null, "an explicit null is a NEW value, not a carry")
	_check(fat[3]["Ada"]["memories"] == mems, "memories still carried at the end")
	_check(fat[0]["Ada"]["x"] == 1 and fat[3]["Ada"]["x"] == 4,
		"always-on fields are untouched")

	# Identity on a fat (1.0) file: every key explicit -> nothing changes.
	var fat_input := [
		{"Ada": _entry(1, {"reasoning": null, "chat": lines, "memories": mems, "trace": []})},
		{"Ada": _entry(2, {"reasoning": null, "chat": null, "memories": mems, "trace": []})},
	]
	var before := str(fat_input)
	_check(str(ReplayCodec.fatten_frames(fat_input)) == before,
		"fattening an already-fat file is the identity")

	# Conservative: a key never carried is not invented (pre-#359 files have no
	# trace anywhere; inventing one would change loaded content).
	var no_trace := [
		{"Ada": _entry(1, {"chat": null})},
		{"Ada": _entry(2)},
	]
	var fat_nt := ReplayCodec.fatten_frames(no_trace)
	_check(not (fat_nt[1]["Ada"] as Dictionary).has("trace"),
		"a never-seen key stays absent")
	_check((fat_nt[1]["Ada"] as Dictionary).has("chat"), "...while seen keys carry")

	# Version-skewed rows degrade instead of crashing (payload-guards style).
	var skewed := ["not-a-dict", {"Ada": "not-a-dict-either"}, {"Ada": _entry(1)}]
	var fat_sk := ReplayCodec.fatten_frames(skewed)
	_check(fat_sk.size() == 3 and fat_sk[2]["Ada"]["x"] == 1,
		"non-dict frames and entries pass through untouched")

	if _failures == 0:
		print("test_replay_codec: all checks passed")
	quit(1 if _failures > 0 else 0)
