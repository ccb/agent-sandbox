"""A plan revision must not silently strip the plan's clock anchors (issue #870).

In #760 batch 6 every LLM plan revision came back with almost no ``start_hour``
anchors (0-4 of ~13, against 8-12 on every initial plan), so one
conversation-triggered revision in the first hour erased the plan's time
skeleton -- and with no anchors left, ``ScheduleMockClient.advance()``'s hour
gate had nothing to hold against and the pointer free-ran on dwell latches to
the end of a 12-anchored plan by 13:26.

The cause is in the revise prompt itself: it rendered the current plan as bare
``place: activity`` pairs, so the model was never shown the pinned hours it was
supposed to keep. These tests pin that the prompt now carries each stop's pin
and the instruction to keep it.
"""

import datetime
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.planner import IMMEDIATE_URGENCY, LLMPlanner  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402
from text_adventure_games.planning import DailyPlan, Stop  # noqa: E402


class ReviseClient:
    """Serves a canned revised stop list and records what it was asked."""

    def __init__(self):
        self.sent = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.sent.append((tool["name"], messages[-1]["content"]))
        stop = {"place": "Houston Hall", "activity": "coffee", "minutes": 15}
        if tool["name"] == "immediate_revision":
            return {"next_stop": stop, "later_stops": []}
        return {"stops": [stop]}

    @property
    def last_message(self):
        return self.sent[-1][1]


def _plan():
    return DailyPlan(
        stops=[
            Stop(place="Van Pelt Library", activity="morning study", steps=360),
            Stop(
                place="Irvine Auditorium",
                activity="Tanaka's guest lecture",
                steps=360,
                start_hour=10,
            ),
            Stop(
                place="College Hall",
                activity="afternoon seminar",
                steps=360,
                start_hour=14,
            ),
        ]
    )


class _Trigger:
    reason = "conversation"
    detail = "meet Priya at Moelis"
    step = 120


def _revise(plan, trigger=None):
    client = ReviseClient()
    clock = SimClock(datetime.datetime(2026, 7, 29, 8, 0), sec_per_step=10)
    LLMPlanner(client, clock=clock, num_steps=4320).revise(plan, trigger or _Trigger())
    return client.last_message


def test_revise_prompt_renders_each_stops_pinned_hour():
    body = _revise(_plan())
    assert "Irvine Auditorium: Tanaka's guest lecture (pinned 10:00)" in body
    assert "College Hall: afternoon seminar (pinned 14:00)" in body
    # The unpinned stop stays a bare pair -- no invented "(pinned ...)".
    assert "Van Pelt Library: morning study;" in body


def test_revise_prompt_tells_the_model_to_keep_the_pins():
    assert "keep its start_hour" in _revise(_plan())


def test_revise_prompt_stays_quiet_with_no_pins():
    plan = DailyPlan(stops=[Stop(place="Houston Hall", activity="coffee")])
    body = _revise(plan)
    assert "(pinned" not in body


class _ImmediateTrigger(_Trigger):
    urgency = IMMEDIATE_URGENCY
    current_stop_index = 0


def test_immediate_revision_prompt_renders_the_pins_too():
    """#848's second revise path shows the same plan; same rule (#870)."""
    body = _revise(_plan(), trigger=_ImmediateTrigger())
    assert "Tanaka's guest lecture at Irvine Auditorium (pinned 10:00)" in body
    assert "afternoon seminar at College Hall (pinned 14:00)" in body
    assert "keep its start_hour" in body
