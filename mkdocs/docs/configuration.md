# Configuration

`GameConfig` (in `text_adventure_games/config.py`) is the one object you hand to a
`Game` to set its tuning knobs — the turn mode, the clock, how LLM-driven NPCs
think, terminal output, and more. These used to be baked into the library as module
constants and function defaults; `GameConfig` surfaces them so you can configure a
game from your own project without editing the engine.

**Every field defaults to the engine's historical value**, so adding a config — or
passing none — changes nothing. Override only what you need.

## Three ways to build one

```python
from text_adventure_games import Game, GameConfig, EngineConfig
from text_adventure_games.config import ClockConfig

# In Python:
config = GameConfig(
    engine=EngineConfig(turn_mode="simultaneous"),
    clock=ClockConfig(enabled=True, start_hour=6),
)

# From a file you ship with your project:
config = GameConfig.from_file("my_game/config.yaml")

# From the library's environment variables (LLM_*, OUTPUT_LEVEL, NO_COLOR):
config = GameConfig.from_env()

game = Game(start_location, player, config=config)
```

## A config file in your project

Drop a `config.yaml` (or `.json`) beside your game and load it with
`GameConfig.from_file(path)`. Top-level keys are the section names; every section
and field is optional and falls back to its default.

```yaml
engine:
  turn_mode: simultaneous   # "sequential" (default) or "simultaneous"
  phases: true              # false = initiative order; true = talk/move/fight
  give_hints: false

clock:
  enabled: true             # the in-game clock is off unless you enable it
  start_hour: 6
  minutes_per_turn: 30

agent:                      # how LLM-driven NPCs decide
  temperature: 0.3
  max_tokens: 96
  max_retries: 2

llm:                        # omit entirely for no LLM
  provider: anthropic       # "anthropic" | "openai" | "mock"
  model: null               # null -> the provider's default

render:
  level: verbose            # null -> follow OUTPUT_LEVEL
  width: 100
```

!!! note "YAML vs JSON"
    YAML needs `pyyaml`, which ships as a dependency, so YAML files work out of the
    box; JSON needs nothing extra. An unknown section or field raises a clear
    `ValueError` instead of being silently ignored.

The five sections:

| Section | Affects | Examples |
|---|---|---|
| `llm` | the LLM connection (reuses `LlmConfig`) | `provider`, `model`, `max_output_tokens` |
| `agent` | LLM-driven NPC decisions | `temperature`, `max_tokens`, `max_retries`, `max_duration` |
| `engine` | turn loop, world, triggers | `turn_mode`, `phases`, `give_hints`, `max_actions_per_turn`, `heard_max`, `cascade_passes` |
| `clock` | the optional in-game clock | `enabled`, `start_hour`, `minutes_per_turn`, `periods` |
| `render` | terminal output | `level`, `width`, `no_color` |

## Precedence

Highest priority wins:

1. An explicit `Game(...)` argument (`turn_mode=`, `time_config=`) — overrides the config.
2. A value set in your `GameConfig`.
3. An environment variable, where one exists (`LLM_*`, `OUTPUT_LEVEL`, `NO_COLOR`) —
   used when the matching config field is left at its `None` ("follow the
   environment") default.
4. The built-in default.

## Wiring the LLM and NPCs

`Game` doesn't create LLM clients or attach NPC brains for you. The config gives you
the parts:

```python
from text_adventure_games.npc import make_react_behavior

client = config.build_llm_client()             # None if the `llm` section is unset
if client:
    troll.set_behavior(make_react_behavior(client, config=config.agent))
```

For field-by-field details, see the [Configuration API reference](api/config.md).
