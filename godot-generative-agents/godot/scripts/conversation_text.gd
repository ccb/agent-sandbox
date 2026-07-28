extends RefCounted
## Pure formatting for the viewer's expanded conversation bubble (viewer.gd).
## Turns the shared transcript [[speaker, line], …] into one labeled, multi-line
## string — "Speaker: line" per turn, in order. Extracted so the format is
## unit-testable headlessly (tests/test_conversation_text.gd) without standing up
## the viewer scene. Pairs with fewer than 2 fields are skipped; text is kept
## verbatim (no truncation — the bubble grows to fit, see bubble_anchor.gd).


## Join a transcript into labeled lines: [[speaker, line], …] -> "A: hi\nB: yo".
static func full_transcript(lines: Array) -> String:
	var out: PackedStringArray = []
	for pair in lines:
		if pair is Array and (pair as Array).size() >= 2:
			out.append("%s: %s" % [String(pair[0]), String(pair[1])])
	return "\n".join(out)
