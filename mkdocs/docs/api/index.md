# API reference

These pages are generated from the engine's own docstrings, so they always match
the installed code. For the conceptual picture, start with the
[design notes](https://github.com/ccb/agent-sandbox/tree/prod/docs/design) on
GitHub; these pages are the precise reference.

The reference is split by subsystem:

- **[Game loop](game-loop.md)** — `Game`, which manages world state and runs rounds.
- **[Configuration](config.md)** — `GameConfig`, the one object that sets a game's tuning knobs.
- **[Turn modes](turn-modes.md)** — the opt-in simultaneous gather → resolve round.
- **[Agents](agents.md)** — the ReAct layer: `Agent`, `LLMAgent`, `ScriptedAgent`.
- **[LLM client](llm-client.md)** — the provider-agnostic client and its adapters.
- **[World model](world-model.md)** — the `Thing` hierarchy and the action gate.
- **[Knowledge & beliefs](knowledge.md)** — what a character believes is true, kept distinct from the world graph.
