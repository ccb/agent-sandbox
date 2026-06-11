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
