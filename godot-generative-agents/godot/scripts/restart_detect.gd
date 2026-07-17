extends RefCounted
## Pure restart-detection for the live follower (issue #578): given the last
## boot nonce we saw, the fresh GET /live handshake's nonce and cursor, and the
## newest cursor we've applied, decide whether the backend is a NEW process and
## the follower must rejoin from scratch (drop the dead run's cast, re-anchor).
## No scene, no HTTP -- viewer.gd feeds it handshake values and acts on the bool.
## Headless-tested (tests/test_restart_detect.gd).


static func should_rejoin(
	prev_boot: String, hs_boot: String, last_cursor: int, hs_cursor: int
) -> bool:
	# A changed per-process boot nonce is the reliable signal: a new process,
	# even if its feed already climbed past our cursor (which the cursor check
	# below cannot see). Empty hs_boot (older server omitting boot_id) or empty
	# prev_boot (our first handshake) falls through to the cursor-rewind
	# heuristic (#549): a handshake cursor below the newest we've applied.
	if hs_boot != "" and prev_boot != "" and hs_boot != prev_boot:
		return true
	return last_cursor > hs_cursor
