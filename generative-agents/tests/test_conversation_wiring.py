"""Offline tests for conversation wired into the Smallville port (issue #86).

The engine dialogue seam is covered in ``tests/test_conversation.py`` (one level
up). These cover the *port-side* wiring:

* :func:`~backend.smallville_agents.maybe_converse` makes co-located, settled
  residents talk, writes the dialogue into both memory streams, surfaces it on
  both replay cards as a list of ``[speaker, line]`` pairs, and throttles a pair
  with a cooldown; and
* a default (mock) ``simulate`` run holds no conversations -- every frame's
  ``chat`` stays ``None`` -- so the exported replay is byte-identical.

Fully offline (``build_world`` + a scripted fake brain, no maze assets, no LLM).
Run from ``generative-agents``::

    uv run pytest tests/test_conversation_wiring.py -v
"""

import pytest

from backend.build_world import PERSONAS, build_world
from backend.run_simulation import simulate
from backend.smallville_agents import (
    CONVERSATION_COOLDOWN_STEPS,
    attach_agents,
    maybe_converse,
)
from backend.world_map import WorldMap

from synthetic_ville import build_synthetic_ville


@pytest.fixture(scope="module")
def world_map(tmp_path_factory):
    ville = build_synthetic_ville(str(tmp_path_factory.mktemp("ville")))
    return WorldMap(ville)


class _ChattyBrain:
    """A fake brain whose ``speak`` tool returns a one-line, wrap-up utterance.

    Every agent in the port shares one brain object, so the line is generic; the
    ``done`` flag keeps each meeting to a single line for a deterministic test.
    A non-``speak`` tool (the decision path) gets a harmless perform answer.
    """

    def __init__(self):
        self.context = {}

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        if tool["name"] == "speak":
            return {"utterance": "Nice to see you!", "done": True}
        return {"reasoning": "t", "action": "perform", "arguments": "chatting"}

    def chat(self, messages, max_tokens=256, temperature=0.0):
        return None

    def count_tokens(self, text):
        return len(text.split())


def _settle_together(chars, a_name, b_name, state):
    """Put two personas in the same room and mark both settled (not walking)."""
    a, b = chars[a_name], chars[b_name]
    b.location.remove_character(b)
    a.location.add_character(b)
    for name in (a_name, b_name):
        state[name] = {"performing": True, "path": [], "chat": None}
    return a, b


def test_maybe_converse_makes_colocated_settled_agents_talk():
    game, chars = build_world()
    attach_agents(chars, PERSONAS, llm_client=_ChattyBrain())
    order = [p["name"] for p in PERSONAS]
    state = {name: {"performing": False, "path": [1], "chat": None} for name in order}
    a, b = _settle_together(chars, order[0], order[1], state)
    frame = {a.name: {"chat": None}, b.name: {"chat": None}}
    cooldowns = {}

    n = maybe_converse(game, chars, state, frame, 10, cooldowns, order)

    assert n == 1
    # Both participants' cards carry the dialogue as [speaker, line] pairs.
    for name in (a.name, b.name):
        assert frame[name]["chat"] == [[a.name, "Nice to see you!"]]
        assert state[name]["chat"] == [[a.name, "Nice to see you!"]]
    # The line is in both memory streams (as CHAT).
    for char in (a, b):
        kinds = [r.kind.value for r in char.agent.memory.records]
        assert "chat" in kinds


def test_maybe_converse_respects_cooldown():
    game, chars = build_world()
    attach_agents(chars, PERSONAS, llm_client=_ChattyBrain())
    order = [p["name"] for p in PERSONAS]
    state = {name: {"performing": False, "path": [1], "chat": None} for name in order}
    _settle_together(chars, order[0], order[1], state)
    frame = {order[0]: {"chat": None}, order[1]: {"chat": None}}
    cooldowns = {}

    assert maybe_converse(game, chars, state, frame, 0, cooldowns, order) == 1
    # Immediately again -> throttled, no new conversation.
    assert maybe_converse(game, chars, state, frame, 5, cooldowns, order) == 0
    # After the cooldown elapses -> they may talk again.
    later = CONVERSATION_COOLDOWN_STEPS + 1
    assert maybe_converse(game, chars, state, frame, later, cooldowns, order) == 1


def test_maybe_converse_skips_walking_agents():
    game, chars = build_world()
    attach_agents(chars, PERSONAS, llm_client=_ChattyBrain())
    order = [p["name"] for p in PERSONAS]
    state = {name: {"performing": False, "path": [1], "chat": None} for name in order}
    a, b = _settle_together(chars, order[0], order[1], state)
    state[a.name]["path"] = [(1, 2)]  # a is still walking -> not eligible
    frame = {a.name: {"chat": None}, b.name: {"chat": None}}
    assert maybe_converse(game, chars, state, frame, 0, {}, order) == 0


def test_default_mock_simulate_holds_no_conversations(world_map):
    # No llm_client -> conversation disabled; the mock brain never speaks, so every
    # frame's chat stays None. This is what keeps the default replay byte-identical.
    frames = simulate(world_map, num_steps=40)
    assert frames
    assert all(cell["chat"] is None for frame in frames for cell in frame.values())
