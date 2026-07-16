#!/bin/bash
# N1 SPRINT SAFETY — user-profile ISOLATION PROOF (repeatable; rerun any time).
#
# Proves the ENTIRE harness fleet (the registered suite + every standalone harness) leaves the
# developer's REAL Godot user dir (~/Library/Application Support/Godot/app_userdata/Tingen)
# BYTE-IDENTICAL: snapshot sha256 of every real profile file, run everything, re-hash, diff.
#
# Excluded from the hash set (not player-profile state):
#   test_sandbox/   — the harness sandbox itself (tests write ONLY here; wiped per proof run)
#   logs/           — Godot's own rotating engine logs (written by the ENGINE every headless boot,
#                     player-meaningless; the game never reads or writes them)
#   shader_cache/ vulkan/ objectdb_snapshots/ — engine caches, same reasoning
#
# Usage:  bash tingen/tests/isolation_proof.sh            (from the repo root)
# Exit 0 = byte-identical (isolation holds).  Exit 1 = the real profile was touched (VIOLATION).

set -u
GODOT="${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PROJ="$REPO/tingen"
USER_DIR="$HOME/Library/Application Support/Godot/app_userdata/Tingen"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

hash_profile() {
	(cd "$USER_DIR" && find . -type f \
		! -path "./test_sandbox/*" \
		! -path "./logs/*" \
		! -path "./shader_cache/*" \
		! -path "./vulkan/*" \
		! -path "./objectdb_snapshots/*" \
		-print0 | sort -z | xargs -0 shasum -a 256 2>/dev/null)
}

run() { # run <label> <args...> — run one harness, record exit code, never abort the proof
	local label="$1"; shift
	echo "--- $label"
	"$GODOT" --headless --path "$PROJ" "$@" >"$TMP/$label.log" 2>&1
	local code=$?
	echo "$label exit=$code" >>"$TMP/exits.txt"
	grep -hE "passed, .*failed|asserts passed" "$TMP/$label.log" | tail -1
}

mkdir -p "$USER_DIR"
rm -rf "$USER_DIR/test_sandbox"          # start from a clean sandbox so leftovers never mask writes
echo "== BEFORE: hashing real user profile ($USER_DIR)"
hash_profile > "$TMP/before.txt"
wc -l < "$TMP/before.txt" | xargs echo "   files hashed:"

# --- the full harness fleet ----------------------------------------------------------------------
run run_tests            -s tests/run_tests.gd
run combat_sim           -s tests/combat_sim.gd
run run_combat_vectors   -s tests/run_combat_vectors.gd
run full_run             -s tests/full_run.gd
run hermit_full_run      -s tests/hermit_full_run.gd
run death_full_run       -s tests/death_full_run.gd
run test_death_live      -s tests/test_death_live.gd
run test_death_pathway   -s tests/test_death_pathway.gd
run test_death_primary   -s tests/test_death_primary.gd
run test_death_save_load -s tests/test_death_save_load.gd
run test_continue_resume -s tests/test_continue_resume.gd
run continue_probe_s1    -s tests/continue_probe_s1.gd
run continue_probe_s2    -s tests/continue_probe_s2.gd
run boot_smoke           -s tests/boot_smoke.gd
run test_adversary2      -s tests/test_adversary2.gd
run test_adversary3      -s tests/test_adversary3.gd
run test_affordances     -s tests/test_affordances.gd
run test_deciding_fact   -s tests/test_deciding_fact.gd
run test_hud_persistence -s tests/test_hud_persistence.gd
run test_interiors       -s tests/test_interiors.gd
run test_intro_room      -s tests/test_intro_room.gd
run test_leads           -s tests/test_leads.gd
run test_live_bugs       -s tests/test_live_bugs.gd
run test_mem_importance  -s tests/test_mem_importance.gd
run test_meta_isolation  -s tests/test_meta_isolation.gd
run test_meta_payoff     -s tests/test_meta_payoff.gd
run test_meter_teeth     -s tests/test_meter_teeth.gd
run test_meters          -s tests/test_meters.gd
run test_neil_home       -s tests/test_neil_home.gd
run test_nighthawks_hq   -s tests/test_nighthawks_hq.gd
run test_npc_cost_loot   -s tests/test_npc_cost_loot.gd
run test_opening         -s tests/test_opening.gd
run test_polish          -s tests/test_polish.gd
run test_portrait_ui     -s tests/test_portrait_ui.gd
run test_progression     -s tests/test_progression.gd
run test_reload          -s tests/test_reload.gd
run test_ritual_night    -s tests/test_ritual_night.gd
run test_run_shell       -s tests/test_run_shell.gd
run test_scene_fade      -s tests/test_scene_fade.gd
run test_shop            -s tests/test_shop.gd
run test_stuck_guard     -s tests/test_stuck_guard.gd
run test_transition_anywhere -s tests/test_transition_anywhere.gd
run test_university_archive  -s tests/test_university_archive.gd
run test_visual_foundation   -s tests/test_visual_foundation.gd

echo "== AFTER: re-hashing real user profile"
hash_profile > "$TMP/after.txt"

echo "== harness exit codes"
cat "$TMP/exits.txt"

if diff -u "$TMP/before.txt" "$TMP/after.txt" > "$TMP/profile.diff"; then
	echo "== ISOLATION PROOF: PASS — real user profile is BYTE-IDENTICAL after the full fleet"
	exit 0
else
	echo "== ISOLATION PROOF: FAIL — the real user profile WAS TOUCHED:"
	cat "$TMP/profile.diff"
	exit 1
fi
