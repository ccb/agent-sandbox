"""End-to-end tests: the ReAct loop driving the live Action Castle game (issue #5).

Earlier suites exercised the ReAct loop against tiny two-room worlds
(`test_agent_layer.py`) and the real game with *scripted* NPCs
(`test_npc_behaviors.py`). This suite closes the loop: the real game, with
troll/guard/ghost driven purely by `make_react_behavior` and the `mock` LLM
provider -- so the full Observe -> Decide -> Act -> Reflect cycle runs offline,
deterministically, and for free.

The key demonstration is `test_react_troll_escalates_and_reflect_gates_attack`:
the mock brain deliberately issues `attack player` without naming a weapon, the
parser's `check_preconditions()` rejects it ("troll doesn't have a weapon."),
the Reflect step feeds that reason back, and the agent retries with
`attack player with club` -- which succeeds.

Run with pytest::

    pytest tests/test_react_live_game.py -v
"""

import pytest

from notebooks.hw1_llm import build_llm_game
from text_adventure_games.llm_client import (
    LlmConfig,
    MockReActClient,
    _mock_brain_choose,
    client_from_env,
    create_llm_client,
)
from text_adventure_games.npc import _parse_decision
from text_adventure_games.webapp.web_parser import WebParser


def action_of(reply):
    """The command in a labeled 'Reasoning: ...\\nAction: ...' mock reply --
    parsed with the same helper LLMAgent.decide() uses, so the mock's output
    format and the agent's parser are tested as a pair."""
    return _parse_decision(reply)[1]


@pytest.fixture
def live_game():
    """The real Action Castle with mock-ReAct NPCs and a message-buffering parser.

    Returns ``(game, mock)`` so tests can assert both on game state and on the
    prompts the agents sent to the "LLM".
    """
    mock = MockReActClient()
    game = build_llm_game(mock)
    game.set_parser(WebParser(game))
    game.parser.parse_command("look")
    game.parser.get_messages()  # drain the initial look
    return game, mock


def run_commands(game, commands):
    """Run player commands, returning all parser messages they produced."""
    messages = []
    for cmd in commands:
        game.do_command(cmd)
        messages.extend(game.parser.get_messages())
    return messages


def by_type(messages, msg_type):
    return [m["text"] for m in messages if m["type"] == msg_type]


# ----------------------------------------------------------------------
# The mock provider plugs into the existing factory / env-var gating
# ----------------------------------------------------------------------


def test_mock_provider_registered():
    client = create_llm_client(LlmConfig(provider="mock"))
    assert isinstance(client, MockReActClient)


def test_client_from_env_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert isinstance(client_from_env(), MockReActClient)


def test_client_from_env_unset(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert client_from_env() is None


# ----------------------------------------------------------------------
# The mock brain's rules, in isolation
# ----------------------------------------------------------------------

TROLL_SYSTEM = (
    "You are an NPC in a text adventure game.\n" "Persona: I am the troll. I am hungry."
)

DRAWBRIDGE_OBS = (
    "DRAWBRIDGE\n"
    "You are standing on one side of a drawbridge.\n"
    "Characters here:\n"
    " * The player - You are a simple peasant destined for greatness.\n"
    "Inventory:\n"
    " * club - a heavy club\n"
    "Available actions: attack, growl, snarl\n"
    "Turn: 3"
)


def test_mock_brain_troll_escalates_from_history():
    # First contact: growl.
    assert action_of(_mock_brain_choose(TROLL_SYSTEM, DRAWBRIDGE_OBS)) == "growl player"
    # Its own growl shows up in the observation history: escalate to snarl.
    growled = (
        DRAWBRIDGE_OBS
        + "\n\nRecent events:\n  Game: Troll growls menacingly at The player."
    )
    assert action_of(_mock_brain_choose(TROLL_SYSTEM, growled)) == "snarl player"
    # After snarling: attack -- deliberately without naming a weapon.
    snarled = growled + "\n  Game: Troll snarls and bares its teeth at The player."
    assert action_of(_mock_brain_choose(TROLL_SYSTEM, snarled)) == "attack player"
    # The Reflect step appended the parser's failure reason: name the club.
    reflected = (
        snarled
        + "\n\nYour previous command 'attack player' failed: troll doesn't have a weapon.\n"
        "Reflect on why it failed and choose a different action."
    )
    assert (
        action_of(_mock_brain_choose(TROLL_SYSTEM, reflected))
        == "attack player with club"
    )


def test_mock_brain_replies_are_labeled():
    """Every mock decision uses the labeled two-line format the real LLM is
    instructed to use, so the reasoning is visible in the agent trace."""
    reply = _mock_brain_choose(TROLL_SYSTEM, DRAWBRIDGE_OBS)
    reasoning, command, _duration = _parse_decision(reply)
    assert reply.startswith("Reasoning: ")
    assert "\nAction: " in reply
    assert reasoning, "mock reply has no reasoning"
    assert command == "growl player"


def test_mock_brain_idles_when_player_absent():
    alone = DRAWBRIDGE_OBS.replace(
        " * The player - You are a simple peasant destined for greatness.\n", ""
    )
    assert _mock_brain_choose(TROLL_SYSTEM, alone) is None


def test_mock_brain_not_fooled_by_history_mentions():
    # The player left, but "The player" still appears under Recent events.
    # _player_present must only read the "Characters here:" section.
    gone = (
        "DRAWBRIDGE\n"
        "You are standing on one side of a drawbridge.\n"
        "Inventory:\n"
        " * club - a heavy club\n"
        "Turn: 5\n\n"
        "Recent events:\n"
        "  Game: Troll growls menacingly at The player."
    )
    assert _mock_brain_choose(TROLL_SYSTEM, gone) is None


def test_mock_brain_ignores_non_npc_prompts():
    # e.g. the LLM parser asking for narration: return None so callers fall
    # back to their non-LLM path.
    assert (
        _mock_brain_choose("You narrate a text adventure game.", "The player waits.")
        is None
    )


def test_mock_brain_recognizes_original_personas():
    # The webapp passes the client to build_game(), whose hybrid NPCs keep
    # the original hw1_solution personas (no "I am the {name}." prefix). The
    # brain identifies them by a distinctive persona phrase instead.
    original = (
        "You are an NPC in a text adventure game.\n"
        "Persona: I am hungry. The guard promised to feed me if I guard the "
        "drawbridge and keep people out of the castle."
    )
    assert action_of(_mock_brain_choose(original, DRAWBRIDGE_OBS)) == "growl player"


def test_mock_brain_troll_stands_down_when_fed():
    fed = DRAWBRIDGE_OBS + "\n\nRecent events:\n  Game: Troll eats the fish."
    assert _mock_brain_choose(TROLL_SYSTEM, fed) is None


# ----------------------------------------------------------------------
# The live game: ReAct NPCs in the actual turn loop
# ----------------------------------------------------------------------


def test_react_troll_escalates_and_reflect_gates_attack(live_game):
    """The core issue #5 demonstration.

    The troll observes, reasons (via the mock LLM), escalates from its own
    action history, has an attack rejected by check_preconditions(), reflects
    on the parser's failure reason, and lands the corrected attack.
    """
    game, mock = live_game
    messages = run_commands(
        game,
        [
            "go out",
            "go north",
            "go east",  # arrive at the drawbridge (troll growls)
            "wait",  # troll snarls
            "wait",  # attack fails -> Reflect -> attack with club
        ],
    )

    # The NPC's turns flowed through LLMAgent's structured tool call (not a
    # scripted behavior, and not the chat() fallback) -- this is the issue #44
    # demonstration that decisions now go through provider tool calling.
    assert mock.tool_calls, "the agent never used the structured tool path"

    # Escalation driven by observation history. The full strings pin the
    # subject too: the actor seam must attribute the action to the troll
    # (a legacy command-text scan would mis-resolve it to the player).
    npc_actions = by_type(messages, "npc_action")
    assert "Troll growls menacingly at The player." in npc_actions, "missing growl"
    assert (
        "Troll snarls and bares its teeth at The player." in npc_actions
    ), "missing snarl"

    # The bare 'attack player' was rejected by the precondition gate...
    errors = by_type(messages, "error")
    assert any("doesn't have a weapon" in m for m in errors), "attack was not gated"

    # ...and the Reflect step fed the parser's real failure reason back.
    reflect_prompts = [
        call["messages"][-1]["content"]
        for call in mock.tool_calls
        if "' failed:" in call["messages"][-1]["content"]
    ]
    assert reflect_prompts, "no reflect retry happened"
    assert any("doesn't have a weapon" in p for p in reflect_prompts)

    # The corrected command passed the gate and applied real effects.
    assert any("attacked" in m for m in by_type(messages, "output"))
    assert game.player.get_property("is_unconscious") is True

    # Every decision was traced with explicit reasoning/action labels,
    # including the failed attempt and the post-Reflect correction.
    trace = by_type(messages, "npc_log")
    assert any(m.startswith("troll [reasoning]") for m in trace), "no reasoning label"
    assert "troll [action] growl player" in trace
    assert "troll [action] attack player" in trace
    assert "troll [action] attack player with club" in trace
    assert any("which weapon" in m for m in trace), "reflect reasoning missing"

    # The trace is private: none of it leaked into command_history (which
    # feeds other NPCs' observations).
    assert not any(
        "[reasoning]" in e["content"] or "[action]" in e["content"]
        for e in game.parser.command_history
    )


def test_react_guard_warns_then_escalates(live_game):
    game, mock = live_game
    messages = run_commands(
        game,
        [
            "get pole",
            "go out",
            "go south",
            "catch fish with pole",
            "go north",
            "go north",
            "go east",  # drawbridge (troll growls)
            "give fish to troll",  # troll is no longer hungry
            "go east",  # courtyard: guard warns
            "wait",  # guard threatens
            "wait",  # guard attacks with sword
        ],
    )

    # Full strings pin the actor-seam attribution (guard, not player).
    npc_actions = by_type(messages, "npc_action")
    assert (
        'Guard warns The player: "You don\'t belong here."' in npc_actions
    ), "missing warn"
    assert (
        'Guard threatens The player: "This is your LAST warning!"' in npc_actions
    ), "missing threaten"
    assert any("attacked" in m for m in by_type(messages, "output"))
    assert game.player.get_property("is_unconscious") is True
    assert mock.tool_calls


def test_react_ghost_haunts_then_kills(live_game):
    game, mock = live_game

    # Teleport into the dungeon (same shortcut test_npc_behaviors.py uses).
    game.player.location.remove_character(game.player)
    dungeon = game.locations["Dungeon"]
    dungeon.add_character(game.player)
    game.player.location = dungeon

    messages = run_commands(game, ["look", "wait"])

    # Full strings pin the actor-seam attribution (ghost, not player).
    npc_actions = by_type(messages, "npc_action")
    assert any(
        m.startswith("Ghost turns its hollow eyes toward The player.")
        for m in npc_actions
    ), "missing haunt"
    assert (
        "Ghost plunges its icy hand into The player's chest and stops their heart."
        in npc_actions
    ), "missing ghost touch"
    assert game.player.get_property("is_dead") is True
    assert mock.tool_calls


def test_react_banished_ghost_is_gated(live_game):
    """Preconditions gate the agent even when it keeps trying: a banished
    ghost's haunt is rejected and no NPC action lands."""
    game, mock = live_game
    game.characters["ghost"].set_property("is_banished", True)

    game.player.location.remove_character(game.player)
    dungeon = game.locations["Dungeon"]
    dungeon.add_character(game.player)
    game.player.location = dungeon

    messages = run_commands(game, ["look"])

    assert by_type(messages, "npc_action") == []
    assert any("has been banished" in m for m in by_type(messages, "error"))
    assert not game.player.get_property("is_dead")


def test_webapp_hybrid_path_is_react_driven():
    """The exact webapp wiring -- build_game(llm_client=...) with hybrid
    behaviors and WebLlmParser -- is genuinely driven by ReAct when the mock
    provider is set, not by the scripted fallback. The two are distinguishable
    on the troll's third turn: the scripted troll pounds its fists, the mock
    brain attacks. (WebLlmParser.fail() must set last_fail_message for the
    Reflect retry to learn the real reason -- this is the regression test.)"""
    from notebooks.hw1_solution import action_castle
    from text_adventure_games.llm_parser import WebLlmParser

    mock = MockReActClient()
    game = action_castle.build_game(llm_client=mock)
    game.set_parser(WebLlmParser(game, mock))
    game.parser.parse_command("look")
    game.parser.get_messages()

    messages = run_commands(game, ["go out", "go north", "go east", "wait", "wait"])

    assert mock.tool_calls, "the hybrid behavior never used the structured tool path"
    npc_actions = by_type(messages, "npc_action")
    assert not any(
        "pounds its fists" in m for m in npc_actions
    ), "scripted fallback drove the troll instead of ReAct"
    assert any("attacked" in m for m in by_type(messages, "output"))
    assert game.player.get_property("is_unconscious") is True


def test_npcs_idle_when_player_absent(live_game):
    """Every NPC observes and decides each turn, but with nobody to menace
    the brain returns None and no command is routed through the parser."""
    game, mock = live_game
    messages = run_commands(game, ["wait"])  # player is alone in the cottage

    # All three ReAct NPCs consulted the LLM this turn (via the structured tool;
    # each declined, so call_tool returned None and the agent also tried the
    # chat fallback -- we assert on the structured path here).
    assert len(mock.tool_calls) == 3
    # ...but none of them acted, so there is nothing to trace either.
    assert by_type(messages, "npc_action") == []
    assert by_type(messages, "npc_log") == []
    npc_commands = [
        entry["content"]
        for entry in game.parser.command_history
        if entry["role"] == "user"
        and entry["content"].startswith(("troll ", "guard ", "ghost "))
    ]
    assert npc_commands == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
