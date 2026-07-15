# Per-Run Usage View — Run-Scoped Totals Beside the Lifetime Ledger (#526)

**Issue:** #526 · **Branch:** `feat/per-run-usage-526` off `godot-ga-main` ·
**Review track:** godot-ga-main (backend + tests only).

## Goal

The LLM dashboard's run strip shows cumulative call/cost totals that keep
climbing across `POST /reset`, while the call log (per-run since `63d1934`)
clears — "calls: 27" over a 3-row log reads as a mismatch. The product call
(made in the issue, confirmed here): **keep the lifetime ledger and expose a
per-run view** — the spend cap is per server process and must survive resets
("a tripped ceiling stays tripped"), so rebasing the ledger is off the table.
Ship `run_calls` / `run_cost_usd` on `GET /usage`, and fix the RunStore drift
this exposes: run rows currently store *lifetime* cost, so after a reset,
run #2's `cost` column silently includes run #1's spend.

## Current state (verified)

- `UsageLedger` (`text_adventure_games/usage.py`): `records` is an
  append-only list; `total_cost_usd()` sums it (line 210); `summary()`
  (252-262) reports `calls = len(records)` + totals. Deliberately survives
  `PennStepper.reset()` (the ledger is constructed in `__init__`, not
  `_build()` — serve_penn.py:297) so `over_budget()` gates lifetime spend.
  **The engine file is untouched by this feature.**
- `GET /usage` (`backend/api.py:1064-1091`): serves `ledger.summary()` +
  `available`/`over_budget`/`max_cost_usd`/`remaining_budget_usd`; a zeroed
  same-shape dict when no ledger is wired. `create_app` receives the
  `stepper` directly (api.py:505-516), and the codebase's idiom for optional
  stepper capabilities is `getattr` probing (`ledger`, `drain_events` —
  `backend/live.py:38-57`).
- `PennStepper._build()` (serve_penn.py:333) runs at boot and on every
  reset — the same boundary that opens a new RunStore run id, so "this run"
  is already well-defined and shared with #304's persistence.
- The RunStore drift: `_persist_tick` writes
  `cost=self.ledger.total_cost_usd()` (serve_penn.py:510) — lifetime, not
  run-scoped.
- Endpoint-test home: `godot-generative-agents/tests/test_live_seam.py`
  (TestClient + fake-stepper fixtures `_walker`/`_live_client`). The
  lifetime `/usage` shape is pinned by the main-track `tests/test_api.py`,
  which stays untouched.

## Design

### 1. Ledger baseline on the stepper

`PennStepper._build()` snapshots the ledger position alongside the other
per-run cursors:

```python
self._run_ledger_calls_base = len(self.ledger.records)
self._run_ledger_cost_base = self.ledger.total_cost_usd()
```

Set unconditionally (no store required — the run view works for any live
server). Every reset re-baselines; the lifetime ledger keeps accumulating.

### 2. `PennStepper.run_usage()` — a third probed optional attribute

```python
def run_usage(self) -> dict:
    return {
        "run_calls": len(self.ledger.records) - self._run_ledger_calls_base,
        "run_cost_usd": round(
            self.ledger.total_cost_usd() - self._run_ledger_cost_base, 6
        ),
    }
```

Documented next to `ledger`/`drain_events` in the `SimStepper` docstring's
optional-attribute list (`backend/live.py`) — probed, never required.

### 3. `GET /usage` merges the run view

After building the lifetime summary (both the real and the zeroed branch
stay byte-identical), the handler probes the stepper:

```python
run_usage = getattr(stepper, "run_usage", None)
if callable(run_usage):
    summary.update(run_usage())
```

Additive fields only: `calls`, `total_cost_usd`, `by_actor`, token totals,
`over_budget`, `max_cost_usd`, `remaining_budget_usd` are unchanged, so the
existing strip and the budget line keep working before the web side ever
consumes the new fields. A stepper without `run_usage` (the generic demo
stepper, a bare `create_app(game)`) serves today's response unchanged.

### 4. RunStore run rows become run-scoped

`_persist_tick`'s update becomes:

```python
cost=self.ledger.total_cost_usd() - self._run_ledger_cost_base,
```

so a run row records that run's spend. One-line clarification in
`backend/README.md`'s RunStore section (`cost` = the run's spend, not the
server's lifetime total).

### 5. Out of scope

- The web strip change (consuming `run_calls`/`run_cost_usd`, lifetime in a
  tooltip) — Alistair's area; after merge, a comment on #526 names the new
  fields and their semantics.
- Any engine change (`text_adventure_games/usage.py` untouched); no
  `UsageLedger.mark()`/`summary(since=)` generalization until a second
  consumer wants it.
- The feed's `reason: "reset"` status record (the issue's alternative
  carrier) — unnecessary once `/usage` serves the fields.
- Rebasing the ledger (option 1) — rejected: it would let a reset bypass
  `max_cost_usd`.

## Verification

All offline, in `godot-generative-agents/tests/`:

- `test_penn_live.py`: a stepper with synthetic spend injected into its
  ledger (the mock brain spends $0, so the test records fake `CallRecord`s
  to make the arithmetic visible) → `run_usage()` reports the injected
  calls/cost; after `reset()` it re-zeroes while `ledger.summary()` keeps
  the lifetime totals and `over_budget()` still reflects lifetime spend
  against `max_cost_usd`; with a RunStore attached, run #1's row carries
  run-scoped cost and run #2's row starts from zero (the #304 drift test).
- `test_live_seam.py`: a fake stepper exposing `run_usage` → `GET /usage`
  carries the merged `run_calls`/`run_cost_usd` beside the lifetime fields;
  a fake stepper without `run_usage` → today's response shape exactly.
- `uv run pytest godot-generative-agents/tests/ -q` green; root
  `tests/test_api.py` untouched and green in CI; `uv run black .` clean.
