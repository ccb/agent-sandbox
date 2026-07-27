"""The planner's memory + grounding fixes (issue #795).

#795: under `--plan llm` no two agents were ever settled in the same room.
The cause was not planner blindness -- the agent's own commitments are
already seeded at t=0 by attach_agents and already retrieved -- but that
LLMPlanner.generate passed the retrieved block only to _day_outline, so
every place and duration was chosen two summarisation hops downstream.
"""

import datetime
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.planner import LLMPlanner, median_travel_minutes  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402


class RecordingClient:
    """Captures every (tool_name, user_message) the planner sends."""

    def __init__(self):
        self.sent = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.sent.append((tool["name"], messages[-1]["content"]))
        if tool["name"] == "day_outline":
            return {"blocks": [{"label": "midday", "summary": "lunch then study"}]}
        if tool["name"] == "hourly_plan":
            return {"hours": [{"start_hour": 12, "summary": "lunch at Houston Hall"}]}
        return {"stops": [{"place": "Houston Hall", "activity": "eating lunch"}]}

    def user_message_for(self, tool_name):
        return next(body for name, body in self.sent if name == tool_name)


class FakeMemory:
    """Minimal stand-in for AgentMemory.retrieve()."""

    def __init__(self, texts):
        self._records = [type("R", (), {"text": t})() for t in texts]

    def retrieve(self, query, turn, **kwargs):
        return self._records


COMMITMENT = (
    "Plan: go to Irvine Auditorium and setting up for an afternoon guest lecture."
)


def test_memory_reaches_every_planning_level():
    client = RecordingClient()
    planner = LLMPlanner(client)
    planner.generate(
        persona={"persona": "I am Professor Tanaka."}, memory=FakeMemory([COMMITMENT])
    )
    for level in ("day_outline", "hourly_plan", "minute_plan"):
        assert COMMITMENT in client.user_message_for(
            level
        ), f"{level} did not receive the retrieved memory block"


def test_no_memory_leaves_every_level_clean():
    """With no memory, no level gains a stray 'You remember:' header."""
    client = RecordingClient()
    LLMPlanner(client).generate(persona={"persona": "I am Diego."}, memory=None)
    for _name, body in client.sent:
        assert "You remember:" not in body


class MinutesClient(RecordingClient):
    """Emits a minute plan using the `minutes` field."""

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.sent.append((tool["name"], messages[-1]["content"]))
        if tool["name"] == "day_outline":
            return {"blocks": [{"label": "midday", "summary": "study"}]}
        if tool["name"] == "hourly_plan":
            return {"hours": [{"start_hour": 12, "summary": "study"}]}
        return {
            "stops": [
                {"place": "Houston Hall", "activity": "eating lunch", "minutes": 10}
            ]
        }


def _clock():
    return SimClock(datetime.datetime(2026, 7, 26, 8, 0), sec_per_step=10)


def test_minute_prompt_states_the_run_window():
    client = MinutesClient()
    LLMPlanner(client, clock=_clock(), num_steps=1200).generate(
        persona={"persona": "I am Diego."}
    )
    body = client.user_message_for("minute_plan")
    assert "08:00" in body and "11:20" in body


def test_minutes_convert_to_steps_against_the_clock():
    client = MinutesClient()
    plan = LLMPlanner(client, clock=_clock(), num_steps=1200).generate(
        persona={"persona": "I am Diego."}
    )
    # SEC_PER_STEP is 10, so 10 minutes == 600 seconds == 60 steps.
    assert [s.steps for s in plan.stops] == [60]


def test_without_a_clock_minutes_are_read_as_steps():
    """Tests that omit a clock keep today's behaviour exactly."""
    client = MinutesClient()
    plan = LLMPlanner(client).generate(persona={"persona": "I am Diego."})
    assert [s.steps for s in plan.stops] == [10]


def test_a_non_positive_duration_still_means_stay_put():
    class ZeroClient(MinutesClient):
        def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
            if tool["name"] == "minute_plan":
                self.sent.append((tool["name"], messages[-1]["content"]))
                return {
                    "stops": [{"place": "Houston Hall", "activity": "x", "minutes": 0}]
                }
            return super().call_tool(messages, tool, max_tokens, temperature)

    plan = LLMPlanner(ZeroClient(), clock=_clock(), num_steps=1200).generate(
        persona={"persona": "I am Diego."}
    )
    assert plan.stops[0].steps is None


def test_plan_system_prompt_is_not_smallville():
    from backend.prompt_templates import render

    assert "Smallville" not in render("plan_system")


class FakeMap:
    """Two addresses 60 tiles apart, one unknown."""

    def __init__(self):
        self.address_tiles = {
            "A:one:x": {(0, 0)},
            "A:two:x": {(60, 0)},
            "A:three:x": {(0, 30)},
        }

    def tiles_for(self, address):
        return self.address_tiles.get(address, set())


def test_median_travel_minutes_is_a_chebyshev_lower_bound():
    # Pairs: (0,0)-(60,0)=60, (0,0)-(0,30)=30, (60,0)-(0,30)=60. Median = 60
    # tiles == 60 steps == 600 in-game seconds == 10 minutes at sec_per_step 10.
    got = median_travel_minutes(
        FakeMap(), ["A:one:x", "A:two:x", "A:three:x"], _clock()
    )
    assert got == 10


def test_median_travel_minutes_is_none_without_a_map():
    assert median_travel_minutes(None, ["A:one:x"], _clock()) is None
    assert median_travel_minutes(FakeMap(), [], _clock()) is None


def test_minute_prompt_carries_the_travel_clause_when_known():
    client = MinutesClient()
    LLMPlanner(client, clock=_clock(), num_steps=1200, travel_minutes=23).generate(
        persona={"persona": "I am Diego."}
    )
    body = client.user_message_for("minute_plan")
    assert "23 minutes" in body
    assert "charged on top" in body


def test_minute_prompt_omits_the_travel_clause_when_unknown():
    """No fabricated constant: with no hint the clause is absent entirely."""
    client = MinutesClient()
    LLMPlanner(client, clock=_clock(), num_steps=1200).generate(
        persona={"persona": "I am Diego."}
    )
    assert "charged on top" not in client.user_message_for("minute_plan")
