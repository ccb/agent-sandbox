# Simulation backend

`backend` connects the reusable text-adventure agent engine to the Penn campus
application and its out-of-process viewers.

## Main entry points

- `penn/serve_penn.py` serves a live Penn simulation over HTTP and WebSocket.
- `penn/generate_penn_replay.py` bakes the same world into a replay.
- `api.py` exposes health, world-state, command, live, and run-control routes.
- `run_store.py` persists local run metadata and artifacts.
- `cognition.py` coordinates perceive/plan/decide/act/converse/reflect behavior.
- `sim_config.py` loads typed YAML/JSON simulation configuration.

Both Penn entry points call `penn.build_penn_world`; do not fork world setup into
the server and replay generator. Both emit the contract in `contract.py`, with
slim/fatten transformations in `replay_codec.py`.

## Run locally

```bash
uv sync --extra server
uv run python godot-generative-agents/backend/penn/serve_penn.py \
  --brain mock --tick-seconds 0.1
```

The deterministic mock path is the development default. For a paid run, install
the `llm` extra, set `ANTHROPIC_API_KEY` in an untracked `.env`, and pass both
`--steps` and `--max-cost`.

The API is unauthenticated only on loopback. Binding another interface requires
`SIM_API_TOKEN`; clients then send `Authorization: Bearer <token>`.

## Test

```bash
uv run pytest godot-generative-agents/tests/ -q
uv run pytest tests/test_api.py -q
```

Tests must be offline unless a separately approved authenticated smoke test is
being performed. Keep cassette data and development RunStore output untracked.

## Add or change a world

Implement one factory returning the same configured world type as
`penn_world.build_penn_world`, register it deliberately, and cover:

- fresh builds and reset behavior;
- deterministic replay production;
- manifest scenario/config fields and re-run behavior;
- action grounding and location validity;
- compatibility with the API and viewer schema.

World-specific actions belong next to the world when they are not reusable.
Reusable mechanics belong in `text_adventure_games` with engine-level tests.
