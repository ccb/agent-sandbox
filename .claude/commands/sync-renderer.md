---
description: Wire a new output Channel through every renderer (+ a test)
argument-hint: "[CHANNEL_NAME or feature description]"
---

The output seam (`text_adventure_games/reporting.py`,
`docs/design/output-and-trace-rendering.md`) routes each `Message` to renderers
by its `Channel`. Renderers fall back **silently** for an unknown channel, so a
new feature's channel must be wired through every surface or it renders wrong.
This command does that wiring end to end.

**Target channel:** `$ARGUMENTS` if given (a `Channel` name like
`AGENT_GOAL_UPDATE`, or a short description of the new feature's output).
Otherwise, run the coverage guard to discover the gap:
`echo '{"tool_input":{"file_path":"'$PWD'/text_adventure_games/reporting.py"}}' | uv run python .claude/hooks/check_renderer_coverage.py`
and wire whatever channels it reports.

For the target channel, make sure **each** of these is handled (add the case only
where it's missing — don't duplicate existing ones):

1. **`Channel` enum** (`reporting.py`) — add the member with a one-line comment if
   it doesn't exist yet.
2. **Visibility** — add it to the right level set in `_LEVEL_CHANNELS`
   (`QUIET`/`NORMAL`/`VERBOSE`). Agent-trace steps usually show at `NORMAL`;
   noisy/observation-style channels only at `VERBOSE`. `VERBOSE` already includes
   everything via `set(Channel)`.
3. **`AGENT_CHANNELS`** — add it here **iff** it's part of an NPC's private ReAct
   trace (so the terminal groups it under the actor and it stays out of
   `command_history`).
4. **`PlainRenderer._format()`** — add an `if c is Channel.X:` branch returning the
   line shape (e.g. `f"{m.actor} [label] {m.text}"`). The bare
   `return wrap_text(m.text)` at the end is the catch-all for plain narration only.
5. **`RichTerminalRenderer`** — for a top-level line, add a `(prefix, style)` entry
   to `_LINE`; for an agent-trace line, add a `(label, style)` entry to
   `_AGENT_LABEL` (or special-case it in `_emit_agent`, as `AGENT_ACTION` is).
6. **`WebRenderer._WEB_TYPE`** (`webapp/web_parser.py`) — map the channel to a web
   `type` string; add a branch to `WebRenderer._text()` if it needs a labeled
   one-liner like the other agent channels.
7. **Emitter** — if the feature needs a new parser entry point, add a thin
   `def <name>(self, actor, text): self._emit(Channel.X, text, actor=actor)`
   shim in `parsing.py` and call it from the feature code.
8. **Test** — add a channel-focused test to `tests/test_reporting.py` using
   `CaptureRenderer` (assert on `channel`/`actor`, not formatted bytes), matching
   the existing patterns there.

Then verify:

```
uv run pytest tests/test_reporting.py -q
echo '{"tool_input":{"file_path":"'$PWD'/text_adventure_games/reporting.py"}}' | uv run python .claude/hooks/check_renderer_coverage.py
```

The coverage guard must exit 0 (no gaps) and the reporting tests must pass before
you're done. Keep edits minimal and match the surrounding style — this code is
read by first/second-year undergraduates.
