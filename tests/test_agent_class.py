"""Unit tests for the Agent decision seam (issue #3).

The seam is ``Agent.decide(observation) -> command``: a pure function from an
observation string to a single game-command string, with pluggable LLM and
scripted backends behind one interface (see
``docs/design/multi-character-play.md`` §4). These tests exercise the seam in
isolation -- no game, no parser -- plus one end-to-end check that an
``LLMAgent`` can drive a character through the parser via the existing
behavior bridge.

Run with pytest::

    pytest tests/test_agent_class.py -v
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.llm_client import MockLlmClient
from text_adventure_games.npc import (
    Agent,
    LLMAgent,
    ScriptedAgent,
    make_react_behavior,
)


# ----------------------------------------------------------------------
# The seam in isolation (no game, no parser)
# ----------------------------------------------------------------------


def test_agent_base_decide_is_abstract():
    """The base Agent defines the seam but leaves the backend to subclasses."""
    with pytest.raises(NotImplementedError):
        Agent(persona="I am here.").decide("anything")


def test_llmagent_decide_returns_command():
    mock = MockLlmClient(["go north"])
    agent = LLMAgent(mock, persona="I am a troll.")
    assert agent.decide("You are in a field.") == "go north"
    assert len(mock.calls) == 1


def test_llmagent_decide_puts_persona_and_goals_in_system_message():
    """Persona and goals are the agent's, sent as the system message; the
    observation is the user message. decide() stays a pure (str) -> str seam."""
    mock = MockLlmClient(["wait"])
    agent = LLMAgent(
        mock, persona="I am a lonely gravedigger.", goals=["find a friend"]
    )
    agent.decide("You are in the churchyard.")

    system = mock.calls[0]["messages"][0]
    user = mock.calls[0]["messages"][1]
    assert system["role"] == "system"
    assert "lonely gravedigger" in system["content"]
    assert "find a friend" in system["content"]
    assert user == {"role": "user", "content": "You are in the churchyard."}


def test_llmagent_decide_takes_first_line_only():
    mock = MockLlmClient(["go north\nthen I will eat the player"])
    agent = LLMAgent(mock)
    assert agent.decide("obs") == "go north"


def test_llmagent_decide_returns_none_on_llm_failure():
    """A None reply (simulated API failure) yields None, not a crash."""
    mock = MockLlmClient(default=None)
    agent = LLMAgent(mock)
    assert agent.decide("obs") is None


def test_llmagent_decide_returns_none_on_blank_reply():
    mock = MockLlmClient(["   "])
    agent = LLMAgent(mock)
    assert agent.decide("obs") is None


def test_llmagent_supports_legacy_callable():
    """Backwards compat: a plain (str) -> str callable still works as a backend."""
    seen = {}

    def legacy(prompt):
        seen["prompt"] = prompt
        return "take sword"

    agent = LLMAgent(legacy, persona="I am greedy.")
    assert agent.decide("You see a sword.") == "take sword"
    assert "I am greedy." in seen["prompt"]
    assert "You see a sword." in seen["prompt"]


def test_scriptedagent_decide_runs_rule_on_observation():
    """The deterministic backend: a rule (observation) -> command."""

    def rule(obs):
        return "take shovel" if "churchyard" in obs else "look"

    agent = ScriptedAgent(rule)
    assert agent.decide("You are in the churchyard.") == "take shovel"
    assert agent.decide("You are in the field.") == "look"


def test_backends_are_interchangeable_behind_decide():
    """The whole point of the seam: caller can't tell LLM from scripted."""
    llm = LLMAgent(MockLlmClient(["go north"]))
    scripted = ScriptedAgent(lambda obs: "go north")
    for agent in (llm, scripted):
        assert agent.decide("You are in a field.") == "go north"


# ----------------------------------------------------------------------
# The seam end-to-end, through the parser's precondition gate
# ----------------------------------------------------------------------


@pytest.fixture
def tiny_game():
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)

    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")

    game = games.Game(field, player, characters=[troll])
    field.add_character(troll)
    return game


def test_llmagent_drives_character_through_parser(tiny_game):
    from text_adventure_games.webapp.web_parser import WebParser

    tiny_game.set_parser(WebParser(tiny_game))
    troll = tiny_game.characters["troll"]
    troll.set_behavior(make_react_behavior(MockLlmClient(["go north"])))

    troll.take_turn(tiny_game)
    assert troll.location is tiny_game.locations["Forest"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
