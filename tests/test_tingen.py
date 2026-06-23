"""Offline tests for the Tingen adventure (issue #108).

These prove the engine delivers #108's core claim — autonomous NPCs with
competing goals in a shared world, who can be talked to — all on the
``text_adventure_games`` engine, with no network access.
"""

from text_adventure_games.llm_client import create_llm_client, LlmConfig
from text_adventure_games.adventures.tingen import (
    build_game,
    RITUAL_THRESHOLD,
    CLUES_TO_EXPOSE,
)


def test_world_builds_with_districts_and_cast():
    game = build_game()
    for district in [
        "Iron Cross Market",
        "Saint Selena's Cathedral",
        "Cathedral Crypt",
        "Tingen Docks",
        "Raphael Cemetery",
        "Blackthorn Security Co.",
    ]:
        assert district in game.locations
    assert {"Hanass", "acolyte", "Dunn", "gravedigger"}.issubset(game.characters.keys())
    assert game.player.name == "Klein"


def test_cult_completes_ritual_autonomously():
    """With no player intervention, the cult leader pursues its goal — walk to
    the crypt, then perform the rite once corruption crests — entirely on its
    own, through the precondition/effect gate."""
    game = build_game()
    for _ in range(RITUAL_THRESHOLD + 3):
        game.do_command("look")
        if game.is_game_over():
            break
    assert game.ritual_complete
    assert game.is_game_over()


def test_player_can_talk_to_npc():
    game = build_game()
    game.do_command("go south")  # market -> cathedral
    game.do_command("go west")  # cathedral -> cemetery (the gravedigger)
    assert game.do_command("talk to gravedigger")


def test_investigate_gathers_a_clue():
    game = build_game()
    game.do_command("go east")  # market -> docks (a clue is here)
    assert game.do_command("investigate")
    assert game.clues_found == 1
    # The clue is consumed — a second search finds nothing.
    assert not game.do_command("investigate")


def test_expose_needs_evidence_then_wins():
    game = build_game()
    game.do_command("go south")  # cathedral
    game.do_command("go down")  # crypt
    # Without enough evidence the confrontation fails (precondition gate).
    assert not game.do_command("expose cult")
    assert not game.player_won
    # With evidence in hand, Klein can expose the cult and win.
    game.clues_found = CLUES_TO_EXPOSE
    assert game.do_command("expose cult")
    assert game.player_won
    assert game.is_won()


def test_hybrid_llm_brain_runs_offline():
    """NPCs wired with an LLM brain (mock provider) + scripted fallback take
    turns without error."""
    mock = create_llm_client(LlmConfig(provider="mock"))
    game = build_game(llm_client=mock)
    for _ in range(4):
        game.do_command("look")
        if game.is_game_over():
            break
    assert game.turn >= 1
