---
description: Wire a new output channel through the structured and terminal renderers
argument-hint: "[CHANNEL_NAME]"
---

When adding `$ARGUMENTS` to `text_adventure_games/reporting.py`, update:

1. the `Channel` enum and verbosity set;
2. `AGENT_CHANNELS` if it is private agent trace data;
3. `PlainRenderer` and `RichTerminalRenderer` presentation;
4. parser emitter helpers when needed;
5. `JSONRenderer` consumers only if the generic channel record is insufficient;
6. channel-focused tests in `tests/test_reporting.py` using `CaptureRenderer`.

Then run `uv run pytest tests/test_reporting.py -q`. Consumers must branch on
semantic `channel` values, not terminal formatting.
