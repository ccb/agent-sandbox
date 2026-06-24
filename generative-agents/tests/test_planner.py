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

from backend.build_world import PERSONAS, build_world
from backend.planner import MockPlanner
from backend.smallville_agents import attach_agents, maybe_revise_plan

from text_adventure_games.planning import (
    BEHIND_SCHEDULE,
    DailyPlan,
    Planner,
    RevisionTrigger,
    Stop,
    replace_tail,
)


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


def test_attach_agents_routes_schedule_through_planner():
    # The wiring: attach_agents builds a MockPlanner per agent, keeps it (and the
    # generated plan) on the agent, and the client's schedule comes from the
    # plan's stops -- not straight from the persona dict. This is what lets a real
    # LLMPlanner replace the schedule source later without touching the loop.
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    for spec in PERSONAS:
        agent = chars[spec["name"]].agent
        assert isinstance(agent.planner, MockPlanner)
        assert isinstance(agent.plan, DailyPlan)
        # The client drives exactly the plan's stops, which equal the schedule.
        assert agent.llm_client.schedule == [
            s.to_schedule_entry() for s in agent.plan.stops
        ]
        assert agent.llm_client.schedule == spec["schedule"]


class _RevisingPlanner:
    """A planner that rewrites the tail on the first revise() call.

    Stands in for the future LLMPlanner so the revision seam can be tested without
    a model: it preserves the executed prefix (via ``replace_tail``) and swaps in
    ``new_tail`` for everything after ``after``.
    """

    def __init__(self, base: DailyPlan, after: int, new_tail: list[Stop]):
        self._base, self._after, self._new_tail = base, after, new_tail
        self.calls: list = []

    def generate(self, persona=None, memory=None, clock=None) -> DailyPlan:
        return self._base

    def revise(self, plan, trigger, memory=None, clock=None) -> DailyPlan:
        self.calls.append(trigger)
        return replace_tail(plan, self._after, self._new_tail)


def test_maybe_revise_plan_commits_tail_and_protects_prefix():
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    char = chars[PERSONAS[0]["name"]]
    agent = char.agent
    original = agent.plan
    # The agent is mid-day: it has started stop 0 (the client's stop_index).
    agent.llm_client.stop_index = 0
    new_tail = [Stop("Johnson Park", "regrouping after a change of plans", "🌳", 50)]
    agent.planner = _RevisingPlanner(original, after=0, new_tail=new_tail)

    changed = maybe_revise_plan(char, RevisionTrigger(BEHIND_SCHEDULE, 360), clock=None)

    assert changed is True
    assert agent.planner.calls == [RevisionTrigger(BEHIND_SCHEDULE, 360)]
    # Executed/current stop 0 is preserved; the tail is the planner's new stops.
    assert agent.plan.stops[0] == original.stops[0]
    assert agent.plan.stops[1:] == new_tail
    assert agent.plan.revision == original.revision + 1
    # The client now drives the revised schedule, stop_index intact.
    assert agent.llm_client.stop_index == 0
    assert agent.llm_client.schedule == [
        s.to_schedule_entry() for s in agent.plan.stops
    ]


def test_maybe_revise_plan_reanchors_when_planner_rewrites_a_past_stop():
    # Even if a planner wrongly rewrites stop 0, the loop keeps the real prefix.
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    char = chars[PERSONAS[0]["name"]]
    agent = char.agent
    original = agent.plan
    agent.llm_client.stop_index = 1  # already past stops 0 and 1

    class _BadPlanner:
        def generate(self, **_):
            return original

        def revise(self, plan, trigger, memory=None, clock=None):
            # Rewrites EVERY stop, including already-executed 0 and 1.
            return DailyPlan(stops=[Stop("Nowhere", "wrong", steps=5)] * 4)

    agent.planner = _BadPlanner()
    maybe_revise_plan(char, RevisionTrigger(BEHIND_SCHEDULE, 360))

    # Stops 0 and 1 are untouched ground truth; only stops past index 1 changed.
    assert agent.plan.stops[:2] == original.stops[:2]


def test_maybe_revise_plan_noop_planner_changes_nothing():
    game, chars = build_world()
    attach_agents(chars, PERSONAS)  # MockPlanner: revise is a no-op
    char = chars[PERSONAS[0]["name"]]
    before = list(char.agent.llm_client.schedule)
    changed = maybe_revise_plan(char, RevisionTrigger(BEHIND_SCHEDULE, 360))
    assert changed is False
    assert char.agent.llm_client.schedule == before


def test_generate_returns_fresh_stop_list():
    # Two generate() calls must not share the same mutable list, so a later
    # tail-revision on one plan can't bleed into another.
    planner = MockPlanner(PERSONAS[0])
    a = planner.generate()
    b = planner.generate()
    assert a.stops == b.stops
    assert a.stops is not b.stops
    assert isinstance(a, DailyPlan)
