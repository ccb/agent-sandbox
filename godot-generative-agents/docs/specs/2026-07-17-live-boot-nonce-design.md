# Live boot nonce — two-sided restart detection on `GET /live` (#578)

**Issue:** #578 (`Live followers: two-sided restart detection (boot nonce on GET /live), not just cursor rewind`)
**Review track:** `godot-ga-main` (see "Branch routing" below)
**Status:** design approved 2026-07-17
**Follows:** #549 / PR #565 (cursor-rewind re-anchoring). Related: #567, #306, #568.

## Problem

Restart re-anchoring (#549) detects a backend restart by a **cursor rewind**: the
follower's kept cursor is above the fresh `GET /live` handshake's cursor, so the
in-memory feed must have restarted near zero. This is one-sided.

If the restarted backend's new feed has already climbed **to or past** the client's
kept cursor by the time the client reconnects, no rewind is seen and two runs are
silently stitched together. Concrete: client at cursor 10; a `--tick-seconds 0.1`
backend mints ~150 cursors while the follower's reconnect backoff grows toward 15 s
→ the handshake reports cursor 150, `150 < 10` is false, no re-anchor.

Consequences:

- **Web companion** (`useLive.ts`): the dead run's call log is kept and the new
  run's rows append under it as one continuous run; the new run's records below the
  old cursor are skipped entirely.
- **Godot viewer** (`viewer.gd`): worse — the old cast is never torn down (`_names`
  stays non-empty, so the new run's meta never respawns it) while new-run frames land
  in the dead run's view.

## Fix (approved design)

A per-process **boot nonce** exposed as a `boot_id` field on `GET /live`: one value
both clients compare against the last seen, instead of the cursor heuristic each
maintains. A changed `boot_id` means "new process, rejoin from scratch" regardless of
where the new feed's cursor landed.

### Why a dedicated nonce, not `run_id`

The issue offered "a per-process boot nonce **or** reuse #306's durable run IDs." A
dedicated nonce is the better fit:

- `run_id` is `None` when the server runs without `--persist` (no run store), so it
  cannot be the universal restart signal.
- `run_id` changes on every *in-process* run swap (`reset`, `POST /runs`, resume) —
  but those are already handled inside a live process by the feed's `reason:"reset"`
  status record. A restart signal that also fires on in-process swaps over-signals.
- #567 deliberately deferred putting `run_id` on `/live`.

A boot nonce changes **only** on process restart, is **always present**, and never
fires on an in-process reset/adopt — precisely the missing bit.

## Architecture

### 1. Backend: mint + expose `boot_id`

- Mint a per-process nonce **once in `create_app`** (called exactly once per server
  process) with `secrets.token_hex(8)` (a 16-char opaque hex string), and close over
  it in the route handlers.
- Add a `boot_id: str | None` field to the `LiveStatusResponse` model.
- `GET /live` returns it:
  - **enabled** response (a live loop is injected) → `boot_id` = the nonce;
  - **disabled** response (no controller/stepper, the command-only API) → `boot_id =
    null`. There is no live process to follow, and `null` keeps that response
    deterministic.

Minting in `create_app` yields the right semantics without extra bookkeeping:

- **stable across repeated `/live` calls** — a healthy follower re-handshaking never
  sees it move;
- **unchanged by `reset()` / `POST /runs` / resume** — in-process run swaps, already
  covered by the feed's `reason:"reset"` record;
- **fresh on every process restart** — a new process calls `create_app` again.

### 2. Placement: `GET /live` only

`boot_id` goes **only** on the `GET /live` response, not on the `started` status
record in the feed (`live.py`). Both clients already do restart detection at
handshake time (they compare the `/live` cursor), so `/live` is sufficient. Keeping it
off the `started` record avoids breaking a second exact-equality contract test
(`test_loop_appends_frames_with_contiguous_cursors`, which pins the `started` record's
exact shape) for no functional gain. One contract surface changes, not two.

### 3. Clients: nonce-primary, cursor-rewind fallback

Both `useLive.ts` and `viewer.gd`:

- remember the last-seen `boot_id`;
- on each fresh handshake, **a changed `boot_id` triggers the existing "rejoin from
  scratch" path** — web: clear the call log + re-anchor the cursor at the new head;
  Godot: `_teardown_cast()` + reset `_last_cursor` to `-1`. This is a strict superset
  of today's cursor-rewind trigger: it catches the missed case (new feed already
  climbed past the kept cursor) *and* the currently-caught rewind case.
- **retain the cursor-rewind check as a fallback** for an older/mixed-version server
  that omits `boot_id`. Both clients already default a missing handshake field to "no
  rewind", so a server without the field behaves exactly as today — no regression.

The first handshake of a session records `boot_id` without triggering a rejoin (there
is no prior run to tear down), mirroring how the cursor-rewind check only fires when a
prior cursor exists.

## Error handling / edge cases

- **Server omits `boot_id`** (older backend): clients treat it as "unknown" and fall
  back to the cursor-rewind heuristic; no rejoin is forced on its absence.
- **`boot_id` unchanged, cursor rewound** (a genuine same-process anomaly that
  "shouldn't" happen): the retained cursor-rewind fallback still re-anchors, so the
  nonce never makes detection *weaker* than today.
- **Disabled `/live`**: `boot_id` is `null`; a follower pointed at a command-only
  server never enters the follow path, so `null` is inert.

## Testing

Backend (offline `TestClient`, no key):

- `GET /live` disabled → response includes `boot_id: null` (update the existing
  exact-equality test);
- `GET /live` enabled → `boot_id` is a non-empty string, and is **stable** across two
  successive `/live` calls on the same app;
- two separate `create_app(...)` instances mint **different** `boot_id`s (the restart
  signal);
- the `started` feed record is **unchanged** (still its pinned shape — guards the §2
  placement decision).

Clients:

- **web** (`useLive.ts` test): a handshake whose `boot_id` changed while the new
  cursor is **≥** the kept cursor clears the call log / re-anchors — the exact gap
  #578 describes (cursor-rewind would miss it);
- **Godot** (`viewer.gd`, exercised via the viewer's test harness / smoke path): a
  changed `boot_id` with a non-rewound cursor tears down the cast and refetches;
- both: a server response with **no** `boot_id` still behaves as today (fallback).

## Branch routing

The issue says "routes to `main`" because `GET /live` was pinned by exact-equality in
the root `tests/test_api.py`. That guidance is **stale**: since #399 the backend moved
under `godot-generative-agents/backend/`, and the entire live-follower stack
(#262/#263/#549/#565) plus the `/live`-pinning copy of `tests/test_api.py` now live on
**`godot-ga-main`**. `main` has no `GET /live` handler at all, so #578 is not buildable
there. This change therefore targets `godot-ga-main`, where the machinery and the
pinning test both live. (Confirmed with the repo owner; the issue's routing note will
be corrected.)

## Scope / YAGNI

- No `run_id` on `/live` (deferred, see above); no change to the `started` feed record;
  no new endpoint. One field on one handshake, plus the two clients' comparison.
- The nonce is opaque — no versioning, no structured payload (pid/timestamp). If a
  future need arises (e.g. displaying process uptime), that's a separate change.

## References

- Code anchors (on `godot-ga-main`): `godot-generative-agents/backend/api.py`
  (`create_app`, the `/live` handler, `LiveStatusResponse`); `backend/live.py`
  (`EventLog`, `LiveRunController.status`, `run_loop`'s `started` record — for the
  "do not touch" guard); `godot-generative-agents/web/src/useLive.ts` (handshake +
  rewind); `godot-generative-agents/godot/scripts/viewer.gd` (handshake + teardown);
  `tests/test_api.py` and `godot-generative-agents/tests/test_live_seam.py` (contract
  tests).
- Issue #578; follows #549 / PR #565; related #567, #306, #568.
