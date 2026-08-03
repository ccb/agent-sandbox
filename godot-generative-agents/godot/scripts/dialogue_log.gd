extends RefCounted
## Dialogue-history extraction for the viewer's dialogue-log panel (#963).
## Pure over the `_frames` array shape so the dedup rules are unit-testable
## headlessly (tests/test_dialogue_log.gd) without standing up the viewer scene.
##
## A frame's `chat` is the SHARED conversation window ([[speaker, line], ...])
## stamped identically on BOTH participants, and it carries forward unchanged
## on every following frame until replaced (schema 1.1 fattening). A baked
## replay stamps the whole window at its onset step; the live real-LLM path
## grows it one line per step. Both shapes reduce to the same log here.


## The chronological dialogue history visible at step `up_to` (inclusive):
## an Array of { "step": int, "speaker": String, "line": String }, where
## "step" is the step the line is SPOKEN on screen — a window stamped whole
## at step k plays one line per `line_steps` (the bubbles' pacing), so the
## log grows in sync with the bubbles and timestamps match what was watched.
##
## Dedup rules, in the order the loop applies them:
##   lingering     — `chat == was` (deep value compare) skips carried-forward
##                   frames, so a window is read once, not once per step.
##   double-stamp  — only the transcript's OPENING speaker's frame records it
##                   (the same trick social_graph_panel._recompute uses), so
##                   the shared window counts once, not once per participant.
##   live growth   — a `chat` that merely EXTENDS the previous value emits
##                   only the appended tail (content dedup: the real-LLM path
##                   republishes the whole window every added line).
## A replaced transcript (or null -> window) starts a fresh window; a window
## that closes and later returns with identical content is a genuinely new
## conversation and re-emits — the bubbles replay it too.
static func extract(frames: Array, names: Array, up_to: int, line_steps: int) -> Array:
	var out: Array = []
	var prev := {}     # name -> the `chat` value seen on the previous frame
	var emitted := {}  # name -> lines of the current window already emitted
	var last := mini(up_to, frames.size() - 1)
	for k in range(0, last + 1):
		if not frames[k] is Dictionary:
			continue  # live gap the poller hasn't backfilled yet
		var frame: Dictionary = frames[k]
		for name_v in names:
			var name := String(name_v)
			if not frame.get(name) is Dictionary:
				continue
			var chat: Variant = (frame[name] as Dictionary).get("chat")
			var was: Variant = prev.get(name)
			prev[name] = chat
			if chat == null or not chat is Array or (chat as Array).is_empty():
				emitted[name] = 0  # window closed; the next one starts fresh
				continue
			if chat == was:
				continue  # carry-forward lingering, already read
			var lines: Array = chat
			var opener: Variant = lines[0]
			if not (opener is Array and (opener as Array).size() >= 2 \
					and String(opener[0]) == name):
				continue  # the partner's stamp (or malformed opener) — skip
			var start := int(emitted.get(name, 0)) if _extends(was, lines) else 0
			var batch := 0  # position within this newly-observed batch
			for idx in range(start, lines.size()):
				var pair: Variant = lines[idx]
				if not (pair is Array and (pair as Array).size() >= 2):
					continue
				var reveal := k + batch * line_steps
				batch += 1
				if reveal > up_to:
					continue  # the bubble hasn't reached this line yet
				out.append({
					"step": reveal,
					"speaker": String(pair[0]),
					"line": String(pair[1]),
				})
			emitted[name] = lines.size()
	# Total order (step, then speaker, then line): sort_custom isn't stable, so
	# ties must break deterministically for extract(n) to stay a prefix of
	# extract(n+1) — the panel's append-only fast path relies on that.
	out.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		if a["step"] != b["step"]:
			return int(a["step"]) < int(b["step"])
		if a["speaker"] != b["speaker"]:
			return String(a["speaker"]) < String(b["speaker"])
		return String(a["line"]) < String(b["line"]))
	return out


## true when `chat` is `was` plus appended lines — the live growth case.
static func _extends(was: Variant, chat: Array) -> bool:
	if not was is Array:
		return false
	var w: Array = was
	if w.is_empty() or w.size() >= chat.size():
		return false
	return chat.slice(0, w.size()) == w
