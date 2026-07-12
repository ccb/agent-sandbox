"""Offline tests for the agent layer (issue #2).

The agent layer — the LLM client (`llm_client.py`), the LLM-enhanced parser
(`llm_parser.py`), and the ReAct NPC loop (`npc.py`) — used to be untestable
because every code path called a real OpenAI/Anthropic API. This suite uses
`MockLlmClient` to exercise all of that deterministically, offline, and without
an API key.

Run with pytest::

    pytest tests/test_agent_layer.py -v

Sections:
  A. MockLlmClient itself.
  B. LlmParser keyword-first / LLM-fallback behavior (via WebLlmParser).
  C. The npc.py ReAct loop (react + hybrid behaviors).
"""

import re

import pytest

from text_adventure_games import games, things
from text_adventure_games.llm_client import LlmClient, MockLlmClient
from text_adventure_games.llm_parser import WebLlmParser
from text_adventure_games.npc import make_hybrid_behavior, make_react_behavior
from text_adventure_games.webapp.web_parser import WebParser


@pytest.fixture
def tiny_game():
    """A small, isolated 2-room world: Field --north--> Forest.

    Contains a `player` (in the Field) and a `troll` NPC (also in the Field),
    so tests don't depend on the Action Castle geography. Each test gets a fresh
    game so state (e.g. the troll's location) stays clean.
    """
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)

    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")

    game = games.Game(field, player, characters=[troll])
    field.add_character(troll)
    return game


def pick_option_containing(keyword):
    """Return a `MockLlmClient` responder that simulates `LlmParser._pick_option`.

    The parser sends the LLM a numbered list of options in the system message
    and asks it to "Return just the number." This responder scans those numbered
    lines and returns the index of the first one whose text contains keyword
    (case-insensitive), or `None` if there's no match.
    """

    def responder(messages, max_tokens, temperature):
        system = messages[0]["content"]
        for line in system.splitlines():
            match = re.match(r"\s*(\d+)\.\s*(.*)", line)
            if match and keyword.lower() in match.group(2).lower():
                return match.group(1)
        return None

    return responder


# ----------------------------------------------------------------------
# Section A: MockLlmClient
# ----------------------------------------------------------------------


def test_mock_fifo_and_default():
    client = MockLlmClient(["one", "two"], default="DONE")
    assert client.chat([]) == "one"
    assert client.chat([]) == "two"
    assert client.chat([]) == "DONE"
    assert client.chat([]) == "DONE"
    assert len(client.calls) == 4


def test_mock_callable_responder():
    def responder(messages, max_tokens, temperature):
        return f"saw {len(messages)} message(s) @ {max_tokens} tokens"

    client = MockLlmClient(responder)
    result = client.chat([{"role": "user", "content": "hi"}], max_tokens=64)
    assert result == "saw 1 message(s) @ 64 tokens"


def test_mock_records_calls():
    client = MockLlmClient(["x"])
    client.chat([{"role": "user", "content": "hello"}], max_tokens=10, temperature=0.5)
    call = client.calls[0]
    assert call["max_tokens"] == 10
    assert call["temperature"] == 0.5
    assert call["messages"][0]["content"] == "hello"


def test_mock_count_tokens_and_protocol():
    client = MockLlmClient()
    assert isinstance(client.count_tokens("abcdefgh"), int)
    assert isinstance(client, LlmClient)


# ----------------------------------------------------------------------
# Section B: LlmParser keyword-first / LLM-fallback
# ----------------------------------------------------------------------


def test_determine_intent_keyword_no_llm(tiny_game):
    """A command resolvable by keyword must NOT call the LLM (the fast path)."""
    mock = MockLlmClient(default="SHOULD NOT BE CALLED")
    tiny_game.set_parser(WebLlmParser(tiny_game, mock))

    intent = tiny_game.parser.determine_intent("go north")
    assert intent == "go"
    assert mock.calls == []


def test_determine_intent_llm_fallback(tiny_game):
    """A command with no keyword match falls back to the LLM picker."""
    mock = MockLlmClient(pick_option_containing("Go in a direction"))
    tiny_game.set_parser(WebLlmParser(tiny_game, mock))

    intent = tiny_game.parser.determine_intent("vault the chasm")
    assert intent == "go"
    assert len(mock.calls) >= 1


def test_determine_intent_llm_returns_none(tiny_game):
    """When the LLM can't match, determine_intent returns None (no crash)."""
    mock = MockLlmClient(default=None)
    tiny_game.set_parser(WebLlmParser(tiny_game, mock))

    intent = tiny_game.parser.determine_intent("vault the chasm")
    assert intent is None


def test_get_character_llm_fallback(tiny_game):
    """When keyword matching defaults to the player but a hint is given, the
    LLM is consulted to find a better character match."""
    mock = MockLlmClient(pick_option_containing("troll"))
    tiny_game.set_parser(WebLlmParser(tiny_game, mock))

    result = tiny_game.parser.get_character("the scary one", hint="monster")
    assert result is tiny_game.characters["troll"]
    assert len(mock.calls) == 1


def test_match_item_llm_fallback(tiny_game):
    """When no item name appears in the command, the LLM picks the item."""
    mock = MockLlmClient(pick_option_containing("sword"))
    tiny_game.set_parser(WebLlmParser(tiny_game, mock))

    sword = things.Item("sword", "a short sword", "A SHARP SHORT SWORD.")
    lamp = things.Item("lamp", "a brass lamp", "A LAMP.")
    result = tiny_game.parser.match_item(
        "grab the shiny thing", {"sword": sword, "lamp": lamp}
    )
    assert result is sword


def test_get_direction_llm_fallback(tiny_game):
    """When no direction keyword appears, the LLM resolves the direction."""
    mock = MockLlmClient(pick_option_containing("Forest"))
    tiny_game.set_parser(WebLlmParser(tiny_game, mock))

    field = tiny_game.locations["Field"]
    direction = tiny_game.parser.get_direction("head toward the woods", field)
    assert direction == "north"


def test_narration_ok_fail_npc(tiny_game):
    """ok/fail/npc_ok narrate through the LLM and buffer typed messages."""
    mock = MockLlmClient(default="NARRATED TEXT")
    tiny_game.set_parser(WebLlmParser(tiny_game, mock))
    parser = tiny_game.parser
    parser.get_messages()

    parser.ok("plain description")
    msgs = parser.get_messages()
    assert any(m["type"] == "output" and "NARRATED" in m["text"] for m in msgs)

    parser.fail("you can't do that")
    msgs = parser.get_messages()
    assert any(m["type"] == "error" and "NARRATED" in m["text"] for m in msgs)

    parser.npc_ok("the troll growls")
    msgs = parser.get_messages()
    assert any(m["type"] == "npc_action" and "NARRATED" in m["text"] for m in msgs)


def test_narration_falls_back_when_llm_returns_none(tiny_game):
    """If the LLM returns None, narration uses the original description."""
    mock = MockLlmClient(default=None)
    tiny_game.set_parser(WebLlmParser(tiny_game, mock))
    parser = tiny_game.parser
    parser.get_messages()

    parser.ok("the original description")
    msgs = parser.get_messages()
    assert any("the original description" in m["text"] for m in msgs)


# ----------------------------------------------------------------------
# Section C: npc.py ReAct loop
# ----------------------------------------------------------------------


def test_react_executes_command(tiny_game):
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]
    troll.set_behavior(make_react_behavior(MockLlmClient(["go north"])))

    troll.take_turn(tiny_game)
    assert troll.location is tiny_game.locations["Forest"]


def test_react_retries_on_failure(tiny_game):
    """First command fails (no south exit); the loop retries and succeeds."""
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]
    mock = MockLlmClient(["go south", "go north"])
    troll.set_behavior(make_react_behavior(mock))

    troll.take_turn(tiny_game)
    assert troll.location is tiny_game.locations["Forest"]
    assert len(mock.calls) == 2


def test_hybrid_falls_back_to_scripted(tiny_game):
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]

    scripted_calls = []

    def scripted(character, g):
        scripted_calls.append(character.name)

    troll.set_behavior(make_hybrid_behavior(MockLlmClient(default=None), scripted))
    troll.take_turn(tiny_game)
    assert scripted_calls == ["troll"]


def test_hybrid_uses_llm_when_available(tiny_game):
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]

    scripted_calls = []

    def scripted(character, g):
        scripted_calls.append(character.name)

    troll.set_behavior(make_hybrid_behavior(MockLlmClient(["go north"]), scripted))
    troll.take_turn(tiny_game)
    assert troll.location is tiny_game.locations["Forest"]
    assert scripted_calls == []


# ----------------------------------------------------------------------
# Section D: Reflect step (failure reason fed back to LLM)
# ----------------------------------------------------------------------


def test_react_reflect_prompt_contains_failure_reason(tiny_game):
    """On retry the prompt must include the parser's actual failure message."""
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]
    # "go south" fails (no south exit); "go north" succeeds
    mock = MockLlmClient(["go south", "go north"])
    troll.set_behavior(make_react_behavior(mock, max_retries=2))

    troll.take_turn(tiny_game)

    assert troll.location is tiny_game.locations["Forest"]
    assert len(mock.calls) == 2
    # The second call's user message must contain the engine's failure text, not
    # just the generic "Choose a different action" placeholder.
    second_prompt = mock.calls[1]["messages"][-1]["content"]
    assert "go south" in second_prompt
    # The parser emits "Field does not have an exit 'south'"
    assert "does not have an exit" in second_prompt


def test_react_caps_retries(tiny_game):
    """With max_retries=2 the loop makes at most 3 LLM calls then gives up."""
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]
    # All commands fail — the troll stays put
    mock = MockLlmClient(default="go south")
    troll.set_behavior(make_react_behavior(mock, max_retries=2))

    troll.take_turn(tiny_game)

    assert troll.location is tiny_game.locations["Field"]
    assert len(mock.calls) == 3  # 1 initial + 2 retries


def test_hybrid_reflect_prompt_contains_failure_reason(tiny_game):
    """Hybrid behavior also feeds the failure reason back on retry."""
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]

    scripted_calls = []

    def scripted(character, g):
        scripted_calls.append(character.name)

    mock = MockLlmClient(["go south", "go north"])
    troll.set_behavior(make_hybrid_behavior(mock, scripted, max_retries=2))

    troll.take_turn(tiny_game)

    assert troll.location is tiny_game.locations["Forest"]
    assert scripted_calls == []
    second_prompt = mock.calls[1]["messages"][-1]["content"]
    assert "go south" in second_prompt
    assert "does not have an exit" in second_prompt


# ----------------------------------------------------------------------
# Section D: usage accounting flows through the ReAct loop (usage.py)
# ----------------------------------------------------------------------


def test_mock_chat_records_zero_cost(tiny_game):
    """Every mock call appends one zero-cost record -- the offline accounting
    path. (No game needed, but keeping the fixture import consistent.)"""
    client = MockLlmClient(["go north"])
    client.chat([{"role": "user", "content": "hi"}])
    assert len(client.ledger.records) == 1
    assert client.ledger.records[0].cost_usd == 0.0


def test_decide_and_route_attributes_calls_to_actor_and_turn(tiny_game):
    """The shared decide funnel tags each LLM call with the acting NPC and the
    current turn, so the ledger can roll cost up per agent."""
    from text_adventure_games.llm_client import MockReActClient
    from text_adventure_games.npc import LLMAgent, decide_and_route

    troll = tiny_game.characters["troll"]
    # Put the player in the room so the troll's mock brain decides to act.
    player = tiny_game.player
    observation = (
        "FIELD\nAn open grassy field.\n"
        "Characters here:\n * The player - a hero.\nInventory:\n"
    )

    client = MockReActClient()
    agent = LLMAgent(client, persona="I am the troll. I guard the drawbridge.")
    agent.action_names = ["growl", "snarl", "attack"]
    troll.set_agent(agent)

    decide_and_route(troll, tiny_game, agent, observation)

    assert client.ledger.records, "expected the decision to be recorded"
    rec = client.ledger.records[0]
    assert rec.actor == "troll"
    assert rec.turn == tiny_game.turn  # attribution picked up the game's turn


# ----------------------------------------------------------------------
# Section E: native tool loop wiring (#355) -- reflect in-conversation
# ----------------------------------------------------------------------


def _act_call(action, arguments=""):
    """A scripted choose_action tool call for the loop's call_tools queue."""
    return {
        "tool_calls": [
            {
                "name": "choose_action",
                "arguments": {"action": action, "arguments": arguments},
            }
        ]
    }


def test_decide_and_route_reflects_in_conversation(tiny_game):
    """The #355 acceptance: a failed precondition comes back as an is_error
    tool_result IN THE SAME conversation, and the model's retry then succeeds."""
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]
    # Round 1 'go south' fails (no south exit); round 2 'go north' succeeds.
    mock = MockLlmClient(
        tool_calls_responses=[_act_call("go", "south"), _act_call("go", "north")]
    )
    troll.set_behavior(make_react_behavior(mock))

    troll.take_turn(tiny_game)

    assert troll.location is tiny_game.locations["Forest"]  # the retry landed
    assert len(mock.tool_calls_log) == 2  # two rounds, one conversation
    # Round 2's request carries round 1's tool_use + an is_error tool_result.
    round2 = mock.tool_calls_log[1]["messages"]
    blocks = [b for m in round2 if isinstance(m["content"], list) for b in m["content"]]
    assert any(b.get("type") == "tool_use" for b in blocks)
    assert any(
        b.get("type") == "tool_result"
        and b.get("is_error")
        and "does not have an exit" in str(b["content"])
        for b in blocks
    )
    assert not mock.calls  # the legacy chat() reflect path did NOT run


def test_decide_and_route_no_extra_roundtrip_on_success(tiny_game):
    """A terminal action that succeeds stops the loop immediately -- one
    call_tools, no wasted confirmation round-trip."""
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]
    mock = MockLlmClient(tool_calls_responses=[_act_call("go", "north")])
    troll.set_behavior(make_react_behavior(mock))

    troll.take_turn(tiny_game)
    assert troll.location is tiny_game.locations["Forest"]
    assert len(mock.tool_calls_log) == 1


def test_decide_and_route_caps_rounds_in_conversation(tiny_game):
    """max_rounds = 1 + max_retries bounds the in-conversation retries."""
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]

    def always_fail(messages, tools, tool_choice, max_tokens, temperature):
        return _act_call("go", "south")  # no south exit -> always fails

    mock = MockLlmClient(tool_calls_responses=always_fail)
    troll.set_behavior(make_react_behavior(mock, max_retries=2))

    troll.take_turn(tiny_game)
    assert troll.location is tiny_game.locations["Field"]  # never moved
    assert len(mock.tool_calls_log) == 3  # 1 initial + 2 retries


def test_decide_and_route_falls_back_to_legacy_when_no_tool_call(tiny_game):
    """A client that makes no tool call (only chat scripted) falls through to the
    legacy string-reflection path unchanged."""
    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]
    # No tool_calls_responses -> call_tools returns None (a decline / probe), so
    # decide_and_route falls back to the chat()-driven legacy loop.
    mock = MockLlmClient(["go south", "go north"])
    troll.set_behavior(make_react_behavior(mock))

    troll.take_turn(tiny_game)
    assert troll.location is tiny_game.locations["Forest"]
    assert len(mock.calls) == 2  # chat fallback drove both attempts


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
