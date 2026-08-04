# Penn Generative Agents

This local documentation site covers the reusable Python engine behind the Penn
campus simulation. Build it from a clean clone with:

```bash
cd mkdocs
uv run --extra docs mkdocs serve
```

The engine represents locations, items, characters, actions, memory, time, and
events. LLM agents can choose grounded actions, but the action precondition/effect
system remains authoritative.

## Where to go next

- [Configuration](configuration.md)
- [API overview](api/index.md)
- [Game loop](api/game-loop.md)
- [Agents](api/agents.md)
- [World model](api/world-model.md)
- [Knowledge and beliefs](api/knowledge.md)

Repository-level setup and the two-terminal Godot workflow are in the root
README. Architecture, testing, output, and extension guides live under `docs/`.
