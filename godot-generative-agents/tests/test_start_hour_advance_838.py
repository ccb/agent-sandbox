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


def test_hold_survives_an_unrelated_dead_talk_settle():
    """The hold is per-stop, not per-settle: credit_stop=False from a dead-talk
    should not clear a hold that is still in force. #826, #838."""
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
    assert chars["Ada"].agent.schedule.stop_index == 0

    # Simulate a dead-talk settle: credit_stop becomes False, and a short idle
    # is performed.
    state["Ada"]["credit_stop"] = False
    state["Ada"]["perform_until"] = 260
    state["Ada"]["performing"] = True

    # 08:43: the idle completes. credit_stop is False, so waiting_for_anchor
    # recomputes to False in the old broken code. But the pointer hasn't moved
    # and the anchor hour hasn't arrived, so the hold is still valid. The flag
    # must stay True.
    step(game, chars, state, 260, **common)
    assert state["Ada"]["waiting_for_anchor"] is True
    assert chars["Ada"].agent.schedule.stop_index == 0

    # 10:00: the pointer finally moves, and the flag clears.
    step(game, chars, state, 720, **common)
    assert state["Ada"]["waiting_for_anchor"] is False
    assert chars["Ada"].agent.schedule.stop_index == 1


def test_hold_survives_schedule_replacement():
    """When a DEVIATED plan swaps the next stop, the hold flag remains truthful.
    The flag says 'current stop is finished', which is independent of what the
    next stop is. If the new next stop has no start_hour, the pointer will
    advance on the next completion; if it does, it stays held. Either way, the
    flag correctly represents the current state. #826, #838."""
    game, chars = build_world(None, [_persona()], _LOCATIONS)
    attach_agents(chars, [_persona()], llm_client=None)
    state = _state()
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }

    # 08:30: hold established with next stop anchored at 10:00.
    step(game, chars, state, 180, **common)
    assert state["Ada"]["waiting_for_anchor"] is True
    assert chars["Ada"].agent.schedule.stop_index == 0
    assert chars["Ada"].agent.schedule.next_stop["start_hour"] == 10

    # A plan revision swaps the tail with a new next stop that has NO start_hour.
    new_schedule = [
        {
            "place": "Cafe",
            "activity": "reading",
            "emoji": None,
            "steps": 5,
        },
        {
            "place": "Cafe",
            "activity": "lunch",  # new activity
            "emoji": None,
            "steps": 5,
            # NO start_hour
        },
    ]
    chars["Ada"].agent.schedule.replace_schedule(new_schedule)

    # The hold flag still reflects that the current stop is finished.
    assert state["Ada"]["waiting_for_anchor"] is True

    # But now the pointer can advance without waiting for an anchor hour, because
    # the new next stop has no start_hour constraint.
    step(game, chars, state, 720, **common)
    assert state["Ada"]["waiting_for_anchor"] is False
    assert chars["Ada"].agent.schedule.stop_index == 1


def test_step_advances_a_held_pointer_for_an_agent_that_walked_away():
    game, chars = build_world(None, [_persona()], _LOCATIONS)
    attach_agents(chars, [_persona()], llm_client=None)
    state = _state()
    # The batch-5 shape: the stop was credited, the pointer is held, and the
    # agent left instead of performing again -- so nothing completes to trigger
    # the retry inside the completed-activity block.
    state["Ada"].update(
        performing=False,
        perform_until=None,
        waiting_for_anchor=True,
        path=[(0, 1), (0, 2), (0, 3)],
    )
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }

    # 08:50 -- before the 10:00 anchor, the hold stands.
    step(game, chars, state, 300, **common)
    assert chars["Ada"].agent.schedule.stop_index == 0
    assert state["Ada"]["waiting_for_anchor"] is True

    # 10:00 -- the anchor arrives with no activity completing, and the plan
    # resumes anyway.
    step(game, chars, state, 720, **common)
    assert chars["Ada"].agent.schedule.stop_index == 1
    assert state["Ada"]["waiting_for_anchor"] is False
    assert state["Ada"]["stop_since"] == 720


def test_step_decides_with_the_advanced_pointer_when_the_agent_is_stationary():
    """The batch-5 shape exactly: the agent already arrived (empty path,
    not performing) and stood still while the anchor hour came and went. This
    pins *why* the retry sits before `due` is built, not just that it fires:
    a pointer that advances this tick must be visible to the decide that
    happens later in the very same tick, or the agent decides against the
    stop it already finished."""
    game, chars = build_world(None, [_persona()], _LOCATIONS)
    attach_agents(chars, [_persona()], llm_client=None)
    state = _state()
    state["Ada"].update(
        performing=False,
        perform_until=None,
        waiting_for_anchor=True,
        path=[],
    )
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }

    # 10:00 -- the anchor is due, and the agent never moved, so nothing but
    # the new block can advance the pointer this tick.
    step(game, chars, state, 720, **common)
    assert chars["Ada"].agent.schedule.stop_index == 1
    assert state["Ada"]["waiting_for_anchor"] is False
    assert state["Ada"]["stop_since"] == 720

    # The decide phase runs later in this SAME step() call, and reads the
    # schedule's CURRENT stop -- so if it acted on the second stop's activity
    # ("meeting") rather than the held one ("reading"), the pointer must
    # already have advanced by the time `due` was built and decide ran. This
    # is what makes the test about placement, not just about advancing: move
    # the new block below the `due` append and the pointer still advances,
    # but one tick too late for this decide to see it. `st["desc"]` is
    # unambiguous evidence -- it is stamped straight from the parsed
    # `perform <activity>` command's own activity property, so it names
    # whichever stop the decide actually chose.
    assert state["Ada"]["desc"] == "meeting @ None"
