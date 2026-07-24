extends RefCounted
## Pure backend-run-state derivation for the live follower (issue #678): map the
## `paused` + `step` a GET /live handshake (or a feed status record) carries to
## the sidebar Start/Stop state. "waiting" = armed but never ticked (a
## --start-paused boot, or a freshly-reset day -- both sit at step 0 until
## someone presses ▶ Start); "paused" = the mid-day toggle; "running" = frames
## are (or should be) flowing. No scene, no HTTP -- viewer.gd feeds it the
## payload fields and hands the result to _set_backend_run_state.
## Headless-tested (tests/test_run_state.gd).


static func from_status(paused: bool, step: int) -> String:
	if paused:
		return "waiting" if step == 0 else "paused"
	return "running"
