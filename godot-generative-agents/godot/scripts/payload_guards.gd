extends RefCounted
## Pure guards for the viewer's two data boundaries (issue #638): a partial or
## version-skewed payload must degrade to "skip + warn", never crash the hot
## render loop or die on connect. The viewer already guards this way in its cold
## paths (heatmap_panel, day-plans, markers use .get()/typeof checks) -- these
## helpers give the hot render loop and the load/handshake path the same
## discipline. All static, no scene nodes, so the whole set is unit-testable
## headless (tests/test_payload_guards.gd).

# --- frame / agent field access (the hot render loop) ---


static func agent_entry(frames: Array, i: int, name: String) -> Dictionary:
	## The agent's entry at frame `i`, or {} when the index is out of range, the
	## frame isn't a dict, the persona is absent (a partial frame, #605), or its
	## entry isn't a dict. Callers skip a {} entry instead of hard-indexing null.
	if i < 0 or i >= frames.size():
		return {}
	var frame: Variant = frames[i]
	if typeof(frame) != TYPE_DICTIONARY:
		return {}
	var entry: Variant = (frame as Dictionary).get(name)
	return entry if typeof(entry) == TYPE_DICTIONARY else {}


static func tile_of(entry: Dictionary) -> Vector2i:
	## The entry's tile, defaulting a missing coordinate to 0 rather than
	## crashing on a hard index of a partial entry.
	return Vector2i(int(entry.get("x", 0)), int(entry.get("y", 0)))


static func act_of(entry: Dictionary) -> String:
	return String(entry.get("act", ""))


static func emoji_of(entry: Dictionary) -> String:
	return String(entry.get("e", ""))


# --- load / handshake meta guard ---

const REQUIRED_TOP := ["meta", "frames"]
const REQUIRED_META := ["tile_px", "personas"]


static func replay_load_error(data: Variant) -> String:
	## "" when `data` is a structurally-loadable replay; otherwise a
	## human-readable reason, so the loader can emit a single push_error and
	## abort gracefully instead of hard-indexing a missing key on a truncated
	## re-bake or a version-skewed backend.
	if typeof(data) != TYPE_DICTIONARY:
		return "payload is not a JSON object"
	var d := data as Dictionary
	for k in REQUIRED_TOP:
		if not d.has(k):
			return "payload is missing required key '%s'" % k
	if typeof(d["meta"]) != TYPE_DICTIONARY:
		return "meta is not an object"
	if typeof(d["frames"]) != TYPE_ARRAY:
		return "frames is not an array"
	var meta := d["meta"] as Dictionary
	for k in REQUIRED_META:
		if not meta.has(k):
			return "meta is missing required key '%s'" % k
	if typeof(meta["personas"]) != TYPE_ARRAY:
		return "meta.personas is not an array"
	return ""


static func schema_ok(meta: Dictionary, supported: String) -> bool:
	## A version rail: an absent schema_version is tolerated (older payloads
	## predate it) so this returns true; a present-but-different one returns
	## false so the caller can warn about drift instead of silently
	## mis-rendering.
	var v := String(meta.get("schema_version", ""))
	return v == "" or v == supported


# --- feed record kind ---

const KNOWN_KINDS := ["frame", "status", "engine", "wish"]


static func is_known_kind(kind: String) -> bool:
	## Whether the change-feed record kind is one this viewer renders. An
	## unknown kind (some future backend record type) should be warned about,
	## not dropped without a breadcrumb. `wish` (#622) is known as of #625 (the
	## viewer surfaces it: scene marker + HUD row + timeline). NB: `intervention`
	## is a real emitted kind still missing from KNOWN_KINDS — tracked in #687.
	return KNOWN_KINDS.has(kind)


# --- gap clamp ---

const MAX_GAP := 10000


static func gap_too_large(step: int, size: int) -> bool:
	## Whether padding the frame buffer up to `step` would allocate an absurd
	## number of hold-frames -- a corrupt/huge step index must be rejected, not
	## grown into unboundedly.
	return step - size > MAX_GAP
