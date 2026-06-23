"""Tests for the Space Station port -- the spec of its supported commands.

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
    path = Path(__file__).resolve().parent / "space_station.py"
    spec = importlib.util.spec_from_file_location("ss_port", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ss = _load_module()


def _play(cmds):
    game = ss.build_game()
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


def _without(cmd):
    """The full walkthrough with one command removed."""
    return [c for c in ss.WALKTHROUGH if c != cmd]


# --- the happy path --------------------------------------------------------


def test_walkthrough_wins_at_full_score():
    game, _ = _play(ss.WALKTHROUGH)
    assert game.is_won()
    assert game.score == game.max_score == 100


def test_walkthrough_scores_each_event_once():
    # award() is idempotent by key, so the run lands exactly on the table's 100.
    game, _ = _play(ss.WALKTHROUGH)
    assert game.score == 100


# --- topology --------------------------------------------------------------


def test_every_exit_resolves_and_no_duplicate_destinations():
    game = ss.build_game()
    for loc in game.locations.values():
        dests = list(loc.connections.values())
        for dest in dests:
            assert dest is not None
            assert dest.name in game.locations
        names = [d.name for d in dests]
        assert len(names) == len(set(names)), f"{loc.name} has a duplicate exit"


# --- the hypoinjector (waking up, and overdosing) --------------------------


def test_cryo_sickness_blocks_the_turbolift_until_the_first_dose():
    game, cap = _play(["out", "up"])  # crawl to medical bay, then try to ride up
    assert game.player.location.name == "Medical Bay"  # the turbolift refused
    assert _said(cap, "cryo-sickness")


def test_first_dose_lets_you_move():
    game, _ = _play(["out", "get hypoinjector", "use hypoinjector", "up"])
    assert game.player.location.name == "Cybernetics Lab"
    assert game.score == 10  # +10 hypo


def test_third_dose_explodes_your_heart():
    game, cap = _play(
        [
            "out",
            "get hypoinjector",
            "use hypoinjector",  # dose 1
            "use hypoinjector",  # dose 2
            "use hypoinjector",  # dose 3 -> death
        ]
    )
    assert game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "heart")


# --- bringing the station back online --------------------------------------


def test_comm_terminal_reports_cpu_offline_before_reboot():
    game, cap = _play(
        [
            "out",
            "get hypoinjector",
            "use hypoinjector",
            "up",
            "up",
            "examine comm terminal",
        ]
    )
    assert game.player.location.name == "Command Deck"
    assert _said(cap, "CPU Offline")


def test_cannot_translate_before_cpu_and_sensor_are_fixed():
    game, cap = _play(
        ["out", "get hypoinjector", "use hypoinjector", "up", "up", "input frellion"]
    )
    assert not game.translated
    assert _said(cap, "isn't receiving")


# --- the post-shield-drop hazards (zero-g + radiation) ---------------------


def test_zero_g_without_mag_boots_sets_you_adrift():
    game, cap = _play(
        [
            "out",
            "get hypoinjector",
            "use hypoinjector",
            "down",  # -> Engineering Bay (skip the mag boots)
            "enter shield generator",
            "lower shields",  # gravity fails
            "out",  # move in zero-g, unanchored -> death
        ]
    )
    assert game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "float")


def test_irradiated_flight_deck_kills_an_unsuited_player():
    game, cap = _play(
        [
            "out",
            "get hypoinjector",
            "use hypoinjector",
            "down",  # -> Engineering Bay
            "get mag boots",
            "enter shield generator",
            "lower shields",  # reactor damaged, radiation floods the flight deck
            "wear mag boots",
            "out",  # -> Engineering Bay
            "down",  # -> Flight Deck (reactor unfixed, no suit) -> death
        ]
    )
    assert game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "Radiation")


# --- the reactor: FROZ fixes it; a human only dies in it -------------------


def test_entering_the_reactor_as_a_human_is_fatal():
    game, cap = _play(
        [
            "out",
            "get hypoinjector",
            "use hypoinjector",
            "down",  # -> Engineering Bay
            "enter reactor",  # warning
            "enter reactor",  # insist -> death
        ]
    )
    assert game.is_game_over()
    assert not game.is_won()


def test_the_vulcan_line_earns_the_gratuitous_star_trek_death():
    game, cap = _play(
        [
            "out",
            "get hypoinjector",
            "use hypoinjector",
            "down",  # -> Engineering Bay
            "i am not human",
            "enter reactor",  # heroic death, +15
        ]
    )
    assert game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "heroically")
    assert game.score == 25  # hypo 10 + vulcan 15


# --- the transporter -------------------------------------------------------


def test_untrained_transporter_use_is_a_death():
    game, cap = _play(
        [
            "out",
            "get hypoinjector",
            "use hypoinjector",
            "down",  # -> Engineering Bay
            "down",  # -> Flight Deck
            "enter transporter room",
            "activate transporter",
        ]
    )
    assert game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "scatters your atoms")


# --- launching the pod: the three failure modes ----------------------------


def test_launching_without_a_spacesuit_turns_you_to_goo():
    # Everything's ready (shields down, doors unlocked) but you skip the suit.
    cmds = _without("wear spacesuit")
    game, cap = _play(cmds)
    assert game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "pink goo")


def test_launching_with_doors_locked_is_aborted_not_fatal():
    # Skip throwing the lever: the rebooted computer warns instead of letting
    # you splatter the pod against the locked doors.
    cmds = _without("order froz to pull lever")
    game, cap = _play(cmds)
    assert not game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "Launch aborted")


def test_escaping_without_surrender_gets_you_shot_down():
    cmds = _without("surrender")
    game, cap = _play(cmds)
    assert game.is_game_over()
    assert not game.is_won()
    assert _said(cap, "gravity cannon")


# --- FROZ ------------------------------------------------------------------


def test_leaving_froz_behind_still_wins_but_loses_the_bonus():
    # Order FROZ to wait on the flight deck (after it's done its jobs) so it
    # doesn't ride along: you still escape, but without the +5 "with FROZ".
    cmds = []
    for c in ss.WALKTHROUGH:
        if c == "enter escape pod":
            cmds.append("order froz to wait")
        cmds.append(c)
    game, _ = _play(cmds)
    assert game.is_won()
    assert game.score == 95  # 100 minus the FROZ bonus


def test_froz_cannot_climb_the_ladder_to_the_cpu_core():
    # FROZ follows on the turbolift but its treads can't take the CPU-core
    # ladder, so it waits in the lab.
    cmds = [
        "out",
        "get hypoinjector",
        "use hypoinjector",
        "up",  # -> Cybernetics Lab
        "order froz to follow",
        "enter cpu core",
    ]
    game, _ = _play(cmds)
    assert game.player.location.name == "CPU Core"
    froz = game.characters["froz"]
    assert froz.location.name == "Cybernetics Lab"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
