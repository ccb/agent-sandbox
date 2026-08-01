extends RefCounted
## The read side of the #941 carry-forward frame encoding (the write side is
## backend/replay_codec.py — one Python slims, this fattens).
##
## A schema-1.1 replay FILE omits an agent's sticky fields ("reasoning",
## "chat", "memories", "trace") on frames where the value is unchanged from
## that agent's previous frame: absent = carry forward, present (including an
## explicit null) = a new value. Rehydrating at load hands every downstream
## reader — the speech-bubble differ, the persona inspector, the marker and
## social-graph scans, seek — the exact fat rows a pre-#941 file carried, so
## none of them change.
##
## Conservative, mirroring the Python: a key an agent has never carried stays
## absent (pre-#359 replays have no "trace" anywhere; readers .get() absent
## keys already). Fattening an already-fat 1.0 file is the identity.

const CARRY_FIELDS := ["reasoning", "chat", "memories", "trace"]


static func fatten_frames(frames: Array) -> Array:
	## Rehydrate in place (the caller owns the freshly parsed JSON) and return
	## *frames* for call-site convenience. Carried values are shared by
	## reference — cheap, and safe because nothing downstream mutates entries.
	var carried := {}  # agent name -> {field: last explicit value}
	for frame in frames:
		if typeof(frame) != TYPE_DICTIONARY:
			continue  # version-skewed row; the payload guards warn elsewhere
		for name in (frame as Dictionary):
			var entry: Variant = frame[name]
			if typeof(entry) != TYPE_DICTIONARY:
				continue
			var agent_carry: Dictionary = carried.get_or_add(name, {})
			for k in CARRY_FIELDS:
				if (entry as Dictionary).has(k):
					agent_carry[k] = entry[k]
				elif agent_carry.has(k):
					entry[k] = agent_carry[k]
	return frames
