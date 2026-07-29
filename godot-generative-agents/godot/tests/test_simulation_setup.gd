extends SceneTree
## Headless unit tests for scripts/config_body.gd (issue #733): the pure builder
## behind the Simulation Setup scene's POST /config body. Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_simulation_setup.gd
## Exit 0 = all checks pass; 1 = at least one failed (run_smoke_test.sh runs
## this before the scene smoke).

const ConfigBody := preload("res://scripts/config_body.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


# A GET /config `knobs.current`-shaped blob (only the sections/keys the scene reads).
func _knobs() -> Dictionary:
	return {
		"game": {"agent": {"temperature": 0.7, "max_tokens": 128}},
		"retrieval": {"alpha_recency": 1.0, "alpha_importance": 1.0, "alpha_relevance": 1.0},
		"cognition": {"vision_r": 8, "conversation_cooldown_steps": 90, "conversation_max_exchanges": 6},
	}


func _base_state() -> Dictionary:
	# An untouched form: every value equals its server initial, no knob edits.
	return {
		"cast": ["diego", "sofia"],
		"brain": "mock", "initial_brain": "mock",
		"steps": 1080, "initial_steps": 1080,
		"tick": 0.1, "initial_tick": 0.1,
		"max_cost": 0.0,
		"knobs_current": _knobs(),
		"knob_edits": {},
	}


func _initialize() -> void:
	# --- untouched form: only `cast` is sent (the primary control) ---
	var body := ConfigBody.build_post_body(_base_state())
	_check(body.get("cast") == ["diego", "sofia"], "cast always sent")
	_check(body.size() == 1, "untouched form sends cast only (no brain/steps/tick/sim_config)")

	# --- changed brain is sent ---
	var s := _base_state()
	s["brain"] = "scripted"
	body = ConfigBody.build_post_body(s)
	_check(body.get("brain") == "scripted", "changed brain is sent")

	# --- changed steps is sent as an int ---
	s = _base_state()
	s["steps"] = 500
	body = ConfigBody.build_post_body(s)
	_check(body.get("steps") == 500 and typeof(body["steps"]) == TYPE_INT, "changed steps sent as int")

	# --- changed tick is sent as tick_seconds ---
	s = _base_state()
	s["tick"] = 0.5
	body = ConfigBody.build_post_body(s)
	_check(is_equal_approx(body.get("tick_seconds", -1.0), 0.5), "changed tick sent as tick_seconds")

	# --- max_cost rides only with the llm brain and a positive value ---
	s = _base_state()
	s["brain"] = "mock"
	s["max_cost"] = 10.0
	body = ConfigBody.build_post_body(s)
	_check(not body.has("max_cost"), "max_cost dropped on a non-llm brain")
	s = _base_state()
	s["brain"] = "llm"
	s["max_cost"] = 0.0
	body = ConfigBody.build_post_body(s)
	_check(not body.has("max_cost"), "max_cost dropped when zero even on llm")
	s = _base_state()
	s["brain"] = "llm"
	s["max_cost"] = 10.0
	body = ConfigBody.build_post_body(s)
	_check(is_equal_approx(body.get("max_cost", -1.0), 10.0), "max_cost sent on llm brain when positive")

	# --- a knob edit merges over current; untouched keys are preserved ---
	s = _base_state()
	s["knob_edits"] = {"retrieval": {"alpha_recency": 1.5}}
	body = ConfigBody.build_post_body(s)
	_check(body.has("sim_config"), "knob edit produces a sim_config block")
	var sc: Dictionary = body["sim_config"]
	_check(is_equal_approx(sc["retrieval"]["alpha_recency"], 1.5), "edited retrieval key applied")
	_check(is_equal_approx(sc["retrieval"]["alpha_relevance"], 1.0), "untouched retrieval key preserved")
	_check(sc["cognition"]["vision_r"] == 8, "untouched cognition section preserved")

	# --- merge_knobs does not mutate its input ---
	var cur := _knobs()
	var merged := ConfigBody.merge_knobs(cur, {"cognition": {"vision_r": 12}})
	_check(merged["cognition"]["vision_r"] == 12, "merge overlays the edit")
	_check(cur["cognition"]["vision_r"] == 8, "merge leaves the input dictionary unchanged")

	# --- a NESTED knob edit (game.agent.temperature) merges deep, preserving siblings ---
	s = _base_state()
	s["knob_edits"] = {"game": {"agent": {"temperature": 0.9}}}
	body = ConfigBody.build_post_body(s)
	sc = body["sim_config"]
	_check(is_equal_approx(sc["game"]["agent"]["temperature"], 0.9), "nested edited leaf (game.agent.temperature) applied")
	_check(sc["game"]["agent"]["max_tokens"] == 128, "sibling leaf (game.agent.max_tokens) preserved under a nested edit")
	_check(sc["cognition"]["vision_r"] == 8, "unrelated section preserved under a nested edit")

	# --- merge_knobs deep-merges a nested path without mutating input ---
	cur = _knobs()
	merged = ConfigBody.merge_knobs(cur, {"game": {"agent": {"temperature": 1.2}}})
	_check(is_equal_approx(merged["game"]["agent"]["temperature"], 1.2), "nested merge overlays the deep leaf")
	_check(merged["game"]["agent"]["max_tokens"] == 128, "nested merge preserves the deep sibling")
	_check(is_equal_approx(cur["game"]["agent"]["temperature"], 0.7), "nested merge leaves the input unchanged")

	# --- planner knob (#791): only a CHANGED plan is sent ---
	s = _base_state()
	s["plan"] = "auto"
	s["initial_plan"] = "auto"
	body = ConfigBody.build_post_body(s)
	_check(not body.has("plan"), "untouched plan is omitted (keeps the session's request)")
	s["plan"] = "schedule"
	body = ConfigBody.build_post_body(s)
	_check(body.get("plan") == "schedule", "changed plan is sent")
	# No planner row rendered (a pre-#790 backend serves no `plans`): the scene
	# passes empty strings for both -> nothing is sent.
	body = ConfigBody.build_post_body(_base_state())
	_check(not body.has("plan"), "absent plan state sends nothing")

	# --- seed_plan (#791): a re-run reproduces the REQUEST, not the resolution ---
	_check(
		ConfigBody.seed_plan({"plan_request": "auto", "plan": "llm"}) == "auto",
		"seed_plan prefers the saved plan_request"
	)
	_check(ConfigBody.seed_plan({"plan": "llm"}) == "llm", "seed_plan falls back to the resolved plan")
	_check(ConfigBody.seed_plan({}) == "", "seed_plan with no planner in the seed -> empty")

	# --- thinking-depth knob (#845): only a CHANGED effort is sent ---
	s = _base_state()
	s["effort"] = "default"
	s["initial_effort"] = "default"
	body = ConfigBody.build_post_body(s)
	_check(not body.has("effort"), "untouched effort is omitted (keeps the session's depth)")
	s["effort"] = "medium"
	body = ConfigBody.build_post_body(s)
	_check(body.get("effort") == "medium", "changed effort is sent")
	# "default" is a real request, not an absence: it is how a re-run of a run
	# that asked for no thinking clears a depth the server launched with.
	s["effort"] = "default"
	s["initial_effort"] = "high"
	body = ConfigBody.build_post_body(s)
	_check(body.get("effort") == "default", "clearing a depth back to default is sent")
	# No effort row rendered (a pre-#845 backend serves no `efforts`).
	body = ConfigBody.build_post_body(_base_state())
	_check(not body.has("effort"), "absent effort state sends nothing")

	# --- model knob (#887): only a CHANGED model is sent ---
	s = _base_state()
	s["model"] = "claude-haiku-4-5"
	s["initial_model"] = "claude-haiku-4-5"
	body = ConfigBody.build_post_body(s)
	_check(not body.has("model"), "untouched model is omitted (keeps the session's model)")
	s["model"] = "claude-sonnet-5"
	body = ConfigBody.build_post_body(s)
	_check(body.get("model") == "claude-sonnet-5", "changed model is sent")
	# No model row rendered (a pre-#887 backend serves no `models`).
	body = ConfigBody.build_post_body(_base_state())
	_check(not body.has("model"), "absent model state sends nothing")

	# --- effective_plan (#791): the hint label's client-side auto rule ---
	_check(ConfigBody.effective_plan("auto", "llm") == "llm", "auto resolves to llm under the llm brain")
	_check(ConfigBody.effective_plan("auto", "mock") == "schedule", "auto resolves to schedule under a free brain")
	_check(ConfigBody.effective_plan("schedule", "llm") == "schedule", "an explicit plan passes through")

	if _failures == 0:
		print("test_simulation_setup: all checks passed")
	quit(1 if _failures > 0 else 0)
