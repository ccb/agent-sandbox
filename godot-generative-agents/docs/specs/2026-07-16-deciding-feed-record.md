# Spec: `deciding` lifecycle feed record + per-agent thinking bubbles (issue #551)

**Track:** godot-ga-main (backend emit + Godot viewer — both under `godot-generative-agents/`).
**Date:** 2026-07-16

## Problem

Multiple live consumers need to know **"agent X is deciding right now,"** but the
change feed carries no such signal — it has `frame`, `status`, and `engine`
records only. Today each consumer infers it privately:

- **#372** (shipped) infers a *stall* locally in the Godot viewer — frames stop
  arriving for `THINKING_STALL_MS` — and shows a **global** "thinking…" pill
  (`thinking_indicator.gd` / `thinking_badge.gd`, wired in `viewer.gd`). That
  heuristic is **defeated by #366**: with concurrent per-agent decides, some
  agents keep producing frames while others think, so the frame stream never
  stalls; the cue misfires or never fires. It also can't say *which* agent is
  deciding, and a network hiccup reads as "thinking."
- **#525** (web companion) wants the identical state and would re-derive it.
- **#359 / #368** want a "which agent is deciding" marker to attribute an
  in-flight `llm_call` and its cost to the causing agent.

#366 (concurrent per-agent decisions) is the component that *inherently knows*
it is waiting on a decision — it submits each agent's decide to an executor and
collects/parks the future. A `deciding` begin/end record is a near-free
byproduct there. Emit it **once** as a first-class feed record so every consumer
subscribes to the same authoritative signal.

## Approach (decided)

Add a `deciding` change-feed record with a `begin`/`end` lifecycle per agent, and
migrate #372's viewer indicator onto it as **per-agent** bubbles. All on
`godot-ga-main` (backend + the `godot/` viewer).

### 1. Backend — emit via the drain pattern

The feed's `EventLog.append(kind, **fields)` (`backend/live.py`) is
**event-loop-only**, and #366 runs decides on **worker threads** (`_decide_for`
submitted to `decide_executor`; collected via `fut.result()`, parked in
`decide_pending` across ticks — `run_simulation.step`). So do **not** append at
the decide site. Mirror the existing `drain_events()` seam:

- **`run_simulation.step` gains an optional `deciding_sink`** (a callable
  `(agent: str, state: str, step: int, elapsed_ms: int | None) -> None`, default
  `None` = today's behavior). `step` calls it on the **main thread**:
  - `begin` right after `decide_executor.submit(...)` for an agent (or
    immediately before the inline synchronous decide on the serial path);
  - `end` when that agent's future is **collected** (`fut.result()` returns) —
    which may be a **later tick** for a parked/straggler decide, exactly the
    lifecycle #372 cannot infer. `elapsed_ms` measured begin→collect.
  - A parked future (still running past `decide_timeout`) emits **no** `end`
    yet — it is still deciding; `end` fires only on collection.
- **The stepper (`serve_penn.PennStepper`) owns a buffer.** It passes its
  buffer-appender as `deciding_sink` into `step(...)`, and exposes the
  accumulated records the same way `drain_events()` works. `serve_penn` already
  computes a per-tick `deciders` **count** + `timeouts` on the `frame` record
  (`last_deciders`, `run_simulation.py:299`); that coarse aggregate stays
  unchanged — the per-agent `deciding` lifecycle is complementary, not a
  replacement.
- **`live.run_loop` drains and appends** each buffered record as
  `log.append("deciding", agent=…, state=…, step=…, elapsed_ms=…)`, in the same
  place it appends `engine` records — on the event loop, safely.

**Record shape:**
```json
{"cursor": N, "kind": "deciding", "agent": "Maya", "state": "begin", "step": 42}
{"cursor": M, "kind": "deciding", "agent": "Maya", "state": "end", "step": 44, "elapsed_ms": 1830}
```

**Emission gate — real/scripted brains only.** Emit only when a brain actually
reaches the decide path: gate on `self.llm_client is not None`. That is true for
`--brain llm` and (once #563 merges) `--brain scripted`, and false for the pure
schedule mock — so the **default mock feed stays byte-identical** and no
"thinking" is signalled where none happens. No dependency on #563: the gate
covers it automatically when it lands.

### 2. Viewer — consume + migrate #372 to per-agent bubbles

`_apply_record()` (`viewer.gd`) dispatches on `kind` via a `match` that
**silently ignores unknown kinds**, so a new `"deciding"` case is additive-safe.

- **New `"deciding"` case:** update a per-agent `_deciding: {name: bool}` dict
  (`begin` → true, `end` → false), then show/hide a **per-agent thinking
  bubble** anchored to `_agents[name]["node"]` (mirrors the existing speech-
  bubble pattern at `_spawn_agent`), animated with `thinking_indicator.gd`'s
  `ellipsis()`. Styled as a decision cue, distinct from #245 speech balloons.
- **No wedged bubbles:** clear `_deciding` in `_teardown_cast()` and on the #549
  backend-restart path (handshake cursor rewind), so a dropped `end` across a
  reconnect can't strand a bubble. The existing `_last_cursor` guard already
  de-dups replayed records.
- **Global badge → smart fallback (decided).** Keep `thinking_badge.gd`, but
  drive it from the real signal when it is present: show the global pill when
  **any** agent is in `_deciding`; fall back to today's stall-inference
  (`ThinkingIndicator.should_show`) only when **no** `deciding` record has ever
  arrived this run (plain `--brain mock`, or an older backend that doesn't emit
  the kind). No regression in any mode; the `--stall-seconds` debug demo still
  works.

### 3. Tests

- **Backend:** a fake real/scripted brain drives the stepper; assert the buffer
  drains `deciding` begin/end records around each decide, that `end` carries a
  plausible `elapsed_ms`, that a parked future defers its `end` to the
  collecting tick, and that **no** `deciding` records appear under the pure mock
  (byte-identical gate).
- **Viewer:** new `godot/tests/test_deciding_indicator.gd` (pure logic like
  `test_thinking_indicator.gd`): `begin` → shows for that agent; `end` → clears;
  an unmatched `end` (no prior `begin`) is ignored; teardown/reset clears all;
  the global-badge smart-fallback truth table. Wired into `run_smoke_test.sh`.

## Deliverables

- `run_simulation.step` `deciding_sink` param + begin/end calls on the main
  thread (serial and #366 concurrent paths).
- `serve_penn.PennStepper` deciding buffer + drain method; `deciding_sink` wired;
  emission gated on `self.llm_client is not None`. `last_deciders`/`timeouts`
  unchanged.
- `live.run_loop` drains + appends `deciding` records to the feed (beside
  `engine`).
- `viewer.gd` `"deciding"` case + `_deciding` state + per-agent bubble node +
  teardown/restart clearing + global-badge smart fallback.
- `godot/tests/test_deciding_indicator.gd` + `run_smoke_test.sh` hook; backend
  test.
- Short note in `godot-generative-agents/README.md` / backend feed docs listing
  the new `deciding` kind.

## Acceptance

- A live `--brain llm` (or `--brain scripted`) run emits `deciding` begin/end
  records per agent on `GET /events` and `WS /ws`; `end.elapsed_ms` reflects real
  decision latency; a parked decide's `end` lands on a later tick.
- The Godot viewer shows a **per-agent** thinking bubble over the deciding
  agent's sprite, appearing/clearing on begin/end, and never wedges across a
  reconnect/reset.
- The global badge shows when any agent is deciding under a real/scripted brain,
  and falls back to stall-inference under plain mock / an older backend.
- **`--brain mock` feed is byte-identical** (no `deciding` records); the
  determinism suite stays green.
- Additive-safe: unknown-kind handling means no downstream consumer errors;
  feed records are not persisted, so no contract/RunStore change.
- `run_smoke_test.sh` green (new viewer test included); backend suite + `black`
  green.

## Out of scope

- **#525 web companion** migration onto the signal — a separate frontend; a
  follow-up. (This spec makes the signal available; #525 subscribes later.)
- **#359/#368** attribution of `llm_call`/cost to the deciding agent — the
  `deciding` record is the hook they will use; wiring them is their issue.
- Changing the per-tick `deciders` **count**/`timeouts` on the `frame` record
  (kept as-is).
- Persisting feed records (they remain ephemeral in-memory, as today).

## Verification

- `GET /events?since=0` on a short real/scripted run shows well-formed
  begin/end pairs; kill+reconnect mid-decision → the bubble resolves (either an
  `end` arrives or the restart path clears it), never strands.
- Determinism: `--brain mock` bake/live byte-identical (`test_penn_live.py`,
  replay-contract suites green); diff the mock feed before/after — no new
  records.
- `run_smoke_test.sh` loads the viewer and the new `test_deciding_indicator.gd`
  passes headless.
- `git status` shows only the backend files, `viewer.gd`, the new viewer test +
  smoke hook, the doc note, and this spec/plan — no unrelated files.

## Risks

- **Emitting off the worker thread (mitigated):** the sink is called only on the
  main thread (at submit and at collect), never inside `_decide_for` on a
  worker; the feed append happens on the event loop via the drain, matching the
  proven `engine`-record path.
- **Dropped `end` wedging a bubble (mitigated):** viewer clears `_deciding` on
  teardown + #549 restart; a `begin` with no `end` within a run is bounded by
  the next reset.
- **Double-count vs `deciders` (mitigated):** the per-agent lifecycle and the
  per-tick count are independent fields serving different consumers; neither
  reads the other.
- **Mock-feed drift (mitigated):** the `self.llm_client is not None` gate means
  the pure mock never emits the kind; the determinism suite guards it.

## Relates to

- #372 (viewer stall-inference — this migrates it to the real per-agent signal),
  #366 (the decide dispatch this rides on), #525 / #359 / #368 (future
  consumers), #563 (`--brain scripted`, which the gate covers for free once it
  merges).
