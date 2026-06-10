from text_adventure_games import parsing
from text_adventure_games.reporting import Channel, Message, NORMAL, Renderer, wrap_text

# Channel -> the legacy web message "type" the Flask template renders as a
# `msg-<type>` CSS class. Keeping these strings stable is what lets the web UI
# (and the test suites that assert on them) work unchanged on top of the new
# Message/Channel seam.
_WEB_TYPE = {
    Channel.NARRATION: "output",
    Channel.NPC_NARRATION: "npc_action",
    Channel.BLOCKED: "error",
    Channel.CONFLICT: "conflict",
    Channel.COMMAND: "command",
    Channel.AGENT_REASONING: "npc_log",
    Channel.AGENT_ACTION: "npc_log",
    Channel.AGENT_REFLECTION: "npc_reflection",
    Channel.AGENT_OBSERVATION: "npc_observation",
    Channel.SYSTEM: "system",
}


class WebRenderer(Renderer):
    """Buffer Messages as the ``{"type", "text"}`` dicts the Flask template
    renders, then hand them over via :meth:`drain`.

    This is the web surface's renderer: it maps each :class:`Channel` to the
    legacy message ``type`` string and wraps text to 80 columns exactly as the
    old ``WebParser`` did, so the page (and the tests) are byte-for-byte
    unchanged while the engine now speaks in channels.
    """

    def __init__(self, level: str = NORMAL):
        self.level = level
        self.messages = []

    def emit(self, message: Message) -> None:
        if not self._visible(message):
            return
        self.messages.append(
            {
                "type": _WEB_TYPE.get(message.channel, "output"),
                "text": self._text(message),
            }
        )

    def _text(self, m: Message) -> str:
        # Agent-trace channels keep the legacy labeled one-liner the web UI
        # (and tests) expect: "troll [reasoning] ..." / "troll [action] ...".
        if m.channel is Channel.AGENT_REASONING:
            return wrap_text(f"{m.actor} [reasoning] {m.text}")
        if m.channel is Channel.AGENT_ACTION:
            return wrap_text(f"{m.actor} [action] {m.text}")
        if m.channel is Channel.AGENT_REFLECTION:
            return wrap_text(f"{m.actor} [reflect] {m.text}")
        return wrap_text(m.text)

    def turn_header(self, turn: int, time: str = None) -> None:
        # The web stream is not turn-ruled (matches the design doc's web mock).
        pass

    def drain(self):
        msgs = list(self.messages)
        self.messages = []
        return msgs


class WebParser(parsing.Parser):
    """Compatibility shim: a Parser that renders to a :class:`WebRenderer`.

    All output logic now lives in :class:`~text_adventure_games.parsing.Parser`
    plus the renderer; this subclass only installs the web renderer and exposes
    ``get_messages()`` so existing wiring (``WebParser(game)`` /
    ``game.parser.get_messages()``) keeps working.
    """

    def __init__(self, game, echo_commands=False):
        super().__init__(game, echo_commands=echo_commands, renderer=WebRenderer())

    def get_messages(self):
        return self.renderer.drain()
