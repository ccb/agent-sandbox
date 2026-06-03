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
black .                                       # format
```

To enable the LLM layer: set `LLM_PROVIDER` (`anthropic` or `openai`) and the
matching `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` before launching.

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

### Agent layer (work in progress — see ROADMAP)

- `npc.py`: a **ReAct skeleton** (Observe→Think→Act). It has **no Reflect step**, is
  **untested**, and is **not wired into the live game** (shipped NPCs use scripted
  behaviors in `homeworks/hw1_solution/action_castle.py`). Building this out is the
  summer's central task — do not assume it works as-is.
- `llm_client.py`: provider-agnostic LLM client (OpenAI / Anthropic adapters).
- `llm_parser.py`: keyword-first, LLM-fallback parser. Preconditions stay hard-gated.

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
