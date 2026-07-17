"""Multi-tick conversation pacing (issue #371).

A conversation is a stateful activity spread across ticks: roughly one line per
tick, participants pinned "conversing" (they neither walk nor re-decide), each
line published on the tick it was said, and the #582 outcome pass firing only
when the conversation ends. The deterministic mock never produces an utterance,
so every conversation dies on its first empty line -> the bake is byte-identical.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_conversation_multitick_371.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend import cognition  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents, maybe_converse  # noqa: E402

_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Cafe", "description": "a cafe", "address": "T:Cafe:counter"},
]


def _persona(name):
    return {
        "name": name,
        "home": "Plaza",
        "persona": f"I am {name}.",
        "emoji": "\U0001f9d1",
        "start_tile": [0, 0],
        "destination": "Cafe",
        "activity": "reading",
        "schedule": [
            {"place": "Cafe", "activity": "reading", "emoji": None, "steps": 5}
        ],
    }


class _ScriptedConvoBrain:
    """A brain that speaks a fixed list of lines (one per converse() ask) then
    goes silent, and answers conversation_outcome inertly. Shared by both agents,
    like the classic single-brain live path -- the speaker alternates each tick,
    so the shared list drains across both."""

    def __init__(self, lines):
        self._lines = list(lines)
        self.context: dict = {}
        self.outcome_calls = 0

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        if tool["name"] == "conversation_outcome":
            self.outcome_calls += 1
            return {"plans_changed": False}
        # The engine's dialogue seam (Agent.converse) forces the "speak" tool.
        if self._lines:
            return {"utterance": self._lines.pop(0), "done": not self._lines}
        return {}  # nothing left to say -> ends the conversation


def _colocated_pair(brain):
    personas = [_persona("Maria Lopez"), _persona("Ayesha Khan")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    plaza = game.locations["Plaza"]
    order = ["Maria Lopez", "Ayesha Khan"]
    for name in order:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        plaza.add_character(ch)
    state = {n: {"performing": True, "path": None, "chat": None} for n in order}
    frame = {n: {} for n in order}
    return game, chars, state, frame, order


def test_conversation_spans_multiple_ticks_one_line_each():
    # Three lines -> three ticks with a line, then a fourth tick that ends it.
    brain = _ScriptedConvoBrain(["Hi!", "How are you?", "Good, bye!"])
    game, chars, state, frame, order = _colocated_pair(brain)
    active: dict = {}
    cooldowns: dict = {}

    # Tick 0: conversation starts, first line said, still going.
    completed = maybe_converse(
        game, chars, state, frame, 0, cooldowns, order, active=active
    )
    assert completed == 0
    assert len(active) == 1
    assert state["Maria Lopez"]["conversing"] is True
    assert state["Ayesha Khan"]["conversing"] is True
    assert frame["Maria Lopez"]["chat"] == [["Maria Lopez", "Hi!"]]
    assert brain.outcome_calls == 0  # no outcome mid-conversation

    # Tick 1: second line, transcript grows by one.
    completed = maybe_converse(
        game, chars, state, frame, 1, cooldowns, order, active=active
    )
    assert completed == 0
    assert frame["Maria Lopez"]["chat"] == [
        ["Maria Lopez", "Hi!"],
        ["Ayesha Khan", "How are you?"],
    ]

    # Tick 2: third line carries done=True -> conversation ends this tick.
    completed = maybe_converse(
        game, chars, state, frame, 2, cooldowns, order, active=active
    )
    assert completed == 1
    assert active == {}  # conversation removed
    assert state["Maria Lopez"]["conversing"] is False
    assert state["Ayesha Khan"]["conversing"] is False
    assert brain.outcome_calls == 2  # outcome fires once per participant, on end
    assert cooldowns  # cooldown recorded on end
    # Full transcript on both cards.
    assert len(frame["Maria Lopez"]["chat"]) == 3


def test_max_exchanges_caps_across_ticks():
    # Ramble forever; the cap ends the conversation after max_exchanges lines.
    brain = _ScriptedConvoBrain([f"line{i}" for i in range(50)])
    game, chars, state, frame, order = _colocated_pair(brain)
    active: dict = {}
    cooldowns: dict = {}
    total = 0
    for step in range(10):
        total += maybe_converse(
            game,
            chars,
            state,
            frame,
            step,
            cooldowns,
            order,
            active=active,
            max_exchanges=4,
        )
    assert total == 1  # exactly one conversation, capped and completed
    assert active == {}
    assert len(frame["Maria Lopez"]["chat"]) == 4


def test_mock_brain_never_converses_and_stays_inert():
    personas = [_persona("Maria Lopez"), _persona("Ayesha Khan")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=None)  # mock brain
    plaza = game.locations["Plaza"]
    order = ["Maria Lopez", "Ayesha Khan"]
    for name in order:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        plaza.add_character(ch)
    state = {n: {"performing": True, "path": None, "chat": None} for n in order}
    frame = {n: {} for n in order}
    active: dict = {}

    completed = maybe_converse(game, chars, state, frame, 0, {}, order, active=active)

    assert completed == 0
    assert active == {}
    # chat stays None (never written) -> the frame is byte-identical to today.
    assert state["Maria Lopez"]["chat"] is None
    assert "chat" not in frame["Maria Lopez"]
    assert state["Maria Lopez"].get("conversing") in (None, False)
