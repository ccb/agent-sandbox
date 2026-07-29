"""Keep schedule advancement behind an upcoming stop's clock anchor (#838).

Fully offline. Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \
        godot-generative-agents/tests/test_start_hour_advance_838.py -v
"""

import datetime

from backend.build_world import build_world
from backend.cognition import ScheduleMockClient, attach_agents, decide_context_block
from backend.run_simulation import step
from backend.sim_clock import SimClock


def _schedule():
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
            "start_hour": 10,
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


def test_step_holds_a_credited_pointer_then_advances_when_the_anchor_arrives():
    """A held pointer un-latches and settles again, and the *completed-activity*
    block advances it once the anchor hour arrives -- which must not be mistaken
    for end-of-day parking.

    Named for the completion path deliberately: at 180 the agent re-settles with
    ``perform_until=185``, so by 720 an activity has completed and the
    pre-existing block does the advancing. This test does NOT exercise the #826
    retry (deleting that block leaves it green); the retry is pinned by
    ``test_step_advances_a_held_pointer_for_an_agent_that_walked_away`` and
    ``test_step_decides_with_the_advanced_pointer_when_the_agent_is_stationary``,
    where nothing completes. An earlier name claimed the retry and was wrong."""
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
    """When a DEVIATED plan swaps the next stop, the hold flag remains truthful,
    and it is dropping the replacement's anchor -- not the mere passage of
    time -- that lets the pointer move. #826, #838.

    Steps at 300 (08:50), BEFORE the original 10:00 anchor: at that hour
    nothing but the missing ``start_hour`` on the replacement stop can let
    the pointer advance. (An earlier version of this test stepped at 720,
    10:00 -- by which time the pointer would advance whether or not the
    anchor survived the replacement, so it never actually exercised what its
    docstring claimed.) See
    ``test_hold_survives_schedule_replacement_with_a_new_anchor`` below for
    the control: the same replacement, same pre-anchor hour, but with the
    anchor carried over -- there the pointer must stay held.

    Mutation check: put ``"start_hour": 10`` back onto the replacement stop
    and this test goes RED (the pointer would still be held at 300)."""
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

    # 08:50 -- BEFORE the original 10:00 anchor. The pointer advances anyway,
    # because the replacement's next stop carries no start_hour constraint.
    step(game, chars, state, 300, **common)
    assert state["Ada"]["waiting_for_anchor"] is False
    assert chars["Ada"].agent.schedule.stop_index == 1


def test_hold_survives_schedule_replacement_with_a_new_anchor():
    """Control for the test above: the replacement stop keeps its OWN
    start_hour (still 10:00), so at the very same pre-anchor hour (300 ==
    08:50) the pointer must stay held. Together the two tests isolate the
    real variable -- whether the replacement carries an anchor -- rather
    than the hour `step()` happens to be called at. #826, #838."""
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

    new_schedule = [
        {
            "place": "Cafe",
            "activity": "reading",
            "emoji": None,
            "steps": 5,
        },
        {
            "place": "Cafe",
            "activity": "lunch",
            "emoji": None,
            "steps": 5,
            "start_hour": 10,  # anchor carried over, unlike the test above
        },
    ]
    chars["Ada"].agent.schedule.replace_schedule(new_schedule)
    assert state["Ada"]["waiting_for_anchor"] is True

    # 08:50 -- still before 10:00: the anchor survived, so the pointer stays held.
    step(game, chars, state, 300, **common)
    assert state["Ada"]["waiting_for_anchor"] is True
    assert chars["Ada"].agent.schedule.stop_index == 0

    # 10:00 -- now due.
    step(game, chars, state, 720, **common)
    assert state["Ada"]["waiting_for_anchor"] is False
    assert chars["Ada"].agent.schedule.stop_index == 1


# `test_step_advances_a_held_pointer_for_an_agent_that_walked_away` lived here.
# It asserted that a held pointer advances at its anchor hour while the agent is
# still WALKING, which #868 established is the wrong behavior: the pointer moved
# mid-leg, `stop_since` was stamped there, and the agent's next prompt reported an
# unreached stop as current with minutes already accrued against it (batch 6, a
# 52-minute abandoned leg). Its real guarantee -- that the retry fires with *no
# activity completing*, the batch-5 shape where an agent left instead of
# performing again -- is kept by
# `test_the_retry_leaves_a_walking_agents_pointer_alone_until_it_arrives` (which
# advances on the arrival tick, nothing having completed) and by
# `test_step_decides_with_the_advanced_pointer_when_the_agent_is_stationary`.


def test_the_retry_leaves_a_conversing_agents_pointer_alone():
    """The retry must not re-point the plan of an agent mid-exchange. #371 pins
    the schedule for the whole of a multi-tick conversation, and the anchor hour
    arriving is no reason to break that -- the agent would return from its
    meeting to find its current stop silently changed underneath it.

    Mutation check: drop ``and not st.get("conversing")`` from the retry and this
    goes RED. (It was the one guard in that condition nothing pinned.)"""
    game, chars = build_world(None, [_persona()], _LOCATIONS)
    attach_agents(chars, [_persona()], llm_client=None)
    state = _state()
    state["Ada"].update(
        performing=False,
        perform_until=None,
        waiting_for_anchor=True,
        conversing=True,
        path=[],
    )
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }

    # 10:00 -- the anchor is due and nothing is performing, so only `conversing`
    # stands between the retry and the pointer.
    step(game, chars, state, 720, **common)
    assert chars["Ada"].agent.schedule.stop_index == 0
    assert state["Ada"]["waiting_for_anchor"] is True

    # The exchange ends, and the very next tick resumes the plan.
    state["Ada"]["conversing"] = False
    step(game, chars, state, 721, **common)
    assert chars["Ada"].agent.schedule.stop_index == 1
    assert state["Ada"]["waiting_for_anchor"] is False


def test_a_hold_clears_when_a_revision_leaves_no_next_stop():
    """A hold with no next stop has no reason to exist, so it must not latch.

    Reachable through ``cognition.maybe_revise_plan``, which commits
    ``plan.stops[: after + 1] + proposed.stops[after + 1 :]`` -- a revision
    proposing fewer stops than that protected prefix leaves the pointer on the
    last stop. ``advance()`` then refuses forever on ``next_stop is None``, so a
    flag that only the pointer's movement could clear would stay True for the
    rest of the run. That is worse than a stuck flag: ``finished`` *replaces* the
    elapsed clause in decide_context.prompty, so every later prompt would call
    the stop finished and drop "This has been your current stop for N min." --
    deleting #826's own warning signal for the agent most likely to need it.

    Mutation check: remove the ``not has_next`` branch from the retry and this
    goes RED at the first assertion after the replacement."""
    game, chars = build_world(None, [_persona()], _LOCATIONS)
    attach_agents(chars, [_persona()], llm_client=None)
    state = _state()
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }

    # 08:30: hold established against the 10:00 anchor.
    step(game, chars, state, 180, **common)
    assert state["Ada"]["waiting_for_anchor"] is True

    # The revision's committed result: only the protected prefix survives, so the
    # held stop is now the last one.
    chars["Ada"].agent.schedule.replace_schedule([_schedule()[0]])
    assert chars["Ada"].agent.schedule.has_next is False

    # 08:50: no anchor can ever arrive, so the hold ends here rather than latching.
    step(game, chars, state, 300, **common)
    assert state["Ada"]["waiting_for_anchor"] is False
    assert chars["Ada"].agent.schedule.stop_index == 0

    # And the prompt is back to reporting elapsed time, not "already finished".
    block = decide_context_block(
        chars["Ada"].agent,
        300,
        common["clock"],
        stop_since=0,
        waiting=state["Ada"]["waiting_for_anchor"],
    )
    assert "This has been your current stop for" in block
    assert "already finished" not in block


def test_the_retry_leaves_a_walking_agents_pointer_alone_until_it_arrives():
    """#868: a held pointer must not advance mid-walk.

    The retry's gate is the same three-part gate `due` uses, `not st["path"]`
    included. Without it the pointer moved while the agent was walking and
    `stop_since` was stamped there, so the elapsed clock started on a stop the
    agent had not reached and was walking *away* from -- and the decide prompt
    then reported that stop as current, with minutes already accrued against it.

    `decide_context_block` defends the elapsed clock on an unreached stop
    deliberately ("an agent that wanders off-plan never arrives, so nothing
    re-anchors"), but that premise is "the agent chose not to go". It is false
    when the loop assigns the stop mid-transit. In #760 batch 6 Maya Chen was told
    she had been on a Houston Hall coffee break for 15 minutes in a building she
    had never entered, and turned around five steps from the door she was walking
    to -- a 52-minute abandoned leg, the run's only #826 criterion-1 breach.

    Mutation check: drop `not st["path"]` from the retry and this goes RED at the
    first assertion after 10:00."""
    game, chars = build_world(None, [_persona()], _LOCATIONS)
    attach_agents(chars, [_persona()], llm_client=None)
    state = _state()
    state["Ada"].update(
        performing=False,
        perform_until=None,
        waiting_for_anchor=True,
        path=[(0, 1), (0, 2), (0, 3)],  # mid-walk
    )
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }

    # 10:00 -- the anchor is due, but she is walking, so the pointer holds and
    # no elapsed clock starts on a stop she has not reached.
    step(game, chars, state, 720, **common)
    assert chars["Ada"].agent.schedule.stop_index == 0
    assert state["Ada"]["waiting_for_anchor"] is True
    assert state["Ada"]["stop_since"] == 0

    # She arrives (the path empties), and the very next tick resumes the plan.
    state["Ada"]["path"] = []
    step(game, chars, state, 721, **common)
    assert chars["Ada"].agent.schedule.stop_index == 1
    assert state["Ada"]["waiting_for_anchor"] is False
    assert state["Ada"]["stop_since"] == 721


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
