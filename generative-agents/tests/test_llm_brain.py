"""Offline tests for the real-LLM decision brain (issue #78, NEXT-STEPS Phase A).

``attach_agents`` can drive each persona's travel/perform decision through a real
``LlmClient`` instead of the deterministic mock. These tests cover that wiring
with a scripted fake client (no network): the brain and the schedule pacing driver
are separated, decisions route through the supplied brain, and -- crucially -- the
default (no client) path is unchanged, with the mock serving as both brain and
driver so the replay stays byte-identical.

Run from ``generative-agents``::

    uv run pytest tests/test_llm_brain.py -v
"""

from backend.build_world import PERSONAS, build_world
from backend.smallville_agents import (
    SmallvilleMockClient,
    attach_agents,
    observe_and_decide,
)


class _FixedBrain:
    """A fake decision ``LlmClient`` that always returns the same action.

    Matches the shape ``LLMAgent.decide`` expects from ``call_tool`` (a dict with
    ``reasoning``/``action``/``arguments``), so ``decide`` assembles the command
    ``"<action> <arguments>"`` -- letting us prove decisions route through it.
    """

    def __init__(self, action: str, arguments: str):
        self.action, self.arguments = action, arguments
        self.calls: list = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append(messages)
        return {"reasoning": "test", "action": self.action, "arguments": self.arguments}

    def chat(self, *args, **kwargs):
        return None

    def count_tokens(self, text):
        return len(text.split())


def test_default_brain_is_the_schedule_client():
    # No llm_client: the brain and the pacing driver are the SAME mock client, so
    # behavior is deterministic and the replay is byte-identical to before Phase A.
    _, chars = build_world()
    attach_agents(chars, PERSONAS)
    for spec in PERSONAS:
        agent = chars[spec["name"]].agent
        assert isinstance(agent.schedule, SmallvilleMockClient)
        assert agent.llm_client is agent.schedule


def test_real_brain_separates_decision_from_pacing():
    # With an llm_client, the brain is that client while a SmallvilleMockClient
    # still owns the schedule pacing (advance/steps/emoji), and the two are
    # distinct objects.
    brain = _FixedBrain("perform", "tending the cafe counter")
    _, chars = build_world()
    attach_agents(chars, PERSONAS, llm_client=brain)
    for spec in PERSONAS:
        agent = chars[spec["name"]].agent
        assert agent.llm_client is brain
        assert isinstance(agent.schedule, SmallvilleMockClient)
        assert agent.schedule is not agent.llm_client
        # Pacing still comes from the authored schedule.
        assert agent.schedule.schedule == spec["schedule"]


def test_decision_routes_through_the_real_brain():
    # The actual decision seam: observe_and_decide -> agent.decide -> the brain's
    # call_tool, assembling the command from the brain's action/arguments.
    brain = _FixedBrain("perform", "coding a mobile app")
    game, chars = build_world()
    attach_agents(chars, PERSONAS, llm_client=brain)
    char = chars[PERSONAS[0]["name"]]
    command = observe_and_decide(game, char, step=0)
    assert command == "perform coding a mobile app"
    assert brain.calls  # the brain was actually consulted
    assert char.agent.last_reasoning == "test"
