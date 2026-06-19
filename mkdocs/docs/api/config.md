# Configuration

The unified `GameConfig` and its sub-configs. Build one and pass it to `Game`; see
the [Configuration guide](../configuration.md) for examples and a sample config file.

::: text_adventure_games.config
    options:
      heading_level: 2
      members:
        - GameConfig
        - AgentConfig
        - EngineConfig
        - ClockConfig
        - RenderConfig
