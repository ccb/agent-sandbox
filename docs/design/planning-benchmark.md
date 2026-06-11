# Multi-Step Planning Benchmark — Temp Plan

**Status:** Temporary plan / placeholder. Expected to change as the follow-ups to
#26, the household sim environment, and the multi-agent loop land. This is the
shared sketch to argue over, not a frozen spec.

**Issue:** #47 (likely an epic). **Builds on:** #26 —
`text_adventure_games/scenario.py` world-state predicates (already merged).

*A harness that gives an agent a broad **goal** in a defined environment, lets it
choose a sequence of actions, and reports whether it reached the **goal state** —
graded at increasing step-counts so we can measure how far an agent's planning
holds up.*

---

## 1. The idea

We want to benchmark **multi-step planning**: not "did the agent say something
plausible," but "did the sequence of actions it chose actually change the world
into a state that satisfies the goal." Splitting tasks by the number of actions
required is a clean difficulty axis. CCB's apartment-sim examples:

- **1 action:** turn on the stove.
- **A few actions:** the agent is hungry → make food → eat it.
- **Many actions:** the bed sheets are dirty → washer → dryer → fresh sheets on
  the bed.

The framing is **environments as benchmarks**: design environments/tasks that
exercise a specific capability and score success at reaching goal states that
require *X* steps. Prior art to borrow from:

- **ScienceWorld**, **ALFWorld**, **Discovery World** — text/embodied task suites
  graded on goal achievement.
- **AI2-THOR** — the 3D analog (out of scope here, useful as a reference point).

This is *not* limited to Action Castle. The household sim (stove / food / laundry)
is a natural second environment and is in scope.

### On "realism" (the thing we are deliberately *not* doing)

Alistair raised Concordia (arXiv:2312.03664) and the question of judging
simulation *realism*. CCB's steer: judging realism directly is too hard, and
LLMs grading LLM output is unreliable. So this benchmark sidesteps it:

- **Primary signal = agent behavior**, i.e. goal achievement at N steps. No model
  judges "was this realistic."
- Where a quality judgment is genuinely unavoidable, prefer a **structured
  rubric** (AutoRubric, https://autorubric.org) that decomposes "is this good?"
  into granular, checkable items — never a single naive yes/no.
- Grounding an environment in an **existing domain theory** (economics, urban
  design, household routines) can serve as a realism proxy without a judge.

For the first pass, every task here is scored by a deterministic `game -> bool`
predicate. No LLM grader.

---

## 2. What we already have (#26)

`text_adventure_games/scenario.py` is the foundation. It is intentionally
game-agnostic so an agent eval can import it directly:

- `play(game, commands)` — run a command sequence, return per-command success.
- `blocked(game, location, direction)`, `prop(game, thing, key)`,
  `at(game, character, location)`, `has_item(game, character, item)` — read world
  state **by name**, not by holding object references.

`tests/test_scenarios.py` already expresses **goal predicates** as plain
`game -> bool` functions (`troll_fed`, `drawbridge_open`, `rose_picked`) and its
docstring explicitly anticipates this benchmark:

> a future agent eval would let an agent generate the commands and reuse the same
> `game -> bool` predicates below to score success.

So the seam already exists: a scripted scenario = *command sequence* + *goal
predicate*. This benchmark **replaces the scripted command sequence with an
agent run** and reuses the predicate to score it. That's the whole trick.

---

## 3. Three pieces (the epic, split for sub-issues)

Per the acceptance note, #47 is likely an epic. The natural split:

1. **Task environments** — the worlds and starting states. Action Castle exists;
   add a small household sim (stove, food, laundry) as the second environment.
2. **Goal predicates** — `game -> bool` checks for each task's goal state, plus a
   shared vocabulary of composable predicates (extends #26's helpers).
3. **The runner / scorer** — drives an agent toward a goal under a step budget,
   detects goal satisfaction, and reports the result + metrics.

Each can be its own sub-issue; (1) and (2) unblock (3).

---

## 4. Task ladder (≥3 tasks, 1-step → multi-step)

Acceptance asks for at least 3 tasks spanning the difficulty axis. Tentative set,
mixing both environments so we don't overfit to one:

| Tier | Steps | Household sim | Action Castle analog |
|------|-------|---------------|----------------------|
| T1 | 1 | turn on the stove | `troll_fed` after a single `give fish to troll` from a primed state |
| T2 | few (3–5) | hungry → make food → eat it (`not is_hungry`) | pick the rose: navigate → `pick rose` (`rose_picked`) |
| T3 | many (6+) | dirty sheets → washer → dryer → make bed (`bed.has_clean_sheets`) | feed-the-troll end to end: get pole → fish → cross → `drawbridge_open` |

Each task is a record (sketch):

```python
@dataclass
class PlanningTask:
    name: str
    tier: int                       # 1 / 2 / 3 (rough step-count band)
    build_game: Callable[[], Game]  # fresh instance, agent attached
    goal_text: str                  # the broad goal handed to the agent
    is_goal: Callable[[Game], bool] # reuses #26 predicates
    max_steps: int                  # step budget (≈ optimal * slack)
    optimal_steps: int | None = None
```

`goal_text` is the only natural-language part the agent sees; `is_goal` is the
deterministic grader.

---

## 5. The runner / scorer (sketch)

```python
def run_task(task) -> TaskResult:
    game = task.build_game()              # agent attached via Character.set_agent
    for step in range(task.max_steps):
        if task.is_goal(game):
            return TaskResult(task.name, reached=True, steps=step)
        game.advance()                    # one agent decision -> action
    return TaskResult(task.name, reached=task.is_goal(game), steps=task.max_steps)
```

Open seam: **how the agent gets the goal.** Cleanest is to put `goal_text` into
the agent's persona/goals so it flows through the existing
`Agent.decide(observation)` path — no new prompt machinery, and it matches how
goals already reach NPCs. To confirm against the current agent loop / `turns.py`.

Notes:

- Every action still passes the parser's `check_preconditions()` → `apply_effects()`
  gate. The benchmark never lets an agent shortcut the world.
- The loop checks the goal *each step*, so we capture **steps-to-goal**, not just
  pass/fail.
- Runs must be reproducible offline: `LLM_PROVIDER=mock` should drive the harness
  for free in CI, with real providers gated behind env vars.

---

## 6. The metric (short writeup, to expand)

Report per task and aggregated by tier:

- **Goal success rate** — fraction of tasks where `is_goal(game)` holds within the
  step budget. The headline number.
- **Success @ tier** — success broken out by 1-step / few / many, so we can see
  *where* planning falls off.
- **Steps-to-goal** and **step efficiency** (`optimal_steps / steps_taken`) for
  solved tasks — distinguishes "barely made it under budget" from "planned well."
- **Failure reason** (optional, later) — budget exhausted vs. stuck-looping vs.
  precondition wall.

Keep it deterministic and predicate-based. No realism score, no LLM judge.

---

## 7. Build order (tentative)

| Stage | Deliverable |
|-------|-------------|
| 1 | `PlanningTask` / `TaskResult` types + `run_task` runner, scored with #26 predicates against Action Castle. |
| 2 | One task per tier on Action Castle (reuse existing predicates); offline mock run end to end. |
| 3 | Minimal household sim environment (stove / food / laundry) + its goal predicates. |
| 4 | Full ladder across both environments; aggregate metric report. |
| 5 | Short metric writeup (this doc's §6, expanded) + example run output. |
| 6 | (Stretch) AutoRubric-style structured checks for any task whose goal can't be a clean boolean. |

Stages 1–2 are enough to satisfy acceptance (harness + ≥3 tasks + reuses #26 +
metric writeup); 3+ broaden coverage.

---

## 8. Open questions

- **Goal delivery:** persona/goals field, a dedicated `goal_text` prompt section,
  or both? Depends on where the agent loop settles (#25 / turn-mode work).
- **Household sim scope:** how rich? Just enough things/actions for the three
  household tasks, or a reusable environment others build on?
- **Step budget policy:** fixed per task, or `optimal * k`? How do we set
  `optimal_steps` — hand-authored scripted solution length?
- **Multi-agent tasks:** start single-agent. Do contested-goal / cooperative
  tasks belong here later, or in a separate benchmark?
- **Partial credit:** boolean goal only, or sub-goal checkpoints for the
  many-step tasks (e.g. sheets washed / dried / on bed)?
- **Where does this live?** `text_adventure_games/benchmark/` module vs.
  `tests/`-adjacent. Leaning toward an importable module so it's not test-only.

---

## 9. Why this is a temp plan

The pieces this depends on are still moving:

- The **agent loop / turn mode** (#25 and follow-ups) determines how an agent is
  attached and stepped — §5's `game.advance()` is a placeholder for whatever that
  settles into.
- **Agent memory** (#37 design) will change how well agents do many-step tasks,
  which affects budgets and tiering.
- The **household sim** doesn't exist yet; its actions/properties will reshape §4.

So treat §4–§7 as a direction, not a contract. The stable commitments are: reuse
#26's `game -> bool` predicates, score behavior not realism, and grade by
steps-to-goal across a 1-step → many-step ladder.
