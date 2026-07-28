extends SceneTree
## Headless unit tests for scripts/conversation_text.gd: the transcript formatting
## used by the viewer's expanded conversation bubble. Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_conversation_text.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const ConversationText := preload("res://scripts/conversation_text.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# 1) Multi-turn: order preserved, one "Speaker: line" per turn, both speakers.
	var multi := ConversationText.full_transcript(
		[["Diego", "hi"], ["Sofia", "yo"], ["Diego", "bye"]])
	_check(multi == "Diego: hi\nSofia: yo\nDiego: bye", "multi-turn formats in order")

	# 2) Single line: no trailing newline.
	_check(ConversationText.full_transcript([["Diego", "hi"]]) == "Diego: hi",
		"single line, no trailing newline")

	# 3) Empty transcript -> empty string.
	_check(ConversationText.full_transcript([]) == "", "empty transcript -> empty string")

	# 4) Malformed pairs (fewer than 2 fields) are skipped; the rest still format.
	var mixed := ConversationText.full_transcript(
		[["Diego", "hi"], ["Sofia"], ["Diego", "bye"]])
	_check(mixed == "Diego: hi\nDiego: bye", "malformed pair skipped")

	# 5) No truncation: a line longer than the collapsed 120-char clip is verbatim.
	var long_line := "x".repeat(200)
	var out := ConversationText.full_transcript([["Diego", long_line]])
	_check(out == "Diego: " + long_line, "long line preserved verbatim (no truncation)")

	if _failures == 0:
		print("test_conversation_text: all checks passed")
	quit(1 if _failures > 0 else 0)
