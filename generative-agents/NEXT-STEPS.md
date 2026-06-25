# Next steps: from replay demo to a proper Generative Agents simulation

This is the roadmap from **what runs today** — a replay-only visualization of 25
Smallville residents following hardcoded morning routines, driven by a deterministic
mock — to a **proper, full-fidelity Generative Agents simulation**: LLM-driven agents
that perceive their surroundings, remember what happened, plan their day, reflect, and
talk to each other, in the sense of Park et al., *Generative Agents: Interactive
Simulacra of Human Behavior* (UIST '23).

It expands the README's [Not done yet](README.md#not-done-yet-future-work) bullets into
ordered, dependency-aware milestones. Read this alongside
[`../docs/design/generative-agents-port.md`](../docs/design/generative-agents-port.md)
(the survey of the upstream world, cast, and cognitive loop this port builds on).

## How to read this doc

Every work item carries two markers:

- **Where the work lives**
  - `[engine]` — an improvement to the shared `text_adventure_games` library (one level
    up). Benefits every project on the engine, not just this port.
  - `[port]` — code specific to `generative-agents/` (the Smallville cast, the maze
    bridge, the exporter, the frontend).
- **Rough size** — `S` (a sitting), `M` (a few days), `L` (1–2 weeks), `XL` (a
  multi-week effort, usually its own design doc + PRs).

Most of the heavy lifting is `[engine]` work: the cognitive architecture belongs in the
library so other simulations and games inherit it. The `[port]` work is mostly wiring
Smallville's data and the frontend onto those new engine seams.

## Where we are vs. where we're going

The paper's agent runs a cognitive loop of **perceive → retrieve → plan → execute →
reflect** (plus **converse** on agent-to-agent contact). Here is each piece today:

| Cognitive step | Today | Target |
| --- | --- | --- |
| **LLM** | None — `SmallvilleMockClient` is deterministic (`backend/smallville_agents.py`) | Real model via `client_from_env()`; mock kept for tests |
| **Perceive** | Absent — agents never observe each other or events | Vision-radius perception writes nearby agents/objects/events to memory |
| **Retrieve** | Absent — no memory exists | Recency × relevance × importance retrieval feeds each decision |
| **Plan** | Hardcoded — one destination + one activity per persona (`build_world.py`) | Generated daily plan, decomposed day → hourly → minute |
| **Execute** | Two verbs (`travel`, `perform`) through the precondition gate | Same gate, richer action set targeting objects and other agents |
| **Reflect** | Skeleton only — `npc.py` reflects on command *failure*, not periodically | Periodic synthesis of recent memories into higher-level thoughts |
| **Converse** | ✅ Done (#86) — co-located agents run a turn-taking dialogue (`conversation.py`); each line lands in both memory streams (`MemoryKind.CHAT`) and on the replay's chat card. Gated on a real brain; mock replay unchanged | Co-located agents talk; both memory streams update |
| **Runtime** | Pre-baked: backend writes all movement JSON up front, Django replays it | Optional live mode: agents decide as the sim advances |

What we already have going for us (don't rebuild these):

- A **clean engine seam**. The port already drives every persona through the engine's
  real `Agent.decide()` → parser → precondition gate (`text_adventure_games/npc.py`),
  with `turn_mode="simultaneous"` (`text_adventure_games/turns.py`). Swapping the brain
  is a client swap, not a rewrite.
- The **upstream data we need for fidelity is on disk**: each persona's `scratch.json`
  (identity + cognition knobs — `vision_r=8`, retrieval weights, `recency_decay=0.995`),
  `spatial_memory.json` (the partial known-places tree), and
  `agent_history_init_n25.csv` (the pre-seeded relationships — "where social structure
  lives at t=0"). The associative memory ships empty by design; it accrues during a run.
- **Design docs already drafted** for most of the engine work — this roadmap points at
  them rather than re-specifying.

---

## Phase A — Get a real model into the loop

Goal: a real LLM makes the travel/perform decisions before we add any cognition, so
later phases build on a live model rather than the mock. Low risk, high momentum.

- `[port] S` ✅ **Done (#78) — Swap `SmallvilleMockClient` for a real client.**
  `run_simulation` now builds a real client from `LLM_PROVIDER` (anthropic / openai;
  unset or `mock` keeps the deterministic mock) and threads it through
  `simulate` → `attach_agents`, where it becomes each agent's decision brain. A
  `SmallvilleMockClient` stays on `agent.schedule` to pace the day
  (`advance`/`steps`/`emoji`), so when no provider is set the mock is *both* brain and
  driver and the replay is **byte-identical**. The same client also drives daily
  planning (`LLMPlanner`, Phase D). The real path is wired and unit-tested with a
  scripted fake client (`tests/test_llm_brain.py`); it has not yet been exercised
  against a live model end to end.
- `[engine] M` **LLM cost & token observability.** A 25-agent full day is thousands of
  model calls; we need per-agent / per-step token and dollar accounting before scaling
  up. Anchor:
  [`../docs/design/llm-cost-observability.md`](../docs/design/llm-cost-observability.md).
- `[port] S` ✅ **Done (#74) — Make sim parameters configurable.** Start time
  (`--start`, ISO), duration (`--steps`), and `SEC_PER_STEP` (`--sec-per-step`) are now
  CLI flags on `backend/run_simulation.py`; the exporter derives `start_date` from the
  passed `start_dt` so `meta.json` tracks the flag instead of a hardcoded constant.

---

## Phase B — Memory stream + retrieval (the foundation)

Goal: agents accumulate an episodic memory stream and retrieve from it when deciding.
**This is the deepest dependency** — perception, reflection, planning, and conversation
all read and write memory, so nothing downstream is meaningful without it.

- `[engine] L` **Append-only memory stream on `Agent`.** Timestamped events / thoughts /
  chats, each with an importance score. `npc.py:5` explicitly notes "memory is Phase 2";
  this fills that gap. Anchor:
  [`../docs/design/agent-memory.md`](../docs/design/agent-memory.md).
- `[engine] L` ✅ **Done (#76) — Retrieval scoring = recency × relevance × importance.**
  A pluggable `EmbeddingClient` (model2vec default, offline) scores the relevance term;
  `recency_decay` is already a persona knob. Wired into the sim by **#102**:
  `run_simulation --embeddings [PROVIDER]` (else `EMBEDDING_PROVIDER`), with
  `backend/compare_retrieval.py` measuring keyword-vs-semantic retrieval directly (the
  mock brain ignores the block, so the replay is byte-identical until Phase A's real
  brain). ROADMAP flags a clean reference implementation of exactly this scoring in the
  "Generative Action Castle" prototype (ask Chris) — study it rather than reinventing.
- `[engine] M` **Inject retrieved memories into the observation.** The string
  `Agent.decide(observation)` sees should include the top-scored memories, so the model
  reasons over its past, not just the current tile.
- `[port] M` ✅ **Done (#79) — Seed personas at t=0.** `attach_agents` now folds
  `agent_history_init_n25.csv` relationships into each agent's memory stream and surfaces
  each persona's *partial* known-places tree (`spatial_memory.json`) as beliefs in the
  engine's `Knowledge` layer (rendered into the "What you know:" observation section). The
  loaders live in `backend/seed.py` and tolerate the git-ignored assets being absent, so a
  fresh checkout / CI seeds nothing and stays byte-identical. Anchor:
  [`../docs/design/agent-knowledge.md`](../docs/design/agent-knowledge.md).

---

## Phase C — Perception + agent-to-agent interaction

Goal: agents become aware of each other and the world around them — the input side of
memory, and the precondition for conversation.

- `[engine] L` **Vision-radius perception.** Each turn, an agent perceives nearby
  agents, objects, and events within its radius and writes them to memory. Hook the
  engine's existing `Game.events` into this rather than inventing a parallel channel.
  (ROADMAP Phase 2: "structured observations".)
- `[engine] M` **Let actions target other agents.** Today actions default to targeting
  the player; agents need to act on each other for any social behavior to work.
- `[port] M` **Map Smallville proximity onto perception.** Translate the tile world
  (`vision_r = 8`, `backend/world_map.py`) into the engine's "who/what is nearby" query
  so co-location on the map means co-presence in the sim.

---

## Phase D — Planning + reflection

Goal: replace the fixed routine with generated, revisable plans, and let agents form
higher-level thoughts. This is the largest behavioral leap from today's demo.

- `[engine/port] XL` **Daily planning, decomposed day → hourly → minute.** Generate a
  plan from identity + memory, then refine it down to concrete actions, revising as the
  day unfolds. Replaces the single hardcoded `destination` + `activity` per persona in
  `backend/build_world.py`. This is the change that makes the town feel alive. Anchor:
  [`../docs/design/daily-planning.md`](../docs/design/daily-planning.md).
- `[engine] L` ✅ **Done (#84) — Periodic reflection.** A new engine
  `text_adventure_games/reflection.py` synthesizes recent memories into higher-level
  thoughts on a salience cadence: `should_reflect` fires once an agent's accumulated
  memory importance crosses `AgentConfig.reflection_threshold`, then `reflect()` runs
  the paper's flow (salient questions → retrieve supporting memories → one grounded
  inference each → append as `MemoryKind.REFLECTION` records citing their evidence →
  reset the accumulator). The cognition sits behind a `Reflector` protocol with a
  deterministic `MockReflector` (offline/CI) and an `LLMReflector` (real synthesis over
  the `LlmClient` seam), mirroring the `Planner` split. Wired into both loops via
  `npc.maybe_reflect`: the engine ReAct loop (`react_behavior`) and the Smallville step
  loop (`run_simulation.simulate`, gated on `attach_agents(reflector_client=...)`).
  **Off by default** — with no reflector wired on, reflection never fires and the mock
  replay stays byte-identical. This is the paper's *additive* synthesis; the
  *subtractive* "dreaming"/compaction angle (#84's thread) is a distinct, later
  capability sharing this summarization seam. Distinct from #4, which reflects only on
  command *failure*.
- `[port] M` **Time mapping.** Smallville is minute-level continuous time
  (`SEC_PER_STEP = 10`); our engine is discrete turns (`clock.py`). Define the mapping
  so plans expressed in clock time drive the right number of turns/tiles per step.

---

## Phase E — Conversation

Goal: when agents meet, they talk, and the conversation changes what they each remember.

- `[engine] L` ✅ **Done (#86) — Agent-to-agent dialogue seam.** A new engine
  `text_adventure_games/conversation.py` runs a turn-taking exchange between co-located
  agents: `converse(game, a, b)` alternates speakers, asking each for its next line via
  a new `Agent.converse` seam (`LLMAgent` fills a structured `speak` tool, with a
  free-text fallback; `ScriptedAgent` takes a `converse_rule`), and ends on a decline /
  wrap-up flag / `max_exchanges` cap. Every line is written into **both** participants'
  memory streams as the new `MemoryKind.CHAT` (speaker "I said…", listener "X said to
  me…") and delivered to the listener's `heard` buffer. Who may talk is the engine's one
  audibility seam (`Game.audience_for`), so a range/line-of-sight world constrains
  conversation exactly as it constrains a `Say`. Built on perception (Phase C: co-located
  agents already perceive each other's events into memory) and memory (Phase B).
- `[port] S` ✅ **Done (#86, verified #87) — Surface chat end to end.**
  `run_simulation.simulate` detects co-located, *settled* residents each step and runs
  `smallville_agents.maybe_converse` (cooldown-throttled), populating each frame's `chat`
  field with the dialogue as `[speaker, line]` pairs — the shape the frontend's existing
  (previously unused) `chat__<name>` slot ("Current Conversation" on the agent card)
  renders. **Gated on a real brain**: with the mock brain no utterance is produced, so the
  default replay holds no conversations and stays byte-identical. The exporter already
  writes the frame verbatim, so no exporter change was needed. #87 confirmed the full path
  and locked the export-boundary contract with a regression test
  (`test_exporter_surfaces_populated_chat`): a populated transcript survives into
  `movement/<step>.json` for both participants (the prior export test only covered the null
  case).

---

## Phase F — Live (non-replay) mode

Goal: run the sim interactively instead of pre-generating the whole thing.

- `[port] XL` **Step-by-step serving.** Have the backend serve the upstream
  `update_environment` endpoint — deciding one step at a time as the frontend advances —
  instead of pre-baking every `movement/<step>.json`. This is an architectural change to
  the backend ↔ Django boundary (currently a one-way file dump; see the diagram in
  [README — How it works](README.md#how-it-works)). Independent of B–E; it can land late,
  once the cognition is worth watching in real time.

---

## Cross-cutting / supporting work

Not a phase — do these alongside the relevant phase.

- `[port] M` **Grow the offline test suite.** `tests/` (with the synthetic-maze fixture)
  currently covers world build, pathing, and the export contract. Add coverage for
  memory, retrieval, planning, and conversation as each lands — and keep the deterministic
  **mock path working throughout** so CI stays free and offline.
- `[engine] M` **Structured observations + world-state export API.** A clean, typed feed
  of world state serves both this exporter and the future Godot renderer (ROADMAP
  Phase 2/3). Anchor:
  [`../docs/design/output-and-trace-rendering.md`](../docs/design/output-and-trace-rendering.md).

---

## Ordering & dependencies

```
A (real LLM) ──► B (memory + retrieval) ──► C (perception) ──► E (conversation)
                          │                      │
                          └────► D (planning + reflection)
                                                              F (live mode) — independent
```

- **A first** — get a live model deciding before adding cognition around it.
- **B is the gate** — memory + retrieval unblock C, D, and E; do it before anything that
  reads or writes memory.
- **C before E** — agents must perceive each other before they can converse.
- **D rides on B** — planning and reflection both reason over the memory stream.
- **F is independent** — live mode is a runtime change, not a cognition change; land it
  whenever, but it's most rewarding after B–E make the agents worth watching live.

This supersedes the README's "Not done yet" section as the working plan; that section can
shrink to a one-line pointer here once we start executing.
