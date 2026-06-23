"""Tests for the Spooky Manor port -- the spec of its supported commands.

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
    path = Path(__file__).resolve().parent / "spooky_manor.py"
    spec = importlib.util.spec_from_file_location("sm_port", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sm = _load_module()

# The common run-up: through the front door and into the great hall (which locks
# the door behind you). Every interior fail-state test starts from here.
PRELUDE = [
    "get parcel",
    "lock bike",
    "north",
    "knock",
    "enter house",
    "hang raincoat",
    "north",
]


def _play(cmds):
    game = sm.build_game()
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
    game, _ = _play(sm.WALKTHROUGH)
    assert game.is_won()
    assert game.score == game.max_score == 100


def test_walkthrough_scores_each_event_once():
    # award() is idempotent by key, so the full run lands exactly on 100.
    game, _ = _play(sm.WALKTHROUGH)
    assert game.score == 100


# --- topology --------------------------------------------------------------


def test_every_exit_resolves_and_no_duplicate_destinations():
    game = sm.build_game()
    for loc in game.locations.values():
        dests = list(loc.connections.values())
        for dest in dests:
            assert dest is not None
            assert dest.name in game.locations
        # No room should have two exits to the same place (an authoring smell).
        names = [d.name for d in dests]
        assert len(names) == len(set(names)), f"{loc.name} has a duplicate exit"


# --- gates on the critical path --------------------------------------------


def test_must_knock_before_entering():
    game, cap = _play(["get parcel", "lock bike", "north", "enter house"])
    assert game.player.location.name == "Front Door"
    assert _said(cap, "KNOCK")


def test_must_hang_raincoat_before_the_great_hall():
    game, cap = _play(
        ["get parcel", "lock bike", "north", "knock", "enter house", "north"]
    )
    assert game.player.location.name == "Vestibule"
    assert _said(cap, "hang up your raincoat")


def test_front_door_locks_behind_you_and_needs_the_key():
    game, cap = _play(PRELUDE + ["south", "out", "south"])
    assert game.player.location.name == "Front Door"
    assert _said(cap, "locked")


def test_hedge_maze_is_impassable_until_cut():
    game, cap = _play(PRELUDE + ["east", "north", "north", "east", "east", "south"])
    assert game.player.location.name == "Hedge Maze"
    assert _said(cap, "hedges")


def test_taking_mysteries_opens_the_secret_study():
    game, _ = _play(PRELUDE + ["east", "take mysteries of ancient egypt", "south"])
    assert game.player.location.name == "Secret Study"
    assert game.score == 15  # lock_bike 5 (in PRELUDE) + secret_study 10


def test_wolfsbane_needs_the_herbalism_book_first():
    game, cap = _play(PRELUDE + ["east", "north", "north", "east", "take wolfsbane"])
    assert _said(cap, "Gardening isn't your area")
    assert not sm._is_holding(game.player, "wolfsbane")


def test_sick_courier_cannot_pry_the_crypt():
    # Get the shears from the pool (which soaks you), cut the maze, then try to
    # pry the crypt while still a shivering wreck -- the recovery interlock.
    cmds = PRELUDE + [
        "west",
        "north",
        "get oil",
        "south",
        "east",  # fetch the olive oil
        "east",
        "north",
        "north",
        "east",  # -> Garden
        "north",
        "enter pool",
        "south",  # shears (+ soaked)
        "use oil on shears",
        "east",
        "use shears",
        "south",  # cut maze -> Graveyard
        "get spade",
        "pry door",
    ]
    game, cap = _play(cmds)
    assert game.player.location.name == "Graveyard"
    assert not game.locations["Graveyard"].get_property("crypt_open")
    assert _said(cap, "shivering wreck")


# --- fail-states / sinister endings ----------------------------------------


def test_dantes_inferno_is_the_ghost_ending():
    game, cap = _play(PRELUDE + ["east", "take dante's inferno"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "incinerator")
    assert _said(cap, "permanent resident")  # the Ghost epilogue


def test_diving_into_the_pool_drowns_you():
    game, cap = _play(
        PRELUDE + ["east", "north", "north", "east", "north", "dive into pool"]
    )
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "drown")


def test_attacking_the_wolf_makes_you_a_werewolf():
    game, cap = _play(PRELUDE + ["west", "north", "down", "attack wolf"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "baleful howl")


def test_lingering_in_the_cellar_makes_you_a_werewolf():
    game, cap = _play(PRELUDE + ["west", "north", "down"] + ["wait"] * 6)
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "Forever changed")


def test_staking_vanessa_without_garlic_turns_you():
    idx = sm.WALKTHROUGH.index("crypt")
    game, cap = _play(sm.WALKTHROUGH[: idx + 1] + ["use stake"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "leathery wings")


def test_grabbing_the_key_wakes_the_vampire():
    idx = sm.WALKTHROUGH.index("crypt")
    game, cap = _play(sm.WALKTHROUGH[: idx + 1] + ["take key"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "bites you")


def test_cannot_leave_before_delivering_the_parcel():
    game, cap = _play(["get parcel", "lock bike", "east"])
    assert not game.is_game_over()
    assert game.player.location.name == "The Gate"
    assert _said(cap, "Once you deliver your parcel")


def test_unlocked_bike_means_the_hitchhiker_ending():
    # Same winning run, but never lock the bike: riding up the path wrecks it,
    # so the courier leaves on foot -- straight into the Hitchhiker's bad end.
    no_lock = [c for c in sm.WALKTHROUGH if c != "lock bike"]
    game, cap = _play(no_lock)
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "evil smile")


def test_riding_up_the_path_damages_the_bike():
    game, cap = _play(["get parcel", "north"])  # skip the lock, pedal up
    assert game.player.location.name == "Front Door"
    assert game.player.get_property("bike_damaged")
    assert _said(cap, "go flat")
