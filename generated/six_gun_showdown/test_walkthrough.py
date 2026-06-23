"""Tests for the Six-Gun Showdown port -- the spec of its supported commands.

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
    path = Path(__file__).resolve().parent / "six_gun_showdown.py"
    spec = importlib.util.spec_from_file_location("sgs_port", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sgs = _load_module()
WALK = sgs.WALKTHROUGH


def _play(cmds):
    game = sgs.build_game()
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


def _upto(cmd, inclusive=True):
    """The walkthrough prefix up to (and by default including) *cmd*."""
    i = WALK.index(cmd)
    return WALK[: i + 1] if inclusive else WALK[:i]


# --- the happy path --------------------------------------------------------


def test_walkthrough_wins_at_full_score():
    game, cap = _play(WALK)
    assert game.is_won()
    assert game.score == game.max_score == 100
    assert _said(cap, "The Law is back in town")


def test_walkthrough_scores_each_event_once():
    # award() is idempotent by key, so the full run lands exactly on the
    # rulebook's 100 -- no double counts from re-entered rooms or triggers.
    game, _ = _play(WALK)
    assert game.score == 100


# --- topology --------------------------------------------------------------


def test_every_exit_resolves_and_no_duplicate_destinations():
    game = sgs.build_game()
    for loc in game.locations.values():
        dests = list(loc.connections.values())
        for dest in dests:
            assert dest is not None
            assert dest.name in game.locations
        names = [d.name for d in dests]
        assert len(names) == len(set(names)), f"{loc.name} has a duplicate exit"


# --- the saloon / poker set-piece ------------------------------------------


def test_folding_the_hand_loses_the_badge_and_ends_it():
    game, cap = _play(_upto("examine black jack") + ["fold"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "you're nothin'")


def test_calling_with_two_pair_scores_five_not_ten():
    # Skipping the DRAW means you win the hand on two pair (+5), not the drawn
    # full house (+10).
    prefix = _upto("wager badge")
    game, _ = _play(prefix)
    before = game.score
    game.do_command("call")
    assert "poker" in game._scored_keys
    assert game.score - before == 5


def test_hit_needs_black_jack_enraged_first():
    # Smashing the bottle only works once he's drawn his knife (after CALL).
    game, cap = _play(_upto("wager badge") + ["hit black jack with bottle"])
    assert _said(cap, "watching you too closely")
    assert not game.bj_out


def test_shooting_at_the_table_is_a_death():
    game, _ = _play(_upto("call") + ["shoot black jack"])
    assert game.is_game_over() and not game.is_won()


# --- the desert: supplies gate and thirst ----------------------------------


def test_desert_is_blocked_without_supplies():
    game, cap = _play(["south", "south"])  # Main St -> Outskirts -> (blocked)
    assert game.player.location.name == "Outskirts of Town"
    assert _said(cap, "New York City")


def test_two_skipped_drinks_is_a_thirst_death():
    # Enter the desert (a drink is prompted) then push on twice without drinking.
    # The prefix ends on the Desert-entry "south", just before the first drink.
    game, cap = _play(_upto("drink water", inclusive=False) + ["west", "south"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "collapse and perish")


def test_cutting_the_cactus_adds_a_water_ration():
    game, _ = _play(_upto("cut cactus"))
    assert "cactus" in game._scored_keys
    assert game.water_rations >= 2  # 3 start, 2 drunk, +1 from the cactus


# --- the overnight camp: the snake in your boot ----------------------------


def test_checking_your_boot_reveals_the_snake_and_scores():
    game, cap = _play(_upto("examine boots"))
    assert game.snake_seen
    assert "check_boot" in game._scored_keys
    assert _said(cap, "rattlesnake")


def test_wearing_boots_with_the_snake_inside_is_a_death():
    # Reach morning, shake the snake out, but pull the boots on without killing
    # it -- a faithful instant death (page 184).
    game, cap = _play(_upto("shake boot") + ["wear boots"])
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "fangs sink into your foot")


def test_shooting_the_snake_fails_for_shaky_hands():
    game, cap = _play(_upto("shake boot") + ["shoot snake"])
    assert not game.is_game_over()
    assert _said(cap, "shaking too much")


# --- the cave: drop the pack, burn the map ---------------------------------


def test_cave_is_blocked_until_the_rucksack_is_dropped():
    game, cap = _play(_upto("get flint and steel") + ["enter cave"])
    assert game.player.location.name == "Rocky Bluff"
    assert _said(cap, "tight squeeze")


# --- the showdown ----------------------------------------------------------


def test_drawing_before_the_sun_is_a_death():
    game, _ = _play(_upto("duel black jack") + ["draw and fire"])
    assert game.is_game_over() and not game.is_won()


def test_duel_requires_steady_hands():
    # Stand at the clock tower with the shakes still on you: you can't risk it.
    game = sgs.build_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    tower = game.locations["Main Street Clock Tower"]
    bj = game.characters["black jack"]
    game.relocate(game.player, tower)
    game.relocate(bj, tower)
    game.player.set_property("hands_shaky", True)
    game.do_command("duel black jack")
    assert game.player.location.name == "Main Street Clock Tower"
    assert _said(cap, "hands shaking")


# --- parser routing (multi-word verbs must beat the built-in keywords) ------


@pytest.mark.parametrize(
    "command,expected",
    [
        ("hit black jack with bottle", "hit black jack with bottle"),
        ("show map to mariah", "show map to mariah"),
        ("show gold to mariah", "show gold to mariah"),
        ("give snake to doc", "give snake to doc"),
        ("cut cactus", "cut cactus"),
        ("kill snake with knife", "kill snake with knife"),
        ("use snake oil on hands", "use snake oil on hands"),
        ("wager badge", "wager badge"),
        ("drink bottle", "drink sarsaparilla"),
        ("draw and fire", "draw and fire"),
        ("wear badge", "wear badge"),
    ],
)
def test_multiword_verbs_route_specific_first(command, expected):
    game = sgs.build_game()
    assert game.parser.determine_intent(command, actor=game.player) == expected
