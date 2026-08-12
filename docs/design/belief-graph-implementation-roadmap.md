# Belief graphs (Phases 1–2): implementation roadmap

Companion to [`belief-graph-memory.md`](belief-graph-memory.md) (the proposal —
read that first for the full rationale and literature). This doc is the
**"just the mechanism and database" slice** of that proposal, broken into
implementation chunks — Phases 1–2 of the original doc's build-order table,
deliberately stopping before Phase 3 (clustering) and Phase 4 (GraphRAG
retrieval), which stay future work.

**Status: none of this is built yet.** Confirmed by repo search: no
`belief_graph.py`, no `records_since`, no `last_aggregated_turn`, no
`maybe_build_beliefs` exist anywhere in the codebase. This is greenfield work
inside an established pattern, not a partial feature to extend.

## Two refinements over the original doc's sketch

1. **Edge-triggered, not polled.** The proposal sketches a per-tick poll for
   the `IS_SLEEPING` `False→True` transition, with a one-shot dedupe guard
   (`_already_aggregated_this_sleep`) to avoid re-firing every tick while
   asleep. But both existing `Sleep.apply_effects` implementations
   (Action Castle's and Penn's) set `IS_SLEEPING = True` at exactly one
   synchronous point — the transition *is* the action firing. Hooking
   directly into that call site needs no guard at all: the action only runs
   once per `sleep` command.

2. **Concepts/procedures are one graph, two views.** No need for two parallel
   mechanisms — the proposal's own `RelationKind` enum already splits this
   way: `PRECEDES` edges are the procedure graph (temporal order — "what
   comes first"); `IMPLIES`/`SUBSET_OF`/`SAME_AS` edges are the concept graph
   (logical relationships). Filter one graph two ways.

Everything below follows this repo's established "`Protocol` + deterministic
`Mock` + real LLM-backed implementation" pattern exactly, mirroring
`text_adventure_games/reflection.py`'s `Reflector`/`MockReflector`/
`LLMReflector` and its `should_reflect`/`reflect` free functions — the
proposal doc itself names this as the shape to mirror.

---

## Chunk 1 — Data model

**New file:** `text_adventure_games/belief_graph.py`

Implement the proposal's sketched dataclasses in full (it left methods as
`...` stubs):

- `RelationKind(str, Enum)`: `IMPLIES`, `PRECEDES`, `SUBSET_OF`, `SAME_AS`,
  `MENTIONS`.
- `BeliefNode` (`id`, `label`, `kind`, `source_record_ids`, `metadata`),
  `BeliefEdge` (`source_id`, `target_id`, `relation`, `confidence`).
- `BeliefGraph(owner)`: `add_node`, `add_edge`,
  `neighbors(node_id, relation=None)`, `to_primitive()` / `from_primitive()`
  — mirror `MemoryRecord`'s tolerant-of-missing-keys round-trip style
  (`memory.py`).
- Two additions beyond the proposal's sketch, both trivial given the above:
  - `to_adjacency_list() -> dict[int, list[tuple[int, RelationKind]]]` — the
    literal adjacency-list structure.
  - `concept_edges()` / `procedure_edges()` — thin filters over `self.edges`
    by `RelationKind`, giving the concepts/procedures split as two views.

No LLM, no new dependency.

**Tests** (`tests/test_belief_graph.py`, new): round-trip
(`to_primitive`/`from_primitive`), `neighbors`, the two view filters,
adjacency-list shape. All deterministic.

**Done when:** the test file passes with zero network access.

---

## Chunk 2 — Mock extraction pipeline

**Same file:** `text_adventure_games/belief_graph.py`

- `RelationExtractor` Protocol: `extract(records) -> list[tuple[BeliefNode, BeliefNode, RelationKind]]`
  — duck-typed on `.text`/`.id`/`.actor`/`.created_turn`, same style as
  `Reflector`'s duck-typed `records`.
- `MockRelationExtractor`:
  - `PRECEDES` between any two records ordered by `created_turn` (free —
    already in the data).
  - `SAME_AS` above a keyword-overlap threshold — reuse `memory.py`'s
    standalone `relevance_score(query, text) -> float` (`memory.py:229`,
    already used by `AgentMemory._relevance_by_id`) rather than
    reimplementing keyword overlap.
- `build_beliefs(memory, extractor, turn) -> list[BeliefEdge]`: orchestrator
  mirroring `reflection.reflect()`'s shape — pull
  `memory.records_since(memory.last_aggregated_turn)`, call
  `extractor.extract(...)`, fold results into `memory.belief_graph`
  (creating it on first use), advance `last_aggregated_turn`.

**Tests:** `MockRelationExtractor` produces correctly-ordered `PRECEDES` and
threshold-gated `SAME_AS`, deterministically — mirror
`test_reflection.py`'s Mock-determinism test shape.

**Done when:** `build_beliefs` run twice on an identical record stream
produces identical graphs.

---

## Chunk 3 — Wire into `AgentMemory` / `Agent`

**Existing files:**

- `text_adventure_games/memory.py`:
  - Add `records_since(turn) -> list[MemoryRecord]` to `AgentMemory`.
  - Add `last_aggregated_turn: int = 0` field.
  - Add `belief_graph: BeliefGraph | None = None` field.
  - Extend `to_primitive`/`from_primitive` to include it when present
    (`None` when absent → byte-identical primitive to today).
- `text_adventure_games/npc.py`:
  - Add `Agent.relation_extractor: RelationExtractor | None = None` (mirrors
    `Agent.reflector`).
  - Add `maybe_build_beliefs(agent, game, character=None) -> list`, placed
    near `maybe_reflect` (~line 1384), same guard shape (`if
    relation_extractor is None or memory is None: return []`), calling
    `belief_graph.build_beliefs(memory, relation_extractor, game.turn)`.

**No behavior change** for any existing agent — this only adds
fields/functions nothing calls yet.

**Tests:** `records_since` returns the right slice at turn boundaries;
`maybe_build_beliefs` is a no-op for an agent with no `relation_extractor`
configured (byte-identical to today).

---

## Chunk 4 — Trigger wiring at the fall-asleep transition

- `godot-generative-agents/backend/actions.py`, `Sleep.apply_effects`
  (currently lines 369–371, sets only `IS_SLEEPING = True`): call
  `maybe_build_beliefs(self.character.agent, self.game, self.character)`
  right after, guarded on `getattr(self.character, "agent", None)` being set
  (mirrors the existing `getattr(self.character, "agent", None)` guard
  already used in `WaitPenn.apply_effects` in the same file).
- `text_adventure_games/adventures/action_castle.py`, `Sleep.apply_effects`
  (currently lines 128–138): same call, placed right after
  `set_property("is_sleeping", True)` and *before* the `while` fast-forward
  loop begins — so it aggregates "yesterday" exactly once per sleep, before
  the night is fast-forwarded.

**Verify before writing:** check that adding an `npc.py` import into these
two action files doesn't create a circular import (`uv run python -c "import
..."` after the edit is enough to catch it; if it cycles, import
`maybe_build_beliefs` lazily inside `apply_effects` instead of at module
level).

**Optional, lower priority:** a day-boundary fallback (`SimClock`-based, for
worlds with no `Sleep` action at all) — real, per the original proposal, but
both games the user actually runs (Action Castle, Penn) already have a
`Sleep` action, so this can be deferred unless full Phase-1 parity with the
proposal doc is wanted.

**Tests** (`godot-generative-agents/tests/test_belief_graph_trigger.py`, new,
following this dir's flat `test_<feature>.py` convention): falling asleep
with a `relation_extractor` configured populates `agent.memory.belief_graph`
exactly once; falling asleep with none configured is a no-op; the Action
Castle sleep path aggregates before its fast-forward loop runs.

---

## Chunk 5 — Real LLM extraction

- `LLMRelationExtractor` in `belief_graph.py`, same shape as `LLMReflector`:
  a new tool schema (`CLASSIFY_RELATIONS_TOOL`, mirroring
  `SALIENT_QUESTIONS_TOOL`/`INSIGHT_TOOL`'s `{name, description, parameters}`
  shape in `reflection.py`) plus a new
  `text_adventure_games/prompt_templates/extract_relations_system.prompty`,
  calling `LlmClient.call_tool` exactly like `LLMReflector._call` does.
- **Batched, not pairwise:** one call per ~8–10 record batch asking "which
  pairs among these relate, and how" — the proposal doc explicitly flags
  naive pairwise extraction as O(n²) and names this as the mitigation to
  ship with, not defer.
- **Tests** via the same `_ScriptedClient` fake-client pattern
  `test_reflection.py` uses (canned `call_tool` responses keyed by tool
  name) — no real network call in CI.
- Update `prompt_templates/README.md`'s table and pin the new template's
  exact output in `tests/test_prompt_templates.py`, per this repo's explicit
  convention (see root `CLAUDE.md`) for any new/changed prompt.

---

## Explicitly out of scope for this roadmap

- **Phase 3 (community detection) and Phase 4 (GraphRAG retrieval)** — the
  user's own "later" scope. No `networkx`/`python-louvain` dependency needed
  yet.
- **Wiring `BeliefGraph` persistence into `run_store.py`.** Confirmed
  `AgentMemory.to_primitive()`/`from_primitive()` itself isn't wired into
  `run_store.py` yet (the proposal doc's own stage 8 is still open), so
  persisting belief graphs there would be building on a foundation that
  doesn't exist. `to_primitive`/`from_primitive` on `BeliefGraph` itself
  (Chunk 1) is still in scope — that's the "database" as an
  inspectable/round-trippable data structure, independent of where it's
  ultimately saved to disk.

## Critical files at a glance

| File | Change |
|---|---|
| `text_adventure_games/belief_graph.py` (new) | Chunks 1, 2, 5 |
| `text_adventure_games/memory.py` | Chunk 3 |
| `text_adventure_games/npc.py` | Chunk 3 |
| `godot-generative-agents/backend/actions.py` | Chunk 4 |
| `text_adventure_games/adventures/action_castle.py` | Chunk 4 |
| `text_adventure_games/prompt_templates/extract_relations_system.prompty` (new) + `README.md` | Chunk 5 |
| `tests/test_belief_graph.py` (new), `tests/test_prompt_templates.py` (addition) | Chunks 1, 2, 5 |
| `godot-generative-agents/tests/test_belief_graph_trigger.py` (new) | Chunk 4 |

## Verification (after each chunk)

```bash
uv run pytest tests/test_belief_graph.py godot-generative-agents/tests/test_belief_graph_trigger.py -v
uv run pytest tests/ godot-generative-agents/tests/ -q   # full regression, currently all green
```

End-to-end manual check after Chunk 4: run the existing mock-LLM Action
Castle or Penn flow through a sleep cycle
(`LLM_PROVIDER=mock uv run python -m notebooks.hw1_llm.play`, or the Penn
mock bake) and confirm `agent.memory.belief_graph` is populated after the
character sleeps, with zero crashes for agents that never configured a
`relation_extractor`.
