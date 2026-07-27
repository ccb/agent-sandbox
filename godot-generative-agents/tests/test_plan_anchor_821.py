"""The planner keeps the clock anchor it gave itself (issue #821).

Stage 2 (`hourly_plan`) pins a commitment to an hour -- "10:00, Tanaka's guest
lecture at Irvine". Stage 3 (`minute_plan`) used to have nowhere to put that
hour, so the anchor survived only as prose and the arithmetic that has to land
the stop on it went unchecked. In #760 batch 4 that arithmetic was wrong by 56
minutes and the agent never reached the lecture at all.

The stop lists below are the real ones from that batch's cassettes, so the
check is pinned against model output that actually happened rather than
numbers invented to suit it.
"""

import datetime
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.planner import LLMPlanner  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402

# The live Penn median (median_travel_minutes over the real campus map).
TRAVEL = 24


def _clock():
    return SimClock(datetime.datetime(2026, 7, 26, 8, 0), sec_per_step=10)


class AnchorClient:
    """Serves a scripted minute plan, and a second one on the corrective re-ask."""

    def __init__(self, stops, retry_stops=None):
        self.stops = stops
        self.retry_stops = retry_stops
        self.sent = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.sent.append((tool["name"], messages[-1]["content"]))
        if tool["name"] == "day_outline":
            return {"blocks": [{"label": "morning", "summary": "the guest lecture"}]}
        if tool["name"] == "hourly_plan":
            return {
                "hours": [{"start_hour": 10, "summary": "Tanaka's lecture at Irvine"}]
            }
        if self.minute_calls > 1 and self.retry_stops is not None:
            return {"stops": self.retry_stops}
        return {"stops": self.stops}

    @property
    def minute_calls(self):
        return sum(1 for name, _ in self.sent if name == "minute_plan")

    @property
    def last_minute_message(self):
        return [body for name, body in self.sent if name == "minute_plan"][-1]


def _plan(client, **kwargs):
    """Run generate() with the live window: 08:00-11:20, hours 8/9/10/11."""
    kwargs.setdefault("clock", _clock())
    kwargs.setdefault("num_steps", 1200)
    kwargs.setdefault("travel_minutes", TRAVEL)
    return LLMPlanner(client, **kwargs).generate(persona={"persona": "I am Diego."})


# Diego's real Sonnet 5 plan: 40 + 40 + 16 minutes of stops, four different
# places, and a lecture he pinned to 10:00. 480 + 96 dwell + 3x24 travel = 10:48.
DIEGO_LATE = [
    {"place": "Meyerson Hall", "activity": "studio model", "minutes": 40},
    {"place": "Van Pelt — Kamin Gallery", "activity": "the exhibits", "minutes": 40},
    {
        "place": "Van Pelt — Digital Scholarship Exchange",
        "activity": "wave propagation reading",
        "minutes": 16,
    },
    {
        "place": "Irvine Auditorium",
        "activity": "Attending Professor Tanaka's guest lecture",
        "start_hour": 10,
    },
]

DIEGO_FIXED = [
    {"place": "Meyerson Hall", "activity": "studio model", "minutes": 45},
    {
        "place": "Irvine Auditorium",
        "activity": "Attending Professor Tanaka's guest lecture",
        "start_hour": 10,
    },
]


def test_a_pinned_stop_the_plan_cannot_reach_is_sent_back():
    client = AnchorClient(DIEGO_LATE, retry_stops=DIEGO_FIXED)
    plan = _plan(client)

    assert client.minute_calls == 2, "the unreachable 10:00 stop was not re-asked"
    body = client.last_minute_message
    assert "pinned to 10:00" in body
    assert "10:48" in body, "the correction must name the projected arrival"
    assert "48 minutes of stop time" in body, "and the budget actually available"
    # The correction is appended, so the original instructions still stand (the
    # back-to-back sentence #795 added is pinned verbatim by its own test).
    assert "Turn it into concrete stops." in body
    # The re-ask's answer is what gets planned.
    assert [s.place for s in plan.stops] == ["Meyerson Hall", "Irvine Auditorium"]


def test_the_anchor_survives_onto_the_stop():
    """The whole point: start_hour reaches Stop instead of dying in the prompt."""
    plan = _plan(AnchorClient(DIEGO_LATE, retry_stops=DIEGO_FIXED))
    pinned = plan.stops[-1]
    assert pinned.start_hour == 10
    assert pinned.to_schedule_entry()["start_hour"] == 10


# Tanaka's real plan: three back-to-back stops in ONE room, hosting at 10:00.
# 480 + 180 dwell + NO walks = lands at 10:00 exactly.
TANAKA_SAME_PLACE = [
    {"place": "Irvine Auditorium", "activity": "check the AV", "minutes": 60},
    {"place": "Irvine Auditorium", "activity": "set up the podium", "minutes": 60},
    {
        "place": "Irvine Auditorium",
        "activity": "Host the guest lecture",
        "minutes": 60,
        "start_hour": 10,
    },
    {"place": "Williams Hall — Classroom A", "activity": "office hours"},
]


def test_consecutive_stops_in_one_room_are_charged_no_walk():
    """Counting a travel leg per stop *index* would bill 48 minutes of walking
    between three stops in the same auditorium, and send back a plan that lands
    on the hour exactly -- a paid re-ask on a false premise, for the one agent
    the whole scenario hangs off."""
    client = AnchorClient(TANAKA_SAME_PLACE)
    _plan(client)
    assert client.minute_calls == 1


# Diego's real Haiku plan from the A/B run: 60 minutes then the lecture.
# 480 + 60 + 24 = 09:24, i.e. 36 minutes EARLY for the 10:00 anchor.
DIEGO_EARLY = [
    {"place": "Meyerson Hall", "activity": "studio model", "minutes": 60},
    {
        "place": "Irvine Auditorium",
        "activity": "Attending the guest lecture",
        "minutes": 20,
        "start_hour": 10,
    },
]


def test_an_early_projection_is_never_re_asked():
    """Travel is a deliberate lower bound, so 'optimistically early' says
    nothing -- the real walk is longer. Only lateness is evidence. A symmetric
    abs() check would spend a call making this fine plan worse."""
    client = AnchorClient(DIEGO_EARLY)
    _plan(client)
    assert client.minute_calls == 1


def test_stay_put_before_an_anchor_reports_that_it_never_happens():
    """`minutes` omitted means "stay for the rest of the day", so an anchored
    stop after one is not late, it is unreachable -- and the naive arithmetic
    would raise TypeError straight out of generate(), which attach_agents calls
    unguarded."""
    client = AnchorClient(
        [
            {"place": "Meyerson Hall", "activity": "studio model"},  # no minutes
            {
                "place": "Irvine Auditorium",
                "activity": "Attending the guest lecture",
                "start_hour": 10,
            },
        ]
    )
    _plan(client)  # must not raise
    assert client.minute_calls == 2
    body = client.last_minute_message
    assert "never happens" in body
    assert "rest of the day" in body


def test_an_hour_outside_the_run_window_is_left_alone():
    """23:00 is not in a 08:00-11:20 run. A re-ask cannot repair that, so the
    check declines to act rather than demanding the impossible."""
    client = AnchorClient(
        [
            {"place": "Meyerson Hall", "activity": "studio model", "minutes": 200},
            {"place": "Irvine Auditorium", "activity": "a lecture", "start_hour": 23},
        ]
    )
    _plan(client)
    assert client.minute_calls == 1


def test_without_a_clock_nothing_is_checked():
    """No clock means `minutes` are read as steps, so there is no wall clock to
    be late against -- the pre-#821 behaviour, unchanged."""
    client = AnchorClient(DIEGO_LATE)
    LLMPlanner(client).generate(persona={"persona": "I am Diego."})
    assert client.minute_calls == 1


def test_revise_is_not_subject_to_the_check():
    """revise() shares the parsing but not the premise: its tail starts wherever
    the agent has actually got to, not at the window's opening time, so the
    from-step-0 arithmetic would be wrong."""
    client = AnchorClient(DIEGO_LATE)
    planner = LLMPlanner(client, clock=_clock(), num_steps=1200, travel_minutes=TRAVEL)
    plan = planner.generate(persona={"persona": "I am Diego."})
    before = client.minute_calls
    planner.revise(plan, trigger=None)
    assert client.minute_calls == before + 1, "revise must not spend a re-ask"
