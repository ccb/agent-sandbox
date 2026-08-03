"""Tests for Sleep (#931): a Penn action that recovers energy over time.

Modeled on Action Castle's Sleep/SleepGate work: falling asleep is gated (too
energetic / no sleep-capable spot in scope) and sets Property.IS_SLEEPING.
Unlike Action Castle, Sleep gates on a world-tagged affordance (mirroring
Study's REQUIRED_AFFORDANCES = ("studyable",)) rather than always being
available -- so a location needs a "sleepable" tag before Sleep is reachable
there. (world_data_upenn.yaml doesn't have one yet -- Sleep is exercised here
via this file's own tiny world, not the live/bake one.)

Penn's step loop is externally ticked (live server / bake), unlike Action
Castle's do_command single-command round, so Sleep can't fast-forward turns
the way Action Castle's does. These tests reflect that: Sleep only sets
is_sleeping; the *drive* (drives.sleep_accumulation, see test_energy_drive.py)
restores energy on subsequent ticks instead.

Run with: uv run pytest godot-generative-agents/tests/test_sleep_action.py -v
"""

from backend.actions import Sleep  # noqa: E402
from backend.build_world import _normalize_personas, build_world  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402

LOCATIONS = [
    {
        "name": "Campus",
        "description": "The campus green.",
        "address": None,
        "hub": True,
    },
    {
        "name": "Dorm Room",
        "description": "A cramped dorm room.",
        "address": None,
        "properties": ["sleepable"],
    },
]


def _persona(schedule):
    return {
        "name": "Testa",
        "home": "Dorm Room",
        "persona": "I am Testa, a test persona.",
        "emoji": "🙂",
        "start_tile": [0, 0],
        "schedule": schedule,
    }


def _tiny_world(extra_actions=()):
    """(game, char) for a one-persona world with the given extra actions."""
    personas = _normalize_personas(
        [_persona([{"place": "Dorm Room", "activity": "resting", "steps": 5}])]
    )
    game, chars = build_world(
        None, personas, LOCATIONS, extra_actions=list(extra_actions)
    )
    return game, chars["Testa"]


def test_sleep_override_is_registered():
    game, _ = _tiny_world(extra_actions=[Sleep])
    assert game.parser.actions["sleep"] is Sleep


def test_sleep_fails_without_a_sleepable_location():
    game, char = _tiny_world(extra_actions=[Sleep])
    char.set_property(Property.ENERGY, 5)
    game.characters["Testa"].location = game.locations["Campus"]
    assert not game.parser.parse_command("sleep", actor=char)
    assert not char.get_property(Property.IS_SLEEPING)


def test_sleep_fails_when_not_tired():
    game, char = _tiny_world(extra_actions=[Sleep])
    char.set_property(Property.ENERGY, 90)
    assert not game.parser.parse_command("sleep", actor=char)
    assert not char.get_property(Property.IS_SLEEPING)


def test_sleep_succeeds_at_a_sleepable_location_when_tired():
    game, char = _tiny_world(extra_actions=[Sleep])
    char.set_property(Property.ENERGY, 5)
    assert game.parser.parse_command("sleep", actor=char)
    assert char.get_property(Property.IS_SLEEPING) is True
