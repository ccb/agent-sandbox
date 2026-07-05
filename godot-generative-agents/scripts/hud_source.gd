extends Node
## Base class for the run-monitor HUD's data feed (issue #264).
##
## The HUD (live_hud.gd) is pure UI: it renders whatever a *source* reports and
## never talks to a backend itself. This base class pins the contract the two
## sources share, so penn_replay.gd can wire either one to the HUD without
## caring which it got:
##
## * hud_source_replay.gd -- baked-replay mode (the default today): no backend
##   exists, so it SYNTHESIZES plausible usage numbers while playback runs, and
##   the Stop button just freezes the replay. Clearly labeled "simulated".
## * hud_source_live.gd -- live mode: polls the real backend's `GET /usage` +
##   `GET /health` (issue #262) and drives `POST /pause` from the Stop button.
##
## Both emit `usage_updated` with the SAME dict shape: the engine's
## `UsageLedger.summary()` (text_adventure_games/usage.py), which is exactly
## what the backend's `GET /usage` route serves. That shared shape is what makes
## the switch to a real LLM seamless -- the HUD can't tell mock from live:
##
##     {"calls": N, "total_cost_usd": X, "by_actor": {...},
##      "input_tokens": N, "output_tokens": N,
##      "cache_creation_input_tokens": N, "cache_read_input_tokens": N,
##      # optional budget fields (the ledger's #183 kill-switch state):
##      "max_cost_usd": X, "over_budget": false}

## A fresh cumulative usage summary (see the shape above). Cumulative like the
## real ledger -- totals only ever grow, they never rewind on a replay seek.
signal usage_updated(summary: Dictionary)
## The backend's (or the simulation's) health changed: a Health value + a short
## human line for the HUD's status row ("turn 42", "backend unreachable", ...).
signal health_changed(state: int, detail: String)
## The run was halted (emergency stop confirmed) or resumed.
signal halted_changed(halted: bool)

## SIMULATED = baked-replay mode, numbers are synthetic; OK/DEGRADED/DOWN are
## the live-backend liveness ladder (healthy / missed a check / unreachable).
enum Health { SIMULATED, OK, DEGRADED, DOWN }


func set_cast(_names: Array) -> void:
	## The persona names, once the replay (or world) is loaded -- so a source can
	## attribute per-actor spend. The live source ignores this (the backend's
	## ledger already knows its actors).
	pass


func set_running(_running: bool) -> void:
	## Whether the run is advancing (playing, not paused/halted/ended). The
	## replay source accrues simulated spend only while true; the live source
	## ignores it (a real backend spends on its own clock, not the viewer's).
	pass


func request_stop() -> void:
	## The HUD's Emergency Stop. Replay: freeze playback + trip the mock budget
	## gate. Live: POST /pause (and #183's kill-switch once #262 exposes it).
	pass


func request_resume() -> void:
	## Lift a previous stop (the viewer calls this when Play is pressed while
	## halted). Replay: un-trip and resume accrual. Live: POST /resume.
	pass
