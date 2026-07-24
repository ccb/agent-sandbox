# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview

`agent-sandbox` is a research test bed for **multi-agent simulated environments**,
built by extending a text-adventure engine with LLM-driven agents. The summer goal
is a shared framework on which team members build their own games and simulations.
See `README.md` for the vision, `ROADMAP.md` for the plan, and `FEATURE-ROADMAP.md`
for technical feature specs. The audience is first/second-year undergraduates —
favor clear, readable code and explanation over cleverness.

`ROADMAP.md` / `FEATURE-ROADMAP.md` describe the summer plan and are useful for
*why*, but read as aspirational for features that already shipped — e.g. they list
triggers, a time model, and a world-state export API as upcoming work; all three
are implemented (`triggers.py`, `clock.py`, `world_state.py`, see below). Trust the
code over those docs for *what currently exists*.

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
uv run pytest tests/test_some_file.py::test_name -v # a single test
uv run black .                                       # format

LLM_PROVIDER=mock uv run python -m notebooks.hw1_llm.play  # ReAct NPCs, free + offline
```

Before opening a PR, run `/check` (or manually: `uv run black --check .` then
`uv run pytest tests/ -q`) — the same two gates CI runs.

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
  An opt-in `Game(..., turn_mode="simultaneous")` runs a **gather → resolve →
  react → advance** round instead (`turns.py`, issue #25): NPC agents (attached
  via `Character.set_agent`) decide against the turn-start snapshot, then commands
  resolve player-first and in `initiative` order (contention fails at the
  precondition gate and is fed back for a retry), then triggers react, then the
  turn counter advances.
- **Things** (`things/`): `Thing` → `Location`, `Item`, `Character`. Properties are
  a `defaultdict(bool)`; any property can be set dynamically (`is_locked`, `is_dead`).
  `Character.take_turn()` delegates to a pluggable `self.behavior(character, game)`
  (sequential mode) or to an attached `self.agent` via `set_agent()` (simultaneous
  mode) — see Agent layer below.
- **Actions** (`actions/`): every action subclasses `Action` and implements
  `check_preconditions()` → `apply_effects()`. This precondition/effect gate is the
  classical-planning core — agents may only do what preconditions permit.
- **Blocks** (`blocks/`): obstacles that prevent movement until a condition is met.
- **Parser** (`parsing.py`): keyword matching. `llm_parser.py` adds an LLM fallback.
- **Triggers** (`triggers.py`): `Trigger(condition, action, repeatable)` +
  factory helpers (`at_turn`, `every`, `in_location`, `has_property`, `all_of`/
  `any_of`, `from_command`), registered via `game.add_trigger()`. Runs in the
  post-round **react** phase (`Game._run_triggers()`) in both turn modes, with a
  bounded cascade (`MAX_CASCADE_PASSES = 2`) so one trigger firing another can't loop.
- **Clock** (`clock.py`): `GameClock` maps `Game.turn` to wall-clock time/periods
  (`time_at`, `period_at`, `describe`); opt-in via `Game(..., time_config=...)`,
  stored as `game.clock`. `Character.take_turn()` uses `minutes_per_turn` for a
  per-turn action-duration budget.
- **World-state export** (`world_state.py`): `world_state(game)` builds a typed,
  JSON-able snapshot (`WorldState`/`ClockState`/`LocationState`/`CharacterState`/
  `ItemState`/`GoalState`/`EventState`) — deliberately excludes private agent
  cognition (memory/knowledge/beliefs). This is what `backend/api.py`'s
  `GET /world_state` serves.

### Agent / cognition layer: ReAct, memory, reflection, planning

`npc.py` is the seam and is fully wired into the live game — memory is created
unconditionally for every agent and read/written every turn; reflection, planning,
knowledge, and cognition tools are opt-in (off unless configured) but functional,
not stubs.

- `npc.py`: `Agent.decide(observation) -> command` is the pure decision seam.
  `LLMAgent` reasons via an `LlmClient`; `ScriptedAgent` is a deterministic rule,
  for tests/cheap NPCs. The surrounding Observe→Act→Reflect loop
  (`react_behavior`, `decide_and_route`, `maybe_reflect`) lives outside `decide()`
  and is bridged onto a character two ways: `make_react_behavior`/
  `make_hybrid_behavior` build an `LLMAgent` and return a `set_behavior()` closure
  (sequential turn mode); `Character.set_agent()` lets `turns.py`'s simultaneous
  gather phase call `.decide()` directly. Both paths go through the same
  `Agent`/memory/reflection machinery. Agents reply in a labeled
  `Reasoning:`/`Action:` format, traced via `parser.npc_log` (kept out of
  `command_history` so one NPC's thoughts never leak into another's observations).
  Wired into the live game via `notebooks/hw1_llm/` (pure ReAct, no fallback) and
  the webapp via `build_game(llm_client=...)` (hybrid: ReAct with scripted fallback).
- `memory.py`: `AgentMemory` — an append-only per-agent episodic log
  (`MemoryRecord`s: observation/reflection/plan/chat), with `perceive()` and
  `retrieve()` (recency × importance × relevance, optionally embedding-based via
  `embedding_client.py`). This *is* the live "Observe" step — called from
  `react_behavior` and from `turns.py`'s gather phase every turn.
  `conversation.py`'s `converse()` extends it into agent-to-agent dialogue,
  writing `CHAT` records into both participants' memory.
- `reflection.py` / `planning.py`: `reflect()`/`should_reflect()` periodically
  synthesize raw memories into higher-level thoughts (distinct from the
  per-failure Reflect step); `DailyPlan`/`Planner` produce day→hour→minute
  schedules. Both are opt-in per-agent (`AgentConfig.reflection_threshold`, a
  `plan`) and reachable mid-decision via cognition tools (`read_plan`,
  `query_knowledge` against `knowledge.py`'s `Knowledge`/`Belief`).
- `perception.py`: `Veil`/`Sight`/`Scene` — location-attached visibility
  conditions (darkness, fog) that gate what `AgentMemory.perceive` can observe;
  zero-cost when unused.
- `reactions.py`: `Reaction`/`GatedEffect` (Startle, FleesAtNoise, …) — thing-owned
  reflexes triggered by world events, independent of `Agent.decide` (not part of
  the ReAct loop).
- `llm_client.py`: provider-agnostic LLM client (OpenAI / Anthropic adapters), plus
  `MockReActClient` (provider `"mock"`) — a deterministic offline stand-in that drives
  the full ReAct loop for free — and `client_from_env()` for env-var gating.
  `usage.py` tracks per-call token/cost accounting for every LLM call the agent
  layer makes.
- `llm_parser.py`: keyword-first, LLM-fallback parser. Preconditions stay hard-gated.
- `prompt_templates/`: the engine's LLM prompts as in-repo `.prompty` files (Jinja +
  Prompty), rendered with `prompt_templates.render(name, **vars)` instead of inline
  f-strings (issue #145). `prompt_templates/README.md` maps each template to the code
  that renders it. (Not to be confused with `prompts.py`, the in-game `Prompt` choice
  mechanism, #110.)
- Offline tests: `tests/test_agent_layer.py` (unit), `tests/test_react_live_game.py`
  (ReAct vs the real Action Castle game), plus focused suites per subsystem
  (`test_memory.py`, `test_reflection.py`, `test_planning.py`, `test_perception*.py`,
  `test_conversation.py`, `test_simultaneous_turns.py`, `test_triggers.py`,
  `test_time_model.py`).

### Web app: `text_adventure_games/webapp/`

Flask app with a `WebParser` that buffers messages for the HTTP response. Imports
the game from `notebooks/hw1_solution/action_castle.py`. This is the human-facing
HTML UI — distinct from the headless JSON API below.

### `backend/`: HTTP transport + the Smallville simulation stack

`backend/` holds two largely **decoupled** things — `api.py` doesn't import the
simulation modules below it:

- **HTTP API — `backend/api.py`** (issue #179): the project's **one canonical
  backend seam**: a FastAPI app (`server` extra) that serves any engine `Game`
  over HTTP so every out-of-process frontend (Godot, Phaser, the web companion)
  polls the *same* endpoints instead of baking its own data path. `GET /health`,
  `GET /world_state` (the typed `WorldState` snapshot, #90), `POST /command`
  (advances one turn → change-feed `events` + new snapshot); OpenAPI contract at
  `/docs`. `create_app(game)` is game-agnostic; `run(game, host, port)` serves it
  (`uv sync --extra server`, then `uv run python -m backend.api` for a demo
  world). Security (#186): loopback + unauthenticated by default, a 64 KiB body
  cap, and `run()` refuses a non-loopback bind without `SIM_API_TOKEN` (then
  requires `Authorization: Bearer`).
- **Smallville simulation** (the rest of `backend/`, see `backend/README.md`): a
  full Generative-Agents-style simulation built *on top of* the engine, distinct
  from a single playable `Game`. `world_map.py` bridges engine locations to a
  Smallville tile grid; `tiled_game.py`'s `TiledGame` (a `Game` subclass) makes
  "nearby" tile-distance rather than room-adjacency; `path_finder.py` (vendored
  from Stanford's Generative Agents) routes agents across the map;
  `smallville_agents.py` is where personas actually perceive→decide→act and
  revise plans; `planner.py` generates daily plans (mock or LLM); `sim_clock.py`
  maps sim steps to wall-clock time; `build_world.py` builds the town (cast +
  locations) from `world_data.yaml` / `world_data_upenn.yaml`; `run_simulation.py`
  / `run_upenn.py` are the CLI drivers (base Smallville town vs. the real UPenn
  campus map); `exporter.py` dumps a finished run into the replay format
  `generative-agents/` (a Django frontend, **not** the same thing as Chris's
  private "Generative Action Castle" prototype mentioned in `ROADMAP.md` — the
  similar names are coincidental) plays back. `compare_plans.py`,
  `compare_retrieval.py`, `smoke_llm.py` are dev/debug tooling.

## Other top-level directories

- `app/` — the engine running unmodified in-browser via Pyodide ("the Tomb
  terminal"), for playing *Tomb of Nassak An-Rah*; `ios/` wraps that in a
  SwiftUI/WKWebView shell for TestFlight. Both are live, working features,
  unrelated to the Smallville stack above.
- `godot-generative-agents/` — an early Godot 4.6 proof-of-concept (sprites
  wandering a Godot-rendered UPenn map; no player controls yet), not integrated
  with `backend/` or `generative-agents/`. Lives on the `godot-ga-main` branch
  (see Key Patterns).
- `tools/geo/` — converts real-world OSM/GeoJSON data into Tiled tilemaps and
  into the Smallville "matrix" format `backend/world_map.py` consumes; this is
  how the real UPenn campus map used by `run_upenn.py` is generated.
- `docs/` — hand-written design docs/guides, read directly on GitHub.
  `mkdocs/` builds a separate, deliberately **local-only** site (never
  published) from the engine's docstrings plus `docs/`; see the `update-mkdocs`
  skill/command.
- `generated/`, `parsely_pdfs/` — auto-generated notebooks and PDF-derived
  planning notes for porting other Parsely-format games; not hand-maintained
  source.

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
- Feature branches → PR → `main`. **Exception — the `godot-ga-main` branch:** a
  change that touches *only* `godot-generative-agents/` and/or `tools/geo/` goes on
  the long-lived `godot-ga-main` branch instead — branch off it and target your PR at
  it (reviewed by the Godot/geo owners, @aking526 + @0frankie, not the full `main`
  review). Anything touching the shared engine library (`text_adventure_games/`,
  `backend/`, the root `tests/`, top-level docs, …) still goes through `main`. A change
  spanning *both* the engine and godot/geo goes to `main`. Minor shared-config tweaks
  (`.gitignore`, `mkdocs/`) may ride along on `godot-ga-main` when they're in service
  of godot/geo work. `godot-ga-main` is cut from `main` and synced forward periodically.
