# Run Registry — Browse, Fetch, Export, and Delete Persisted Runs (#306, registry half)

**Issue:** #306 (decomposed — this ships the registry; resume-across-restart
splits into a new issue at finish) · **Branch:** `feat/run-registry-306` off
`godot-ga-main` · **Review track:** godot-ga-main (backend + tests only; the
issue's "target main" header predates #399).

## Goal

The #304 RunStore holds a durable history of runs (manifest, frames, events,
memories) and #307 can turn any of them back into a viewer-loadable replay —
but only from the shell. Give the HTTP API a **run registry**: list the
history, fetch a run, download its replay from a running server, delete old
runs. This is the read-plus-housekeeping half of #306; the hard half
(create/resume across restarts, run-scoped world_state/events) needs its own
design cycle and is explicitly out of scope.

## Current state (verified)

- `backend/api.py` has zero RunStore knowledge. The store hangs off the
  stepper only (`PennStepper.run_store`, `run_id` property —
  serve_penn.py:405-412). The API's idiom for optional stepper capabilities
  is `getattr` probing (`ledger` at api.py:546; `run_usage` landing via PR
  #540), and `/usage` answers `available: false` with a zeroed shape rather
  than erroring when unwired (api.py:1072-1084).
- `RunStore` (backend/run_store.py): `list_runs()` (newest first),
  `get_run()` (None on unknown), `read_frames`/`read_events`/`memories_for`.
  **No delete** — nothing removes a row, its memories, or `runs/<id>/`.
  `create_run` builds the dir + `manifest.json` + `frames.jsonl`
  (run_store.py:117-122).
- `backend/penn/export_replay.py::build_replay(store, run_id) -> dict` (#307)
  assembles the four-key `Replay`; **store-generic** (reads only
  manifest/frames/memories/events; no Penn imports inside the function) but
  it lives under `backend/penn/` because the replay *shape* is the Penn
  viewer's dialect. Raises `ValueError` on an unknown id.
- Endpoint tests live in `godot-generative-agents/tests/test_live_seam.py`
  (TestClient + `ScriptedStepper` fakes; post-construction attributes are the
  blessed way to give a fake optional capabilities). Store tests in
  `godot-generative-agents/tests/test_run_store.py`.
- All mutating/reading routes sit behind `require_auth`; the API is
  loopback + unauthenticated by default (#186).

## Design

### 1. `RunStore.delete_run(run_id)` (new store method)

```python
def delete_run(self, run_id: str) -> None:
```

One transaction deletes the `runs` row and the run's `memories` rows; then
`shutil.rmtree` removes `runs/<run_id>/` (`ignore_errors=True` — the row is
the source of truth; a half-removed dir on a dead disk shouldn't wedge the
API). Unknown id raises `KeyError` (the `update_run` precedent). Stdlib only
(`shutil` joins the imports).

### 2. Four registry endpoints in `create_app`

All probe `store = getattr(stepper, "run_store", None)` (resolved per
request, not captured at startup — `PennStepper` assigns `run_store` in
`__init__`, but per-request resolution is one line and immune to future
reordering) and `current = getattr(stepper, "run_id", None)`:

- **`GET /runs`** → `{"available": bool, "current": str | None,
  "runs": [...]}` — `list_runs()` rows minus the manifest blob (id, status,
  model, created, cost, steps; the manifest rides the per-run route instead
  — a hundred-run history shouldn't ship a hundred manifests). No store:
  `{"available": false, "current": null, "runs": []}` (the `/usage`
  precedent).
- **`GET /runs/{run_id}`** → the full `get_run()` row including the parsed
  manifest, plus `"current": bool`. Unknown id or no store: 404.
- **`GET /runs/{run_id}/replay`** → `build_replay(store, run_id)` as the
  JSON body — the endpoint half #307 deferred here; a browser/viewer can
  save it as `penn_replay.json` and open it in the landing menu's file
  picker. Unknown id or no store: 404. **Import choice:** the handler
  lazy-imports `backend.penn.export_replay.build_replay` with a comment —
  `api.py` stays importable without Penn, and Penn's is the only replay
  dialect today; a second world's format is the cue to promote a
  `replay_builder=` seam on `create_app`. (Flagged deliberately: reviewers
  should judge this against the alternative param-injection.)
- **`DELETE /runs/{run_id}`** → `delete_run()`; `{"ok": true,
  "deleted": run_id}`. Deleting the **current live run** is a 409 (the
  stepper is mid-write: frames.jsonl line numbering and the memory cursor
  would dangle). Unknown id or no store: 404. Destructive but auth-gated
  and loopback-default like every other mutating route.

Response models: plain dicts with docstrings, matching `/usage`'s style
(the run row's shape is the store's row contract, already pinned by
`test_run_store.py`) — no new pydantic models; the #305 `Replay` conformance
of the replay body is already guaranteed by #307's round-trip tests.

### 3. Out of scope (→ new issue at finish)

- `POST /runs` (world-factory seam), `POST /runs/{id}/resume`
  (re-hydration fidelity: snapshots vs replay-from-frames, #296/#297),
  run-scoping of `/world_state`/`/events`, multi-active runs. Filed as a
  follow-up issue citing this spec; **#306 stays open** (it names resume
  explicitly) with a comment marking the registry half shipped and pointing
  at the new issue.
- No engine change; no viewer/web change (the web run-browser UI is its own
  feature once these endpoints exist).
- No pagination/filtering on `GET /runs` until a real history outgrows one
  response.

## Verification

All offline, in `godot-generative-agents/tests/`:

- `test_run_store.py`: `delete_run` removes the row, its memories rows, and
  the run dir while leaving other runs (rows + dirs + memories) untouched;
  unknown id raises `KeyError`; deleting a run with no events file works
  (lazy events.jsonl).
- `test_live_seam.py`: a `ScriptedStepper` given a real tmp-path `RunStore`
  (post-construction attributes `run_store`/`run_id`) →
  `GET /runs` lists newest-first with `current` marked; `GET /runs/{id}`
  serves the manifest row; `GET /runs/{id}/replay` equals
  `build_replay(store, id)`; `DELETE` on a non-current run removes it (404
  on re-GET), on the current run 409s, on an unknown id 404s. A storeless
  stepper → `available: false` and 404s on every id route.
- `uv run pytest godot-generative-agents/tests/ -q` green;
  `uv run black .` clean.
