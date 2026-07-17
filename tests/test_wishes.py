"""Tests for the action-wish demand channel (#620): the ActionWish record,
the Game.log_wish sink, the AGENT_WISH trace channel, and the propose verb."""

from text_adventure_games import games, things
from text_adventure_games.reporting import CaptureRenderer, Channel
from text_adventure_games.wishes import (
    ActionWish,
    TRIGGER_PARSE_GAP,
    TRIGGER_PROPOSED,
)

# ----------------------------------------------------------------------
# Section A: the ActionWish record
# ----------------------------------------------------------------------


def test_action_wish_to_primitive_round_trips_all_fields():
    wish = ActionWish(
        actor="Sofia",
        turn=13,
        location="Houston Kitchen",
        desired="fill the pot from the sink",
        reason="boiling needs water in the pot",
        trigger=TRIGGER_PROPOSED,
        goals=["make the water safe to drink"],
        scope=["pot", "stove", "sink", "Diego"],
        raw_command="propose fill the pot from the sink because boiling needs water in the pot",
    )
    assert wish.to_primitive() == {
        "actor": "Sofia",
        "turn": 13,
        "location": "Houston Kitchen",
        "desired": "fill the pot from the sink",
        "reason": "boiling needs water in the pot",
        "trigger": "proposed",
        "goals": ["make the water safe to drink"],
        "scope": ["pot", "stove", "sink", "Diego"],
        "raw_command": "propose fill the pot from the sink because boiling needs water in the pot",
        "meta": {},
    }


def test_action_wish_defaults_are_empty_not_shared():
    a = ActionWish(actor=None, turn=0, location=None, desired="x")
    b = ActionWish(actor=None, turn=0, location=None, desired="y")
    a.goals.append("mutated")
    a.meta["k"] = "v"
    assert b.goals == [] and b.scope == [] and b.meta == {}
    assert a.reason == "" and a.trigger == TRIGGER_PROPOSED


def test_trigger_constants():
    # #621 (parse-gap capture) will use the reserved constant; pin both values
    # because wishes.jsonl consumers key on them (#622/#623).
    assert TRIGGER_PROPOSED == "proposed"
    assert TRIGGER_PARSE_GAP == "parse_gap"
