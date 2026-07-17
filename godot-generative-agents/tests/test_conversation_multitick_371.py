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
from backend.cognition import (  # noqa: E402
    ActiveConversation,
    attach_agents,
    maybe_converse,
)
from text_adventure_games import conversation as convo  # noqa: E402

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


def _colocated_trio(brain, names):
    """Three co-located residents, all sharing one brain -- attach_agents wires
    the same ``llm_client`` onto every persona, exactly as ``_colocated_pair``
    does for two, so a single scripted brain must answer for whichever of the
    three is asked."""
    personas = [_persona(n) for n in names]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    plaza = game.locations["Plaza"]
    for name in names:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        plaza.add_character(ch)
    state = {n: {"performing": True, "path": None, "chat": None} for n in names}
    frame = {n: {} for n in names}
    return game, chars, state, frame


class _TrioConvoBrain:
    """Shared by all three agents. Every "speak" ask gets a done-flagged line,
    so any conversation that gets a turn this tick completes on its first line
    -- which is what makes a same-tick second conversation observable. Outcome
    calls are tallied by actor name (stamped onto ``context`` right before each
    call, like the real ``apply_conversation_outcome``/``_stamp_convo_ctx``
    seams): #187 says a participant holds at most one conversation per step, so
    a name appearing twice here is exactly that violation."""

    def __init__(self):
        self.context: dict = {}
        self.outcome_by_actor: dict[str, int] = {}
        self._line_count = 0

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        actor = self.context.get("actor")
        if tool["name"] == "conversation_outcome":
            self.outcome_by_actor[actor] = self.outcome_by_actor.get(actor, 0) + 1
            return {"plans_changed": False}
        self._line_count += 1
        return {"utterance": f"line{self._line_count}", "done": True}


def test_finished_participant_not_repaired_same_tick():
    """#187: a participant whose in-progress conversation COMPLETES in phase 1
    must not be free to start a second conversation with a third party in the
    SAME tick. Bug: phase 2's ``busy`` set was computed straight from ``active``
    -- AFTER phase 1's ``del active[key]`` for anything that just finished -- so
    a just-freed participant looked exactly like someone who was never talking
    this step, and could immediately start (and finish) a second conversation.
    """
    a_name, b_name, c_name = "Maria Lopez", "Ayesha Khan", "Diego Fields"
    brain = _TrioConvoBrain()
    game, chars, state, frame = _colocated_trio(brain, [a_name, b_name, c_name])
    order = [a_name, b_name, c_name]

    # Seed an in-progress A-B conversation: one line already said, B's turn
    # next -- and the brain always answers with a done-flagged line, so A-B
    # completes this tick (phase 1).
    ac = ActiveConversation(
        a=a_name,
        b=b_name,
        convo=convo.Conversation(participants=(a_name, b_name), lines=[(a_name, "Hi")]),
        next_speaker=b_name,
        started=0,
    )
    active = {frozenset((a_name, b_name)): ac}
    state[a_name]["conversing"] = True
    state[b_name]["conversing"] = True
    # Mirror the earlier tick's publish, so a same-tick clobber is visible.
    state[a_name]["chat"] = state[b_name]["chat"] = [[a_name, "Hi"]]
    cooldowns: dict = {}

    completed = maybe_converse(
        game, chars, state, frame, 5, cooldowns, order, active=active
    )

    # Only A-B completed -- C (settled, ready to talk) never got a partner:
    # A and B are still "busy" this step even though phase 1 just freed them.
    assert completed == 1
    assert state[c_name]["chat"] is None
    # The just-finished A-B transcript survives untouched -- not overwritten by
    # a second, same-tick conversation with C.
    assert state[a_name]["chat"] == [[a_name, "Hi"], [b_name, "line1"]]
    assert state[b_name]["chat"] == state[a_name]["chat"]
    # The #582 outcome pass fires once per participant per step, never twice.
    assert brain.outcome_by_actor.get(a_name) == 1
    assert brain.outcome_by_actor.get(b_name) == 1
    assert c_name not in brain.outcome_by_actor


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
