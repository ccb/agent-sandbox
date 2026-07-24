# Run Resume — Pick a Persisted Run Back Up (#543, the second half of #306)

**Issue:** #543 (split from #306 by the registry spec) · **Branch:**
`feat/run-resume-543` off `godot-ga-main` · **Review track:** godot-ga-main
(backend + tests + docs only).

## Goal

The #304 RunStore records a live run durably and the #542 registry serves the
history over HTTP — but nothing could bring a persisted run back to life. A
server restart abandoned the old run: the new process minted a fresh id and a
follower's day was gone. This ships the resume half: adopt a persisted run as
the live one, at boot (`--resume`) or on a running server
(`POST /runs/{run_id}/resume`).

## Design decisions (made with @aking526, as #543 requested)

1. **Memory-first fidelity.** Rebuild a fresh world (`build_penn_world()` +
   `attach_agents` — the routing patches are stateful, a fresh build is
   mandatory), then restore only what the store holds durably: the step
   counter (`len(frames)` — the frames file is the authority; the row's
   `steps` column can lag one behind after a crash, and this keeps
   `append_frame`'s step == line-count invariant by construction), each
   agent's rendered position (the last frame's x/y), each schedule's cursor
   (fast-forwarded by authored dwell times — walking legs aren't stored, so
   an agent may land a stop early), the full memory streams (lossless, the
   `query_memories` pattern over `full_records`), and the run's spend
   (`_cost_base` — the process ledger restarts at $0, so the stored cost is
   topped up, never overwritten backwards). Transient world state resets by
   design: item properties, conversation cooldowns, meeting-injector arming,
   perform timers. The memories are the identity — this is what the
   generative-agents literature actually needs, with no engine changes.
   (Rejected: replay-from-frames — exact only for mock runs, which are free
   to regenerate, and LLM runs can't re-drive decisions; world snapshots —
   `Game.to_primitive` drops blocks/triggers/`tile_address`/the Penn patches
   and never captured agent minds, so it needs engine work on `main` *and*
   the memory rehydrate anyway.)
2. **Run-scoping = adoption.** Resume repoints `stepper.run_id` and rebuilds
   `stepper.game`, and because every route reads through the stepper (the
   `_GameProxy` seam), `/world_state`, `/events`, and the `/agents/{name}/*`
   family serve the resumed run from then on. Dead runs stay readable whole
   via `GET /runs/{run_id}/replay`.
3. **The wire signal is `reason: "reset"`.** Adoption publishes the
   documented "world rebuilt — refetch meta and follow from here" status
   record (with an additive `run_id` field), so both frontends handle a
   mid-process resume with zero client changes. A resume *across a restart*
   needs no signal at all: the in-memory feed starts over and the #549
   re-anchor already handles the cursor rewind on both clients.
4. **Resumability is broad.** Any run the store still has can be adopted —
   including rows orphaned at `running` by a crash (nothing else can reopen
   those). Guard: the stored manifest's cast must equal the cast the current
   world YAML builds, and its map geometry (`schema_version`/`width`/`height`)
   must match the current campus (map regen is routine, and tiles seeded from
   another map's last frame could be out of bounds) — both checked before any
   teardown. A `finished` run resumed
   under the same `--steps` finishes again immediately (the boot print says
   so; pass `--endless` or a larger `--steps`).

## What shipped

- `RunStore.full_records` / `RunStore.hydrated_records` — the former
  `_full_records` made public, plus the rehydrating read (`from_primitive`,
  id-ordered) that `query_memories` and resume share.
- `PennStepper(resume_run_id=...)` / `PennStepper.resume_run(run_id)` — both
  funnel into `_build(resume_run_id=...)` → `_adopt_run()`. The mid-process
  path guards **before** teardown (a failure after the rebuild would leave
  `_step_idx = 0` against a non-empty frames file and kill the run loop) and
  closes the abandoned day exactly like `reset()` does.
- `POST /runs/{run_id}/resume` — registry conventions: no store → 404, no
  `resume_run` capability on the stepper → 501, already-live → 409 (checked
  under the lock, atomic with the swap), unknown id → 404, refused resume →
  409. Runs in an executor under the app lock and bumps
  `controller.generation` (the `/reset` in-flight-tick protection).
- `serve_penn --resume [RUN_ID]` — bare means newest (`resolve_resume`);
  requires `--persist`; bad ids exit with a clean message.
- Fixed en route: `_persist_tick` used to write `cost=ledger.total_cost_usd()`
  absolute, which would have clobbered a resumed real-LLM run's recorded
  spend with ~$0. The run's row and `GET /usage` now share one
  `_run_cost_usd()` sum — #526's per-run ledger baseline plus the resumed
  run's stored spend (`_cost_base`) — so the two agree structurally and
  same-process re-adoption counts correctly.

## Out of scope (deliberate)

- **`POST /runs`** (create a run over HTTP) — needs a world-factory seam;
  there is exactly one Penn world configured at launch and `POST /reset`
  already opens a fresh id. Its own follow-up issue.
- **Per-run read scoping** (`GET /runs/{id}/events`,
  `/runs/{id}/agents/{name}/memory`, …) — the replay route already serves a
  stored run whole; paged per-run reads wait for a client that needs them.
- **`run_id` on `GET /live`** — the repo-root `tests/test_api.py` pins that
  payload with exact dict equality, so the field routes a PR to `main`; the
  resume response, the status record, and `GET /runs`' `current` already
  carry the id. One-line follow-up when something needs it.

## Verification

All offline, in `godot-generative-agents/tests/`: `test_penn_live.py` grows
the resume family (fast-forward unit; crash-orphan resume with contiguous
frames, lossless memories, seeded tiles; guards incl. cast mismatch and
finish-again; mid-process `resume_run`; `resolve_resume`), `test_live_seam.py`
the endpoint family (adopt + feed record, conflict/error mapping, 501 without
the capability). Manual e2e: `serve_penn --persist`, Ctrl-C mid-day,
`--persist --resume` — the boot line reports the adopted id + step and a
web-companion follower attached across the restart picks the resumed run up
via the #549 re-anchor.
