extends RefCounted
## Pure formatting for one GET /runs entry (issue #716), factored out of
## past_runs.gd so the row text is unit-testable headless (tests/test_run_row.gd).
## Input is one element of the /runs "runs" array (backend/run_store.py):
##   {id, status, model(nullable), created(ISO-8601), cost(float), steps(int)}

const Money := preload("res://scripts/money.gd")


static func label(entry: Dictionary) -> String:
	# "run-2-live · running · claude-haiku · 2026-07-22 12:34 · $0.0123 · 42 steps"
	var id := String(entry.get("id", "?"))
	var status := String(entry.get("status", "?"))
	# Mock-brain runs persist model == null; show "mock" so the row never reads "<null>".
	var model := String(entry.get("model")) if entry.get("model") != null else "mock"
	var created := _short_time(String(entry.get("created", "")))
	var cost := Money.usd(float(entry.get("cost", 0.0)))
	var steps := int(entry.get("steps", 0))
	return "%s · %s · %s · %s · %s · %d steps" % [id, status, model, created, cost, steps]


static func _short_time(iso: String) -> String:
	# "2026-07-22T12:34:56+00:00" -> "2026-07-22 12:34". Anything that doesn't look
	# like an ISO timestamp passes through so a future backend format still shows
	# something rather than an empty or mangled cell.
	if iso.length() < 16 or not iso.contains("T"):
		return iso
	return iso.substr(0, 10) + " " + iso.substr(11, 5)


# A one-line summary of a run's applied config (#734), for the Past-runs row:
# "3 persona(s) · llm · temp 0.7". A run no one configured (config == null)
# reads "no config recorded"; fields absent from an older block are skipped.
static func config_summary(entry: Dictionary) -> String:
	var config: Variant = entry.get("config")
	if typeof(config) != TYPE_DICTIONARY:
		return "no config recorded"
	var cfg := config as Dictionary
	var parts := PackedStringArray()
	var cast: Variant = cfg.get("cast")
	if typeof(cast) == TYPE_ARRAY:
		parts.append("%d persona(s)" % (cast as Array).size())
	else:
		parts.append("default cast")
	parts.append(str(cfg.get("brain", "?")))
	# Temperature is honored only by the llm brain (#564); for a mock/scripted run
	# it was inert, so don't imply it shaped that run (#734 review follow-up).
	var temp: Variant = _config_temperature(cfg)
	if temp != null and str(cfg.get("brain", "")) == "llm":
		parts.append("temp %s" % str(temp))
	# Thinking depth (#845), like temperature a paid-brain-only setting: show it
	# only when a level was actually requested ("default" means none was, and a
	# block saved before #845 records nothing at all).
	var effort := str(cfg.get("effort", "default"))
	if effort != "default" and str(cfg.get("brain", "")) == "llm":
		parts.append("effort %s" % effort)
	return " · ".join(parts)


# The full applied-config block as pretty JSON (#734), for the row's expandable
# detail view. A run with no block says so.
static func config_detail(entry: Dictionary) -> String:
	var config: Variant = entry.get("config")
	if typeof(config) != TYPE_DICTIONARY:
		return "No configuration was recorded for this run."
	return JSON.stringify(config, "  ")


# The live sampling temperature buried at sim_config.game.agent.temperature
# (#564), or null if this block recorded none.
static func _config_temperature(config: Dictionary) -> Variant:
	var cur: Variant = config.get("sim_config")
	for key in ["game", "agent", "temperature"]:
		if typeof(cur) != TYPE_DICTIONARY or not (cur as Dictionary).has(key):
			return null
		cur = (cur as Dictionary)[key]
	return cur
