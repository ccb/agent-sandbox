# Memory Retrieval — Embedding Models — Temp Plan

**Status:** Temporary plan / placeholder. Exploration of the *choice*, not a frozen
spec. Expected to shift to match PR #94's final memory API — no code lands until
that PR merges. This is the sketch to argue over.

**Issue:** #76 ([Phase B] Retrieval scoring: recency × relevance × importance +
inject into the observation). **Builds on:** PR #94 (#75) — lands
`text_adventure_games/memory.py` plus the recency / importance / injection wiring.
This plan covers only the one piece #94 deliberately left as a placeholder:
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

## 4. Recommendation

A **pluggable `EmbeddingClient`** with three real backends plus a deterministic
mock, and **keyword overlap retained as the default** when no client is configured:

- **Default (free / offline / light): model2vec.** Best satisfies constraints 1–3
  for the out-of-the-box student experience. Honest tradeoff: it's a newer library
  and its embeddings are a notch below full transformer models — but for short
  memory snippets that gap doesn't change which memories surface. If we'd rather
  bet on maturity over install size, `all-MiniLM-L6-v2` is the fallback choice, at
  the cost of pulling torch.
- **Opt-in high quality: OpenAI `text-embedding-3-small`.** One env var away. The
  `openai` SDK is already an optional extra, so this is the least *code* to add and
  the highest quality for anyone who has a key. `text-embedding-3-large` is
  available but unnecessary here.
- **Opt-in (Anthropic-aligned): Voyage `voyage-3-lite`.** For teams already on the
  Anthropic stack who want a hosted embedding to match.
- **Always-available fallback: keyword overlap + mock.** If `EMBEDDING_PROVIDER` is
  unset, relevance stays keyword-based exactly as #94 ships it. Tests use the mock
  (or the unset path) so the offline/deterministic invariant holds with no network.

Embeddings are therefore **strictly opt-in**: existing games and the whole test
suite behave identically until someone sets a provider.

---

## 5. Proposed API + seam (direction, not contract)

Mirror `llm_client.py`. Sketch:

```python
# text_adventure_games/embedding_client.py  (new)

class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...   # batched

class MockEmbeddingClient:      # deterministic hash -> fixed-dim vector, no deps
class LocalEmbeddingClient:     # model2vec (default) or sentence-transformers; lazy import
class OpenAIEmbeddingClient:    # wraps openai SDK (already lazy-imported elsewhere)
class VoyageEmbeddingClient:    # wraps voyageai SDK  (the "Anthropic" path)

def embedding_client_from_env() -> EmbeddingClient | None:
    # reads EMBEDDING_PROVIDER / EMBEDDING_MODEL / EMBEDDING_API_KEY;
    # returns None when unset -> caller falls back to keyword overlap.
```

Wiring it into the existing scorer is a few lines:

- Give `AgentMemory.__init__` an optional `embedding_client=None`, stored on the
  instance.
- Add an optional arg to relevance so the keyword path stays the default:

  ```python
  def relevance_score(query, text, embedding_client=None) -> float:
      if embedding_client is None:
          return _keyword_overlap(query, text)        # today's behavior
      return cosine_similarity(embedding_client.embed([query])[0],
                               embedding_client.embed([text])[0])
  ```

- Cache the vector on the field that already exists — `MemoryRecord.embedding` —
  so each record is embedded once, not on every `retrieve()`.
- Add a small `cosine_similarity()` helper. (numpy is the obvious tool but is *not*
  currently a core dependency — see open questions.)

The only edit to the hot path is the one argument threaded into the existing
`ALPHA_RELEVANCE * relevance_score(query, record.text)` line in `retrieve()`.
Everything else (recency, importance, sort, token budget, injection) is untouched.

Extras would grow by one or two entries, following the existing `[openai]` /
`[anthropic]` / `[llm]` convention — e.g. `embeddings-local = ["model2vec", "numpy"]`
and reuse `[openai]` for the hosted path.

---

## 6. Open questions

- **Score normalization.** Keyword overlap is `[0, 1]`; cosine similarity is
  `[-1, 1]`. Mixing them under the same `ALPHA_RELEVANCE` weight is apples to
  oranges. Rescale cosine to `[0, 1]` (e.g. `(1 + cos) / 2` or clamp at 0), or
  retune the alphas per backend?
- **numpy as a hard dep vs. extra.** Cosine wants numpy, but it's currently only
  used in `generative-agents/`, not the core engine. Add it to `[embeddings-local]`
  only, promote it to a core dep, or hand-roll cosine in pure Python for the engine?
- **When to embed.** On `add_observation`/`add_reflection` (pay up front, every
  memory), or lazily on first `retrieve()` (pay only for memories that are ever
  scored)? Lazy is cheaper for chatty agents.
- **Provider fallback.** Should `EMBEDDING_PROVIDER` default to `LLM_PROVIDER`, or
  stay an independent knob? (An agent on `anthropic` chat can't reuse it for
  embeddings — there's no Anthropic embedding endpoint — so coupling them is leaky.)
- **Reference scoring.** The "Generative Action Castle" prototype implements this
  exact scoring (the issue says to study it rather than reinvent — ask Chris).
  Confirm its relevance backend and weight choices before we lock ours.

---

## 7. Why this is a temp plan

This work edits `memory.py`, which **PR #94 owns and hasn't merged**. Starting now
would mean rebasing onto a moving file and risking conflicts on the very function
(`relevance_score`) and field (`MemoryRecord.embedding`) we'd change. So:

- **No code until #94 merges.** This PR is the plan doc only.
- Expect §5's signatures to shift to match #94's final API (arg names, where the
  client is threaded). The stable commitments are the ones worth arguing over now:
  **embeddings are opt-in and pluggable, keyword overlap stays the default, the
  offline/deterministic test invariant is preserved, and the free local default is
  model2vec.**
