# godot-generative-agents/tests

The offline test suite for the `backend` package that powers this project (the
sim engine + headless HTTP API under [`../backend/`](../backend/)). It moved here
from `generative-agents/tests/` so the tests sit beside the code they exercise —
the backend package itself was folded into `godot-generative-agents/backend/` in
#400/#399.

## Scope — the Penn world, no Smallville

These tests cover the **Penn** simulation and the **world-agnostic** backend
utilities. The old Smallville-coupled tests (which built the 25-resident
`the_ville` world via `build_world`/`PERSONAS`, or the synthetic-`the_ville` maze
fixture, or seeded from `agent_history_init_n25.csv` / `spatial_memory.json`) were
dropped in the move — this project renders Penn, not Smallville. The shared
cognition those tests exercised (memory, retrieval, perception, planning,
reflection, conversation) is still covered at the engine level by the repo-root
[`../../tests/`](../../tests/) suite (`test_memory.py`, `test_conversation.py`,
`test_reflection.py`, `test_planning.py`, `test_perception.py`, …).

| File | Covers |
| --- | --- |
| `test_penn_live.py` | `build_penn_world`, `PennStepper` reproducing `simulate()` frame-for-frame, and the `LiveMeetingInjector` (issues #263/#297) |
| `test_penn_live_llm.py` | The `--brain llm` path: `resolve_llm`, real conversations, outage → idle-and-retry, the cost ceiling (issue #261) — fully offline via a scripted "real-shaped" brain, no SDK/key |
| `test_llm_monitor.py` | The terminal LLM-request monitor + `RoleTaggedLedger` write-through accounting, and its `PennStepper` wiring |
| `test_sim_clock.py` | `SimClock` step ↔ wall-clock mapping (issue #83) |
| `test_dotenv.py` | The repo-root `.env` loader (`backend/env.py`) |

## Running

Fully offline (mock brain + the tracked `the_upenn` matrix) — no `./setup.sh`, no
external clone, no API keys. From the repo root:

```bash
uv run pytest godot-generative-agents/tests/ -q
```

It's a separate pytest root (not collected by the repo-root `tests/` run), so CI
runs it as its own step. The Penn sim modules (`penn_world`, `serve_penn`) live in
[`../backend/penn/`](../backend/penn/) and are run as scripts, so each test that
uses them prepends that directory to `sys.path`; `backend` and
`text_adventure_games` resolve through the editable install.
