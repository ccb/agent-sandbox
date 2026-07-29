"""What a walk costs, in the decide prompt (issue #826).

Penn legs are long -- Van Pelt to Houston Hall is ~57 sim-minutes -- but the
exits list prices every destination the same, so an agent forms "quick coffee
run" intentions that are two-hour round trips. This line prices them.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_walk_minutes_826.py -v
"""

import datetime
import os
import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.prompt_templates import render  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    ACTION_TAG,
    DECIDE_MAX_ENUM,
    attach_agents,
    observe_and_decide,
    walk_minutes_line,
)
from backend.sim_clock import SimClock  # noqa: E402
from backend.world_map import WorldMap  # noqa: E402
from text_adventure_games.llm_client import MockLlmClient, ToolCallResult  # noqa: E402

START = datetime.datetime(2023, 2, 13, 8, 0, 0)
UPENN = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "backend", "penn", "the_upenn"
)

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


class _FakeMap:
    """Two priced addresses and one label-only address, at known distances."""

    width = 100
    height = 100

    def tiles_for(self, address):
        return {
            "T:Cafe:counter": {(0, 30)},
            "T:Library:desks": {(0, 6)},
        }.get(address, set())

    def tile_gap_from(self, tile, address):
        tiles = self.tiles_for(address)
        if not tiles:
            return self.width + self.height
        return min(max(abs(tile[0] - t[0]), abs(tile[1] - t[1])) for t in tiles)

    def tile_gap(self, addr_a, addr_b):
        # Not what these tests exercise, but TiledGame.perceivable_locations
        # calls it whenever an agent perceives -- answer "never nearby" rather
        # than AttributeError if a later test in this file perceives.
        return self.width + self.height


def _ada(world_map):
    personas = _personas()
    game, chars = build_world(world_map, personas, LOCATIONS)
    attach_agents(chars, personas)
    return game, chars["Ada"]


# ------------------------------------------------------ the WorldMap primitive


def test_tile_gap_from_matches_tile_gap_semantics_on_the_real_map():
    wm = WorldMap(UPENN)
    address = "UPenn:Houston Hall:lobby"
    tiles = wm.tiles_for(address)
    assert tiles, "expected the Houston Hall lobby to resolve on the real map"
    # A tile inside the footprint is zero away from it.
    assert wm.tile_gap_from(next(iter(tiles)), address) == 0
    # An unknown address gets tile_gap's own large sentinel, so it never reads
    # as nearby.
    assert wm.tile_gap_from((0, 0), "UPenn:Nowhere:void") == wm.width + wm.height
    # And it agrees with tile_gap when the source tile IS the other footprint:
    # never larger than the box-to-box gap (a point box is inside the source box).
    other = "UPenn:Van Pelt Library:lobby"
    if wm.tiles_for(other):
        box_gap = wm.tile_gap(other, address)
        point_gaps = [wm.tile_gap_from(t, address) for t in wm.tiles_for(other)]
        assert min(point_gaps) <= box_gap


# ----------------------------------------------------------------- the line


def test_line_is_empty_without_a_map_or_a_clock():
    game, ada = _ada(None)
    assert walk_minutes_line(game, ada, SimClock(START)) == ""
    game2, ada2 = _ada(_FakeMap())
    assert walk_minutes_line(game2, ada2, None) == ""


def test_line_prices_destinations_nearest_first_and_drops_unmapped_ones():
    game, ada = _ada(_FakeMap())
    # Exercise the generic pricing helper without #849's schedule curation;
    # focused same-place tests pin the curated subset.
    ada.agent.schedule = None
    ada.tile = (0, 0)
    # Library is 6 tiles away (1 min at 10 s/step), Cafe 30 tiles (5 min).
    # The Green has address None -- no tiles -- so it is dropped.
    assert walk_minutes_line(game, ada, SimClock(START)) == (
        "Walking from here takes at least about: Library 1 min; Cafe 5 min."
    )


def test_line_lists_the_place_the_agent_is_standing_in_at_zero():
    game, ada = _ada(_FakeMap())
    ada.agent.schedule = None
    ada.tile = (0, 6)  # standing on the Library's tile
    got = walk_minutes_line(game, ada, SimClock(START))
    assert got.startswith("Walking from here takes at least about: Library 0 min;")


def test_line_is_empty_when_the_character_has_no_tile():
    game, ada = _ada(_FakeMap())
    if hasattr(ada, "tile"):
        del ada.tile
    assert walk_minutes_line(game, ada, SimClock(START)) == ""


class _ManyLocsGame:
    """Minimal game double (#826 review, minor 3): N addressed locations, no
    engine machinery needed -- walk_minutes_line only reads .locations."""

    def __init__(self, n):
        self.locations = {
            f"Loc{i}": type("L", (), {"tile_address": f"T:Loc{i}:x"})()
            for i in range(n)
        }
        self.world_map = self._LinearMap()

    class _LinearMap:
        """Every address's one tile sits at (i, 0), i taken from its name --
        an exact, monotonic nearest-first order with no real map needed."""

        def tiles_for(self, address):
            i = int(address.split(":")[1].removeprefix("Loc"))
            return {(i, 0)}

        def tile_gap_from(self, tile, address):
            x, _y = next(iter(self.tiles_for(address)))
            return abs(tile[0] - x)


def test_line_caps_at_decide_max_enum_nearest_first():
    # action_tools_for's own destination enum falls back to free text past
    # DECIDE_MAX_ENUM, so pricing every destination beyond that cap would grow
    # this line unboundedly on a bigger world for no benefit -- keep only the
    # DECIDE_MAX_ENUM nearest.
    game = _ManyLocsGame(DECIDE_MAX_ENUM + 5)
    char = type("C", (), {"tile": (0, 0)})()
    got = walk_minutes_line(game, char, SimClock(START))
    assert got.count(" min") == DECIDE_MAX_ENUM
    assert f"Loc{DECIDE_MAX_ENUM - 1} " in got  # farthest destination that survives
    assert f"Loc{DECIDE_MAX_ENUM} " not in got  # first one dropped by the cap


# ------------------------------------ the decide-prompt order (#826 review)

# Every other test in this file (and the wiring tests in
# test_recent_actions_826.py) builds with world_map=None, so walk_minutes_line
# is always "" there (its own `world_map is None` guard) -- none of them can
# tell a correct call order from a dropped `walk_minutes_line` call or the two
# #826 blocks swapped. This is the one test with a real tile-bearing map, so
# the walk line actually renders and the documented order -- walk cost, then
# own recent history, then retrieved memories -- has coverage.

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


def test_decide_prompt_orders_walk_before_recent_before_memories():
    brain = MockLlmClient(tool_calls_responses=[TRAVEL])
    personas = _personas()
    game, chars = build_world(_FakeMap(), personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    ada = chars["Ada"]
    ada.agent.memory.add_observation(
        "I traveled to Cafe.", turn=300, importance=2.0, tags={ACTION_TAG}
    )

    command = observe_and_decide(game, ada, 360, clock=SimClock(START))

    assert command == "travel to Cafe"
    user = brain.tool_calls_log[0]["messages"][-1]["content"]
    assert "Walking from here takes at least about:" in user
    assert user.index("Walking from here takes at least about:") < user.index(
        "Recently, you:"
    )
    assert user.index("Recently, you:") < user.index("Relevant memories:")


# ------------------------------------------------------------- pinned wording


def test_render_pins_the_line():
    assert render(
        "walk_minutes",
        destinations="Van Pelt — Moelis Reading Room 0 min; Houston Hall 27 min",
    ) == (
        "Walking from here takes at least about: "
        "Van Pelt — Moelis Reading Room 0 min; Houston Hall 27 min."
    )
