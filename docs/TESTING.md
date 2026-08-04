# Testing

Routine validation is deterministic and offline.

```bash
uv sync --extra dev --extra server
uv run black --check .
uv run pytest tests/ -q
uv run pytest godot-generative-agents/tests/ -q
uv run pytest godot-generative-agents/tools/geo/ -q
uv run python godot-generative-agents/tools/geo/validate_tmj.py
```

The root suite protects reusable engine behavior. The Penn/backend suite protects
world construction, cognition, API/run behavior, replay contracts, and the public
showcase. Geo tests protect the authored TMJ and pathfinding matrix from drift.

Viewer changes also require:

```bash
./godot-generative-agents/run_smoke_test.sh
```

Web changes require `pnpm lint`, `pnpm test`, and `pnpm build` from
`godot-generative-agents/web`. Documentation changes require
`cd mkdocs && uv run --extra docs mkdocs build --strict`.

Use the mock or scripted brain in tests. A paid authenticated smoke test is a
separate, explicitly approved activity with a small `--steps` value and
`--max-cost` ceiling. Never record keys in test output or commit its cassette/run
store.
