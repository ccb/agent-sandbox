extends RefCounted
## Pure cumulative most-taken-actions tally for the viewer HUD (issue #700).
##
## The viewer twin of tools/most_common_actions.py (#699): the SAME filter +
## ranking, but "up to the current cursor" -- it counts only the events at or
## before a given playhead step, so scrubbing the replay backward LOWERS the
## counts (never a monotone-only counter). Pure functions over plain
## Arrays/Dictionaries (no scene nodes), so the whole file is unit-testable
## headlessly (tests/test_action_tally.gd) -- the same shape as replay_markers.gd.

# Engine-internal GameEvent.action values that are NOT player/NPC commands:
# EventKind.TRIGGER and EventKind.SOUND (text_adventure_games/enums.py). The
# same set most_common_actions.py drops (#699), reproduced here rather than
# imported -- this is a viewer with no engine dependency. If the engine grows a
# new non-command EventKind, add its action string here (and in #699's tool).
const EXCLUDED_ACTIONS := ["trigger", "sound"]


static func tally(events: Array, up_to_step: int, top_n: int) -> Array:
	## Rank the actions taken at or before `up_to_step`, most-taken first.
	## Returns at most `top_n` rows: [{"action": String, "count": int}, ...].
	##
	## Dropped: engine-internal kinds (EXCLUDED_ACTIONS), empty actions, non-dict
	## records, and records whose `turn` is missing, non-numeric, negative, or
	## beyond the cursor -- so a partial or version-skewed payload degrades to
	## fewer rows rather than a crash (#638). Ranking is count desc, ties broken
	## by the action verb ascending; both criteria live in the sort key, so the
	## order is fully deterministic and never depends on dict iteration order.
	var counts := {}  # action verb -> count
	for rec in events:
		if typeof(rec) != TYPE_DICTIONARY:
			continue
		var e := rec as Dictionary
		var action := String(e.get("action", "")).strip_edges()
		if action == "" or action in EXCLUDED_ACTIONS:
			continue
		# JSON numbers arrive as int or float; a missing/null/string turn can't be
		# placed on the timeline, so skip it rather than int()-crash on null (#638).
		var turn_val: Variant = e.get("turn")
		if typeof(turn_val) != TYPE_INT and typeof(turn_val) != TYPE_FLOAT:
			continue
		var turn := int(turn_val)
		if turn < 0 or turn > up_to_step:
			continue
		counts[action] = int(counts.get(action, 0)) + 1

	var rows: Array = []
	for action in counts:
		rows.append({"action": action, "count": int(counts[action])})
	rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		if int(a["count"]) != int(b["count"]):
			return int(a["count"]) > int(b["count"])
		return String(a["action"]) < String(b["action"]))
	# slice(0, top_n) returns the first top_n rows (all of them if fewer exist),
	# and an empty array for top_n <= 0.
	return rows.slice(0, maxi(top_n, 0))
