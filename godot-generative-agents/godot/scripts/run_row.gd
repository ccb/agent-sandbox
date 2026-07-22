extends RefCounted
## Pure formatting for one GET /runs entry (issue #716), factored out of
## past_runs.gd so the row text is unit-testable headless (tests/test_run_row.gd).
## Input is one element of the /runs "runs" array (backend/run_store.py):
##   {id, status, model(nullable), created(ISO-8601), cost(float), steps(int)}

static func label(entry: Dictionary) -> String:
	# "run-2-live · running · claude-haiku · 2026-07-22 12:34 · $0.0123 · 42 steps"
	var id := String(entry.get("id", "?"))
	var status := String(entry.get("status", "?"))
	# Mock-brain runs persist model == null; show "mock" so the row never reads "<null>".
	var model := String(entry.get("model")) if entry.get("model") != null else "mock"
	var created := _short_time(String(entry.get("created", "")))
	var cost := _fmt_usd(float(entry.get("cost", 0.0)))
	var steps := int(entry.get("steps", 0))
	return "%s · %s · %s · %s · %s · %d steps" % [id, status, model, created, cost, steps]


static func _short_time(iso: String) -> String:
	# "2026-07-22T12:34:56+00:00" -> "2026-07-22 12:34". Anything that doesn't look
	# like an ISO timestamp passes through so a future backend format still shows
	# something rather than an empty or mangled cell.
	if iso.length() < 16 or not iso.contains("T"):
		return iso
	return iso.substr(0, 10) + " " + iso.substr(11, 5)


static func _fmt_usd(x: float) -> String:
	# Four decimals below $10 (early-run costs are fractions of a cent), two above.
	return ("$%.4f" if x < 10.0 else "$%.2f") % x
