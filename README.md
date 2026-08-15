# Penn Generative Agents

[![Live site](https://img.shields.io/badge/Live_site-pennagents.vercel.app-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://pennagents.vercel.app/)
[![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](pyproject.toml)
[![Godot](https://img.shields.io/badge/Godot-4.6-478CBF?style=for-the-badge&logo=godotengine&logoColor=white)](godot-generative-agents/godot)
[![License](https://img.shields.io/badge/License-MIT-011F5B?style=for-the-badge)](LICENSE)

Penn Generative Agents is a forkable multi-agent simulation of a day on the
University of Pennsylvania campus. LLM-driven characters perceive a shared
world, form daily plans, remember events, travel, use grounded actions, and talk
to one another. A Godot 4 viewer and a browser companion make the simulation
inspectable rather than leaving it as a stream of model output.

This repository is the source package behind the public project writeup at
**[pennagents.vercel.app](https://pennagents.vercel.app/)**, where the writeup
explains how an agent works and the viewer plays a recorded run in the browser.
The `prod` branch intentionally matches that published showcase; ongoing
research may live on other branches.

## How it fits together

```text
text_adventure_games/                 state, actions, memory, planning, LLM clients
godot-generative-agents/backend/      simulation loop, Penn world, HTTP/WebSocket API
godot-generative-agents/godot/        native Godot 4 replay/live viewer
godot-generative-agents/web/          browser writeup and embedded replay
godot-generative-agents/tools/geo/    authored Penn map validation/conversion
tests/                                engine tests
godot-generative-agents/tests/        Penn/backend tests
```

The engine is authoritative. Models select from grounded action tools, while
preconditions and effects decide what actually happens. The frontend consumes a
versioned replay/live-state contract; it does not simulate a second copy of the
world.

## Prerequisites

- Python 3.11–3.13 (the repository pins 3.12) and
  [uv](https://docs.astral.sh/uv/)
- Godot 4.6 for the native viewer
- The licensed art packs for the viewer — they are not in the repo (their
  licenses forbid redistribution); [ASSETS.md](ASSETS.md) lists where to get
  each one and where the files go
- Node.js 22 and pnpm 11 only when developing the browser companion
- An Anthropic API key only for paid LLM runs

## Run the free mock simulation

From a clean clone:

```bash
uv sync --extra dev --extra server
```

Start the deterministic, key-free backend in terminal 1:

```bash
uv run python godot-generative-agents/backend/penn/serve_penn.py \
  --brain mock --tick-seconds 0.1
```

Start the viewer in terminal 2:

```bash
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```

The viewer can also play a baked replay. Generate one without saving a local run:

```bash
uv run python godot-generative-agents/backend/penn/generate_penn_replay.py \
  --no-persist
./godot-generative-agents/run.sh
```

See [the Godot/backend guide](godot-generative-agents/README.md) for controls,
configuration, replay generation, and troubleshooting.

## Run with Anthropic

Copy `.env.example` to `.env`, set `ANTHROPIC_API_KEY`, and keep that file local.
Then run a deliberately bounded simulation:

```bash
uv sync --extra server --extra llm
uv run python godot-generative-agents/backend/penn/serve_penn.py \
  --brain llm --steps 360 --max-cost 1.00
```

Model calls are pay-as-you-go. Cost depends on cast size, duration, model tier,
and cognition settings. The retained study measured roughly $0.52 for one agent
over 12 simulated hours and $1.38 for five agents over 3 hours; the five-agent,
12-hour showcase runs cost $5.37–$6.82. Treat those as historical observations,
not quotes or guarantees. Always set `--steps` and `--max-cost` first. The
canonical measurements and caveats are in
[`runs/cost-scaling`](godot-generative-agents/runs/cost-scaling/README.md).

## Develop and verify

```bash
uv run black --check .
uv run pytest tests/ -q
uv run pytest godot-generative-agents/tests/ -q
uv run pytest godot-generative-agents/tools/geo/ -q
uv run python godot-generative-agents/tools/geo/validate_tmj.py
./godot-generative-agents/run_smoke_test.sh

cd godot-generative-agents/web
pnpm install --frozen-lockfile
pnpm lint && pnpm test && pnpm build
```

Local API documentation remains part of the forkable package:

```bash
cd mkdocs
uv run --extra docs mkdocs serve
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing the public surface and
[CLAUDE.md](CLAUDE.md) when using a coding agent in a fork.

## Customize a fork

The most direct extension points are:

- `godot-generative-agents/backend/penn/world_data_upenn.yaml` and its
  `personas/` directory for cast,
  schedules, relationships, and model configuration;
- `godot-generative-agents/backend/penn/penn_world.py` for world construction
  and Penn-specific actions;
- `text_adventure_games/actions/` for new precondition/effect verbs;
- `godot-generative-agents/backend/promptviz_chains/cognition.yaml` for the
  documented cognition graph;
- `godot-generative-agents/godot/maps/upenn_core_urban.tmj` and
  `godot-generative-agents/tools/geo/` for map changes.

Keep model output behind the engine's action gate, add offline tests for new
extension points, and do not commit `.env`, cassettes, databases, raw prompts, or
generated run stores.

## Evidence, privacy, and scope

The repository keeps one selected believability analysis and aggregate cost CSV,
not the private development RunStore. The browser showcase replay is retained at
`godot-generative-agents/web/public/replay/penn_replay.json`.

Restricted artwork replacement and clean standalone publication/history are
tracked separately from this source-tree preparation. Review asset provenance
before redistributing a fork.

## Citation

```bibtex
@misc{king2026penngenerativeagents,
  title  = {Penn Generative Agents},
  author = {King, Alistair and L, Frankie and Callison-Burch, Chris},
  year   = {2026}
}
```

## License

Code is released under the [MIT License](LICENSE). Third-party assets and data
may carry their own terms; preserve notices and attribution when redistributing.
