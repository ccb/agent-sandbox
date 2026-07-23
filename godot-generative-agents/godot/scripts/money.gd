extends RefCounted
## Shared USD formatting for the viewer's cost readouts. One home for the "$" rule
## so the Past-runs list (run_row.gd) and the live HUD (live_hud.gd) can't drift
## apart (issue #716 review).

static func usd(x: float) -> String:
	# Four decimals below $10 (early-run costs are fractions of a cent), two above
	# (where the tail digits stop mattering).
	return ("$%.4f" if x < 10.0 else "$%.2f") % x
