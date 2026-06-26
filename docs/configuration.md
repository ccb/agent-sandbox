# Configuring a game with `GameConfig`

Most of the engine's tuning knobs used to be baked into the library — the day
periods in `clock.py`, the per-turn action cap in `things/characters.py`, the LLM
agent's `temperature`/`max_tokens` in `npc.py`, and so on. To change one you had to
edit our source. That's fine for us, but a pain if you're building *your* game on
top of this library.

`GameConfig` (in `text_adventure_games/config.py`) gathers those knobs into one
place. You build it once — in Python, or by loading a YAML/JSON file you ship with
your project — and hand it to `Game`. **Every field defaults to the engine's old
value, so adding a config (or passing none) changes nothing.** Adopt it gradually,
overriding only what you need.

## Quick start

Three ways to get a config, from most explicit to most automatic:

```python
from text_adventure_games import Game, GameConfig, EngineConfig
from text_adventure_games.config import ClockConfig

# 1. Build it in Python
config = GameConfig(
    engine=EngineConfig(turn_mode="simultaneous"),
    clock=ClockConfig(enabled=True, start_hour=6, minutes_per_turn=30),
)

# 2. Load it from a file you ship with your project
config = GameConfig.from_file("my_game/config.yaml")

# 3. Read the library's environment variables (LLM_*, OUTPUT_LEVEL, NO_COLOR)
config = GameConfig.from_env()

game = Game(start_location, player, config=config)
```

If you pass no config, `Game` uses `GameConfig()` internally — identical to the old
behavior.

## Writing a config file for your project

Put a `config.yaml` (or `.json`) next to your game and load it with
`GameConfig.from_file(path)`. The top-level keys are the section names; **every
section and every field is optional** — anything you leave out keeps its default.

```yaml
# my_game/config.yaml — every value below is the engine default, shown for reference.
# Delete the lines you don't want to change.

llm:                      # the LLM connection; omit this whole section for no LLM
  provider: anthropic     # "anthropic" | "openai" | "mock" (free offline stand-in)
  model: null             # null -> the provider's default model
  max_output_tokens: 256
  max_context_tokens: 8000
  # api_key: null         # better to leave unset and use the ANTHROPIC_API_KEY /
                          # OPENAI_API_KEY env var instead of committing a key

agent:                    # how an LLM-driven NPC thinks
  temperature: 0.7        # 0.0 = deterministic, higher = more varied
  max_tokens: 128         # output budget per NPC decision (cost + verbosity)
  max_retries: 1          # retries after a command fails its preconditions
  max_duration: 1440      # cap (in-game minutes) on an action's claimed duration

engine:                   # the turn loop, world, and triggers
  turn_mode: sequential   # "sequential" or "simultaneous"
  phases: false           # false = plain initiative order; true = talk/move/fight
                          #   order; or a {action_name: rank} map of your own
  give_hints: true        # print each item's special commands as hints
  max_actions_per_turn: 100
  heard_max: 5            # how many recent utterances a character remembers
  cascade_passes: 2       # trigger re-evaluation passes per round

clock:                    # the optional in-game clock (off by default)
  enabled: false          # set true to give the game a clock
  start_hour: 8
  start_minute: 0
  minutes_per_turn: 15
  periods: null           # null -> default day periods; [] -> no period names

render:                   # terminal output
  level: null             # null -> follow OUTPUT_LEVEL; else "quiet"/"normal"/"verbose"
  width: 80               # wrap column for the plain renderer
  no_color: null          # null -> follow NO_COLOR; true forces the plain renderer

observability:            # LLM cost/usage logging (off by default)
  log_path: null          # null -> no artifact; a dir gets a timestamped
                          #   {ts}-{provider}.jsonl file; a *.jsonl path is used as-is
  log_prompts: false      # true also writes full prompts/responses (not just numbers)
```

The same config as JSON (`config.json`) — note JSON has no comments and uses
`null`/`true`/`false`:

```json
{
  "engine": { "turn_mode": "simultaneous" },
  "clock": { "enabled": true, "start_hour": 6, "minutes_per_turn": 30 }
}
```

!!! note "YAML vs JSON"
    YAML files need `pyyaml`, which ships as a dependency of this library, so
    `from_file("config.yaml")` works out of the box. JSON needs nothing extra.
    A typo in a section or field name raises a clear `ValueError` rather than being
    silently ignored.

## The sections

| Section | Affects | Key fields |
|---|---|---|
| `llm` | the LLM connection (reuses `LlmConfig`) | `provider`, `model`, `api_key`, `max_output_tokens`, `max_context_tokens`, `base_url` |
| `agent` | LLM-driven NPC decisions | `temperature`, `max_tokens`, `max_retries`, `max_duration` |
| `engine` | turn loop, world, triggers | `turn_mode`, `phases`, `give_hints`, `max_actions_per_turn`, `heard_max`, `cascade_passes` |
| `clock` | the optional in-game clock | `enabled`, `start_hour`, `start_minute`, `minutes_per_turn`, `periods` |
| `render` | terminal output | `level`, `width`, `no_color` |
| `observability` | LLM cost/usage logging (`usage.py`) | `log_path`, `log_prompts` |

## How values are chosen (precedence)

From highest priority to lowest:

1. **An explicit `Game(...)` argument.** `Game(..., turn_mode=..., time_config=...)`
   still works and overrides the config — handy for back-compat and one-offs.
2. **A value set in your `GameConfig`.**
3. **An environment variable**, for the few knobs that have one: the `LLM_*` vars
   (see below), `OUTPUT_LEVEL` (`render.level`), `NO_COLOR` (`render.no_color`), and
   `LLM_LOG` / `LLM_LOG_PROMPTS` (`observability.*`). These apply when the matching
   config field is left at its "follow the environment" default (`None`/`False`).
4. **The built-in default** (the engine's historical value).

## LLM and agents

`Game` does not create LLM clients or wire up NPC brains for you — that's the game
author's job. The config gives you the pieces:

```python
from text_adventure_games import GameConfig
from text_adventure_games.config import AgentConfig
from text_adventure_games.npc import make_react_behavior

config = GameConfig.from_file("my_game/config.yaml")

# Build a client from the `llm` section (or None if you omitted it)
client = config.build_llm_client()

# Wire an NPC's behavior, threading the `agent` section's temperature/max_tokens/
# max_retries/max_duration into the LLMAgent
if client:
    troll.set_behavior(make_react_behavior(client, config=config.agent))
```

`make_react_behavior` and `make_hybrid_behavior` both accept a `config=AgentConfig`.
You can still pass `max_retries=...` explicitly to override the config's value.

`GameConfig.from_env()` reads the same `LLM_*` variables as
`text_adventure_games.llm_client.client_from_env`: `LLM_PROVIDER`, `LLM_API_KEY`,
`LLM_MODEL`, `LLM_BASE_URL`, `LLM_VERBOSE`.

## Cost & usage logging (observability)

The engine calls a model once per acting NPC per round, so a busy run is thousands
of calls. The `observability` section controls the per-run usage artifact
(`usage.py`). Token tallying is always on and cheap (an in-memory `UsageLedger`);
setting `log_path` *also* streams a JSONL artifact — a `run` header, one `call`
line per LLM call, and a `summary` footer of per-actor token/cost totals. Set
`log_prompts: true` to include the full prompts/responses too.

`GameConfig.build_run_log(...)` turns the section into a `RunLog` (or `None` when
logging is off), mirroring `build_llm_client()`. A directory `log_path` becomes a
timestamped `{ts}-{provider}.jsonl` file; a `*.jsonl`/`*.json` path is used as-is:

```python
config = GameConfig.from_env()           # or from_file(...) / built in Python
ledger = UsageLedger()
run_log = config.build_run_log(provider="anthropic", model="claude-haiku-4-5")
with run_log or nullcontext():           # no-op when logging is off
    if run_log is not None:
        run_log.attach(ledger)
    ...                                  # run the game; calls stream to disk
# summary footer written on exit; ledger.summary() has the totals in memory
```

`GameConfig.from_env()` reads `LLM_LOG` (the `log_path`) and `LLM_LOG_PROMPTS`. The
Smallville backend (`gen_agents/run_simulation.py`) wires this up:
pass `--config my.yaml` (or set the env vars), and `--llm-log` / `--llm-log-prompts`
override the config's `observability` section.

!!! note "The Smallville `--config` is a `SimulationConfig`, not a bare `GameConfig`"
    The generative-agents sim wraps this `GameConfig` in a `SimulationConfig` (run-time
    + memory-retrieval knobs on top). In its `--config` file the engine sections live
    **under a `game:` key** (e.g. `game: {engine: {turn_mode: simultaneous}}`), with
    `simulation:`, `retrieval:`, and `embedding:` as siblings. See
    [SimulationConfig design](design/simulation-config.md).

## Web app

The Flask demo app reads a few settings from the environment so you don't edit
source to deploy it:

- `FLASK_SECRET_KEY` — the session secret (the built-in fallback is insecure and
  for local dev only; **set this before exposing the app**).
- `HOST` / `PORT` — where to bind (defaults `127.0.0.1` / `8080`; use
  `HOST=0.0.0.0` to accept remote connections).

## API reference

See the docstrings in `text_adventure_games/config.py`, or the generated
[Configuration API page](../mkdocs/docs/api/config.md) in the MkDocs site.
