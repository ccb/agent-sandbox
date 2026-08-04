"""Tests for the output rendering seam.

These assert on *channels* (via :class:`CaptureRenderer`), not on formatted
bytes -- the pattern the design doc proposes for the rest of the suite. They
cover the Message/Channel taxonomy, verbosity gating, the plain + JSON
renderers, that the parser routes its output through the renderer, and that the
ReAct loop emits the Observe/Think/Act/Reflect channels (and keeps them out of
command_history).

Run with pytest::

    pytest tests/test_reporting.py -v
"""

import io

import pytest

from text_adventure_games import games, things
from text_adventure_games.llm_client import MockLlmClient
from text_adventure_games.npc import make_react_behavior
from text_adventure_games.reporting import (
    NORMAL,
    QUIET,
    VERBOSE,
    CaptureRenderer,
    Channel,
    JSONRenderer,
    Message,
    PlainRenderer,
    channel_visible,
    default_renderer,
)


@pytest.fixture
def tiny_game():
    """A 2-room world (Field --north--> Forest) with a player and a troll."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)
    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")
    game = games.Game(field, player, characters=[troll])
    field.add_character(troll)
    return game


# ----------------------------------------------------------------------
# Verbosity gating (design doc section 6)
# ----------------------------------------------------------------------


def test_verbosity_levels():
    # Quiet hides the agent trace; normal shows reasoning/action but not the
    # full observation; verbose shows everything.
    assert not channel_visible(Channel.AGENT_REASONING, QUIET)
    assert channel_visible(Channel.NARRATION, QUIET)

    assert channel_visible(Channel.AGENT_REASONING, NORMAL)
    assert channel_visible(Channel.AGENT_ACTION, NORMAL)
    assert not channel_visible(Channel.AGENT_OBSERVATION, NORMAL)

    assert channel_visible(Channel.AGENT_OBSERVATION, VERBOSE)


def test_capture_renderer_records_and_filters():
    cap = CaptureRenderer()  # defaults to VERBOSE -> sees everything
    cap.emit(Message(Channel.NARRATION, "a room"))
    cap.emit(Message(Channel.AGENT_REASONING, "hmm", actor="troll"))
    assert cap.texts(Channel.NARRATION) == ["a room"]
    assert cap.by_channel(Channel.AGENT_REASONING)[0].actor == "troll"


def test_capture_renderer_honors_level():
    cap = CaptureRenderer(level=NORMAL)
    cap.emit(Message(Channel.AGENT_OBSERVATION, "big context", actor="troll"))
    cap.emit(Message(Channel.AGENT_REASONING, "hmm", actor="troll"))
    # The observation is gated out at normal; the reasoning gets through.
    assert cap.by_channel(Channel.AGENT_OBSERVATION) == []
    assert len(cap.by_channel(Channel.AGENT_REASONING)) == 1


# ----------------------------------------------------------------------
# PlainRenderer
# ----------------------------------------------------------------------


def test_plain_renderer_formats_agent_trace():
    buf = io.StringIO()
    r = PlainRenderer(level=VERBOSE, stream=buf)
    r.emit(Message(Channel.AGENT_REASONING, "escalate", actor="troll"))
    r.emit(Message(Channel.AGENT_ACTION, "growl player", actor="troll"))
    out = buf.getvalue()
    assert "troll [reasoning] escalate" in out
    assert "troll [action] growl player" in out


def test_plain_renderer_drops_observation_at_normal():
    buf = io.StringIO()
    r = PlainRenderer(level=NORMAL, stream=buf)
    r.emit(Message(Channel.AGENT_OBSERVATION, "the whole scene", actor="troll"))
    assert buf.getvalue() == ""


def test_default_renderer_falls_back_without_tty(monkeypatch):
    # pytest's stdout isn't a TTY, so the default is the plain fallback even
    # when rich is installed -- which is what keeps test output deterministic.
    assert isinstance(default_renderer(), PlainRenderer)


# ----------------------------------------------------------------------
# RichTerminalRenderer: every line carries a glyph cue and bracketed channel label
# ----------------------------------------------------------------------


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_rich_renderer_labels_every_line():
    """Each rendered line opens with a glyph cue *and* names its channel in
    brackets so the *kind* of line is legible from the text alone (color is only
    a tertiary cue), and agent-trace lines are attributed to the acting
    character."""
    pytest.importorskip("rich")
    from rich.console import Console

    from text_adventure_games.reporting import RichTerminalRenderer

    buf = io.StringIO()
    # no_color keeps the literal label text un-escaped so we can assert on it.
    console = Console(file=buf, width=100, no_color=True, force_terminal=True)
    r = RichTerminalRenderer(level=VERBOSE, console=console)
    for m in [
        Message(Channel.COMMAND, "go north", turn=1),
        Message(Channel.NARRATION, "You walk north.", turn=1),
        Message(Channel.NPC_NARRATION, "The troll growls.", turn=1),
        Message(Channel.BLOCKED, "the way is blocked", turn=1),
        Message(Channel.CONFLICT, "guard got the fish first", actor="troll", turn=1),
        Message(Channel.SYSTEM, "the bells ring", turn=1),
        Message(
            Channel.AGENT_OBSERVATION,
            "A troll blocks the bridge.",
            actor="troll",
            turn=1,
        ),
        Message(Channel.AGENT_REASONING, "Escalate.", actor="troll", turn=1),
        Message(Channel.AGENT_ACTION, "growl player", actor="troll", turn=1),
        Message(Channel.AGENT_REFLECTION, "Try again.", actor="troll", turn=1),
    ]:
        r.emit(m)
    out = _strip_ansi(buf.getvalue())

    # Top-level lines carry a glyph cue followed by the bracketed kind...
    assert "> [player command] go north" in out
    assert "» [narration] You walk north." in out
    assert "» [npc] The troll growls." in out
    assert "✗ [blocked] the way is blocked" in out
    assert "⚔ [conflict] guard got the fish first" in out
    assert "· [system] the bells ring" in out
    # ...and agent-trace lines pair a glyph with the actor and the label.
    assert "◦ troll [observation] A troll blocks the bridge." in out
    assert "· troll [reasoning] Escalate." in out
    assert "▸ troll [action] growl player" in out
    assert "↺ troll [reflection] Try again." in out


# ----------------------------------------------------------------------
# JSONRenderer: the backend/viewer event surface
# ----------------------------------------------------------------------


def test_json_renderer_preserves_channels_and_attribution():
    r = JSONRenderer()
    r.emit(Message(Channel.NARRATION, "a room"))
    r.emit(Message(Channel.BLOCKED, "no can do"))
    r.emit(Message(Channel.NPC_NARRATION, "the troll growls"))
    r.emit(Message(Channel.AGENT_REASONING, "escalate", actor="troll"))
    r.emit(Message(Channel.AGENT_ACTION, "growl player", actor="troll"))
    msgs = r.drain()
    assert any(m["channel"] == "narration" and m["text"] == "a room" for m in msgs)
    assert any(m["channel"] == "blocked" and m["text"] == "no can do" for m in msgs)
    assert any(
        m["channel"] == "npc_narration" and m["text"] == "the troll growls"
        for m in msgs
    )
    assert any(
        m["channel"] == "agent_reasoning"
        and m["actor"] == "troll"
        and m["text"] == "escalate"
        for m in msgs
    )
    assert any(
        m["channel"] == "agent_action"
        and m["actor"] == "troll"
        and m["text"] == "growl player"
        for m in msgs
    )
    assert r.drain() == []  # draining clears the buffer


def test_json_renderer_drops_observation_at_normal():
    r = JSONRenderer(level=NORMAL)
    r.emit(Message(Channel.AGENT_OBSERVATION, "the whole scene", actor="troll"))
    assert r.drain() == []


# ----------------------------------------------------------------------
# Parser routes its output through the renderer
# ----------------------------------------------------------------------


def test_parser_emits_on_channels(tiny_game):
    cap = CaptureRenderer()
    tiny_game.parser.set_renderer(cap)
    tiny_game.parser.ok("a calm field")
    tiny_game.parser.fail("you can't go that way")
    tiny_game.parser.npc_ok("the troll shuffles")
    # ok() capitalizes the first character of narration.
    assert cap.texts(Channel.NARRATION) == ["A calm field"]
    assert cap.texts(Channel.BLOCKED) == ["you can't go that way"]
    assert cap.texts(Channel.NPC_NARRATION) == ["the troll shuffles"]
    # fail() still records the reason for the ReAct Reflect step.
    assert tiny_game.parser.last_fail_message == "you can't go that way"


# ----------------------------------------------------------------------
# The ReAct loop emits Observe / Think / Act / Reflect on their channels
# ----------------------------------------------------------------------


def test_react_loop_traces_all_react_channels(tiny_game):
    cap = CaptureRenderer()
    tiny_game.parser.set_renderer(cap)
    troll = tiny_game.characters["troll"]
    # First command fails (no south exit) -> Reflect -> retry north succeeds.
    mock = MockLlmClient(
        [
            "Reasoning: try south\nAction: go south",
            "Reasoning: go north instead\nAction: go north",
        ]
    )
    troll.set_behavior(make_react_behavior(mock, max_retries=2))
    troll.take_turn(tiny_game)

    assert troll.location is tiny_game.locations["Forest"]
    # Observe (once), Think (twice), Act (twice), Reflect (once after the fail).
    assert len(cap.by_channel(Channel.AGENT_OBSERVATION)) == 1
    assert cap.texts(Channel.AGENT_REASONING) == ["try south", "go north instead"]
    assert cap.texts(Channel.AGENT_ACTION) == ["go south", "go north"]
    assert len(cap.by_channel(Channel.AGENT_REFLECTION)) == 1
    assert "exit" in cap.by_channel(Channel.AGENT_REFLECTION)[0].text
    # Each trace line is attributed to the troll.
    assert all(
        m.actor == "troll"
        for m in cap.messages
        if m.channel
        in (Channel.AGENT_OBSERVATION, Channel.AGENT_REASONING, Channel.AGENT_ACTION)
    )


def test_agent_reasoning_never_enters_command_history(tiny_game):
    """The privacy invariant: an NPC's reasoning is traced for the human but
    must never land in command_history (which feeds other NPCs' observations)."""
    tiny_game.parser.set_renderer(CaptureRenderer())
    troll = tiny_game.characters["troll"]
    mock = MockLlmClient(["Reasoning: a secret plan\nAction: go north"])
    troll.set_behavior(make_react_behavior(mock))
    troll.take_turn(tiny_game)

    history_text = " ".join(e["content"] for e in tiny_game.parser.command_history)
    assert "a secret plan" not in history_text
    assert "[reasoning]" not in history_text


# ----------------------------------------------------------------------
# The conflict channel (issue #42): contention is a first-class signal
# ----------------------------------------------------------------------


def test_conflict_channel_visible_at_every_level():
    # Contention is important, so it shows even at quiet (it's a _BASE channel).
    assert channel_visible(Channel.CONFLICT, QUIET)
    assert channel_visible(Channel.CONFLICT, NORMAL)
    assert channel_visible(Channel.CONFLICT, VERBOSE)


def test_plain_renderer_formats_conflict():
    buf = io.StringIO()
    r = PlainRenderer(level=NORMAL, stream=buf)
    r.emit(Message(Channel.CONFLICT, "bob got the gem first this turn.", actor="alice"))
    assert "bob got the gem first this turn." in buf.getvalue()


def test_json_renderer_maps_conflict_channel():
    r = JSONRenderer()
    r.emit(Message(Channel.CONFLICT, "bob got the gem first", actor="alice"))
    assert r.drain() == [
        {
            "channel": "conflict",
            "text": "bob got the gem first",
            "actor": "alice",
            "turn": None,
            "phase": None,
            "meta": {},
        }
    ]


def test_parser_conflict_emits_on_conflict_channel(tiny_game):
    cap = CaptureRenderer()
    tiny_game.parser.set_renderer(cap)
    tiny_game.parser.conflict("alice", "bob got the gem first")
    msgs = cap.by_channel(Channel.CONFLICT)
    assert len(msgs) == 1
    assert msgs[0].actor == "alice"
    assert msgs[0].text == "bob got the gem first"
    # A lost contest is the actor's private setback; like the agent trace it must
    # not leak into command_history (which feeds other characters' observations).
    history_text = " ".join(e["content"] for e in tiny_game.parser.command_history)
    assert "got the gem first" not in history_text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
