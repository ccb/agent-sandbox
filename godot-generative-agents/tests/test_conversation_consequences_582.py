"""Conversation consequences (issue #582).

A meeting can change the rest of the day and the relationship: an agreement
becomes a plan revision, a notable exchange a durable relationship memory. One
structured ``conversation_outcome`` call per participant, at the tail of
``maybe_converse``, only when a real brain drove an actual conversation.

Fully offline (fake brains + fake planners). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_conversation_consequences_582.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_pacing_authority_581.py: the Penn sim modules run as
# scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend import cognition  # noqa: E402
from backend.prompt_templates import render  # noqa: E402


def test_trigger_and_importance_constants():
    assert cognition.CONVERSATION == "conversation"
    assert cognition.RELATIONSHIP_NOTE_IMPORTANCE == 8.0


def test_outcome_tool_schema_shape():
    tool = cognition.CONVERSATION_OUTCOME_TOOL
    assert tool["name"] == "conversation_outcome"
    props = tool["parameters"]["properties"]
    assert set(props) == {"plans_changed", "commitment", "relationship_note"}
    assert props["plans_changed"]["type"] == "boolean"
    # Only the yes/no gate is required; the two strings are optional.
    assert tool["parameters"]["required"] == ["plans_changed"]


def test_outcome_prompt_renders_partner_and_transcript():
    text = render(
        "conversation_outcome",
        partner="Ayesha Khan",
        transcript="Maria Lopez: Library at 2?\nAyesha Khan: See you there.",
    )
    assert "Ayesha Khan" in text
    assert "Library at 2?" in text
    assert "See you there." in text


from text_adventure_games.planning import DailyPlan, Stop  # noqa: E402


class _OutcomeBrain:
    """A real-shaped brain: answers exactly one conversation_outcome call with a
    scripted dict, and records what tools/messages it was asked."""

    def __init__(self, result):
        self._result = result
        self.context: dict = {}
        self.calls: list[dict] = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append({"tool": tool["name"], "messages": messages})
        return self._result


class _RecordingPlanner:
    """Records the triggers maybe_revise_plan hands it; appends a Library stop on
    revise so the schedule genuinely changes (maybe_revise_plan commits only a
    changed tail)."""

    def __init__(self):
        self.triggers = []

    def generate(self, persona=None, memory=None, clock=None):
        return DailyPlan(stops=[Stop(place="Cafe", activity="reading", steps=5)])

    def revise(self, plan, trigger=None, memory=None, clock=None):
        self.triggers.append(trigger)
        stops = list(plan.stops) + [
            Stop(place="Library", activity="meeting up", steps=10)
        ]
        return DailyPlan(stops=stops, revision=plan.revision + 1)


class _FakeSchedule:
    """Minimal stand-in for the pacing client maybe_revise_plan reads (#581):
    only stop_index + replace_schedule are used on the revision path."""

    def __init__(self):
        self.stop_index = 0
        self.replaced = None

    def replace_schedule(self, entries):
        self.replaced = entries


def _agent_with(brain, planner):
    """A bare LLMAgent-shaped stub carrying just what the outcome path reads."""
    from text_adventure_games.memory import AgentMemory
    from text_adventure_games.things import Character

    char = Character("Maria Lopez", "Maria", "")
    agent = type("A", (), {})()
    agent.llm_client = brain
    agent.max_tokens = 256
    agent.memory = AgentMemory()
    agent.memory.owner = char.name
    agent.planner = planner
    agent.plan = planner.generate()
    agent.schedule = _FakeSchedule()
    # apply_conversation_outcome uses the persona system message for the call.
    agent._structured_system_message = lambda: "You are Maria Lopez."
    char.set_agent(agent)
    return char


def test_agreement_revises_plan_and_writes_relationship_note():
    from text_adventure_games.memory import MemoryKind

    brain = _OutcomeBrain(
        {
            "plans_changed": True,
            "commitment": "meet Ayesha at the Library at 2pm",
            "relationship_note": "Ayesha is a kindred spirit about robotics.",
        }
    )
    planner = _RecordingPlanner()
    maria = _agent_with(brain, planner)

    changed = cognition.apply_conversation_outcome(
        maria, "Ayesha Khan", "Maria Lopez: Library at 2?\nAyesha Khan: Yes.", step=7
    )

    assert changed is True
    # One outcome call, forced onto the outcome tool.
    assert [c["tool"] for c in brain.calls] == ["conversation_outcome"]
    # The revision fired with the CONVERSATION reason and the commitment as detail.
    assert planner.triggers[0].reason == cognition.CONVERSATION
    assert planner.triggers[0].detail == "meet Ayesha at the Library at 2pm"
    assert planner.triggers[0].step == 7
    # The schedule was re-committed with the appended Library stop.
    assert maria.agent.schedule.replaced[-1]["place"] == "Library"
    # The relationship note is a high-importance CHAT memory attributed to Ayesha.
    notes = [
        r
        for r in maria.agent.memory.records
        if r.kind == MemoryKind.CHAT and "robotics" in r.text
    ]
    assert len(notes) == 1
    assert notes[0].importance == cognition.RELATIONSHIP_NOTE_IMPORTANCE
    assert notes[0].actor == "Ayesha Khan"  # add_chat stores partner as actor


def test_small_talk_changes_nothing():
    brain = _OutcomeBrain({"plans_changed": False})
    planner = _RecordingPlanner()
    maria = _agent_with(brain, planner)

    changed = cognition.apply_conversation_outcome(
        maria,
        "Ayesha Khan",
        "Maria Lopez: Nice weather.\nAyesha Khan: Sure is.",
        step=3,
    )

    assert changed is False
    assert planner.triggers == []  # no revision offered
    assert maria.agent.memory.records == []  # no note written


def test_missing_commitment_falls_back_to_the_transcript_as_detail():
    brain = _OutcomeBrain({"plans_changed": True})  # no commitment string
    planner = _RecordingPlanner()
    maria = _agent_with(brain, planner)
    transcript = "Maria Lopez: See you at the game.\nAyesha Khan: I'll be there."

    cognition.apply_conversation_outcome(maria, "Ayesha Khan", transcript, step=1)

    assert planner.triggers[0].detail == transcript


def test_none_and_non_dict_results_are_safe_no_ops():
    for result in (None, "oops", 42):
        planner = _RecordingPlanner()
        maria = _agent_with(_OutcomeBrain(result), planner)
        assert cognition.apply_conversation_outcome(maria, "X", "t", step=0) is False
        assert planner.triggers == []
        assert maria.agent.memory.records == []


def test_client_without_call_tool_is_a_no_op():
    planner = _RecordingPlanner()
    maria = _agent_with(brain=object(), planner=planner)  # no call_tool attr
    assert cognition.apply_conversation_outcome(maria, "X", "t", step=0) is False
    assert planner.triggers == []
    assert maria.agent.memory.records == []


from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents, maybe_converse  # noqa: E402

_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Library", "description": "a library", "address": "T:Library:desks"},
    {"name": "Cafe", "description": "a cafe", "address": "T:Cafe:counter"},
]


def _persona(name):
    return {
        "name": name,
        "home": "Plaza",
        "persona": f"I am {name}.",
        "emoji": "\U0001f9d1",
        "start_tile": [0, 0],
        "destination": "Cafe",
        "activity": "reading",
        "schedule": [
            {"place": "Cafe", "activity": "reading", "emoji": None, "steps": 5}
        ],
    }


class _ConvoThenOutcomeBrain:
    """A real-shaped brain that both talks (converse -> one line, then done) and
    answers conversation_outcome with an agreement. Shared by both agents, like
    the classic single-brain live path."""

    def __init__(self):
        self.context: dict = {}
        self.outcome_calls = 0

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        if tool["name"] == "conversation_outcome":
            self.outcome_calls += 1
            return {
                "plans_changed": True,
                "commitment": "meet at the Library",
                "relationship_note": "A good friend from the cafe.",
            }
        # The engine's dialogue seam (Agent.converse) forces the "speak" tool.
        return {"utterance": "Library later?", "done": True}


def _colocated_settled_pair(brain):
    personas = [_persona("Maria Lopez"), _persona("Ayesha Khan")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    # Give each agent a planner that appends a shared Library stop on revise.
    for name in ("Maria Lopez", "Ayesha Khan"):
        agent = chars[name].agent
        agent.planner = _RecordingPlanner()
        agent.plan = agent.planner.generate()
    # Co-locate both in the Plaza and mark them settled (performing, not walking).
    plaza = game.locations["Plaza"]
    order = ["Maria Lopez", "Ayesha Khan"]
    for name in order:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        plaza.add_character(ch)
    state = {n: {"performing": True, "path": None, "chat": None} for n in order}
    frame = {n: {} for n in order}
    return game, chars, state, frame, order


def test_conversation_revises_both_plans_and_writes_both_notes():
    from text_adventure_games.memory import MemoryKind

    brain = _ConvoThenOutcomeBrain()
    game, chars, state, frame, order = _colocated_settled_pair(brain)

    happened = maybe_converse(game, chars, state, frame, 4, {}, order, clock=None)

    assert happened == 1
    # <= 2 outcome calls per conversation (one per participant).
    assert brain.outcome_calls == 2
    for name in order:
        agent = chars[name].agent
        # Both plans revised to a shared upcoming Library stop.
        assert agent.planner.triggers[0].reason == cognition.CONVERSATION
        assert any(s.place == "Library" for s in agent.plan.stops)
        # Both streams got the high-importance relationship note.
        notes = [
            r
            for r in agent.memory.records
            if r.kind == MemoryKind.CHAT
            and r.importance == cognition.RELATIONSHIP_NOTE_IMPORTANCE
        ]
        assert len(notes) == 1


def test_mock_brain_runs_no_outcome_calls():
    # The default mock never converses (no utterance) -> maybe_converse reports 0
    # and the outcome pass is never reached: the bake stays byte-identical.
    personas = [_persona("Maria Lopez"), _persona("Ayesha Khan")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=None)  # mock brain
    plaza = game.locations["Plaza"]
    order = ["Maria Lopez", "Ayesha Khan"]
    for name in order:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        plaza.add_character(ch)
    state = {n: {"performing": True, "path": None, "chat": None} for n in order}
    frame = {n: {} for n in order}

    happened = maybe_converse(game, chars, state, frame, 4, {}, order, clock=None)

    assert happened == 0
    for name in order:
        assert all(
            r.importance != cognition.RELATIONSHIP_NOTE_IMPORTANCE
            for r in chars[name].agent.memory.records
        )
