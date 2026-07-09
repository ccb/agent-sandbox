# Persist the GameEvent Log into Run Records (#467)

**Issue:** #467 · **Branch:** `feat/events-record-467` off `feat/boil-water-300` (stacked on PR #465; PR bases on that branch and auto-retargets to `godot-ga-main` when #465 merges) · **Review track:** godot-ga-main (backend-only).

## Goal

Every `GameEvent` the engine logs during a run (`game.log_event(...)` → `game.events`,
e.g. PR #465's `sickness` event) is persisted into both of the run's records:

1. **Bake** — the replay artifacts written after an offline simulation.
2. **Live** — the change feed a running server publishes (`GET /events?since=` + WS).

This completes #300's measurement criterion: #299's "count sickness events and
their cause" becomes a pure read of the run record, instead of inferring from
the memory stream.

## Record shape

`GameEvent.to_primitive()` (`text_adventure_games/events.py:39`) already returns
the exact `EventState` contract from #305 (`world_state.py:131`):

```json
{"turn": 3, "actor": "Sofia Ramirez", "action": "sickness",
 "summary": "Sofia Ramirez got sick drinking cup of murky water",
 "payload": {"item": "cup of murky water", "location": "Houston Hall"}}
```

No reshaping anywhere. Bake and live carry this dict verbatim; the live feed
adds `"kind": "game_event"` (see below).

## Design

All changes live in `godot-generative-agents/backend/`. The engine is untouched.

### 1. `simulate()` exposes the event log (bake source)

`run_simulation.simulate()` builds the game internally and returns only
`frames`; per-run extras use the **out-parameter convention** already
established by `out_memories` (`run_simulation.py:369` — "not part of the
return so the many `frames = simulate(...)` call sites keep working").

Add `out_events: list | None = None`. After the step loop ends, extend it with
`event.to_primitive()` for every entry in `game.events`. End-of-run dump is
sufficient for bake — each record carries its own `turn` stamp.

### 2. Penn replay bake

`penn/generate_penn_replay.py` passes `out_events` and writes it as a
top-level `"events"` array in the replay JSON, parallel to `"frames"` and
`"memory_streams"`. Safe for the viewer: `viewer.gd:449` reads only the keys
it knows (`frames`, `memory_streams`); unknown top-level keys are ignored.

### 3. Generic exporter bake

`exporter.write_simulation()` gains a keyword `events: list | None = None`;
when provided (even empty), it writes `events.json` (a single JSON array of
the records) into the sim's storage folder alongside the existing artifacts.
`run_simulation.main()` (the Smallville bake entry point) threads
`out_events` from `simulate()` into it.

### 4. Live feed

`penn/serve_penn.py` `PennStepper`:

- a `self._events_seen = 0` counter, initialised in `_build()` so
  `reset()` naturally clears it with the rebuilt game;
- `drain_events()` — which `backend.live`'s tick loop already drains and
  publishes at the tick boundary (`live.py:253-255`, the #349 publish-point
  rule) — additionally returns the new slice of `game.events` as
  `dict(event.to_primitive(), kind="game_event")`, then advances the counter.

That is the whole live half. Each record flows out as the existing envelope
`{"cursor": n, "kind": "engine", "step": s, "event": {…, "kind": "game_event"}}`
through **both** doors (`GET /events?since=` and `/ws`) with zero changes to
`live.py` or `api.py`, keeping #262's cursor semantics. The inner `kind`
mirrors the existing `llm_call` re-stamp pattern (`serve_penn.py:446` docstring)
so feed consumers distinguish record types without guessing at fields.

Viewer compatibility (verified, no work needed): `viewer.gd:657-667` routes
inner `kind == "llm_call"` to the request monitor and every other engine
record through the generic `add_engine_event` row path (#394) — `game_event`
records render as readable log rows for free.

Concurrency: `tick_once()` steps and drains under the same app lock
(`live.py:187-202`), so the counter never sees a torn read.

## Non-goals

- No viewer/HUD feature work (surfacing beyond the free #394 rows is #302/#264/#163).
- No engine changes — `GameEvent`/`log_event` stay as they are.
- No new endpoints, no event filtering or truncation (payloads are already
  digest-sized), no backfill of old baked replays.

## Testing (all offline / mock, no keys)

- **Drain unit:** after `game.log_event(...)` on a `PennStepper`'s game,
  `drain_events()` yields the `game_event` record exactly once (second drain
  is empty); `reset()` restarts the counter.
- **Live seam:** using the existing `test_live_seam.py` harness style, a
  drained `game_event` record round-trips through the `EventLog` and comes
  back from `GET /events?since=0` inside the `engine` envelope.
- **Bake unit:** `simulate(..., out_events=evts)` on the boil-water scenario
  world (the `test_boil_water.py` e2e fixture: persona homed at Houston Hall
  with authored get/drink commands) fills `evts` with the `sickness` record
  carrying `payload={"item", "location"}` — issue #467's acceptance.
- **Replay assembly:** the baked replay dict contains the top-level
  `"events"` key with those records.
- **Exporter:** `write_simulation(..., events=[…])` writes `events.json`
  containing exactly that list.
- Full godot + root suites green; `black --check` clean.

## Acceptance (from #467)

1. After a mock bake of the Sofia scenario, the run artifacts contain the
   `sickness` event with `{item, location}`.
2. During a live run, a `/events`-style read (or WS message) surfaces the
   same event.
