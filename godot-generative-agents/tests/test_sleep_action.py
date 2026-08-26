"""Tests for Sleep (#931): a Penn action that recovers energy over time.

Modeled on Action Castle's Sleep/SleepGate work: falling asleep is gated (too
energetic / no sleep-capable spot in scope) and sets Property.IS_SLEEPING.
Unlike Action Castle, Sleep gates on a world-tagged affordance (mirroring
Study's REQUIRED_AFFORDANCES = ("studyable",)) rather than always being
available -- so a location needs a "sleepable" tag before Sleep is reachable
there. Most of these tests use this file's own tiny world; the last one is a
wiring check that the real Penn world actually furnishes one too.

"Tired enough to sleep" is Property.IS_SLEEPY -- the same flag
drives.accrue_tiredness flips once its independent "restedness" resource
crosses its low-restedness threshold, not a separate raw-energy comparison of
Sleep's own. That keeps "the system says you're sleepy" and "you're allowed
to sleep" as one signal instead of two independently tuned numbers that could
disagree.

Penn's step loop is externally ticked (live server / bake), unlike Action
Castle's do_command single-command round, so Sleep can't fast-forward turns
the way Action Castle's does. These tests reflect that: Sleep only sets
is_sleeping; the *drive* (drives.sleep_accumulation, see
test_tiredness_drive.py) restores restedness on subsequent ticks instead --
never Property.ENERGY, which is hunger's resource, not sleep's (#931
follow-up).

Run with: uv run pytest godot-generative-agents/tests/test_sleep_action.py -v
"""

from backend.actions import Sleep  # noqa: E402
from backend.build_world import _normalize_personas, build_world  # noqa: E402
from backend.drives import accrue_tiredness  # noqa: E402
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
    char.set_property(Property.IS_SLEEPY, True)
    game.characters["Testa"].location = game.locations["Campus"]
    assert not game.parser.parse_command("sleep", actor=char)
    assert not char.get_property(Property.IS_SLEEPING)


def test_sleep_fails_when_not_tired():
    game, char = _tiny_world(extra_actions=[Sleep])
    # IS_SLEEPY defaults to False -- never set here.
    assert not game.parser.parse_command("sleep", actor=char)
    assert not char.get_property(Property.IS_SLEEPING)


def test_sleep_succeeds_at_a_sleepable_location_when_tired():
    game, char = _tiny_world(extra_actions=[Sleep])
    char.set_property(Property.IS_SLEEPY, True)
    assert game.parser.parse_command("sleep", actor=char)
    assert char.get_property(Property.IS_SLEEPING) is True


def test_sleep_succeeds_once_accrue_tiredness_flips_is_sleepy():
    # The unification this action relies on: Sleep doesn't compare restedness
    # itself, it trusts whatever accrue_tiredness already decided about
    # IS_SLEEPY -- so decaying restedness via the real drive is enough to
    # make Sleep reachable, with no separate threshold of Sleep's own
    # involved.
    game, char = _tiny_world(extra_actions=[Sleep])
    char.set_property("restedness", 100)
    assert not char.get_property(Property.IS_SLEEPY)
    accrue_tiredness(char)  # decays toward the low-restedness threshold (20)... not yet
    assert not game.parser.parse_command("sleep", actor=char)
    char.set_property("restedness", 20)  # at the threshold
    accrue_tiredness(char)  # decays past it
    assert char.get_property(Property.IS_SLEEPY)
    assert game.parser.parse_command("sleep", actor=char)
    assert char.get_property(Property.IS_SLEEPING) is True


def test_live_penn_world_has_a_sleepable_location():
    # Wiring check: the real Penn world (not this file's tiny synthetic one)
    # must actually furnish a "sleepable" location, or Sleep has nowhere to
    # be reached from in the live sim/bake -- same category of check as
    # test_eat_energy.py's test_live_penn_world_meals_carry_energy_value.
    from backend.penn.penn_world import build_penn_world

    world = build_penn_world()
    game, _characters = world.build_world_fn(world.world_map)
    sleepable = [
        loc for loc in game.locations.values() if loc.get_property("sleepable")
    ]
    assert sleepable, "expected at least one sleepable location in the Penn world"
