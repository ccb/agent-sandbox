# tests/ — TOOLS (not auto-run tests)

N1 (sprint safety): **every** `tests/*.gd` file must be registered somewhere —
`run_tests.gd` enforces this (`_test_harness_registry`, RED on any unlisted file):

- **In-suite runners** — `load("res://tests/<file>")`-folded into `run_tests.gd`
  (the `run_all()` pattern; e.g. `test_run_pace.gd`, `hermit_full_run.gd`,
  `run_combat_vectors.gd`).
- **Standalone fleet** — `STANDALONE_HARNESSES` in `run_tests.gd`: SceneTree
  harnesses executed as child Godot processes by `_test_standalone_fleet()`,
  their pass/fail counts folded into the suite totals.
- **Tools** — `TOOL_SCRIPTS` in `run_tests.gd` + this file: on-demand probes and
  generators with no headless pass/fail contract. Intentionally NOT auto-run
  (they need a window, a human's eyes/ears, or real LLM API money).

Every harness and probe activates `src/TestSandbox.gd` first, so none of them can
touch the real user profile (`~/Library/Application Support/Godot/app_userdata/Tingen`).
The repeatable full-fleet proof is `tests/isolation_proof.sh` (hash the real user
dir → run everything → re-hash → assert byte-identical).

## The tools

| File | What it is | How to run | Output |
|---|---|---|---|
| `audio_probe.gd` | Audio-bus smoke probe — proves REAL sound reaches the bus on live boot. Audible; refuses `--headless`. | `$GODOT --path tingen --resolution 1280x720 -s tests/audio_probe.gd` | PASS/FAIL prints + audible output |
| `continue_probe.sh` | N3 TWO-PROCESS Continue proof: session 1 plays/checkpoints/quits, session 2 is a FRESH Godot process that presses the REAL title Continue and asserts a first-class resume (B-F1/B-F2/B-F5). | `bash tingen/tests/continue_probe.sh` | PASS/FAIL prints + exit code |
| `continue_probe_s1.gd` | Continue proof session 1 — New Run, learn a codex fact, rest to day 2 (nightly disk save to the fixed `user://test_sandbox/continue_probe/` slots), quit mid-run. | `$GODOT --headless --path tingen -s tests/continue_probe_s1.gd` | PASS/FAIL prints + shared save |
| `continue_probe_s2.gd` | Continue proof session 2 — fresh process, REAL BootController Continue, asserts run_active/day/pause/codex/checkpoints/Ritual-Night arming/save staleness. Run after s1. | `$GODOT --headless --path tingen -s tests/continue_probe_s2.gd` | PASS/FAIL prints + exit code |
| `dump_combat_vectors.gd` | Expected-value GENERATOR for `combat_test_vectors.json` (spec governance: change algorithm → regenerate → never hand-edit expecteds). | `$GODOT --headless --path tingen -s tests/dump_combat_vectors.gd` | `<vectors>.filled` beside the source |
| `live_butcher.gd` | LIVE-LLM acceptance run of the §0 Butcher script (real Sonnet decides intents). Costs ~$1–2. | `TINGEN_SIDECAR_URL=http://127.0.0.1:8777 $GODOT --headless --path tingen -s tests/live_butcher.gd` | PASS/FAIL prints + exit code |
| `live_combat.gd` | LIVE-LLM combat validation (M4 checklist) incl. mid-fight sidecar kill/fallback. Costs ~$1. | `TINGEN_SIDECAR_URL=http://127.0.0.1:8777 $GODOT --headless --path tingen -s tests/live_combat.gd` | PASS/FAIL prints + exit code |
| `live_sim.gd` | LIVE-LLM summoning sim — drives N beats against the real sidecar to judge decision diversity. Costs ~15–25 /decide calls. | `TINGEN_SIDECAR_URL=http://127.0.0.1:8777 $GODOT --headless --path tingen -s tests/live_sim.gd` | per-beat action prints |
| `probe_thinking_tell.gd` | P3 thinking-tell capture — a REAL bounded /decide against a hung responder puts the inspect card's "( thinking… )" tell up, then the timeout restores the live thought. Windowed; no LLM cost. | `$GODOT --path tingen -s tests/probe_thinking_tell.gd [-- outdir=/abs/path]` | `thinking_01_in_flight.png` + `thinking_02_restored.png` |
| `screenshot_probe.gd` | Rendered-frame capture (title → New Run → move → bed prompt → combat beats) for human eyeballing. Windowed. | `$GODOT --path tingen -s tests/screenshot_probe.gd [-- outdir=/abs/path]` | numbered PNGs (default `user://probe_shots`) |
| `vfx_shot.gd` | Combat-FX visual proof — stages a projectile/zone/spark-burst slice and saves a screenshot. | `$GODOT --headless --path tingen -s tests/vfx_shot.gd` | screenshot artifact |

## Standalone gates (also run directly, every change)

`combat_sim.gd` and `full_run.gd` are folded into the suite's standalone fleet
AND remain the sprint's standalone gate commands (byte-identical sims / full-run
integration), alongside `run_tests.gd`, `run_combat_vectors.gd`,
`hermit_full_run.gd` and the boot gate — see `CLAUDE.md` and
`docs/handoff/HANDOFF.md`.
