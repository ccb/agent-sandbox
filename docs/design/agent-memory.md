# Agent Memory Design

**Status:** Stages 1–4 implemented **and wired into the generative-agents
(Smallville) sim**, which **closes #75** (issue #75, PR #94); stages 5–8 remain
future work. The append-only memory stream, deterministic retrieval, event
perception, and action-outcome memories ship in `text_adventure_games/memory.py`
and `text_adventure_games/npc.py`; the Smallville port now perceives co-located
residents, remembers its own actions, and retrieves memories into each
observation (`backend/smallville_agents.py` +
`run_simulation.py`). The later stages — LLM importance scoring, reflection and
plan *generation*, and save/load through `Character` — are not built yet. See
**§12** for the per-stage status, and the **"As built"** notes (§4, §5, §9, §10)
for where the implementation refined this proposal.

**Source paper:** Park et al., "Generative Agents: Interactive Simulacra of
Human Behavior" (arXiv:2304.03442v2 / UIST 2023).

*A design for adding private, retrievable agent memory to the existing ReAct NPC
layer without changing the engine's action precondition gate.*

---

## 1. Why memory

Today an NPC can observe the current room, reason about one command, act, and
reflect on a failed command. That is enough for short ReAct demos, but not enough
for believable simulations over many turns. An agent that has no durable memory
will forget who it met, what it tried, what it learned, and what plans it was
following.

The Generative Agents paper solves this with three connected pieces:

1. A **memory stream**: an append-only list of natural-language records about
   what the agent experienced.
2. **Retrieval**: before deciding, select only the most useful memories by
   recency, importance, and relevance.
3. **Reflection and planning**: periodically turn raw memories into higher-level
   thoughts and plans, then store those as memories too.

For this repo, memory should make NPCs more coherent while keeping the code easy
for new contributors to understand and test offline.

---

## 2. Design goals

- **Private per-agent state.** One NPC's thoughts and memories must not leak into
  another NPC's observation prompt.
- **No action shortcuts.** Memory can influence what command an agent chooses,
  but every command still goes through `Parser.parse_command()` and the normal
  `check_preconditions()` -> `apply_effects()` gate.
- **Small first implementation.** Start with in-memory Python objects and
  deterministic retrieval. Do not require a vector database or persistent
  backend.
- **Mockable LLM use.** Importance scoring, semantic relevance, and reflection
  may use an LLM later, but tests must pass with `MockLlmClient`.
- **Readable records.** Memory records should be inspectable as plain text in
  tests, debug output, and save files.

Non-goals for the first pass:

- Cross-session persistence beyond the existing game save/load path.
- Global shared memory between agents.
- Long daily schedules for every NPC. That belongs after the time model and
  event system are stable.

---

## 3. Current repo fit

The repo already has most of the seams this needs:

- `text_adventure_games/npc.py` has `Agent.decide(observation)` and says memory
  is Phase 2.
- `react_behavior()` owns the Observe -> Act -> Reflect loop, so it is the right
  place to retrieve memories and write new observations.
- `Game.events` is an append-only event log. This should become the main source
  for "what did the agent perceive since last turn?"
- `parser.agent_reasoning()`, `parser.agent_action()`, and
  `parser.agent_reflection()` already keep private ReAct traces out of
  `command_history`. Memory should follow that privacy rule.
- `Game.describe_for(character)` already builds a character-specific current
  observation. Memory should add context around this observation, not replace it.

Important distinction:

- **Event log:** public-ish world facts about what happened.
- **Agent memory:** private records derived from what a specific agent perceived,
  inferred, or planned.

As built, the stream is also readable live over HTTP, one persona at a time:
`GET /agents/{name}/memory` (#298) — see `backend/README.md`, "The memory
stream", for the wire shape (a lean projection of §4's record).

---

## 4. Data model

Add a new module:

```text
text_adventure_games/memory.py
```

Suggested records:

```python
from dataclasses import dataclass, field
from enum import Enum


class MemoryKind(str, Enum):
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    PLAN = "plan"


@dataclass
class MemoryRecord:
    id: int
    kind: MemoryKind
    text: str
    created_turn: int
    last_accessed_turn: int
    importance: float = 1.0       # 1 to 10, paper-style
    actor: str | None = None
    source_event_ids: list[int] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    embedding: list[float] | None = None
    metadata: dict = field(default_factory=dict)
```

Suggested container:

```python
class AgentMemory:
    def __init__(self, owner: str):
        self.owner = owner
        self.records: list[MemoryRecord] = []
        self.last_seen_event_index = 0
        self.importance_since_reflection = 0.0

    def add_observation(self, text: str, turn: int, **kwargs) -> MemoryRecord:
        ...

    def add_reflection(self, text: str, turn: int, evidence_ids=None) -> MemoryRecord:
        ...

    def add_plan(self, text: str, turn: int, **kwargs) -> MemoryRecord:
        ...

    def retrieve(self, query: str, turn: int, max_records=6, token_budget=800):
        ...
```

`Agent` should gain:

```python
self.memory = AgentMemory(owner="")
```

The owner can be filled when `make_react_behavior()` first binds the agent to a
character.

> **As built:** the owner is bound lazily in both `react_behavior()` *and*
> `decide_and_route()` (the first time either runs for the agent), so the
> simultaneous resolve path — which reaches `decide_and_route()` without going
> through `react_behavior()` — also gets a correctly-owned memory.

---

## 5. Writing memories

An agent should write memories from three sources.

### A. Perceived world events

At the start of `react_behavior(character, game, agent)`, compare
`agent.memory.last_seen_event_index` against `game.events`.

For each new event:

1. Decide whether the character could perceive it.
2. Convert it to one short natural-language sentence.
3. Store it as an `OBSERVATION`.

Initial visibility rule:

- The agent remembers its own actions.
- The agent remembers events in its current location.
- The agent remembers events whose payload explicitly names it.

This is intentionally conservative. When `View.build(game, viewer)` lands, use
that instead of ad hoc visibility logic.

> **As built:** `AgentMemory.ingest_events()` keeps the co-located and
> payload-naming rules, but **skips the agent's own actions** here. An agent's
> own action is already captured — more richly, with its success/failure outcome
> — by §B below, so ingesting the matching `Game.event` too would only duplicate
> the record and double-count its importance.

> **Vision radius (issue #80).** The anticipated `View.build(game, viewer)` lands
> here as two method-based seams rather than a dataclass (the simpler, lower-surface
> realization — `View.build` can later seed off the first):
>
> - **`Game.perceivable_locations(character)`** — the spatial *visibility* seam, the
>   sight counterpart to `audience_for` (hearing). It returns the rooms a character
>   can see into: by default a BFS over room `connections` out to the character's
>   `vision_r` hops (0 ⇒ just the current room; blocks don't stop sight). A world
>   with its own geometry overrides this — Smallville maps its tile `vision_r=8`
>   here — and the memory layer is unchanged.
> - **`AgentMemory.perceive(game, character)`** — the single perception entry point,
>   called by every turn mode (sequential `react_behavior`, the simultaneous
>   `gather_intents`, and the Smallville `observe_and_decide`). It folds events
>   (radius-aware, via the seam above; `vision_r=0` is byte-identical to
>   `ingest_events`) **and** the agents/objects in view. Presence is **opt-in**:
>   only `vision_r > 0` records "I see X nearby" sightings, and only for things
>   *newly* in view (tracked in `AgentMemory._perceived`, keyed by kind/name/room,
>   capped per turn) so a stable neighbor isn't re-logged each turn. `describe_for`
>   stays room-only, so a wider radius widens *memory*, not the live room
>   description.
>
> Still open for the Smallville port: override `perceivable_locations` with
> `world_map.py` tile distance and read `vision_r` from each persona.

### B. Agent's own action outcome

After `_route()` succeeds, store a memory such as:

```text
I tried "take shovel" and succeeded.
```

After `_route()` fails and the Reflect step runs, store:

```text
I tried "attack player" but it failed because troll doesn't have a weapon.
```

This helps an agent avoid repeating the same failed command even when the parser
failure has fallen out of the immediate observation prompt.

### C. Reflections and plans

Reflections and plans are not public narration. They are private memories created
by the agent's reasoning layer.

Examples:

```text
The player keeps returning to the drawbridge, so they probably intend to enter
the castle.
```

```text
Plan: guard the drawbridge unless the player offers food or leaves.
```

---

## 6. Retrieval

Before an agent decides, build a query from:

- the current `game.describe_for(character)` observation,
- the agent's active goals,
- any reflected failure from this turn.

Score each memory with the paper's three ingredients:

```text
score =
    alpha_recency * recency
  + alpha_importance * importance
  + alpha_relevance * relevance
```

Default weights:

```python
alpha_recency = 1.0
alpha_importance = 1.0
alpha_relevance = 1.0
```

### Recency

Use exponential decay over turns:

```python
recency = decay ** max(0, turn - record.last_accessed_turn)
```

Start with `decay = 0.95`. The paper used a slower decay for sandbox hours, but
text-adventure turns are shorter and noisier.

### Importance

Normalize `record.importance` from 1-10 into 0-1:

```python
importance = record.importance / 10
```

Initial implementation:

- Hard-code action/outcome observations to low-medium scores.
- Let tests pass explicit importance values.
- Add LLM importance scoring later.

LLM-backed scorer, when enabled:

- Ask for a 1-10 "poignancy" or importance rating.
- Clamp invalid output into the 1-10 range.
- Fall back to `1.0` if the model returns nothing.

### Relevance

Default implementation (keyword overlap):

- Deterministic keyword overlap between the query and memory text.
- Strip common stop words.
- Return a 0-1 score.

Embedding implementation (issue #76, opt-in):

- A separate `EmbeddingClient` protocol (`embedding_client.py`), not a method on
  the LLM client — embeddings are a distinct provider axis (e.g. there is no
  Anthropic embedding endpoint).
- Embeddings are stored/cached on `MemoryRecord.embedding`.
- Cosine similarity, rescaled `(1 + cos) / 2` onto the keyword path's 0-1 scale.
- Opt-in: pass `AgentMemory(embedding_client=...)`; with none, relevance stays
  keyword overlap. Backends: model2vec (local, the default), sentence-transformers
  (local transformer), and OpenAI (hosted); plus a deterministic mock for tests.
  See `docs/design/memory-retrieval-embeddings.md`.

The first memory PR (#94) was deliberately not blocked on embeddings; they landed
right after, in #76.

### Prompt insertion

After retrieval, add a short memory block to the observation:

```text
Relevant memories:
- [observation, turn 3] The player gave me a fish.
- [reflection, turn 4] The player may be friendly if they offer food.
```

Then pass the augmented observation to `Agent.decide()`.

Only retrieved memories enter the prompt. The full memory stream should never be
dumped into the LLM context.

---

## 7. Reflection — implemented (#84)

Raw observations help with continuity, but reflections help with generalization.
The paper generates reflections when recent importance crosses a threshold. We use
the same idea at a smaller text-adventure scale, in `text_adventure_games/reflection.py`.

Trigger (`reflection.should_reflect`):

```python
if should_reflect(agent.memory, threshold):   # threshold = AgentConfig.reflection_threshold (30)
    reflect(agent.memory, agent.reflector, turn)
```

Reflection flow (`reflection.reflect`), the paper's loop:

1. Take the `recent_window` (default 50) most recent **lived** memory records.
   `PLAN` records are intentions, not experience — shown to a reflector they let
   an agent "remember" its own future (#777) — and they are filtered out *before*
   the window is sliced, so the seed stays `recent_window` wide.
2. Ask the `Reflector` for the salient questions they raise (capped at 3).
3. For each question, *retrieve* supporting memories — read-only (`touch=False`),
   so reflecting never disturbs decision-time recency, and with
   `exclude_kinds=("plan",)` so plans are dropped inside the retrieval ranking:
   each one's slot backfills with the next-best lived record instead of thinning
   the evidence set (#777).
4. Ask the `Reflector` for one short inference grounded in those memories.
5. Store each inference as `MemoryKind.REFLECTION` via `add_reflection`, with the
   supporting record ids as `source_event_ids`.
6. Reset `importance_since_reflection` (after adding, so the reflections' own
   importance doesn't immediately re-trigger).

The trigger matches what the pass can see: `AgentMemory._add` skips `PLAN`
records when accruing `importance_since_reflection`, so a plan-dense stretch
(#778 writes one commitment plan per conversation) can't fire a paid reflection
pass over evidence that hasn't moved. The plan guard is by *kind*, not tense: a
future commitment restated in a `CHAT` relationship note (#785 stores those as
chat precisely so reflection sees them) still reaches the reflector — tagging
inputs by tense (#777's option (b)) is the follow-up that would close that gap.

The cognition sits behind a `Reflector` protocol (mirroring `planning.py`'s
`Planner`): a deterministic `MockReflector` for offline/CI runs and an
`LLMReflector` (structured `call_tool` over the `LlmClient` seam) for live runs.

Reflection is **off unless a reflector is wired onto the agent** — with none, the
ReAct loop never reflects and behavior is byte-identical. It is wired into both
loops through `npc.maybe_reflect`: the engine `react_behavior` (via the `reflector`
arg on `make_react_behavior` / `make_hybrid_behavior`) and the Smallville step loop
(`run_simulation.simulate`, gated on `attach_agents(reflector_client=...)`, real
provider only). Tests (`tests/test_reflection.py`,
`generative-agents/tests/test_reflection_wiring.py`) cover the threshold and flow
with fake/scripted reflectors before any real model is involved.

This is the *additive* synthesis the issue scopes (the stream keeps growing). The
*subtractive* "dreaming" / compaction angle in #84's thread — consolidate aged,
low-importance, rarely-retrieved memories and evict the raw ones to bound the
stream — is a distinct, later capability that should reuse this summarization seam
and the #76 retrieval score to pick candidates.

---

## 8. Planning

Plans should be stored as memories, but planning can land after basic retrieval
and reflection.

For this engine, start smaller than the paper's day-level schedules:

- **Short-term plan:** 1-3 next intentions tied to current goals.
- **Location-aware plan:** include where the agent expects to execute it.
- **Revision-friendly plan:** failed actions or new observations can create a new
  plan instead of mutating the old one.

Example:

```text
Plan: stay near the drawbridge and warn the player before attacking.
```

Prompt rule:

- Retrieved plans can guide action choice.
- Plans do not schedule world mutations by themselves.
- The chosen command still has to pass parser preconditions.

When the time model is mature, plans can grow into clock-aware schedules with
start turns and durations.

---

## 9. Integration sketch

`react_behavior()` becomes:

```python
def react_behavior(character, game, agent: Agent, max_retries: int = 1) -> bool:
    if not agent.memory.owner:
        agent.memory.owner = character.name

    agent.memory.ingest_events(game, character)

    base = build_npc_context(character, game)
    relevant = agent.memory.retrieve(
        query=base,
        turn=game.turn,
        token_budget=800,
    )
    observation = format_observation_with_memories(base, relevant)

    game.parser.agent_observation(character.name, observation)

    for _ in range(1 + max_retries):
        command = agent.decide(observation)
        if not command:
            return False

        _log_decision(character, game, agent, command)
        if _route(character, game, command):
            agent.memory.add_observation(
                f'I tried "{command}" and succeeded.',
                turn=game.turn,
                importance=3,
            )
            return True

        failure_reason = getattr(game.parser, "last_fail_message", None) or "action failed"
        agent.memory.add_observation(
            f'I tried "{command}" but it failed because {failure_reason}',
            turn=game.turn,
            importance=4,
        )
        game.parser.agent_reflection(character.name, failure_reason)
        observation = _reflect(base, command, failure_reason)

    return False
```

> **As built:** `react_behavior()` does the Observe step (lazy owner-bind →
> `ingest_events()` → `retrieve()` → `format_observation_with_memories()`), but
> the **success/failure outcome memories live in `decide_and_route()`**, the
> Decide→Act→Reflect core shared by both the sequential loop and the
> simultaneous resolve path. That way an outcome is recorded once, regardless of
> turn mode. The failure sentence is worded `... but it failed because ...`
> (avoiding the `' failed:'` substring the mock troll brain keys on) so a private
> memory can never spoof another agent's decision.

Important privacy rule:

- Use `agent.memory.retrieve()` only inside that agent's own prompt.
- Never append memory records to `parser.command_history`.
- Never put `AGENT_REASONING` records into `Game.events`.

---

## 10. Save/load

The current behavior factory captures an `Agent` inside a closure, which makes
agent state hard to serialize. There are two reasonable paths:

### Short-term

Add `memory` to `Character`:

```python
character.memory = AgentMemory(owner=character.name)
```

`make_react_behavior()` then points `agent.memory` at `character.memory`. This
lets `Character.to_primitive()` serialize memory records while keeping the
existing behavior hook.

### Longer-term

Promote agents to first-class objects on characters:

```python
character.agent = LLMAgent(...)
```

Then `Character.to_primitive()` serializes `agent.memory`, persona, and goals,
while runtime-only fields like the LLM client are reattached after load.

Recommendation: use the short-term path for the first memory PR, and leave the
first-class `character.agent` refactor for the broader multi-agent loop work.

> **As built (stage 8 not done yet):** memory currently lives on the **`Agent`**
> (`agent.memory`), not on `Character`. `AgentMemory` and `MemoryRecord` already
> provide `to_primitive()` / `from_primitive()` round-trips (unit-tested), but
> they are **not yet wired into `Character.to_primitive()`**, so agent memory
> does not survive game save/load. Wiring that up is stage 8.

---

## 11. Testing plan

Unit tests:

- `MemoryRecord.to_primitive()` / `from_primitive()` round-trips.
- Recency decay decreases as turns pass.
- Importance normalization handles 1, 10, and invalid values.
- Keyword relevance returns higher scores for related text than unrelated text.
- Retrieval returns top records in deterministic order.
- Retrieval updates `last_accessed_turn`.
- Token budget limits the number of prompt memories.

Agent-loop tests:

- A ReAct NPC's prompt includes a relevant prior memory.
- A failed command is stored as memory and can affect the retry prompt.
- One NPC's memory never appears in another NPC's prompt.
- `parser.command_history` does not receive memory or private reasoning.
- Mock clients can exercise all paths without API keys.

Live-game tests:

- In Action Castle, the troll remembers that a previous bare `attack player`
  failed because it did not name a weapon.
- If the player gives the troll food, the troll can remember that friendliness
  and stop escalating in later turns.

---

## 12. Build order

| Stage | Status | Deliverable |
|-------|--------|-------------|
| 1 | ✅ Done | `memory.py` with `MemoryRecord`, `AgentMemory`, deterministic scoring, and unit tests (`tests/test_memory.py`). |
| 2 | ✅ Done | Add `Agent.memory`; retrieve memories into `react_behavior()` prompts. |
| 3 | ✅ Done | Ingest visible `Game.events` into per-agent observations (own actions excluded — see §5). |
| 4 | ✅ Done | Store action success/failure outcomes as memories (in `decide_and_route()`). |
| 5 | ⬜ Future | Add optional LLM importance scoring behind a mockable interface. |
| 6 | ✅ Done | Periodic reflection: threshold + memory synthesis in `reflection.py` (`should_reflect` / `reflect`, `Mock`/`LLMReflector`), wired into both loops via `npc.maybe_reflect` (#84). |
| 7 | ⬜ Future | Add simple plan memories (the `add_plan` writer exists; automatic generation does not). |
| 8 | ⬜ Future | Serialize memory through `Character.to_primitive()` / `from_primitive()` (`AgentMemory` already round-trips; the `Character` hook is unwired). |

Stages 1–4 ship in PR #94; each kept existing no-memory games working (the
empty-render guard means an agent with no memories produces a byte-identical
observation). The same PR also wires this engine memory into the
generative-agents (Smallville) sim — residents perceive co-located neighbors,
remember their own actions, and retrieve memories into each observation, while
the deterministic mock replay is unchanged (`generative-agents/tests/
test_memory_wiring.py`) — which **closes #75**. Stages 5–8 remain future work.

---

## 13. Open questions

- Should event visibility wait for a formal `View` object, or is the simple
  location-based rule good enough for the first PR?
- Should importance scoring be configured per game, or globally through
  `LLM_PROVIDER`?
- ~~Do we want embeddings in this package, or should relevance remain a pluggable
  strategy so games can choose their own backend?~~ Resolved (#76): pluggable
  `EmbeddingClient`, opt-in, with keyword overlap as the default.
- How should memory debug output be exposed: verbose agent trace, a `/memory`
  meta command, or tests only?

---

## 14. Design invariants

- Memory is context, not authority. The world graph remains the source of truth.
- Retrieved memory may influence a command, but only actions mutate the world.
- Private reasoning stays private.
- The first implementation must be useful without network access.
- The implementation should be obvious enough that a first- or second-year
  undergraduate can read, test, and extend it.
