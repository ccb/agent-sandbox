"""Offline tests for the Smallville planners (issue #83, Phase D).

The engine plan data model + helpers are covered in the engine suite
(``tests/test_planning.py``). These cover the *port-side* planner: that
:class:`gen_agents.planner.MockPlanner` reproduces a persona's authored
``world_data.yaml`` schedule exactly -- the property that lets it replace the
schedule source later without moving a single exported frame.

Fully offline (``build_world`` only, no maze assets, no LLM). Run from
``generative-agents``::

    uv run pytest tests/test_planner.py -v
"""

import datetime

from gen_agents.build_world import PERSONAS, build_world
from gen_agents.planner import (
    DAY_OUTLINE_TOOL,
    HOURLY_TOOL,
    MINUTE_TOOL,
    LLMPlanner,
    MockPlanner,
)
from gen_agents.sim_clock import SimClock
from gen_agents.smallville_agents import attach_agents, maybe_revise_plan

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


class _ScriptedClient:
    """A fake ``LlmClient`` returning canned tool arguments by tool name.

    Lets the LLMPlanner's generate/revise logic be exercised deterministically and
    offline -- the real model is the same ``call_tool`` seam (Phase A swaps it in).
    """

    def __init__(self, by_tool: dict):
        self.by_tool = by_tool
        self.calls: list[str] = []
        self.user_by_tool: dict[str, str] = {}  # last user prompt per tool

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append(tool["name"])
        self.user_by_tool[tool["name"]] = messages[-1]["content"] if messages else ""
        return self.by_tool.get(tool["name"])

    def chat(self, *args, **kwargs):
        return None

    def count_tokens(self, text):
        return len(text.split())


_FULL_SCRIPT = {
    DAY_OUTLINE_TOOL["name"]: {
        "blocks": [
            {"label": "morning", "summary": "open and run the cafe"},
            {"label": "afternoon", "summary": "errands"},
        ]
    },
    HOURLY_TOOL["name"]: {
        "hours": [
            {"start_hour": 8, "summary": "tend the counter"},
            {"start_hour": 9, "summary": "buy milk"},
        ]
    },
    MINUTE_TOOL["name"]: {
        "stops": [
            {"place": "Hobbs Cafe", "activity": "tending", "emoji": "☕", "steps": 200},
            {"place": "Johnson Park", "activity": "a break", "steps": 100},
        ]
    },
}


def test_llm_planner_generates_decomposed_plan():
    planner = LLMPlanner(_ScriptedClient(_FULL_SCRIPT))
    plan = planner.generate(persona={"persona": "I am Isabella."})
    assert [b.label for b in plan.day] == ["morning", "afternoon"]
    assert [h.start_hour for h in plan.hours] == [8, 9]
    assert [s.place for s in plan.stops] == ["Hobbs Cafe", "Johnson Park"]
    assert plan.stops[0].steps == 200


def test_llm_planner_drops_unknown_places():
    script = {
        MINUTE_TOOL["name"]: {
            "stops": [
                {"place": "Hobbs Cafe", "activity": "coffee", "steps": 50},
                {"place": "Atlantis", "activity": "lost", "steps": 50},  # unknown
            ]
        }
    }
    planner = LLMPlanner(_ScriptedClient(script), known_places={"Hobbs Cafe"})
    plan = planner.generate(persona={"persona": "x"})
    assert [s.place for s in plan.stops] == ["Hobbs Cafe"]


def test_llm_planner_revise_rewrites_stops():
    base = LLMPlanner(_ScriptedClient(_FULL_SCRIPT)).generate(persona={"persona": "x"})
    revised_script = {
        MINUTE_TOOL["name"]: {
            "stops": [
                {"place": "The Rose and Crown Pub", "activity": "lunch", "steps": 80}
            ]
        }
    }
    planner = LLMPlanner(_ScriptedClient(revised_script))
    out = planner.revise(base, trigger=RevisionTrigger(BEHIND_SCHEDULE, 360))
    assert [s.place for s in out.stops] == ["The Rose and Crown Pub"]
    assert out.revision == base.revision + 1


def test_llm_planner_degrades_when_tool_returns_nothing():
    # A model/tool failure (call_tool -> None) yields empty levels, never raises;
    # revise with nothing usable returns the plan unchanged (a no-op to the loop).
    planner = LLMPlanner(_ScriptedClient({}))
    plan = planner.generate(persona={"persona": "x"})
    assert plan.day == [] and plan.hours == [] and plan.stops == []
    same = planner.revise(plan, trigger=RevisionTrigger(BEHIND_SCHEDULE, 1))
    assert same is plan


def test_llm_planner_satisfies_protocol():
    assert isinstance(LLMPlanner(_ScriptedClient({})), Planner)


def test_llm_planner_tolerates_string_array_items():
    # Reproduces the live failure (#78): the model returned tool arrays whose items
    # were strings, not objects. Parsing must drop them and degrade, never raise.
    script = {
        DAY_OUTLINE_TOOL["name"]: {"blocks": ["morning: cafe", "afternoon"]},
        HOURLY_TOOL["name"]: {
            "hours": ["8: tend", {"start_hour": 9, "summary": "milk"}]
        },
        MINUTE_TOOL["name"]: {"stops": ["Hobbs Cafe: tending", "Johnson Park"]},
    }
    plan = LLMPlanner(_ScriptedClient(script)).generate(persona={"persona": "x"})
    assert plan.day == []  # both string blocks dropped
    assert [h.start_hour for h in plan.hours] == [9]  # only the well-formed hour
    assert plan.stops == []  # both string stops dropped, no crash


def test_llm_planner_tolerates_non_list_tool_value():
    script = {MINUTE_TOOL["name"]: {"stops": "Hobbs Cafe then the park"}}
    plan = LLMPlanner(_ScriptedClient(script)).generate(persona={"persona": "x"})
    assert plan.stops == []


def test_llm_planner_coerces_numeric_string_fields():
    # A model may stringify numbers; coerce where sensible, drop garbage to None.
    script = {
        MINUTE_TOOL["name"]: {
            "stops": [
                {"place": "Hobbs Cafe", "activity": "tending", "steps": "200"},
                {"place": "Johnson Park", "activity": "a walk", "steps": "soon"},
            ]
        }
    }
    plan = LLMPlanner(_ScriptedClient(script)).generate(persona={"persona": "x"})
    assert plan.stops[0].steps == 200  # "200" -> 200
    assert plan.stops[1].steps is None  # unparseable -> stay put, not a crash


def test_attach_agents_uses_llm_planner_when_client_supplied():
    # The gate: a supplied planner_client routes every agent through LLMPlanner,
    # and the client drives the generated stops (known Smallville places).
    game, chars = build_world()
    attach_agents(chars, PERSONAS, planner_client=_ScriptedClient(_FULL_SCRIPT))
    agent = chars[PERSONAS[0]["name"]].agent
    assert isinstance(agent.planner, LLMPlanner)
    assert [s.place for s in agent.plan.stops] == ["Hobbs Cafe", "Johnson Park"]
    assert agent.llm_client.schedule == [
        s.to_schedule_entry() for s in agent.plan.stops
    ]


def test_llm_planner_bounds_prompts_to_the_run_window():
    # With a clock + run length, the day/hour prompts are bounded to the hours the
    # run actually covers (8-11am for 1080 steps at 10s/step), not a generic day.
    client = _ScriptedClient(_FULL_SCRIPT)
    clock = SimClock(datetime.datetime(2023, 2, 13, 8, 0, 0), sec_per_step=10)
    LLMPlanner(client, clock=clock, num_steps=1080).generate(persona={"persona": "x"})
    assert "08:00 to 11:00" in client.user_by_tool[DAY_OUTLINE_TOOL["name"]]
    assert "[8, 9, 10]" in client.user_by_tool[HOURLY_TOOL["name"]]


def test_llm_planner_unbounded_without_a_clock():
    client = _ScriptedClient(_FULL_SCRIPT)
    LLMPlanner(client).generate(persona={"persona": "x"})
    assert "runs from" not in client.user_by_tool[DAY_OUTLINE_TOOL["name"]]


def test_attach_agents_reports_planner_sources():
    # out_planner_sources records where each agent's plan came from, so a full run
    # can report how many were model-generated vs. fell back.
    _, chars = build_world()
    sources = {}
    attach_agents(
        chars,
        PERSONAS,
        planner_client=_ScriptedClient(_FULL_SCRIPT),
        out_planner_sources=sources,
    )
    assert set(sources) == {p["name"] for p in PERSONAS}
    assert all(s == "llm" for s in sources.values())


def test_attach_agents_reports_static_fallback_source():
    _, chars = build_world()
    sources = {}
    attach_agents(
        chars,
        [PERSONAS[0]],
        planner_client=_ScriptedClient({}),  # empty -> fallback
        out_planner_sources=sources,
    )
    assert sources[PERSONAS[0]["name"]] == "static"


def test_attach_agents_reports_mock_source_by_default():
    _, chars = build_world()
    sources = {}
    attach_agents(chars, PERSONAS, out_planner_sources=sources)
    assert all(s == "mock" for s in sources.values())


def test_attach_agents_falls_back_to_mock_on_empty_llm_plan():
    # If the model yields no usable stops, the agent must not be left scheduleless:
    # it falls back to the authored static schedule (MockPlanner).
    game, chars = build_world()
    spec = PERSONAS[0]
    attach_agents(chars, [spec], planner_client=_ScriptedClient({}))  # empty plan
    agent = chars[spec["name"]].agent
    assert isinstance(agent.planner, MockPlanner)
    assert agent.llm_client.schedule == spec["schedule"]


def test_generate_returns_fresh_stop_list():
    # Two generate() calls must not share the same mutable list, so a later
    # tail-revision on one plan can't bleed into another.
    planner = MockPlanner(PERSONAS[0])
    a = planner.generate()
    b = planner.generate()
    assert a.stops == b.stops
    assert a.stops is not b.stops
    assert isinstance(a, DailyPlan)
