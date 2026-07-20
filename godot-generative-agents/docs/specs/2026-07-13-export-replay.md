# Live→Replay Export — Persist Events + Export a Run to `penn_replay.json` (#307)

**Issue:** #307 · **Branch:** `feat/export-replay-307` off `godot-ga-main` ·
**Review track:** godot-ga-main (backend + tests only). Depends on the merged
#304 RunStore (PR #517) and the pinned #305 contract.

## Goal

A real-LLM live run is the expensive, interesting one — and today it vanishes
with the process (the RunStore keeps its frames/memories, but nothing turns
them back into a viewable file). Ship the **live→replay bridge**: persist the
one missing piece (the `GameEvent` log) and add an exporter that reads a run
from the `RunStore` and writes a `penn_replay.json` identical in shape to the
bake's — so a recorded live run re-opens in the existing Godot viewer
(`scenes/penn_replay.tscn`) with every shipped feature working: conversation
bubbles/links, cognition card + memory stream, and the timeline's
"interesting moments" markers.

## Current state (verified)

- **The replay file** is assembled inline in
  `backend/penn/generate_penn_replay.py::main()` (lines 210–246):
  `{"meta", "frames", "memory_streams", "events"}`. `events` is filled by
  `simulate(out_events=...)` (`run_simulation.py:524-525`) with
  `GameEvent.to_primitive()` dicts. The issue suggests reusing
  `backend/exporter.py`, but that writes the *legacy Django folder format* —
  the suggestion predates that discovery; the inline dict above is the real
  shape.
- **Contract** (`backend/contract.py`, constants-only — importable without
  pydantic): `EVENT_STATE_FIELDS = ("turn", "actor", "action", "summary",
  "payload")` (line 64) beside `AGENT_FRAME_FIELDS` (line 57).
  `contract_models.Replay` (lines 115–124) pins `events:
  list[EventState] | None = None` — **optional**, "absent pre-#467".
  `Meta` (98–113) has `steps: int | None` (bake-only) and `llm: LlmInfo |
  None` (live-only).
- **What the viewer reads** (`godot/scripts/viewer.gd`): `meta` (533–572,
  spawn/geometry/personas), `frames` (236–238, everything animated),
  `memory_streams` (485, 1526 — timeline reflection markers + the persona
  inspector's full history), `events` (491 — `ReplayMarkers.collect()`, the
  timeline's game-event markers, #476/#249). Empty `events` degrades to a
  timeline without game-event markers; nothing else breaks.
  **Conversations need nothing top-level**: dialogue rides in each frame's
  `chat` field, which the store already persists — bubbles/links work from
  frames alone. The desktop menu opens any `*.json` via a native file picker
  (`main_menu.gd:248-292`), so an exported file is directly loadable; **no
  viewer change needed**.
- **The RunStore** (`backend/run_store.py`, #304) persists manifest +
  `frames.jsonl` + memories. It does **not** persist events — the one
  fidelity gap this feature closes.
- **The live event stream**: `PennStepper.drain_events()`
  (`serve_penn.py:521-549`) publishes `game.events` to the change feed with
  its own cursor (`self._events_seen`, line 343/545) — persistence must use
  an **independent cursor** so the feed sees every event exactly once
  regardless of `--persist`. Its docstring notes a finishing tick logs no new
  GameEvents, but `POST /world/event` (`api.py:1174-1218`) appends a
  `GameEvent` *between* ticks (actor `None`) — so events can land after the
  final persisted tick, and finish/reset need a tail flush.
- **Persistence hooks** (from #304): `_build()` opens the run
  (`serve_penn.py:400-403`), `_persist_tick()` (490) runs pre-increment,
  `_finish_run()` (510) is idempotent, `reset()` (551) closes an unfinished
  run as `"reset"`. The bake's `--persist` block
  (`generate_penn_replay.py:267-273`) already holds the full `events` list
  when it writes.
- **Meta shapes**: the live manifest is `PennStepper.meta()` (414–445) — the
  bake's `meta` minus `steps` plus `llm`. Both validate as contract `Meta`.
  The bake's persisted manifest is `replay["meta"]` verbatim (steps
  included).

## Design

### 1. Store extension — events, mirroring frames

`RunStore` gains a third artifact, `<root>/<run_id>/events.jsonl`:

- `append_events(run_id, events: list[dict]) -> None` — validates **every**
  dict first (all five `EVENT_STATE_FIELDS` required, nothing unpinned —
  keys only, same structural style as `_validate_frame`; a bad event means
  nothing from the batch hits disk), then appends one compact JSON line per
  event. An empty list is a no-op. Unlike frames there is **no step == line
  invariant** — a step can emit zero or many events and they carry their own
  `turn`; order is append order.
- `read_events(run_id) -> list[dict]` — the lines in order; `[]` when the
  file doesn't exist (a run with no events never creates it).
- Module-level `_validate_event(event: dict)` beside `_validate_frame`,
  against `backend.contract.EVENT_STATE_FIELDS`. Keys-only on purpose: the
  base env has no pydantic (#304 precedent), and `POST /world/event` events
  legitimately carry `actor=None`.

### 2. Live wiring — an independent event cursor in `PennStepper`

- `_build()`: alongside the run-open block, seed
  `self._persist_events_seen = 0` (a fresh world starts with an empty
  `game.events`).
- `_persist_tick()`: after the memory sync, flush
  `self.game.events[self._persist_events_seen:]` as `to_primitive()` dicts
  via `append_events`, then advance the cursor. This runs *after* `step()`,
  so the tick's own events — and any `POST /world/event` injected since the
  previous tick — are captured in the same call.
- Tail flush: a small `_persist_pending_events()` helper (same slice +
  advance, no-op when nothing is pending or not persisting), called at the
  top of `_finish_run()` and `reset()` — catching events injected after the
  final tick. `_finish_run()` stays idempotent (the flush no-ops on the
  second call; the status flip is already guarded).
- `drain_events()` and its feed cursor are untouched.

### 3. Bake wiring — one line

In `generate_penn_replay.py`'s `--persist` block, after the frames loop:
`store.append_events(run_id, replay["events"])`.

### 4. The exporter — `backend/penn/export_replay.py` (new)

- `build_replay(store: RunStore, run_id: str) -> dict` — assembles the
  four-key replay from the store:
  - `meta`: the run manifest, with `meta.setdefault("steps", len(frames))`
    (live manifests don't know steps up front; a bake manifest already has
    it and must pass through untouched for the round-trip guarantee). The
    live manifest's `llm` key rides along — contract-valid, and it records
    which model produced the run.
  - `frames`: `store.read_frames(run_id)`.
  - `memory_streams`: `{p["name"]: store.memories_for(run_id, p["name"])
    for p in meta["personas"]}` — the lean 4-field projection in record-id
    order, which #304's guardrail already proved equal to the bake's
    `memory_streams`.
  - `events`: `store.read_events(run_id)`.
  - Unknown `run_id` raises `ValueError` (the CLI turns it into a clear
    exit).
- CLI (`python -m backend.penn.export_replay [run_id] [--runs-dir DIR]
  [--out PATH]`):
  - `run_id` optional — defaults to the newest run (`list_runs()[0]`); an
    empty store is a clear error.
  - `--runs-dir` defaults to `run_store.DEFAULT_RUNS_DIR`.
  - `--out` defaults to `<runs-dir>/<run_id>/penn_replay.json` — the
    artifact lives beside its run, and the printed absolute path is what
    the viewer's "Open a local replay file" picker wants.
  - Prints a one-line summary (run id, steps, personas, event count, output
    path). Exit 0 on success, 2 on unknown/empty.
- No `api.py`/`live.py`/viewer changes. `GET /runs/{run_id}/replay` is
  #306's territory (run-scoped routes).

### 5. Out of scope

- The API endpoint form of the exporter, run registry/resume, "current run"
  selection (#306).
- Any viewer change (the file picker already opens exported files).
- Any engine change; `backend/exporter.py` (legacy Django format) is
  untouched.
- Clip/video export (#488's remaining half) and reproducibility tooling
  (#197) — this just makes the recorded run exist as a file.

## Verification

All offline (mock brain, no keys), in `godot-generative-agents/tests/`:

- `test_run_store.py`: events append/read round-trip across two batches
  (order preserved); validation rejection (missing key, unpinned key) with
  nothing-hits-disk on a bad batch; `read_events` of an event-less run
  → `[]`.
- `test_penn_live.py`: extend the persistence test — after N ticks plus a
  hand-appended `GameEvent` mid-run (the `POST /world/event` shape,
  actor `None`), `read_events(run_id)` equals
  `[e.to_primitive() for e in stepper.game.events]`; an event appended
  *after* the final tick is captured by `reset()`/finish (tail flush), and
  the feed (`drain_events`) still sees every event exactly once.
- Export guardrails (bake-based, `test_event_records.py` style): run the
  bake with `--persist` into a `tmp_path` store, then
  `build_replay(store, run_id)` **equals** the written `penn_replay.json`
  as a dict — the whole bridge is byte-faithful; the exported dict
  validates as `contract_models.Replay` (pydantic is present in the test
  env); the CLI (argv-monkeypatched) writes the same file and prints the
  path.
- `uv run pytest godot-generative-agents/tests/ -q` green;
  `uv run black .` clean; the simulate-mirror byte-identity test stays
  untouched and green.

## Docs

- `backend/README.md`: extend the "RunStore: durable runs (#304)" section —
  `events.jsonl` in the layout, the exporter CLI with an example, and the
  note that an exported run opens in the viewer's file picker; update any
  forward-looking #307 pointers to the real module.
