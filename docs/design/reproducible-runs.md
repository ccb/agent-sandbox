# Reproducible Agent Runs — Record, Replay & Deterministic Testing

**Status:** Proposal — not yet implemented. **Companion to**
`docs/design/planning-benchmark.md` (issue #47): the benchmark *scores* agent
runs; this doc is about making those runs **re-creatable**. No issue filed yet —
this is the plan to argue over before opening one.

*A way to record the whole agent response pipeline once, replay it offline and
for free, and pin every source of nondeterminism so the same run produces the
same result every time.*

---

## 1. Why

Three problems, one root:

- **A benchmark you can't re-run isn't a benchmark.** #47 reports whether an agent
  reached a goal in N steps. If the same task gives a different score each run, we
  can't detect regressions, compare models, or trust a number. Reproducibility is
  a prerequisite, not a nice-to-have.
- **Real model runs cost money and aren't deterministic.** We can't put live
  `anthropic`/`openai` calls in CI. Today's offline determinism comes from
  `MockReActClient` — but that's a hand-written brain **string-coupled to Action
  Castle** (its rules match `"i am the troll"`, `"guard the drawbridge"`, etc.).
  It won't generalize to new environments (the household sim) or tell us anything
  about how a *real* model plans. We want to record a real model **once** and
  replay it forever.
- **"What actually happened?"** When an agent fails a task we want the whole
  pipeline of that run saved — observation, prompt, raw response, parsed command,
  outcome — not just a pass/fail bit. That's what lets us debug a divergence,
  attach provenance to a score, or diff two runs.

---

## 2. Where the nondeterminism actually is

An honest inventory, so we know exactly what has to be pinned:

| Source | Where | Fix |
|--------|-------|-----|
| LLM sampling | `LLMAgent` runs at `temperature=0.7`; `llm_parser.py` at `1.0` (narration) and `0.0` (match) | record/replay (§4A); or pin temp=0 for benchmark runs |
| API variance | real providers vary even at temp 0 | record/replay (§4A) |
| Engine RNG | `actions/rose.py` → `random.choice(rose_smells)`, unseeded | seed it (§4C) |

Dict iteration is insertion-ordered (Py 3.7+), so character/location traversal is
already stable — but the determinism harness should *assert* that, not assume it.
The LLM is the big lever; the engine RNG is small but real and would silently
break a byte-identical replay.

---

## 3. The seam already exists

Every model call in the codebase — agent decisions **and** the LLM parser — goes
through one Protocol:

```python
class LlmClient(Protocol):
    def chat(self, messages, max_tokens=256, temperature=0.0) -> str | None: ...
```

And `MockLlmClient` already records every call:

```python
self.calls.append({"messages": messages, "max_tokens": ..., "temperature": ...})
```

So record/replay is a **thin wrapper around the Protocol** — no changes to
`npc.py`, the parser, or any game. A recording client delegates to a real one and
logs `(request → response)`; a replay client serves those responses back. This is
the well-trodden "VCR cassette" pattern (vcrpy / betamax), applied to `chat()`
instead of HTTP.

---

## 4. Three layers (separable; build independently)

### A. Cassettes — record / replay of LLM calls

```python
class RecordingClient:
    """Wraps a real LlmClient; behaves identically, and appends each
    (request, response) to a JSONL cassette as a side effect."""
    def __init__(self, inner: LlmClient, path: str): ...
    def chat(self, messages, max_tokens=256, temperature=0.0):
        response = self._inner.chat(messages, max_tokens, temperature)
        self._append({"request": {...}, "response": response})
        return response

class ReplayClient:
    """Serves recorded responses. No network, no API key."""
    def __init__(self, path: str, *, strict: bool = True): ...
    def chat(self, messages, max_tokens=256, temperature=0.0):
        return self._lookup(messages, max_tokens, temperature)
```

Design choices:

- **Matching: keyed, with ordered fallback.** Key each entry by a hash of the
  normalized request (messages + params). Keyed matching survives reordering —
  which matters in simultaneous mode (#25), where agents resolve in a non-fixed
  order. Pure FIFO ordering is simpler but brittle. Recommend keyed; keep an
  ordered index as a tiebreaker for identical requests.
- **Normalization** is the subtle part: observations embed turn numbers and recent
  events, so two "identical" decisions may differ by a timestamp. Define a
  normalization step (and document what it strips) up front.
- **Miss policy:** on a replay miss, either error (`strict=True`, for CI) or fall
  through to a real call and record it (`record-missing`, for incremental
  recording). Mirror vcrpy's record modes (`none` / `once` / `new_episodes`).
- Registering `RecordingClient`/`ReplayClient` alongside the existing providers in
  `_PROVIDERS` (or via `client_from_env()` flags) keeps wiring familiar.

### B. Run transcript — "save the whole pipeline"

The cassette captures only the model's I/O. The **transcript** captures the whole
Observe → Decide → Act → Reflect step and its outcome — one structured record per
agent step:

```python
@dataclass
class StepRecord:
    turn: int
    actor: str
    observation: str        # build_npc_context() output
    system_prompt: str      # persona + goals
    raw_response: str | None
    reasoning: str | None   # parsed "Reasoning:" line
    command: str | None     # parsed "Action:" line
    route_ok: bool          # parser precondition gate result
    fail_reason: str | None # parser.last_fail_message on failure
    world_delta: dict       # what changed (or a snapshot ref)
```

This is a **superset of the cassette** and the natural home for "re-create the
results." It builds directly on the existing trace machinery: `reporting.py`'s
`Message`/`Channel`/`Renderer` seam and the parser's `agent_reasoning` /
`agent_action` / `agent_reflection` channels already carry most of these fields.
The new piece is a `TranscriptRenderer` (or Channel) that serializes them to
JSONL — one transcript per run.

### C. Determinism harness — pin everything

```python
def seed_world(seed: int) -> None:
    """Pin every engine RNG. Today that's just random.seed(seed) for the
    rose action; new randomized actions must seed through here too."""
```

The contract the harness asserts:

```text
run(game, seed, RecordingClient) → cassette
run(game, seed, ReplayClient(cassette)) → byte-identical final world state
```

"Byte-identical" = equal `Game.to_primitive()` snapshots. That single assertion is
the regression test for the whole reproducibility story.

---

## 5. Provenance — the unit that makes a result re-creatable

A run reproduces iff you can pin **(game build + seed) + (cassette) + (code
version)**. Bundle that as a manifest stored next to each benchmark result:

```python
@dataclass
class RunRecord:
    game: str            # build id / module path (e.g. action_castle.build_game)
    seed: int
    cassette: str        # path + content hash
    engine_version: str  # git sha
    result: "TaskResult" # from #47's scorer
```

Replaying a `RunRecord` must reproduce its `result`. This is the object #47's
runner attaches to every score — so a benchmark number always comes with the
recipe to regenerate it.

---

## 6. Relationship to the existing save/load path

`Game.to_primitive()` / `from_primitive()` (and `save_game` / `load_game`) already
exist, but:

- they're **incomplete** — block deserialization is commented out, so save/load
  silently drops blocks (CLAUDE.md, known issues), and
- **agent state isn't serialized at all** — personas/goals (and Phase-2 memory)
  live inside behavior closures (see `agent-memory.md` §10).

These are a *different* capability and this plan must not block on fixing them:

- **save/load** = freeze and resume a game **mid-run**.
- **cassette + transcript** = reproduce a **whole run from the start**.

This plan needs the latter, which sidesteps the broken bits — a from-scratch
replay never deserializes a mid-run snapshot. The two converge later: the
`agent-memory.md` "promote the agent to `character.agent`" refactor would let both
mid-run saves *and* transcripts capture agent state cleanly. Note the dependency;
don't require it.

---

## 7. What this unlocks for testing

- **Real-model fixtures in CI.** Record one real `anthropic`/`openai` run, commit
  the cassette, replay it in CI — deterministic and free. The benchmark (#47) can
  then score *real* model behavior in CI, not just the mock brain.
- **Golden-transcript regression tests.** Assert a recorded run still produces the
  same commands and final world state. A prompt tweak or parser change that
  silently alters behavior shows up as a transcript diff.
- **`MockReActClient` stays** as the zero-fixture path; cassettes are the bridge
  from the hand-written mock to real models without paying per CI run.

---

## 8. Build order (tentative)

| Stage | Deliverable |
|-------|-------------|
| 1 | `RecordingClient` + `ReplayClient` (JSONL cassette, keyed matching, strict miss). Unit-tested with `MockLlmClient` as the wrapped "inner" client. |
| 2 | Commit one cassette fixture; a CI test replays a recorded Action Castle run fully offline. |
| 3 | `seed_world()` + a seedable rose action; the byte-identical record→replay assertion test. |
| 4 | `StepRecord` transcript Channel/Renderer (JSONL), reusing `reporting.py`; one transcript per run. |
| 5 | `RunRecord` manifest; wire it into #47's runner so each `TaskResult` carries its provenance. |
| 6 | (Stretch) golden-transcript regression test + a transcript-diff helper. |

Stages 1–3 deliver the core (record, replay, determinism) and are independently
useful even before #47 exists.

---

## 9. Open questions

- **Cassette matching & normalization:** keyed hash vs. ordered? What does the
  normalizer strip (whitespace, turn numbers, recent-events history) so a stable
  decision keys stably?
- **Where do cassettes live** — `tests/fixtures/cassettes/`? Committed, or
  git-lfs if they grow? (Prompts embed game text, not secrets, so redaction is
  light — just never record API keys.)
- **Granularity:** one cassette per run, or per `(provider, model, task)`? What's
  the re-record workflow when prompts change — an `LLM_RECORD=once|new|none` env
  flag mirroring vcrpy?
- **Transcript schema:** reuse `reporting.py`'s `Message` shape, or a dedicated
  `StepRecord`? JSONL vs. one JSON doc per run?
- **Seeding mechanism:** global `random.seed()` (simple, but leaky/global) vs.
  threading a `random.Random` instance through `Game` (clean, more plumbing).
  Lean global + documented for the first pass.
- **The LLM parser:** does its `temperature=1.0` narration path need recording
  too, or do we pin benchmark runs to a keyword-only / temp-0 parser so only agent
  decisions vary?

---

## 10. Design invariants

- **One seam.** Every model call goes through `LlmClient.chat`; record/replay
  wraps the Protocol and never special-cases a provider.
- **Replay is offline and free.** A replayed run touches no network and needs no
  API key — that's the whole point.
- **Recording is transparent.** A `RecordingClient` behaves exactly like the
  client it wraps: same return values, same `None`-on-failure, same token counts.
- **Separate sources of truth.** The cassette is authoritative for *what the model
  said*; the transcript for *what happened*; the world graph for *current state*.
  Neither cassette nor transcript mutates the world — only actions do (consistent
  with the precondition-gate invariant).
- **Readable.** Cassettes and transcripts are plain JSONL a first- or second-year
  undergrad can open, read, and diff.
