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

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .            # editable install of the engine
pip install -e .[dev]       # + black, nbformat
pip install -e .[llm]       # + openai, anthropic, tiktoken

python -m text_adventure_games.webapp.app   # Flask web UI at localhost:8080
python test_npc_behaviors.py                 # turn-based NPC behavior suite
pytest tests/ -v                             # offline agent-layer + live-game suites
black .                                       # format

LLM_PROVIDER=mock python -m homeworks.hw1_llm.play  # ReAct NPCs, free + offline
```

To enable the LLM layer: set `LLM_PROVIDER` (`anthropic`, `openai`, or `mock` —
a free deterministic stand-in) and, for the real providers, the matching
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` before launching.

## Architecture

### Engine: `text_adventure_games/`

- **Game loop** (`games.py`): `Game` manages world state and runs rounds.
  `do_command()` handles the player's command and, on success, calls `end_turn()`,
  which increments `self.turn` and gives every living NPC a `take_turn(game)`.
  This is the **turn-based multi-agent loop** — player first, then NPCs.
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
  two ways: `homeworks/hw1_llm/` (pure ReAct, no fallback) and the webapp via
  `build_game(llm_client=...)` (hybrid: ReAct with scripted fallback). No memory yet —
  that's Phase 2.
- `llm_client.py`: provider-agnostic LLM client (OpenAI / Anthropic adapters), plus
  `MockReActClient` (provider `"mock"`) — a deterministic offline stand-in that drives
  the full ReAct loop for free — and `client_from_env()` for env-var gating.
- `llm_parser.py`: keyword-first, LLM-fallback parser. Preconditions stay hard-gated.
- Offline tests: `tests/test_agent_layer.py` (unit), `tests/test_react_live_game.py`
  (ReAct vs the real Action Castle game).

### Web app: `text_adventure_games/webapp/`

Flask app with a `WebParser` that buffers messages for the HTTP response. Imports
the game from `homeworks/hw1_solution/action_castle.py`.

## Known issues / good first fixes

- `Game.from_primitive()` has commented-out block deserialization, so save/load
  silently drops blocks. Save/load is incomplete — don't rely on it.
- Mild Python 3.9-vs-3.10 syntax tension (PEP 604 `X | None` works only via
  `from __future__ import annotations`).

## Key Patterns

- New game: subclass `Game`, override `is_won()`, define locations/items/characters,
  pass custom actions to the constructor.
- New action: subclass `Action`, set `ACTION_NAME`, implement `check_preconditions()`
  and `apply_effects()`, use the precondition helpers (`at()`, `has_property()`,
  `is_in_inventory()`, `was_matched()`).
- Parser results go through `self.parser.ok(message)` / `self.parser.fail(message)`.
- Feature branches → PR → `main`.
