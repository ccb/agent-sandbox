# Daily Planning Design — day → hourly → minute

**Status:** Build order §13 steps 1–6 implemented (issue #83). The engine plan
data model + `Planner` protocol + pure helpers ship in
`text_adventure_games/planning.py`; the Smallville `MockPlanner`/`LLMPlanner`, the
`SimClock` time mapping, the revision seam (`maybe_revise_plan` + the
`simulate()` trigger sites), and `backend/compare_plans.py` ship in
`generative-agents/backend/`. The mock path keeps the replay byte-identical;
`LLMPlanner` is written against the engine's `LlmClient` seam and tested with a
fake client, so a real model is a `client_from_env()` swap once **Phase A** lands.
Still open: periodic **reflection** (§13 step 7) and the **`PERCEPTION`** revision
trigger (needs mid-activity perception). This supersedes the brief planning sketch
in [`agent-memory.md` §8](agent-memory.md), expanding it from "1–3 next intentions"
to the paper's full day → hourly → minute decomposition with revision.

**Source paper:** Park et al., "Generative Agents: Interactive Simulacra of Human
Behavior" (arXiv:2304.03442v2 / UIST 2023), §"Planning and Reacting".

**Issue:** #83 (XL). **Builds on:** Phase B memory (#75/#76/#79, done) and the
static-schedule seam landed on `ga-5-agents-memory-reasoning-ui` (see §3).
**Wants, but does not strictly require:** Phase A (a real LLM brain) — see §9 on
how the design stays useful and testable while the mock is still the default
brain.

> **Reference implementation to study, not reinvent:** the ROADMAP flags a clean
> planning + retrieval implementation in the "Generative Action Castle" prototype
> (ask Chris). Read it before building §6–§8 — the prompt shapes and the
> day→hourly→minute recursion are already worked out there.

*A design for replacing each persona's hand-authored schedule with a plan the
agent **generates** from its identity and memory, **decomposes** from a coarse
day outline down to minute-level concrete stops, and **revises** as the day
unfolds — without changing the step loop, the precondition gate, or the
offline/CI replay's determinism.*

---

## 1. Why planning

Today a persona's whole day is hand-authored YAML. Isabella's day is literally
four dictionaries a human typed:

```yaml
schedule:
- {place: Hobbs Cafe, activity: tending the cafe counter, emoji: ☕, steps: 220}
- {place: The Willows Market and Pharmacy, activity: buying fresh milk, emoji: 🛒, steps: 150}
- {place: Hobbs Cafe, activity: chatting with the morning customers, emoji: 💬, steps: 200}
- {place: Johnson Park, activity: taking a quiet break on a bench}
```

That is a real improvement over the original single `destination`/`activity` — it
keeps memory growing and lets co-located residents meet more than once — but it is
**static**. Every run is the same; the plan ignores who the agent is, what it
remembers, and what just happened. Isabella will go buy milk at the same step
whether or not she already has milk, whether or not she just had a long
conversation, whether or not it would make her late to open the cafe.

The paper makes the day **emerge** from the agent instead:

1. **Generate** a broad daily plan from the agent's identity + a summary of
   yesterday ("Isabella, café owner, party tonight → open café, prep, host").
2. **Decompose** it top-down: day outline → hourly chunks → minute-level actions,
   each level conditioned on the level above.
3. **Revise** it when reality diverges — a conversation runs long, a perception
   contradicts the plan, an action fails. React, then re-plan the rest of the day.

This is the single change that most makes the town feel alive, because it is what
lets two runs differ and lets an agent's history actually shape its day.

---

## 2. Design goals

In priority order — earlier goals win ties:

1. **The offline mock replay stays byte-identical.** This is the project's iron
   rule (README, `resolve_embedding_client` docstring, the determinism tests). A
   default `run_simulation` run must produce the same `movement/*.json` it does
   today. The mock planner reproduces today's static schedule exactly (§9).
2. **Reuse the seam, don't re-plumb the loop.** The output of planning is the
   same ordered list of `{place, activity, emoji, steps}` stops the step loop
   already drives via `SmallvilleMockClient.advance()` (§3). A planner *produces*
   schedules; `simulate()` keeps *consuming* them unchanged.
3. **Plans are memories.** A plan is stored as `MemoryKind.PLAN` records in the
   agent's stream (the API already exists — `AgentMemory.add_plan`), so retrieval
   surfaces "what I meant to do today" and reflection can reason over it.
4. **Preconditions stay hard-gated.** A plan is an *intention*, never a world
   mutation. Every concrete stop still travels and performs through the engine's
   `Travel`/`Act` precondition gate. A plan can want something illegal; the parser
   still says no, and that failure feeds revision (§8).
5. **Readable over clever.** Audience is first/second-year undergrads. Three named
   levels (day/hourly/minute), small dataclasses, one prompt per level.
6. **Engine vs port split.** The *mechanism* — a plan data model, a `Planner`
   protocol, decompose/revise helpers — is reusable cognition and belongs in the
   `text_adventure_games` library `[engine]`. The *Smallville wiring* — feeding it
   the cast, turning minute-stops into tile walks — is `[port]`.

---

## 3. Current repo fit — what we build on

The groundwork already in `main` (merged from `ga-5-agents-memory-reasoning-ui`)
gives planning a clean place to plug in. Don't rebuild these:

- **The schedule seam.** `build_world._normalize_personas()` guarantees every
  persona carries a uniform `schedule` list of `{place, activity, emoji, steps}`
  stops. `SmallvilleMockClient` reads the *current* stop and exposes `advance()`;
  `run_simulation.simulate()` owns the clock and calls `advance()` when a stop's
  `steps` elapse. **A generated planner produces this same list** — it replaces
  the *source* of the schedule (hand-authored YAML), not the loop that drives it.
- **The decision seam.** Every persona already decides through the engine's real
  `Agent.decide()` → parser → precondition gate, under `turn_mode="simultaneous"`.
  Swapping in a real brain is a client swap (Phase A), not a rewrite.
- **The memory stream (Phase B, done).** `AgentMemory` has `add_plan()`,
  `MemoryKind.PLAN`, and `retrieve(query, turn)` scored by recency × relevance ×
  importance. `attach_agents` already seeds one day-plan memory per persona
  ("Plan: go to … Today's stops: …"). Planning generalizes that seed from a
  hand-copied string into a generated, decomposed, revisable structure.
- **The clock.** `run_simulation` already has `--start` (ISO datetime),
  `--steps`, and `--sec-per-step`. The exporter derives wall-clock time per step.
  So "8:00 AM" ↔ "step 0" is already expressible; §10 just formalizes the mapping
  planning needs.

The gap is only the **source** of the schedule and the **cognition** that revises
it. Everything downstream of "here is an ordered list of stops" already works.

---

## 4. The three levels

The paper plans recursively, each level conditioned on the one above. We mirror
that with three named levels, all expressed in the engine's vocabulary
(`Location` names + activity strings), so the output drops straight onto the
existing seam.

| Level | Granularity | Example | Maps to |
| --- | --- | --- | --- |
| **Day outline** | 4–6 broad blocks, no exact times | "morning: open & run the café; midday: errands; afternoon: prep for tonight's party" | a list of `DayBlock` |
| **Hourly plan** | one line per in-sim hour | "8–10am tend the counter; 10–11am buy milk at the market; 11am–1pm chat with customers" | a list of `HourBlock` |
| **Minute plan** | concrete stops with durations | `{place: Hobbs Cafe, activity: tending the counter, steps: 220}` … | the existing `schedule` list |

Only the **minute plan** reaches the step loop — it *is* today's `schedule`
shape. The day and hourly levels are intermediate reasoning kept as PLAN memories
so retrieval and reflection (and revision, §8) can see the agent's intentions at
every altitude, not just the next concrete stop.

Decomposition is top-down and **lazy where it helps**: generate the whole day
outline at wake time, but only decompose the *current and next* hour to
minute-stops, re-decomposing later hours after revisions. This keeps early
minute-stops from being invalidated the moment the day diverges (and, with a real
LLM, keeps token cost down — you don't pay to plan minutes you'll re-plan anyway).

---

## 5. Data model `[engine]`

Small, immutable dataclasses in a new `text_adventure_games/planning.py`. Plans
also round-trip into the memory stream as text (§3, goal 3); these structs are the
*working* representation the planner manipulates before it commits stops to the
schedule.

```python
@dataclass(frozen=True)
class DayBlock:
    label: str            # "morning", "midday", "afternoon", "evening"
    summary: str          # "open and run the café"

@dataclass(frozen=True)
class HourBlock:
    start_hour: int       # in-sim hour, 0-23
    summary: str          # "tend the counter, then buy milk"

@dataclass(frozen=True)
class Stop:               # the minute level == today's schedule entry
    place: str            # must resolve to a known Location name
    activity: str
    emoji: str | None = None
    steps: int | None = None   # None => stay for the rest of the day

@dataclass
class DailyPlan:
    day: list[DayBlock]
    hours: list[HourBlock]
    stops: list[Stop]          # the part the step loop consumes
    revision: int = 0          # bumped each time revise() rewrites the tail
```

`DailyPlan.stops` is exactly the list `SmallvilleMockClient` already walks, so
"commit a plan" is `client.schedule = [asdict-ish stop for stop in plan.stops]`.
A `Stop` with `steps=None` is the existing "stay put" convention — preserved so
the last stop of the day still behaves as it does now.

---

## 6. Generation — identity + memory → day outline `[engine]` mechanism / `[port]` data

At the start of an agent's day (step where the sim clock crosses the agent's wake
time), generate the day outline from:

- **Identity** — the persona text already in the system prompt (innate traits,
  role, `learned`/`currently`), plus the upstream `daily_plan_req` hard constraint
  when present (shopkeeper hours, etc.) — the port doc §3.1 lists these fields.
- **Memory** — a retrieval over the stream for "what matters for today": the
  highest-importance recent memories + any leftover plans/reflections. This is
  the existing `AgentMemory.retrieve()` call; planning just queries it with a
  "what should I do today" query instead of the current-tile query.

The generation step is a single LLM call behind a `Planner` protocol (§9). It
returns the `DayBlock` list, which is then committed to memory as PLAN records and
decomposed downward (§7). Prompt shape (study the Generative Action Castle
prototype for the exact wording):

```
You are {persona}. It is {weekday} morning, {date}.
Relevant memories: {retrieved block}
{daily_plan_req, if any}
Sketch your day as 4-6 broad blocks (morning/midday/afternoon/evening).
Each block: a short phrase. Don't pick exact times yet.
```

---

## 7. Decomposition — day → hourly → minute `[engine]`

Two more LLM calls, each conditioned on the level above and the agent's known
places (the `spatial_memory` tree already surfaced as engine `Knowledge`, #79 —
so the planner only schedules places the agent actually knows):

1. **Day → hourly:** given the day outline and the day's hour span (derived from
   `--start` + `--steps` via §10), produce one `HourBlock` per hour.
2. **Hourly → minute:** for the current (and next) hour, expand each into concrete
   `Stop`s. The planner picks `steps` durations that sum to the hour's step budget
   (§10 converts hours↔steps), and an emoji per stop (falling back to the
   persona's default, exactly as `_normalize_personas` does today).

**Validation gate (deterministic, no LLM):** before any generated stop is
committed, check `place` resolves to a known `Location` and `steps` is a positive
int or `None` — the same check `build_world` does today for hand-authored places,
moved into the planner so a hallucinated place is caught with a clear message
instead of failing in the parser. An invalid stop is dropped and re-requested
(bounded retries), never silently kept.

---

## 8. Revision — react and re-plan the tail `[engine]`

The paper re-plans when an observation is relevant enough to interrupt the current
action. We hook the moments the step loop already has and the precondition gate
already produces:

- **Perception divergence** — `ingest_events` folded in a memory that contradicts
  the plan (e.g. "the café is already crowded", a conversation started). Trigger:
  a perceived memory above an importance threshold while an activity is in
  progress.
- **Action failure** — a `travel`/`perform` command failed its preconditions. The
  failure reason is already captured (`react_behavior` records it; §9 of
  agent-memory). That reason feeds the re-plan prompt directly.
- **Running behind / ahead** — the agent is still walking when its hour's step
  budget is spent, or finished early. Detectable from the clock alone (§10), no
  LLM needed to *notice*; an LLM call to *decide* what to drop.

Revision **only rewrites the tail** — stops the agent hasn't started yet. Already
executed stops are history (they're in memory). Mechanically: re-decompose the
remaining hours (§7), replace `plan.stops[stop_index+1:]`, bump `plan.revision`,
and write a short PLAN memory ("Re-planned: skipping the market, café first"). The
step loop keeps reading the *current* stop via `advance()`, so a tail rewrite is
invisible to the loop — it just finds different stops waiting when it advances.

> **Invariant:** revision never edits the stop the agent is *currently* performing
> (that would desync the on-screen activity from the schedule). It edits only what
> comes after. This keeps memory, the replay, and the schedule consistent.

---

## 9. The brain split — mock vs real LLM (determinism) `[port]`

Planning is a *cognition* change, and Phase A (a real LLM) is not landed yet. The
design works in both worlds via a `Planner` protocol with two implementations,
chosen the same way the brain is today:

```python
class Planner(Protocol):
    def generate(self, persona, memory, clock) -> DailyPlan: ...
    def revise(self, plan, trigger, memory, clock) -> DailyPlan: ...
```

- **`MockPlanner` (default, offline, CI).** Produces a `DailyPlan` whose `stops`
  are **exactly today's hand-authored schedule** for that persona — read from
  `world_data.yaml` just as now. `revise()` is a no-op (returns the plan
  unchanged). Result: `MockPlanner` + `SmallvilleMockClient` reproduce the current
  schedule stop-for-stop, so **`movement/*.json` is byte-identical** and the
  determinism tests pass untouched. The YAML schedules become the *mock's fixture*
  rather than the only source of truth.
- **`LLMPlanner` (opt-in, Phase A).** Implements §6–§8 against a real
  `client_from_env()` model. Selected by the same provider gate as the brain
  (`LLM_PROVIDER` ≠ `mock`), so an offline run never reaches it.

This mirrors exactly how `--embeddings` already works: a default-on cognitive
upgrade that the mock brain ignores, leaving the replay identical, with a
`compare_*` path to actually watch the two diverge. We add a small
`backend/compare_plans.py` (analogous to `compare_retrieval.py`) that prints a
mock schedule beside an LLM-generated one for the same persona, so the difference
is inspectable offline-vs-online without needing the frontend.

---

## 10. Time mapping `[port]` (the Phase D `[port] M` item)

Smallville is minute-level continuous time; our loop is discrete 10-second steps.
Planning needs to talk in hours and have them land on the right step counts.

- One step = `--sec-per-step` seconds (default 10). One in-sim **hour** =
  `3600 / sec_per_step` steps (360 at the default).
- The sim clock at step *s* is `start_dt + s * sec_per_step`. So "this agent's
  9am hour" is the step range `[(9:00 - start)/sec_per_step, (10:00 - start)/...)`.
- A `Stop.steps` is a count of these steps — already what `perform_until` consumes
  in `simulate()`. Hourly→minute decomposition (§7) just makes each hour's stops'
  `steps` sum to that hour's step budget.

This lives in a small `clock`-aware helper the planner shares with the loop, so
"plan in clock time" and "drive in steps" use one conversion, not two.

`game.turn` is already set to the step index each iteration (for memory recency),
so plans, memories, and the loop all share one integer time axis.

---

## 11. Integration sketch `[port]`

What changes in the existing files, kept deliberately small:

- **`build_world.py`** — `_normalize_personas` stays (it's how the mock fixture is
  loaded), but `PERSONAS` schedules are no longer assumed to be *the* plan. A
  persona's schedule is what `MockPlanner` returns; `LLMPlanner` ignores it.
- **`attach_agents` (`smallville_agents.py`)** — construct a `Planner` per agent
  (mock vs real by the provider gate), call `planner.generate(...)` at wake, and
  commit `plan.stops` onto the client's `schedule`. The one-line plan-memory seed
  it does today becomes "write each `DayBlock`/`HourBlock` as a PLAN memory."
- **`run_simulation.simulate()`** — at an agent's wake step, generate its plan; at
  the existing revision triggers (§8), call `planner.revise(...)` and replace the
  schedule tail. **The advance()/perform_until clock loop is untouched** — it
  already drives whatever stops are in the schedule. This is the payoff of goal 2.

Pseudo-diff of the loop's decision point (additions only):

```python
# at wake (clock crosses agent's wake time), once per agent per day:
plan = planner.generate(persona, char.agent.memory, clock)
commit_plan_memories(char.agent.memory, plan, turn=_step)
char.agent.llm_client.schedule = [stop_to_dict(s) for s in plan.stops]

# at a revision trigger (perception/failure/behind), tail-only:
plan = planner.revise(plan, trigger, char.agent.memory, clock)
char.agent.llm_client.replace_tail(plan.stops, after=client.stop_index)
```

`SmallvilleMockClient` grows one method — `replace_tail(stops, after)` — that
swaps out `schedule[after+1:]`; everything else on the client stays.

---

## 12. Testing plan `[port]` + `[engine]`

Offline, deterministic, no live LLM — same discipline as the rest of the suite:

1. **Determinism (the gate):** with `MockPlanner`, `simulate()` produces frames
   byte-identical to a golden run. This is the existing determinism test; it must
   pass unchanged. *If this breaks, the change is wrong.*
2. **Data model:** `DailyPlan` round-trips through `to_primitive`/`from_primitive`
   and into/out of the memory stream as PLAN records.
3. **Decomposition arithmetic (no LLM):** a fake planner returning canned levels —
   assert hour blocks cover the day span, minute-stops' `steps` sum to each hour's
   budget, every stop's place is a known `Location`, invalid stops are dropped.
4. **Revision tail-only:** given a plan mid-execution and a trigger, assert
   `revise()` leaves executed + current stops intact and only rewrites the tail,
   bumps `revision`, and writes a PLAN memory.
5. **Time mapping:** hour↔step conversions at non-default `--sec-per-step` and a
   non-midnight `--start`.
6. **Mock-vs-LLM seam:** a stub `LLMPlanner` over the `MockReActClient` proves the
   protocol is satisfiable and the provider gate selects correctly — no network.

Keep the mock path green throughout (cross-cutting NEXT-STEPS item).

---

## 13. Build order (suggested PR slicing)

Each row is a shippable PR; the replay stays byte-identical until the very last.

1. **`[engine]` Plan data model + `Planner` protocol** (`planning.py`) + unit
   tests (§12.2). No behavior change.
2. **`[engine]` Decompose/revise helpers** as pure functions over a fake
   level-generator (§12.3–4). Still no live model, no port wiring.
3. **`[port]` `MockPlanner` + wire `attach_agents`/`simulate` to it.** This is the
   determinism-critical PR: schedules now *flow through* the planner, but
   `MockPlanner` reproduces the YAML, so frames don't move (§12.1).
4. **`[port]` Time mapping helper** (§10) + tests (§12.5).
5. **`[port]` Revision triggers** wired to the existing perception/failure/clock
   signals, `MockPlanner.revise` still a no-op → frames unchanged.
6. **`[engine/port]` `LLMPlanner`** (rides on Phase A) + `compare_plans.py` (§9).
   First PR where an opt-in real-LLM run produces a *different*, generated day.
7. **Periodic reflection** (the sibling Phase D item) can land in parallel after
   3 — it writes REFLECTION memories the planner reads, but isn't on this
   doc's critical path.

Stop after 5 and the port has a real planning *architecture* with the static day
as its mock fixture; 6 is what makes the town's day actually emergent.

---

## 14. Design invariants

The rules a reviewer should check every PR against:

1. **A default (mock) run's `movement/*.json` is byte-identical to today's.** The
   determinism test is the gate; `MockPlanner` exists to honor this.
2. **A plan is an intention, never a mutation.** Every stop still executes through
   the `Travel`/`Act` precondition gate; planning cannot bypass it.
3. **Plans live in the memory stream** as `MemoryKind.PLAN` records — one source of
   truth for "what I meant to do," visible to retrieval and reflection.
4. **Revision rewrites only the unstarted tail** — never the current/executed
   stops, so memory, schedule, and the on-screen replay never desync.
5. **Generated stops are validated before they're committed** — place resolves to
   a known `Location`, `steps` is positive-or-None — caught in the planner, not
   the parser.
6. **The step loop is untouched.** Planning changes the *source* and *revision* of
   the schedule, not `advance()`/`perform_until`.

---

## 15. Open questions

- **Reflection coupling.** Periodic reflection (the other Phase D item) feeds
  planning by adding REFLECTION memories the day outline retrieves. Land it before
  or alongside `LLMPlanner`? (Build order §13 treats it as parallel.)
- **Multi-day runs.** Today's runs are ~3 hours. Day-level planning only fully
  matters across a day boundary ("plan today given yesterday"). Do we extend the
  default run, or have generation summarize a synthetic "yesterday" from the seed?
- **Cost.** A 25-agent day with three LLM calls per agent at wake + revisions is
  many calls. Lazy minute-decomposition (§4) helps; the usage ledger (#74/Phase A)
  already accounts for it. Worth a budget knob before scaling past 5 agents.
- **Conversation interplay (Phase E).** A conversation is the most natural
  revision trigger ("we agreed to meet at the pub at noon"). The revision seam
  (§8) is designed to accept it, but the dialogue itself is Phase E — keep the
  trigger generic so it plugs in later without reshaping the planner.
- **Where does wake time come from?** The upstream `lifestyle` field encodes
  sleep/wake rhythm. Parse it into a per-persona wake step, or keep the current
  "everyone starts at `--start`" simplification for the first pass?
```
