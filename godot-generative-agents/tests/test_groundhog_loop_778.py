"""Break the groundhog-day conversation loop (issue #778).

Two co-located agents who keep choosing `talk_to` each other re-ran
substantially the same conversation forever. Two mechanisms, fixed here:

**A.** The #582 outcome pass produced a concrete `commitment` ("leaving right
now to grab food") on 16 of 18 calls in the live run `run-20260724-194343-78858a`
and threw every one away: the only consumer was `maybe_revise_plan`, and the
default `plan_mode: "schedule"` wires `MockPlanner`, whose `revise()` is a no-op.
The commitment now becomes a durable PLAN memory in the speaker's own stream.

**C.** `schedule.advance()` only fires for an ON-PLAN settle, and a `talk_to`
routes through `_settle_after_dead_talk`, which sets `on_plan = False` (#689).
So no conversation ever advanced a stop -- not even when the conversation WAS
the scheduled activity. A real conversation held at the scheduled place now
credits that stop.

Fully offline (fake brains + fake planners). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_groundhog_loop_778.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_conversation_consequences_582.py: the Penn sim
# modules run as scripts (no package), so tests import them off the sim
# directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from text_adventure_games.memory import AgentMemory, MemoryKind  # noqa: E402
from text_adventure_games.planning import DailyPlan, Stop  # noqa: E402
from text_adventure_games.things import Character  # noqa: E402

from backend import cognition  # noqa: E402


class _OutcomeBrain:
    """A real-shaped brain: answers exactly one conversation_outcome call with a
    scripted dict, and records what tools it was asked for."""

    def __init__(self, result):
        self._result = result
        self.context: dict = {}
        self.calls: list[dict] = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append({"tool": tool["name"], "messages": messages})
        return self._result


class _NoOpPlanner:
    """The planner shape the DEFAULT live run actually has: MockPlanner, whose
    revise() returns the plan unchanged. This is the configuration that dropped
    all 16 of the live run's commitments, so it is the one the regression pins.
    """

    def __init__(self):
        self.triggers = []

    def generate(self, persona=None, memory=None, clock=None):
        return DailyPlan(stops=[Stop(place="Cafe", activity="reading", steps=5)])

    def revise(self, plan, trigger=None, memory=None, clock=None):
        self.triggers.append(trigger)
        return plan  # unchanged -> maybe_revise_plan commits nothing


class _FakeSchedule:
    """Minimal stand-in for the pacing client maybe_revise_plan reads (#581)."""

    def __init__(self):
        self.stop_index = 0
        self.replaced = None

    def replace_schedule(self, entries):
        self.replaced = entries


def _agent_with(brain, planner):
    """A bare LLMAgent-shaped stub carrying just what the outcome path reads."""
    char = Character("Maria Lopez", "Maria", "")
    agent = type("A", (), {})()
    agent.llm_client = brain
    agent.max_tokens = 256
    agent.memory = AgentMemory()
    agent.memory.owner = char.name
    agent.planner = planner
    agent.plan = planner.generate()
    agent.schedule = _FakeSchedule()
    agent._structured_system_message = lambda: "You are Maria Lopez."
    char.set_agent(agent)
    return char


def _plans(char):
    return [r for r in char.agent.memory.records if r.kind == MemoryKind.PLAN]


def test_commitment_becomes_a_locked_plan_memory():
    brain = _OutcomeBrain(
        {
            "plans_changed": True,
            "commitment": "meet Ayesha at the Library at 2pm",
            "relationship_note": "Ayesha is a kindred spirit about robotics.",
        }
    )
    maria = _agent_with(brain, _NoOpPlanner())

    cognition.apply_conversation_outcome(
        maria, "Ayesha Khan", "Maria Lopez: Library at 2?\nAyesha Khan: Yes.", step=7
    )

    plans = _plans(maria)
    assert len(plans) == 1
    # First-person, naming the partner and carrying the commitment verbatim.
    assert plans[0].text == (
        "I agreed with Ayesha Khan: meet Ayesha at the Library at 2pm"
    )
    assert plans[0].created_turn == 7
    # Importance is load-bearing: the SAME conversation mints an 8.0 relationship
    # note and 7-8 scored talk observations, so add_plan's 5.0 default would be
    # crowded straight out of the retrieved block by its own partner-chatter.
    assert plans[0].importance == cognition.RELATIONSHIP_NOTE_IMPORTANCE
    # Locked, for the same reason the note is: a deliberate high signal that the
    # #583 scorer must not re-guess.
    assert plans[0].metadata[cognition._IMPORTANCE_LOCKED] is True


def test_commitment_lands_even_though_the_planner_is_a_no_op():
    """The live-run regression. plan_mode "schedule" -> MockPlanner.revise is a
    no-op, so apply_conversation_outcome returns False and NOTHING used to
    survive the call. The intention must persist regardless."""
    brain = _OutcomeBrain(
        {
            "plans_changed": True,
            "commitment": "grab food with Ayesha, leaving right now",
        }
    )
    planner = _NoOpPlanner()
    maria = _agent_with(brain, planner)

    changed = cognition.apply_conversation_outcome(
        maria, "Ayesha Khan", "Maria Lopez: Food?\nAyesha Khan: Now!", step=263
    )

    assert changed is False  # the planner proposed no change -- as in the live run
    assert planner.triggers[0].reason == cognition.CONVERSATION  # still offered
    assert len(_plans(maria)) == 1  # ...and the intention survived anyway


def test_no_commitment_writes_no_plan_memory():
    """plans_changed with no commitment string: the transcript remains the
    revision DETAIL (existing #582 behaviour), but a whole transcript must never
    be stored as a plan -- that is noise, not an intention."""
    brain = _OutcomeBrain({"plans_changed": True})  # no commitment key
    planner = _NoOpPlanner()
    maria = _agent_with(brain, planner)
    transcript = "Maria Lopez: See you at the game.\nAyesha Khan: I'll be there."

    cognition.apply_conversation_outcome(maria, "Ayesha Khan", transcript, step=1)

    assert planner.triggers[0].detail == transcript  # unchanged from #582
    assert _plans(maria) == []


def test_blank_commitment_writes_no_plan_memory():
    brain = _OutcomeBrain({"plans_changed": True, "commitment": "   "})
    maria = _agent_with(brain, _NoOpPlanner())

    cognition.apply_conversation_outcome(maria, "Ayesha Khan", "t", step=1)

    assert _plans(maria) == []


def test_plans_unchanged_writes_no_plan_memory():
    """A commitment string present but plans_changed false: the model did not
    commit to anything, so nothing is written."""
    brain = _OutcomeBrain(
        {"plans_changed": False, "commitment": "maybe coffee sometime"}
    )
    maria = _agent_with(brain, _NoOpPlanner())

    cognition.apply_conversation_outcome(maria, "Ayesha Khan", "t", step=1)

    assert _plans(maria) == []
