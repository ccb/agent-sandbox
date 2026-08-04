# Belief Graphs: from flat memory to structured belief (proposal)

**Status:** Proposal, not built. Depends on and extends
[`agent-memory.md`](agent-memory.md) — read that first. Its stages 1–4 (the
memory stream, retrieval, event ingestion, action-outcome memories) and stage
6 (reflection, #84) are **done** and are this proposal's foundation. This doc
adds a new layer *on top of* that stream; it does not replace any of it.

**Relationship to the existing system, in one sentence:** `AgentMemory` is a
flat, append-only list an agent reads with a scored query
(`recency × importance × relevance`); this proposal periodically compresses
that list into a **graph of relationships between memories** (a "belief
graph"), then retrieves from the graph instead of — or alongside — the flat
list.

---

## Why this is a distinct layer, not a replacement

The current retrieval (`agent-memory.md` §6) is deliberately flat: score every
record independently, take the top-K. That is simple, testable, and has no
dependencies — exactly the repo's design goals. Its limit is that it can't
answer "why" or "what follows from what": it retrieves memories that *look*
relevant to the query text, not memories that are *logically connected* to
each other (Alice told Bob a secret → Bob is avoiding Alice → therefore Bob
probably knows something about Alice she doesn't want shared). That chained
inference is what turns raw observations into something worth calling a
**belief**, and it's what "agent drift" over a long-running sim erodes when
every decision is grounded in isolated flat retrieval instead of an
accumulated, connected world-model (Raieli & Iuculano, 2025, cited below).

This is genuinely new work — no relation-extraction, graph, or clustering
code exists in this repo yet. The plan below is staged so each phase is
independently useful and independently testable, following this repo's usual
Mock-first pattern (`Reflector`/`Planner`/`EmbeddingClient`): every new
capability gets a dependency-free, deterministic Mock implementation first,
and a real (LLM- or library-backed) implementation behind the same
`Protocol`, exactly like `reflection.py`'s `MockReflector`/`LLMReflector` and
`embedding_client.py`'s local/hosted backends.

---

## Phase 1 — Daily observation aggregation (the "sleep" trigger)

**Literature:** Park et al., "Generative Agents: Interactive Simulacra of
Human Behavior" (2023) — the memory stream itself. **Already built** as
`AgentMemory.records` (`text_adventure_games/memory.py`); this phase is only
about *when to aggregate*, not the storage format.

### What already exists

Every `MemoryRecord` already carries a `created_turn` and free-text `text` —
that *is* the "natural language memory object with a creation timestamp" the
proposal asks for. Nothing new needed here.

### What's new: the sleep trigger

The proposal's "sleep trigger" is not hypothetical in this codebase anymore —
this session added it. `godot-generative-agents/backend/actions.py`'s `Sleep`
sets `Property.IS_SLEEPING` when a character's `Property.IS_SLEEPY` flag is
set (itself flipped by `drives.accrue_energy` once energy crosses a
threshold — "an energy upkeep threshold is met", exactly as the proposal
names it). That state transition — `IS_SLEEPING` flips `False → True` — is
the natural aggregation trigger for Penn:

```python
# godot-generative-agents/backend/cognition.py, near maybe_reflect's call site
def maybe_build_beliefs(agent, game, character) -> list:
    """Aggregate today's memories into the belief graph when a character
    falls asleep. Mirrors maybe_reflect's shape (npc.py) but triggers on the
    IS_SLEEPING transition instead of an importance threshold -- the
    proposal's "sleep trigger", concretely: backend.actions.Sleep firing."""
    if not character.get_property(Property.IS_SLEEPING):
        return []
    if character.name in _already_aggregated_this_sleep:  # one-shot per sleep
        return []
    _already_aggregated_this_sleep.add(character.name)
    todays_records = agent.memory.records_since(agent.memory.last_aggregated_turn)
    ...
```

Action Castle has an equivalent: its own `Sleep` action already fast-forwards
through the night (`text_adventure_games/adventures/action_castle.py`); the
same aggregation call can sit in its `recover_and_wake_up` trigger.

A pure clock-based alternative (no `Sleep` action required, for games/worlds
that don't use one) is a day-boundary crossing via `SimClock`
(`backend/sim_clock.py`): compare `sim_clock.time_at(step).date()` across
ticks and fire once when it changes. Recommendation: support **both** —
`Sleep`-triggered where available (it's the more meaningful moment, since it
corresponds to the character's own experience of "the day is over"), falling
back to the clock boundary for worlds with no sleep mechanic at all.

### `AgentMemory` additions needed

```python
# text_adventure_games/memory.py
def records_since(self, turn: int) -> list[MemoryRecord]:
    """All records created after `turn` -- "today's observations"."""
    return [r for r in self.records if r.created_turn > turn]
```

Plus a `last_aggregated_turn` field on `AgentMemory`, mirroring
`last_seen_event_index`.

---

## Phase 2 — Building the belief (knowledge graph construction)

**Literature:** Hogan et al., "Knowledge Graphs: A Guided Tour" (2021) —
formal nodes-and-edges definitions this phase implements a small slice of.

### Data model

New module, `text_adventure_games/belief_graph.py`, following the same
dataclass style as `memory.py`:

```python
from dataclasses import dataclass, field
from enum import Enum


class RelationKind(str, Enum):
    IMPLIES = "implies"       # entailment: "if A then B"
    PRECEDES = "precedes"     # temporal order
    SUBSET_OF = "subset_of"   # set-theoretic hierarchy (an OWL-style "is-a")
    SAME_AS = "same_as"       # co-reference / same real-world entity or event
    MENTIONS = "mentions"     # an entity node <-> the observation node it came from


@dataclass
class BeliefNode:
    id: int
    label: str                                   # entity name, or observation text for leaf nodes
    kind: str                                     # "entity" | "observation" | "community"
    source_record_ids: list[int] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class BeliefEdge:
    source_id: int
    target_id: int
    relation: RelationKind
    confidence: float = 1.0  # the extractor's own certainty, 0-1


class BeliefGraph:
    """A Labeled Property Graph over one agent's memories -- observation and
    entity nodes, typed+confidence-scored edges. Mirrors AgentMemory's shape
    (owner-scoped, to_primitive()/from_primitive() round-trip) rather than
    reaching for a graph database: this is one agent's belief state, not a
    shared world graph, and stays small enough to live in memory."""

    def __init__(self, owner: str):
        self.owner = owner
        self.nodes: dict[int, BeliefNode] = {}
        self.edges: list[BeliefEdge] = []

    def add_node(self, node: BeliefNode) -> None: ...
    def add_edge(self, edge: BeliefEdge) -> None: ...
    def neighbors(self, node_id: int, relation: RelationKind | None = None) -> list[BeliefNode]: ...
    def to_primitive(self) -> dict: ...

    @classmethod
    def from_primitive(cls, data: dict) -> "BeliefGraph": ...
```

### Extraction: the `RelationExtractor` protocol

Mirrors `reflection.Reflector` / `planning.Planner` exactly: a `Protocol`,
a deterministic `Mock`, and an LLM-backed real implementation.

```python
from typing import Protocol


class RelationExtractor(Protocol):
    """Given today's memory records, propose entities and typed relations
    between them (or between existing belief-graph nodes and new ones)."""

    def extract(
        self, records: list["MemoryRecord"]
    ) -> list[tuple[BeliefNode, BeliefNode, RelationKind]]: ...


class MockRelationExtractor:
    """Dependency-free, deterministic. Two relations it CAN produce without
    an LLM, so tests and CI need no network/API key:
    - PRECEDES between any two records, ordered by created_turn (temporal
      order is free -- it's already in the data).
    - SAME_AS between two records whose keyword-overlap (memory.py's
      existing relevance_score) exceeds a fixed threshold.
    Entity/IMPLIES/SUBSET_OF extraction is where a real LLM is needed; the
    mock simply produces none of those, so a mock-only test suite still
    exercises the graph plumbing (add_node/add_edge/neighbors/persistence)
    without asserting on LLM-quality output."""

    def extract(self, records): ...


class LLMRelationExtractor:
    """Structured call_tool over LlmClient (the reflection.py precedent):
    one tool call per *pair* of recent records (or a batched call over the
    day's records, cost permitting) asking the model to classify the
    relation, if any, between them -- entailment, temporal order, or
    subset/same-set (the proposal's three logical relations). Returns
    (BeliefNode, BeliefNode, RelationKind) triples with the model's stated
    confidence."""

    def extract(self, records): ...
```

**Open design question, flagged rather than resolved here:** pairwise
extraction over a full day's records is O(n²) tool calls at the naive
implementation. Realistic mitigations (pick one before this ships): batch
several records per call (ask "which pairs among these 10 relate, and how"
in one tool call), or extraction only against nodes already in the graph
(new record → compare against existing nodes, not all past records
pairwise) once Phase 1 has run more than once.

### `AgentMemory` integration

`AgentMemory` gains an optional `belief_graph: BeliefGraph | None`, populated
by `maybe_build_beliefs` (Phase 1) calling the extractor and folding its
output in — same "off unless wired" opt-in shape as `reflector`/
`embedding_client`: an agent with no `relation_extractor` configured has no
belief graph, and behaves exactly as it does today.

---

## Phase 3 — Concept clustering (structure matching)

**Literature:** Bratanič & Hane, "Essential GraphRAG" (2025) — hierarchical
community detection to surface cross-cutting themes.

### Community detection: the `CommunityDetector` protocol

```python
class CommunityDetector(Protocol):
    def detect(self, graph: BeliefGraph) -> list[set[int]]:
        """Partition graph.nodes into dense clusters (node-id sets)."""
        ...


class MockCommunityDetector:
    """Dependency-free: connected components via BFS/union-find over the
    graph's edges, ignoring edge type. Not as sophisticated as Louvain/
    Leiden modularity optimization, but deterministic, O(n+m), and needs no
    new dependency -- the right default for tests and for a graph too small
    to need real community detection yet (most single-agent belief graphs,
    for a while)."""

    def detect(self, graph): ...


class LouvainCommunityDetector:
    """Wraps networkx + python-louvain (lazy-imported, `uv sync --extra
    graph` -- mirrors embedding_client.py's lazy-import-behind-an-extra
    pattern exactly). Real modularity-based community detection for graphs
    where connected-components is too coarse (one giant component)."""

    def detect(self, graph): ...
```

Add to `pyproject.toml`, next to the existing `embeddings`/`embeddings-st`
extras:

```toml
# Optional community detection for belief graphs (docs/design/belief-graph-memory.md).
# The engine falls back to connected-components (no dependency) when this
# isn't installed.
graph = ["networkx>=3.0", "python-louvain>=0.16"]
```

### Community aggregation (super-nodes)

Once a community is found, compress it into one summary node:

```python
def summarize_community(
    graph: BeliefGraph, node_ids: set[int], summarizer: "Reflector"
) -> BeliefNode:
    """Ask the same Reflector protocol reflection.py already defines for one
    short inference grounded in the community's member nodes' text --
    reusing the reflection seam rather than inventing a second summarization
    interface. The result becomes kind="community", linked to every member
    via a new MENTIONS-style edge (so the hierarchy is still just graph
    edges, not a second data structure)."""
```

This is deliberately built on the *existing* `Reflector` protocol
(`text_adventure_games/reflection.py`) instead of a new summarizer
abstraction — one fewer seam to test and explain, and it's already
LLM/Mock-split. The result is the "hierarchical memory tree" the proposal
describes: raw observations → belief-graph entities/relations → community
super-nodes → (recursively) communities-of-communities, each level just more
`BeliefNode`s of `kind="community"` pointing down at what they summarize.

**Testing note:** `MockCommunityDetector` + `MockReflector` together give a
fully deterministic, offline path through this entire phase — no graph
library, no network — for CI. That's the same bar `agent-memory.md`'s design
invariants set ("the first implementation must be useful without network
access").

---

## Phase 4 — Retrieval: GraphRAG with concept funnels

**Literature:** the "Synergized Bidirectional System" pattern (Atlan's guide
to combining knowledge graphs with LLMs) — retrieval that traverses relations
for connected context, not flat vector similarity alone.

### The `GraphRetriever` protocol

```python
class GraphRetriever(Protocol):
    def retrieve(
        self, graph: BeliefGraph, query: str, turn: int, token_budget: int = 800
    ) -> list[BeliefNode]:
        """Multi-hop: start from nodes the flat AgentMemory.retrieve() would
        already surface, then walk 1-2 edge hops (community membership,
        IMPLIES, PRECEDES) to pull in connected context flat retrieval
        would miss, budget-limited like the existing retrieval."""
```

### How this composes with the existing retrieval — not a replacement

`AgentMemory.retrieve()` (`agent-memory.md` §6) stays exactly as it is and
keeps being the default. `GraphRetriever` is an **additional, opt-in pass**:
when an agent has a `belief_graph`, `format_observation_with_memories()`
(`npc.py`) can append a second block —

```text
Relevant memories:
- [observation, turn 3] The player gave me a fish.

Related beliefs (from your longer-term understanding):
- [community] You believe the player is generally friendly toward you,
  based on 4 related memories from the last several days.
```

— rather than the graph retrieval replacing or reordering the flat list.
This mirrors exactly how embeddings (#76) were added as an opt-in relevance
strategy alongside keyword overlap, not a replacement for it: a persona with
no belief graph gets byte-identical prompts to today.

### Query planning

The "query planner" in the proposal is, concretely: given the current
observation text, (1) run the normal flat retrieval to get seed nodes/
records, (2) look up which community/communities those seed records belong
to in the belief graph, (3) include the community summary node(s) plus one
hop of their most-confident edges, capped by `token_budget`. No new "planner"
abstraction needed — it's a few lines of graph traversal composed from
Phase 2/3's data structures, not a new cognitive component.

---

## Build order (phased roadmap)

| Phase | Status | Deliverable | Depends on |
|-------|--------|-------------|------------|
| 0 | ✅ Done | Flat memory stream, scored retrieval, reflection (`agent-memory.md` stages 1–4, 6) | — |
| 1 | ⬜ Proposed | `AgentMemory.records_since`/`last_aggregated_turn`; `maybe_build_beliefs`, wired at the `Sleep` `IS_SLEEPING` transition (Penn) and Action Castle's `recover_and_wake_up`, with a `SimClock` day-boundary fallback for worlds with no sleep mechanic | Phase 0 |
| 2 | ⬜ Proposed | `belief_graph.py`: `BeliefNode`/`BeliefEdge`/`BeliefGraph`; `RelationExtractor` protocol + `MockRelationExtractor` (temporal + keyword-overlap only) + `LLMRelationExtractor` | Phase 1 |
| 3 | ⬜ Proposed | `CommunityDetector` protocol + `MockCommunityDetector` (connected components, no dependency) + `LouvainCommunityDetector` (`uv sync --extra graph`); `summarize_community` reusing the existing `Reflector` protocol | Phase 2 |
| 4 | ⬜ Proposed | `GraphRetriever` protocol; wire an opt-in "Related beliefs" block into `format_observation_with_memories` alongside (not replacing) flat retrieval | Phase 3 |

Each phase should land as its own PR, in order — Phase 2 is meaningless
without Phase 1's aggregation trigger, Phase 3 needs a graph to cluster, and
Phase 4 needs clusters to fetch. A partial build (say, just Phases 1–2) is
still useful and shippable on its own: a belief graph with no clustering is
already a richer structure than the flat stream, even before Phase 4's
retrieval catches up to use it.

---

## Testing plan

Following `agent-memory.md` §11's bar exactly — every phase must be testable
with **no network access and no API key**:

- **Phase 1:** `records_since` returns the right slice at record-count/turn
  boundaries; `maybe_build_beliefs` fires exactly once per sleep (not once
  per tick while `IS_SLEEPING` stays true), and never fires for a persona
  with no `relation_extractor` configured (byte-identical to today).
- **Phase 2:** `BeliefGraph.add_node`/`add_edge`/`neighbors`/
  `to_primitive`/`from_primitive` round-trip; `MockRelationExtractor`
  produces PRECEDES edges in the correct temporal order and SAME_AS only
  above its keyword-overlap threshold, deterministically.
- **Phase 3:** `MockCommunityDetector` finds the expected components on a
  small hand-built graph (a disconnected pair + a connected triangle should
  yield exactly two communities); `summarize_community` with a
  `MockReflector` produces a deterministic summary string.
- **Phase 4:** `GraphRetriever` with a mock graph returns the seed record
  plus its community summary, respects `token_budget`, and — critically —
  an agent with no belief graph gets the exact same prompt as before this
  feature existed (the same "empty-render guard" invariant `agent-memory.md`
  leans on throughout).

---

## Open questions

- **Cost of Phase 2's extraction.** Pairwise LLM relation extraction is
  expensive at scale (flagged above). Needs a concrete batching/scoping
  decision before Phase 2 ships for real (not just for the Mock path).
- **Graph size/pruning.** Nothing here proposes evicting old belief-graph
  nodes. A long-running persona's graph grows forever, same as the flat
  memory stream does today (`agent-memory.md` §7 notes eviction/"dreaming"
  as unsolved there too) — this proposal inherits that open problem rather
  than solving it.
- **Per-agent vs. shared beliefs.** This proposal keeps `BeliefGraph`
  strictly owner-scoped (private, like `AgentMemory`), matching
  `agent-memory.md`'s "no global shared memory between agents" non-goal.
  A shared/world-level belief graph (Atlan's "enterprise-scale" pattern) is
  explicitly out of scope here.
- **OWL ontologies for `SUBSET_OF`.** The proposal mentions OWL for
  hierarchical class definitions. A full OWL reasoner is almost certainly
  overkill for this repo's scale and audience; `SUBSET_OF` as a plain typed
  edge (no formal ontology, no reasoner) is the recommended starting point,
  revisited only if a concrete need for formal entailment shows up.

---

## Design invariants

Extending `agent-memory.md` §14's list:

- The belief graph is **derived from** the memory stream, never authoritative
  over it — `AgentMemory.records` remains the ground truth an agent can
  always fall back to.
- A persona with no belief graph configured behaves byte-identically to
  today (the same opt-in rule every memory feature in this repo follows).
- Every new cognitive capability (extraction, clustering, retrieval) ships
  behind a `Protocol` with a dependency-free, deterministic Mock — no phase
  requires network access or an API key to test.
- Graph nodes/edges must be inspectable as plain data in tests and debug
  output (`to_primitive()`), same as `MemoryRecord`.

---

## Relevant literature

**Cited per phase above, collected here for reference:**

- Park, J. S., et al. "Generative Agents: Interactive Simulacra of Human
  Behavior." UIST 2023 (arXiv:2304.03442). *The memory stream — already this
  repo's foundation, see `agent-memory.md`.*
- Hogan, A., et al. "Knowledge Graphs: A Guided Tour." 2021. *Formal
  nodes-and-edges definitions behind Phase 2's data model.*
- Bratanič, T. & Hane, O. "Essential GraphRAG." 2025. *Hierarchical
  community detection to capture cross-cutting themes — Phase 3.*
- Atlan. "The Complete Guide to Combining Knowledge Graphs with LLMs."
  *The "Synergized Bidirectional System" retrieval pattern — Phase 4.*
- Thambi, R. "The Empty Brain Hypothesis." 2025. *The "sleep" metaphor for
  digesting raw experience into internal models via detected knowledge gaps
  — motivates Phase 1's trigger design.*
- Raieli, S. & Iuculano, G. "Building AI Agents with LLMs, RAG, and
  Knowledge Graphs." 2025. *Knowledge graphs as persistent semantic memory
  against long-horizon "agent drift" — this doc's core motivation (see
  "Why" above).*
- Shinn, N., et al. "Reflexion: Language Agents with Verbal Reinforcement
  Learning." 2023 (arXiv:2303.11366). *Agents reasoning over their own past
  trajectories to improve future planning — this repo's existing
  `reflection.py` is already this idea in miniature; Phase 3's community
  summarization reuses that same `Reflector` seam rather than building a
  second one.*
