# LLM Cost & Observability Design

**Status:** Partially implemented. Pieces **1 (usage capture)** and **3 (run
artifacts)**, plus the per-agent cost report, shipped in **PR #91** (closing
[#73] *[Phase A] LLM cost & token observability*). Pieces **2 (prompt caching)**
and **4 (deterministic runs / record-replay)** are **not built** — they were
scoped out of #73 as separate concerns (optimization and reproducibility) and
are tracked under their own follow-ups. See
[Implementation status](#implementation-status) for the detail.

*A design for measuring, reducing, and reproducing the cost of LLM-driven runs:
capture token usage on every call, turn on Anthropic prompt caching where it
pays off, write a per-run usage log, and make runs reproducible with a global
seed plus record/replay.*

---

## Implementation status

| Piece | Status | Where |
|-------|--------|-------|
| **1. Usage capture** — `Usage`, `CallRecord`, `UsageLedger`, `PRICES`, `price()`, `record_call()` | ✅ Shipped (PR #91) | `text_adventure_games/usage.py`; recorded in both `chat()` and `call_tool()` of every adapter in `llm_client.py` |
| **3. Run artifacts** — `RunLog` JSONL (header / call / summary); `LLM_LOG` + `LLM_LOG_PROMPTS` | ✅ Shipped (PR #91) | `usage.py`; wired via `client_from_env(run_log=...)` and the generative-agents backend |
| **Per-agent cost report** (build-order stage 7) | ✅ Shipped (PR #91) | `backend/run_simulation.py` (`_print_cost_summary`, via `reporting.py`) |
| **2. Prompt caching** | ⬜ Not built (out of scope for #73) | seam left: `AnthropicClient` still passes a plain-string `system`; `Usage` carries the cache fields and `price()` already applies the write/read multipliers |
| **4. Deterministic runs** (seed + `ReplayClient`) | ⬜ Not built (out of scope for #73) | seam left: `CallRecord.prompt_sha256` + `attempt`, and the full transcript under `LLM_LOG_PROMPTS`, are the replay keys/record |

**Decisions resolved while implementing (PR #91)** — these settle several of the
[open questions](#12-open-questions) below:

- **Attribution channel:** a mutable `client.context` attribute set before each
  `decide()`, *not* `chat()` kwargs — it works for both the engine ReAct path
  (`decide_and_route`) and the generative-agents direct-decide loop without
  touching the `LlmClient` Protocol.
- **Pricing source of truth:** a hard-coded `PRICES` dict in `usage.py`; an
  unknown model warns once and costs `$0` rather than crashing a run.
- **Verbose-transcript privacy:** numbers-only by default; full prompts/responses
  require `LLM_LOG_PROMPTS=1`.
- **Related fix (§5):** the default Anthropic model moved off the retired
  `claude-sonnet-4-20250514` to `claude-haiku-4-5`.

Anything below describing Pieces 2 and 4 (notably §6 and §8) is **design intent,
not current behavior**.

---

## 1. Why this matters

The engine calls an LLM once per acting NPC per round (twice when a command
fails and the ReAct loop retries). A simulation with 8 NPCs run for 50 rounds is
already 400-800 model calls, and the observation prompt grows as `Recent events:`
history accumulates. With real providers that gets expensive fast, and right now
we have no idea *how* expensive: `LlmClient.chat()` returns only the reply text
and throws the `usage` block away.

Three problems follow from that blind spot:

1. **Cost is invisible.** Nobody can answer "what did that run cost?" or "which
   NPC is burning the most tokens?" without instrumenting by hand.
2. **There is no lever to pull.** Anthropic prompt caching can cut the cost of
   the stable parts of a prompt by ~90%, but we don't emit `cache_control`, and
   we couldn't tell whether it was working if we did.
3. **Runs aren't reproducible.** Research on agent behavior needs a run you can
   re-create exactly. Today a run depends on un-seeded `random` calls and on
   whatever the model happened to sample that minute.

This design adds four connected pieces — **usage capture**, **prompt caching**,
**run artifacts**, and **deterministic runs** — built in that order so each one
stands on the measurements the previous one provides. The guiding rule: *you
can't optimize, or reproduce, what you don't measure.*

---

## 2. Design goals

- **Measure first, optimize second.** Authoritative token/cost numbers come
  before any caching change, so we can prove caching helped (or didn't).
- **Non-breaking by default.** `chat()` keeps returning `str | None`. Usage is
  captured on a side channel (a ledger the client owns), so `npc.py`,
  `llm_parser.py`, and existing tests don't change.
- **Provider-agnostic.** One normalized `Usage` record. The OpenAI and Anthropic
  adapters map their SDK's usage object into it; the mock provider reports zero
  cost.
- **Free and offline-testable.** Every path is exercised with `MockLlmClient` /
  `MockReActClient` — no SDK, no network, no API key.
- **Honest about determinism.** True bit-for-bit determinism is only achievable
  with the mock provider or via replay; we say so plainly rather than implying a
  seed makes a live model deterministic.
- **Readable for undergraduates.** Plain dataclasses, a JSONL log you can open in
  any editor, and a price table that's just a dict.

Non-goals for the first pass:

- A live cost dashboard or web UI. The artifact is a file; rendering it can come
  later (and should reuse the `reporting.py` renderer seam).
- Per-token streaming. We capture the `usage` block from the final response.
- Cross-provider cost parity or budget *enforcement* (hard stops). We report; a
  later issue can add a ceiling.

---

## 3. Current repo fit

The seams this needs already exist:

- `text_adventure_games/llm_client.py` defines the `LlmClient` Protocol
  (`chat()` + `count_tokens()`) and the `OpenAIClient` / `AnthropicClient` /
  `MockLlmClient` / `MockReActClient` adapters, plus `create_llm_client()` and
  `client_from_env()`. This is the single choke point every model call flows
  through — the right place to capture usage and add caching.
- `AnthropicClient.chat()` already splits the system message out into
  Anthropic's separate `system` parameter (`llm_client.py:163-189`). It calls
  `self._client.messages.create(**kwargs)` and returns `response.content[0].text`
  — **`response.usage` is discarded right there.** That one return statement is
  where accounting starts.
- `LLMAgent._system_message()` (`npc.py:155-170`) builds a *stable* system prompt
  per NPC: a shared opener (`"You are an NPC in a text adventure game."`),
  persona, goals, and `_DECISION_INSTRUCTION`. The per-turn `observation` is the
  user message. **Stable system + volatile observation is exactly the shape
  prompt caching rewards.**
- The engine is already nearly deterministic in its ordering: `turns.py`
  resolves NPCs by `initiative` with a *stable* sort (`resolve_order`,
  `turns.py:84-89`), and gather order is `game.characters` insertion order. The
  only un-seeded randomness in the engine today is `random.choice` in
  `actions/rose.py:128`.

What's missing is entirely additive: a usage record, a ledger, a price table, a
caching flag, a run object, and a log writer.

---

## 4. The four pieces

| Piece | Adds | Depends on |
|-------|------|------------|
| 1. Usage capture | `Usage` record + `UsageLedger` + cost table; adapters record each call | nothing |
| 2. Prompt caching | `cache_control` on the system prefix, gated by a config flag | 1 (to verify hits) |
| 3. Run artifacts | a per-run JSONL log: header, per-call records, summary | 1 |
| 4. Deterministic runs | a `Run`/seed object, engine RNG seeding, record/replay client | 1, 3 |

```text
   capture usage  ──►  prompt caching   (prove it fires via cache_read tokens)
        │
        ├──────────►  run artifacts     (cost + a full transcript on disk)
        │                   │
        └───────────────────┴──►  deterministic runs (seed + replay the transcript)
```

---

## 5. Piece 1 — Usage capture & token accounting

> **✅ Implemented in PR #91.** The shipped code follows this section closely; it
> also instruments `call_tool()` (the default NPC path), records via the shared
> `record_call()` helper, and adds a `"mock"` price entry so offline runs don't
> warn.

### Data model

Add a normalized record and a ledger to `llm_client.py` (or a small new
`usage.py` if `llm_client.py` gets crowded):

```python
@dataclass
class Usage:
    """Token usage for one chat() call, normalized across providers."""
    provider: str
    model: str
    input_tokens: int = 0            # uncached input, full price
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0   # written to cache (~1.25x input)
    cache_read_input_tokens: int = 0       # served from cache (~0.1x input)

    @property
    def total_input_tokens(self) -> int:
        # The full prompt size = uncached + cache writes + cache reads.
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


@dataclass
class CallRecord:
    """One LLM call, with enough context to attribute and replay it."""
    usage: Usage
    cost_usd: float
    turn: int | None = None
    actor: str | None = None          # which NPC, when known
    prompt_sha256: str | None = None  # hash of the messages (for replay keying)
    latency_ms: float | None = None


class UsageLedger:
    """Append-only log of CallRecords for one run, plus running totals."""
    def __init__(self):
        self.records: list[CallRecord] = []

    def record(self, rec: CallRecord) -> None:
        self.records.append(rec)

    def total_cost_usd(self) -> float: ...
    def totals_by_actor(self) -> dict[str, float]: ...
    def summary(self) -> dict: ...   # totals for the run footer
```

### Capturing usage in the adapters

The client gains an optional `ledger`. When present, `chat()` records into it.
This is the only change to existing callers — and they don't have to make it,
because the ledger defaults to one the client creates for itself.

```python
class AnthropicClient:
    def __init__(self, config, ledger: UsageLedger | None = None):
        ...
        self.ledger = ledger or UsageLedger()

    def chat(self, messages, max_tokens=256, temperature=0.0):
        ...
        response = self._client.messages.create(**kwargs)
        u = response.usage
        self.ledger.record(CallRecord(
            usage=Usage(
                provider="anthropic",
                model=self._model,
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0),
                cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0),
            ),
            cost_usd=price(self._model, ...),
        ))
        return response.content[0].text
```

Notes per provider:

- **Anthropic:** read `response.usage` (always present). The two cache fields are
  the proof that caching fired (Piece 2).
- **OpenAI:** map `response.usage.prompt_tokens` / `completion_tokens` onto
  `input_tokens` / `output_tokens`; cache fields stay 0 (different mechanism).
- **Mock:** record a `Usage` with zero tokens and zero cost. Tests can still
  assert that a record was *written* (one per call), which is how we test the
  accounting path offline.

### Cost table

A plain dict, prices in USD per 1M tokens. Cache writes cost 1.25× the input
price at the default 5-minute TTL (2× at 1 hour); cache reads cost ~0.1× input.

```python
# $/1M tokens: (input, output). Cache write = 1.25 * input (5m); read = 0.1 * input.
PRICES = {
    "claude-opus-4-8":   (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5":  (1.00,  5.00),
    # OpenAI models added as needed.
}

def price(model, usage: Usage, ttl="5m") -> float:
    pin, pout = PRICES[model]
    write_mult = 2.0 if ttl == "1h" else 1.25
    return (
        usage.input_tokens / 1e6 * pin
        + usage.cache_creation_input_tokens / 1e6 * pin * write_mult
        + usage.cache_read_input_tokens / 1e6 * pin * 0.10
        + usage.output_tokens / 1e6 * pout
    ) / 1.0
```

Unknown models cost `None`/0 with a warning rather than crashing a run.

### Counting tokens *before* a call vs accounting *after*

Keep these separate:

- **After a call**, the response's `usage` block is authoritative and free — this
  is what the ledger records. Always prefer it.
- **Before a call** (budgeting / `limit_context_length`), the existing
  `count_tokens()` heuristic (`len(text) // 4`) is a cheap estimate. Note that
  the OpenAI adapter's `tiktoken` count is **wrong for Claude** (it undercounts
  Claude tokens by 15-20%+). For accurate pre-call budgeting against a Claude
  model, use Anthropic's token-counting endpoint
  (`client.messages.count_tokens(model=..., messages=...)`) — but that's a
  network round-trip, so reserve it for budgeting decisions, not per-call
  accounting.

### Related fix (out of scope, but flag it)

The default Anthropic model is `claude-sonnet-4-20250514` (`llm_client.py:138`),
which is deprecated (retires 2026-06-15). The price table and caching minimums
are model-specific, so the default should move to a current model (e.g.
`claude-sonnet-4-6` for balanced NPC play, or `claude-haiku-4-5` for cheap
high-volume NPCs). Track this in its own issue; this design just assumes the
default is a current model.

---

## 6. Piece 2 — Anthropic prompt caching

> **⬜ Not implemented (out of scope for #73; tracked separately).** This is
> design intent. PR #91 left the seam in place: `AnthropicClient` still sends a
> plain-string `system`, and `Usage`/`price()` already account for the cache
> fields, so this plugs in here when picked up.

### The mechanic

Prompt caching is a **prefix match**: the cache key is the exact bytes of the
rendered prompt up to a `cache_control` breakpoint. Render order is
`tools → system → messages`. Put stable content first; any byte change in the
prefix invalidates everything after it. Cache reads cost ~0.1× input; the first
(write) request costs ~1.25× — so it pays off from the **second** identical-prefix
request onward (5-minute TTL).

### Where it plugs in here

`AnthropicClient.chat()` currently passes `system` as a plain string. Switch it
to the structured block form with a breakpoint, gated by a config flag:

```python
if config.enable_prompt_caching and system_text:
    kwargs["system"] = [{
        "type": "text",
        "text": system_text,
        "cache_control": {"type": "ephemeral"},   # 5-minute TTL
    }]
else:
    kwargs["system"] = system_text
```

That caches the **system prefix** (persona + goals + decision instruction). The
observation stays after the breakpoint, uncached, because it changes every turn.

### What actually gets cached in *this* engine

Two distinct opportunities, with different payoffs:

1. **Same NPC across turns (the real win).** An NPC's system prompt is stable
   turn to turn, so turn 2's call reads the system prefix that turn 1 wrote.
   Over a 50-round run that's one write and ~49 reads per NPC of the system
   block — *if the run stays within the cache TTL and the prefix clears the
   minimum size* (below).
2. **Shared boilerplate across NPCs.** The opener + `_DECISION_INSTRUCTION` is
   identical for every NPC, but it's small and currently sits *before* the
   per-NPC persona. To share it across NPCs you'd restructure `_system_message()`
   so the shared block comes first with its own breakpoint, then persona/goals.
   Worth doing for hygiene, but see the size caveat.

The per-turn `observation` (from `describe_for()` + the growing `Recent events:`
history) is **not** cacheable — it shifts every turn. As runs lengthen, the
observation, not the system prompt, becomes the dominant input cost. Caching
helps the stable part; trimming history and choosing a cheaper model help the
rest.

### The size caveat — measure before you celebrate

The minimum cacheable prefix is **model-specific** and larger than our prompts
may be:

| Model | Minimum prefix |
|-------|---------------:|
| Opus 4.8 / 4.7 / 4.6 / Haiku 4.5 | 4096 tokens |
| Sonnet 4.6 | 2048 tokens |
| Sonnet 4.5 | 1024 tokens |

A typical NPC system prompt — a few sentences of persona, a handful of goals, the
decision instruction — is likely a few hundred tokens, **below every threshold**.
Below the minimum, caching silently does nothing (no error; `cache_creation_input_tokens`
stays 0). So prompt caching may yield zero for short NPC prompts. This is *why*
Piece 1 comes first: the usage log tells us the real prefix size and whether
`cache_read_input_tokens` is ever non-zero. If it isn't, the lever to pull is
model choice / context trimming, not caching.

### Verifying hits, and silent invalidators

After a few rounds, check the ledger: if `cache_read_input_tokens` is 0 across
repeated calls for the same NPC, either the prefix is under the minimum, the TTL
expired between turns, or something is invalidating the prefix. Things that would
silently invalidate it (audit `_system_message()` against this list before
shipping):

- A timestamp, UUID, or turn number interpolated into the system prompt.
- Switching the model mid-run (caches are model-scoped).
- Non-deterministic serialization (e.g. `json.dumps` of a `set` without sorting).

Our current `_system_message()` is clean on all three. One *legitimate*
invalidation: when an NPC completes a goal, `_format_goals()` output changes, so
that NPC's system prefix changes and re-writes once. That's correct behavior, not
a bug.

### Concurrent calls (relevant to simultaneous mode)

A cache entry is only readable after the first response *begins streaming*. In
`turn_mode="simultaneous"`, NPCs decide against the same snapshot — but each NPC
has a *different* system prompt, so they don't share a prefix and there's no
fan-out cache benefit between them. The cross-turn win (opportunity 1) still
applies. No special handling needed for the first pass.

---

## 7. Piece 3 — Run artifacts

> **✅ Implemented in PR #91** as `RunLog` in `usage.py`. One refinement over the
> sketch below: call lines *stream* to disk as they happen (via a ledger hook
> installed by `RunLog.attach`) rather than being collected at close, so a crash
> mid-run still leaves a usable artifact.

A per-run log serves both masters: cost analysis *and* reproducibility (a full
transcript of what each agent was asked and answered).

### Format

One JSONL file per run, `runs/<timestamp>-<seed>.jsonl`, with three kinds of
line:

```jsonc
// 1. Header (first line): how to reproduce this run.
{"kind": "run", "seed": 1234, "provider": "anthropic", "model": "claude-sonnet-4-6",
 "git_sha": "ffde8b1", "started_at": "2026-06-10T19:30:00Z", "turn_mode": "sequential"}

// 2. One record per LLM call.
{"kind": "call", "turn": 3, "actor": "troll", "prompt_sha256": "9f2c...",
 "input_tokens": 412, "output_tokens": 18,
 "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
 "cost_usd": 0.00168, "latency_ms": 740,
 "messages": [...], "response": "Reasoning: ...\nAction: growl player"}

// 3. Footer (last line): totals for quick cost answers.
{"kind": "summary", "calls": 412, "total_cost_usd": 1.97,
 "by_actor": {"troll": 0.61, "guard": 0.55, ...},
 "cache_read_tokens": 0, "input_tokens": 169_000, "output_tokens": 7_400}
```

Storing the full `messages` and `response` makes the artifact a transcript, which
Piece 4 replays. If transcripts get large or sensitive, gate the verbose fields
behind a `LLM_LOG_PROMPTS` flag and always keep the usage/cost numbers.

### Writer

A small `RunLog` object opens the file, writes the header, exposes
`log_call(record, messages, response)`, and writes the summary on close (use it
as a context manager so the summary is written even if the run errors). It reads
from the `UsageLedger` rather than recomputing.

### Wiring without threading state everywhere

The cleanest seam is to give the *client* the ledger (Piece 1) and let a
run-level object own both the client and the `RunLog`. `client_from_env()` grows
optional knobs:

- `LLM_LOG=runs/` — directory to write the artifact (off if unset).
- `LLM_LOG_PROMPTS=1` — include full prompts/responses (default: numbers only).

`actor` and `turn` on each record need to reach the client. Two options: pass
them through `chat()` as optional kwargs (small, explicit signature change,
backward-compatible via defaults), or set a `client.context = {"actor": ..., "turn": ...}`
that `react_behavior()` updates before each `decide()`. The kwargs route is more
honest and is the recommendation; the attribute route avoids touching `chat()`'s
signature if we want it fully non-breaking.

---

## 8. Piece 4 — Deterministic runs

> **⬜ Not implemented (out of scope for #73; tracked separately).** This is
> design intent. PR #91 left the seam in place: every `CallRecord` carries a
> `prompt_sha256` and `attempt`, and the `RunLog` transcript under
> `LLM_LOG_PROMPTS` is exactly the record a future `ReplayClient` replays. No
> RNG seeding is wired in yet.

### What a seed can and can't do

A global seed makes the **engine** deterministic. It does **not** make a live
model deterministic — the Anthropic Messages API exposes no `seed`, and on the
newest models `temperature`/`top_p` are removed entirely (even `temperature=0`
never guaranteed identical output on older ones). So we split determinism into
two honest tiers:

1. **Engine determinism (the seed).** At run start, `random.seed(seed)`. This
   pins the only current engine RNG use (`actions/rose.py`) and any future
   tie-breaking, sampling, or shuffling. Ordering in `turns.py` is already
   deterministic (stable sort on `initiative`), so a fixed character set + seed
   gives a fixed turn order. The seed goes in the artifact header.

2. **LLM determinism (provider-dependent):**
   - **Mock provider** — deterministic by construction. `MockReActClient` reads
     the prompt and applies fixed substring rules. This is the reproducible-
     research backbone: `LLM_PROVIDER=mock` + a seed = a fully repeatable run,
     free and offline.
   - **Real providers** — not bit-reproducible live. Use **record/replay**: a run
     records every `(prompt → response)` in the artifact (Piece 3); a
     `ReplayClient` then satisfies each `chat()` from the recorded response keyed
     by `prompt_sha256`, with no network call. Seed + recorded transcript =
     exact replay of a real-LLM run, which is what reproducibility for research
     actually requires.

```python
class ReplayClient:
    """Replays recorded responses from a RunLog, keyed by prompt hash.
    Raises (or falls back to a wrapped live client) on a cache miss, so a
    diverging run is loud, not silently re-sampled."""
    def __init__(self, run_log_path, fallback: LlmClient | None = None): ...
    def chat(self, messages, max_tokens=256, temperature=0.0):
        key = sha256_of(messages)
        if key in self._responses:
            return self._responses[key]
        if self.fallback:
            return self.fallback.chat(messages, max_tokens, temperature)
        raise KeyError(f"no recorded response for prompt {key[:12]}")
```

A `Run` object ties it together: `seed`, `provider`/`model`, the client (with its
ledger), and the `RunLog`. `Game` takes an optional `run` and seeds RNG at start.

### Why a hash-keyed replay is enough

Because the engine is seeded and ordering is deterministic, the *sequence* of
prompts a replay produces matches the recorded run. If a code change alters a
prompt, its hash misses — and the loud failure tells you the run diverged, which
is exactly the signal you want. Optional later refinement: key by
`(turn, actor, attempt)` instead of/in addition to the hash, to tolerate cosmetic
prompt changes.

---

## 9. Integration sketch

```python
# client_from_env() grows usage/logging/caching knobs (all optional, all
# default-off so existing behavior is unchanged):
def client_from_env(run_log: "RunLog | None" = None) -> LlmClient | None:
    provider = os.environ.get("LLM_PROVIDER")
    if not provider:
        return None
    config = LlmConfig(
        provider=provider,
        model=os.environ.get("LLM_MODEL"),
        enable_prompt_caching=os.environ.get("LLM_CACHE", "").lower() in ("1", "true"),
        ...
    )
    ledger = UsageLedger()
    client = create_llm_client(config, ledger=ledger)
    if run_log:
        run_log.attach(ledger)   # summary reads from the ledger on close
    return client
```

`react_behavior()` / `decide_and_route()` set the per-call context (actor, turn)
before `agent.decide()`, so each `CallRecord` is attributed. Nothing about the
ReAct loop, the precondition gate, or the renderer changes.

Invariants this must preserve:

- `chat()` still returns `str | None`; usage rides the ledger, not the return.
- The mock providers stay free and deterministic, and every new path is testable
  with them.
- Turning off caching, logging, and seeding reproduces today's behavior exactly.

---

## 10. Testing plan

Unit tests (all offline, mock-only):

- `Usage.total_input_tokens` sums uncached + cache write + cache read.
- `price()` matches hand-computed costs, including the 1.25× write / 0.1× read
  multipliers and the 1h-TTL 2× write.
- `price()` on an unknown model warns and returns 0 rather than raising.
- `UsageLedger.totals_by_actor()` attributes cost to the right NPC.
- A `chat()` call through any provider appends exactly one `CallRecord`.
- The mock provider records a zero-cost `Usage`.

Caching tests (mock the Anthropic client's response object):

- With `enable_prompt_caching=True`, `system` is sent as a structured block with
  `cache_control`; with it off, `system` is a plain string.
- A fake response carrying `cache_read_input_tokens` flows into the ledger and
  the summary.

Artifact tests:

- `RunLog` writes a header line, one `call` line per call, and a `summary` line
  on close, and writes the summary even when the run raises.
- `LLM_LOG_PROMPTS` toggles inclusion of `messages`/`response`.

Determinism tests:

- Two `LLM_PROVIDER=mock` runs with the same seed produce identical artifacts
  (byte-for-byte, modulo timestamps).
- `ReplayClient` returns recorded responses for known prompts and raises on a
  miss (and falls back when a fallback client is supplied).
- Seeding `random` makes `actions/rose.py`'s scent choice repeatable.

---

## 11. Build order

| Stage | Status | Deliverable |
|-------|--------|-------------|
| 1 | ✅ PR #91 | `Usage`, `CallRecord`, `UsageLedger`, `PRICES`, `price()`; adapters record into an optional ledger. Unit tests. |
| 2 | ⬜ | `enable_prompt_caching` flag; `cache_control` on the system block in `AnthropicClient`. Tests that the block shape and ledger cache fields work. |
| 3 | ✅ PR #91 | `RunLog` (header / call / summary JSONL); wire `LLM_LOG` + `LLM_LOG_PROMPTS` through `client_from_env()`. |
| 4 | ⬜ | `Run`/seed object; `random.seed()` at game start; record full transcript. |
| 5 | ⬜ | `ReplayClient`; replay a recorded run with no network. |
| 6 | ⬜ | (Optional) restructure `_system_message()` so shared boilerplate is a leading cached block across NPCs; measure whether it clears the size minimum. |
| 7 | ✅ PR #91 | (Optional) a tiny report command that prints a run's summary, reusing the `reporting.py` renderer seam. |

Each stage keeps existing no-instrumentation runs working unchanged. Stages 1, 3,
and 7 shipped in PR #91; stages 2 and 4–6 (caching + determinism/replay) are out
of scope for #73 and remain as follow-ups.

---

## 12. Open questions

Resolved in PR #91:

- ~~**Attribution channel**~~ → a `client.context` attribute (not `chat()`
  kwargs); see [Implementation status](#implementation-status).
- ~~**Pricing source of truth**~~ → hard-coded `PRICES` dict.
- ~~**Verbose transcript privacy**~~ → numbers-only by default, full prompts via
  `LLM_LOG_PROMPTS=1`.

Still open (deferred with Pieces 2 & 4):

- **Replay keying:** prompt hash only, or `(turn, actor, attempt)` so cosmetic
  prompt edits don't break replay? (`CallRecord` already carries both.)
- **Where does the seed live?** On `Game`, on a new `Run` object, or read from
  `LLM_SEED` in the environment alongside the other knobs?
- **Should caching be on by default** once we confirm prefixes clear the size
  minimum, or stay opt-in?

---

## 13. Design invariants

- Measure before optimizing: authoritative `usage` from responses is the source
  of truth, not estimates.
- Accounting is a side channel: `chat()`'s contract (`str | None`) doesn't change.
- The mock providers stay free, offline, and deterministic — the backbone of
  reproducible runs and of every test here.
- A seed makes the *engine* reproducible; only mock or replay makes the *model*
  reproducible. Don't conflate the two.
- Caching is conditional, not magic: if the prefix is below the model's minimum,
  it does nothing, and the usage log is how we know.
- Off by default reproduces today's behavior exactly.
- The implementation should be obvious enough that a first- or second-year
  undergraduate can read, run, and extend it.
