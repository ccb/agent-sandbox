"""Tests for the Dangertown Beatdown port -- the spec of its supported commands.

Loads the sibling module by file path (so the test runs regardless of how
``test_gen`` is importable) and drives it through a CaptureRenderer, the house
pattern from docs/converting-parsely-games.md section 11. Covers the winning
walkthrough, the city topology, the motorcycle/Porsche overworld gates, the
protagonist switch, and every THE END (the bribe, the deaths, the two Boss D
endings).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from text_adventure_games.reporting import CaptureRenderer, Channel


def _load_module():
    path = Path(__file__).resolve().parent / "dangertown_beatdown.py"
    spec = importlib.util.spec_from_file_location("dt_port", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dt = _load_module()
WT = dt.WALKTHROUGH


def _play(cmds):
    game = dt.build_game()
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


def _through(cmd):
    """The walkthrough up to and including *cmd* (a robust prefix slice)."""
    return WT[: WT.index(cmd) + 1]


# --- the happy path --------------------------------------------------------


def test_walkthrough_wins_at_full_score():
    game, _ = _play(WT)
    assert game.is_won()
    assert game.score == game.max_score == 100


def test_score_breaks_down_65_slade_plus_35_chang():
    game, _ = _play(WT)
    slade_keys = {
        "msg",
        "newspaper",
        "refuse_bribe",
        "kettle_ko",
        "tip",
        "boss_location",
        "warehouse_num",
        "beat_cutter",
        "patched",
        "coffee",
        "donuts",
        "audiotape",
        "free_jetta",
    }
    chang_keys = {
        "help_knockout",
        "save_slade",
        "badge_gun",
        "defeat_rocco",
        "enter_penthouse",
        "arrest",
        "finish",
    }
    assert slade_keys | chang_keys <= game._scored_keys
    assert "kill_boss" not in game._scored_keys  # the +0 ending is not on the win path


# --- topology --------------------------------------------------------------


def test_every_exit_resolves_and_no_duplicate_destinations():
    game = dt.build_game()
    known = set(id(loc) for loc in game.locations.values())
    for loc in game.locations.values():
        dests = []
        for direction, dest in loc.connections.items():
            assert id(dest) in known, f"{loc.name} -{direction}-> unregistered room"
            dests.append(dest.name)
        assert len(dests) == len(set(dests)), f"{loc.name} has two exits to one room"


def test_blocks_point_at_their_own_room():
    game = dt.build_game()
    for loc in game.locations.values():
        for direction, block in loc.blocks.items():
            owner = getattr(block, "location", None)
            if owner is not None:
                assert owner is loc


# --- the motorcycle / Porsche overworld ------------------------------------

# Reaching Southside on foot, carrying the keys (a short manual prefix).
_TO_SOUTHSIDE = [
    "play message",
    "open closet",
    "get jacket",
    "wear jacket",
    "out",
    "make coffee",
    "read newspaper",
    "say no",
    "hit man with kettle",
    "get bat",
    "search man",
    "out",
]


def test_ride_exit_is_blocked_on_foot():
    game, cap = _play(_TO_SOUTHSIDE + ["drive to downtown"])
    assert game.player.location.name == "Southside"  # didn't move
    assert _said(cap, "on foot")


def test_building_entry_is_blocked_while_riding():
    game, cap = _play(_TO_SOUTHSIDE + ["get on motorcycle", "enter strip club"])
    assert game.player.location.name == "Southside"  # still on the bike, didn't enter
    assert game.player.riding is not None


def test_starting_the_bike_needs_the_keys():
    # Walk to Southside WITHOUT ever wearing the jacket (so no keys).
    no_keys = [
        "open closet",
        "out",
        "make coffee",
        "read newspaper",
        "say no",
        "hit man with kettle",
        "out",
    ]
    game, cap = _play(no_keys + ["get on motorcycle"])
    assert game.player.riding is None
    assert _said(cap, "keys")


# --- the bleeding gate -----------------------------------------------------


def test_cafe_is_blocked_while_bleeding_then_opens_after_gheorghe():
    # Up through getting slashed by Cutter and riding to Little Italy.
    bleeding = _play(
        _through("take switchblade")
        + [
            "out",
            "south",
            "get on motorcycle",
            "drive to little italy",
            "park bike",
            "enter cafe",
        ]
    )
    game, cap = bleeding
    assert game.player.location.name == "Little Italy"  # Marge turned you away
    assert game.bleeding is True
    # Patch up, then the cafe lets you in.
    for c in ["enter gym", "ask gheorghe for help", "out", "enter cafe"]:
        game.do_command(c)
    assert game.player.location.name == "Pixel City Cafe"
    assert game.bleeding is False


# --- the protagonist switch ------------------------------------------------


def test_giving_the_tape_switches_you_to_jetta_chang():
    game, cap = _play(_through("give tape"))
    assert game.is_chang is True
    assert game.player is game.jetta
    assert game.goon_threat is True
    assert _said(cap, "JETTA CHANG")


# --- endings: the bribe ----------------------------------------------------


def test_saying_yes_to_the_bribe_is_a_loss():
    game, cap = _play(_through("read newspaper") + ["say yes"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "THE END")


def test_walking_off_with_the_attache_is_a_loss():
    game, cap = _play(_through("push p") + ["take attache"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "on the take")


# --- endings: the deaths ---------------------------------------------------


def test_refusing_then_not_knocking_out_the_gangster_kills_you():
    game, cap = _play(_through("read newspaper") + ["say no", "wait"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "bloody pulp")


def test_lingering_in_the_evidence_locker_gets_you_busted():
    game, cap = _play(_through("take audiotape") + ["wait"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "tampering with evidence")


def test_not_helping_knockout_gets_you_riddled_with_bullets():
    game, cap = _play(_through("give tape") + ["wait"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "riddled with bullets")


def test_not_taking_rocco_out_in_the_elevator_kills_you():
    game, cap = _play(_through("enter elevator") + ["wait", "wait"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "shoots you")


def test_arresting_boss_d_without_disarming_him_kills_you():
    game, cap = _play(_through("push p") + ["arrest boss d"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "shoots you dead")


def test_slashing_the_tires_strands_the_getaway_car():
    # Slash the tires at Harbor View on the way in, then try the escape.
    game, cap = _play(
        _through("enter bay #23")[:-1]
        + [
            "slash tires",
            "find bay",
            "enter bay #23",
            "free jetta chang",
            "give tape",
            "attack goon",
            "search goon",
            "drag slade out",
            "use key on porsche",
        ]
    )
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "bleeds out")


# --- endings: killing Boss D (a downer ending, +0, not a win) ---------------


def test_shooting_boss_d_ends_the_game_without_a_win():
    game, cap = _play(_through("search boss d") + ["shoot boss d"])
    assert game.is_game_over()
    assert not game.is_won()
    assert "kill_boss" in game._scored_keys
    assert "arrest" not in game._scored_keys
    assert game.score == 90  # 65 Slade + 25 Chang milestones, no arrest/finish bonus
    assert _said(cap, "vengeance")
