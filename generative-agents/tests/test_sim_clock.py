"""Tests for the sim step <-> clock-time mapping (issue #83, Phase D §10).

Covers ``backend.sim_clock.SimClock``: the wall-clock instant at a step (and that
it matches the exporter's own formula, the "one conversion" guarantee), the
hour-of-day lookup, duration->steps conversion, the per-hour step budget, and the
hour spine used by day->hourly decomposition.

Fully offline, no maze assets, no LLM. Run from ``generative-agents``::

    uv run pytest tests/test_sim_clock.py -v
"""

import datetime

import pytest

from backend import exporter
from backend.sim_clock import SimClock

START = datetime.datetime(2023, 2, 13, 8, 0, 0)  # 8:00 AM, the sim default


def test_time_at_matches_exporter_formula():
    # SimClock and the exporter must compute the same instant per step, or a
    # plan's clock would disagree with the navbar/memory timestamps.
    clock = SimClock(START, sec_per_step=10)
    for step in (0, 1, 17, 360, 1079):
        expected = START + datetime.timedelta(seconds=step * exporter.SEC_PER_STEP)
        assert clock.time_at(step) == expected


def test_hour_at_crosses_the_hour_boundary():
    clock = SimClock(START, sec_per_step=10)  # 360 steps/hour
    assert clock.hour_at(0) == 8
    assert clock.hour_at(359) == 8  # last step of the 8am hour
    assert clock.hour_at(360) == 9  # first step of the 9am hour
    assert clock.hour_at(720) == 10


def test_steps_per_hour_default_and_custom():
    assert SimClock(START, sec_per_step=10).steps_per_hour == 360
    assert SimClock(START, sec_per_step=60).steps_per_hour == 60  # 1 min/step
    assert SimClock(START, sec_per_step=3600).steps_per_hour == 1


def test_steps_for_seconds_floors():
    clock = SimClock(START, sec_per_step=10)
    assert clock.steps_for_seconds(3600) == 360
    assert clock.steps_for_seconds(95) == 9  # 9 whole steps fit in 95s, never 10
    assert clock.steps_for_seconds(0) == 0


def test_steps_for_seconds_rejects_negative():
    with pytest.raises(ValueError):
        SimClock(START, sec_per_step=10).steps_for_seconds(-1)


def test_hour_starts_spine():
    clock = SimClock(START, sec_per_step=10)  # 360/hour
    # A 3-hour run (1080 steps) -> three hour blocks at 8, 9, 10am.
    assert clock.hour_starts(1080) == [(0, 8), (360, 9), (720, 10)]


def test_hour_starts_partial_and_empty():
    clock = SimClock(START, sec_per_step=10)
    # Shorter than an hour still yields the opening block.
    assert clock.hour_starts(100) == [(0, 8)]
    # A run that spills a little past an hour gets the second block too.
    assert clock.hour_starts(400) == [(0, 8), (360, 9)]
    # No steps -> no blocks.
    assert clock.hour_starts(0) == []


def test_non_midnight_start_and_wrap():
    # Start late so the run crosses into the next clock hour naming.
    clock = SimClock(datetime.datetime(2023, 2, 13, 23, 30, 0), sec_per_step=60)
    assert clock.hour_at(0) == 23
    assert clock.hour_at(30) == 0  # 30 min later -> midnight, hour wraps to 0
    assert clock.time_at(30) == datetime.datetime(2023, 2, 14, 0, 0, 0)


def test_rejects_nonpositive_sec_per_step():
    with pytest.raises(ValueError):
        SimClock(START, sec_per_step=0)
