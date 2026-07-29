"""Same-place travel convergence (issue #849).

Rooms and their lobby share a ``world:sector`` tile-address parent, while the
addressless campus hub matches every place.  A scheduled resident may only
travel within that group toward the current stop, eliminating lobby/room/hub
turnarounds without blocking real cross-building travel.
"""

import datetime
import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    DECIDE_MAX_ENUM,
    action_tools_for,
    attach_agents,
    nearby_affordances_line,
    walk_minutes_line,
)
from backend.run_simulation import step  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402
from backend.sim_config import CognitionConfig  # noqa: E402
from text_adventure_games.llm_client import ToolCallResult  # noqa: E402

LOCATIONS = [
    {
        "name": "Penn campus",
        "description": "the campus hub",
        "address": None,
        "hub": True,
    },
    {
        "name": "Van Pelt Library",
        "description": "the lobby",
        "address": "UPenn:Van Pelt Library:lobby",
    },
    {
        "name": "Van Pelt — Moelis Reading Room",
        "description": "the reading room",
        "address": "UPenn:Van Pelt Library:Moelis",
        "properties": ["studyable"],
    },
    {
        "name": "Van Pelt — Book Stacks",
        "description": "the stacks",
        "address": "UPenn:Van Pelt Library:West Wing Books",
        "properties": ["studyable"],
    },
    {
        "name": "Houston Hall",
        "description": "the student union",
        "address": "UPenn:Houston Hall:lobby",
        "properties": ["dining"],
    },
]


def _persona(first="Van Pelt — Moelis Reading Room"):
    return {
        "name": "Ada",
        "home": "Penn campus",
        "persona": "I am Ada.",
        "emoji": "📚",
        "start_tile": [0, 0],
        "destination": first,
        "activity": "studying",
        "schedule": [
            {
                "place": first,
                "activity": "studying",
                "emoji": "📚",
                "steps": 5,
            },
            {
                "place": "Van Pelt — Book Stacks",
                "activity": "browsing",
                "emoji": "📚",
                "steps": 5,
            },
        ],
    }


def _world(*, first="Van Pelt — Moelis Reading Room", brain=None):
    persona = _persona(first)
    game, chars = build_world(None, [persona], LOCATIONS)
    attach_agents(chars, [persona], llm_client=brain)
    return game, chars["Ada"]


def _move(game, char, name):
    if char.location is not None:
        char.location.remove_character(char)
    game.locations[name].add_character(char)


def _destinations(game, char, max_enum=DECIDE_MAX_ENUM):
    tools = {tool["name"]: tool for tool in action_tools_for(game, char, max_enum)}
    travel = tools.get("travel")
    if travel is None:
        return None
    return travel["parameters"]["properties"]["destination"].get("enum")


def test_building_choices_converge_then_follow_a_room_to_room_schedule():
    game, ada = _world()
    _move(game, ada, "Van Pelt Library")

    # From the lobby, the scheduled room is the sole same-building option;
    # cross-building travel remains a legitimate deviation.
    assert _destinations(game, ada) == [
        "Houston Hall",
        "Van Pelt — Moelis Reading Room",
    ]

    _move(game, ada, "Van Pelt — Moelis Reading Room")
    assert _destinations(game, ada) == ["Houston Hall"]

    # Advancing the authored schedule makes the sibling room the new convergent
    # target, preserving legitimate room-to-room itineraries.
    assert ada.agent.schedule.advance()
    assert _destinations(game, ada) == [
        "Houston Hall",
        "Van Pelt — Book Stacks",
    ]


class _ForbiddenTravelBrain:
    def __init__(self):
        self.context = {}

    def call_tools(self, messages, tools, **kwargs):
        # Deliberately ignore the curated enum to exercise the parser authority
        # used by free text and providers that return an out-of-schema value.
        return ToolCallResult(
            text=None,
            tool_calls=[
                {
                    "id": "call-849",
                    "name": "travel",
                    "arguments": {
                        "reasoning": "circle back",
                        "destination": "Van Pelt Library",
                    },
                }
            ],
        )


class _NoPathMap:
    def walk_path(self, src, address, furniture=None):
        return []


def test_hand_authored_forbidden_travel_fails_in_place_with_actionable_memory():
    game, ada = _world(brain=_ForbiddenTravelBrain())
    _move(game, ada, "Van Pelt Library")
    state = {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "📚",
            "desc": "idling",
            "performing": False,
            "perform_until": None,
            "reasoning": "",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }

    step(
        game,
        {"Ada": ada},
        state,
        0,
        order=["Ada"],
        world_map=_NoPathMap(),
        emoji={"Ada": "📚"},
        clock=None,
        cog=CognitionConfig(),
    )

    assert ada.location.name == "Van Pelt Library"
    failures = [
        record.text
        for record in ada.agent.memory.records
        if "didn't work" in record.text
    ]
    assert len(failures) == 1
    assert "scheduled stop, Van Pelt — Moelis Reading Room" in failures[0]
    assert "same place" in failures[0]


def test_parser_allows_the_scheduled_room_and_a_different_building():
    game, ada = _world()
    _move(game, ada, "Van Pelt Library")
    assert game.parser.parse_command(
        "travel to Van Pelt — Moelis Reading Room", actor=ada
    )
    assert ada.location.name == "Van Pelt — Moelis Reading Room"

    game, ada = _world()
    _move(game, ada, "Van Pelt Library")
    assert game.parser.parse_command("travel to Houston Hall", actor=ada)
    assert ada.location.name == "Houston Hall"


def test_addressless_hub_converges_and_suppresses_repeated_departures():
    game, ada = _world()
    assert ada.location.name == "Penn campus"
    assert _destinations(game, ada) == ["Van Pelt — Moelis Reading Room"]

    game, ada = _world(first="Penn campus")
    # At an addressless scheduled stop every destination is same-place, so the
    # travel tool disappears and even hand-authored departures fail.
    assert _destinations(game, ada) is None
    assert not game.parser.parse_command("travel to Houston Hall", actor=ada)
    assert ada.location.name == "Penn campus"
    assert (
        "already at your scheduled stop, Penn campus" in game.parser.last_fail_message
    )


class _Map:
    def tiles_for(self, address):
        return {(index, 0)} if (index := self._index(address)) is not None else set()

    def tile_gap_from(self, tile, address):
        return abs(tile[0] - self._index(address))

    @staticmethod
    def _index(address):
        names = {
            "UPenn:Van Pelt Library:lobby": 0,
            "UPenn:Van Pelt Library:Moelis": 1,
            "UPenn:Van Pelt Library:West Wing Books": 2,
            "UPenn:Houston Hall:lobby": 10,
        }
        return names.get(address)


def test_walk_cost_and_nearby_affordances_hide_forbidden_destinations():
    game, ada = _world()
    _move(game, ada, "Van Pelt Library")
    game.world_map = _Map()
    ada.tile = (0, 0)
    game.perceivable_locations = lambda _char: list(game.locations.values())

    nearby = nearby_affordances_line(game, ada)
    walk = walk_minutes_line(
        game, ada, SimClock(datetime.datetime(2025, 9, 15, 9, 0, 0))
    )

    assert "Moelis Reading Room" in nearby
    assert "Houston Hall" in nearby
    assert "Book Stacks" not in nearby
    assert "Van Pelt Library (" not in nearby
    assert "Moelis Reading Room" in walk
    assert "Houston Hall" in walk
    assert "Book Stacks" not in walk
    assert "Van Pelt Library " not in walk


def test_oversized_enum_fallback_keeps_parser_gate_authoritative():
    game, ada = _world()
    _move(game, ada, "Van Pelt Library")
    assert _destinations(game, ada, max_enum=1) is None
    assert not game.parser.parse_command("travel to Van Pelt — Book Stacks", actor=ada)
    assert ada.location.name == "Van Pelt Library"


def test_character_without_a_schedule_keeps_unrestricted_travel():
    game, ada = _world()
    _move(game, ada, "Van Pelt Library")
    ada.agent.schedule = None
    assert _destinations(game, ada) == sorted(game.locations)
    assert game.parser.parse_command("travel to Van Pelt — Book Stacks", actor=ada)
