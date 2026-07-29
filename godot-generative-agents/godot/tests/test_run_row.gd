extends SceneTree
## Headless unit tests for scripts/run_row.gd (issue #716). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_run_row.gd

const RunRow := preload("res://scripts/run_row.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	var row := {
		"id": "run-2-live", "status": "running", "model": "claude-haiku-4-5",
		"created": "2026-07-22T12:34:56+00:00", "cost": 0.0123, "steps": 42,
	}
	var s := RunRow.label(row)
	_check(s.begins_with("run-2-live · running · claude-haiku-4-5 · 2026-07-22 12:34"),
		"label leads with id/status/model + short time")
	_check(s.contains("$0.0123") and s.ends_with("42 steps"),
		"label carries cost + steps")

	# A mock-brain run has model == null -> "mock".
	var mockrow := {"id": "r1", "status": "finished", "model": null,
		"created": "2026-07-22T09:00:00+00:00", "cost": 0.0, "steps": 5}
	_check(RunRow.label(mockrow).contains(" · mock · "), "null model renders as 'mock'")

	# An odd/short created string passes through rather than crashing.
	var weird := {"id": "r2", "status": "x", "model": "m", "created": "soon", "cost": 12.5, "steps": 1}
	var w := RunRow.label(weird)
	_check(w.contains(" · soon · "), "unparseable created passes through")
	_check(w.contains("$12.50"), "cost >= $10 uses two decimals")

	# --- config summary + detail (#734) ---
	var configured := {
		"id": "run-x", "status": "finished", "model": "claude-haiku-4-5",
		"created": "2026-07-24T10:00:00+00:00", "cost": 0.5, "steps": 10,
		"config": {
			"cast": ["diego", "tanaka", "sofia"], "brain": "llm",
			"sim_config": {"game": {"agent": {"temperature": 0.7}}},
			"run": {"steps": 10, "tick_seconds": 0.1, "max_cost": 5.0},
		},
	}
	_check(RunRow.config_summary(configured) == "3 persona(s) · llm · temp 0.7",
		"config summary reads cast size, brain, temperature")
	var detail := RunRow.config_detail(configured)
	_check(detail.contains("\"cast\"") and detail.contains("diego"),
		"config detail is the pretty-printed block")
	_check(typeof(JSON.parse_string(detail)) == TYPE_DICTIONARY,
		"config detail is valid JSON")

	# A run with no config block at all.
	var bare := {"id": "run-y", "status": "finished"}
	_check(RunRow.config_summary(bare) == "no config recorded",
		"missing config summarised")
	_check(RunRow.config_detail(bare).begins_with("No configuration"),
		"missing config detail")

	# cast == null -> "default cast"; sim_config == null -> temperature omitted.
	var defcast := {"config": {"cast": null, "brain": "mock", "sim_config": null}}
	_check(RunRow.config_summary(defcast) == "default cast · mock",
		"null cast + null sim_config: default cast, no temp")

	# temp rides only with the llm brain (#564): a mock/scripted run that recorded
	# a temperature does not advertise it -- it was inert on that run.
	var mocktemp := {"config": {
		"cast": ["a"], "brain": "mock",
		"sim_config": {"game": {"agent": {"temperature": 0.9}}},
	}}
	_check(RunRow.config_summary(mocktemp) == "1 persona(s) · mock",
		"mock-brain run omits temp even when one was recorded")

	# Thinking depth (#845): shown when a level was requested, hidden when the run
	# asked for none ("default") and on a free brain, where it was inert.
	var deep := {"config": {"cast": ["a"], "brain": "llm", "effort": "medium"}}
	_check(RunRow.config_summary(deep) == "1 persona(s) · llm · effort medium",
		"llm run advertises its thinking depth")
	var nodepth := {"config": {"cast": ["a"], "brain": "llm", "effort": "default"}}
	_check(RunRow.config_summary(nodepth) == "1 persona(s) · llm",
		"a run that requested no depth says nothing")
	var mockdepth := {"config": {"cast": ["a"], "brain": "mock", "effort": "high"}}
	_check(RunRow.config_summary(mockdepth) == "1 persona(s) · mock",
		"mock-brain run omits effort even when one was recorded")

	if _failures == 0:
		print("test_run_row: all checks passed")
	quit(1 if _failures > 0 else 0)
