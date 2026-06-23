"""Tests for the Flaming Goat port -- the spec of its supported commands.

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
    path = Path(__file__).resolve().parent / "flaming_goat.py"
    spec = importlib.util.spec_from_file_location("fg_port", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fg = _load_module()


def _play(cmds):
    game = fg.build_game()
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
    game, _ = _play(fg.WALKTHROUGH)
    assert game.is_won()
    assert game.score == game.max_score == 1000


def test_winning_scores_exactly_once():
    # award() is idempotent by key, so even re-cresting the top can't double it.
    game, _ = _play(fg.WALKTHROUGH)
    assert game.score == 1000


# --- topology --------------------------------------------------------------


def test_every_exit_resolves_and_no_duplicate_destinations():
    game = fg.build_game()
    for loc in game.locations.values():
        dests = list(loc.connections.values())
        for dest in dests:
            assert dest is not None
            assert dest.name in game.locations
        names = [d.name for d in dests]
        assert len(names) == len(set(names)), f"{loc.name} has a duplicate exit"


# --- the WALK-only escalator gag -------------------------------------------


def test_go_up_goes_nowhere_but_walk_up_climbs():
    # GO UP (and bare "up") is the dead-escalator gag; only WALK UP moves you.
    game, cap = _play(["go up"])
    assert game.player.location.name == "Subway Platform"
    assert _said(cap, "go nowhere")

    game, _ = _play(["walk up"])
    assert game.player.location.name == "Broken Escalator"


def test_up_and_down_on_the_escalator_do_not_work():
    # Midway up, GO UP / GO DOWN just report the escalator is still dead; you
    # must WALK. (WALK DOWN is exercised separately below.)
    cmds = ["walk up", "up", "down"]
    game, cap = _play(cmds)
    assert game.player.location.name == "Broken Escalator"
    assert _said(cap, "continues to not work")


def test_walk_down_returns_to_the_platform():
    game, _ = _play(["walk up", "walk down"])
    assert game.player.location.name == "Subway Platform"


# --- the goat puzzle gate --------------------------------------------------


def test_goat_blocks_the_way_up_until_it_is_fed():
    # With the goat still there, WALK UP is blocked -- and while it's aflame the
    # block names the fire.
    game, cap = _play(["walk up", "walk up"])
    assert game.player.location.name == "Broken Escalator"
    assert _said(cap, "flaming goat stands in the way")


def test_cannot_feed_the_goat_while_it_is_on_fire():
    cmds = ["shake vending machine", "get can", "walk up", "feed can to goat"]
    game, cap = _play(cmds)
    assert not game.game_over
    assert game.goat_on_fire and not game.goat_gone
    assert _said(cap, "far too angry")


def test_pouring_douses_but_the_hungry_goat_still_blocks():
    # After dousing, the goat is no longer angry but is still in the way; the
    # block description updates to say so.
    cmds = [
        "shake vending machine",
        "get can",
        "walk up",
        "pour soda on goat",
        "walk up",
    ]
    game, cap = _play(cmds)
    assert game.player.location.name == "Broken Escalator"
    assert not game.goat_on_fire
    assert _said(cap, "still hungry")


def test_pouring_twice_reports_the_flames_are_already_out():
    cmds = [
        "shake vending machine",
        "get can",
        "walk up",
        "pour soda on goat",
        "pour soda on goat",
    ]
    game, cap = _play(cmds)
    assert _said(cap, "already out")


# --- needing the can in hand -----------------------------------------------


def test_pouring_without_the_can_fails():
    game, cap = _play(["walk up", "pour soda on goat"])
    assert _said(cap, "don't have a can")
    assert game.goat_on_fire


def test_vending_machine_yields_its_can_only_once():
    game, cap = _play(["shake vending machine", "shake vending machine"])
    assert _said(cap, "nothing else comes out")
    assert "can" in game.player.location.items  # still on the floor, only one


# --- flavor verbs ----------------------------------------------------------


def test_open_and_drink_are_flavor():
    cmds = ["shake vending machine", "get can", "open can", "drink soda"]
    game, cap = _play(cmds)
    assert _said(cap, "hssssss") or _said(cap, "pop the top")
    assert _said(cap, "not thirsty")
