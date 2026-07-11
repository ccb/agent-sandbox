# A `--cognition-tools` Flag for serve_penn (#514)

**Issue:** #514 · **Branch:** `feat/cognition-tools-flag-514` off `godot-ga-main` ·
**Review track:** godot-ga-main (touches only `godot-generative-agents/backend/penn/`
+ `godot-generative-agents/tests/`).

## Goal

PR #513 (issue #512) wired the #358 cognition tools into the Penn live decide
seam behind `CognitionConfig.cognition_tools` (default off), and
`PennStepper._build` forwards the flag into `attach_agents` — but `_build`
constructs a bare `CognitionConfig()` (`serve_penn.py:318`), defaults only.
So Penn live mode, the intended consumer, has no way to turn the flag on:
today the only enabled route is `simulate(cognition=CognitionConfig(
cognition_tools=True))`, i.e. not the live server. Add the CLI switch.

## Current state (verified)

- `PennStepper.__init__(self, num_steps=DEFAULT_STEPS, endless=False,
  world=None, monitor=None, llm=None)` calls `self._build(world)`
  (`serve_penn.py:268`); `reset()` (`serve_penn.py:484`) rebuilds via `_build`
  too, so anything `_build` reads must live on the stepper, not in `args`.
- `_build` already forwards `cognition_tools=self.cog.cognition_tools` into
  `attach_agents` (`serve_penn.py:333`) — the only missing piece is a config
  source for `self.cog`.
- `attach_agents(..., cognition_tools=True)` stamps `agent.cognition_tools`
  on every agent (`cognition.py:341-342`), which both the decide tool loop
  and the engine's converse path read. Budget: up to `1 + COGNITION_BUDGET`
  model rounds per decide (`cognition.py:579`); `COGNITION_BUDGET = 2`
  (`npc.py:384`), so ≤ 3 requests per decide tick instead of 1.
- The CLI already uses `argparse.BooleanOptionalAction` for
  `--start-paused` and `--monitor` (`serve_penn.py:548-562`) — same idiom.
- The mock brain never reaches the tool loop, so the flag is meaningful with
  `--brain llm` only; under mock it stamps the attribute and changes nothing.
- Two stale comments sit exactly where this change lands: `_build`'s mirror
  note cites `test_step_seam.py::_build_run` (no such file) and the
  `PennStepper` docstring cites `generative-agents/tests/test_penn_live.py`
  (tests moved in #399). The real pin is
  `godot-generative-agents/tests/test_penn_live.py::test_stepper_matches_simulate_prefix`.

## Design

### 1. CLI flag

`--cognition-tools` / `--no-cognition-tools`
(`argparse.BooleanOptionalAction`, `default=False`), added after `--max-cost`
(it's a brain-behavior knob, so it reads best next to the brain/cost group).
Help text carries what it buys and what it costs: under `--brain llm`, each
decide — and each conversation line — may first consult its memory / world
knowledge / day plan (`recall`, `query_knowledge`, `read_plan`, issue #358),
at up to 3 model requests per decide tick instead of 1; the `--max-cost`
kill-switch applies as usual; no effect under the mock brain.

### 2. Threading (reset-safe)

- `PennStepper.__init__` gains `cognition_tools=False`, stored as
  `self.cognition_tools` before the `_build(world)` call.
- `_build` constructs `CognitionConfig(cognition_tools=self.cognition_tools)`
  instead of `CognitionConfig()`. Everything downstream (`attach_agents`,
  the `cog=self.cog` handoff into the step loop) is already wired.
- `main()` passes `cognition_tools=args.cognition_tools` at the
  `PennStepper(...)` construction site.

`POST /reset` re-runs `_build`, which re-reads `self.cognition_tools` — the
setting survives resets by construction, with no ambient `args` read.

### 3. Startup banner

One line in `main()`'s existing brain report, printed only when the flag is
on: under `--brain llm`, that cognition tools are ON and a decide tick may
cost up to 3 requests; under mock, that the flag has no effect on the mock
brain. Keeps the operator-facing story in one place; no new API surface (the
request monitor's extra `role: decide` lines are the runtime evidence).

### 4. Stale-pointer fixes (in passing)

- `_build`'s comment: `test_step_seam.py::_build_run` →
  `tests/test_penn_live.py::test_stepper_matches_simulate_prefix`.
- `PennStepper` docstring: `generative-agents/tests/test_penn_live.py` →
  `godot-generative-agents/tests/test_penn_live.py`.

### 5. Out of scope (per the issue)

- A `cognition:` config block for serve_penn (world YAML or sim-config
  file) — `vision_r` and the conversation-pacing knobs are default-only in
  live mode today; grow a config source when a second knob needs flipping.
- Surfacing the flag in `/world_state` meta or `/health`.
- Any change to `simulate()` / `SimulationConfig` (already support this).

## Verification

- New offline test in `godot-generative-agents/tests/test_penn_live.py`
  (mock brain, no keys): `PennStepper(cognition_tools=True)` stamps
  `agent.cognition_tools is True` on every character; the default leaves it
  `False` (the engine default — `attach_agents` only stamps when on); the
  setting survives `reset()`.
- Existing suite pins the default path stays byte-identical:
  `test_stepper_matches_simulate_prefix` (mirror) + the determinism tests.
- `uv run pytest godot-generative-agents/tests/ -q` green; `uv run black .`
  clean.
- Manual (documented, not gated): `serve_penn.py --brain llm
  --cognition-tools` shows extra `role: decide` monitor lines when an agent
  retrieves before acting.
