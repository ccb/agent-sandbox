"""The InvisiClues-style hint system (hints.py + actions/hints.py): the menu
lists only puzzles the player has MET and not yet beaten, each ask reveals one
more level, reveals cost no turn but survive the (seed, journal) replay, and
the game owns up to how many hints were taken."""

import json
import sys

from text_adventure_games.hints import Hint
from text_adventure_games.reporting import CaptureRenderer, Channel
from text_adventure_games.adventures import tomb_of_nassak_an_rah as tomb

sys.path.insert(0, "app")


def _game():
    g = tomb.build_game(seed=0)
    return g


def _texts(game):
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return cap


def test_a_game_without_hints_says_so():
    g = _game()
    g.hints = []
    cap = _texts(g)
    g.do_command("hint")
    assert "keeps its own counsel" in " ".join(cap.texts(Channel.BLOCKED))


def test_menu_lists_only_met_and_unsolved_topics():
    g = _game()
    cap = _texts(g)
    g.do_command("hint")
    menu = " ".join(cap.texts(Channel.NARRATION))
    assert "see anything" in menu  # light: always available
    assert "crimson seal" not in menu  # canopic not visited: unspoiled
    assert "Fungal Horror" not in menu  # the endgame stays dark
    g.locations["Hall of the Canopic Jars"].has_been_visited = True
    cap2 = _texts(g)
    g.do_command("hint")
    assert "crimson seal" in " ".join(cap2.texts(Channel.NARRATION))


def test_each_ask_reveals_one_more_level_and_it_costs_no_turn():
    g = _game()
    cap = _texts(g)
    turn = g.turn
    g.do_command("hint light")
    first = " ".join(cap.texts(Channel.NARRATION))
    assert "did not die carrying nothing" in first
    assert "SEARCH" not in first  # level 2 stays unbought
    g.do_command("hint light")
    second = " ".join(cap.texts(Channel.NARRATION))
    assert "SEARCH the dead merchant" in second
    assert g.turn == turn  # consulting the booklet costs no time
    assert g.hints_taken == 2
    g.do_command("hint light")  # level 3
    g.do_command("hint light")  # fully revealed: re-read only
    assert g.hints_taken == 3
    assert "That is the whole of it" in " ".join(cap.texts(Channel.NARRATION))


def test_topics_answer_to_number_key_and_question_words():
    g = _game()
    cap = _texts(g)
    g.do_command("hint 1")
    g.do_command("hint light")
    g.do_command("hint missing")  # a word from the score question
    assert g.hint_progress.get("light") == 2
    assert g.hint_progress.get("score") == 1
    g.do_command("hint frobnicate")
    assert "No open question" in " ".join(cap.texts(Channel.BLOCKED))
    assert g.hints_taken == 3  # the miss bought nothing


def test_solved_topics_leave_the_menu():
    g = _game()
    g.award("first_light", 5)
    cap = _texts(g)
    g.do_command("hint")
    assert "see anything" not in " ".join(cap.texts(Channel.NARRATION))


def test_reveals_survive_the_journal_replay():
    """HINT is a journaled free action: a (seed, journal) save must restore
    the same reveal depth and the same honesty counter."""
    g = _game()
    _texts(g)
    g.do_command("go north")
    g.do_command("hint light")
    g.do_command("hint light")
    assert "hint light" in g.journal
    g2 = tomb.build_game(seed=0)
    g2.parser.set_renderer(CaptureRenderer())
    g2.replay(list(g.journal))
    assert g2.hint_progress.get("light") == 2
    assert g2.hints_taken == 2


def test_the_dead_may_still_read_the_booklet():
    g = _game()
    g.player.set_property("is_dead", True)
    cap = _texts(g)
    g.do_command("hint")
    assert "questions worth asking" in " ".join(cap.texts(Channel.NARRATION))


def test_the_bridge_reports_hints_taken():
    import app_api

    app_api.boot(0)
    app_api.command("hint light")
    payload = json.loads(app_api.command("hint light"))
    assert payload["status"]["hints"] == 2
    assert "hint" in payload["suggestions"]["verbs"]
