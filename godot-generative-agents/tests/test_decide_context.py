"""The decide-prompt context block (issue #580).

Pins the always-on context slice a live brain gets on every decision --
sim time, the plan's current stop, elapsed time on it -- and the plumbing
that renders it only when the step loop threads a SimClock, so the
deterministic mock bake stays byte-identical.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_decide_context.py -v
"""

import datetime
import sys
from pathlib import Path

# Same import shim as test_cognition_wiring.py: the Penn sim modules are run
# as scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.prompt_templates import render  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    at_scheduled_stop,
    attach_agents,
    decide_context_block,
    memories_for_frame,
    observe_and_decide,
)
from backend.sim_clock import SimClock  # noqa: E402
from text_adventure_games.llm_client import (  # noqa: E402
    MockLlmClient,
    ToolCallResult,
)

# 2023-02-13 is a Monday -- the same instant as penn_world.SIM_START.
START = datetime.datetime(2023, 2, 13, 8, 0, 0)

# ------------------------------------------------------------ a tiny world
#
# The same three-location, one-persona world test_cognition_wiring.py drives.

LOCATIONS = [
    {
        "name": "The Green",
        "description": "the central lawn",
        "address": None,
        "hub": True,
    },
    {"name": "Cafe", "description": "a coffee shop", "address": "T:Cafe:counter"},
    {"name": "Library", "description": "a small library", "address": "T:Library:desks"},
]


def _personas():
    # Fresh dicts per test: attach_agents and the step loop mutate the spec.
    return [
        {
            "name": "Ada",
            "home": "The Green",
            "persona": "I am Ada, a curious first-year.",
            "emoji": "\U0001f4d6",
            "start_tile": [0, 0],
            "destination": "Cafe",
            "activity": "reading a novel",
            "schedule": [
                {
                    "place": "Cafe",
                    "activity": "reading a novel",
                    "emoji": "\U0001f4d6",
                    "steps": None,
                }
            ],
        }
    ]


def _world(llm_client=None):
    """(game, Ada) with agents attached -- mock brain, or the supplied one."""
    personas = _personas()
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=llm_client)
    return game, chars["Ada"]


TRAVEL = ToolCallResult(
    text=None,
    tool_calls=[
        {
            "id": "call_1",
            "name": "travel",
            "arguments": {"reasoning": "coffee first", "destination": "Cafe"},
        }
    ],
)

# ---------------------------------------------------------- the helper unit


def test_block_requires_a_clock_and_a_schedule():
    _game, ada = _world()
    assert decide_context_block(ada.agent, 5, None, 0) == ""

    class Bare:  # an agent with no schedule attribute
        pass

    assert decide_context_block(Bare(), 5, SimClock(START), 0) == ""


def test_block_reads_the_clock_and_current_stop():
    _game, ada = _world()  # schedule steps=None -> no planned clause
    # Step 12 at 10 s/step = 08:02; stop_since=6 -> 6 steps = 1 min elapsed.
    assert decide_context_block(ada.agent, 12, SimClock(START), 6) == (
        "Right now it is Monday 08:02 AM.\n"
        "Your plan's current stop: reading a novel at Cafe. "
        "This has been your current stop for 1 min."
    )


# ------------------------------------------------- the decide-prompt wiring


def test_decide_prompt_carries_the_block_after_the_environment_text():
    brain = MockLlmClient(tool_calls_responses=[TRAVEL])
    game, ada = _world(llm_client=brain)

    command = observe_and_decide(game, ada, 12, clock=SimClock(START), stop_since=6)

    assert command == "travel to Cafe"
    user = brain.tool_calls_log[0]["messages"][-1]["content"]
    assert (
        "Right now it is Monday 08:02 AM.\n"
        "Your plan's current stop: reading a novel at Cafe. "
        "This has been your current stop for 1 min."
    ) in user
    # The first non-empty line is still the location: the deterministic mock's
    # first-line read (ScheduleMockClient._current_location) is untouched.
    first = next(line for line in user.splitlines() if line.strip())
    assert "Right now" not in first


def test_no_clock_means_no_block():
    brain = MockLlmClient(tool_calls_responses=[TRAVEL])
    game, ada = _world(llm_client=brain)

    observe_and_decide(game, ada, 12)  # no clock -- the pre-#580 call shape

    user = brain.tool_calls_log[0]["messages"][-1]["content"]
    assert "Right now it is" not in user


def test_mock_decision_and_retrieval_unchanged_by_the_block():
    # The two frame-visible outputs of a decide -- the command and the
    # retrieved memories -- must be identical with and without a clock:
    # retrieval must keep querying the PLAIN environment text (frames embed
    # the retrieved list, so a shifted query would change the mock bake).
    game1, ada1 = _world()
    plain = observe_and_decide(game1, ada1, 0)
    game2, ada2 = _world()
    clocked = observe_and_decide(game2, ada2, 0, clock=SimClock(START))

    assert plain == clocked == "travel to Cafe"
    assert memories_for_frame(ada1.agent.last_retrieved) == memories_for_frame(
        ada2.agent.last_retrieved
    )


# ------------------------------------------------------- the pinned wording


def test_render_pins_the_full_block():
    assert render(
        "decide_context",
        time="Monday 12:05 PM",
        place="Houston Hall",
        activity="eating lunch",
        minutes=40,
        elapsed=15,
    ) == (
        "Right now it is Monday 12:05 PM.\n"
        "Your plan's current stop: eating lunch at Houston Hall (planned ~40 min). "
        "This has been your current stop for 15 min."
    )


def test_render_drops_the_optional_clauses():
    # minutes=None: the schedule says stay indefinitely -- no planned clause.
    # elapsed=0: the stop just began -- no elapsed sentence.
    assert render(
        "decide_context",
        time="Monday 08:00 AM",
        place="The Quad",
        activity="stretching",
        minutes=None,
        elapsed=0,
    ) == (
        "Right now it is Monday 08:00 AM.\n"
        "Your plan's current stop: stretching at The Quad."
    )


# ------------------------------------------------------- step-loop plumbing

from backend.run_simulation import step  # noqa: E402


def _perform_call(activity):
    return ToolCallResult(
        text=None,
        tool_calls=[
            {
                "id": "call_1",
                "name": "perform",
                "arguments": {"reasoning": "on it", "activity": activity},
            }
        ],
    )


def test_step_restamps_stop_since_when_the_schedule_advances():
    # Two stops at Ada's start location (no travel, so no WorldMap needed):
    # a 1-step stretch, then settle. Step 0 decides stop 1; the pre-pass of
    # step 1 expires it, advances the schedule, and restamps stop_since --
    # so the second decide's prompt shows the NEW stop with no elapsed clause.
    personas = _personas()
    personas[0]["destination"] = "The Green"
    personas[0]["activity"] = "stretching"
    personas[0]["schedule"] = [
        {
            "place": "The Green",
            "activity": "stretching",
            "emoji": "\U0001f4d6",
            "steps": 1,
        },
        {
            "place": "The Green",
            "activity": "people-watching",
            "emoji": "\U0001f4d6",
            "steps": None,
        },
    ]
    brain = MockLlmClient(
        tool_calls_responses=[
            _perform_call("stretching"),
            _perform_call("people-watching"),
        ]
    )
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    state = {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f4d6",
            "desc": "waking up",
            "performing": False,
            "perform_until": None,
            "reasoning": "(waking up)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }
    clock = SimClock(START)
    common = dict(
        order=["Ada"], world_map=None, emoji={"Ada": "\U0001f4d6"}, clock=clock
    )

    step(game, chars, state, 0, **common)
    assert state["Ada"]["performing"] is True
    assert state["Ada"]["stop_since"] == 0

    step(game, chars, state, 1, **common)
    assert state["Ada"]["stop_since"] == 1
    user = brain.tool_calls_log[1]["messages"][-1]["content"]
    assert "people-watching at The Green" in user
    assert "This has been your current stop" not in user  # elapsed 0: just advanced


def test_arrival_restamps_stop_since_so_elapsed_excludes_the_walk():
    # A stop that needs a walk: stop_since re-anchors when the last path tile
    # is consumed, so elapsed counts time AT the stop -- commensurate with the
    # planned minutes, which budget the activity, not the walk there.
    class _TwoTileWalk:
        """WorldMap stand-in: every walk is the same two-tile path."""

        def walk_path(self, start, address, furniture=None):
            return [(0, 1), (0, 2)]

    brain = MockLlmClient(
        tool_calls_responses=[TRAVEL, _perform_call("reading a novel")]
    )
    personas = _personas()  # default: one Cafe stop, reached by travel
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    state = {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f4d6",
            "desc": "waking up",
            "performing": False,
            "perform_until": None,
            "reasoning": "(waking up)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }
    common = dict(
        order=["Ada"],
        world_map=_TwoTileWalk(),
        emoji={"Ada": "\U0001f4d6"},
        clock=SimClock(START),
    )

    step(game, chars, state, 0, **common)  # decides travel, walks 1st tile
    assert state["Ada"]["path"] == [(0, 2)]
    assert state["Ada"]["stop_since"] == 0  # mid-walk: no re-anchor yet

    step(game, chars, state, 1, **common)  # last tile popped: arrival
    assert state["Ada"]["stop_since"] == 1

    step(game, chars, state, 2, **common)  # arrival decide: perform
    user = brain.tool_calls_log[1]["messages"][-1]["content"]
    assert "reading a novel at Cafe" in user
    assert "This has been your current stop" not in user  # walk time excluded


def test_stop_since_survives_an_offplan_arrival():
    # #826: arriving somewhere that is NOT the current stop's place must not
    # re-anchor stop_since. It used to, on every arrival -- so `elapsed` was 0
    # on every decide that followed a walk and the "this has been your current
    # stop for N min" clause never rendered for a traveling agent. An agent
    # alternating between two errands could then never see that its 10-minute
    # coffee run had been running for two hours (the reported symptom).
    class _TwoTileWalk:
        def walk_path(self, start, address, furniture=None):
            return [(0, 1), (0, 2)]

    # Her stop is the Cafe; she travels to the Library instead -- a deviation.
    library = ToolCallResult(
        text=None,
        tool_calls=[
            {
                "id": "call_1",
                "name": "travel",
                "arguments": {"reasoning": "browsing first", "destination": "Library"},
            }
        ],
    )
    brain = MockLlmClient(
        tool_calls_responses=[library, _perform_call("reading a novel")]
    )
    personas = _personas()  # destination "Cafe", one Cafe stop
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    state = {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f4d6",
            "desc": "waking up",
            "performing": False,
            "perform_until": None,
            "reasoning": "(waking up)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }
    common = dict(
        order=["Ada"],
        world_map=_TwoTileWalk(),
        emoji={"Ada": "\U0001f4d6"},
        clock=SimClock(START),
    )

    step(game, chars, state, 0, **common)  # decides travel to Library, 1st tile
    step(game, chars, state, 1, **common)  # last tile popped: off-plan arrival
    assert chars["Ada"].location.name == "Library"
    assert state["Ada"]["stop_since"] == 0  # NOT re-anchored to step 1

    # The payoff: because the clock kept running, a decide later in the day now
    # renders the elapsed clause instead of dropping it. 400 steps at 10 s/step
    # is 66 min, measured from the preserved stop_since of 0.
    assert "This has been your current stop for 66 min." in decide_context_block(
        chars["Ada"].agent, 400, SimClock(START), state["Ada"]["stop_since"]
    )


def test_stop_since_survives_a_completed_offplan_activity():
    # #826 review: surviving the off-plan *arrival* is not enough. A settle that
    # expires without moving the pointer used to re-anchor stop_since anyway, so
    # a neglected stop's clock was reset while it stood still. The pointer has not
    # moved in this branch, so its clock must not restart.
    #
    # #831 narrowed who reaches it: a completed off-plan activity now credits its
    # stop and advances, so the only settle left that credits nothing is
    # `settle_after_dead_talk` (#689) -- a dropped talk, which is the state this
    # test builds. The invariant under test is unchanged: no advance, no restart.
    personas = _personas()
    brain = MockLlmClient(tool_calls_responses=[_perform_call("reading a novel")])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    state = {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f4d6",
            "desc": "grabbing coffee",
            # Settled by a dropped talk (#689), expiring at 399: credits nothing.
            "performing": True,
            "credit_stop": False,
            "perform_until": 399,
            "reasoning": "(deviating)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }
    common = dict(
        order=["Ada"],
        world_map=None,
        emoji={"Ada": "\U0001f4d6"},
        clock=SimClock(START),
    )

    step(game, chars, state, 400, **common)  # the pre-pass expires the deviation

    assert state["Ada"]["performing"] is True  # re-decided into a new perform
    assert state["Ada"]["stop_since"] == 0  # NOT re-anchored to step 400
    # The payoff, in the prompt the agent actually got: 400 steps at 10 s/step
    # is 66 min of neglect, and it now says so.
    user = brain.tool_calls_log[0]["messages"][-1]["content"]
    assert "This has been your current stop for 66 min." in user


# ------------------------------------------- the shared at-scheduled-stop test
#
# @0frankie on PR #830: at_scheduled_stop is now a shared predicate five call
# sites depend on, so pin its contract directly rather than only through the
# behaviours that consume it.


def _place(game, char, dest):
    if char.location is not None:
        char.location.remove_character(char)
    game.locations[dest].add_character(char)


def test_at_scheduled_stop_is_true_only_standing_at_the_stops_own_place():
    game, ada = _world()  # her one stop is the Cafe
    _place(game, ada, "Cafe")
    assert at_scheduled_stop(ada) is True

    _place(game, ada, "Library")
    assert at_scheduled_stop(ada) is False


def test_at_scheduled_stop_is_false_without_a_place_or_a_location():
    game, ada = _world()
    _place(game, ada, "Cafe")

    # An unplaced stop is not somewhere you can be standing, even though the
    # agent is somewhere. `bool(place)` covers both None and "".
    ada.agent.schedule.schedule[0]["place"] = None
    assert at_scheduled_stop(ada) is False
    ada.agent.schedule.schedule[0]["place"] = "Cafe"

    # Nowhere at all: char.location is None until the world places a character,
    # and `_resting_pron`'s callers reach this predicate before that happens.
    ada.location.remove_character(ada)
    assert ada.location is None
    assert at_scheduled_stop(ada) is False


def test_at_scheduled_stop_is_false_for_an_agent_with_no_schedule():
    game, ada = _world()
    _place(game, ada, "Cafe")
    ada.agent.schedule = None
    assert at_scheduled_stop(ada) is False


def test_an_offplan_travel_drops_the_furniture_hint():
    # The consequence @0frankie flagged, pinned at the call site rather than
    # only on the predicate. The furniture bias is dropped off-plan because the
    # scheduled stop's furniture is for the wrong place -- and that call site
    # reads `char.location` via at_scheduled_stop, relying on the engine having
    # already moved the character to its destination at parse time. A predicate
    # unit test cannot see that invariant break; this can. The mock bake only
    # ever exercises the on-plan half (it never deviates), so without this the
    # off-plan half had no coverage at all.
    class _RecordingWalk:
        def __init__(self):
            self.calls = []

        def walk_path(self, start, address, furniture=None):
            self.calls.append((address, furniture))
            return [(0, 1)]

    def _travel_to(place):
        return ToolCallResult(
            text=None,
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "travel",
                    "arguments": {"reasoning": "going", "destination": place},
                }
            ],
        )

    personas = _personas()
    personas[0]["schedule"][0]["furniture"] = "T:Cafe:counter:armchair"
    brain = MockLlmClient(
        tool_calls_responses=[_travel_to("Library"), _travel_to("Cafe")]
    )
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    walker = _RecordingWalk()
    state = {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f4d6",
            "desc": "waking up",
            "performing": False,
            "perform_until": None,
            "reasoning": "(waking up)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }
    common = dict(
        order=["Ada"],
        world_map=walker,
        emoji={"Ada": "\U0001f4d6"},
        clock=SimClock(START),
    )

    step(game, chars, state, 0, **common)  # off-plan: travels to the Library
    state["Ada"]["path"] = []  # clear the walk so she is due to decide again
    step(game, chars, state, 1, **common)  # on-plan: travels to the Cafe

    assert walker.calls == [
        ("T:Library:desks", None),  # off-plan -> hint dropped
        ("T:Cafe:counter", "T:Cafe:counter:armchair"),  # on-plan -> hint kept
    ]


def test_live_mock_decide_request_carries_the_block():
    # The issue's acceptance, offline: a live decide request body shows time +
    # current stop (+ elapsed once nonzero). Under the mock brain the pacing
    # ScheduleMockClient IS the brain, and its structured route logs every
    # request it was sent -- the exact live decide request body.
    from penn_world import build_penn_world  # noqa: E402  (sys.path shim above)
    from serve_penn import PennStepper  # noqa: E402

    stepper = PennStepper(num_steps=2, world=build_penn_world())
    assert stepper.clock.time_at(0) == START  # anchored at SIM_START

    assert stepper.tick() is not None

    logged = [
        call
        for char in stepper.chars.values()
        for call in char.agent.llm_client.tool_calls
    ]
    assert logged, "expected at least one decide request on the first tick"
    assert any(
        "Right now it is Monday 08:00 AM" in call["messages"][-1]["content"]
        for call in logged
    )
