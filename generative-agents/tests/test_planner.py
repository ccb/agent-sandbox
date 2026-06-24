"""Offline tests for the Smallville planners (issue #83, Phase D).

The engine plan data model + helpers are covered in the engine suite
(``tests/test_planning.py``). These cover the *port-side* planner: that
:class:`backend.planner.MockPlanner` reproduces a persona's authored
``world_data.yaml`` schedule exactly -- the property that lets it replace the
schedule source later without moving a single exported frame.

Fully offline (``build_world`` only, no maze assets, no LLM). Run from
``generative-agents``::

    uv run pytest tests/test_planner.py -v
"""

from backend.build_world import PERSONAS
from backend.planner import MockPlanner

from text_adventure_games.planning import DailyPlan, Planner


def test_mock_planner_reproduces_authored_schedule():
    # Every active persona's generated plan must equal its normalized schedule,
    # stop for stop -- this is what guarantees a byte-identical replay once the
    # planner is wired in.
    for spec in PERSONAS:
        plan = MockPlanner(spec).generate()
        assert [s.to_schedule_entry() for s in plan.stops] == spec["schedule"]


def test_mock_planner_leaves_higher_levels_empty():
    # The mock has only an authored minute plan -- no day/hour outline to recall.
    plan = MockPlanner(PERSONAS[0]).generate()
    assert plan.day == []
    assert plan.hours == []
    assert plan.revision == 0


def test_mock_planner_revise_is_noop():
    planner = MockPlanner(PERSONAS[0])
    plan = planner.generate()
    assert planner.revise(plan, trigger="anything") is plan


def test_mock_planner_satisfies_planner_protocol():
    assert isinstance(MockPlanner(PERSONAS[0]), Planner)


def test_generate_returns_fresh_stop_list():
    # Two generate() calls must not share the same mutable list, so a later
    # tail-revision on one plan can't bleed into another.
    planner = MockPlanner(PERSONAS[0])
    a = planner.generate()
    b = planner.generate()
    assert a.stops == b.stops
    assert a.stops is not b.stops
    assert isinstance(a, DailyPlan)
