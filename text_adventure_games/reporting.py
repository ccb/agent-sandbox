"""Output rendering: a typed ``Message`` + a pluggable ``Renderer`` seam.

This is the ``reporting.py`` the appendix of ``docs/design/multi-character-play.md``
anticipated, designed in ``docs/design/output-and-trace-rendering.md``.

The idea: the engine emits a :class:`Message` tagged with a :class:`Channel` (what
*kind* of information it is -- world narration, an error, an agent's private
reasoning, ...). A :class:`Renderer` decides how those messages *look* on one
surface (a colored terminal, the web app, a test capture). Swap the renderer, not
the engine, and the same game prints to a terminal, buffers dicts for Flask, or
records structured messages for a test.

Renderers here:

* :class:`PlainRenderer` -- no color/markup; the guaranteed fallback (used when
  ``rich`` isn't installed, when stdout isn't a TTY, or when ``NO_COLOR`` is set)
  and what keeps test output deterministic.
* :class:`RichTerminalRenderer` -- colored, turn-structured terminal output via
  ``rich``. Imported lazily so the engine never *hard*-requires ``rich``.
* :class:`CaptureRenderer` -- records messages for tests to assert on *channels*,
  not formatted bytes.

The web renderer lives next to the Flask app in
``text_adventure_games/webapp/web_parser.py`` (it speaks the template's
``{"type", "text"}`` dicts).
"""

from __future__ import annotations

import os
import sys
import textwrap
from dataclasses import dataclass, field
from enum import Enum


class Channel(Enum):
    """What *kind* of information a :class:`Message` carries.

    Each value is the meaning of the message, independent of how any surface
    draws it. These promote the web UI's ad-hoc message ``type`` strings into a
    first-class engine concept.
    """

    NARRATION = "narration"  # world / action result (Parser.ok)
    NPC_NARRATION = "npc_narration"  # an NPC's action result (Parser.npc_ok)
    BLOCKED = "blocked"  # an action failed a precondition (Parser.fail)
    CONFLICT = "conflict"  # two characters contended for one thing (Parser.conflict)
    COMMAND = "command"  # the actor's echoed command
    AGENT_OBSERVATION = "agent_observation"  # ReAct "Observe"
    AGENT_REASONING = "agent_reasoning"  # ReAct "Think"
    AGENT_ACTION = "agent_action"  # ReAct chosen command
    AGENT_REFLECTION = "agent_reflection"  # ReAct "Reflect" after a failure
    SYSTEM = "system"  # turn header, clock, meta-command, game-over


# The agent's private ReAct trace -- never enters command_history, and the
# terminal renderer groups these under their actor with a turn rule above them.
AGENT_CHANNELS = frozenset(
    {
        Channel.AGENT_OBSERVATION,
        Channel.AGENT_REASONING,
        Channel.AGENT_ACTION,
        Channel.AGENT_REFLECTION,
    }
)


@dataclass
class Message:
    """One thing the engine wants to show.

    ``channel`` is the meaning; ``text`` is the raw (un-wrapped) content -- each
    renderer wraps/escapes as needed. ``actor`` is which character it's about,
    ``turn`` is which turn (for grouping and turn rules), and ``meta`` carries
    extras (e.g. a failure reason). ``phase`` is reserved for the simultaneous
    turn mode (#30) and is unused today.
    """

    channel: Channel
    text: str
    actor: str | None = None
    turn: int | None = None
    phase: str | None = None  # "gather"/"resolve" in simultaneous mode (#30)
    meta: dict = field(default_factory=dict)


# ----------------------------------------------------------------------
# Verbosity: which channels a renderer shows (see design doc section 6)
# ----------------------------------------------------------------------

QUIET = "quiet"
NORMAL = "normal"
VERBOSE = "verbose"

_BASE = {
    Channel.NARRATION,
    Channel.NPC_NARRATION,
    Channel.BLOCKED,
    Channel.CONFLICT,
    Channel.COMMAND,
    Channel.SYSTEM,
}
_LEVEL_CHANNELS = {
    QUIET: _BASE,
    NORMAL: _BASE
    | {Channel.AGENT_REASONING, Channel.AGENT_ACTION, Channel.AGENT_REFLECTION},
    VERBOSE: set(Channel),  # everything, including AGENT_OBSERVATION
}


def channel_visible(channel: Channel, level: str) -> bool:
    """Whether *channel* is shown at verbosity *level*."""
    return channel in _LEVEL_CHANNELS.get(level, _LEVEL_CHANNELS[NORMAL])


def wrap_text(text: str, width: int = 80) -> str:
    """Wrap each line to *width* columns (preserving existing newlines)."""
    return "\n".join(textwrap.fill(line, width) for line in text.split("\n"))


# ----------------------------------------------------------------------
# The Renderer seam
# ----------------------------------------------------------------------


class Renderer:
    """Consume :class:`Message`\\ s and render them for one surface.

    Subclasses override :meth:`emit`. ``turn_header`` and ``flush`` are optional
    hooks. ``level`` gates which channels are shown (see :func:`channel_visible`).
    """

    level: str = NORMAL

    def emit(self, message: Message) -> None:
        raise NotImplementedError

    def turn_header(self, turn: int, time: str | None = None) -> None:
        pass

    def flush(self) -> None:
        pass

    def _visible(self, message: Message) -> bool:
        return channel_visible(message.channel, self.level)


class PlainRenderer(Renderer):
    """Color-free terminal output: one wrapped block per visible message.

    The guaranteed fallback (no ``rich`` needed) and what tests/logs use, so
    output stays deterministic. Agent-trace lines keep the legacy
    ``name [reasoning] ...`` / ``name [action] ...`` shape.
    """

    def __init__(self, level: str = NORMAL, stream=None):
        self.level = level
        self.stream = stream if stream is not None else sys.stdout

    def emit(self, message: Message) -> None:
        if not self._visible(message):
            return
        print(self._format(message), file=self.stream)

    def turn_header(self, turn: int, time: str | None = None) -> None:
        label = f"Turn {turn}" + (f" ({time})" if time else "")
        print(f"-- {label} " + "-" * max(0, 60 - len(label)), file=self.stream)

    def _format(self, m: Message) -> str:
        c = m.channel
        if c is Channel.AGENT_REASONING:
            return wrap_text(f"{m.actor} [reasoning] {m.text}")
        if c is Channel.AGENT_ACTION:
            return wrap_text(f"{m.actor} [action] {m.text}")
        if c is Channel.AGENT_REFLECTION:
            return wrap_text(f"{m.actor} [reflect] {m.text}")
        if c is Channel.AGENT_OBSERVATION:
            return wrap_text(f"{m.actor} [observe]\n{m.text}")
        if c is Channel.CONFLICT:
            return wrap_text(f"⚔ {m.text}")
        if c is Channel.COMMAND:
            return f"> {m.text}"
        return wrap_text(m.text)  # NARRATION, NPC_NARRATION, BLOCKED, SYSTEM


class RichTerminalRenderer(Renderer):
    """Colored, labeled, turn-structured terminal output via ``rich``.

    Every line carries a bracketed label naming its channel -- ``[narration]``,
    ``[action]``, ``[observation]``, ... -- so the *kind* of line is legible from
    the text alone; color is only a secondary cue (which keeps the trace readable
    even when several channels share a hue). Agent-trace lines are additionally
    attributed to the acting character (``troll [reasoning] ...``), matching the
    :class:`PlainRenderer`. A turn rule is drawn lazily -- when the first
    agent/NPC line of a new turn arrives -- so there are no empty headers. Never
    instantiated unless ``rich`` imports (see :func:`default_renderer`).
    """

    def __init__(self, level: str = NORMAL, console=None):
        from rich.console import Console

        self.level = level
        self.console = console if console is not None else Console()
        self._last_turn = None

    # channel -> (label, style) for the indented agent-trace lines. AGENT_ACTION
    # is special-cased in emit(); the rest are looked up here.
    _AGENT_LABEL = {
        Channel.AGENT_OBSERVATION: ("[observation]", "dim cyan"),
        Channel.AGENT_REASONING: ("[reasoning]", "cyan"),
        Channel.AGENT_REFLECTION: ("[reflection]", "yellow"),
    }
    # channel -> (label, style) for the top-level lines. The bracketed label is
    # what makes each line legible regardless of color; the color is only a
    # secondary cue, so the styles are kept distinct across channels (no two
    # greens).
    _LINE = {
        Channel.COMMAND: ("[player command]", "bold yellow"),
        Channel.NARRATION: ("[narration]", "green"),
        Channel.NPC_NARRATION: ("[npc]", "magenta"),
        Channel.BLOCKED: ("[blocked]", "red"),
        Channel.CONFLICT: ("[conflict]", "bold yellow"),
        Channel.SYSTEM: ("[system]", "dim"),
    }

    def turn_header(self, turn: int, time: str | None = None) -> None:
        from rich.text import Text

        label = f"Turn {turn}" + (f" · {time}" if time else "")
        self.console.rule(Text(label, style="bold cyan"), align="left")
        self._last_turn = turn

    def emit(self, message: Message) -> None:
        if not self._visible(message):
            return
        # Lazy turn rule: only when an agent/NPC line opens a new turn, so the
        # player's own command never draws an empty header above it.
        if (
            message.turn is not None
            and message.turn != self._last_turn
            and message.channel
            in AGENT_CHANNELS | {Channel.NPC_NARRATION, Channel.CONFLICT}
        ):
            self.turn_header(message.turn, message.meta.get("time"))

        from rich.text import Text

        if message.channel in AGENT_CHANNELS:
            # Agent-trace lines name the acting character: "troll [reasoning] ...".
            if message.channel is Channel.AGENT_ACTION:
                label, style = "[action]", "bold cyan"
            else:
                label, style = self._AGENT_LABEL[message.channel]
            who = f"{message.actor} " if message.actor else ""
            prefix = f"{who}{label} "
        else:
            # Every other line stands alone: "[narration] ...".
            label, style = self._LINE.get(message.channel, ("", ""))
            prefix = f"{label} " if label else ""

        # Align continuation lines (e.g. a multi-line observation) under the body.
        body = message.text.replace("\n", "\n" + " " * len(prefix))
        self.console.print(Text(f"{prefix}{body}", style=style or None))


class CaptureRenderer(Renderer):
    """Record messages instead of rendering them, for tests.

    Defaults to :data:`VERBOSE` so a test sees every channel. Assert on
    ``channel`` (and ``actor``/``text``), not on formatted bytes.
    """

    def __init__(self, level: str = VERBOSE):
        self.level = level
        self.messages: list[Message] = []

    def emit(self, message: Message) -> None:
        if self._visible(message):
            self.messages.append(message)

    def by_channel(self, channel: Channel) -> list[Message]:
        return [m for m in self.messages if m.channel is channel]

    def texts(self, channel: Channel) -> list[str]:
        return [m.text for m in self.by_channel(channel)]

    def drain(self) -> list[Message]:
        msgs = list(self.messages)
        self.messages = []
        return msgs


def _level_from_env(default: str = NORMAL) -> str:
    level = os.environ.get("OUTPUT_LEVEL", "").strip().lower()
    return level if level in (QUIET, NORMAL, VERBOSE) else default


def default_renderer(level: str | None = None) -> Renderer:
    """Pick a terminal renderer.

    ``rich`` when it's importable and the output is an interactive TTY (and
    ``NO_COLOR`` is unset); otherwise the plain fallback -- which keeps pytest,
    pipes, and CI clean. Verbosity comes from ``OUTPUT_LEVEL`` (quiet/normal/
    verbose) unless given explicitly.
    """
    if level is None:
        level = _level_from_env()
    if os.environ.get("NO_COLOR"):
        return PlainRenderer(level=level)
    try:
        import rich  # noqa: F401
    except ImportError:
        return PlainRenderer(level=level)
    if not getattr(sys.stdout, "isatty", lambda: False)():
        return PlainRenderer(level=level)
    try:
        return RichTerminalRenderer(level=level)
    except Exception:
        return PlainRenderer(level=level)
