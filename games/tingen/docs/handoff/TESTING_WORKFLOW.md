# TESTING WORKFLOW — the verification pyramid

Every layer exists and is wired; baselines below are as of commit `cc4e2e2`. Run layers 0–2 on
every change; 3 on anything touching the LLM seam; 4 before telling the user something "looks
right" or "plays well".

## 0. Static suites (free, ~2 min, run ALWAYS)

```
GODOT=/Applications/Godot.app/Contents/MacOS/Godot
cd <repo>/tingen
$GODOT --headless --path . --import                    # only after adding/changing assets
$GODOT --headless --path . -s tests/run_tests.gd      # baseline: 1861 passed, 0 failed
cd ../agent-sidecar
python3 cognition/test_brain.py                        # 75/0
python3 cognition/run_vectors.py                       # 26/0 (cognition parity vectors)
python3 test_narrate_route.py                          # 13/0
python3 test_converse_route.py                         # 8/0
```
Notes: `run_tests.gd` is a single SceneTree script, ~4400 lines, `_ok()` asserts, exits nonzero
on failure. Tests are registered in the call list at the top (~line 100-140). Use Edit-tool
string edits only — multiple workstreams share this file. `pytest` does NOT discover these Python
suites (custom runners) — run them as scripts.

## 1. Deterministic combat sim (free, ~30s)

```
$GODOT --headless --path tingen -s tests/combat_sim.gd    # 33 asserts, 0 failed
```
Scenarios: A dodger (projectile/telegraph/reflex), B dummy (zones/statuses/poise), C butcher-vs-
brawler (tactical bands + styles), D the full §0 Kell acceptance script offline — INCLUDING a
byte-identical determinism re-run. `const DT = 1.0/60.0` — **step_combat takes SECONDS**; passing
ms tunnels projectiles (cost an hour tonight). Scenario D is the reference transcript for "did
combat behavior change?" — any diff in its event signature is a behavioral change you must
explain in the commit message.

## 2. Language-neutral spec vectors (free, ~20s, Yumina parity gate)

```
$GODOT --headless --path tingen -s tests/run_combat_vectors.gd   # 95/0
```
Fixtures: `agent-sidecar/cognition/combat_test_vectors.json`; contract:
`agent-sidecar/cognition/COMBAT_SPEC.md`. GOVERNANCE: never hand-edit expected values — change
the algorithm, then regenerate via `tests/dump_combat_vectors.gd` (fills through the SAME fill_*
statics the verifier compares), then BOTH the GDScript runner and (later) Yumina's vitest runner
must pass. The cognition layer has the same pattern one level up (`SPEC.md` +
`test_vectors.json` + `run_vectors.py`).

## 3. Live-LLM gates (~$1–2 each, real Sonnet through the local sidecar)

Boot the sidecar first (HANDOFF.md). Three harnesses, all SceneTree scripts with PASS/FAIL
prints + exit codes:

```
TINGEN_SIDECAR_URL=http://127.0.0.1:8777 $GODOT --headless --path tingen -s tests/live_sim.gd      # world beats
TINGEN_SIDECAR_URL=http://127.0.0.1:8777 $GODOT --headless --path tingen -s tests/live_combat.gd   # M4 combat-intent gate
TINGEN_SIDECAR_URL=http://127.0.0.1:8777 $GODOT --headless --path tingen -s tests/live_butcher.gd  # full §0 acceptance (11 checks)
```

What they prove that layers 0–2 cannot: prompt content actually rendered (probe the `_prompt`
field of /decide responses — `TINGEN_DECIDE_LOG=1` prints decision traces only, never prompts);
verb legality of REAL model output; latency/backpressure behavior (consume-once cache);
mid-fight sidecar death → ambient fallback. Gotchas: GDScript lambdas capture primitives BY
VALUE — use a Dictionary for captured counters (bit us twice); `OS.delay_msec` between beats is
load-bearing (HTTP worker needs wall time); a failed assert must `quit(1)`, never hang.

## 4. Interactive playtest — computer use + screenshots (the "does it FEEL right" gate)

No harness can check readability, game feel, or visual correctness. Protocol (requires the
desktop; ask the user for screen access via request_access first):

**Launch** (from a shell, NOT inside the editor — deterministic env):
```
TINGEN_SIDECAR_URL=http://127.0.0.1:8777 $GODOT --path <repo>/tingen &
```
The game window is a normal app (computer-use tier "full" — clicks AND keys work; note terminals/
IDEs are click-only, so drive the GAME window, not the editor).

**Scripted pass** (screenshot at every ★; compare against the checklist):
1. ★ Boot: city at 08:00 morning, day tint, HUD bottom (hp/stamina bars, rounds counter = 12,
   two cooldown pips), no telegraph line. NPCs visibly dispersing to schedules.
2. Walk (WASD) one screen in each direction. ★ Buildings: no floating sprites, no sliced
   rooflines (the fill blocks!), no walking THROUGH buildings (colliders), NPCs route around.
3. Open each panel, ★ each: Tab board (clue cards), M map, C cult progress (materials 0/3
   early), R rituals, P prayer, I inventory (revolver + 12 rounds — item-backed since cc4e2e2),
   G GM digest (an entry within 30s; with live sidecar a narration paragraph appends), ` console.
4. Time-skip to night: use the dev console (`) — check DevConsole.gd for the time/clock command
   (or wait through phases if the demo clock is fast). ★ Night tint; lamplighter behavior.
5. The Butcher: find bram_kell (butcher shop by day; canal round ~world (4230,2050) late-night).
   ★ Suspicious-clue toast near his deed site at night.
6. Fight: Space/LMB shot (★ telegraph appears ON HIM for bystanders? no — on YOUR HUD only when
   HE winds up), Shift dash through his cleaver (★ i-frames — no damage), Q charm zone (★ slow).
   At ~half hp ★ "Bram Kell winds up shed the skin!" then ★ monster sprite. Down him:
   ★ body stays, ★ board gains bram_kell_revealed, ★ G panel narrates, C panel unaffected.
7. ★ Ammo drain: rounds hit 0 → shots refuse (no crash, HUD 0); pick-up/reload flow does NOT
   exist yet (designed follow-up — DESIGN_ammo_items_followups.md).
8. Portals: enter/exit every interior (butcher shop, tavern, police, almshouse, warehouse,
   Franky's, Klein living-room→bedroom, cathedral→crypt, HQ, Neil's, archive). ★ each: correct
   scene, correct scale feel (warehouse ≈3× Klein rooms), a working door BACK.
9. EndGame: console-force the summoning climax (or sabotage/allow the cult). ★ overlay, ★ Restart
   actually resets (inventory back to loadout, clues cleared, clock 08:00 Day 1).

**Screenshot discipline**: save to the session scratchpad, name by step (`playtest_03_board.png`),
and READ each one before claiming it passed — a screenshot you didn't look at is not evidence.
File visual bugs with the screenshot path + world position.

**Doc-parity check** (same pass, no game needed): for each doc claim that names a key, file, or
number, grep the code for it. Canonical pairs to keep honest: COMBAT_SPEC constants vs
`CombatResolver/TacticalBrain/ReflexRules` (the vectors do this for you); GDD §14 phases vs
`Clock.PHASE_BOUNDS`; panel keybinds in any doc vs `project.godot [input]`; HANDOFF suite
baselines vs an actual run. Fix the DOC unless the code is wrong.

## 5. Review-re-edit framework (per milestone — mandatory)

For every milestone-sized change: (1) TDD build (failing asserts watched red first);
(2) layers 0–2; (3) a FRESH-CONTEXT adversarial review agent over the actual diff with an
explicit hunt list (see WORKFLOWS.md §2 for the 3-stage template — build/review/fix);
(4) fix criticals + regression asserts; (5) live gate if the LLM seam moved; (6) checkpoint
commit; (7) RUNLOG.md entry (timestamped `## hh:xx — TITLE`, what/why/suite line/spend).
Tonight's combat arc (M0–M9) shipped through this loop with 6 review rounds; the final
whole-arc review verdict and its 9 findings are all in RUNLOG. It works. Keep it.
