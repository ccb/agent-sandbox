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

from homeworks.hw1_llm import build_llm_game
from text_adventure_games.llm_client import (
    LlmConfig,
    MockReActClient,
    _mock_brain_choose,
    client_from_env,
    create_llm_client,
)
from text_adventure_games.webapp.web_parser import WebParser


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
    assert _mock_brain_choose(TROLL_SYSTEM, DRAWBRIDGE_OBS) == "growl player"
    # Its own growl shows up in the observation history: escalate to snarl.
    growled = (
        DRAWBRIDGE_OBS
        + "\n\nRecent events:\n  Game: Troll growls menacingly at The player."
    )
    assert _mock_brain_choose(TROLL_SYSTEM, growled) == "snarl player"
    # After snarling: attack -- deliberately without naming a weapon.
    snarled = growled + "\n  Game: Troll snarls and bares its teeth at The player."
    assert _mock_brain_choose(TROLL_SYSTEM, snarled) == "attack player"
    # The Reflect step appended the parser's failure reason: name the club.
    reflected = (
        snarled
        + "\n\nYour previous command 'attack player' failed: troll doesn't have a weapon.\n"
        "Reflect on why it failed and choose a different action."
    )
    assert _mock_brain_choose(TROLL_SYSTEM, reflected) == "attack player with club"


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
    assert _mock_brain_choose(original, DRAWBRIDGE_OBS) == "growl player"


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

    # The NPC's turns flowed through LLMAgent.chat(), not a scripted behavior.
    assert mock.calls, "the agent never consulted the LLM"

    # Escalation driven by observation history.
    npc_actions = by_type(messages, "npc_action")
    assert any("growls menacingly" in m for m in npc_actions), "missing growl"
    assert any("snarls and bares" in m for m in npc_actions), "missing snarl"

    # The bare 'attack player' was rejected by the precondition gate...
    errors = by_type(messages, "error")
    assert any("doesn't have a weapon" in m for m in errors), "attack was not gated"

    # ...and the Reflect step fed the parser's real failure reason back.
    reflect_prompts = [
        call["messages"][-1]["content"]
        for call in mock.calls
        if "' failed:" in call["messages"][-1]["content"]
    ]
    assert reflect_prompts, "no reflect retry happened"
    assert any("doesn't have a weapon" in p for p in reflect_prompts)

    # The corrected command passed the gate and applied real effects.
    assert any("attacked" in m for m in by_type(messages, "output"))
    assert game.player.get_property("is_unconscious") is True


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

    npc_actions = by_type(messages, "npc_action")
    assert any("You don't belong here" in m for m in npc_actions), "missing warn"
    assert any("LAST warning" in m for m in npc_actions), "missing threaten"
    assert any("attacked" in m for m in by_type(messages, "output"))
    assert game.player.get_property("is_unconscious") is True
    assert mock.calls


def test_react_ghost_haunts_then_kills(live_game):
    game, mock = live_game

    # Teleport into the dungeon (same shortcut test_npc_behaviors.py uses).
    game.player.location.remove_character(game.player)
    dungeon = game.locations["Dungeon"]
    dungeon.add_character(game.player)
    game.player.location = dungeon

    messages = run_commands(game, ["look", "wait"])

    npc_actions = by_type(messages, "npc_action")
    assert any("Leave this place, mortal" in m for m in npc_actions), "missing haunt"
    assert any("icy hand" in m for m in npc_actions), "missing ghost touch"
    assert game.player.get_property("is_dead") is True
    assert mock.calls


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
    from homeworks.hw1_solution import action_castle
    from text_adventure_games.llm_parser import WebLlmParser

    mock = MockReActClient()
    game = action_castle.build_game(llm_client=mock)
    game.set_parser(WebLlmParser(game, mock))
    game.parser.parse_command("look")
    game.parser.get_messages()

    messages = run_commands(game, ["go out", "go north", "go east", "wait", "wait"])

    assert mock.calls, "the hybrid behavior never consulted the LLM"
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

    # All three ReAct NPCs consulted the LLM this turn...
    assert len(mock.calls) == 3
    # ...but none of them acted.
    assert by_type(messages, "npc_action") == []
    npc_commands = [
        entry["content"]
        for entry in game.parser.command_history
        if entry["role"] == "user"
        and entry["content"].startswith(("troll ", "guard ", "ghost "))
    ]
    assert npc_commands == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
