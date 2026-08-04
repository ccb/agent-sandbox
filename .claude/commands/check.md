---
description: Run the public package's full pre-PR validation gates
---

`/check` runs the same gates as `.github/workflows/ci.yml`. Continue through all
independent gates so the report shows every failure.

Run these in order:

1. `uv run black --check .`
2. `uv run pytest tests/ -q`
3. `uv run pytest godot-generative-agents/tests/ -q`
4. `uv run pytest godot-generative-agents/tools/geo/ -q`
5. `uv run python godot-generative-agents/tools/geo/validate_tmj.py`
6. `./godot-generative-agents/run_smoke_test.sh`
7. In `godot-generative-agents/web`: `pnpm lint`, `pnpm test`, `pnpm build`.
8. In `mkdocs`: `uv run --extra docs mkdocs build --strict`.

If `uv` isn't installed, fall back to the activated venv (`black --check .` /
`python -m pytest tests/ -q`).

Print a compact PASS/FAIL/SKIP summary and the actionable output for failures.
Do not commit or push.
