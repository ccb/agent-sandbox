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


# --- TiledGame: audibility by tile distance (issues #82, #86) ----------------
#
# Smallville arenas are separate Locations, so the engine's room-based audience
# would never let two residents in different arenas talk. TiledGame overrides
# audience_for to measure "nearby" by tile distance (mirroring its perception
# seam), so conversation is gated by the same vision radius as sight.

from gen_agents.tiled_game import TiledGame  # noqa: E402


class _StubMap:
    """A WorldMap stand-in: ``tile_gap`` returns a fixed distance per address pair."""

    def __init__(self, gap):
        self._gap = gap

    def tile_gap(self, a, b):
        return 0 if a == b else self._gap


def _two_arenas(gap, *, with_map=True):
    """Two tile-addressed arenas ``gap`` tiles apart, an agent-driven resident in
    each (and the player parked in the first). Returns (game, alice, bob)."""
    a = Location("A", "arena A")
    b = Location("B", "arena B")
    a.tile_address = "Ville:A:spot"
    b.tile_address = "Ville:B:spot"
    a.add_connection("east", b)  # so both arenas register in game.locations
    player = Character("player", "you", "")
    alice = Character("alice", "alice", "")
    bob = Character("bob", "bob", "")
    alice.set_agent(ScriptedAgent(lambda obs: None))
    bob.set_agent(ScriptedAgent(lambda obs: None))
    a.add_character(player)
    a.add_character(alice)
    b.add_character(bob)
    game = TiledGame(
        a,
        player,
        characters=[alice, bob],
        world_map=_StubMap(gap) if with_map else None,
    )
    return game, alice, bob


def test_tiled_audience_includes_residents_within_vision_radius():
    game, alice, bob = _two_arenas(gap=3)
    alice.vision_r = 5
    audience = game.audience_for(alice, "")
    assert bob in audience
    assert alice not in audience  # a speaker never hears itself


def test_tiled_audience_excludes_residents_beyond_vision_radius():
    game, alice, bob = _two_arenas(gap=8)
    alice.vision_r = 2
    assert bob not in game.audience_for(alice, "")


def test_tiled_conversation_is_gated_by_proximity():
    # The conversation layer reads audience_for through can_converse /
    # find_conversation_pairs, so the tile gating flows straight through.
    near, alice, bob = _two_arenas(gap=3)
    alice.vision_r = bob.vision_r = 5
    assert convo.can_converse(near, alice, bob)
    assert (alice, bob) in convo.find_conversation_pairs(near, [alice, bob])

    far, carol, dave = _two_arenas(gap=20)
    carol.vision_r = dave.vision_r = 2
    assert not convo.can_converse(far, carol, dave)
    assert convo.find_conversation_pairs(far, [carol, dave]) == []


def test_tiled_audience_falls_back_to_room_without_map():
    # No world_map -> perceivable_locations yields just the speaker's arena, so
    # the audience is the engine's co-located default and bob (a separate arena)
    # is out of earshot even with a wide radius.
    game, alice, bob = _two_arenas(gap=1, with_map=False)
    alice.vision_r = 5
    assert bob not in game.audience_for(alice, "")
