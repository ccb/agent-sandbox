extends RefCounted
## Pure builder for the POST /config body from the Simulation Setup form
## (issue #733). Free functions over plain Dictionaries/Arrays -- no scene
## nodes -- so the whole file is unit-testable headlessly
## (tests/test_simulation_setup.gd), the same shape as action_tally.gd.
##
## Only fields the user actually CHANGED from the server's current values are
## sent (POST /config's "omit = keep current" contract), except `cast`, which
## is the scene's primary control and is always sent. `max_cost` rides only
## with the llm brain -- the backend 400s it with any other brain.


# Build the POST /config body from a snapshot of the form state.
# `state` keys:
#   cast           Array[String]  persona ids currently checked
#   brain          String         selected brain
#   initial_brain  String         run.brain from GET /config
#   steps          int            steps spinbox value
#   initial_steps  int            run.steps
#   tick           float          tick-seconds spinbox value
#   initial_tick   float          run.tick_seconds
#   max_cost       float          cost spinbox value (0.0 = unset)
#   knobs_current  Dictionary     GET /config's knobs.current
#   knob_edits     Dictionary     nested dict keyed by path segments, for CHANGED knobs only
static func build_post_body(state: Dictionary) -> Dictionary:
	var body := {"cast": state.get("cast", [])}
	if state.get("brain", "") != state.get("initial_brain", ""):
		body["brain"] = state.get("brain", "")
	if int(state.get("steps", 0)) != int(state.get("initial_steps", 0)):
		body["steps"] = int(state.get("steps", 0))
	if not is_equal_approx(float(state.get("tick", 0.0)), float(state.get("initial_tick", 0.0))):
		body["tick_seconds"] = float(state.get("tick", 0.0))
	if state.get("brain", "") == "llm" and float(state.get("max_cost", 0.0)) > 0.0:
		body["max_cost"] = float(state.get("max_cost", 0.0))
	var edits: Dictionary = state.get("knob_edits", {})
	if not edits.is_empty():
		body["sim_config"] = merge_knobs(state.get("knobs_current", {}), edits)
	return body


# Overlay CHANGED knob values onto a deep copy of the server's current knobs, so
# untouched keys round-trip unchanged. Recursive so an edit can reach a nested
# path (e.g. game/agent/temperature) without clobbering its siblings; the input
# dictionaries are never mutated (current is deep-copied; edits is read-only).
static func merge_knobs(current: Dictionary, edits: Dictionary) -> Dictionary:
	var out: Dictionary = current.duplicate(true)
	_deep_merge(out, edits)
	return out


# Recursively overlay `edits` onto `into` (mutating `into`, which is already a
# fresh deep copy): a dict value merges into the matching sub-dict; any other
# value overwrites the leaf.
static func _deep_merge(into: Dictionary, edits: Dictionary) -> void:
	for k in edits:
		var v: Variant = edits[k]
		if typeof(v) == TYPE_DICTIONARY and typeof(into.get(k)) == TYPE_DICTIONARY:
			_deep_merge(into[k], v)
		else:
			into[k] = v.duplicate(true) if typeof(v) == TYPE_DICTIONARY else v
