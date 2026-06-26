"""Tests for the Jungle Adventure port -- the spec of its supported commands.

Loads the sibling module by file path (so the test runs regardless of how
``test_gen`` is importable) and drives it through a CaptureRenderer, the house
pattern from docs/converting-parsely-games.md section 11.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from text_adventure_games.reporting import CaptureRenderer, Channel


def _load_module():
    path = Path(__file__).resolve().parent / "jungle_adventure.py"
    spec = importlib.util.spec_from_file_location("ja_port", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ja = _load_module()


def _play(cmds, game=None):
    if game is None:
        game = ja.build_game()
        cap = CaptureRenderer()
        game.parser.set_renderer(cap)
    else:
        cap = game.parser.renderer
    for c in cmds:
        game.do_command(c)
        if game.is_game_over():
            break
    return game, cap


def _said(cap, sub):
    """True if any player-facing text (narration or a blocked/failed message)
    contained *sub*."""
    return any(
        sub in t for ch in (Channel.NARRATION, Channel.BLOCKED) for t in cap.texts(ch)
    )


def _upto(cmd, inclusive=True):
    """The walkthrough prefix up to *cmd* (inclusive by default)."""
    idx = ja.WALKTHROUGH.index(cmd)
    return ja.WALKTHROUGH[: idx + 1] if inclusive else ja.WALKTHROUGH[:idx]


# --- the happy path --------------------------------------------------------


def test_walkthrough_wins_at_full_score():
    game, _ = _play(ja.WALKTHROUGH)
    assert game.is_won()
    assert game.score == game.max_score == 100


def test_winning_path_takes_the_monkey_not_the_egg():
    # Egg (ornithology, +5) and monkey (zoo, +10) are mutually exclusive: the egg
    # is cooked and fed to the monkey to capture it. The perfect run banks the
    # monkey and never scores the egg.
    game, _ = _play(ja.WALKTHROUGH)
    assert "monkey" in game._scored_keys
    assert "egg" not in game._scored_keys
    # The eight scored lines that make up 100.
    assert game._scored_keys >= {
        "temple",
        "navigate",
        "skull",
        "skirt",
        "monkey",
        "escape",
        "finish",
    }


def test_scoring_is_idempotent():
    game, _ = _play(ja.WALKTHROUGH)
    # Re-entering the helicopter can't double anything (award is keyed).
    game.do_command("enter helicopter")
    assert game.score == 100


# --- topology --------------------------------------------------------------


def test_every_exit_resolves_and_no_duplicate_destinations():
    game = ja.build_game()
    for loc in game.locations.values():
        dests = list(loc.connections.values())
        for dest in dests:
            assert dest is not None
            assert dest.name in game.locations
        names = [d.name for d in dests]
        assert len(names) == len(set(names)), f"{loc.name} has a duplicate exit"


# --- the Deep Jungle compass maze ------------------------------------------


def test_deep_jungle_without_compass_just_wanders_in_circles():
    # Skip taking the backpack (so the compass stays in the plane): every exit
    # is a U-turn.
    game, cap = _play(["unbuckle seatbelt", "out", "go jungle", "south"])
    assert game.player.location.name == "Deep Jungle"
    assert _said(cap, "wander in circles")


def test_compass_opens_the_jungle_and_scores_the_crossing():
    game, cap = _play(
        ["unbuckle seatbelt", "get backpack", "out", "go jungle", "south"]
    )
    assert game.player.location.name == "Village"
    assert "navigate" in game._scored_keys
    assert _said(cap, "without a single false turn")


# --- the lethal transitions ------------------------------------------------


def test_entering_the_cave_unarmed_is_death():
    game, cap = _play(
        [
            "unbuckle seatbelt",
            "get backpack",
            "out",
            "go jungle",
            "south",
            "west",
            "west",
            "enter cave",
        ]
    )
    assert game.is_game_over() and not game.is_won()
    assert game.player.location.name == "Outside the Dark Cave"
    assert _said(cap, "disembowels you")


def test_crossing_the_gorge_without_the_necklace_is_death():
    game, cap = _play(
        ["unbuckle seatbelt", "get backpack", "out", "go jungle", "east", "east"]
    )
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "crocodile food")


def test_wading_into_the_pool_is_death():
    game, cap = _play(
        [
            "unbuckle seatbelt",
            "get backpack",
            "out",
            "go jungle",
            "east",
            "south",
            "enter pool",
        ]
    )
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "water snake")


def test_attacking_the_witch_doctor_curses_you_to_death_on_leaving():
    cmds = [
        "unbuckle seatbelt",
        "get backpack",
        "out",
        "go jungle",
        "south",
        "enter witch doctors hut",
        "attack witch doctor",
        "out",
        "north",  # leaving the village triggers the fire-ant curse
    ]
    game, cap = _play(cmds)
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "fire ants")


# --- the spear / cave / trades ---------------------------------------------


def test_entering_the_cave_with_the_spear_slays_the_tiger():
    game, cap = _play(_upto("enter cave"))
    assert game.player.location.name == "Inside the Dark Cave"
    assert game.characters["tiger"].get_property("is_dead")
    assert not game.is_game_over()
    # The spear lodges in the carcass -- you no longer carry it.
    assert "spear" not in ja._held_names(game.player)


# --- the altar gate --------------------------------------------------------


def test_altar_seals_the_tunnel_until_bones_are_placed():
    game, cap = _play(_upto("put bones on altar", inclusive=False))
    assert game.player.location.name == "Sacrificial Chamber"
    _play(["south"], game=game)  # blocked: no bones yet
    assert game.player.location.name == "Sacrificial Chamber"
    assert _said(cap, "altar blocks the way")
    _play(["put bones on altar", "south"], game=game)
    assert game.player.location.name == "Treasure Chamber"


# --- the monkey / skull interlock ------------------------------------------


def test_monkey_snatches_the_skull_and_must_be_fed_to_release_it():
    game, cap = _play(_upto("give egg to monkey", inclusive=False))
    assert game.monkey_has_skull
    _play(["get skull"], game=game)  # the monkey is clutching it
    assert "skull" not in ja._held_names(game.player)
    assert _said(cap, "clutching the gold skull")


def test_feeding_a_raw_egg_is_refused():
    # Same path as the win but without COOK EGG: the monkey turns up its nose.
    cmds = [c for c in _upto("give egg to monkey") if c != "cook egg"]
    game, cap = _play(cmds)
    assert game.monkey_has_skull  # still holding it
    assert _said(cap, "Cook it first")


def test_taking_the_skull_wakes_the_guardian_and_pins_you_north():
    game, cap = _play(_upto("get skull"))
    assert game.guardian_active
    assert "skull" in ja._held_names(game.player)
    # In the Sacrificial Chamber the only way out is north; going south is barred.
    _play(["north", "south"], game=game)
    assert game.player.location.name == "Sacrificial Chamber"
    assert _said(cap, "only escape is NORTH")


# --- the escape gate -------------------------------------------------------


def test_helicopter_will_not_fly_until_it_has_landed():
    game = ja.build_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.relocate(game.player, game.locations["Rocky Plateau"])
    game.do_command("enter helicopter")
    assert not game.is_game_over()
    assert _said(cap, "hasn't landed")
