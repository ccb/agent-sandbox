"""The per-action decide path for a real brain (issue #485).

Pins the transport that replaces the single free-text ``choose_action`` tool
when a real LLM client drives the cast:

* a supplied ``call_tools`` brain is offered one typed tool per verb
  (``travel`` / ``perform``, ``tool_choice="any"``) and its pick is
  reassembled into the exact command string the step loop routes through the
  precondition gate;
* ``travel``'s ``destination`` slot carries an enum of the world's real
  location names -- and the Penn campus fits under the enum cap, so the enum
  actually survives on the real map;
* the default offline mock is byte-identical: the schedule brain never
  receives a plural ``call_tools`` decision;
* a brain that declines (an outage, a refusal) falls back to the classic
  ``agent.decide()`` path, so live mode degrades exactly as before;
* driven through ``run_simulation.step``, the whole decide is one model
  request, stamped ``role: "decide"`` for the ledger / request monitor.

Fully offline (fake brains; the tracked ``the_upenn`` matrix for the Penn
test). Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_per_action_decide.py -v
"""

import sys
from pathlib import Path

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself (same pattern as test_penn_live.py).
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    DECIDE_MAX_ENUM,
    action_tools_for,
    attach_agents,
    observe_and_decide,
)
from backend.run_simulation import step  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from text_adventure_games.llm_client import ToolCallResult  # noqa: E402

# ------------------------------------------------------------ a tiny world
#
# Three locations and one persona are enough to watch a whole decide tick;
# build_world wires them exactly as it wires the Penn campus (hub-and-spoke,
# travel/perform registered, simultaneous mode).

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


# ------------------------------------------------------------- fake brains


class PerActionBrain:
    """A 'real-shaped' brain for the #485 path: records every ``call_tools``
    offer and answers with one scripted per-action tool call. It also carries
    the ``context`` dict the step loop stamps attribution into, snapshotting
    it at call time -- exactly when the real adapters read it (record_call)."""

    def __init__(self, name, arguments):
        self._name = name
        self._arguments = arguments
        self.context: dict = {}
        self.offers: list[dict] = []

    def call_tools(
        self, messages, tools, tool_choice="auto", max_tokens=256, temperature=0.0
    ):
        self.offers.append(
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "context": dict(self.context),
            }
        )
        return ToolCallResult(
            text=None,
            tool_calls=[
                {"id": "call_1", "name": self._name, "arguments": dict(self._arguments)}
            ],
        )


class DecliningBrain:
    """``call_tools``-capable but always declines (an outage / a refusal),
    while the forced-single ``choose_action`` route still answers -- so the
    test can watch the fallback land on the classic decide() path."""

    def __init__(self):
        self.context: dict = {}
        self.plural_calls = 0
        self.single_calls = 0

    def call_tools(
        self, messages, tools, tool_choice="auto", max_tokens=256, temperature=0.0
    ):
        self.plural_calls += 1
        return None

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.single_calls += 1
        return {
            "reasoning": "fallback",
            "action": "perform",
            "arguments": "people-watching",
        }


# ------------------------------------------------- the per-action transport


def test_real_brain_gets_per_verb_tools_and_routes_the_pick():
    brain = PerActionBrain(
        "travel", {"reasoning": "coffee first", "destination": "Cafe"}
    )
    game, ada = _world(llm_client=brain)

    command = observe_and_decide(game, ada, 0)

    # The tool call became the routed command, reasoning preserved for traces.
    assert command == "travel to Cafe"
    assert ada.agent.last_reasoning == "coffee first"
    # One model request for the whole decide -- the same per-tick call count
    # (and ledger attribution) as the choose_action path this replaces.
    assert len(brain.offers) == 1
    offer = brain.offers[0]
    assert [t["name"] for t in offer["tools"]] == ["travel", "perform"]
    assert offer["tool_choice"] == "any"
    assert offer["messages"][0]["role"] == "system"
    assert offer["messages"][-1]["role"] == "user"
    # The command re-enters the precondition gate exactly as a free-text one.
    assert game.parser.parse_command(command, actor=ada)
    assert ada.location.name == "Cafe"


def test_travel_carries_the_location_enum_and_perform_stays_free_text():
    brain = PerActionBrain(
        "perform", {"reasoning": "settling in", "activity": "stretching"}
    )
    game, ada = _world(llm_client=brain)

    command = observe_and_decide(game, ada, 0)
    assert command == "perform stretching"

    tools = {t["name"]: t for t in brain.offers[0]["tools"]}
    # travel: destination constrained to the world's real location names --
    # the same game.locations the Travel action matches a command against.
    destination = tools["travel"]["parameters"]["properties"]["destination"]
    assert destination["enum"] == ["Cafe", "Library", "The Green"]
    assert "destination" in tools["travel"]["parameters"]["required"]
    # perform: any short phrase is a valid on-screen label, so no enum.
    activity = tools["perform"]["parameters"]["properties"]["activity"]
    assert activity["type"] == "string"
    assert "enum" not in activity
    assert "activity" in tools["perform"]["parameters"]["required"]


def test_penn_campus_fits_under_the_enum_cap():
    # The point of the enum is that every real venue stays nameable: if the
    # campus ever outgrows DECIDE_MAX_ENUM the slot silently degrades to free
    # text and the #485 wiring buys nothing -- fail loudly here instead.
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    attach_agents(chars, pw.personas)
    char = chars[pw.personas[0]["name"]]

    assert len(game.locations) <= DECIDE_MAX_ENUM
    tools = {t["name"]: t for t in action_tools_for(game, char)}
    destination = tools["travel"]["parameters"]["properties"]["destination"]
    assert destination["enum"] == sorted(game.locations)


# --------------------------------------------------- the determinism gates


def test_default_mock_run_never_sees_a_plural_decision():
    game, ada = _world(llm_client=None)
    agent = ada.agent
    # The wiring the gate keys on: with no supplied client, the brain IS the
    # pacing schedule client (one object) -- so the gate must stay closed.
    assert agent.llm_client is agent.schedule

    command = observe_and_decide(game, ada, 0)

    assert command == "travel to Cafe"  # the schedule brain decided, as before
    schedule = agent.schedule
    # The decision took the classic forced-single choose_action route...
    assert len(schedule.tool_calls) == 1
    assert schedule.tool_calls[0]["tool"]["name"] == "choose_action"
    # ...and the inherited plural route was never consulted (a naive
    # hasattr(brain, "call_tools") gate would have flipped the mock onto it).
    assert schedule.tool_calls_log == []


def test_declining_brain_falls_back_to_classic_decide():
    brain = DecliningBrain()
    game, ada = _world(llm_client=brain)

    command = observe_and_decide(game, ada, 0)

    assert brain.plural_calls == 1  # the per-action round was tried first
    assert brain.single_calls == 1  # then decide()'s choose_action fallback
    assert command == "perform people-watching"
    assert ada.agent.last_reasoning == "fallback"


# ------------------------------------------- attribution through the loop


class _StubMap:
    """Just enough WorldMap for one step(): travel asks it for a tile route."""

    def walk_path(self, src, address):
        return [(1, 1)]


def test_step_attributes_the_decide_and_keeps_the_reasoning_on_the_frame():
    brain = PerActionBrain(
        "perform", {"reasoning": "settling in", "activity": "people-watching"}
    )
    personas = _personas()
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
        }
    }

    frame, _chats = step(
        game,
        chars,
        state,
        0,
        order=["Ada"],
        world_map=_StubMap(),
        emoji={"Ada": "\U0001f4d6"},
    )

    # One role:decide request for the persona's decision tick -- the context
    # the step loop stamped is what the adapters record into the ledger and
    # the request monitor reads for its per-role rows.
    assert len(brain.offers) == 1
    ctx = brain.offers[0]["context"]
    assert ctx["role"] == "decide"
    assert ctx["actor"] == "Ada"
    assert ctx["turn"] == 0
    # The tool call's reasoning reaches the replay card unchanged.
    assert frame["Ada"]["reasoning"] == "settling in"
    assert state["Ada"]["performing"] is True
    assert chars["Ada"].get_property("activity") == "people-watching"
