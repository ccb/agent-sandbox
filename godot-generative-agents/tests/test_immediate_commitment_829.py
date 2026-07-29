"""Immediate conversation commitments preempt at the playback boundary (#829).

Fully offline. Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
        godot-generative-agents/tests/test_immediate_commitment_829.py -v
"""

from backend import cognition
from backend.build_world import build_world
from backend.cognition import attach_agents, maybe_converse
from backend.planner import IMMEDIATE_REVISION_TOOL, MINUTE_TOOL, LLMPlanner
from backend.run_simulation import step
from text_adventure_games.memory import AgentMemory
from text_adventure_games.planning import (
    DailyPlan,
    IMMEDIATE_URGENCY,
    RevisionTrigger,
    Stop,
)
from text_adventure_games.things import Character


class _ImmediateTailClient:
    def __init__(self, result=None):
        self.result = result or {
            "next_stop": {
                "place": "Library",
                "activity": "race to the lecture",
                "minutes": 20,
                "start_hour": 15,
            },
            "later_stops": [{"place": "Cafe", "activity": "get coffee", "minutes": 10}],
        }
        self.calls = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append((tool["name"], messages[-1]["content"]))
        return self.result


def test_llm_planner_builds_an_immediate_tail_after_the_real_current_stop():
    client = _ImmediateTailClient()
    planner = LLMPlanner(client, known_places={"Studio", "Cafe", "Library"})
    plan = DailyPlan(
        stops=[
            Stop("Studio", "drawing", steps=10),
            Stop("Cafe", "talking", steps=20),
            Stop("Studio", "editing", steps=30),
        ]
    )
    trigger = RevisionTrigger(
        cognition.CONVERSATION,
        12,
        "race to the Library right now",
        current_stop_index=1,
        urgency=cognition.COMMITMENT_IMMEDIATE,
    )

    revised = planner.revise(plan, trigger)

    assert client.calls[0][0] == "immediate_plan_revision"
    prompt = client.calls[0][1]
    assert "0. completed: drawing at Studio" in prompt
    assert "1. current: talking at Cafe" in prompt
    assert "2. upcoming: editing at Studio" in prompt
    assert revised.stops[:2] == plan.stops[:2]
    assert [stop.place for stop in revised.stops[2:]] == ["Library", "Cafe"]
    assert revised.immediate_next is True
    # Immediate supersedes the stale future clock gate returned by the model.
    assert revised.stops[2].start_hour is None


def test_immediate_revision_without_a_valid_next_stop_is_a_no_op():
    planner = LLMPlanner(
        _ImmediateTailClient(
            {"next_stop": {"place": "Nowhere", "activity": "leave"}, "later_stops": []}
        ),
        known_places={"Cafe"},
    )
    plan = DailyPlan(stops=[Stop("Cafe", "reading", steps=10)])
    trigger = RevisionTrigger(
        cognition.CONVERSATION,
        3,
        "leave now",
        current_stop_index=0,
        urgency=cognition.COMMITMENT_IMMEDIATE,
    )

    assert planner.revise(plan, trigger) is plan


class _ImmediatePlanner:
    def __init__(self, mark_immediate=True):
        self.triggers = []
        self.mark_immediate = mark_immediate

    def generate(self, persona=None, memory=None, clock=None):
        return DailyPlan(stops=[Stop("Cafe", "reading", steps=100)])

    def revise(self, plan, trigger=None, memory=None, clock=None):
        self.triggers.append(trigger)
        return DailyPlan(
            stops=list(plan.stops)
            + [
                Stop(
                    "Library",
                    "race to the lecture",
                    steps=10,
                    start_hour=15,
                )
            ],
            revision=plan.revision + 1,
            immediate_next=(
                self.mark_immediate
                and getattr(trigger, "urgency", "normal") == IMMEDIATE_URGENCY
            ),
        )


class _ImmediateOutcomeBrain:
    def __init__(self):
        self.context = {}

    def chat(self, messages, max_tokens=256, temperature=0.0):
        # The integration assertion is the pre-decision schedule transition;
        # idling afterward keeps the test focused on that boundary.
        return None

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        if tool["name"] == "conversation_outcome":
            return {
                "plans_changed": True,
                "commitment": "race to the Library right now",
                "commitment_timing": "immediate",
            }
        return {"utterance": "Let's race to the Library right now.", "done": True}


class _OutcomeOnlyBrain:
    def __init__(self, result):
        self.result = result
        self.context = {}

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        return self.result


def _bare_agent(planner, brain=None):
    char = Character("Maria Lopez", "Maria", "")
    agent = type("AgentStub", (), {})()
    agent.memory = AgentMemory()
    agent.memory.owner = char.name
    agent.planner = planner
    agent.plan = planner.generate()
    agent.schedule = cognition.ScheduleMockClient(
        [stop.to_schedule_entry() for stop in agent.plan.stops]
    )
    agent.llm_client = brain if brain is not None else object()
    agent.max_tokens = 256
    agent._structured_system_message = lambda: "You are Maria Lopez."
    char.set_agent(agent)
    return char


def test_revision_context_comes_from_the_schedule_and_clears_the_clock_gate():
    planner = _ImmediatePlanner()
    char = _bare_agent(planner)

    result = cognition.maybe_revise_plan(
        char,
        RevisionTrigger(
            cognition.CONVERSATION,
            5,
            "leave now",
            urgency=cognition.COMMITMENT_IMMEDIATE,
        ),
    )

    assert planner.triggers[0].current_stop_index == 0
    assert result == cognition.PlanRevisionResult(changed=True, immediate_next=True)
    assert char.agent.plan.stops[0].activity == "reading"
    assert char.agent.plan.stops[1].activity == "race to the lecture"
    assert char.agent.plan.stops[1].start_hour is None
    assert "start_hour" not in char.agent.schedule.schedule[1]


def test_unmarked_custom_planner_tail_cannot_bypass_the_clock_gate():
    planner = _ImmediatePlanner(mark_immediate=False)
    char = _bare_agent(planner)

    result = cognition.maybe_revise_plan(
        char,
        RevisionTrigger(
            cognition.CONVERSATION,
            5,
            "leave now",
            urgency=IMMEDIATE_URGENCY,
        ),
    )

    assert result == cognition.PlanRevisionResult(changed=True)
    assert char.agent.plan.stops[1].start_hour == 15
    assert char.agent.plan.immediate_next is False
    assert char.agent.schedule.schedule[1]["start_hour"] == 15


def test_immediate_tool_stop_schemas_are_independent_copies():
    minute_stop = MINUTE_TOOL["parameters"]["properties"]["stops"]["items"]
    immediate = IMMEDIATE_REVISION_TOOL["parameters"]["properties"]
    next_stop = immediate["next_stop"]
    later_stop = immediate["later_stops"]["items"]

    assert next_stop == minute_stop
    assert later_stop == minute_stop
    assert next_stop is not minute_stop
    assert later_stop is not minute_stop
    assert next_stop is not later_stop


def test_immediate_requires_a_nonblank_commitment():
    planner = _ImmediatePlanner()
    char = _bare_agent(
        planner,
        _OutcomeOnlyBrain(
            {
                "plans_changed": True,
                "commitment": "   ",
                "commitment_timing": "immediate",
            }
        ),
    )

    result = cognition.apply_conversation_outcome(
        char, "Ayesha Khan", "Maria: Now?\nAyesha: Yes.", step=5
    )

    assert result.changed is True
    assert result.immediate_next is False
    assert planner.triggers[0].urgency == "normal"
    # A non-immediate revision preserves the planner's future anchor.
    assert char.agent.plan.stops[1].start_hour == 15


def test_scheduled_commitment_changes_the_tail_without_preempting():
    planner = _ImmediatePlanner()
    char = _bare_agent(
        planner,
        _OutcomeOnlyBrain(
            {
                "plans_changed": True,
                "commitment": "meet at the Library at 3pm",
                "commitment_timing": "scheduled",
            }
        ),
    )

    result = cognition.apply_conversation_outcome(
        char, "Ayesha Khan", "Maria: Library at three?\nAyesha: Yes.", step=5
    )

    assert result == cognition.PlanRevisionResult(changed=True)
    assert planner.triggers[0].urgency == "normal"
    assert char.agent.plan.stops[1].start_hour == 15


def test_only_the_participant_with_an_immediate_tail_expires():
    state = _settled_state(["Maria Lopez", "Ayesha Khan"])
    expired = cognition._expire_immediate_commitments(
        state,
        {
            "Maria Lopez": cognition.PlanRevisionResult(
                changed=True, immediate_next=True
            ),
            "Ayesha Khan": cognition.PlanRevisionResult(changed=True),
        },
        5,
    )

    assert expired == {"Maria Lopez"}
    assert state["Maria Lopez"]["perform_until"] == 5
    assert state["Ayesha Khan"]["perform_until"] == 100


_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Cafe", "description": "a cafe", "address": "T:Cafe:counter"},
    {"name": "Library", "description": "a library", "address": "T:Library:desks"},
]


def _persona(name):
    return {
        "name": name,
        "home": "Plaza",
        "persona": f"I am {name}.",
        "emoji": "🧑",
        "start_tile": [0, 0],
        "destination": "Cafe",
        "activity": "reading",
        "schedule": [
            {"place": "Cafe", "activity": "reading", "emoji": None, "steps": 100}
        ],
    }


def _settled_state(names):
    return {
        name: {
            "tile": (0, 0),
            "path": [],
            "pron": "🧑",
            "desc": "reading",
            "performing": True,
            "perform_until": 100,
            "reasoning": "",
            "memories": [],
            "chat": None,
            "stop_since": 0,
            "credit_stop": True,
            "conversing": False,
        }
        for name in names
    }


def test_immediate_commitment_expires_after_outcome_but_advances_after_playback():
    names = ["Maria Lopez", "Ayesha Khan"]
    personas = [_persona(name) for name in names]
    brain = _ImmediateOutcomeBrain()
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    plaza = game.locations["Plaza"]
    for name in names:
        char = chars[name]
        if char.location is not None:
            char.location.remove_character(char)
        plaza.add_character(char)
        char.agent.planner = _ImmediatePlanner()
        char.agent.plan = char.agent.planner.generate()
        char.agent.schedule.replace_schedule(
            [stop.to_schedule_entry() for stop in char.agent.plan.stops]
        )

    state = _settled_state(names)
    frame = {name: {} for name in names}
    active = {}

    completed = maybe_converse(
        game,
        chars,
        state,
        frame,
        4,
        {},
        names,
        clock=None,
        active=active,
        line_playback_steps=2,
    )

    assert completed == 1
    assert active  # the finished exchange is held for viewer playback
    for name in names:
        assert state[name]["perform_until"] == 4
        assert state[name]["conversing"] is True
        assert chars[name].agent.schedule.stop_index == 0
        assert chars[name].agent.schedule.schedule[1]["place"] == "Library"

    # Releasing playback still does not mutate the pointer inside cognition.
    maybe_converse(
        game,
        chars,
        state,
        frame,
        6,
        {},
        names,
        clock=None,
        active=active,
        line_playback_steps=2,
    )
    assert not active
    assert all(chars[name].agent.schedule.stop_index == 0 for name in names)

    # The next ordinary tick consumes the expired, credited latch through the
    # one schedule-advance authority and makes the immediate stop current.
    step(
        game,
        chars,
        state,
        7,
        order=names,
        world_map=None,
        emoji={name: "🧑" for name in names},
        conversation_enabled=False,
    )
    assert all(chars[name].agent.schedule.stop_index == 1 for name in names)


def test_immediate_outcome_does_not_preempt_a_reactive_midwalk_conversation():
    names = ["Maria Lopez", "Ayesha Khan"]
    personas = [_persona(name) for name in names]
    brain = _ImmediateOutcomeBrain()
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    for name in names:
        chars[name].agent.planner = _ImmediatePlanner()
        chars[name].agent.plan = chars[name].agent.planner.generate()

    state = _settled_state(names)
    state[names[0]]["performing"] = False
    state[names[0]]["perform_until"] = None
    state[names[0]]["path"] = [(1, 0), (2, 0)]
    convo_obj = type(
        "ConversationStub",
        (),
        {
            "happened": True,
            "transcript": lambda self: (
                "Maria Lopez: Let's go now.\nAyesha Khan: Yes."
            ),
        },
    )()

    _completed, revisions = cognition._finish_conversation(
        chars[names[0]], chars[names[1]], convo_obj, 5, {}, None
    )
    expired = cognition._expire_immediate_commitments(state, revisions, 5)

    assert revisions[names[0]].immediate_next is True
    assert names[0] not in expired
    assert names[1] in expired
    assert state[names[0]]["perform_until"] is None
    assert state[names[0]]["path"] == [(1, 0), (2, 0)]
    assert chars[names[0]].agent.schedule.stop_index == 0
