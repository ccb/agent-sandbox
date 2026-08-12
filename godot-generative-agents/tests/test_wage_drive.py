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
