#!/usr/bin/env python3
"""PostToolUse guard: every Channel must be wired through every renderer.

Background (see docs/design/output-and-trace-rendering.md): the output seam in
``text_adventure_games/reporting.py`` routes a ``Message`` to renderers by its
``Channel``. Each renderer falls back silently for an unknown channel --
``WebRenderer`` defaults the web type to ``"output"``, the terminal renderers
default to an empty prefix / the plain catch-all -- so a feature that adds a new
``Channel`` but forgets to teach the renderers will *look* fine yet render wrong.

This hook turns that silence into a warning. It fires after edits to the files
that define channels or their renderer mappings, recomputes coverage, and tells
you (and Claude) exactly which channel is unhandled on which surface, pointing at
``/sync-renderer`` to fix it.

Contract:
- Reads the PostToolUse JSON from stdin; only acts when the edited file is the
  renderer module or the web renderer. Otherwise exits 0 silently.
- If ``reporting.py`` isn't importable yet (it lands with PR #31, not on main),
  exits 0 silently -- the guard is inert until the renderer exists.
- On a coverage gap: prints the gaps to stderr and exits 2, which feeds the
  message back to Claude. The edit itself is not undone.
- When coverage is complete: exits 0 silently.
"""

import io
import json
import os
import sys

# Files whose edits could change channel coverage. Anything else -> no-op.
WATCHED_SUFFIXES = ("text_adventure_games/reporting.py", "webapp/web_parser.py")


def _read_edited_path():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return ""
    return data.get("tool_input", {}).get("file_path", "") or ""


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


def main():
    edited = _read_edited_path().replace("\\", "/")
    if not any(edited.endswith(s) for s in WATCHED_SUFFIXES):
        return 0  # not a renderer file -- nothing to check

    sys.path.insert(0, _repo_root())
    try:
        from text_adventure_games import reporting
    except Exception:
        # Renderer not present yet (pre-#31) or import broken mid-edit: stay quiet.
        return 0

    Channel = getattr(reporting, "Channel", None)
    if Channel is None:
        return 0
    all_channels = set(Channel)

    gaps = []  # (surface, channel, hint)

    # -- Verbosity: VERBOSE should be able to show everything --------------
    try:
        verbose_set = reporting._LEVEL_CHANNELS[reporting.VERBOSE]
        for c in sorted(all_channels - set(verbose_set), key=lambda x: x.name):
            gaps.append(("verbosity", c, "add to _LEVEL_CHANNELS (at least VERBOSE)"))
    except Exception:
        pass

    # -- Terminal (rich): handled if in _LINE or an agent-trace channel ----
    try:
        rich = reporting.RichTerminalRenderer
        agent_channels = set(getattr(reporting, "AGENT_CHANNELS", set()))
        line_keys = set(getattr(rich, "_LINE", {}))
        label_keys = set(getattr(rich, "_AGENT_LABEL", {}))
        handled = line_keys | agent_channels
        for c in sorted(all_channels - handled, key=lambda x: x.name):
            gaps.append(("RichTerminalRenderer", c, "add to _LINE (or AGENT_CHANNELS)"))
        # Agent channels other than AGENT_ACTION are looked up in _AGENT_LABEL;
        # a miss is a hard KeyError at render time.
        action = getattr(Channel, "AGENT_ACTION", None)
        for c in sorted((agent_channels - {action}) - label_keys, key=lambda x: x.name):
            gaps.append(("RichTerminalRenderer", c, "add to _AGENT_LABEL"))
    except Exception:
        pass

    # -- Web: every channel must be an explicit key in _WEB_TYPE -----------
    try:
        from text_adventure_games.webapp import web_parser

        web_keys = set(getattr(web_parser, "_WEB_TYPE", {}))
        for c in sorted(all_channels - web_keys, key=lambda x: x.name):
            gaps.append(("WebRenderer", c, "add to _WEB_TYPE"))
    except Exception:
        pass

    # -- Plain: functional probe. A channel that renders identically to the
    #    bare catch-all (and isn't one of its legitimate owners) is unhandled.
    try:
        legit_plain = {
            getattr(Channel, n)
            for n in ("NARRATION", "NPC_NARRATION", "BLOCKED", "SYSTEM")
            if hasattr(Channel, n)
        }
        sentinel = "Z__renderer_coverage_probe__Z"
        bare = reporting.wrap_text(sentinel)
        for c in sorted(all_channels - legit_plain, key=lambda x: x.name):
            buf = io.StringIO()
            pr = reporting.PlainRenderer(level=reporting.VERBOSE, stream=buf)
            pr.emit(reporting.Message(c, sentinel, actor="probe", turn=1))
            if buf.getvalue().strip() == bare.strip():
                gaps.append(("PlainRenderer", c, "add a case in _format()"))
    except Exception:
        pass

    if not gaps:
        return 0

    lines = ["[renderer-coverage] new/unwired Channel(s) detected:"]
    for surface, channel, hint in gaps:
        lines.append(f"  - {channel.name}: not handled by {surface} -> {hint}")
    lines.append(
        "Run /sync-renderer to wire the channel through every renderer "
        "(+ a test), or update the mappings by hand. "
        "Until then it will fall back to default rendering."
    )
    print("\n".join(lines), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
