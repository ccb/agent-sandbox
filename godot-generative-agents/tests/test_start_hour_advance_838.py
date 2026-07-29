"""Keep schedule advancement behind an upcoming stop's clock anchor (#838).

Fully offline. Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
        godot-generative-agents/tests/test_start_hour_advance_838.py -v
"""

import datetime

from backend.build_world import build_world
from backend.cognition import ScheduleMockClient, attach_agents
from backend.run_simulation import step
from backend.sim_clock import SimClock


def _schedule(next_start_hour=10):
    return [
        {
            "place": "Cafe",
            "activity": "reading",
            "emoji": None,
            "steps": 5,
        },
        {
            "place": "Cafe",
            "activity": "meeting",
            "emoji": None,
            "steps": 5,
            "start_hour": next_start_hour,
        },
    ]


def test_advance_waits_for_the_next_stops_start_hour():
    schedule = ScheduleMockClient(_schedule())

    assert schedule.advance(current_hour=9) is False
    assert schedule.has_next is True
    assert schedule.stop_index == 0

    assert schedule.advance(current_hour=10) is True
    assert schedule.stop_index == 1
    assert schedule.has_next is False


def test_clockless_advance_preserves_the_existing_path():
    schedule = ScheduleMockClient(_schedule())

    assert schedule.advance() is True
    assert schedule.stop_index == 1


_LOCATIONS = [
    {"name": "Cafe", "description": "a cafe", "address": None, "hub": True},
]


def _persona():
    return {
        "name": "Ada",
        "home": "Cafe",
        "persona": "I am Ada.",
        "emoji": "📖",
        "start_tile": [0, 0],
        "destination": "Cafe",
        "activity": "reading",
        "schedule": _schedule(),
    }


def _state():
    return {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "📖",
            "desc": "reading",
            "performing": True,
            "perform_until": 1,
            "reasoning": "(reading)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
            "credit_stop": True,
            "conversing": False,
        }
    }


def test_step_retries_a_held_pointer_and_advances_when_due():
    game, chars = build_world(None, [_persona()], _LOCATIONS)
    attach_agents(chars, [_persona()], llm_client=None)
    state = _state()
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }

    # 08:30: the completed activity is credited, but the 10:00 stop is held.
    step(game, chars, state, 180, **common)
    assert chars["Ada"].agent.schedule.stop_index == 0
    assert state["Ada"]["performing"] is True
    assert state["Ada"]["stop_since"] == 0

    # The retry settled again. At 10:00 its timer has elapsed and the same
    # pointer can advance; this must not be mistaken for end-of-day parking.
    step(game, chars, state, 720, **common)
    assert chars["Ada"].agent.schedule.stop_index == 1
    assert state["Ada"]["stop_since"] == 720


def test_next_stop_is_the_stop_after_the_current_one():
    schedule = ScheduleMockClient(_schedule())

    assert schedule.next_stop == {
        "place": "Cafe",
        "activity": "meeting",
        "emoji": None,
        "steps": 5,
        "start_hour": 10,
    }

    assert schedule.advance(current_hour=10) is True
    assert schedule.next_stop is None


def test_step_records_the_hold_so_the_prompt_can_report_it():
    game, chars = build_world(None, [_persona()], _LOCATIONS)
    attach_agents(chars, [_persona()], llm_client=None)
    state = _state()
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }

    # 08:30: credited, but the 10:00 stop is held -- the flag says so.
    step(game, chars, state, 180, **common)
    assert state["Ada"]["waiting_for_anchor"] is True

    # 10:00: the pointer moves, so the hold is over and the flag clears.
    step(game, chars, state, 720, **common)
    assert chars["Ada"].agent.schedule.stop_index == 1
    assert state["Ada"]["waiting_for_anchor"] is False
