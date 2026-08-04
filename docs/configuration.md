# Configuration

Penn world content and default model routing live in
`godot-generative-agents/backend/penn/world_data_upenn.yaml`. Reusable persona
definitions live beside it under `personas/`.

`backend.sim_config.SimulationConfig` composes these typed sections:

- `game`: reusable engine, agent, rendering, and observability settings;
- `simulation`: start time, step count, seconds per step, and seed;
- `retrieval`: memory scoring weights and limits;
- `cognition`: perception, conversation, duration, reaction, and tool settings;
- `embedding`: optional relevance backend.

Load YAML or JSON with `SimulationConfig.from_file`. Unknown sections and fields
fail validation rather than being ignored. CLI flags intentionally override the
loaded configuration for a single run; inspect `serve_penn.py --help` for the
current surface.

Secrets are not configuration files. Put `ANTHROPIC_API_KEY` and optional
`SIM_API_TOKEN` in an untracked root `.env` or export them in the process
environment. Never put a key in Penn YAML, a committed replay, or a run manifest.

Use explicit `--steps` and `--max-cost` values for every paid run. The server's
mock brain ignores model credentials and is the recommended development path.
