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
