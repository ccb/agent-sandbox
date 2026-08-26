"""The dither damper (issue #933).

#916 fixed the *mechanical* mid-walk retarget, but #878 candidate 1 showed the
behavioral layer can still alternate "legitimate" decides: 12 cross-building
retargets and 238 abandoned-leg minutes in one afternoon, including a clean
5-cycle Houston <-> Irvine ping-pong. The damper: when an agent abandoned a
travel leg to building X within the last ``ABANDONED_LEG_WINDOW_MIN``
sim-minutes, its decide prompt discourages re-targeting X -- unless a new
memory or conversation involving X arrived since the abandonment, or X is the
plan's own current stop. A discouragement the model can override with a stated
reason, never a hard block.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_dither_damper_933.py -v
"""

import datetime
import sys
from pathlib import Path

# Same import shim as test_decide_context.py: the Penn sim modules are run as
# scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    ABANDONED_LEG_WINDOW_MIN,
    ACTION_TAG,
    abandoned_walks_block,
    attach_agents,
    building_of,
)
from backend.run_simulation import step  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402
from text_adventure_games.llm_client import (  # noqa: E402
    MockLlmClient,
    ToolCallResult,
)

# 2023-02-13 is a Monday -- the same instant as penn_world.SIM_START.
START = datetime.datetime(2023, 2, 13, 8, 0, 0)

# ------------------------------------------------------------ a tiny world
#
# test_decide_context.py's three-location world, plus enough buildings to
# ping-pong between: Cafe and Library are distinct buildings, Cafe Patio is a
# second room of the Cafe building, Van Pelt carries a room whose display name
# ("Moelis Reading Room") shares no word with its building -- the case the
# justification scan must still match. Ada's schedule points at Hall, so a
# Cafe <-> Library ping-pong is entirely off-plan (the observed #933 shape:
# no plan stop justified any leg).

LOCATIONS = [
    {
        "name": "The Green",
        "description": "the central lawn",
        "address": None,
        "hub": True,
    },
    {"name": "Cafe", "description": "a coffee shop", "address": "T:Cafe:counter"},
    {
        "name": "Cafe Patio",
        "description": "the cafe's patio",
        "address": "T:Cafe:patio",
    },
    {"name": "Library", "description": "a small library", "address": "T:Library:desks"},
    {"name": "Hall", "description": "a lecture hall", "address": "T:Hall:lobby"},
    {
        "name": "Moelis Reading Room",
        "description": "a grand reading room",
        "address": "T:Van Pelt:reading",
    },
]


def _personas(home="Cafe", destination="Hall", activity="attending a seminar"):
    # Fresh dicts per test: attach_agents and the step loop mutate the spec.
    return [
        {
            "name": "Ada",
            "home": home,
            "persona": "I am Ada, a curious first-year.",
            "emoji": "\U0001f4d6",
            "start_tile": [0, 0],
            "destination": destination,
            "activity": activity,
            "schedule": [
                {
                    "place": destination,
                    "activity": activity,
                    "emoji": "\U0001f4d6",
                    "steps": None,
                }
            ],
        }
    ]


def _world(llm_client=None, personas=None):
    """(game, chars) with agents attached -- mock brain, or the supplied one."""
    personas = personas if personas is not None else _personas()
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=llm_client)
    return game, chars


def _unit_world():
    """(game, Ada) for the block-level unit tests."""
    game, chars = _world()
    return game, chars["Ada"]


def _travel(destination):
    return ToolCallResult(
        text=None,
        tool_calls=[
            {
                "id": "call_1",
                "name": "travel",
                "arguments": {"reasoning": "off I go", "destination": destination},
            }
        ],
    )


def _perform(activity):
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


def _state():
    return {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f4d6",
            "desc": "waking up",
            "performing": False,
            "perform_until": None,
            "reasoning": "",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }


class _TwoTileWalk:
    """WorldMap stand-in: every walk is the same two-tile path."""

    def walk_path(self, start, address, furniture=None):
        return [(0, 1), (0, 2)]


def _prompt(brain, decide_idx):
    """The user message the brain saw on its Nth decide."""
    return brain.tool_calls_log[decide_idx]["messages"][-1]["content"]


# --------------------------------------------------------- address reduction


def test_building_of_reduces_a_tile_address():
    # world:building:place -- the same reduction tools/analyze_run.py applies.
    assert building_of("T:Cafe:counter") == "Cafe"
    assert building_of("UPenn:Van Pelt Library:Moelis Family Grand Reading Room") == (
        "Van Pelt Library"
    )
    # The hub has no address; a flat address names no building.
    assert building_of(None) == ""
    assert building_of("flat-address") == ""


# ---------------------------------------------------------- the block itself


def test_block_needs_a_clock_and_live_abandons():
    game, ada = _unit_world()
    clock = SimClock(START)
    assert abandoned_walks_block(game, ada, None, 5, clock) == ""
    assert abandoned_walks_block(game, ada, {}, 5, clock) == ""
    # No clock (the bake, the offline tests): never renders.
    assert abandoned_walks_block(game, ada, {"Library": 0}, 5, None) == ""


def test_block_pins_the_damper_sentence():
    game, ada = _unit_world()
    # Abandoned at step 0; step 72 at 10 s/step = 12 min ago.
    assert abandoned_walks_block(game, ada, {"Library": 0}, 72, SimClock(START)) == (
        "You recently abandoned a walk to Library (12 min ago) without doing "
        "anything there, and nothing new has come up about that place since. "
        "Do not travel back there without a new reason you can state -- "
        "walking back and forth wastes the day."
    )


def test_block_lists_multiple_legs_most_recent_first():
    game, ada = _unit_world()
    # At step 126: Cafe abandoned at 66 (10 min ago), Library at 60 (11 min).
    assert abandoned_walks_block(
        game, ada, {"Library": 60, "Cafe": 66}, 126, SimClock(START)
    ) == (
        "You recently abandoned walks to Cafe (10 min ago) and Library "
        "(11 min ago) without doing anything there, and nothing new has come "
        "up about those places since. Do not travel back there without a new "
        "reason you can state -- walking back and forth wastes the day."
    )


def test_block_decays_past_the_window():
    game, ada = _unit_world()
    clock = SimClock(START)
    edge = ABANDONED_LEG_WINDOW_MIN * 6  # minutes -> steps at 10 s/step
    # At the window edge the leg still renders ...
    assert "Library" in abandoned_walks_block(game, ada, {"Library": 0}, edge, clock)
    # ... one minute past it, the damper has decayed.
    assert abandoned_walks_block(game, ada, {"Library": 0}, edge + 6, clock) == ""


def test_a_new_memory_about_the_building_lifts_the_damper():
    game, ada = _unit_world()
    clock = SimClock(START)
    # A conversation involving the abandoned building, AFTER the abandonment:
    # the retarget is justified, so the damper stands down.
    ada.agent.memory.add_chat(
        "Priya said: meet me at the Library in ten minutes.", turn=30, partner="Priya"
    )
    assert abandoned_walks_block(game, ada, {"Library": 20}, 60, clock) == ""
    # The same memory BEFORE the abandonment justifies nothing.
    assert "Library" in abandoned_walks_block(game, ada, {"Library": 40}, 60, clock)


def test_a_room_name_lifts_its_whole_building():
    game, ada = _unit_world()
    clock = SimClock(START)
    # "Moelis Reading Room" shares no word with its building ("Van Pelt") --
    # the analyze_run lesson: display names drop the building qualifier. A new
    # memory naming any room of the building justifies returning to it.
    ada.agent.memory.add_chat(
        "Priya said: I'll be in the Moelis Reading Room.", turn=30, partner="Priya"
    )
    assert abandoned_walks_block(game, ada, {"Van Pelt": 20}, 60, clock) == ""


def test_own_action_memories_do_not_lift_the_damper():
    game, ada = _unit_world()
    clock = SimClock(START)
    # The agent's own action records are not new information -- least of all
    # the #636 failure memory for a blocked travel to the very same building.
    ada.agent.memory.add_observation(
        'I tried to "travel Library" but it didn\'t work: it is closed.',
        turn=30,
        tags={ACTION_TAG},
    )
    assert "Library" in abandoned_walks_block(game, ada, {"Library": 20}, 60, clock)


def test_the_current_scheduled_stop_is_exempt():
    game, ada = _unit_world()  # scheduled at Hall
    clock = SimClock(START)
    # The plan is a standing justification: the #580 context block already
    # says "your plan's current stop is ... at Hall", and a damper clause
    # saying "do not go back to Hall" would contradict it head-on.
    assert abandoned_walks_block(game, ada, {"Hall": 0}, 12, clock) == ""
    # Mixed: only the off-plan building is discouraged.
    text = abandoned_walks_block(game, ada, {"Hall": 0, "Library": 0}, 12, clock)
    assert "Library" in text
    assert "Hall" not in text


# ------------------------------------------------------- step-loop plumbing


def test_ping_pong_records_the_abandon_and_damps_the_redecide():
    # The #933 fingerprint, in miniature: Ada (scheduled at Hall) walks
    # Library -> Cafe -> Library, never settling. Departing Library for Cafe
    # abandons the Library leg; when she re-picks Library two steps later,
    # her decide prompt must carry the damper.
    brain = MockLlmClient(
        tool_calls_responses=[_travel("Library"), _travel("Cafe"), _travel("Library")]
    )
    game, chars = _world(llm_client=brain)
    state = _state()
    common = dict(
        order=["Ada"],
        world_map=_TwoTileWalk(),
        emoji={"Ada": "\U0001f4d6"},
        clock=SimClock(START),
    )

    step(game, chars, state, 0, **common)  # decide 1: travel Library
    step(game, chars, state, 1, **common)  # arrive
    step(game, chars, state, 2, **common)  # decide 2: travel Cafe -> abandon
    assert state["Ada"]["abandoned_legs"] == {"Library": 2}
    step(game, chars, state, 3, **common)  # arrive
    step(game, chars, state, 4, **common)  # decide 3: travel Library again

    assert "You recently abandoned a walk to Library (just now)" in _prompt(brain, 2)
    # ... and departing Cafe for Library recorded the second abandon.
    assert state["Ada"]["abandoned_legs"] == {"Library": 2, "Cafe": 4}


def test_a_fresh_memory_keeps_the_redecide_clean():
    # Same ping-pong, but a conversation names the Library between the
    # abandonment and the re-decide: the damper stands down, per the issue --
    # "unless a new memory/conversation justifying it".
    brain = MockLlmClient(
        tool_calls_responses=[_travel("Library"), _travel("Cafe"), _travel("Library")]
    )
    game, chars = _world(llm_client=brain)
    state = _state()
    common = dict(
        order=["Ada"],
        world_map=_TwoTileWalk(),
        emoji={"Ada": "\U0001f4d6"},
        clock=SimClock(START),
    )
    for idx in range(3):
        step(game, chars, state, idx, **common)
    chars["Ada"].agent.memory.add_chat(
        "Priya said: forgot my notes at the Library, can you grab them?",
        turn=3,
        partner="Priya",
    )
    step(game, chars, state, 3, **common)
    step(game, chars, state, 4, **common)

    # The abandonment WAS recorded -- only the rendering stood down (the
    # ping-pong test above proves the same setup renders without the memory).
    assert state["Ada"]["abandoned_legs"] == {"Library": 2, "Cafe": 4}
    assert "abandoned a walk" not in _prompt(brain, 2)


def test_settling_at_the_target_completes_the_leg():
    # travel Library -> perform there -> travel Cafe: the settle completed
    # the Library leg, so departing afterwards abandons nothing and the
    # third decide's prompt carries no damper.
    brain = MockLlmClient(
        tool_calls_responses=[
            _travel("Library"),
            _perform("browsing the stacks"),
            _travel("Cafe"),
        ]
    )
    game, chars = _world(llm_client=brain)
    state = _state()
    common = dict(
        order=["Ada"],
        world_map=_TwoTileWalk(),
        emoji={"Ada": "\U0001f4d6"},
        clock=SimClock(START),
    )
    step(game, chars, state, 0, **common)  # decide 1: travel Library
    step(game, chars, state, 1, **common)  # arrive
    step(game, chars, state, 2, **common)  # decide 2: perform (settle)
    assert state["Ada"]["walk_building"] == ""
    state["Ada"]["perform_until"] = 3  # cut the settle short
    step(game, chars, state, 3, **common)  # decide 3: travel Cafe

    assert state["Ada"].get("abandoned_legs", {}) == {}
    assert "abandoned a walk" not in _prompt(brain, 2)


def test_a_same_building_hop_is_not_an_abandon():
    # Arriving at the Cafe counter and re-targeting the Cafe Patio is #849's
    # same-place oscillation, not a cross-building retarget -- out of scope
    # here, and analyze_run's split (#850) treats it the same way.
    personas = _personas(home="Library", destination="Cafe Patio", activity="a coffee")
    brain = MockLlmClient(tool_calls_responses=[_travel("Cafe"), _travel("Cafe Patio")])
    game, chars = _world(llm_client=brain, personas=personas)
    state = _state()
    common = dict(
        order=["Ada"],
        world_map=_TwoTileWalk(),
        emoji={"Ada": "\U0001f4d6"},
        clock=SimClock(START),
    )
    step(game, chars, state, 0, **common)  # decide 1: travel Cafe
    step(game, chars, state, 1, **common)  # arrive
    step(game, chars, state, 2, **common)  # decide 2: hop to the patio

    # The hop itself went through (guards against a vacuous pass on a
    # refused travel) -- it just isn't an abandon.
    assert state["Ada"]["walk_target"] == "Cafe Patio"
    assert state["Ada"].get("abandoned_legs", {}) == {}


def test_recording_prunes_stale_abandons():
    # The per-agent map must not accrete a whole day of expired entries: a
    # record moment past the window drops what has already decayed.
    brain = MockLlmClient(tool_calls_responses=[_travel("Hall")])
    game, chars = _world(llm_client=brain)
    state = _state()
    state["Ada"]["walk_building"] = "Library"  # mid-abandon of a Library leg
    state["Ada"]["abandoned_legs"] = {"Stale Hall": 0}
    window_steps = ABANDONED_LEG_WINDOW_MIN * 6
    step(
        game,
        chars,
        state,
        window_steps + 6,
        order=["Ada"],
        world_map=_TwoTileWalk(),
        emoji={"Ada": "\U0001f4d6"},
        clock=SimClock(START),
    )

    assert state["Ada"]["abandoned_legs"] == {"Library": window_steps + 6}
