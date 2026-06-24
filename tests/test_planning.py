"""Tests for decomposable daily plans (issue #83, NEXT-STEPS Phase D).

Covers the pure data layer and helpers in ``text_adventure_games/planning.py``
-- everything that can be checked without an LLM or a running game, which is the
whole module by design:

  A. Serialization round-trips (``DailyPlan`` / ``Stop`` <-> primitives + the
     schedule-entry bridge the Smallville loop consumes).
  B. ``validate_stops`` keeps known places / valid durations and drops the rest.
  C. ``replace_tail`` preserves the executed prefix, swaps the tail, bumps the
     revision, and refuses an out-of-range index.
  D. ``even_step_split`` sums to exactly the total and stays as even as possible.
  E. ``plan_memory_lines`` renders one recallable line per altitude.

Run with pytest::

    pytest tests/test_planning.py -v
"""

import pytest

from text_adventure_games.planning import (
    DailyPlan,
    DayBlock,
    HourBlock,
    Planner,
    Stop,
    even_step_split,
    plan_memory_lines,
    replace_tail,
    validate_stops,
)


def _sample_plan() -> DailyPlan:
    return DailyPlan(
        day=[DayBlock("morning", "open the cafe"), DayBlock("midday", "errands")],
        hours=[HourBlock(8, "tend the counter"), HourBlock(10, "buy milk")],
        stops=[
            Stop("Hobbs Cafe", "tending the counter", "☕", 220),
            Stop("The Willows Market", "buying milk", "🛒", 150),
            Stop("Johnson Park", "a quiet break"),  # steps=None => stay
        ],
    )


# --- A. serialization -------------------------------------------------------


def test_dailyplan_primitive_round_trip():
    plan = _sample_plan()
    plan.revision = 3
    restored = DailyPlan.from_primitive(plan.to_primitive())
    assert restored == plan


def test_from_primitive_tolerates_missing_keys():
    # A lean payload (only stops) still loads, defaulting the rest.
    plan = DailyPlan.from_primitive({"stops": [{"place": "Pub", "activity": "rest"}]})
    assert plan.day == []
    assert plan.hours == []
    assert plan.revision == 0
    assert plan.stops == [Stop("Pub", "rest", None, None)]


def test_stop_schedule_entry_bridge():
    stop = Stop("Hobbs Cafe", "tending the counter", "☕", 220)
    entry = stop.to_schedule_entry()
    assert entry == {
        "place": "Hobbs Cafe",
        "activity": "tending the counter",
        "emoji": "☕",
        "steps": 220,
    }
    # The bridge is loss-free, and tolerates a YAML stop that omits emoji/steps.
    assert Stop.from_schedule_entry(entry) == stop
    assert Stop.from_schedule_entry(
        {"place": "Johnson Park", "activity": "a walk"}
    ) == Stop("Johnson Park", "a walk", None, None)


# --- B. validate_stops ------------------------------------------------------


def test_validate_stops_partitions_known_and_unknown():
    known = {"Hobbs Cafe", "Johnson Park"}
    stops = [
        Stop("Hobbs Cafe", "coffee", steps=100),
        Stop("Atlantis", "lost", steps=50),  # unknown place -> dropped
        Stop("Johnson Park", "stay", steps=None),  # None steps is valid
    ]
    kept, dropped = validate_stops(stops, known)
    assert [s.place for s in kept] == ["Hobbs Cafe", "Johnson Park"]
    assert [s.place for s in dropped] == ["Atlantis"]


@pytest.mark.parametrize("bad_steps", [0, -5, True, 1.5, "100"])
def test_validate_stops_rejects_nonpositive_or_nonint_steps(bad_steps):
    kept, dropped = validate_stops(
        [Stop("Hobbs Cafe", "coffee", steps=bad_steps)], {"Hobbs Cafe"}
    )
    assert kept == []
    assert len(dropped) == 1


# --- C. replace_tail --------------------------------------------------------


def test_replace_tail_preserves_prefix_and_bumps_revision():
    plan = _sample_plan()
    new_tail = [Stop("Oak Hill College", "studying", "📚", 90)]
    # after=0 => keep stop 0 (executed/current), replace everything past it.
    revised = replace_tail(plan, after=0, new_stops=new_tail)
    assert revised.stops[0] == plan.stops[0]  # untouched
    assert revised.stops[1:] == new_tail  # tail swapped
    assert revised.revision == plan.revision + 1
    # The original plan is not mutated (replace() returns a copy).
    assert len(plan.stops) == 3


def test_replace_tail_after_negative_one_replaces_everything():
    plan = _sample_plan()
    revised = replace_tail(plan, after=-1, new_stops=[Stop("Pub", "rest", steps=10)])
    assert revised.stops == [Stop("Pub", "rest", None, 10)]


def test_replace_tail_rejects_index_below_negative_one():
    with pytest.raises(ValueError):
        replace_tail(_sample_plan(), after=-2, new_stops=[])


# --- D. even_step_split -----------------------------------------------------


@pytest.mark.parametrize(
    "total,n,expected",
    [
        (360, 3, [120, 120, 120]),  # exact
        (10, 3, [4, 3, 3]),  # remainder spread onto the leading parts
        (5, 5, [1, 1, 1, 1, 1]),  # one each
    ],
)
def test_even_step_split_values(total, n, expected):
    parts = even_step_split(total, n)
    assert parts == expected
    assert sum(parts) == total  # never drifts


def test_even_step_split_guards():
    with pytest.raises(ValueError):
        even_step_split(10, 0)  # n must be positive
    with pytest.raises(ValueError):
        even_step_split(2, 3)  # can't make 3 positive parts from 2 steps


# --- E. plan_memory_lines ---------------------------------------------------


def test_plan_memory_lines_one_per_altitude():
    lines = plan_memory_lines(_sample_plan())
    assert any("outline" in ln for ln in lines)
    assert any(ln.startswith("At 08:00") for ln in lines)
    assert any(ln.startswith("At 10:00") for ln in lines)
    assert any("My stops today" in ln for ln in lines)


def test_plan_memory_lines_empty_plan_is_empty():
    assert plan_memory_lines(DailyPlan()) == []


# --- protocol ---------------------------------------------------------------


def test_planner_protocol_is_runtime_checkable():
    class _NoopPlanner:
        def generate(self, persona, memory, clock):
            return DailyPlan()

        def revise(self, plan, trigger, memory, clock):
            return plan

    assert isinstance(_NoopPlanner(), Planner)
    assert not isinstance(object(), Planner)
