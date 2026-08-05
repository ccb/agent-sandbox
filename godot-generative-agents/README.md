# Penn simulation, viewer, and web companion

This directory contains the Penn-specific application built on the shared
`text_adventure_games` engine.

```text
backend/     simulation loop, cognition, Penn world, API, run/replay tooling
godot/       Godot 4.6 native viewer
tools/geo/   map generation, furnishing, and TMJ↔matrix validation
web/         public React/Vite writeup and browser replay
runs/        minimal aggregate/case-study evidence (not a development RunStore)
```

## Free live workflow

From the repository root, install the backend and start it:

```bash
uv sync --extra server
uv run python godot-generative-agents/backend/penn/serve_penn.py \
  --brain mock --tick-seconds 0.1
```

In a second terminal, launch the viewer:

```bash
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```

The mock brain is deterministic, uses the real world/action/replay paths, needs
no key, and spends no money. The server listens on loopback by default. A
non-loopback bind requires `SIM_API_TOKEN` and bearer authentication.

`run.sh` locates Godot on `PATH` or in the standard macOS application location,
imports assets on a fresh clone, and opens the landing menu. Pass a scene path to
launch it directly.

## Baked replay

Generate the Penn replay without retaining a local run:

```bash
uv run python godot-generative-agents/backend/penn/generate_penn_replay.py \
  --no-persist
./godot-generative-agents/run.sh
```

The generated native-viewer file is ignored. The reviewed browser showcase
artifact lives at `web/public/replay/penn_replay.json`; regenerate it through
`web/scripts/gen-replay.sh` only when intentionally updating the publication.

## Paid live workflow

Copy the root `.env.example` to `.env`, set `ANTHROPIC_API_KEY`, and run with an
explicit step budget and cost ceiling:

```bash
uv sync --extra server --extra llm
uv run python godot-generative-agents/backend/penn/serve_penn.py \
  --brain llm --steps 360 --max-cost 1.00
```

The model recipe defaults come from `backend/penn/world_data_upenn.yaml` and may
be overridden by supported CLI/config options. Watch the terminal monitor. A
cost ceiling is a safety boundary, not a prediction; historical measurements
are documented in `runs/cost-scaling/README.md`.

## If something goes wrong

- **`Godot 4 not found.`** — `run.sh` probes `godot`, then `godot4`, then
  `/Applications/Godot.app/Contents/MacOS/Godot`. Install Godot 4.6 or put it on
  `PATH` under one of those names.
- **An import error naming the LLM extra** — `--brain llm` needs
  `uv sync --extra server --extra llm`. The server exits with that instruction
  rather than starting without a brain.
- **`--brain llm needs ANTHROPIC_API_KEY`** — export it in the serving terminal
  or put it in a repo-root `.env` (template: `.env.example`). An already-exported
  variable wins over `.env`, and no other key variable is consulted.
- **`ANTHROPIC_API_KEY was rejected by the API`** — the key is present but not
  valid. One free models-list request verifies it at boot, so a typo'd or revoked
  key stops the server here instead of leaving the cast frozen at $0 spend for a
  whole simulated day.
- **`Can't reach … — is the backend running?`** in the viewer's menu — start the
  server terminal first, and check `SIM_API_URL` matches its `--host`/`--port`
  (default `http://127.0.0.1:8080`).
- **The server dies with an address-in-use error** — something else owns 8080.
  Pass `--port` to the server and match it in `SIM_API_URL`.

## Penn world and extension points

- `backend/penn/world_data_upenn.yaml`: cast, schedules, relationships, meetings,
  and model defaults.
- `backend/penn/personas/`: reusable persona definitions.
- `backend/penn/penn_world.py`: the one shared world factory used by live and
  baked execution.
- `backend/penn/serve_penn.py`: live controls and the replay-compatible stepper.
- `backend/promptviz_chains/cognition.yaml`: static cognition-flow source used by
  the writeup.
- `godot/maps/upenn_core_urban.tmj`: authored visual map.
- `backend/penn/the_upenn/`: pathfinding matrix consumed by the simulation.

Forks can add a world builder to the scenario registry, but each shipped scenario
must provide its world data, tests, documentation, and replay contract together.

## Map changes

The TMJ picture and backend matrix must remain synchronized. See
`tools/geo/README.md` for the authoring pipeline, then run:

```bash
uv run pytest godot-generative-agents/tools/geo/ -q
uv run python godot-generative-agents/tools/geo/validate_tmj.py
```

Asset credits beside the map are part of the distribution. Preserve them and
verify the license of every added tile, sprite, font, and dataset.

## Validation

```bash
uv run pytest godot-generative-agents/tests/ -q
./godot-generative-agents/run_smoke_test.sh

cd godot-generative-agents/web
pnpm install --frozen-lockfile
pnpm lint && pnpm test && pnpm build
```

The smoke test imports the Godot project, runs its GDScript tests, and loads the
important scenes headlessly. Run it after viewer, map, asset, or replay changes.
