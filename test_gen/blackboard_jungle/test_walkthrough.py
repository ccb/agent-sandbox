"""Tests for the Blackboard Jungle port -- the spec of its supported commands.

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
    path = Path(__file__).resolve().parent / "blackboard_jungle.py"
    spec = importlib.util.spec_from_file_location("bj_port", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bj = _load_module()


def _play(cmds):
    game = bj.build_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
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


# --- the happy path --------------------------------------------------------


def test_walkthrough_wins_at_full_score():
    game, _ = _play(bj.WALKTHROUGH)
    assert game.is_won()
    assert game.score == game.max_score == 50


def test_walkthrough_scores_each_event_once():
    # Re-handing nothing, re-cleaning, etc. shouldn't change the total; award()
    # is idempotent by key, so the full run lands exactly on the table's 50.
    game, _ = _play(bj.WALKTHROUGH)
    assert game.score == 50


# --- topology --------------------------------------------------------------


def test_every_exit_resolves_and_no_duplicate_destinations():
    game = bj.build_game()
    for loc in game.locations.values():
        dests = list(loc.connections.values())
        for dest in dests:
            assert dest is not None
            assert dest.name in game.locations
        # No room should have two exits to the same place (an authoring smell).
        names = [d.name for d in dests]
        assert len(names) == len(set(names)), f"{loc.name} has a duplicate exit"


# --- fail-states (the interesting Parsely fidelity) ------------------------


def test_uncleaned_puddle_is_a_concussion_death():
    game, cap = _play(["east", "east"])  # gym -> hallway west -> (slip!)
    assert game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "nurse's office")


def test_sawdust_makes_the_hallway_safe():
    game, _ = _play(
        ["south", "get bucket", "north", "east", "use pink sawdust", "east"]
    )
    assert not game.is_game_over()
    assert game.player.location.name == "Hallway East"


def test_library_without_glasses_is_the_stare_at_wall_ending():
    # Skip the glasses, clean the puddle, walk into the library.
    cmds = [
        "south",
        "get bucket",
        "north",
        "east",
        "use pink sawdust",
        "east",
        "enter library",
    ]
    game, cap = _play(cmds)
    assert game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "staring at the wall") or _said(cap, "stare at the wall")


def test_librarian_blocks_the_exit_until_glasses_returned():
    cmds = [
        "get glasses",
        "south",
        "get bucket",
        "north",
        "east",
        "use pink sawdust",
        "east",
        "enter library",
        "out",
    ]
    game, cap = _play(cmds)
    # Still stuck in the library, with the librarian's refusal shown.
    assert game.player.location.name == "Library"
    assert _said(cap, "until the end of day")


def test_classroom_without_homework_sends_you_to_detention():
    # Reach the classroom with no homework -> detention in the library, and with
    # no glasses either that's the stare-at-the-wall ending.
    cmds = [
        "south",
        "get bucket",
        "north",
        "east",
        "use pink sawdust",
        "west",
        "east",
        "enter classroom",
    ]
    game, cap = _play(cmds)
    assert _said(cap, "detention")
    assert game.is_game_over() and not game.is_won()


# --- the glasses gag -------------------------------------------------------


def test_wearing_glasses_blinds_you():
    game, cap = _play(["get glasses", "wear glasses", "look"])
    assert _said(cap, "blurry")
    # Taking them off restores normal sight.
    game.do_command("take off glasses")
    assert not game._glasses_on()


# --- the combination lock --------------------------------------------------


def test_wrong_combination_costs_the_first_try_bonus():
    cmds = [
        "get glasses",
        "south",
        "get bucket",
        "north",
        "east",
        "use pink sawdust",
        "east",
        "enter library",
        "give glasses to librarian",
        "out",
        "use combination 16-32-64",
        "use combination 8-16-32",
        "get homework",
    ]
    game, cap = _play(cmds)
    assert _said(cap, "don't go that high")
    assert "homework" in game.player.inventory
    # 5 glasses + 1 sweep + 10 return + 10 locker, but NOT the +2 first-try.
    assert game.score == 26


@pytest.mark.parametrize(
    "combo", ["use combination 8-16-32", "use combination 16-32-64"]
)
def test_combination_verbs_route_in_the_hallway(combo):
    # Both multi-word combination verbs must reach the hallway (specific-first
    # routing), not collide with a built-in.
    cmds = ["south", "get bucket", "north", "east", "use pink sawdust", "east", combo]
    game, cap = _play(cmds)
    assert _said(cap, "opens") or _said(cap, "don't go that high")
