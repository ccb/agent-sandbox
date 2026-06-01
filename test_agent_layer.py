"""Offline tests for the agent layer (issue #2).

The agent layer -- the LLM client (``llm_client.py``), the LLM-enhanced parser
(``llm_parser.py``), and the ReAct NPC loop (``npc.py``) -- used to be untestable
because every code path called a real OpenAI/Anthropic API. This suite uses the
new ``MockLlmClient`` to exercise all of that deterministically, offline, and for
free (no API key required).

Run it like the other suite::

    python test_agent_layer.py

Sections:
  A. MockLlmClient itself.
  B. LlmParser keyword-first / LLM-fallback behavior (via WebLlmParser).
  C. The npc.py ReAct loop (react + hybrid behaviors).
"""

import re

from text_adventure_games import games, things
from text_adventure_games.llm_client import MockLlmClient, LlmClient
from text_adventure_games.llm_parser import WebLlmParser
from text_adventure_games.webapp.web_parser import WebParser
from text_adventure_games.npc import make_react_behavior, make_hybrid_behavior

# ----------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------


def build_tiny_game():
    """Build a small, isolated 2-room world: Field --north--> Forest.

    Contains a ``player`` (in the Field) and a ``troll`` NPC (also in the Field),
    so tests don't depend on the Action Castle geography. A fresh game per test
    keeps state (e.g. the troll's location) clean between tests.
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
    """Return a MockLlmClient responder that simulates LlmParser._pick_option.

    The parser sends the LLM a numbered list of options in the system message
    and asks it to "Return just the number." This responder scans those numbered
    lines and returns the index of the first one whose text contains *keyword*
    (case-insensitive), or None if there's no match -- exactly what a competent
    LLM would do, but deterministically.
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
    assert client.chat([]) == "DONE"  # queue exhausted -> default
    assert client.chat([]) == "DONE"
    assert len(client.calls) == 4
    print("PASSED: MockLlmClient returns list responses FIFO, then the default")


def test_mock_callable_responder():
    def responder(messages, max_tokens, temperature):
        return f"saw {len(messages)} message(s) @ {max_tokens} tokens"

    client = MockLlmClient(responder)
    result = client.chat([{"role": "user", "content": "hi"}], max_tokens=64)
    assert result == "saw 1 message(s) @ 64 tokens", result
    print("PASSED: MockLlmClient supports a callable responder")


def test_mock_records_calls():
    client = MockLlmClient(["x"])
    client.chat([{"role": "user", "content": "hello"}], max_tokens=10, temperature=0.5)
    call = client.calls[0]
    assert call["max_tokens"] == 10
    assert call["temperature"] == 0.5
    assert call["messages"][0]["content"] == "hello"
    print("PASSED: MockLlmClient records every call for assertions")


def test_mock_count_tokens_and_protocol():
    client = MockLlmClient()
    assert isinstance(client.count_tokens("abcdefgh"), int)
    # The runtime-checkable LlmClient protocol requires chat() + count_tokens().
    assert isinstance(client, LlmClient)
    print("PASSED: MockLlmClient satisfies the LlmClient protocol")


# ----------------------------------------------------------------------
# Section B: LlmParser keyword-first / LLM-fallback
# ----------------------------------------------------------------------


def test_determine_intent_keyword_no_llm():
    """A command resolvable by keyword must NOT call the LLM (the fast path)."""
    game = build_tiny_game()
    mock = MockLlmClient(default="SHOULD NOT BE CALLED")
    game.set_parser(WebLlmParser(game, mock))

    intent = game.parser.determine_intent("go north")
    assert intent == "go", intent
    assert mock.calls == [], "keyword-resolvable command should make no LLM call"
    print("PASSED: determine_intent resolves keywords without calling the LLM")


def test_determine_intent_llm_fallback():
    """A command with no keyword match falls back to the LLM picker."""
    game = build_tiny_game()
    mock = MockLlmClient(pick_option_containing("Go in a direction"))
    game.set_parser(WebLlmParser(game, mock))

    intent = game.parser.determine_intent("vault the chasm")
    assert intent == "go", intent
    assert len(mock.calls) >= 1, "expected the LLM fallback to be used"
    print("PASSED: determine_intent falls back to the LLM and resolves 'go'")


def test_determine_intent_llm_returns_none():
    """When the LLM can't match, determine_intent returns None (no crash)."""
    game = build_tiny_game()
    mock = MockLlmClient(default=None)
    game.set_parser(WebLlmParser(game, mock))

    intent = game.parser.determine_intent("vault the chasm")
    assert intent is None, intent
    print("PASSED: determine_intent returns None when the LLM can't match")


def test_get_character_llm_fallback():
    """When keyword matching defaults to the player but a hint is given, the
    LLM is consulted to find a better character match."""
    game = build_tiny_game()
    mock = MockLlmClient(pick_option_containing("troll"))
    game.set_parser(WebLlmParser(game, mock))

    result = game.parser.get_character("the scary one", hint="monster")
    assert result is game.characters["troll"], result
    assert len(mock.calls) == 1
    print("PASSED: get_character LLM fallback matches the troll")


def test_match_item_llm_fallback():
    """When no item name appears in the command, the LLM picks the item."""
    game = build_tiny_game()
    mock = MockLlmClient(pick_option_containing("sword"))
    game.set_parser(WebLlmParser(game, mock))

    sword = things.Item("sword", "a short sword", "A SHARP SHORT SWORD.")
    lamp = things.Item("lamp", "a brass lamp", "A LAMP.")
    result = game.parser.match_item(
        "grab the shiny thing", {"sword": sword, "lamp": lamp}
    )
    assert result is sword, result
    print("PASSED: match_item LLM fallback matches the sword")


def test_get_direction_llm_fallback():
    """When no direction keyword appears, the LLM resolves the direction."""
    game = build_tiny_game()
    mock = MockLlmClient(pick_option_containing("Forest"))
    game.set_parser(WebLlmParser(game, mock))

    field = game.locations["Field"]
    direction = game.parser.get_direction("head toward the woods", field)
    assert direction == "north", direction
    print("PASSED: get_direction LLM fallback resolves 'north' (toward Forest)")


def test_narration_ok_fail_npc():
    """ok/fail/npc_ok narrate through the LLM and buffer typed messages."""
    game = build_tiny_game()
    mock = MockLlmClient(default="NARRATED TEXT")
    game.set_parser(WebLlmParser(game, mock))
    parser = game.parser
    parser.get_messages()  # drain anything buffered so far

    parser.ok("plain description")
    msgs = parser.get_messages()
    assert any(m["type"] == "output" and "NARRATED" in m["text"] for m in msgs), msgs

    parser.fail("you can't do that")
    msgs = parser.get_messages()
    assert any(m["type"] == "error" and "NARRATED" in m["text"] for m in msgs), msgs

    parser.npc_ok("the troll growls")
    msgs = parser.get_messages()
    assert any(
        m["type"] == "npc_action" and "NARRATED" in m["text"] for m in msgs
    ), msgs
    print("PASSED: narration produces output/error/npc_action messages")


def test_narration_falls_back_when_llm_returns_none():
    """If the LLM returns None, narration uses the original description."""
    game = build_tiny_game()
    mock = MockLlmClient(default=None)
    game.set_parser(WebLlmParser(game, mock))
    parser = game.parser
    parser.get_messages()

    parser.ok("the original description")
    msgs = parser.get_messages()
    assert any("the original description" in m["text"] for m in msgs), msgs
    print("PASSED: narration falls back to the original text when LLM returns None")


# ----------------------------------------------------------------------
# Section C: npc.py ReAct loop
# ----------------------------------------------------------------------


def test_react_executes_command():
    game = build_tiny_game()
    game.set_parser(WebParser(game))
    troll = game.characters["troll"]
    troll.set_behavior(make_react_behavior(MockLlmClient(["go north"])))

    troll.take_turn(game)
    assert troll.location is game.locations["Forest"], troll.location
    print("PASSED: ReAct loop executes the LLM's chosen command")


def test_react_retries_on_failure():
    """First command fails (no south exit); the loop retries and succeeds."""
    game = build_tiny_game()
    game.set_parser(WebParser(game))
    troll = game.characters["troll"]
    mock = MockLlmClient(["go south", "go north"])
    troll.set_behavior(make_react_behavior(mock))  # default max_retries=1

    troll.take_turn(game)
    assert troll.location is game.locations["Forest"], troll.location
    assert len(mock.calls) == 2, "expected one retry after the failed command"
    print("PASSED: ReAct loop retries after a failed command")


def test_hybrid_falls_back_to_scripted():
    game = build_tiny_game()
    game.set_parser(WebParser(game))
    troll = game.characters["troll"]

    scripted_calls = []

    def scripted(character, g):
        scripted_calls.append(character.name)

    # LLM returns None -> hybrid should use the scripted fallback.
    troll.set_behavior(make_hybrid_behavior(MockLlmClient(default=None), scripted))
    troll.take_turn(game)
    assert scripted_calls == ["troll"], scripted_calls
    print("PASSED: hybrid behavior falls back to scripted when the LLM fails")


def test_hybrid_uses_llm_when_available():
    game = build_tiny_game()
    game.set_parser(WebParser(game))
    troll = game.characters["troll"]

    scripted_calls = []

    def scripted(character, g):
        scripted_calls.append(character.name)

    troll.set_behavior(make_hybrid_behavior(MockLlmClient(["go north"]), scripted))
    troll.take_turn(game)
    assert troll.location is game.locations["Forest"], troll.location
    assert scripted_calls == [], "scripted fallback must not run when the LLM works"
    print("PASSED: hybrid behavior uses the LLM when it returns a valid command")


# ----------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------

TESTS = [
    # Section A
    test_mock_fifo_and_default,
    test_mock_callable_responder,
    test_mock_records_calls,
    test_mock_count_tokens_and_protocol,
    # Section B
    test_determine_intent_keyword_no_llm,
    test_determine_intent_llm_fallback,
    test_determine_intent_llm_returns_none,
    test_get_character_llm_fallback,
    test_match_item_llm_fallback,
    test_get_direction_llm_fallback,
    test_narration_ok_fail_npc,
    test_narration_falls_back_when_llm_returns_none,
    # Section C
    test_react_executes_command,
    test_react_retries_on_failure,
    test_hybrid_falls_back_to_scripted,
    test_hybrid_uses_llm_when_available,
]


if __name__ == "__main__":
    print("=" * 60)
    print("AGENT LAYER OFFLINE TESTS (issue #2)")
    print("=" * 60)
    for test in TESTS:
        test()
    print("=" * 60)
    print(f"ALL {len(TESTS)} TESTS PASSED")
    print("=" * 60)
