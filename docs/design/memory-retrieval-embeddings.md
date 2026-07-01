# Memory Retrieval — Embedding Models — Design & Implementation

**Status:** Implemented on a branch **stacked on PR #94** (#75), which owns
`text_adventure_games/memory.py`. Ships a pluggable `EmbeddingClient` with three
real backends — **model2vec** (local, the default), **sentence-transformers**
(local transformer), and **OpenAI** (hosted) — plus a deterministic **mock**, and
pure-Python cosine relevance wired into retrieval. Voyage and a raw-`transformers`
backend are left as future work behind the same seam. Stays a draft until #94
merges, then retargets to `main`. §3 keeps the full option survey that drove the choice.

**Issue:** #76 ([Phase B] Retrieval scoring: recency × relevance × importance +
inject into the observation). **Builds on:** PR #94 (#75) — lands
`text_adventure_games/memory.py` plus the recency / importance / injection wiring.
This work covers only the one piece #94 deliberately left as a placeholder:
**relevance via embeddings**.

*Pick an embedding model for the **relevance** term of memory retrieval — so each
decision pulls the memories that actually relate to the situation — while keeping
the default free, offline-testable, and friendly to a first/second-year audience.*

---

## 1. What #94 already shipped vs. what #76 still needs

Most of #76 is already in PR #94. `AgentMemory.retrieve()` in `memory.py` scores
every record and `react_behavior()` in `npc.py` already folds the top records into
the observation `Agent.decide()` sees. The current score:

```python
# text_adventure_games/memory.py (PR #94)
score = (
    ALPHA_RECENCY * recency_score(record, turn, decay)
    + ALPHA_IMPORTANCE * importance_score(record)
    + ALPHA_RELEVANCE * relevance_score(query, record.text)
)
```

| Term | Status in #94 | #76's job |
|------|---------------|-----------|
| recency | ✓ `recency_score` — exponential `decay ** (turn - last_accessed)` | leave as-is |
| importance | ✓ `importance_score` — 1–10 normalized to 0–1 | leave as-is |
| injection | ✓ `format_observation_with_memories()` appends the retrieved block | leave as-is |
| **relevance** | **placeholder** — `relevance_score()` is keyword overlap | **this plan** |

`relevance_score()` is honest about being a stand-in:

```python
def relevance_score(query: str, text: str) -> float:
    """Keyword overlap between *query* and *text* as a 0-1 fraction.
    ... A deterministic stand-in for the paper's embedding similarity
    that needs no model and no network."""
```

And `MemoryRecord` already carries the field where a real vector would live:

```python
embedding: list[float] | None = None   # unused in #94
```

So the seam is small and well-marked. The whole question of this doc is **what
fills that field, and how relevance is computed from it.**

The design doc `docs/design/agent-memory.md` anticipated this exactly — §6
("Relevance") says the LLM-backed path is to *"Add an embedding method to the LLM
client layer or a separate `EmbeddingClient` protocol… Use cosine similarity for
relevance. Do not block the first memory PR on embeddings."* — and §13 leaves it
as an open question: *"Do we want embeddings in this package, or should relevance
remain a pluggable strategy so games can choose their own backend?"* This plan
answers both: **pluggable strategy, embeddings opt-in, keyword overlap stays as the
zero-config default.**

---

## 2. Constraints that drive the choice

This is a teaching/research sandbox, not a production RAG system. The constraints
that actually matter here, in priority order:

1. **Free + no API key by default.** The audience is first/second-year
   undergraduates. The thing a student runs out of the box must not require a
   credit card or a key.
2. **Offline + deterministic for tests.** The whole suite must pass with no
   network and no key — the same invariant `MockReActClient` already guarantees
   for the LLM layer. Embeddings cannot break that.
3. **Light install.** `uv sync` should stay fast. A multi-hundred-MB dependency
   (e.g. `torch`) is a real cost for a student on a laptop and for CI.
4. **Fits the existing pattern.** `llm_client.py` already establishes a clean
   shape: a `Protocol`, per-provider adapters with **lazy** SDK imports, optional
   extras in `pyproject.toml`, and a `client_from_env()` factory. An embedding
   layer should mirror it, not invent a new style.
5. **Quality is secondary.** Memories are short, first-person snippets ("The
   player gave me a fish."), not long documents. Almost any modern embedding
   clears the bar; we are not chasing leaderboard MTEB scores.

Note that constraints 1–3 are about the *default a student gets*, not about
capability. The architecture below keeps the high-quality hosted models one env
var away — they're just not the default.

---

## 3. The options

Scored against the constraints above. "Determinism (tests)" means: does the
*offline test path* stay reproducible — for hosted APIs the answer is "no, so tests
use the mock," which is fine.

| Option | Cost | API key? | Offline? | Install weight | Dims | Quality | Determinism (tests) | Code |
|--------|------|----------|----------|----------------|------|---------|---------------------|------|
| **keyword overlap** (status quo) | free | no | yes | none | — | low | yes | trivial |
| **mock** (hash → vector) | free | no | yes | none | any | n/a | yes | trivial |
| **model2vec** (static, e.g. `potion-base-8M`) | free | no | yes | ~30 MB, numpy-only | 256 | good | yes (fixed weights) | small |
| **sentence-transformers** (`all-MiniLM-L6-v2`) | free | no | yes¹ | **heavy** (torch, ~hundreds of MB) | 384 | strong | yes (fixed weights) | small |
| **OpenAI** `text-embedding-3-small` | ~$0.02/1M tok | yes | no | SDK already an extra | 1536² | strong | no (mock in tests) | tiny |
| **Voyage AI** `voyage-3-lite` | low | yes | no | new `voyageai` dep | 512 | strong | no (mock in tests) | small |

¹ Offline *after* the first model download. ² `-3-small` supports shortening to
fewer dims; `-3-large` (3072d) is higher quality but overkill for one-sentence memories.

A few notes that aren't obvious from the table:

- **The "Anthropic" embedding path is Voyage AI.** Anthropic ships no first-party
  embeddings model and points users to Voyage. So even though the repo has an
  `AnthropicClient` for chat, an "Anthropic embeddings" adapter would really wrap
  the `voyageai` SDK + a `VOYAGE_API_KEY`. Worth stating plainly so nobody hunts
  for an endpoint that doesn't exist.
- **model2vec vs. sentence-transformers** is the crux of the free/offline tier.
  Both run locally with no key. model2vec distills a sentence-transformer into
  *static* token vectors (a lookup + mean-pool), so it needs only numpy — no
  torch, ~30 MB, millisecond inference on CPU. sentence-transformers is more
  accurate but drags in torch, which is the single heaviest thing we'd add to the
  project. For one-line memories the accuracy gap is small and the install gap is
  large.
- **keyword overlap doesn't go away.** It stays as the zero-dependency default and
  the test fallback. The point of #76 is to make embeddings *available*, not
  mandatory.

---

## 4. Decision (what shipped)

A **pluggable `EmbeddingClient`** with three real backends plus a deterministic
**mock**, and **keyword overlap retained as the default** when no client is configured:

- **Default real backend (free / offline / light): model2vec.** Best satisfies
  constraints 1–3 for the out-of-the-box student experience. Honest tradeoff: it's
  a newer library and its embeddings are a notch below full transformer models —
  but for short memory snippets that gap doesn't change which memories surface.
- **Opt-in local transformer: sentence-transformers** (`SentenceTransformerEmbeddingClient`,
  default `all-MiniLM-L6-v2`). Higher quality than model2vec; `.encode()` handles
  pooling/normalization. Tradeoff: pulls `torch` (a heavy install), so it's the
  `embeddings-st` extra, not the default.
- **Opt-in hosted: OpenAI** (`OpenAIEmbeddingClient`, default
  `text-embedding-3-small`). Reuses the existing `[openai]` extra; needs an API key
  + network. Cheap and strong for short snippets.
- **Tests / offline: the mock.** `MockEmbeddingClient` hashes words into a
  fixed-length count vector — deterministic, no deps, no network — so the whole
  suite exercises the embedding path with no model download.
- **Always-available fallback: keyword overlap.** If `EMBEDDING_PROVIDER` is unset
  (and no client is injected), relevance stays keyword-based exactly as #94 ships
  it. So the offline/deterministic invariant holds with no network.

Future, behind the same seam (Protocol + `EmbeddingProvider` enum + factory leave a
one-class slot for each):

- **Raw Hugging Face `transformers`.** A `TransformersEmbeddingClient` using
  `AutoModel` + manual mean-pooling (and optional L2 normalization), for users who
  want a specific model without the sentence-transformers wrapper. Deferred because
  sentence-transformers already covers the local-transformer case with far less
  pooling code to get subtly wrong.
- **Voyage AI** (`voyage-3-lite`) — the Anthropic-aligned hosted path (Anthropic
  ships no first-party embeddings). Deferred to avoid a new `voyageai` dependency.

Embeddings are therefore **strictly opt-in**: existing games and the whole test
suite behave identically until someone sets a provider (default `embedding_client=None`).

---

## 5. The API + seam (as built)

`text_adventure_games/embedding_client.py` mirrors `llm_client.py`:

```python
class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...   # batched

class MockEmbeddingClient:                # deterministic hashlib bag-of-words, no deps
class LocalEmbeddingClient:               # model2vec StaticModel; default potion-base-8M
class SentenceTransformerEmbeddingClient: # sentence-transformers; default all-MiniLM-L6-v2
class OpenAIEmbeddingClient:              # openai embeddings; default text-embedding-3-small
# (all SDKs lazy-imported with a clear ImportError; Voyage / raw-transformers: future)

def create_embedding_client(config) -> EmbeddingClient   # _PROVIDERS dispatch
def embedding_client_from_env() -> EmbeddingClient | None # reads EMBEDDING_PROVIDER,
    # EMBEDDING_MODEL/API_KEY/BASE_URL; None when unset or SDK missing -> keyword overlap.
```

`EmbeddingProvider(_StrEnum)` (`local` / `sentence-transformers` / `openai` / `mock`)
lives in `enums.py` alongside `LlmProvider`. The mock uses `hashlib` (not the
per-process-salted built-in `hash`) so vectors are stable across processes —
required for byte-identical replays and for embeddings written to save files.

Wiring into the scorer (`memory.py`):

- `AgentMemory.__init__(self, owner="", embedding_client=None)` stores the client.
- `retrieve()` calls a new `_relevance_by_id(query)` that **dispatches**: no client
  → today's keyword `relevance_score`; client set → embed the query once, lazily
  batch-embed any records missing `MemoryRecord.embedding` and **cache** the vector
  on the record, then score each by `(1 + cosine(query, record)) / 2` to rescale
  cosine ∈ [-1, 1] onto the keyword path's [0, 1] scale.
- `cosine_similarity()` is hand-rolled in pure Python (returns 0.0 on a zero
  vector), so `memory.py` keeps its no-dependency footprint — numpy stays out of
  the core engine.

Recency, importance, sort, token budget, and injection are untouched. The optional
`embedding_client` is threaded (default `None`) through `Agent`/`LLMAgent` and the
`make_react_behavior` / `make_hybrid_behavior` factories, the Action Castle
`build_game` + ReAct `build_llm_game`, the webapp, and the generative-agents
`attach_agents` / `simulate`.

Dependencies, following the `[openai]` / `[llm]` convention: `embeddings =
["model2vec"]` (the default; no numpy — cosine is pure Python) and `embeddings-st =
["sentence-transformers"]` (the heavier torch backend). The OpenAI backend reuses
the existing `[openai]` extra. Each is lazy-imported, so the base install stays lean.

---

## 6. Open questions

Resolved in this implementation:

- **Score normalization** — cosine ∈ [-1, 1] is rescaled to [0, 1] via
  `(1 + cos) / 2`, so all three ingredients share a scale under equal `ALPHA_*`.
- **numpy** — *not* added; `cosine_similarity` is pure Python, keeping numpy out of
  the core engine. (model2vec pulls numpy transitively, but only under the optional
  `[embeddings]` extra.)
- **When to embed** — lazily, on first `retrieve()`, caching the vector on
  `MemoryRecord.embedding` so chatty agents only embed memories that get scored.

Still open:

- **Provider fallback.** `EMBEDDING_PROVIDER` is an independent knob, *not* coupled
  to `LLM_PROVIDER` (an agent on `anthropic` chat has no Anthropic embedding
  endpoint to reuse). Revisit if that proves annoying in practice.
- **Reference scoring.** The "Generative Action Castle" prototype implements this
  exact scoring (the issue says to study it rather than reinvent — ask Chris).
  Confirm its relevance backend and weight choices against ours.
- **More backends.** A raw Hugging Face `transformers` client (`AutoModel` +
  manual mean-pooling) and a Voyage client are natural future additions — pure
  one-class additions behind the existing seam (see §4).
- **Embedding cost tracking.** The hosted OpenAI backend has no `UsageLedger`
  wiring yet (unlike the LLM client). Cheap at this scale, but worth adding if
  embeddings ever run at volume.

---

## 7. Status & follow-ups

Implemented on a branch **stacked on PR #94**, which owns `memory.py`:

- Stays a **draft until #94 merges**, then retargets to `main`. The default path
  (no embedding client) is byte-identical to #94, so the engine and
  generative-agents suites pass unchanged; new mock-driven tests cover the
  embedding path offline.
- Follow-ups: the hosted backends above, and validating weights/relevance against
  the reference prototype. The stable commitments: **embeddings are opt-in and
  pluggable, keyword overlap stays the default, the offline/deterministic test
  invariant is preserved, and the free local default is model2vec.**

**#76 shipped** (squash `beb062e0`). **Follow-up #102 — embeddings actually used in
the Smallville sim:** `backend/run_simulation.py` grew an
`--embeddings [PROVIDER]` flag (else `EMBEDDING_PROVIDER`, via
`resolve_embedding_client`) that threads a client into `simulate()`, degrading to
keyword overlap when unset or uninstallable — so the default run stays free, offline,
and CI-safe, and the exported replay is byte-identical (the mock brain ignores the
retrieved block). Because the replay can't *show* the difference until a real LLM
brain reasons over retrieved memories (NEXT-STEPS Phase A), the value is measured
**directly** by `backend/compare_retrieval.py`, which accrues a real per-resident
memory stream and prints keyword-overlap vs semantic top-k side by side. To keep that
comparison fair, `AgentMemory.retrieve()` gained a `touch=False` option for
**read-only** retrieval (score what would surface without bumping recency), so the
two relevance modes are compared over an identical recency/importance baseline.
