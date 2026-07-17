# Live boot nonce (`GET /live`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-process `boot_id` to `GET /live` so live-follower clients (web + Godot) reliably detect a backend restart even when the new feed's cursor has already climbed past their kept cursor.

**Architecture:** Mint a nonce once in `create_app` (`secrets.token_hex(8)`), return it on `GET /live` only (never on the `started` feed record). Each client remembers the last-seen `boot_id`; a change triggers the existing "rejoin from scratch" path, with the current cursor-rewind check kept as a fallback for servers that omit the field.

**Tech Stack:** Python 3.12 / FastAPI + pydantic (backend); TypeScript + Vitest (web); GDScript / Godot 4.6 (viewer). uv for Python, npm for web, `run_smoke_test.sh` for Godot.

## Global Constraints

- **`boot_id` on `GET /live` only** — NOT on the `started` status record in `live.py` (that record's exact shape is pinned by `tests/test_api.py::test_loop_appends_frames_with_contiguous_cursors`, which must stay green and unchanged).
- **Minted once per process, in `create_app`** — stable across repeated `/live` calls, unchanged by `reset()`/`POST /runs`/resume, fresh on each process. Format: `secrets.token_hex(8)`.
- **Disabled `/live`** (no stepper) returns `boot_id: null` (deterministic — not a random value).
- **Clients: nonce-primary, cursor-rewind fallback.** A changed `boot_id` → rejoin from scratch (superset of today's rewind trigger). A server that omits `boot_id` (older/mixed-version) must behave exactly as today (fall back to the cursor rewind); never force a rejoin on the field's absence.
- **Review track: `godot-ga-main`** (the whole live stack + the `/live`-pinning `tests/test_api.py` live here; `main` has no `GET /live`).
- Tests offline, no API key. Run `black`/`prettier` only on files you edit; don't reformat unrelated code.

---

### Task 1: Backend — mint `boot_id` and expose it on `GET /live`

**Files:**
- Modify: `godot-generative-agents/backend/api.py` (add `import secrets`; mint in `create_app` near line 540; add `boot_id` field to `LiveStatusResponse` ~line 409-417; add `"boot_id"` to both `/live` return dicts ~line 884-903)
- Test: `tests/test_api.py` (update `test_live_disabled_by_default` ~line 971; add two boot-nonce tests near it)

**Interfaces:**
- Produces: `GET /live` JSON gains `boot_id: str | None` — a non-empty hex string when a live loop is injected, `null` when disabled. Stable within one `create_app`; differs across `create_app` instances.

- [ ] **Step 1: Update the disabled-case exact-equality test and add the nonce tests**

In `tests/test_api.py`, edit `test_live_disabled_by_default` (line 971-981) to expect the new field, and add two tests right after it (before `test_live_handshake_reports_meta_and_state` at line 1030). `_client`, `_live_client`, `_wait_for_events` already exist in this file.

Change the assertion in `test_live_disabled_by_default` from:

```python
    assert c.get("/live").json() == {
        "enabled": False,
        "running": False,
        "paused": False,
        "step": None,
        "cursor": 0,
        "tick_seconds": None,
        "meta": None,
    }
```

to (add the `boot_id` line — disabled ⇒ null):

```python
    assert c.get("/live").json() == {
        "enabled": False,
        "running": False,
        "paused": False,
        "step": None,
        "cursor": 0,
        "tick_seconds": None,
        "meta": None,
        "boot_id": None,
    }
```

Add these two tests:

```python
def test_live_handshake_carries_a_stable_boot_nonce():
    # #578: a per-process boot id on GET /live lets a follower detect a backend
    # restart even when the new feed's cursor already climbed past its own.
    with _live_client() as c:
        first = c.get("/live").json()["boot_id"]
        assert isinstance(first, str) and first  # non-empty
        # Stable within one process: a healthy follower re-handshaking (or the
        # background refresh) must never see it move.
        assert c.get("/live").json()["boot_id"] == first


def test_boot_nonce_differs_across_processes():
    # Two independently created apps stand in for two server processes: distinct
    # nonces, so a reconnecting follower can tell one run's process from the next.
    with _live_client() as a, _live_client() as b:
        assert a.get("/live").json()["boot_id"] != b.get("/live").json()["boot_id"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578 && uv run pytest tests/test_api.py -k "boot_nonce or live_disabled" -v`
Expected: FAIL — `test_live_disabled_by_default` fails (`boot_id` key missing from the response), and the two new tests fail with `KeyError: 'boot_id'`.

- [ ] **Step 3: Add the `secrets` import**

In `godot-generative-agents/backend/api.py`, add `import secrets` to the stdlib import block (line 74-79), keeping alphabetical order — between `import os` (line 77) and `import signal` (line 78):

```python
import os
import secrets
import signal
```

- [ ] **Step 4: Mint the nonce in `create_app`**

In `create_app`, just after `log = EventLog(max_log_records)` (line 540), add:

```python
    # A per-process boot nonce (#578): minted once here, so it is stable across
    # every GET /live in this process and unchanged by reset()/POST /runs
    # (those swap the run, not the process), but fresh on each restart. Clients
    # compare it to detect a restarted backend even when the new feed's cursor
    # has already climbed past the one they kept.
    boot_id = secrets.token_hex(8)
```

- [ ] **Step 5: Add the field to `LiveStatusResponse`**

In `godot-generative-agents/backend/api.py`, add the field at the end of the `LiveStatusResponse` model (after `meta: dict | None` at line 417):

```python
    cursor: int = Field(..., description="the newest change-feed cursor (0 = none yet)")
    tick_seconds: float | None
    meta: dict | None
    boot_id: str | None = Field(
        None,
        description="per-process boot nonce; changes on a backend restart, "
        "null when no live loop is injected (#578)",
    )
```

- [ ] **Step 6: Return `boot_id` from both `/live` branches**

In the `live()` handler, add `"boot_id"` to both returned dicts. Disabled branch (line 884-893) → `None`; enabled branch (line 894-903) → the minted nonce:

```python
        if controller is None or stepper is None:
            return {
                "enabled": False,
                "running": False,
                "paused": False,
                "step": None,
                "cursor": log.latest_cursor(),
                "tick_seconds": None,
                "meta": None,
                "boot_id": None,
            }
        with lock:
            return {
                "enabled": True,
                "running": controller.running,
                "paused": controller.paused,
                "step": stepper.step,
                "cursor": log.latest_cursor(),
                "tick_seconds": tick_seconds,
                "meta": stepper.meta(),
                "boot_id": boot_id,
            }
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578 && uv run pytest tests/test_api.py -k "boot_nonce or live_disabled or loop_appends" -v`
Expected: PASS — the three boot tests pass, and `test_loop_appends_frames_with_contiguous_cursors` (the `started`-record shape guard) still passes **unchanged** (we did not touch the feed record).

- [ ] **Step 8: Format and commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578
uv run black godot-generative-agents/backend/api.py tests/test_api.py
git add godot-generative-agents/backend/api.py tests/test_api.py
git commit -m "feat(backend): per-process boot_id on GET /live (#578)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Web — `boot_id` reboot detection in `useLive.ts`

**Files:**
- Modify: `godot-generative-agents/web/src/types/live.ts` (add `boot_id` to `LiveStatusResponse` ~line 62-70)
- Modify: `godot-generative-agents/web/src/useLive.ts` (add a `bootId` closure var ~line 156; reboot detection in `handshake` ~line 176-200)
- Test: `godot-generative-agents/web/src/useLive.test.ts` (add one test in the `followLive` describe block, after line 286)

**Interfaces:**
- Consumes: the `boot_id` field on `GET /live` from Task 1.

- [ ] **Step 1: Write the failing web test**

In `godot-generative-agents/web/src/useLive.test.ts`, add this test inside the `describe("followLive", ...)` block, right after the `"re-anchors at the handshake's cursor when a reconnect finds it rewound (restart)"` test (ends line 286). The harness (`start`, `FakeWS`, `live`, `events`, `call`, `vi.advanceTimersByTimeAsync`) is defined earlier in the file:

```typescript
  it("re-anchors on a changed boot_id even when the new feed's cursor is past ours (#578)", async () => {
    live.boot_id = "boot-A";
    const sock = await start();
    sock.open();
    sock.push(call(1, 5));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([1]);
    sock.drop(); // the restarting backend takes every socket down with it
    // New process: its feed has ALREADY climbed past our cursor (5), so the
    // cursor-rewind check can't see the restart — only the changed boot_id can.
    live = { ...live, step: 1, cursor: 20, boot_id: "boot-B" };
    await vi.advanceTimersByTimeAsync(1000);
    expect(FakeWS.last.url).toBe("ws://b/ws?since=20"); // re-anchored at the new head
    expect(state.calls).toEqual([]); // the dead run's log is cleared, like a reset
    FakeWS.last.open();
    FakeWS.last.push(call(2, 21));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([2]); // the new run's rows flow
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578/godot-generative-agents/web && npm test -- --run useLive`
Expected: FAIL — without reboot detection the reconnect keeps the old cursor (socket URL is `ws://b/ws?since=5`, not `since=20`) and the call log is not cleared.

- [ ] **Step 3: Add `boot_id` to the TS type**

In `godot-generative-agents/web/src/types/live.ts`, add the field to `LiveStatusResponse` (after `meta: LiveMeta | null;` at line 69). Optional, so a body without it (older server / the test bodies that omit it) still type-checks:

```typescript
export interface LiveStatusResponse {
  enabled: boolean;
  running: boolean;
  paused: boolean;
  step: number | null;
  cursor: number;
  tick_seconds: number | null;
  meta: LiveMeta | null;
  // Per-process boot nonce (#578): changes on a backend restart. Absent on an
  // older server that predates the field.
  boot_id?: string | null;
}
```

- [ ] **Step 4: Add the `bootId` closure var**

In `godot-generative-agents/web/src/useLive.ts`, add a tracker beside the other `followLive` closure state (after `let cursor = 0;` at line 156):

```typescript
  let cursor = 0;
  let bootId: string | null = null; // last-seen GET /live boot nonce (#578)
```

- [ ] **Step 5: Add reboot detection in `handshake`**

In `godot-generative-agents/web/src/useLive.ts`, replace the rewind block (lines 182-183):

```typescript
    const rewound = !wasHandshook && hs.cursor < cursor;
    if (rewound) cursor = hs.cursor;
```

with reboot-primary, rewind-fallback logic:

```typescript
    const rewound = !wasHandshook && hs.cursor < cursor;
    // #578: a changed per-process boot nonce is the reliable restart signal —
    // it catches a new process whose feed has already climbed past our cursor,
    // which `rewound` misses. A first handshake (bootId null) or a server that
    // omits boot_id (older/mixed-version) falls back to the cursor rewind. Fresh
    // connects/reconnects only, like `rewound` — never the background refresh.
    const rebooted =
      !wasHandshook && bootId !== null && hs.boot_id != null && hs.boot_id !== bootId;
    if (hs.boot_id != null) bootId = hs.boot_id;
    const restarted = rewound || rebooted;
    if (restarted) cursor = hs.cursor;
```

Then change the `calls` line in the `setState` call (line 199) from `calls: rewound ? [] : s.calls,` to:

```typescript
      calls: restarted ? [] : s.calls,
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578/godot-generative-agents/web && npm test -- --run useLive`
Expected: PASS — the new test and all existing `followLive` tests pass (the existing restart test at line 271 has no `boot_id` and still re-anchors via the retained cursor-rewind fallback).

- [ ] **Step 7: Lint and commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578/godot-generative-agents/web
npx prettier --write src/useLive.ts src/types/live.ts src/useLive.test.ts
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578
git add godot-generative-agents/web/src/useLive.ts godot-generative-agents/web/src/types/live.ts godot-generative-agents/web/src/useLive.test.ts
git commit -m "feat(web): detect a backend restart via GET /live boot_id (#578)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Godot — extract a pure restart-detection helper, wire `viewer.gd`, test it

**Files:**
- Create: `godot-generative-agents/godot/scripts/restart_detect.gd` (pure helper, mirrors `live_pacer.gd`)
- Create: `godot-generative-agents/godot/tests/test_restart_detect.gd` (headless unit test, mirrors `test_live_pacer.gd`)
- Modify: `godot-generative-agents/godot/scripts/viewer.gd` (preload the helper ~line 132; add `_boot_id` var ~line 251; replace the inline rewind check ~line 686)
- Modify: `godot-generative-agents/run_smoke_test.sh` (add the new test to the runner ~line 56)

**Interfaces:**
- Consumes: the `boot_id` field on `GET /live` from Task 1.
- Produces: `RestartDetect.should_rejoin(prev_boot: String, hs_boot: String, last_cursor: int, hs_cursor: int) -> bool`.

- [ ] **Step 1: Write the failing helper test**

Create `godot-generative-agents/godot/tests/test_restart_detect.gd`:

```gdscript
extends SceneTree
## Headless unit tests for scripts/restart_detect.gd (issue #578). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_restart_detect.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const RestartDetect := preload("res://scripts/restart_detect.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# A changed boot nonce is a restart even when the new feed's cursor climbed
	# PAST ours -- the case the cursor-rewind heuristic misses (#578).
	_check(
		RestartDetect.should_rejoin("boot-A", "boot-B", 5, 20),
		"changed boot nonce with an advanced cursor -> rejoin"
	)
	# Same nonce, cursor advanced normally: a healthy follower, no rejoin.
	_check(
		not RestartDetect.should_rejoin("boot-A", "boot-A", 5, 20),
		"same boot nonce, advancing cursor -> keep following"
	)
	# Older server omits boot_id (empty hs_boot): fall back to the cursor
	# rewind -- a lower handshake cursor still means restart.
	_check(
		RestartDetect.should_rejoin("boot-A", "", 10, 2),
		"no boot_id + rewound cursor -> rejoin (fallback)"
	)
	_check(
		not RestartDetect.should_rejoin("boot-A", "", 5, 20),
		"no boot_id + advanced cursor -> keep following (fallback)"
	)
	# First handshake of a session (empty prev_boot): record only, no rejoin
	# unless the cursor itself rewound.
	_check(
		not RestartDetect.should_rejoin("", "boot-A", -1, 0),
		"first handshake -> no rejoin"
	)

	if _failures == 0:
		print("test_restart_detect: all checks passed")
	quit(1 if _failures > 0 else 0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_restart_detect.gd`
Expected: FAIL — a parse/load error because `res://scripts/restart_detect.gd` does not exist yet (the sentinel line "all checks passed" is not printed).

- [ ] **Step 3: Create the pure helper**

Create `godot-generative-agents/godot/scripts/restart_detect.gd`:

```gdscript
extends RefCounted
## Pure restart-detection for the live follower (issue #578): given the last
## boot nonce we saw, the fresh GET /live handshake's nonce and cursor, and the
## newest cursor we've applied, decide whether the backend is a NEW process and
## the follower must rejoin from scratch (drop the dead run's cast, re-anchor).
## No scene, no HTTP -- viewer.gd feeds it handshake values and acts on the bool.
## Headless-tested (tests/test_restart_detect.gd).


static func should_rejoin(
	prev_boot: String, hs_boot: String, last_cursor: int, hs_cursor: int
) -> bool:
	# A changed per-process boot nonce is the reliable signal: a new process,
	# even if its feed already climbed past our cursor (which the cursor check
	# below cannot see). Empty hs_boot (older server omitting boot_id) or empty
	# prev_boot (our first handshake) falls through to the cursor-rewind
	# heuristic (#549): a handshake cursor below the newest we've applied.
	if hs_boot != "" and prev_boot != "" and hs_boot != prev_boot:
		return true
	return last_cursor > hs_cursor
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_restart_detect.gd`
Expected: PASS — prints `test_restart_detect: all checks passed` and exits 0.

- [ ] **Step 5: Wire `viewer.gd` to the helper**

In `godot-generative-agents/godot/scripts/viewer.gd`:

(a) Preload the helper alongside the others (after line 132, `const LivePacer := preload("res://scripts/live_pacer.gd")`):

```gdscript
const RestartDetect := preload("res://scripts/restart_detect.gd")
```

(b) Add the last-seen nonce beside `_last_cursor` (line 251, `var _last_cursor := -1`):

```gdscript
var _last_cursor := -1
var _boot_id := ""  # last-seen GET /live boot nonce (#578); "" until first handshake
```

(c) Replace the inline rewind check (lines 686-688):

```gdscript
	if _last_cursor > int((data as Dictionary).get("cursor", _last_cursor)):
		_teardown_cast()
		_last_cursor = -1
```

with a call through the helper that also tracks the nonce:

```gdscript
	# Default hs_cursor to _last_cursor so a server omitting `cursor` reads as
	# "no rewind" (not a rewind to 0); the boot nonce is the primary signal (#578).
	var hs_boot := str((data as Dictionary).get("boot_id", ""))
	var hs_cursor := int((data as Dictionary).get("cursor", _last_cursor))
	if RestartDetect.should_rejoin(_boot_id, hs_boot, _last_cursor, hs_cursor):
		_teardown_cast()
		_last_cursor = -1
	if hs_boot != "":
		_boot_id = hs_boot
```

- [ ] **Step 6: Add the test to the smoke runner**

In `godot-generative-agents/run_smoke_test.sh`, add a line after the `test_live_clip_span.gd` invocation (line 55-56, before the `# exec` comment on line 58):

```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_live_clip_span.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_restart_detect.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

- [ ] **Step 7: Run the full smoke test to verify nothing regressed**

Run: `cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578 && ./godot-generative-agents/run_smoke_test.sh`
Expected: exit 0 — all unit tests (including `test_restart_detect`) print their sentinel, and every scene paints its map. (If `godot` is not on PATH, note that and run at least Step 4's single-test command.)

- [ ] **Step 8: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578
git add godot-generative-agents/godot/scripts/restart_detect.gd \
  godot-generative-agents/godot/tests/test_restart_detect.gd \
  godot-generative-agents/godot/scripts/viewer.gd \
  godot-generative-agents/run_smoke_test.sh
git commit -m "feat(viewer): detect a backend restart via GET /live boot_id (#578)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Full-suite guard + spec cross-check

**Files:** none changed — verifies the three feature commits and the "Done when".

- [ ] **Step 1: Backend suite**

Run: `cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578 && uv run pytest tests/test_api.py godot-generative-agents/tests/test_live_seam.py -q`
Expected: PASS — including the new boot-nonce tests, with the `started`-record shape test unchanged and green.

- [ ] **Step 2: Web suite + black**

Run: `cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578/godot-generative-agents/web && npm test -- --run` then `cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boot-nonce-578 && uv run black --check godot-generative-agents/backend/api.py tests/test_api.py`
Expected: web tests all pass; `black` reports both files unchanged.

- [ ] **Step 3: Cross-check the spec's fix**

Confirm and note in the ledger: `boot_id` present on `GET /live` (Task 1), `null` when disabled, absent from the `started` record (Task 1 guard); both clients rejoin on a changed nonce with the new cursor ≥ the kept cursor (Tasks 2-3 tests) and fall back to cursor-rewind when the field is absent (existing web restart test + helper fallback tests). No commit (verification only).

---

## Notes for the implementer

- **Do not** add `boot_id` (or `run_id`) to the `started` status record in `backend/live.py`; the fix lives on `GET /live` only, and touching the record breaks a pinned contract test for no gain.
- **Do not** mint the nonce per request or per reset — it must be minted once in `create_app` so it stays stable within a process and changes only across processes.
- Keep the cursor-rewind checks in both clients as the fallback; the boot nonce augments them, it does not replace them (older servers omit the field).
