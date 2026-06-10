---
description: Run the full pre-PR gate (format check + test suite)
---

This repo has **no CI** — `/check` is the stand-in. Run every gate a PR should
pass, from the repo root, using the project venv interpreter. Run both even
if the first one fails, then report.

Run these in order:

1. **Format** — `venv/bin/black --check .`
   (reports unformatted files; does not modify anything)
2. **Pytest suite** — `venv/bin/python -m pytest tests/ -q`
   (includes the turn-based NPC behavior suite, `tests/test_npc_behaviors.py`)

Then print a compact summary, one line per gate:

```
format   PASS | FAIL
pytest   PASS | FAIL
```

For any gate that FAILs, surface the relevant failing output (unformatted file
list, failing test names + tracebacks) so it can be fixed. If everything passes,
say so plainly — the branch is PR-ready. Do not commit or push anything.
