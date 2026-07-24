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
#   knob_edits     Dictionary     {section: {key: value}} for CHANGED knobs only
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
# untouched keys round-trip unchanged -- a partial sim_config section would
# otherwise reset the keys it omits to their dataclass defaults on the server.
static func merge_knobs(current: Dictionary, edits: Dictionary) -> Dictionary:
	var out: Dictionary = current.duplicate(true)
	for section in edits:
		if not out.has(section) or typeof(out[section]) != TYPE_DICTIONARY:
			out[section] = {}
		for key in edits[section]:
			out[section][key] = edits[section][key]
	return out
