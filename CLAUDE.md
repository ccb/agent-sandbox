# CLAUDE.md

Guidance for coding agents working in a fork of Penn Generative Agents.

## Purpose and boundaries

This repository is a public, forkable Penn campus simulation. Preserve the
separation between the authoritative Python engine/backend and presentation-only
Godot/web clients. Do not reintroduce removed course exercises, Smallville source,
private run stores, raw cassettes, internal journals, or unrelated experiments.

Never read, print, commit, or upload `.env` or API keys. Paid LLM tests require
explicit human approval, a small step count, and a cost ceiling. Offline mock
coverage is the default.

## Setup and common commands

```bash
uv sync --extra dev --extra server
uv run black .
uv run pytest tests/ -q
uv run pytest godot-generative-agents/tests/ -q
uv run pytest godot-generative-agents/tools/geo/ -q
uv run python godot-generative-agents/tools/geo/validate_tmj.py
./godot-generative-agents/run_smoke_test.sh
```

Free live workflow (two terminals):

```bash
uv run python godot-generative-agents/backend/penn/serve_penn.py \
  --brain mock --tick-seconds 0.1
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```

Web companion:

```bash
cd godot-generative-agents/web
pnpm install --frozen-lockfile
pnpm lint && pnpm test && pnpm build
```

Docs: `cd mkdocs && uv run --extra docs mkdocs build --strict`.

## Architecture

- `text_adventure_games/`: world objects, actions, parser/renderers, agents,
  planning, memory, reflection, recording, and provider-neutral LLM clients.
- `godot-generative-agents/backend/`: simulation services and Penn application.
- `backend/penn/penn_world.py`: shared factory for baked and live Penn worlds.
- `backend/penn/serve_penn.py`: live HTTP/WebSocket simulation and run controls.
- `backend/penn/generate_penn_replay.py`: deterministic offline replay bake.
- `godot-generative-agents/godot/`: native viewer; never make it authoritative.
- `godot-generative-agents/web/`: public writeup and embedded artifacts.

Actions use `check_preconditions()` followed by `apply_effects()`. LLM choices
must pass through that gate. New prompts belong in `.prompty` files and need
exact-output tests. Replay/schema changes require producer, consumer, codec, and
contract tests to move together.

## Editing rules for a fork

- Target active engine, backend, Godot, tooling, and documentation development at
  `main`. Changes to `godot-generative-agents/web/` (the browser companion and
  showcase site) target `prod`; base those branches on `prod` and open their PRs
  with `prod` as the base.
- Start from the tests closest to the changed subsystem; finish with all CI gates.
- Keep mock tests deterministic and network-free.
- Preserve the versioned replay API and slim/fatten codec invariants.
- Update README, MkDocs, prompt visualization, and config examples when public
  commands or extension points change.
- Generated outputs belong in ignored paths. Only intentional aggregate evidence
  or a reviewed public replay should be committed.
- Treat map tiles, sprites, fonts, and datasets as separately licensed assets;
  verify provenance before adding or redistributing them.

Useful repository commands live in `.claude/commands/`. They are convenience
wrappers, not substitutes for inspecting failures and reporting what was run.
