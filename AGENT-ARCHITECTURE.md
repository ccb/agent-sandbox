# Agent architecture — state of the system

What the generative-agents simulation in `godot-generative-agents/` **actually
does today**, as opposed to what the roadmaps propose. Written against
`1da413f7` (2026-07-24).

`README.md` says what the project is for. `ROADMAP.md` and `FEATURE-ROADMAP.md`
say where it's going. `godot-generative-agents/README.md` says how to *run* it.
This file says how it *works* and — the part that keeps getting lost — **which
features are switched on when you just press go.**

Every claim here is anchored to a `file:line` so you can check it. Line numbers
drift; the file and symbol names are the durable part. If a citation looks wrong,
trust the code and fix this doc.

---

## 1. Two layers, one rule

```
text_adventure_games/          the ENGINE — world, actions, memory, LLM clients
└── godot-generative-agents/
    ├── backend/               the SIM — cognition, planning, the tick loop, HTTP
    ├── godot/                 the VIEWER — Godot 4.6, reads a replay or the API
    └── web/                   a React companion (same API)
```

**The rule:** the sim composes the engine's *public* API and never forks it. The
engine owns `Character`, the `check_preconditions() → apply_effects()` action
gate, `AgentMemory`, `LlmClient`, reflection, and the ReAct seam. The sim owns
who decides when, the schedule, conversation pacing, and the frame format.

Where that rule bites: `sim_config.py:338` duplicates a ~20-line validator
rather than import the engine's private `config._build`. That duplication is
deliberate, and it's the shape of the whole boundary.

The engine can run agents on its own (`notebooks/hw1_llm/`, the Flask webapp).
Everything below is the *sim's* loop, which does not use the engine's
`Game.end_turn()` NPC loop at all — it drives `observe → decide` itself.

---

## 2. One tick, end to end

`run_simulation.step()` (`run_simulation.py:184`) is the spine. One call = one
10-second in-game tick. It does no I/O, no sleeping, no globals — it mutates
`state` and returns `(frame, chats_this_step)`. `simulate()` is a thin loop over
it for offline bakes; the live server (`PennStepper`) drives it tick-by-tick so
it can ship each frame the moment it exists.

```
game.turn = step_idx                        memory's time axis (run_simulation.py:288)
│
├─ PRE-PASS  (for each agent, before anyone decides)
│   ├─ behind-schedule trigger              new in-game hour AND still walking → replan (:310)
│   ├─ latch expiry → schedule.advance()    the ONLY place a stop advances (:317-355)
│   └─ collect `due`                        not walking, not settled, not conversing (:358)
│
├─ DECIDE   (all `due` agents, parallel under a real brain, serial otherwise)
│   └─ observe_and_decide()                 cognition.py:1082
│       perceive → retrieve → augment → decide
│
├─ RESOLVE  (serially, in `order` — so contention is deterministic)
│   ├─ accrue_thirst()                      opt-in per persona (:449)
│   ├─ parser.parse_command()               THE PRECONDITION GATE (:521)
│   ├─ on success: remember_outcome → score_new_memories → maybe_reflect (:523-534)
│   ├─ travel: walk_path() → one tile of movement (:553)
│   └─ on failure: remember failure → score → reflect → replan (DEVIATED) (:665-678)
│
├─ FRAME ASSEMBLY                           what the viewer renders (:703)
├─ maybe_react()                            perception interruption, OFF by default (:734)
└─ maybe_converse()                         co-located pairs talk (:747)
```

Two things worth internalizing:

**Decide is parallel; resolve is serial.** Under a real brain every due agent
decides concurrently against the *turn-start snapshot* (LLM latency is the whole
point), then effects apply one at a time in `order`. The engine's
gather → resolve simultaneous round is the semantic precedent. A decide that
outruns `--decide-timeout` (default 30 s) degrades to "idle this tick", and its
still-running call is parked so the agent is never asked twice at once — when it
lands, the answer is applied at the agent's *next* decision point rather than
thrown away, because discarding it would desync a stateful brain and pay twice.

**The gate is never bypassed.** Every decision, from any brain, becomes a
*command string* routed through `parse_command`. A model cannot do something the
action's preconditions forbid; it can only be told no and try again. This is why
typed per-verb tools (§5) were built to *emit command strings* rather than call
effects directly.

---

## 3. What an agent is

`cognition.attach_agents()` (`cognition.py:463`) is the assembly point. Each
persona gets one `LLMAgent` carrying:

| Part | What it is | Default |
| --- | --- | --- |
| `agent.llm_client` | the **brain** — decides actions | `ScheduleMockClient` (deterministic, free) |
| `agent.schedule` | day pacer — `destination` / `activity` / `steps` / `advance()` | always a `ScheduleMockClient` |
| `agent.memory` | `AgentMemory` stream | seeded at t=0 |
| `agent.plan` | `DailyPlan` of `Stop`s | from the authored schedule |
| `agent.knowledge` | beliefs (places) | seeded if assets present |

With no `llm_client`, **the brain and the schedule are the same object** —
`agent.llm_client is agent.schedule` — and the run is fully deterministic. That
identity is the switch the whole codebase gates on: `_use_action_tools()`
(`cognition.py:744`) asks "is the brain something other than the schedule
mock?", and if not, the real-brain-only paths never execute.

The mock brain is genuinely simple (`cognition.py:1-20`): *not at my
destination → `travel to <dest>`; there → `perform <activity>`.* It reads its
location off the first line of the observation the engine hands it, so the
decision really does flow through the observe → decide seam.

**Seeded at t=0:** a `PLAN` memory of the day's itinerary; one memory per
authored `relationships:` edge, from that persona's own side (#779); spatial
beliefs from the known-places tree, if the (git-ignored) bootstrap assets are
present.

---

## 4. Memory

Engine-side, `text_adventure_games/memory.py`. Four kinds (`memory.py:114`):
`OBSERVATION`, `REFLECTION`, `PLAN`, `CHAT`.

**Retrieval** (`memory.py:596`) scores every record and returns the top slice:

```
score = α_recency · decay^(turn − last_accessed_turn)
      + α_importance · (importance / 10)
      + α_relevance · similarity(query, text)
```

Defaults: all three weights `1.0`, decay `0.95`, at most **6 records** or **800
tokens** (`memory.py:44-53`), tunable per run via the `retrieval:` config
section. Relevance is keyword overlap unless you configure an `embedding:`
backend, in which case it's cosine similarity.

One behavior to know about: **retrieval bumps `last_accessed_turn`**, so
recency decays from *last recall*, not creation. A memory that keeps surfacing
keeps itself fresh. That's faithful to the paper and it is also the mechanism
behind a real failure mode (§11).

**Importance** is where the intent lives, and the constants matter more than
they look:

| Memory | Importance | Source |
| --- | --- | --- |
| presence ("X is here") | 1.0 | `memory.py:60` |
| a normal observation | 1.0 | `memory.py:324` |
| encounter (react's perceive pass) | 2.0 | `cognition.py:66` |
| chat line | 4.0 | `memory.py:364` |
| plan / reflection default | 5.0 / 6.0 | `memory.py:354`, `reflection.py:58` |
| relationship note, conversation commitment | **8.0** | `cognition.py:104` |

Under a real brain, `score_new_memories()` (`cognition.py:1362`) replaces those
constants with a batched LLM poignancy pass (1–10) — but **only for
`OBSERVATION` and `CHAT`**. `PLAN` and `REFLECTION` records keep their authored
importance. Records can also carry an `importance_locked` flag; note it is
*inert* on a `PLAN` record, since the kind filter excludes it first.

**Reflection** (`reflection.py`) fires when accumulated importance since the last
reflection crosses `reflection_threshold` (default **30.0**), synthesizing recent
memories into higher-level thoughts written back into the stream. It is a real
LLM call, so it only happens when a reflector is wired — i.e. under a real
provider.

---

## 5. Deciding

`observe_and_decide()` (`cognition.py:1082`) builds the observation in a
deliberate order, because **the mock brain reads only the first line** and the
byte-identical bake depends on that staying true:

1. `game.describe_for(char)` — location, exits, items, and *only the verbs this
   agent is actually offered* (#697).
2. Retrieve memories — using the **full** verb menu as the query, not the
   curated one, so changing what's offered can't shift which memories surface.
3. Append, always after the environment text: the decide-context block (sim
   time, current stop, minutes elapsed), a thirst line if flagged, and — real
   brains only — nearby tagged affordances.

Then one of two routes:

- **Typed per-verb tools** (`decide_with_action_tools`, `cognition.py:890`) for
  a real brain: one tool per verb, with slots typed and enumerated (travel's
  destination is an enum of real venue names, capped). The tool call is
  converted to a command string and sent through the gate. A decline or an API
  error falls through to route 2, so an outage degrades exactly as before.
- **The classic `agent.decide()` seam** for the mock and every fallback.

**Cognition tools** (`npc.py:471`, off by default): with them on, a brain may
call `recall` / `query_knowledge` / `read_plan` before acting, at most
`COGNITION_BUDGET = 2` calls per decision. Known tradeoff, deliberately left
lazy: the pushed "Relevant memories:" paste is *still* included, so a run pays
for both engine-pushed and agent-pulled retrieval.

**Pacing authority** (#581): the executed action owns duration. A model may
propose `duration_minutes`, clamped to 1–90; an authored `schedule.steps` is
trusted as-is. That asymmetry is what keeps the mock bake stable.

### The Penn verbs

All in `backend/actions.py`, all subclassing the engine's `Action`:

| Verb | Notes |
| --- | --- |
| `travel` | to a named location; drives pathfinding |
| `perform` | the workhorse; stamps `activity` from the model's own argument |
| `wait` | pacing slot |
| `talk_to` | *opens* a conversation; the talking itself is §7 |
| `study` | requires a `studyable` arena |
| `check_out_book` | requires a `book_shelf` |
| `read` | engine `Read`, Penn-flavored |
| `drink` | engine `Drink` + the sickness arc |

Affordances are location properties (`studyable`, `dining`, `book_shelf`)
authored in the world YAML. A verb is only *offered* where its affordance
exists — the invariant is offered ⇔ place-check.

---

## 6. Planning

`DailyPlan` is a list of `Stop(place, activity, steps, emoji, furniture)`.

- **`MockPlanner`** (`planner.py:36`, the default on a *free* brain) replays the
  authored schedule. Its `revise()` is `return plan` — a genuine no-op. **If you
  write a feature whose only consumer is `revise()`, it does nothing on a mock
  or scripted run.** That was the #778 bug.
- **`LLMPlanner`** (`planner.py:169`, the default under `--brain llm` since
  #787) plans a day in three passes: day outline → hourly → minute-level stops,
  validated against the world's real place names, falling back to the static
  schedule on anything unusable. Force the authored day back with
  `--plan schedule` — worth doing when you need the hand-tuned rendezvous
  overlaps, which a free-play generated day does not guarantee.

**Advancing a stop happens in exactly one place** — the latch-expiry pre-pass
(`run_simulation.py:317-355`) — and only when the completed activity was
*on-plan* (you were standing at the scheduled place). A deviation keeps the
pointer and just un-latches, so the scheduled stop is never silently skipped.
Since #778, a real conversation held at your scheduled place also counts as
having done that stop.

At the **final** stop, `advance()` returns False and the agent stays latched in
place for the rest of the run. That is intentional end-of-day behavior, and it
is load-bearing for the byte-identical bake — don't "fix" it.

Revision triggers: `BEHIND_SCHEDULE` (new hour, still walking), `DEVIATED`
(action failed the gate or happened off-plan, cooldown-guarded at 30 steps),
`CONVERSATION` (something was agreed).

---

## 7. Perception and conversation

**Perception** is `memory.perceive()` (`memory.py:380`): events others logged,
plus who and what is within `vision_r` **Chebyshev** tiles — default **8**
(`cognition.py:251`), measured on tile footprints (`tiled_game.py:102`,
`world_map.py:127`) and gated on `can_perceive`.

**Conversation** is the most heavily-mechanized part of the system.

```
maybe_converse()  cognition.py:1908
  ├─ pair up co-located, settled residents past their cooldown (can_converse)
  ├─ ONE line per tick via convo.exchange()   — a meeting spans ticks (#371)
  ├─ both agents pinned `conversing` (skips decide/movement/advance)
  ├─ end: cooldown stamped + the #582 outcome pass, per participant
  └─ playback HOLD: pair stays pinned 14 steps per transcript line, so the
     viewer can play the transcript back while they stand together (#673)
```

Pacing: at most **6 exchanges** per meeting, **90 steps** minimum between a
given pair's conversations — and their **Nth** conversation waits **N × 90**, so
repeats space out instead of re-opening the instant the window lapses (#803).

The **outcome pass** (`apply_conversation_outcome`, `cognition.py:1245`) asks
each participant's brain whether the conversation changed their plans. It
persists two things: a `relationship_note` (importance 8.0) and — since #778 —
the `commitment` as a `PLAN` memory (importance 8.0), written *before* the plan
revision so it survives a no-op planner.

**Critical, and easy to miss:** `conversation_enabled = llm_client is not None`
(`run_simulation.py:971`). **The pure-mock run never converses at all.** That's
why conversation features are byte-identical to the bake "by vacuity", and why
you cannot test them through the offline bake.

**React-or-continue** (`maybe_react`, `cognition.py:2194`, **off** by default):
when a walking agent newly comes into mutual sight of someone, it may spend one
bounded `react` call — continue / greet / replan — capped at 4 per sim hour with
a 90-step cooldown. Even with the consult off, the cheap perceive pass still
writes the encounter to memory.

---

## 8. What is actually ON by default

This is the table people come here for. Defaults for
`serve_penn.py` / `run_simulation.simulate()`:

| Feature | Default | How to turn on |
| --- | --- | --- |
| Brain | **mock** (free, deterministic) | `--brain llm` / `scripted` |
| Conversation | **off** — implied by the mock brain | any real brain |
| Daily planning | **auto** → `llm` under a paid brain, else **schedule** (authored, `revise()` is a no-op) | `--plan schedule` to force the authored day |
| Reflection | **off** — needs a reflector client | real provider |
| LLM importance scoring | **off** — needs a real brain | real provider |
| Cognition tools (`recall`, …) | **off** | `--cognition-tools`, config, or scripted brain |
| React interruption | **off** | `--react` or `cognition.react_enabled` |
| Parallel decide | **auto** → parallel only under a paid brain | `--decide-workers N` |
| Embedding relevance | **off** → keyword overlap | `embedding:` config section |
| Drives (thirst) | **off** — opt-in per persona | `thirst_rate` on a persona |
| Save run to store | **on** (`--persist`) | `--no-persist` |
| Request monitor | **on** | `--no-monitor` |
| Cost ceiling | none unless set | `--max-cost` / `llm.max_cost_usd` |
| `vision_r` | 8 tiles | config or scenario |
| Steps | 1200 (`serve_penn`) | `--steps`, `--endless` |

**So the honest summary of a default run:** deterministic mock brains walking an
authored schedule, with real perception and real memory retrieval, and **no**
conversation, planning, reflection, or scoring. Every "generative" behavior is
gated behind a real provider. That's not an accident — it's what keeps the
offline bake reproducible and free — but it does mean *most of the interesting
machinery is dark until you pass `--brain llm`.*

Feature flags resolve by **OR** across CLI, sim config, and engine config
(`_resolve_cognition_tools`, `serve_penn.py:198`): any surface can switch a
feature on, none can veto another.

---

## 9. Entry points

Three ways to run it, one shared store:

```bash
# 1. Offline bake → replay file (+ a store row unless --no-persist)
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py

# 2. Live server — the sim advances on its own and publishes frames
uv run python godot-generative-agents/backend/penn/serve_penn.py --tick-seconds 0.1
uv run python godot-generative-agents/backend/penn/serve_penn.py --brain llm --max-cost 1.00

# 3. Viewer — replay, or follow the live server
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```

Scenarios (`serve_penn.py:180`): `penn` (campus), `boil` and `boil_hard` (a
water-boiling experiment world; `boil_hard` pins `vision_r=0`).

**The HTTP seam** (`backend/api.py`, FastAPI) is what makes the frontends thin.
Roughly: `/world_state` and `/agents/{name}/{retrieval,knowledge,plan}` to
inspect; `/live`, `/events`, `/ws` to follow; `/pause`, `/resume`, `/reset` to
control; `/config` (GET/POST, gated to paused-at-step-0) to configure before
starting; `/runs/...` to list, replay, resume, re-run, delete; `/usage` for
spend, broken out `by_role` and `by_tool`. Loopback and unauthenticated by
default; a non-loopback bind requires `SIM_API_TOKEN`.

---

## 10. Reproducibility and cost

The load-bearing invariant of this codebase is that **the offline mock bake is
byte-identical across runs**, pinned by `test_bake_is_byte_identical` under 3
`PYTHONHASHSEED` values for both scenarios. Nearly every design decision above
that looks fussy — append context *after* the environment text, retrieve on the
full menu, trust authored `steps` but clamp model durations, gate real-brain
paths on brain identity — exists to protect it. **If a change touches the sim
loop, run that test.**

For real-LLM runs, `recording.py` wraps the *whole* client protocol in a
cassette (`RecordingClient` / `ReplayClient`, keyed per request and tagged by
method) alongside a seeded world, so a paid run can be replayed offline and
byte-identically re-run. `RunStore` (`run_store.py:76`) is the shared home:
SQLite for run rows plus JSONL for frames, events, wishes, and per-agent
memories. All three entry points save into `godot-generative-agents/runs/` by
default.

Cost: `UsageLedger` accumulates per-agent and per-role spend; `--max-cost` /
`llm.max_cost_usd` is a hard ceiling that ends the day when tripped (resets do
*not* clear spend). Per-role model tiering routes call sites (`decide`, `plan`,
`reflect`, `converse`, `outcome`, `score`, `react`) to different models.

---

## 11. Known gaps and rough edges

Honest list, as of `1da413f7`:

- **Most cognition is dark by default** (§8). Reading the code overstates what a
  default run does.
- **`MockPlanner.revise()` is a no-op**, so anything routed only through plan
  revision silently does nothing on a default run. This caused #778; check for
  other consumers before assuming a revision-triggered feature works.
- **Commitment memories never expire and self-refresh.** A `PLAN` memory has no
  completion, and retrieval bumps its recency, so a locked 8.0 commitment can pin
  itself near the top of the retrieved block indefinitely. Watched risk for the
  next live run: an agent chasing a commitment naming a place the world has no
  `travel` destination for → blocked → failure memory → repeat.
- **Conversation can't be tested through the bake** — the mock never converses,
  so those paths are byte-identical by *vacuity*, not by coverage. They need
  purpose-built offline tests with fake brains.
- **Save/load is incomplete** (engine-side): a loaded `Game.characters` lists only
  the player, and behaviors, triggers, and recipes are runtime-only and must be
  re-registered after a load.
- **`simulation.seed` is carried but unused** (`sim_config.py:67`) — reproducibility
  comes from the cassette plus `seed_world`, not this field.
- **Stale doc-comments.** `observe_and_decide`'s docstring still says "the default
  `vision_r == 0`"; the default has been **8** since #82. Treat prose comments as
  weaker evidence than constants.
- **Only three affordance tags exist** (`studyable`, `dining`, `book_shelf`) and
  `nearby_affordances_line` surfaces just the first two — the affordance system is
  real but thin.
- **`web/` and `godot/` overlap.** Two frontends read the same API; the Godot
  viewer is the maintained one.

---

## 12. If you're changing something

- **New verb** → subclass `Action` in `backend/actions.py`, set `ACTION_NAME`,
  implement `check_preconditions()` / `apply_effects()`. Never bypass the gate.
- **New LLM prompt _or agent-facing memory string_** → a `.prompty` in the right
  `prompt_templates/`, rendered via `render()`, **plus** a row in that directory's
  `README.md` table, **plus** a pinned-output test. Composed memory text counts;
  storing a model's raw string verbatim does not.
- **Touching the tick loop, cognition, or actions** → run
  `test_bake_is_byte_identical` before you push.
- **New per-agent state key** → add it to *both* initializers
  (`run_simulation.simulate` and `PennStepper._build`), and first check whether an
  existing key already means what you want.
- **Bug found in a live run** → its own issue, attached as a sub-issue of #760.

```bash
PYTHONPATH=.:godot-generative-agents uv run pytest godot-generative-agents/tests/ -q
uv run pytest tests/ -q
uv run black .
```
