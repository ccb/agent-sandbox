"""Offline tests for the agent-to-agent conversation seam (issue #86, Phase E).

Cover the engine dialogue layer end to end without a model:

* the turn-taking loop (:func:`conversation.converse`) -- alternation, the
  dual CHAT memory write into BOTH streams, the listener's heard buffer, and the
  termination rules (decline / wrap-up / max-exchanges);
* the audibility gate (:func:`conversation.can_converse` /
  :func:`conversation.find_conversation_pairs`) over ``Game.audience_for``;
* the :class:`~text_adventure_games.npc.LLMAgent.converse` seam against a
  scripted fake client (structured ``speak`` tool + free-text fallback).

Run with::

    uv run pytest tests/test_conversation.py -v
"""

import pytest

from text_adventure_games import conversation as convo
from text_adventure_games.games import Game
from text_adventure_games.memory import MemoryKind
from text_adventure_games.npc import LLMAgent, ScriptedAgent, build_speak_tool
from text_adventure_games.things import Character, Location

# --- helpers ----------------------------------------------------------------


def _talker(lines, *, done_on_last=True):
    """A ScriptedAgent that says *lines* in order, then goes silent.

    Sets ``last_dialogue_done`` on its final line (so a meeting ends cleanly)
    unless ``done_on_last`` is False (to exercise the max-exchanges cap)."""
    it = iter(lines)
    agent = ScriptedAgent(lambda obs: None)

    def rule(observation, partner_name):
        agent.last_dialogue_done = False
        line = next(it, None)
        if line is not None and done_on_last and line == lines[-1]:
            agent.last_dialogue_done = True
        return line

    agent.converse_rule = rule
    return agent


def _two_in_a_room(a_agent, b_agent, *, same_room=True):
    """Build a game with two agent-driven characters, co-located or not."""
    here = Location("Plaza", "the plaza")
    a = Character("alice", "alice", "")
    b = Character("bob", "bob", "")
    player = Character("player", "you", "")
    here.add_character(a)
    here.add_character(player)
    if same_room:
        here.add_character(b)
    else:
        there = Location("Field", "a field")
        there.add_character(b)
    a.set_agent(a_agent)
    b.set_agent(b_agent)
    game = Game(here, player, characters=[a, b])
    return game, a, b


# --- the turn-taking loop ---------------------------------------------------


def test_converse_alternates_and_records_both_streams():
    a = _talker(["Hi Bob, how's the cafe?", "Glad to hear it. Bye!"])
    b = _talker(["Busy as ever, Alice."], done_on_last=False)  # don't end early
    game, alice, bob = _two_in_a_room(a, b)

    convo_result = convo.converse(game, alice, bob, turn=5)

    # Three lines, strictly alternating, in order.
    assert [name for name, _ in convo_result.lines] == ["alice", "bob", "alice"]
    assert convo_result.happened is True
    # Both streams hold every line, phrased from each one's point of view.
    alice_chat = [r for r in alice.agent.memory.records if r.kind is MemoryKind.CHAT]
    bob_chat = [r for r in bob.agent.memory.records if r.kind is MemoryKind.CHAT]
    assert len(alice_chat) == 3 and len(bob_chat) == 3
    assert alice_chat[0].text == 'I said to bob: "Hi Bob, how\'s the cafe?"'
    assert bob_chat[0].text == 'alice said to me: "Hi Bob, how\'s the cafe?"'
    # The partner is recorded as the memory's actor on both sides.
    assert {r.actor for r in alice_chat} == {"bob"}
    assert {r.actor for r in bob_chat} == {"alice"}
    # Memories are stamped with the conversation turn.
    assert all(r.created_turn == 5 for r in alice_chat + bob_chat)


def test_converse_delivers_to_listener_heard_buffer():
    a = _talker(["Hello!"])  # one line, then done
    b = _talker([])  # bob never gets to speak
    game, alice, bob = _two_in_a_room(a, b)
    convo.converse(game, alice, bob, turn=0)
    # Bob (the listener) heard Alice's line, mirroring the Say action.
    assert any("Hello!" in line for line in bob.heard)


def test_converse_ends_on_wrap_up_flag():
    # Alice's first line is flagged done -> bob never replies.
    a = _talker(["One and done."])
    b = _talker(["You won't hear this."])
    game, alice, bob = _two_in_a_room(a, b)
    result = convo.converse(game, alice, bob, turn=0)
    assert [t for _, t in result.lines] == ["One and done."]


def test_converse_initiator_declines_yields_nothing():
    a = _talker([])  # says nothing at all
    b = _talker(["ready to chat"])
    game, alice, bob = _two_in_a_room(a, b)
    result = convo.converse(game, alice, bob, turn=0)
    assert result.happened is False
    assert result.lines == []
    assert not [r for r in alice.agent.memory.records if r.kind is MemoryKind.CHAT]


def test_converse_caps_at_max_exchanges():
    # Both ramble forever; the cap stops them.
    a = _talker([f"a{i}" for i in range(50)], done_on_last=False)
    b = _talker([f"b{i}" for i in range(50)], done_on_last=False)
    game, alice, bob = _two_in_a_room(a, b)
    result = convo.converse(game, alice, bob, turn=0, max_exchanges=4)
    assert len(result.lines) == 4


def test_converse_requires_co_location():
    a = _talker(["Hi"])
    b = _talker(["Hi back"])
    game, alice, bob = _two_in_a_room(a, b, same_room=False)
    result = convo.converse(game, alice, bob, turn=0)
    assert result.happened is False


# --- eligibility helpers ----------------------------------------------------


def test_can_converse_gates_on_audience_and_agents():
    a = _talker(["x"])
    b = _talker(["y"])
    game, alice, bob = _two_in_a_room(a, b)
    assert convo.can_converse(game, alice, bob) is True
    assert convo.can_converse(game, alice, alice) is False  # not with self
    # A character with no agent can't hold up its end.
    bob.agent = None
    assert convo.can_converse(game, alice, bob) is False


def test_find_conversation_pairs_returns_each_pair_once():
    a = _talker(["x"])
    b = _talker(["y"])
    game, alice, bob = _two_in_a_room(a, b)
    pairs = convo.find_conversation_pairs(game)
    assert len(pairs) == 1
    names = {p[0].name for p in pairs} | {p[1].name for p in pairs}
    assert names == {"alice", "bob"}  # the player has no agent, so it's excluded


# --- Conversation dataclass -------------------------------------------------


def test_conversation_transcript_and_last_line():
    c = convo.Conversation(("alice", "bob"))
    assert c.happened is False and c.transcript() == "" and c.last_line() is None
    c.lines.append(("alice", "hi"))
    c.lines.append(("bob", "hey"))
    assert c.transcript() == "alice: hi\nbob: hey"
    assert c.last_line() == "bob: hey"


# --- LLMAgent.converse seam (scripted clients) ------------------------------


class _ToolClient:
    """A fake LlmClient whose ``call_tool`` returns a canned ``speak`` result."""

    def __init__(self, result):
        self.result = result
        self.tools_seen = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.tools_seen.append(tool["name"])
        return self.result

    def count_tokens(self, text):
        return len(text.split())


class _ChatOnlyClient:
    """A fake LlmClient with only ``chat`` (no tool calling) for the fallback."""

    def __init__(self, reply):
        self.reply = reply

    def chat(self, messages, max_tokens=256, temperature=0.0):
        return self.reply


def test_llm_agent_converse_uses_speak_tool():
    agent = LLMAgent(_ToolClient({"utterance": "  Lovely day!  ", "done": True}))
    line = agent.converse("You are talking with Bob.", "bob")
    assert line == "Lovely day!"  # trimmed
    assert agent.last_dialogue_done is True
    assert agent.llm_client.tools_seen == [build_speak_tool()["name"]]


def test_llm_agent_converse_empty_utterance_ends():
    agent = LLMAgent(_ToolClient({"utterance": "   ", "done": False}))
    assert agent.converse("obs", "bob") is None


def test_llm_agent_converse_falls_back_to_freetext():
    # No call_tool on the client -> the chat() reply is the spoken line.
    agent = LLMAgent(_ChatOnlyClient("Good morning to you."))
    assert agent.converse("obs", "bob") == "Good morning to you."
    assert agent.last_dialogue_done is False


def test_llm_agent_converse_tool_without_utterance_is_silent():
    # A mock brain answering a different schema (no 'utterance') and no chat reply
    # -> the agent says nothing, so no conversation happens. This is what keeps a
    # mock-brained run silent and byte-identical.
    class _MockishClient:
        def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
            return {"action": "perform", "arguments": "tending"}

        def chat(self, messages, max_tokens=256, temperature=0.0):
            return None

    assert LLMAgent(_MockishClient()).converse("obs", "bob") is None


def test_base_agent_converse_is_silent():
    # A plain ScriptedAgent with no converse_rule never speaks.
    assert ScriptedAgent(lambda o: "look").converse("obs", "bob") is None


# --- the single-line seam (issue #371) ------------------------------------


def test_exchange_records_one_line_and_signals_continue():
    a = _talker(["Hi Bob."], done_on_last=False)  # a line, no wrap-up flag
    b = _talker([])
    game, alice, bob = _two_in_a_room(a, b)
    convo_obj = convo.Conversation(participants=("alice", "bob"))

    cont = convo.exchange(game, convo_obj, alice, bob, turn=3)

    assert cont is True  # a line was said, no wrap-up -> may continue
    assert convo_obj.lines == [("alice", "Hi Bob.")]
    # Dual write into both streams + the listener's heard buffer (same as converse).
    alice_chat = [r for r in alice.agent.memory.records if r.kind is MemoryKind.CHAT]
    bob_chat = [r for r in bob.agent.memory.records if r.kind is MemoryKind.CHAT]
    assert len(alice_chat) == 1 and len(bob_chat) == 1
    assert any("Hi Bob." in line for line in bob.heard)
    assert alice_chat[0].created_turn == 3


def test_exchange_decline_says_nothing_and_signals_stop():
    a = _talker([])  # declines
    b = _talker(["ready"])
    game, alice, bob = _two_in_a_room(a, b)
    convo_obj = convo.Conversation(participants=("alice", "bob"))

    cont = convo.exchange(game, convo_obj, alice, bob, turn=0)

    assert cont is False
    assert convo_obj.lines == []
    assert not [r for r in alice.agent.memory.records if r.kind is MemoryKind.CHAT]


def test_exchange_wrap_up_flag_signals_stop():
    a = _talker(["One and done."])  # _talker flags last_dialogue_done on its last line
    b = _talker([])
    game, alice, bob = _two_in_a_room(a, b)
    convo_obj = convo.Conversation(participants=("alice", "bob"))

    cont = convo.exchange(game, convo_obj, alice, bob, turn=0)

    assert cont is False  # line was said, but the wrap-up flag ends it
    assert convo_obj.lines == [("alice", "One and done.")]
