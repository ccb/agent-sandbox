"""Tests for the base-engine cross-cutting systems: scoring (award), prescribed
death (end_in_death), and once-only ending epilogues (announce_ending).

These used to be reimplemented per game (Action Castle II/III each carried an
identical ``award`` and ``_die``); they now live on ``games.Game``.
"""

from text_adventure_games import games, things
from text_adventure_games.reporting import CaptureRenderer, Channel


def _game():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    game = games.Game(room, player)
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def _texts(cap):
    return cap.texts(Channel.NARRATION) + cap.texts(Channel.BLOCKED)


# --- scoring ---------------------------------------------------------------


def test_scoring_defaults_are_inert():
    game, _ = _game()
    assert game.score == 0
    assert game.max_score == 0


def test_award_adds_points_and_narrates():
    game, cap = _game()
    game.award("milestone", 10, "You did the thing!")
    assert game.score == 10
    assert any("You did the thing!" in t for t in _texts(cap))


def test_award_is_idempotent_per_key():
    game, _ = _game()
    game.award("milestone", 10)
    game.award("milestone", 10)  # same key -> no double count
    assert game.score == 10
    game.award("other", 5)
    assert game.score == 15


def test_award_without_message_is_silent():
    game, cap = _game()
    game.award("quiet", 3)
    assert game.score == 3
    assert _texts(cap) == []


# --- prescribed death ------------------------------------------------------


def test_end_in_death_ends_game_with_message():
    game, cap = _game()
    game.end_in_death("A trap springs. THE END.")
    assert game.game_over is True
    assert game.is_game_over() is True
    assert game.game_over_description == "A trap springs. THE END."
    assert any("A trap springs. THE END." in t for t in _texts(cap))


# --- ending epilogue -------------------------------------------------------


def test_announce_ending_prints_once():
    game, cap = _game()
    game.announce_ending("You win!")
    game.announce_ending("You win!")  # polled again -> silent
    assert sum("You win!" in t for t in cap.texts(Channel.NARRATION)) == 1


def test_announce_ending_appends_score_when_requested():
    game, cap = _game()
    game.max_score = 50
    game.award("a", 20)
    game.announce_ending("Victory!", show_score=True)
    assert any("Victory!  (Score: 20/50)" in t for t in cap.texts(Channel.NARRATION))


def test_announce_ending_omits_score_when_no_max():
    game, cap = _game()
    game.announce_ending("Victory!", show_score=True)  # max_score still 0
    texts = cap.texts(Channel.NARRATION)
    assert any(t == "Victory!" for t in texts)
    assert not any("Score:" in t for t in texts)
