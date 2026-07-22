# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview

`agent-sandbox` is a research test bed for **multi-agent simulated environments**,
built by extending a text-adventure engine with LLM-driven agents. The summer goal
is a shared framework on which team members build their own games and simulations.
See `README.md` for the vision, `ROADMAP.md` for the plan, and `FEATURE-ROADMAP.md`
for technical feature specs. The audience is first/second-year undergraduates —
favor clear, readable code and explanation over cleverness.

## Setup & Commands

This project defaults to **uv** (committed `uv.lock` + `.python-version` pin
versions and Python 3.12). `uv run <cmd>` auto-uses `.venv/` — no activation.

```bash
uv sync                 # create .venv/ + install engine (editable) from the lockfile
uv sync --extra dev     # + black, nbformat, pytest
uv sync --extra llm     # + openai, anthropic, tiktoken

uv run python -m text_adventure_games.webapp.app   # Flask web UI at localhost:8080
uv run pytest tests/ -v                             # full suite (agent layer + NPC behaviors)
uv run pytest tests/test_npc_behaviors.py -s        # watch the NPC behavior suite, narrated
uv run black .                                       # format

LLM_PROVIDER=mock uv run python -m notebooks.hw1_llm.play  # ReAct NPCs, free + offline
```

No uv? The plain `python3 -m venv venv && source venv/bin/activate && pip install
-e ".[dev]"` flow still works (drop the `uv run` prefixes once activated) — see
`README.md` for the venv/conda fallbacks.

To enable the LLM layer: set `LLM_PROVIDER` (`anthropic`, `openai`, or `mock` —
a free deterministic stand-in) and, for the real providers, the matching
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` before launching.

## Architecture

### Engine: `text_adventure_games/`

- **Game loop** (`games.py`): `Game` manages world state and runs rounds.
  `do_command()` handles the player's command and, on success, calls `end_turn()`,
  which increments `self.turn` and gives every living NPC a `take_turn(game)`.
  This is the **turn-based multi-agent loop** — player first, then NPCs.
  An opt-in `Game(..., turn_mode="simultaneous")` runs a **gather → resolve**
  round instead (`turns.py`, issue #25): NPC agents (attached via
  `Character.set_agent`) decide against the turn-start snapshot, then commands
  resolve player-first and in `initiative` order, with contention failing at
  the precondition gate and fed back for a retry.
- **Things** (`things/`): `Thing` → `Location`, `Item`, `Character`. Properties are
  a `defaultdict(bool)`; any property can be set dynamically (`is_locked`, `is_dead`).
  `Character.take_turn()` delegates to a pluggable `self.behavior(character, game)`.
- **Actions** (`actions/`): every action subclasses `Action` and implements
  `check_preconditions()` → `apply_effects()`. This precondition/effect gate is the
  classical-planning core — agents may only do what preconditions permit.
- **Blocks** (`blocks/`): obstacles that prevent movement until a condition is met.
- **Parser** (`parsing.py`): keyword matching. `llm_parser.py` adds an LLM fallback.

### Agent layer (see ROADMAP for what's next)

- `npc.py`: the **ReAct loop** (Observe→Decide→Act→Reflect). `Agent.decide(observation)`
  is the decision seam; `react_behavior()` routes commands through the parser's
  precondition gate and feeds failure reasons back on retry. Agents reply in a labeled
  `Reasoning:`/`Action:` format; each decision is traced as `name [reasoning] ...` /
  `name [action] ...` lines via `parser.npc_log` (kept out of `command_history` so one
  NPC's thoughts never leak into another's observations). Wired into the live game
  two ways: `notebooks/hw1_llm/` (pure ReAct, no fallback) and the webapp via
  `build_game(llm_client=...)` (hybrid: ReAct with scripted fallback). No memory yet —
  that's Phase 2.
- `llm_client.py`: provider-agnostic LLM client (OpenAI / Anthropic adapters), plus
  `MockReActClient` (provider `"mock"`) — a deterministic offline stand-in that drives
  the full ReAct loop for free — and `client_from_env()` for env-var gating.
- `llm_parser.py`: keyword-first, LLM-fallback parser. Preconditions stay hard-gated.
- `prompt_templates/`: the engine's LLM prompts as in-repo `.prompty` files (Jinja +
  Prompty), rendered with `prompt_templates.render(name, **vars)` instead of inline
  f-strings (issue #145). `prompt_templates/README.md` maps each template to the code
  that renders it. (Not to be confused with `prompts.py`, the in-game `Prompt` choice
  mechanism, #110.)
- Offline tests: `tests/test_agent_layer.py` (unit), `tests/test_react_live_game.py`
  (ReAct vs the real Action Castle game).

### Web app: `text_adventure_games/webapp/`

Flask app with a `WebParser` that buffers messages for the HTTP response. Imports
the game from `notebooks/hw1_solution/action_castle.py`. This is the human-facing
HTML UI — distinct from the headless JSON API below.

### Backend HTTP API: `godot-generative-agents/backend/api.py` (issue #179)

The **backend seam**: a FastAPI app (`server` extra) that serves any engine `Game`
over HTTP so an out-of-process frontend (Godot, the web companion) polls the *same*
endpoints instead of baking its own data path. `GET /health`, `GET /world_state`
(the typed `WorldState` snapshot, #90), `POST /command` (advances one turn →
change-feed `events` + new snapshot); the OpenAPI contract is at `/docs`.
`create_app(game)` is game-agnostic; `run(game, host, port)` serves it
(`uv sync --extra server`, then `uv run python -m backend.api` for a demo world).
Security (#186): loopback + unauthenticated by default, a 64 KiB body cap, and
`run()` refuses a non-loopback bind without `SIM_API_TOKEN` (then requires
`Authorization: Bearer`). The `backend` package was folded into
`godot-generative-agents/` in #399 (its import name is unchanged — `from backend…`
and `python -m backend.api` still work; the root `tests/` and `generative-agents/`
still import it via the editable install).

### Godot viewer: `godot-generative-agents/`

A **Godot 4.6** frontend that renders the real UPenn campus and plays back — or
follows live — a generative-agents simulation walking across it. The Python sim is
unchanged; Godot is just a *viewer* that reads a baked replay file or talks to the
backend seam above. Full docs (map regen, real-LLM live mode, the run monitor):
`godot-generative-agents/README.md`. Needs Godot 4.6 on your `PATH` (as `godot`) or in
the standard macOS app bundle; live mode also needs `uv sync --extra server`.

```bash
# Launch the game — opens the landing menu, where you pick a replay or a live backend:
./godot-generative-agents/run.sh

# Watch the bundled replay: bake it first (from the repo root), then "Play the bundled
# replay" in the menu. It's a git-ignored artifact regenerated per checkout:
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py

# Follow a live sim (mock brain: real requests, no keys, no spend). Serve it, then
# point the viewer at it (or type the URL into the menu's "Run a live simulation"):
uv run python godot-generative-agents/backend/penn/serve_penn.py --tick-seconds 0.1  # terminal 1
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh                    # terminal 2

# Headless smoke test — load every scene and check its campus map painted (exit 0 = OK):
./godot-generative-agents/run_smoke_test.sh
```

`run.sh` auto-imports assets on first run: a fresh checkout has the asset sources but
not the git-ignored `.godot/` cache, and launching a scene directly (unlike opening the
editor) won't build it — so the script runs `--headless --import` first. For real-LLM
live mode (`serve_penn.py --brain llm`, Claude Haiku) see the README. Two slash
commands wrap the two halves: **`/run-viewer`** (launch the frontend — menu, a scene,
or a live URL) and **`/serve-backend`** (serve the sim, mock or real-LLM).

## Known issues / good first fixes

- `Game.from_primitive()` has commented-out block deserialization, so save/load
  silently drops blocks. Save/load is incomplete — don't rely on it.

## Key Patterns

- New game: subclass `Game`, override `is_won()`, define locations/items/characters,
  pass custom actions to the constructor.
- New action: subclass `Action`, set `ACTION_NAME`, implement `check_preconditions()`
  and `apply_effects()`, use the precondition helpers (`at()`, `has_property()`,
  `is_in_inventory()`, `was_matched()`).
- Parser results go through `self.parser.ok(message)` / `self.parser.fail(message)`.
- New/changed LLM prompt: edit or add a `.prompty` file in
  `text_adventure_games/prompt_templates/` (don't hand-build prompt strings inline),
  render it via `prompt_templates.render(name, **vars)`, then **update the usage table
  in `prompt_templates/README.md`** and pin its exact output in
  `tests/test_prompt_templates.py`.
- Feature branches → PR → `main`. All work targets `main` now — the long-lived
  `godot-ga-main` branch was retired and merged back in July 2026. Changes under
  `godot-generative-agents/` (the Godot viewer, `backend/`, `tools/geo/`) are
  still reviewed by the Godot/geo owners (@aking526 + @0frankie); everything else
  gets the normal engine review. (The `backend` package lives under
  `godot-generative-agents/backend/` since #399 — its import name is unchanged,
  and the root `tests/` and `generative-agents/` import it via the editable
  install.)
