# Interfacing with ScienceWorld — design

**Status:** Design doc / proposal. Companion to
[`docs/design/planning-benchmark.md`](planning-benchmark.md) (issue #47). That
doc plans *our own* multi-step planning harness and names ScienceWorld as prior
art; this doc works out what it actually takes to plug our engine into
ScienceWorld — both to **evaluate our agents on an external benchmark** and to
**borrow a battle-tested interface** for #47.

**Issue:** #47. **Builds on:** #26 (`text_adventure_games/scenario.py`
world-state predicates), the agent layer (`npc.py` — `Agent.decide`), and the
turn/loop work (#25).

**The clone:** ScienceWorld is checked out at `benchmarks/ScienceWorld` (a
shallow clone of `https://github.com/allenai/ScienceWorld.git`). That directory
is **git-ignored** (`/benchmarks/` in `.gitignore`) — it is an upstream repo
with its own history and a bundled ~7.8 MB JAR, so we never commit it into our
tree. Re-obtain it with:

```bash
git clone --depth 1 https://github.com/allenai/ScienceWorld.git benchmarks/ScienceWorld
```

---

## 1. What ScienceWorld is, and why it's the right reference

ScienceWorld ([Wang et al., EMNLP 2022](https://arxiv.org/abs/2203.07540)) is a
text-based environment of **30 tasks** drawn from the elementary-school science
curriculum — *boil water*, *measure a melting point*, *test electrical
conductivity*, *find a living thing*, *grow a plant*, *Mendelian genetics*. Each
task has dozens to thousands of randomized **variations** (different rooms,
substances, plants), split into **train / dev / test** sets. The paper's framing
question — *"is your agent smarter than a 5th grader?"* — is exactly issue #47's
framing: **environments as benchmarks**, scored by whether an agent's *actions*
reach a goal state, graded at increasing difficulty.

It is the right thing to interface with for three reasons:

1. **Same shape as us.** It is a turn-based, parser-driven text world: an agent
   sends a command string (`activate stove`, `go north`, `pour beaker into
   cup`), the world replies with an observation string. That is precisely the
   contract behind our `Agent.decide(observation) -> command` seam.
2. **It already answers #47's hard questions.** Deterministic scoring with no
   LLM judge, partial credit for multi-step tasks, step budgets, a difficulty
   ladder, train/dev/test splits, and reference ("gold") solutions — all the
   pieces `planning-benchmark.md` lists as open questions, shipped and
   peer-reviewed.
3. **It's an external yardstick.** Scoring our own agents only against our own
   Action Castle / household sim risks overfitting the benchmark to the engine.
   Running the *same* `Agent` against ScienceWorld tells us whether our agent
   layer is actually any good, on a world we didn't design.

What it is **not**: lightweight. It is a Scala simulator compiled to a JAR, run
in a JVM subprocess and reached from Python over [`py4j`](https://www.py4j.org/).
That shapes every "where does this live / how does CI run" decision below
(§7).

---

## 2. The ScienceWorld API surface (what we get to call)

The Python wrapper is one class, `scienceworld.ScienceWorldEnv`
(`benchmarks/ScienceWorld/scienceworld/scienceworld.py`). It is modeled on the
Jericho / OpenAI-Gym signature, so it will feel familiar:

```python
from scienceworld import ScienceWorldEnv

env = ScienceWorldEnv(taskName="", serverPath=None, envStepLimit=100)  # boots the JVM
env.load(taskName, variationIdx=0, simplificationStr="", generateGoldPath=False)
obs, info = env.reset()                       # reset() internally runs one "look around"
obs, reward, done, info = env.step("activate stove")
env.close()                                   # shuts the JVM subprocess down
```

The pieces that matter for us:

| What | Call | Notes |
|------|------|-------|
| Task catalog | `get_task_names()`, `tasks`, `get_max_variations(name)` | 30 tasks; IDs like `1-1 boil`. |
| Variation splits | `get_variations_train/dev/test()`, `get_random_variation_train()` | The benchmark's train/dev/test discipline. |
| The goal | `get_task_description()` / `info['taskDesc']` | A natural-language goal string — maps to our `goal_text`. |
| Step | `step(cmd) -> (obs, reward, done, info)` | The core loop. `reward` is the **delta** in score. |
| Score | `info['score']` (0–100 int) | `100 * internalScore`; the headline metric. |
| Done | `done` (bool) | Set on goal reached, score < 0 (failure), or `moves > envStepLimit`. |
| Subgoal progress | `get_goal_progress()` | Per-subgoal breakdown — partial credit, no LLM judge. |
| Scene / inventory | `info['look']`, `info['inv']`, free `look()` / `inventory()` | "Free" actions: they consume no step. |
| Action space | `get_possible_actions()`, `get_valid_action_object_combinations()`, `info['valid']` | Valid action–object combos for the *current* state. |
| Reference solution | `get_gold_action_sequence()` (needs `generateGoldPath=True`) | A winning command sequence — our `optimal_steps` and a deterministic smoke test. |
| Difficulty knobs | `simplificationStr` (`teleportAction`, `openDoors`, `openContainers`, …; preset `"easy"`) | Tune how hard the world is. |

Two contract details worth pinning down now:

- **`reset()` spends a move.** It calls `step("look around")` internally, so the
  step budget (`envStepLimit`) and `info['moves']` start at 1, not 0. Account
  for that when we set `max_steps`.
- **Scoring is deterministic and engine-side.** The score comes out of the Scala
  simulator, not a model. This is the same "no LLM judges LLM output" stance
  `planning-benchmark.md` commits to — ScienceWorld is living proof the stance
  is workable.

---

## 3. Two directions to interface (and the idea that unifies them)

There are two distinct things "interface with the benchmark" can mean. We want
both, and they share a seam.

### Direction A — our agent *plays* ScienceWorld

ScienceWorld is the **environment**; our `Agent` is the **brain**. We feed
ScienceWorld's observation to `agent.decide(...)` and post the returned command
to `env.step(...)`. This evaluates *our agent layer* against an external
benchmark — the highest-value outcome, and available now without waiting on the
household sim. (§5 details it.)

### Direction B — ScienceWorld as the template for *our* #47 harness

We do **not** port the Scala simulator into Python. Instead we let ScienceWorld's
*interface design* set the contract for the #47 runner: its `step` signature, its
0–1 score with subgoal partial credit, its step budget, its gold paths, its
variation splits. Our own environments (Action Castle, the household sim) get
wrapped to the same contract. (§6 maps the concepts.)

### The unifying seam: one environment protocol

Both directions fall out of a single, tiny **environment protocol** that
ScienceWorld already satisfies and our `Game` can be wrapped to satisfy. The #47
runner then drives *either* without knowing which:

```python
# A structural interface — no base class to inherit, just these methods.
class BenchmarkEnv(Protocol):
    def reset(self) -> tuple[str, dict]: ...            # (observation, info)
    def step(self, command: str) -> tuple[str, float, bool, dict]: ...
                                                        # (obs, reward, done, info)
    def task_description(self) -> str: ...              # the goal text the agent sees
    def score(self) -> float: ...                       # 0..1, partial credit allowed
    def is_goal(self) -> bool: ...                       # terminal success
```

`ScienceWorldEnv` is *already* this shape (modulo a thin normalization wrapper:
its score is 0–100, `is_goal` is `done and score == 100`). For our engine we
write a `GameEnv` adapter where `step` is `parser.parse_command(cmd, actor)`,
`score`/`is_goal` are #26 predicates, and `task_description` is the task's
`goal_text`. One runner, two (eventually many) environments — which is exactly
"environments as benchmarks."

```
                 ┌─────────────────────────────┐
                 │   #47 runner / scorer        │
                 │   loop: decide → step → score│
                 └──────────────┬──────────────┘
                       BenchmarkEnv protocol
              ┌─────────────────┴─────────────────┐
   ┌──────────▼──────────┐            ┌────────────▼────────────┐
   │ ScienceWorldEnv      │            │ GameEnv (our engine)     │
   │ (JVM, gold paths,    │            │ parser gate + #26        │
   │  engine-side score)  │            │ game->bool predicates    │
   └──────────────────────┘            └─────────────────────────┘
```

---

## 4. Mapping ScienceWorld concepts onto our world

This is the Rosetta Stone — and the column that matters most is the last one,
the `PlanningTask` from `planning-benchmark.md`.

| ScienceWorld | Our engine | `planning-benchmark.md` |
|---|---|---|
| `env.load(task, variation)` | `build_game()` → fresh `Game` instance | `PlanningTask.build_game` |
| `get_task_description()` | persona/goals text handed to the agent | `PlanningTask.goal_text` |
| `step(cmd)` | `game.parser.parse_command(cmd, actor)` | one agent decision → action |
| precondition gate | `Action.check_preconditions()` → `apply_effects()` | the hard gate (never bypassed) |
| `info['score']` (0–100) | a `game -> float` over #26 predicates | the metric (§7 there) |
| `done` / `is_goal` | `game.is_won()` *or* a `game -> bool` predicate | `PlanningTask.is_goal` |
| `get_goal_progress()` subgoals | a list of `game -> bool` checkpoint predicates | partial-credit (open Q §8) |
| `envStepLimit` | step budget on the runner loop | `PlanningTask.max_steps` |
| `get_gold_action_sequence()` | hand-authored scripted solution length | `PlanningTask.optimal_steps` |
| train / dev / test variations | seeds / starting-state variants per task | (not yet — borrow it) |
| `info['valid']` action–object combos | `game.describe_for()`'s "available actions" | what the agent is told it can do |

The table makes a quiet but important point: **`scenario.py`'s `game -> bool`
predicates are our `info['score']`.** ScienceWorld computes its score inside the
simulator; we compute ours by composing #26 helpers (`at`, `has_item`, `prop`,
`blocked`). Same role, different mechanism, and — critically — both are
deterministic, no model in the loop.

---

## 5. Direction A in detail — driving ScienceWorld with `Agent.decide`

Our agent layer was built for this. `Agent.decide(observation) -> command` is
*deliberately free of `game`* (see the `npc.py` module docstring) so it can be
unit-tested offline — and, it turns out, driven by *any* environment that can
produce an observation string and consume a command string. ScienceWorld is one.

The runner needs three small bridges, each mirroring something we already have
for our own engine:

**1. Observation assembly** — the analog of `npc.build_npc_context()`. Our
version concatenates `game.describe_for(character)` with recent history; the
ScienceWorld version concatenates the task description, the latest observation,
`info['look']`, and `info['inv']` — and optionally a *sampled* slice of
`info['valid']` so the LLM is reminded what commands are legal (our
`describe_for` already lists "available actions" for the same reason; the full
valid list can be huge, so sample/truncate).

```python
def build_scienceworld_context(obs, info, sample_valid=20):
    lines = [
        f"Task: {info['taskDesc']}",
        f"Observation: {obs}",
        f"Here: {info['look']}",
        f"Inventory: {info['inv']}",
    ]
    valid = info.get("valid", [])
    if valid:
        shown = valid[:sample_valid]
        lines.append("Some valid actions: " + "; ".join(shown))
    return "\n".join(lines)
```

**2. Command routing** — the analog of `npc._route()`. For our engine, `_route`
posts the command through `parser.parse_command` (the precondition gate).
Against ScienceWorld, routing *is* `env.step(command)`; ScienceWorld's simulator
is the precondition gate. "Did it work?" is no longer a parser boolean — read it
off the result: a positive `reward`, a non-zero `score` change, or the absence of
a "No known action" style observation.

**3. Reflection on failure** — `npc.decide_and_route()` already implements
Decide → Act → Reflect: on failure it feeds the parser's failure reason back into
the next observation and retries. That loop is the one piece **coupled to
`game.parser`** today. The clean move is to lift the reflection tail out of
`npc.py` so it takes a generic "route + explain failure" callable; then the
ScienceWorld runner reuses the *same* retry/reflect logic, with the failure
string drawn from ScienceWorld's observation instead of `parser.last_fail_message`.
(Small refactor; flagged as an open question in §8.)

The runner itself is then short — note how closely it tracks the upstream
`examples/random_agent.py`, with `agent.decide(...)` swapped in for the random
pick:

```python
def run_scienceworld_task(agent, task_name, variation, *, step_limit=100):
    env = ScienceWorldEnv(envStepLimit=step_limit)
    env.load(task_name, variation, simplificationStr="easy")
    obs, info = env.reset()
    done = False
    while not done:
        observation = build_scienceworld_context(obs, info)
        command = agent.decide(observation)        # our Agent — LLM or scripted
        if not command:
            break                                   # agent declined to act
        obs, reward, done, info = env.step(command)
    env.close()
    return {
        "task": task_name, "variation": variation,
        "score": info["score"], "moves": info["moves"],
        "goal_progress": env.get_goal_progress(),   # subgoal breakdown
    }
```

Because `Agent` is the seam, this works unchanged for an `LLMAgent` (real
reasoning), a `ScriptedAgent` (a fixed rule), or a future memory-backed agent —
the runner can't tell which is driving, exactly as in our own loop.

---

## 6. The metric, reconciled

`planning-benchmark.md` §6 wants: goal success rate, success-by-tier,
steps-to-goal, step efficiency — all deterministic, no LLM judge. ScienceWorld
hands us each of these for free, and resolves one of that doc's open questions:

- **Goal success rate** → `info['score'] == 100` (or `done and score == max`).
- **Steps-to-goal / efficiency** → `info['moves']`, with `optimal_steps` from the
  **gold action sequence** (`generateGoldPath=True`) rather than a hand count.
- **Partial credit** → `get_goal_progress()` gives per-subgoal scoring. This is a
  concrete answer to `planning-benchmark.md` §8's open question ("boolean goal
  only, or sub-goal checkpoints?"): adopt ScienceWorld's subgoal model — a task
  carries a list of checkpoint predicates and the score is the fraction met.
- **Difficulty ladder** → ScienceWorld's tasks already span 1-step to many-step,
  and `simplificationStr` tunes difficulty without rewriting tasks. Useful to
  *calibrate* our own 1/few/many tiers against an external scale.

So the metric work isn't duplicated — ScienceWorld and our `GameEnv` report the
same fields through the protocol, and the scorer aggregates them identically
regardless of which environment produced them.

---

## 7. Practical concerns (the cost of the JVM)

ScienceWorld is heavier than anything else we depend on, and that drives where
the code lives and how (and whether) CI runs it.

- **It needs Java + a JVM subprocess.** `ScienceWorldEnv()` launches a JAR via
  `py4j.launch_gateway`. Requires **Java 1.8+** on the machine and the `py4j`
  Python package. This is at odds with our "free, offline, deterministic"
  default (`LLM_PROVIDER=mock`, no network) — so it must be **strictly
  optional**.
- **Python version is fine.** ScienceWorld declares `python_requires>=3.7`; we
  require `>=3.11`. No conflict — it runs on our supported interpreters; only
  Java is the extra prerequisite.
- **Make it an optional extra, mirroring `[llm]`.** Add a `benchmark` extra to
  `pyproject.toml` (`benchmark = ["scienceworld"]`), installed on demand with
  `pip install -e ".[benchmark]"`. The adapter must **import `scienceworld`
  lazily** (inside the runner, not at module top level) and degrade with a clear
  "install the benchmark extra and a JDK" message — exactly how the engine treats
  `rich` and the LLM providers today.
- **Keep it out of the default test suite.** The standard `pytest tests/` run
  must stay JVM-free and offline. Gate ScienceWorld tests behind a marker
  (`@pytest.mark.scienceworld`) and/or an env var, skipped unless Java + the
  extra are present. Same spirit as the LLM tests being mock-only by default.
- **There's a deterministic smoke test that needs no LLM.** Load a task with
  `generateGoldPath=True`, replay `get_gold_action_sequence()` through `step`,
  and assert the score reaches 100. That validates the *adapter wiring* (boot,
  load, step, score) with zero model calls and zero flakiness — the ideal CI
  check for the integration, when a JDK is available.
- **The mock agent won't solve ScienceWorld.** Our `MockReActClient` is
  string-coupled to Action Castle, so it can't plan ScienceWorld tasks. CI's
  cheap path is therefore the gold-path replay (above) plus a *random/scripted*
  agent smoke run (asserting the loop runs and reports a score, not that it
  wins). Real evaluation — "how good is our agent?" — needs a real `LLMAgent`
  and is a deliberate, gated, costs-money run, not part of `pytest`.
- **Lifecycle hygiene.** Each `ScienceWorldEnv` is a live JVM subprocess; always
  `env.close()` (wrap the runner in `try/finally`). Reuse one `env` across
  variations of a task (call `load()` again) rather than booting a JVM per
  episode — booting is slow.
- **Where the code lives.** A `benchmarks/` Python package in *our* tree (sibling
  to the git-ignored clone), e.g. `benchmarks/scienceworld_runner.py` +
  `benchmarks/protocol.py` (the `BenchmarkEnv` shape and the `GameEnv` wrapper).
  Importable, not test-only — `planning-benchmark.md` §8 leans the same way for
  the harness. The git-ignored `benchmarks/ScienceWorld/` clone stays separate;
  the installed `scienceworld` package (the extra) is what we import.

---

## 8. Build order (tentative)

| Stage | Deliverable |
|-------|-------------|
| 1 | `pip install -e ".[benchmark]"` extra + a 10-line spike: boot `ScienceWorldEnv`, load task `1-1 boil`, replay the gold path, print the score. Proves the JVM bridge works on our machines. |
| 2 | `build_scienceworld_context()` + `run_scienceworld_task()` (§5). Drive it with a `ScriptedAgent` / random agent first — wiring before brains. |
| 3 | Run a real `LLMAgent` on a handful of dev variations of 2–3 tasks across the difficulty range; eyeball transcripts + scores. The first real "is our agent any good?" number. |
| 4 | Factor out the `BenchmarkEnv` protocol (§3) and a `GameEnv` wrapper over our engine, so the #47 runner drives both. Lift the reflect tail out of `npc.py` (§5, bridge 3). |
| 5 | Gold-path replay test behind `@pytest.mark.scienceworld`; random-agent smoke run. Wire into a *separate* CI job that installs the JDK + extra. |

Stages 1–3 deliver the high-value outcome (our agent benchmarked externally);
4–5 fold ScienceWorld into the shared #47 harness and make it safe to keep.

---

## 9. Open questions

- **Goal delivery.** ScienceWorld's task description is a clean goal string. Does
  it ride in the agent's `persona`/`goals` (so it flows through the existing
  `_system_message()` path) or a dedicated "Task:" block in the observation?
  Same open question as `planning-benchmark.md` §8 — and answering it here, on a
  real external goal, will inform the answer there.
- **Action-space hinting.** How much of `info['valid']` do we show the agent?
  None (pure planning, hardest), a sampled slice (our `describe_for` analog), or
  all of it (closer to the DRRN/KG-A2C baselines that consume the valid set)?
  This is a real axis of the benchmark, not just a prompt detail.
- **Reflect-loop refactor.** Lifting Decide→Act→Reflect out of its coupling to
  `game.parser` (§5, bridge 3) is the one engine change Direction A needs. Worth
  doing for its own sake (it makes the loop reusable), but it touches `npc.py` —
  scope it before #47 leans on it.
- **Score normalization.** Treat ScienceWorld's 0–100 as our canonical 0–1 score
  in the protocol, or keep environments' native scales and normalize only at
  report time? (Leaning: normalize to 0–1 in the protocol; it keeps the scorer
  environment-agnostic.)
- **Is the JVM worth it long-term?** ScienceWorld is invaluable as an external
  yardstick *now*. But every CI minute it costs and JDK it requires is friction.
  Plausible end state: use it heavily during agent-layer development (validation),
  then keep only the gold-path smoke test in CI and run full evaluations
  on-demand. Decide once we've seen stage-3 numbers.

---

## 10. Why this is a proposal, not a spec

The same caveat as `planning-benchmark.md`: the agent loop (#25), agent memory
(#37), and the household sim are all still moving, and they change how well an
agent does on multi-step tasks — which is the whole thing ScienceWorld measures.
The stable commitments here are narrow and worth holding to: **reuse `Agent` as
the brain unchanged**, **keep ScienceWorld an optional, JVM-gated dependency
out of the default suite**, and **converge our engine and ScienceWorld behind one
`BenchmarkEnv` protocol** so #47's runner is environment-agnostic. Everything in
§5–§8 is a direction, not a contract.
