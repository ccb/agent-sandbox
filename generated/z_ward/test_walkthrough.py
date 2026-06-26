"""Tests for the Z-Ward port -- the spec of its supported commands.

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
    path = Path(__file__).resolve().parent / "z_ward.py"
    spec = importlib.util.spec_from_file_location("zward_port", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


zw = _load_module()


def _play(cmds):
    game = zw.build_game()
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


# A short run-up that gets you inside, having dealt with Honeycutt, the office
# unlocked, and the elevator cleared. Interior tests start from here.
PRELUDE = [
    "read note",
    "east",
    "get shovel",
    "hit man with shovel",
    "get keycard",
    "west",
    "north",
    "get fire extinguisher",
    "use fire extinguisher",
    "use keycard",
]


# --- the happy path --------------------------------------------------------


def test_walkthrough_wins_at_full_score():
    game, _ = _play(zw.WALKTHROUGH)
    assert game.is_won()
    assert game.score == game.max_score == 100


def test_walkthrough_scores_each_event_once():
    # award() is idempotent by key, so the full run lands exactly on 100.
    game, _ = _play(zw.WALKTHROUGH)
    assert game.score == 100


# --- topology --------------------------------------------------------------


def test_every_exit_resolves_and_no_duplicate_destinations():
    game = zw.build_game()
    for loc in game.locations.values():
        dests = list(loc.connections.values())
        for dest in dests:
            assert dest is not None
            assert dest.name in game.locations
        # No room should have two exits to the same place (an authoring smell).
        names = [d.name for d in dests]
        assert len(names) == len(set(names)), f"{loc.name} has a duplicate exit"


# --- scoring details -------------------------------------------------------


def test_reading_the_note_scores_five():
    game, cap = _play(["read note"])
    assert game.score == 5
    assert _said(cap, "halp zomby apokalips")


def test_killing_honeycutt_before_turning_scores_five():
    game, _ = _play(["read note", "east", "get shovel", "hit man with shovel"])
    assert game.score == 10  # note 5 + honeycutt 5


def test_no_outage_bonus_only_with_the_medium_dial():
    # Crank the dial to HIGH and the breakers blow -- no +5 for the wheelchair.
    cmds = PRELUDE + [
        "up",
        "east",
        "east",
        "set dial to high",
        "get wheelchair",
    ]
    game, cap = _play(cmds)
    assert game.outage is True
    assert zw._is_holding(game.player, "wheelchair")
    assert "no_outage" not in game._scored_keys
    assert _said(cap, "power goes out")


# --- gates on the critical path --------------------------------------------


def test_office_is_locked_without_the_keycard():
    game, cap = _play(["read note", "north", "west"])
    assert game.player.location.name == "Hospital Intake"
    assert _said(cap, "need a keycard")


def test_elevator_is_blocked_until_the_zombie_is_cleared():
    game, cap = _play(["read note", "north", "elevator"])
    assert game.player.location.name == "Hospital Intake"
    assert _said(cap, "claws at you from inside the elevator")


def test_quiet_room_padlock_needs_the_key():
    game, cap = _play(PRELUDE + ["up", "east", "north"])
    assert game.player.location.name == "Examination Room"
    assert _said(cap, "padlocked")


def test_walk_in_is_blocked_until_the_zombie_is_cleared():
    game, cap = _play(PRELUDE + ["east", "east", "open walk-in"])
    assert game.player.location.name == "Kitchen"
    assert not game.locations["Kitchen"].get_property("peggy_rescued")
    assert _said(cap, "clawing at the refrigerator")


def test_wheelchair_cannot_take_the_stairs():
    # Reach the point where Frances is in the chair, then try the stairs down.
    idx = zw.WALKTHROUGH.index("put frances in wheelchair")
    cmds = zw.WALKTHROUGH[: idx + 1] + ["out", "west", "down"]
    game, cap = _play(cmds)
    assert game.player.location.name == "Group Therapy Room"
    assert _said(cap, "can't push the wheelchair down the stairs")


# --- fail-states / deaths --------------------------------------------------


def test_entering_the_hospital_first_turns_honeycutt():
    # Go straight in, then back out to the gardens -- the man is now a zombie and
    # bashing him no longer scores the +5.
    game, cap = _play(
        ["read note", "north", "south", "east", "get shovel", "hit man with shovel"]
    )
    man = game.characters["man"]
    assert man.get_property("dead")
    assert game.score == 5  # note only; no honeycutt bonus
    assert _said(cap, "bash in the zombie's skull")


def test_searching_the_chief_unsedated_gets_you_shot():
    game, cap = _play(PRELUDE + ["west", "search chief of staff"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "fires his revolver")


def test_playing_bambi_enrages_the_horde():
    game, cap = _play(PRELUDE + ["east", "north", "up", "play bambi"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "Bambi's mother dies")


def test_lingering_in_the_auditorium_is_fatal():
    game, cap = _play(PRELUDE + ["east", "north", "look", "look"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "close in from every side")


def test_turning_off_the_television_wakes_the_zombie():
    game, cap = _play(PRELUDE + ["up", "turn off television"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "attacks before you can react")


def test_abandoning_frances_to_the_straitjacket_zombie():
    # Rescue Frances from the wall but leave the Quiet Room without securing her
    # in the wheelchair -- the straitjacket zombie gets her.
    idx = zw.WALKTHROUGH.index("give bunny to frances")
    cmds = zw.WALKTHROUGH[: idx + 1] + ["out"]
    game, cap = _play(cmds)
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "loss of your sister")


# --- survivor rescues score correctly --------------------------------------


def test_each_survivor_rescue_scores_ten():
    # Peggy via the meat hook + walk-in.
    game, _ = _play(
        PRELUDE
        + ["east", "east", "get meat hook", "use meat hook on zombie", "open walk-in"]
    )
    assert "peggy" in game._scored_keys
    # Nurse via the plunger.
    game, _ = _play(PRELUDE + ["up", "north", "get plunger", "use plunger on zombie"])
    assert "nurse" in game._scored_keys


@pytest.mark.parametrize(
    "alias",
    [
        "set dial to medium",
        "turn dial to medium",
    ],
)
def test_dial_aliases_route_to_the_machine(alias):
    game, _ = _play(PRELUDE + ["up", "east", "east", alias])
    assert game.locations["EST Room"].get_property("zombie_stunned")
