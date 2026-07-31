"""TDD scaffold (implementation pending) for a Penn Sleep action.

Modeled on Action Castle's Sleep/SleepGate work: falling asleep should be
gated (too energetic / no sleep-capable spot in scope), set Property.IS_SLEEPING,
and restore Property.ENERGY over time. Unlike Action Castle, Sleep gates on a
world-tagged affordance (mirroring Study's REQUIRED_AFFORDANCES = ("studyable",))
rather than always being available -- so a location needs a "sleepable" tag
before this is even reachable in the real Penn world (see the TODO list: no
such location exists yet in world_data_upenn.yaml).

Whether Sleep should fast-forward turns internally (Action Castle's answer)
or something else entirely is an OPEN QUESTION here -- Penn's step loop is
externally ticked (live server / bake), unlike do_command's single-command
round, so that answer may not transfer as-is. These tests assume Sleep sets
is_sleeping and lets the *drive* (see test_energy_drive.py) restore energy on
subsequent ticks, rather than looping internally -- revisit once that
question is actually settled.

Expect failures (an ImportError at collection, until backend/actions.py grows
Sleep, and world_data_upenn.yaml grows a sleepable location).

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
