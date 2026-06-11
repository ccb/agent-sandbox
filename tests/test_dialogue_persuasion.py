"""Offline tests for goal-influencing dialogue / persuasion (issue #46).

A speaker's utterance reaches only co-located listeners (the `heard` buffer,
scoped by Game.audience_for); a listener's LLM agent may then adopt or drop a
goal through the normal precondition gate. Driven by the deterministic
MockReActClient so the whole thing runs offline and for free.
"""

from text_adventure_games import games, things
from text_adventure_games.things.characters import Character, GoalType, HEARD_MAX


def test_hear_appends_and_trims_to_cap():
    c = Character("bob", "a fellow", "I listen.")
    for i in range(HEARD_MAX + 3):
        c.hear(f"line {i}")
    assert len(c.heard) == HEARD_MAX
    # The three oldest entries (0, 1, 2) were dropped; newest is kept.
    assert c.heard[0] == "line 3"
    assert c.heard[-1] == f"line {HEARD_MAX + 2}"


def test_clear_heard_empties_buffer():
    c = Character("bob", "a fellow", "I listen.")
    c.hear("something")
    c.clear_heard()
    assert c.heard == []


def test_audience_for_co_located_minus_speaker():
    field = things.Location("Field", "A field.")
    alice = things.Character("alice", "a herald", "I speak.")
    bob = things.Character("bob", "a fellow", "I listen.")
    game = games.Game(field, alice, characters=[bob])
    field.add_character(bob)

    audience = game.audience_for(alice, "hello", bob)
    assert bob in audience
    assert alice not in audience  # speaker never hears self


def test_audience_for_excludes_other_room():
    field = things.Location("Field", "A field.")
    forest = things.Location("Forest", "A forest.")
    field.add_connection("north", forest)
    alice = things.Character("alice", "a herald", "I speak.")
    carol = things.Character("carol", "afar", "I am elsewhere.")
    game = games.Game(field, alice, characters=[carol])
    forest.add_character(carol)  # not co-located with alice

    assert game.audience_for(alice, "hello") == []


def _two_char_room():
    """alice (player/speaker) and bob (listener), co-located in a field."""
    field = things.Location("Field", "A field.")
    alice = things.Character("alice", "a herald", "I speak.")
    bob = things.Character("bob", "a fellow", "I listen.")
    game = games.Game(field, alice, characters=[bob])
    field.add_character(bob)
    return game, alice, bob


def test_directed_speech_heard_as_to_you():
    game, alice, bob = _two_char_room()
    game.parser.parse_command("say to bob fetch the key", actor=alice)
    assert bob.heard == ["alice said to you: fetch the key"]


def test_broadcast_speech_heard_plainly():
    game, alice, bob = _two_char_room()
    game.parser.parse_command("say hello everyone", actor=alice)
    assert bob.heard == ["alice said: hello everyone"]


def test_speaker_does_not_hear_self():
    game, alice, bob = _two_char_room()
    game.parser.parse_command("say hello", actor=alice)
    assert alice.heard == []


def test_bystander_overhears_directed_speech():
    field = things.Location("Field", "A field.")
    alice = things.Character("alice", "a herald", "I speak.")
    bob = things.Character("bob", "a fellow", "I listen.")
    carol = things.Character("carol", "a bystander", "I overhear.")
    game = games.Game(field, alice, characters=[bob, carol])
    field.add_character(bob)
    field.add_character(carol)
    game.parser.parse_command("say to bob secret plan", actor=alice)
    assert carol.heard == ["alice said to bob: secret plan"]


def test_other_room_does_not_hear_broadcast():
    field = things.Location("Field", "A field.")
    forest = things.Location("Forest", "A forest.")
    field.add_connection("north", forest)
    alice = things.Character("alice", "a herald", "I speak.")
    carol = things.Character("carol", "afar", "I am elsewhere.")
    game = games.Game(field, alice, characters=[carol])
    forest.add_character(carol)
    game.parser.parse_command("say hello", actor=alice)
    assert carol.heard == []


from text_adventure_games.actions.goals import AdoptGoal, DropGoal


def _solo_game():
    """A single character (used as the player) in a field."""
    field = things.Location("Field", "A field.")
    bob = things.Character("bob", "a fellow", "I listen.")
    game = games.Game(field, bob)
    return game, bob


def test_adopt_goal_adds_short_goal():
    game, bob = _solo_game()
    AdoptGoal(game, "adopt goal fetch the key", actor=bob)()
    assert any(
        g.description == "fetch the key" and g.type == GoalType.SHORT and not g.done
        for g in bob.goals
    )


def test_adopt_goal_empty_text_fails():
    game, bob = _solo_game()
    action = AdoptGoal(game, "adopt goal", actor=bob)
    assert action.check_preconditions() is False
    assert bob.goals == []


def test_adopt_goal_duplicate_fails():
    game, bob = _solo_game()
    bob.add_goal("fetch the key", GoalType.SHORT)
    action = AdoptGoal(game, "adopt goal fetch the key", actor=bob)
    assert action.check_preconditions() is False
    assert len(bob.goals) == 1


def test_drop_goal_removes_it():
    game, bob = _solo_game()
    bob.add_goal("fetch the key", GoalType.SHORT)
    DropGoal(game, "drop goal fetch the key", actor=bob)()
    assert bob.goals == []


def test_drop_goal_not_held_fails():
    game, bob = _solo_game()
    action = DropGoal(game, "drop goal nonexistent", actor=bob)
    assert action.check_preconditions() is False
