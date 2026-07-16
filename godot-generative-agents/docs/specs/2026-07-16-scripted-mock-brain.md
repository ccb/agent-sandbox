# Spec: Full-feature mock brain — a scripted, key-free Penn brain + end-to-end coverage test (issue #563)

**Track:** godot-ga-main (backend-only, per #399 fold-in).
**Date:** 2026-07-16

## Problem

The Penn sim's offline mock brain (`ScheduleMockClient`, `backend/cognition.py:69`)
is a solid deterministic driver for **movement + schedule + retrieval**, but every
code path gated on a real `llm_client` is **dark** under it — which is exactly the
half of the backend we've grown most recently (the plural tool loop + per-verb typed
tools #356/#485, tool-result validation #357, cognition tools #358/#512, reflection,
real conversation / `chat` memories, emergent social edges). Both offline runners
(`generate_penn_replay.py`, `serve_penn.py --brain mock`) drive the cast with **no**
`llm_client`, so none of that ever executes offline, and there is **no end-to-end test
that would catch it drifting**. `test_replay_contract.py` checks frame *shape* only
(`extra="forbid"`); nothing asserts the mock actually *populates* chat, reflection, the
tool loop, cognition tools, or relationships. A regression in any of those could ship
without one offline test going red.

This matters now because the #579 cognition epic (brain-authoritative pacing #581,
conversation consequences #582, scored importance #583, believability eval #584) lands
squarely on these gated paths. Without an offline brain that reaches them, that work is
only testable against a paid provider.

## Root cause — the gate is identity-based (and load-bearing)

The path that lights up the gated surface is `_use_action_tools`
(`backend/cognition.py:473`):

```python
brain is not None and brain is not agent.schedule and hasattr(brain, "call_tools")
```

and `attach_agents` wires (`cognition.py:345`):

```python
brain = llm_client if llm_client is not None else schedule
```

So with no client supplied, **the brain *is* the `ScheduleMockClient` object** (one
object is both brain and pacing driver), and `brain is not agent.schedule` is false by
construction. The identical `llm_client is not None` gate also controls the reflector
(`cognition.py:358`) and conversation (`run_simulation.py`). That identity is
**deliberate and load-bearing**: it is what keeps the default bake byte-identical
(the determinism suite depends on it).

**Consequence for the design:** extending `ScheduleMockClient` in place *cannot* open
the gate — it is `agent.schedule`, so the check stays shut and touching it risks the
byte-identical bake. The brain that reaches the gated paths **must be a distinct
object**. This settles the "extend vs. add alongside" question the issue left open.

## Approach (decided): a scripted brain alongside — `--brain scripted`

Promote the existing `MockLlmClient` (`text_adventure_games/llm_client.py:981`) into a
third `--brain` option. It already speaks `chat` / `call_tool` / `call_tools`, records
zero-cost `Usage` into a ledger, and is already used as a tool-calling stand-in in
`test_cognition_wiring.py` / `test_per_action_decide.py`. Driven by a deterministic
**Penn responder callable**, it becomes a distinct `llm_client` object — so the gate
opens and every `llm_client`-gated path runs, offline, with no keys and no spend.

Two constraints shape the responder, both pointing the same way:

- **Pure function of the prompt.** The responder decides from `(messages, tools)` only
  — never from call order or instance state. The client is *shared across all
  personas* and #366 decides them in parallel, so any call-counter would interleave
  nondeterministically. This is also the honest discipline: a real brain sees only the
  prompt, and the #580 context block (sim time / current stop / elapsed) plus the
  offered tool enum already carry everything the responder needs.
- **It need not reproduce the mock bake byte-for-byte.** That is `ScheduleMockClient`'s
  job and stays untouched. `--brain scripted` is a *new, separate* option whose only
  contract is: emit valid, deterministic tool calls that drive the loop through every
  gated branch. Determinism is required (same run → same frames); equivalence to
  `--brain mock` is explicitly **not**.

### Components

1. **`resolve_llm` third outcome** (`serve_penn.py:83`). Today it returns `None`
   (mock) or a `dict` (llm). Add a `"scripted"` sentinel outcome and the CLI choice
   (`--brain` choices become `("mock", "scripted", "llm")`, `serve_penn.py:680`). Like
   `mock`, `scripted` requires no key, no model, no `--max-cost`.
2. **Stepper wiring** (`PennStepper.__init__`, `serve_penn.py:320`). When the resolved
   brain is `scripted`, build `self.llm_client` and `self.reflector_client` as
   `MockLlmClient`s wired to the deterministic responders (recording into the same
   `self.ledger`) instead of `create_llm_client`. `cognition_tools` defaults **on**
   under scripted so the cognition-tool path is exercised. `_build` re-applies on every
   reset, unchanged.
3. **Bake wiring** (`generate_penn_replay.py:196`). The same brain-construction seam so
   `generate_penn_replay.py --brain scripted` bakes a replay that exercises the gated
   paths. `--brain mock` (default) stays the byte-identical bake.
4. **The Penn responder** (new module, e.g. `backend/penn/scripted_brain.py`), a set of
   pure callables:
   - **decide** `(messages, tools, tool_choice, …) -> ToolCallResult`: read the current
     location and the current/next stop out of the prompt's context block; choose
     `travel` to the next stop's place when not there yet, else `perform` the stop's
     activity — picking a value from the offered enum. When a Penn verb tool is offered
     (`get`/`drink`/`activate`/`boil`-class, once #446/boil lands), select it in the
     scripted scenario that exercises it.
   - **cognition** `recall` / `query_knowledge` / `read_plan`: issue one before the
     decide in a bounded, deterministic way so `cognition_tool` usage is non-empty.
   - **converse** (`chat` / `speak`): return a short templated line keyed on the
     speaker + addressee parsed from the prompt, so a real `chat`-kind memory and an
     emergent relationship edge land.
   - **reflect**: return a schema-valid reflection reply (matching `LLMReflector`'s
     expected structure) so reflection memories are written.
   - **repair**: script one invalid-then-valid tool reply for a single persona/turn so
     #357's bounded repair round is exercised and counted.
5. **End-to-end coverage test** (`godot-generative-agents/tests/test_full_feature_mock.py`).
   Run the Penn stepper on `--brain scripted` to completion and assert each
   `AgentFrame`/`Meta` field and feature is **populated, not merely shape-valid** — the
   test that goes red when the mock drifts behind the backend again.

## Deliverables

- `resolve_llm` `"scripted"` outcome + the `--brain scripted` CLI choice in
  `serve_penn.py`, mirrored in `generate_penn_replay.py`.
- `backend/penn/scripted_brain.py`: the deterministic, prompt-pure Penn responders
  (decide / cognition / converse / reflect / repair).
- Stepper + bake wiring that builds `MockLlmClient` brains under `scripted`
  (`llm_client`, `reflector_client`), recording into the run ledger; `cognition_tools`
  on by default under scripted.
- `test_full_feature_mock.py`: one end-to-end test asserting every gated feature is
  populated (list below).
- A short note in `godot-generative-agents/README.md` documenting the third brain.

## Acceptance

- `serve_penn.py --brain scripted` and `generate_penn_replay.py --brain scripted` run
  to completion offline with **no `ANTHROPIC_API_KEY`, no network, no spend**.
- The end-to-end test asserts each is **populated** (fails if any goes dark):
  - `chat`-kind memories written from a real (scripted) conversation, not the authored
    injector;
  - reflection memories present;
  - tool-call records in the ledger (per-verb typed tools exercised);
  - cognition-tool usage (`recall` / `query_knowledge` / `read_plan`) non-empty;
  - at least one emergent relationship edge beyond the t=0 YAML seed graph;
  - one tool-result validation **repair** round counted (#357);
  - a non-empty, non-zero-only usage ledger surface.
- Determinism: same seed/run → identical frames across two runs (assert in the test).
- `--brain mock` bake stays **byte-identical** (existing determinism suite green);
  `test_replay_contract.py` still green for the scripted bake (shape unchanged).
- No new runtime deps; no contract change; no change to real-brain (`--brain llm`)
  behavior.
- Full offline suite + `black` clean.

## Out of scope

- Any change to `ScheduleMockClient` or the byte-identical `--brain mock` bake.
- The cognition *features* themselves (#581–#584) — this spec only guarantees an
  offline brain that *reaches* their code paths and a test that keeps them lit.
- Real-provider (`--brain llm`) behavior, transport resilience (#260), or the contract
  shape (#305).
- Spreading conversation across ticks (#371) — complementary, not required here.

## Verification

- Run both entry points under `--brain scripted` with the environment's
  `ANTHROPIC_API_KEY` unset; confirm completion and zero real calls in the monitor.
- `pytest godot-generative-agents/tests/test_full_feature_mock.py -v` green; each
  populated-field assertion individually meaningful (spot-check by disabling one
  responder branch → the matching assertion goes red).
- Determinism suite / mock bake unchanged (`git`-level frame diff empty for
  `--brain mock`).
- `pytest` (root + godot) green; `black .` clean.

## Risks

- **Responder drifts toward call-order state (mitigated):** the pure-function-of-prompt
  rule is a hard design constraint; the determinism assertion under parallel decides
  (#366) catches an accidental counter.
- **Scripted brain diverges from real-brain schema (mitigated):** reuse the same tool
  schemas the real path offers; #357's validation runs over scripted replies too, so a
  malformed scripted reply is caught by the same layer.
- **Coverage test asserts shape not population (the original bug) (mitigated):** each
  assertion checks a *value* is present (non-empty memory list, ≥1 edge, ≥1 repair
  count), and the spec requires the disable-a-branch spot-check.

## Relates to

- #266 (live real-LLM epic) — this is the offline twin that keeps it testable.
- #579 / #581–#584 — the cognition work that rides these gated paths.
- #356 / #485 (per-action tools), #357 (validation/repair), #358 / #512 (cognition
  tools) — the paths the mock currently can't reach.
- #446 + the boil superaction (in flight) — supplies a real verb the scripted decide
  branch selects once it lands.
