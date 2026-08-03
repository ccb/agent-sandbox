extends SceneTree
## Headless unit tests for scripts/dialogue_log.gd: the dedup rules behind the
## viewer's dialogue-log panel (#963). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_dialogue_log.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const DialogueLog := preload("res://scripts/dialogue_log.gd")
const DialogueLogPanel := preload("res://scripts/dialogue_log_panel.gd")

## Small pacing constant so the reveal math stays legible: a window stamped at
## step 10 with 3 lines reveals them at 10, 13, 16.
const L := 3

const NAMES := ["Ana", "Bo"]

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


## `steps` frames of both agents silent, with `chat` stamped on BOTH
## participants (the backend's double-stamp) over [from, to] inclusive.
func _frames(steps: int, chats: Array = []) -> Array:
	var frames: Array = []
	for k in range(steps):
		frames.append({
			"Ana": {"x": 0, "y": 0, "act": "idle", "chat": null},
			"Bo": {"x": 1, "y": 0, "act": "idle", "chat": null},
		})
	for c in chats:
		for k in range(c["from"], mini(c["to"], steps - 1) + 1):
			frames[k]["Ana"]["chat"] = c["chat"]
			frames[k]["Bo"]["chat"] = c["chat"]
	return frames


func _speakers(rows: Array) -> Array:
	return rows.map(func(r: Dictionary) -> String: return String(r["speaker"]))


func _steps(rows: Array) -> Array:
	return rows.map(func(r: Dictionary) -> int: return int(r["step"]))


func _initialize() -> void:
	var window := [["Ana", "hi"], ["Bo", "hey"], ["Ana", "coffee?"]]

	# 1) Degenerate inputs.
	_check(DialogueLog.extract([], NAMES, 10, L).is_empty(), "empty frames -> []")
	_check(DialogueLog.extract(_frames(5), NAMES, -1, L).is_empty(), "up_to < 0 -> []")
	_check(DialogueLog.extract(_frames(5), NAMES, 4, L).is_empty(), "no chat -> []")

	# 2) A whole window stamped at step 10 on BOTH participants, lingering
	#    (carry-forward) until step 30: each line exactly once, chronological.
	var baked := _frames(31, [{"from": 10, "to": 30, "chat": window}])
	var rows := DialogueLog.extract(baked, NAMES, 30, L)
	_check(rows.size() == 3, "double-stamp + lingering -> 3 lines, not 6 or 63")
	_check(_speakers(rows) == ["Ana", "Bo", "Ana"], "lines in transcript order")
	_check(_steps(rows) == [10, 13, 16], "reveals paced one line per L steps")
	_check(rows.map(func(r: Dictionary) -> String: return String(r["with"]))
		== ["Bo", "Ana", "Bo"], "each line labeled with who it's spoken to")

	# 3) Reveal truncation = bubble sync: the log holds only the lines whose
	#    bubble has fired by up_to.
	_check(DialogueLog.extract(baked, NAMES, 10, L).size() == 1, "up_to=onset -> 1 line")
	_check(DialogueLog.extract(baked, NAMES, 12, L).size() == 1, "up_to=12 -> still 1")
	_check(DialogueLog.extract(baked, NAMES, 13, L).size() == 2, "up_to=13 -> 2 lines")
	_check(DialogueLog.extract(baked, NAMES, 16, L).size() == 3, "up_to=16 -> all 3")

	# 4) Backward scrub truncates, and extract(n) is a PREFIX of extract(n+1)
	#    for every n — the panel's append-only fast path relies on this.
	_check(DialogueLog.extract(baked, NAMES, 9, L).is_empty(), "scrub before onset -> []")
	var prefix_ok := true
	var prev_rows: Array = []
	for n in range(0, 31):
		var now := DialogueLog.extract(baked, NAMES, n, L)
		if now.size() < prev_rows.size() or now.slice(0, prev_rows.size()) != prev_rows:
			prefix_ok = false
		prev_rows = now
	_check(prefix_ok, "extract(n) is a prefix of extract(n+1) across the replay")

	# 5) Live growth: the real-LLM path republishes the whole window with one
	#    line appended per step — only the tail is new, and each line's reveal
	#    is the step it arrived (no restarts, no dupes).
	var live := _frames(30,
		[
			{"from": 20, "to": 20, "chat": window.slice(0, 1)},
			{"from": 21, "to": 21, "chat": window.slice(0, 2)},
			{"from": 22, "to": 29, "chat": window},
		])
	var live_rows := DialogueLog.extract(live, NAMES, 29, L)
	_check(live_rows.size() == 3, "growing transcript -> 3 lines, no restarts")
	_check(_steps(live_rows) == [20, 21, 22], "each grown line reveals on arrival")
	_check(_speakers(live_rows) == ["Ana", "Bo", "Ana"], "grown lines in order")

	# 6) A REPLACED transcript (not a prefix of the old one) is a new window,
	#    paced from its own onset.
	var second := [["Bo", "seen Ana?"], ["Ana", "right here"]]
	var replaced := _frames(40,
		[
			{"from": 10, "to": 19, "chat": window},
			{"from": 20, "to": 39, "chat": second},
		])
	var rep_rows := DialogueLog.extract(replaced, NAMES, 39, L)
	_check(rep_rows.size() == 5, "replacement window emits all its lines")
	_check(_steps(rep_rows) == [10, 13, 16, 20, 23], "replacement paced from its onset")
	_check(String(rep_rows[3]["speaker"]) == "Bo", "Bo opens the second window")

	# 7) chat -> null -> the SAME content again is a genuinely new conversation
	#    and re-emits (the bubbles replay it too).
	var again := _frames(40,
		[
			{"from": 10, "to": 14, "chat": window},
			{"from": 25, "to": 39, "chat": window},
		])
	var again_rows := DialogueLog.extract(again, NAMES, 39, L)
	_check(again_rows.size() == 6, "window -> null -> same window re-emits")
	_check(_steps(again_rows) == [10, 13, 16, 25, 28, 31], "re-run paced from step 25")

	# 8) Robustness: live gaps (non-Dictionary frames), a persona missing from a
	#    frame, non-Array chat, and malformed pairs are skipped without error.
	var messy := _frames(20, [{"from": 5, "to": 19, "chat": window}])
	messy[3] = null
	messy[6] = "not a frame"
	(messy[7] as Dictionary).erase("Ana")
	messy[8]["Ana"] = "not an agent entry"
	var messy_rows := DialogueLog.extract(messy, NAMES, 19, L)
	_check(messy_rows.size() == 3, "holes and junk skipped, real lines kept")
	var junk_chat := _frames(10)
	junk_chat[4]["Ana"]["chat"] = "not an array"
	_check(DialogueLog.extract(junk_chat, NAMES, 9, L).is_empty(),
		"non-Array chat -> no rows, no crash")
	var junk_pairs := _frames(20,
		[{"from": 5, "to": 19, "chat": [["Ana", "hi"], "junk", ["solo"], ["Bo", "hey"]]}])
	var junk_rows := DialogueLog.extract(junk_pairs, NAMES, 19, L)
	_check(junk_rows.size() == 2, "malformed pairs skipped, well-formed kept")
	_check(_steps(junk_rows) == [5, 8], "reveal pacing skips no slots for junk")

	# 9) The panel itself: set_rows takes the append fast path on a prefix-
	#    extension and rebuilds (truncates) on anything else, and neutralizes
	#    bbcode in LLM prose. Instantiated headlessly, like the Label checks in
	#    test_bubble_anchor.gd.
	var panel := DialogueLogPanel.new()
	get_root().add_child(panel)
	var log: RichTextLabel = panel.get_child(0).get_child(0).get_child(1)
	_check(log.get_parsed_text().contains("No dialogue yet."), "panel seeds the empty state")
	var r1 := {"time": "08:00", "speaker": "Ana", "with": "Bo", "line": "hi"}
	var r2 := {"time": "08:02", "speaker": "Bo", "line": "[b]not bold[/b]"}
	panel.set_rows([r1])
	_check(log.get_parsed_text().contains("Ana")
		and not log.get_parsed_text().contains("No dialogue yet."),
		"first rows replace the empty state")
	_check(log.get_parsed_text().contains("→  Bo"),
		"the header names who the line is spoken to")
	panel.set_rows([r1, r2])
	var text := log.get_parsed_text()
	_check(text.contains("hi") and text.contains("08:02"),
		"prefix extension appends the tail")
	_check(text.contains("[b]not bold[/b]"),
		"brackets in LLM prose render literally (bbcode neutralized)")
	panel.set_rows([r2])
	text = log.get_parsed_text()
	_check(not text.contains("Ana") and text.contains("Bo"),
		"non-prefix rows rebuild from scratch (backward scrub truncates)")
	panel.set_rows([])
	_check(log.get_parsed_text().contains("No dialogue yet."),
		"emptying restores the empty state")
	panel.free()

	if _failures == 0:
		print("test_dialogue_log: all checks passed")
	quit(1 if _failures > 0 else 0)
