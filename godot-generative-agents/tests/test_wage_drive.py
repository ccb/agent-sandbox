"""Tests for accrue_wage (#931 follow-up): an opt-in wage drive for personas
with a job, mirroring accrue_thirst's opt-in shape -- a persona with no
``wage_rate`` never accrues, so a non-job persona's bake is untouched.

Unlike thirst/energy/tiredness, wage pay is conditional on more than the rate
being set: the character must actually be settled on an authored ``is_work``
schedule stop, at that stop's place, right now -- having a job doesn't pay by
itself. These tests build the minimal fake schedule/location objects
accrue_wage actually reads (``char.agent.schedule._stop``, ``char.location``)
rather than a full game/world, matching test_drives.py's isolation style.

Run with: uv run pytest godot-generative-agents/tests/test_wage_drive.py -v
"""

import sys
from types import SimpleNamespace
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.drives import accrue_wage  # noqa: E402
import datetime

from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents  # noqa: E402
from backend.run_simulation import step  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402
from backend.sim_config import CognitionConfig  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
from text_adventure_games.things import Character  # noqa: E402


def _char(rate=5, stop=None, at="Houston Hall", activity="ringing up a sale"):
    """A character wired with just enough fake agent/schedule/location for
    accrue_wage to read -- no full game/world needed."""
    c = Character("Rosa", "a food-court worker", "Runs the counter.")
    if rate:
        c.set_property("wage_rate", rate)
    if stop is not None:
        c.agent = SimpleNamespace(schedule=SimpleNamespace(_stop=stop))
    if at is not None:
        c.location = SimpleNamespace(name=at)
    if activity:
        c.set_property("activity", activity)
    return c


_WORK_STOP = {"place": "Houston Hall", "activity": "ringing up a sale", "is_work": True}
_NON_WORK_STOP = {"place": "Houston Hall", "activity": "eating lunch", "is_work": False}


def test_no_wage_rate_is_a_noop():
    c = _char(rate=0, stop=_WORK_STOP)
    accrue_wage(c)
    assert c.get_property(Property.MONEY) is False  # never touched


def test_wage_accrues_while_on_the_work_stop_and_settled():
    c = _char(rate=5, stop=_WORK_STOP)
    c.set_property(Property.MONEY, 20)
    accrue_wage(c)
    assert c.get_property(Property.MONEY) == 25


def test_wage_does_not_accrue_on_a_non_work_stop():
    # Same location, but the current stop isn't tagged is_work -- e.g. Rosa
    # on her own lunch break shouldn't pay herself.
    c = _char(rate=5, stop=_NON_WORK_STOP)
    c.set_property(Property.MONEY, 20)
    accrue_wage(c)
    assert c.get_property(Property.MONEY) == 20


def test_wage_does_not_accrue_while_traveling_there():
    # No `activity` set yet -- still walking to the work stop, not settled.
    c = _char(rate=5, stop=_WORK_STOP, activity=None)
    c.set_property(Property.MONEY, 20)
    accrue_wage(c)
    assert c.get_property(Property.MONEY) == 20


def test_wage_does_not_accrue_when_deviated_off_plan():
    # The schedule says Houston Hall, but she's actually somewhere else --
    # a deviation, not her job.
    c = _char(rate=5, stop=_WORK_STOP, at="Van Pelt Library")
    c.set_property(Property.MONEY, 20)
    accrue_wage(c)
    assert c.get_property(Property.MONEY) == 20


def test_wage_does_not_accrue_without_an_attached_agent():
    # A bare test character (no .agent at all) must not crash accrue_wage --
    # the same defensive shape other drive functions already rely on.
    c = _char(rate=5, stop=None)
    c.set_property(Property.MONEY, 20)
    accrue_wage(c)
    assert c.get_property(Property.MONEY) == 20


_WAGE_LOCATIONS = [
    {
        "name": "Library",
        "description": "a small library",
        "address": "T:Library:desks",
        "hub": True,
    },
    {
        "name": "Houston Hall",
        "description": "a food court",
        "address": "T:HoustonHall:counter",
    },
]


class _TwoTileStubMap:
    def walk_path(self, src, address, furniture=None):
        return [(1, 1), (2, 2)]


def _wage_clock():
    return SimClock(datetime.datetime(2023, 2, 13, 12, 0, 0), sec_per_step=10)


def _wage_persona():
    return {
        "name": "Rosa",
        "home": "Library",
        "persona": "Rosa runs the Houston Hall counter.",
        "emoji": "\U0001f956",
        "start_tile": [0, 0],
        "destination": "Library",
        "activity": "reading",
        "wage_rate": 5,
        "schedule": [
            {
                "place": "Library",
                "activity": "reading",
                "emoji": "\U0001f4d6",
                "steps": 1,
            },
            {
                "place": "Houston Hall",
                "activity": "ringing up a sale",
                "emoji": "\U0001f956",
                "steps": None,
                "is_work": True,
            },
        ],
    }


def _wage_state():
    return {
        "Rosa": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f4d6",
            "desc": "waking up",
            "performing": False,
            "perform_until": None,
            "reasoning": "(waking up)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }


def test_wage_does_not_accrue_while_walking_to_the_next_work_stop():
    # Regression (code review, 2026-08-13): the travel branch in
    # run_simulation.step never cleared Property "activity" when a new
    # travel command started, so accrue_wage's "settled, not still walking"
    # check (a truthy `activity`) stayed true from the PREVIOUS stop's
    # activity string for the whole walk to the next stop -- paying wage
    # while Rosa is still in transit to Houston Hall.
    persona = _wage_persona()
    game, chars = build_world(None, [persona], _WAGE_LOCATIONS)
    attach_agents(chars, [persona], llm_client=None)  # mock brain
    rosa = chars["Rosa"]
    rosa.set_property(Property.MONEY, 0)
    state = _wage_state()
    kwargs = dict(
        order=["Rosa"],
        world_map=_TwoTileStubMap(),
        emoji={"Rosa": "\U0001f956"},
        clock=_wage_clock(),
        cog=CognitionConfig(),
    )

    # Step 0: settles into stop 0 (Library, on-plan, non-work).
    step(game, {"Rosa": rosa}, state, 0, **kwargs)
    assert state["Rosa"]["performing"] is True
    assert rosa.get_property("activity")  # settled with a real activity label

    # Step 1: the 1-step stop completes -> advances -> re-decides -> travels
    # to Houston Hall. The stale "reading" activity must be cleared the
    # instant travel starts.
    step(game, {"Rosa": rosa}, state, 1, **kwargs)
    assert not rosa.get_property("activity")
    assert rosa.get_property(Property.MONEY) == 0

    # Keep stepping through the walk; wage must stay at 0 the whole time.
    step_idx = 2
    while state["Rosa"]["path"] and step_idx < 20:
        step(game, {"Rosa": rosa}, state, step_idx, **kwargs)
        assert rosa.get_property(Property.MONEY) == 0
        step_idx += 1
    assert step_idx < 20  # sanity: she actually arrived
