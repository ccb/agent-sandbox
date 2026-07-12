# serve_penn `--cognition-tools` Flag (#514) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Penn live mode a CLI switch (`--cognition-tools`) that turns on the #513 cognition-tools wiring (`CognitionConfig.cognition_tools`), reset-safe, defaults off.

**Architecture:** `PennStepper` gains a `cognition_tools` constructor kwarg held on the stepper; `_build` constructs `CognitionConfig(cognition_tools=self.cognition_tools)` instead of a bare `CognitionConfig()`, so `POST /reset` (which re-runs `_build`) keeps the setting. `main()` sources the value from a new `argparse.BooleanOptionalAction` flag and prints one banner line when it's on. Everything downstream (`attach_agents`, the step loop's `cog=self.cog`) is already wired by #513.

**Tech Stack:** Python 3.12 (uv), argparse, pytest. No new dependencies.

**Spec:** `godot-generative-agents/docs/specs/2026-07-11-cognition-tools-flag.md`

## Global Constraints

- Branch: `feat/cognition-tools-flag-514` (off `godot-ga-main`; review track godot-ga-main — touch ONLY `godot-generative-agents/backend/penn/serve_penn.py` and `godot-generative-agents/tests/test_penn_live.py`).
- NEVER `git add -A` or `git add .` — the checkout carries unrelated uncommitted files. Add exact paths only.
- Every commit message ends with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Tests are fully offline (mock brain, no API keys, no network).
- The default (no flag) path must stay byte-identical to today — `test_stepper_matches_simulate_prefix` and the determinism tests pin this; do not touch them.
- This file's comment/docstring style writes double-hyphen `--` (not an em dash); match it.
- Run commands from the repo root: `/Users/yh/Documents/GitHub/agent-sandbox`.

---

### Task 1: Thread `cognition_tools` through `PennStepper` (reset-safe)

**Files:**
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (`__init__` at ~line 268, `_build` at ~line 313, class docstring at ~line 256)
- Test: `godot-generative-agents/tests/test_penn_live.py` (insert after `test_stepper_finishes_then_resets`, ~line 226)

**Interfaces:**
- Consumes: `CognitionConfig(cognition_tools: bool = False)` (`backend/sim_config.py:89`); `attach_agents(..., cognition_tools=...)` already receives `self.cog.cognition_tools` (`serve_penn.py:333` — do not change that line).
- Produces: `PennStepper(num_steps=..., endless=..., world=..., monitor=..., llm=..., cognition_tools=False)` — the new keyword Task 2's `main()` passes. `stepper.cognition_tools: bool` attribute readable after construction.

- [ ] **Step 1: Write the failing test**

In `godot-generative-agents/tests/test_penn_live.py`, directly after `test_stepper_finishes_then_resets` (it ends `assert stepper.tick() == first_day[0]  # a fresh day replays deterministically`, ~line 226) and before the `# ---- LiveMeetingInjector` section comment, insert:

```python
def test_stepper_threads_cognition_tools():
    # The #514 plumbing: the flag rides the stepper into attach_agents, which
    # stamps the engine attribute the decide tool loop and the converse path
    # read. _build() re-reads it from the stepper, so POST /reset keeps it.
    stepper = PennStepper(num_steps=3, world=build_penn_world(), cognition_tools=True)
    assert stepper.chars  # guard: the all() below actually checked someone
    assert all(c.agent.cognition_tools is True for c in stepper.chars.values())
    stepper.reset()
    assert all(c.agent.cognition_tools is True for c in stepper.chars.values())


def test_stepper_default_leaves_cognition_tools_off():
    # No flag: agents keep the engine default (attach_agents only stamps when
    # on), so the default live server stays byte-identical to today.
    stepper = PennStepper(num_steps=3, world=build_penn_world())
    assert stepper.chars
    assert all(c.agent.cognition_tools is False for c in stepper.chars.values())
```

(`PennStepper` and `build_penn_world` are already imported at the top of this test file. `stepper.chars` maps persona name -> Character — persona cast only, every one holding an `.agent` set by `attach_agents`.)

- [ ] **Step 2: Run the tests to verify the new one fails**

Run:
```bash
uv run pytest "godot-generative-agents/tests/test_penn_live.py::test_stepper_threads_cognition_tools" "godot-generative-agents/tests/test_penn_live.py::test_stepper_default_leaves_cognition_tools_off" -v
```
Expected: `test_stepper_threads_cognition_tools` FAILS with `TypeError: PennStepper.__init__() got an unexpected keyword argument 'cognition_tools'`. `test_stepper_default_leaves_cognition_tools_off` PASSES already (it pins existing behavior — that's fine).

- [ ] **Step 3: Implement the threading (three edits in `serve_penn.py`)**

Edit (a) — the `__init__` signature and a stored attribute. Replace:

```python
    def __init__(
        self, num_steps=DEFAULT_STEPS, endless=False, world=None, monitor=None, llm=None
    ):
        self.num_steps = num_steps
        self.endless = endless
```

with:

```python
    def __init__(
        self,
        num_steps=DEFAULT_STEPS,
        endless=False,
        world=None,
        monitor=None,
        llm=None,
        cognition_tools=False,
    ):
        self.num_steps = num_steps
        self.endless = endless
        # The #514 switch for the #512 wiring: agentic recall/query_knowledge/
        # read_plan before each decide. Held on the stepper -- not read from
        # argv -- so _build() re-applies it on every reset (POST /reset).
        self.cognition_tools = cognition_tools
```

Edit (b) — `_build` reads the stored flag (and its mirror-note comment stops citing a file that doesn't exist; the real pin is `test_penn_live.py::test_stepper_matches_simulate_prefix`). Replace:

```python
        # Mirror simulate()'s pre-loop setup exactly (run_simulation.py; the
        # same reconstruction test_step_seam.py::_build_run pins). If simulate's
        # setup ever drifts from this, the equivalence test fails -- on purpose.
        self.world = world if world is not None else build_penn_world()
        self.cog = CognitionConfig()
```

with:

```python
        # Mirror simulate()'s pre-loop setup exactly (run_simulation.py; the
        # same reconstruction tests/test_penn_live.py::
        # test_stepper_matches_simulate_prefix pins). If simulate's setup ever
        # drifts from this, the equivalence test fails -- on purpose.
        self.world = world if world is not None else build_penn_world()
        self.cog = CognitionConfig(cognition_tools=self.cognition_tools)
```

Edit (c) — the class docstring's stale test path (tests moved out of `generative-agents/` in #399). Replace:

```python
    produce exactly the frames ``simulate(world_map, N)`` would
    (``generative-agents/tests/test_penn_live.py`` pins that equivalence).
```

with:

```python
    produce exactly the frames ``simulate(world_map, N)`` would
    (``godot-generative-agents/tests/test_penn_live.py`` pins that equivalence).
```

- [ ] **Step 4: Run the full live-Penn test file to verify everything passes**

Run:
```bash
uv run pytest godot-generative-agents/tests/test_penn_live.py -q
```
Expected: all tests PASS — including `test_stepper_matches_simulate_prefix` (the byte-identical default path) and both new tests.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_penn_live.py
git commit -m "feat(backend): thread cognition_tools through PennStepper, reset-safe (#514)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: The `--cognition-tools` CLI flag + startup banner

**Files:**
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (`main()`: the argparse block at ~line 541, the `PennStepper(...)` construction at ~line 591, the brain banner at ~line 607)

**Interfaces:**
- Consumes: `PennStepper(..., cognition_tools=False)` from Task 1; `argparse` is already imported (line 42); `--start-paused`/`--monitor` already use `argparse.BooleanOptionalAction` (same idiom).
- Produces: the user-facing `--cognition-tools` / `--no-cognition-tools` CLI flag, default off.

- [ ] **Step 1: Add the flag to the parser**

In `main()`, directly after the `--max-cost` `ap.add_argument(...)` block (it ends `"(--brain llm only); the day ends when cumulative spend reaches it",` `)`) insert:

```python
    ap.add_argument(
        "--cognition-tools",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="let each decide -- and each conversation line -- consult the "
        "agent's memory / world knowledge / day plan first (recall, "
        "query_knowledge, read_plan; issues #358/#512): up to 3 model "
        "requests per decide tick instead of 1, metered by --max-cost as "
        "usual. --brain llm only; the mock brain never reaches the tool loop",
    )
```

- [ ] **Step 2: Pass it into the stepper**

In the `stepper = PennStepper(...)` construction inside `main()`'s `try:`, replace:

```python
        stepper = PennStepper(
            num_steps=args.steps,
            endless=args.endless,
            world=world,
            monitor=LlmCallMonitor() if args.monitor else None,
            llm=llm,
        )
```

with:

```python
        stepper = PennStepper(
            num_steps=args.steps,
            endless=args.endless,
            world=world,
            monitor=LlmCallMonitor() if args.monitor else None,
            llm=llm,
            cognition_tools=args.cognition_tools,
        )
```

- [ ] **Step 3: Banner line when the flag is on**

Directly after the brain report's `if llm is not None: ... else: ...` block (the `else` branch ends `"For the real thing: --brain llm."` `)`) insert, at the same indentation as that `if`:

```python
    if args.cognition_tools:
        print(
            "Cognition tools: ON -- a decide tick may spend up to 3 model "
            "requests (recall/query_knowledge/read_plan before acting)."
            if llm is not None
            else "Cognition tools: ON, but the mock brain never reaches the "
            "tool loop -- pair it with --brain llm for any effect."
        )
```

- [ ] **Step 4: Verify the CLI surface and the suite**

Run:
```bash
uv run python godot-generative-agents/backend/penn/serve_penn.py --help
```
Expected: exits 0; the options list shows `--cognition-tools, --no-cognition-tools` with the help text above.

Run:
```bash
uv run pytest godot-generative-agents/tests/ -q
uv run black --check godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_penn_live.py
```
Expected: all tests PASS; black reports no reformatting needed (if it does, run `uv run black` on those two files and re-check).

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/penn/serve_penn.py
git commit -m "feat(backend): --cognition-tools flag on serve_penn (#514)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** CLI flag (Task 2 Step 1), reset-safe threading (Task 1 Steps 1-3), banner (Task 2 Step 3), stale-pointer fixes (Task 1 Step 3 edits b+c), offline plumbing test (Task 1 Step 1), default-path byte-identity (Task 1 Step 4 runs the mirror test; Task 2 Step 4 the full sim suite). Out-of-scope items (config block, /world_state surface) appear in no task. ✓
- **Placeholders:** none — every code step carries the exact code. ✓
- **Type consistency:** `cognition_tools=False` kwarg name identical across Task 1's signature, Task 1's tests, and Task 2's call site; `stepper.chars` / `c.agent.cognition_tools` match the verified shapes (`build_world.py:177,197`, `cognition.py:341-342,365`). ✓
