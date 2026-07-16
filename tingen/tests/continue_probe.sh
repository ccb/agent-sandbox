#!/bin/bash
# N3 — the TWO-PROCESS Continue proof (a TOOL; see tests/TOOLS.md). Cross-session Continue can
# only be honestly proven across a REAL process boundary: session 1 (continue_probe_s1.gd) starts
# a run, learns a codex fact, rests to day 2 (nightly checkpoint -> disk save) and QUITS; session
# 2 (continue_probe_s2.gd) is a FRESH Godot process that boots the real title, presses the REAL
# Continue, and asserts the resumed run is a first-class live run (run_active / day / pause /
# codex / checkpoints / Ritual Night arming / save staleness on run end — B-F1/B-F2/B-F5).
#
# Both sessions share fixed save/meta slots under user://test_sandbox/continue_probe/ (inside the
# TestSandbox root, so the real profile stays untouched; isolation_proof.sh excludes it).
#
# Usage:  bash tingen/tests/continue_probe.sh          (from the repo root; GODOT env overrides)
# Exit 0 = both sessions green.  Exit 1 = any FAIL in either session.

set -u
GODOT="${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}"
PROJ="$(cd "$(dirname "$0")/.." && pwd)"

echo "== SESSION 1: play, checkpoint, quit"
"$GODOT" --headless --path "$PROJ" -s tests/continue_probe_s1.gd
S1=$?

echo "== SESSION 2: fresh process, REAL Continue, resume asserts"
"$GODOT" --headless --path "$PROJ" -s tests/continue_probe_s2.gd
S2=$?

echo "== continue_probe: s1 exit=$S1  s2 exit=$S2"
if [ "$S1" -eq 0 ] && [ "$S2" -eq 0 ]; then
	echo "== CONTINUE PROBE: PASS — cross-session Continue is a first-class resume"
	exit 0
else
	echo "== CONTINUE PROBE: FAIL"
	exit 1
fi
