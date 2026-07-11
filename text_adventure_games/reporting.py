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
    DAMAGE = "damage"  # the player took a wound (Parser.damage)
    CONFLICT = "conflict"  # two characters contended for one thing (Parser.conflict)
    COMMAND = "command"  # the actor's echoed command
    AGENT_OBSERVATION = "agent_observation"  # ReAct "Observe"
    AGENT_REASONING = "agent_reasoning"  # ReAct "Think"
    AGENT_ACTION = "agent_action"  # ReAct chosen command
    AGENT_REFLECTION = "agent_reflection"  # ReAct "Reflect" after a failure
    SYSTEM = "system"  # turn header, clock, meta-command, game-over
    FIGURE = "figure"  # an illustration cue: text is a card KEY, not prose


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
    Channel.DAMAGE,
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

    def __init__(self, level: str = NORMAL, stream=None, width: int = 80):
        self.level = level
        self.stream = stream if stream is not None else sys.stdout
        self.width = width

    def emit(self, message: Message) -> None:
        if not self._visible(message):
            return
        print(self._format(message), file=self.stream)

    def turn_header(self, turn: int, time: str | None = None) -> None:
        label = f"Turn {turn}" + (f" ({time})" if time else "")
        print(f"-- {label} " + "-" * max(0, 60 - len(label)), file=self.stream)

    def _wrap(self, text: str) -> str:
        return wrap_text(text, self.width)

    def _format(self, m: Message) -> str:
        c = m.channel
        if c is Channel.AGENT_REASONING:
            return self._wrap(f"{m.actor} [reasoning] {m.text}")
        if c is Channel.AGENT_ACTION:
            return self._wrap(f"{m.actor} [action] {m.text}")
        if c is Channel.AGENT_REFLECTION:
            return self._wrap(f"{m.actor} [reflect] {m.text}")
        if c is Channel.AGENT_OBSERVATION:
            return self._wrap(f"{m.actor} [observe]\n{m.text}")
        if c is Channel.CONFLICT:
            return self._wrap(f"⚔ {m.text}")
        if c is Channel.COMMAND:
            return f"> {m.text}"
        if c is Channel.FIGURE:
            return f"[figure: {m.text}]"  # a key, not prose; VERBOSE-only
        return self._wrap(m.text)  # NARRATION, NPC_NARRATION, BLOCKED, SYSTEM


class RichTerminalRenderer(Renderer):
    """Colored, labeled, turn-structured terminal output via ``rich``.

    Every line opens with two redundant cues: a leading *glyph* (``»``, ``✗``,
    ``⚔``, ...) for a quick at-a-glance scan, and a bracketed *label* naming its
    channel in words -- ``[narration]``, ``[action]``, ``[observation]``, ... --
    so the *kind* of line is legible from the text alone. Color is only a tertiary
    cue (which keeps the trace readable even when several channels share a hue, or
    on a no-color terminal). Agent-trace lines are additionally attributed to the
    acting character (``· troll [reasoning] ...``), matching the
    :class:`PlainRenderer`. A turn rule is drawn lazily -- when the first
    agent/NPC line of a new turn arrives -- so there are no empty headers. Never
    instantiated unless ``rich`` imports (see :func:`default_renderer`).
    """

    def __init__(self, level: str = NORMAL, console=None):
        from rich.console import Console

        self.level = level
        self.console = console if console is not None else Console()
        self._last_turn = None

    # channel -> (glyph, label, style) for the indented agent-trace lines.
    # AGENT_ACTION is special-cased in emit(); the rest are looked up here.
    _AGENT_LABEL = {
        Channel.AGENT_OBSERVATION: ("◦", "[observation]", "dim cyan"),
        Channel.AGENT_REASONING: ("·", "[reasoning]", "cyan"),
        Channel.AGENT_REFLECTION: ("↺", "[reflection]", "yellow"),
    }
    # channel -> (glyph, label, style) for the top-level lines. The glyph is a
    # quick visual cue and the bracketed label names the channel in words;
    # color is only a tertiary cue, so the styles stay distinct across channels
    # (no two greens).
    _LINE = {
        Channel.COMMAND: (">", "[player command]", "bold yellow"),
        Channel.NARRATION: ("»", "[narration]", "green"),
        Channel.NPC_NARRATION: ("»", "[npc]", "magenta"),
        Channel.BLOCKED: ("✗", "[blocked]", "red"),
        Channel.DAMAGE: ("♥", "[damage]", "bold red"),
        Channel.CONFLICT: ("⚔", "[conflict]", "bold yellow"),
        Channel.SYSTEM: ("·", "[system]", "dim"),
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
            # Agent-trace lines name the acting character: "· troll [reasoning] ...".
            if message.channel is Channel.AGENT_ACTION:
                glyph, label, style = "▸", "[action]", "bold cyan"
            else:
                glyph, label, style = self._AGENT_LABEL[message.channel]
            who = f"{message.actor} " if message.actor else ""
            prefix = f"{glyph} {who}{label} "
        else:
            # Every other line stands alone: "» [narration] ...".
            glyph, label, style = self._LINE.get(message.channel, ("", "", ""))
            prefix = f"{glyph} {label} " if label else (f"{glyph} " if glyph else "")

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


def _json_safe(value):
    """Coerce a value to something ``json.dumps`` can emit (an Enum to its
    ``.value``, any other object to ``str``). Mirrors ``world_state._jsonable``
    so the change feed and the snapshot are uniformly JSON-safe."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "value"):
        return value.value
    return str(value)


class JSONRenderer(Renderer):
    """Emit each :class:`Message` as a JSON-able record -- the structured change
    feed a 2D renderer (e.g. Godot) subscribes to (issue #90).

    This is the *delta* complement of the world-state snapshot
    (:func:`text_adventure_games.world_state.world_state`): the snapshot says
    "the world is X", this feed says "X just happened". Each record is
    ``{"channel", "text", "actor", "turn", "phase", "meta"}`` with the channel as
    its string value, so ``json.dumps`` emits it directly.

    Defaults to :data:`VERBOSE`, so the feed carries every channel (including the
    agent trace). Records buffer in :attr:`records` for polling -- :meth:`drain`
    returns and clears them -- or pass a ``sink`` callable to receive each record
    live (e.g. push it down a websocket).

    Message records carry ``{channel, text, actor, turn, phase, meta}``; a turn
    boundary is a leaner ``{channel: "turn_header", turn, time}`` event.
    Consumers switch on ``channel``.
    """

    def __init__(self, level: str = VERBOSE, sink=None):
        self.level = level
        self.sink = sink
        self.records: list[dict] = []

    @staticmethod
    def record(message: Message) -> dict:
        """The JSON-able dict form of *message*."""
        return {
            "channel": message.channel.value,
            "text": message.text,
            "actor": message.actor,
            "turn": message.turn,
            "phase": message.phase,
            "meta": {str(k): _json_safe(v) for k, v in (message.meta or {}).items()},
        }

    def _push(self, record: dict) -> None:
        if self.sink is not None:
            self.sink(record)
        else:
            self.records.append(record)

    def emit(self, message: Message) -> None:
        if self._visible(message):
            self._push(self.record(message))

    def turn_header(self, turn: int, time: str | None = None) -> None:
        # A turn boundary is itself a feed event (so a renderer can group or
        # animate by turn), distinguished by its "turn_header" channel.
        self._push({"channel": "turn_header", "turn": turn, "time": time})

    def drain(self) -> list[dict]:
        recs = list(self.records)
        self.records = []
        return recs


def _level_from_env(default: str = NORMAL) -> str:
    level = os.environ.get("OUTPUT_LEVEL", "").strip().lower()
    return level if level in (QUIET, NORMAL, VERBOSE) else default


def default_renderer(
    level: str | None = None, no_color: bool | None = None, width: int = 80
) -> Renderer:
    """Pick a terminal renderer.

    ``rich`` when it's importable and the output is an interactive TTY (and
    color isn't disabled); otherwise the plain fallback -- which keeps pytest,
    pipes, and CI clean. Verbosity comes from ``OUTPUT_LEVEL`` (quiet/normal/
    verbose) unless given explicitly via *level*. Color is disabled when
    *no_color* is true, or (when *no_color* is None) when the ``NO_COLOR`` env
    var is set. *width* sets the wrap column for the plain renderer (the rich
    renderer wraps to the live terminal instead).
    """
    if level is None:
        level = _level_from_env()
    if no_color is None:
        no_color = bool(os.environ.get("NO_COLOR"))
    if no_color:
        return PlainRenderer(level=level, width=width)
    try:
        import rich  # noqa: F401
    except ImportError:
        return PlainRenderer(level=level, width=width)
    if not getattr(sys.stdout, "isatty", lambda: False)():
        return PlainRenderer(level=level, width=width)
    try:
        return RichTerminalRenderer(level=level)
    except Exception:
        return PlainRenderer(level=level, width=width)
