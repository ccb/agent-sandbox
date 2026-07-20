extends RefCounted
## Pure logic for the day-plans pop-up (issue #251): turn a persona's authored
## schedule into planned ribbon segments, and classify each replay frame into
## what the agent was actually doing. Key insight (see the spec): a travel-leg
## act is "walking to <place> @ <destination address>" — it carries the
## schedule's EXACT place name with that place's resolved address, so the
## place→address mapping is learnable from the frames themselves. That is what
## lets a room-level place ("Van Pelt — Kamin Gallery", whose act building
## segment is just "Van Pelt Library") pair exactly with its planned segment.
## Pure functions over plain Arrays/Dictionaries — unit-tested headlessly
## (tests/test_day_plan_model.gd).

const ReplayMarkers := preload("res://scripts/replay_markers.gd")

const WALKING_PREFIX := "walking to "


static func axis_len(frames_count: int, schedules: Array) -> int:
	# The shared time axis: long enough for the frames we have AND the longest
	# explicitly-planned day, so live mode (frames still growing) gets a stable
	# width. `schedules` is an Array of schedule Arrays (one per persona).
	var longest := 0
	for schedule in schedules:
		var total := 0
		for stop in (schedule as Array):
			var steps: Variant = (stop as Dictionary).get("steps")
			if steps != null:
				total += int(steps)
		longest = maxi(longest, total)
	return maxi(frames_count, longest)


static func planned_segments(schedule: Array, axis: int) -> Array:
	# Lay the stops end-to-end in step units: explicit `steps` sized as
	# authored; null-steps stops split whatever the explicit ones leave,
	# the last null absorbing the integer-division leftover. (In authored
	# worlds only the final stop is null — "stay for the rest of the day".)
	if schedule.is_empty():
		return []
	var explicit := 0
	var nulls := 0
	for stop in schedule:
		var steps: Variant = (stop as Dictionary).get("steps")
		if steps == null:
			nulls += 1
		else:
			explicit += int(steps)
	var remainder := maxi(axis - explicit, 0)
	var null_share := remainder / nulls if nulls > 0 else 0
	var segments: Array = []
	var cursor := 0
	var nulls_seen := 0
	for stop in schedule:
		var steps: Variant = (stop as Dictionary).get("steps")
		var seg_len: int
		if steps == null:
			nulls_seen += 1
			# The last null takes the leftover so the ribbons end flush.
			if nulls_seen == nulls:
				seg_len = remainder - null_share * (nulls - 1)
			else:
				seg_len = null_share
		else:
			seg_len = int(steps)
		segments.append({"place": String((stop as Dictionary).get("place", "")),
			"activity": String((stop as Dictionary).get("activity", "")),
			"start": cursor, "len": seg_len})
		cursor += seg_len
	return segments


static func actual_slots(frames: Array, name: String) -> Array:
	# One {kind, place} per frame for this agent. Pass 1 learns place→address
	# from every walking leg; pass 2 classifies each frame: transit (toward a
	# named place), at (a learned address), or other (grey — off-plan).
	var place_by_addr := {}
	for frame in frames:
		var act := String(((frame as Dictionary).get(name, {}) as Dictionary).get("act", ""))
		if act.begins_with(WALKING_PREFIX):
			var addr := _address_of(act)
			if addr != "":
				place_by_addr[addr] = transit_place(act)
	var slots: Array = []
	for frame in frames:
		var act := String(((frame as Dictionary).get(name, {}) as Dictionary).get("act", ""))
		if act.begins_with(WALKING_PREFIX):
			slots.append({"kind": "transit", "place": transit_place(act)})
			continue
		var addr := _address_of(act)
		if place_by_addr.has(addr):
			slots.append({"kind": "at", "place": String(place_by_addr[addr])})
		else:
			slots.append({"kind": "other", "place": ReplayMarkers.building_of(act)})
	return slots


static func transit_place(act: String) -> String:
	# "walking to <place> @ <address>" -> "<place>"; "" for a non-walking act.
	if not act.begins_with(WALKING_PREFIX):
		return ""
	var rest := act.substr(WALKING_PREFIX.length())
	var at := rest.find(" @ ")
	return rest.substr(0, at) if at >= 0 else rest


static func _address_of(act: String) -> String:
	# The full address after " @ " ("" if the act has none). Kept as the raw
	# string: walking-leg and perform addresses match byte-for-byte per the
	# contract, so no normalization is needed (or wanted).
	var at := act.find(" @ ")
	return act.substr(at + 3) if at >= 0 else ""
