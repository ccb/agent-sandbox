"""Tests for the general-purpose follow mechanism (issue #112).

Following is cascade-on-move: when a character moves, the engine drags everyone
following them along *during that move* (not on the follower's own later turn),
so it's correct regardless of turn order. A follower may decline a destination
via `follow_filter`.
"""

from text_adventure_games import games, things
from text_adventure_games.actions import locations as loc_actions
from text_adventure_games.actions import talk as talk_actions
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world():
    """Two rooms (A north<->south B), a player and a dog NPC, both in A."""
    a = things.Location("A", "Room A.")
    b = things.Location("B", "Room B.")
    a.add_connection("north", b)  # auto-reverses: b -> south -> a
    player = things.Character("player", "the player", "I lead.")
    dog = things.Character("dog", "a shaggy dog", "I am a good dog.")
    game = games.Game(a, player, characters=[dog])
    a.add_character(dog)
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, a, b, player, dog, cap


def _go(game, character, direction):
    loc_actions.Go(game, f"go {direction}", actor=character)()


# --- the cascade: a follower moves with the leader, same command ------------


def test_follower_moves_with_leader_during_the_move():
    game, a, b, player, dog, cap = _world()
    dog.following = player

    _go(game, player, "north")  # one player move

    assert player.location is b
    assert dog.location is b  # dragged along in the same move, not a later turn
    assert any("dog follows you" in t.lower() for t in cap.texts(Channel.NPC_NARRATION))


def test_non_follower_stays_put():
    game, a, b, player, dog, cap = _world()  # dog.following is None
    _go(game, player, "north")
    assert player.location is b
    assert dog.location is a


def test_follow_filter_lets_a_follower_refuse_a_destination():
    game, a, b, player, dog, cap = _world()
    dog.following = player
    dog.follow_filter = lambda dest: dest.name != "B"  # the dog won't enter B

    _go(game, player, "north")

    assert player.location is b
    assert dog.location is a  # stayed behind
    assert dog.following is player  # but still following -- waits to rejoin
    assert any(
        "won't go any farther" in t.lower() for t in cap.texts(Channel.NPC_NARRATION)
    )


def test_follower_rejoins_when_leader_returns():
    game, a, b, player, dog, cap = _world()
    dog.following = player
    dog.follow_filter = lambda dest: dest.name != "B"
    _go(game, player, "north")  # dog refuses, stays in A
    assert dog.location is a
    _go(game, player, "south")  # player back to A
    assert player.location is a and dog.location is a  # together again


# --- chains and cycles ------------------------------------------------------


def test_follow_chain_all_arrive_together():
    game, a, b, player, dog, cap = _world()
    cat = things.Character("cat", "a cat", "I am aloof.")
    game.add_character(cat)
    a.add_character(cat)
    dog.following = player
    cat.following = dog  # player <- dog <- cat

    _go(game, player, "north")

    assert player.location is b and dog.location is b and cat.location is b


def test_follow_cycle_is_safe():
    game, a, b, player, dog, cap = _world()
    cat = things.Character("cat", "a cat", "I am aloof.")
    game.add_character(cat)
    a.add_character(cat)
    dog.following = cat
    cat.following = dog  # mutual follow

    _go(game, dog, "north")  # should not infinite-loop

    assert dog.location is b
    assert cat.location is b  # dragged once, cycle guard stops there


# --- NPC-led following (turn-order independence) ----------------------------


def test_an_npc_can_lead_a_follower():
    game, a, b, player, dog, cap = _world()
    cat = things.Character("cat", "a cat", "I am aloof.")
    game.add_character(cat)
    a.add_character(cat)
    cat.following = dog  # the cat follows the dog, not the player

    _go(game, dog, "north")  # the dog (an NPC) moves

    assert dog.location is b and cat.location is b


# --- the Follow / Unfollow verbs -------------------------------------------


def test_follow_verb_sets_following():
    game, a, b, player, dog, cap = _world()
    talk_actions.Follow(game, "ask dog to follow", actor=player)()
    assert dog.following is player
    assert any("agrees to follow" in t.lower() for t in cap.texts(Channel.NARRATION))


def test_follow_verb_respects_refusal_gate():
    game, a, b, player, dog, cap = _world()
    dog.set_property("refuses_follow", True)
    dog.set_property("follow_refusal_message", "The dog growls and stays put.")

    action = talk_actions.Follow(game, "ask dog to follow", actor=player)
    assert action.check_preconditions() is False
    assert dog.following is None
    assert "growls" in (game.parser.last_fail_message or "")


def test_unfollow_clears_following():
    game, a, b, player, dog, cap = _world()
    dog.following = player

    talk_actions.Unfollow(game, "stop following", actor=player)()

    assert dog.following is None


# --- serialization ----------------------------------------------------------


def test_following_serializes_by_name():
    game, a, b, player, dog, cap = _world()
    dog.following = player
    assert dog.to_primitive().get("following") == "player"
