---
description: Run the full pre-PR gate (format check + test suite)
---

`/check` runs the same gates CI does (`.github/workflows/ci.yml`), locally, before
you push. Run every gate a PR should pass, from the repo root, via `uv run` (it
uses the project's `.venv/` automatically). Run both even if the first one fails,
then report.

Run these in order:

1. **Format** — `uv run black --check .`
   (reports unformatted files; does not modify anything)
2. **Pytest suite** — `uv run pytest tests/ -q`
   (includes the turn-based NPC behavior suite, `tests/test_npc_behaviors.py`)

If `uv` isn't installed, fall back to the activated venv (`black --check .` /
`python -m pytest tests/ -q`).

Then print a compact summary, one line per gate:

```
format   PASS | FAIL
pytest   PASS | FAIL
```

For any gate that FAILs, surface the relevant failing output (unformatted file
list, failing test names + tracebacks) so it can be fixed. If everything passes,
say so plainly — the branch is PR-ready. Do not commit or push anything.
