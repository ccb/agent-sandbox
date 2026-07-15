"""Cognition tools on the live decide seam (issue #512, engine tools #358).

Pins the opt-in wiring that lets a real brain consult its own memory / beliefs
/ plan *before* picking a verb:

* with ``cognition_tools=True``, ``decide_with_action_tools`` runs the engine's
  bounded ``run_tool_loop`` -- ``recall`` / ``read_plan`` offered alongside the
  per-verb action tools -- and the first action pick still becomes the exact
  command string the step loop routes through the precondition gate;
* the ``COGNITION_BUDGET`` cap holds: an over-budget retrieval comes back as an
  ``is_error`` budget refusal the model sees, and the episode still ends in an
  action within ``1 + COGNITION_BUDGET`` rounds;
* flag off (the default): the decide is exactly ONE ``call_tools`` request with
  no cognition tools offered -- the #485 single round, untouched;
* ``attach_agents`` stamps ``agent.cognition_tools`` so the engine's converse
  path picks the tools up for free (the converse machinery itself is pinned by
  the engine's own suite).

Fully offline (``MockLlmClient`` scripted queues only). Run from the repo
root::

    uv run pytest godot-generative-agents/tests/test_cognition_wiring.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_per_action_decide.py: the Penn sim modules are run
# as scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    ScheduleMockClient,
    attach_agents,
    observe_and_decide,
)
from text_adventure_games.llm_client import (  # noqa: E402
    MockLlmClient,
    ToolCallResult,
)
from text_adventure_games.npc import COGNITION_BUDGET  # noqa: E402

# ------------------------------------------------------------ a tiny world
#
# The same three-location, one-persona world test_per_action_decide.py drives:
# enough to watch a whole decide tick through build_world's real wiring.

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


def _world(llm_client=None, cognition_tools=False):
    """(game, Ada) with agents attached -- mock brain, or the supplied one."""
    personas = _personas()
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(
        chars, personas, llm_client=llm_client, cognition_tools=cognition_tools
    )
    return game, chars["Ada"]


def _call(name, arguments, id="call_1"):
    """One scripted tool call in the shape ToolCallResult carries."""
    return {"id": id, "name": name, "arguments": arguments}


TRAVEL = ToolCallResult(
    text=None,
    tool_calls=[_call("travel", {"reasoning": "coffee first", "destination": "Cafe"})],
)


# --------------------------------------------------------- the capped loop


def test_flag_on_recall_round_then_action_routes_through_the_gate():
    brain = MockLlmClient(
        tool_calls_responses=[
            ToolCallResult(
                text=None, tool_calls=[_call("recall", {"query": "my plan"})]
            ),
            TRAVEL,
        ]
    )
    game, ada = _world(llm_client=brain, cognition_tools=True)

    command = observe_and_decide(game, ada, 0)

    # The action pick became the routed command, reasoning preserved.
    assert command == "travel to Cafe"
    assert ada.agent.last_reasoning == "coffee first"
    # Two requests in ONE decide tick: the recall round, then the action.
    assert len(brain.tool_calls_log) == 2
    first = brain.tool_calls_log[0]
    assert first["tool_choice"] == "any"
    # The engine's cognition tools ride alongside the per-verb action tools
    # (no beliefs are seeded in this tiny world, so no query_knowledge).
    assert [t["name"] for t in first["tools"]] == [
        "travel",
        "perform",
        "recall",
        "read_plan",
    ]
    # Round two saw the recall's tool_result in the same conversation.
    second = brain.tool_calls_log[1]["messages"]
    assert second[-2]["content"][0]["name"] == "recall"  # the assistant tool_use
    result_block = second[-1]["content"][0]
    assert result_block["type"] == "tool_result"
    assert result_block["is_error"] is False
    assert result_block["content"]  # the agent's seeded plan memory surfaced
    # The command still re-enters the precondition gate like any decision.
    assert game.parser.parse_command(command, actor=ada)
    assert ada.location.name == "Cafe"


def test_budget_refusal_is_seen_and_the_episode_still_acts():
    # One greedy round of COGNITION_BUDGET + 1 recalls: the over-budget call
    # must come back as the is_error refusal, and the next round still acts.
    recalls = ToolCallResult(
        text=None,
        tool_calls=[
            _call("recall", {"query": f"q{i}"}, id=f"call_{i}")
            for i in range(COGNITION_BUDGET + 1)
        ],
    )
    brain = MockLlmClient(tool_calls_responses=[recalls, TRAVEL])
    game, ada = _world(llm_client=brain, cognition_tools=True)

    command = observe_and_decide(game, ada, 0)

    assert command == "travel to Cafe"  # terminated in an action within budget
    assert len(brain.tool_calls_log) == 2
    # The second request carries one tool_result per recall; the over-budget
    # one is the engine's is_error refusal, verbatim.
    results = brain.tool_calls_log[1]["messages"][-1]["content"]
    assert len(results) == COGNITION_BUDGET + 1
    assert [r["is_error"] for r in results] == [False] * COGNITION_BUDGET + [True]
    assert results[-1]["content"] == "Retrieval budget exhausted -- you must act now."


# ------------------------------------------------------ the default gates


def test_flag_off_default_is_a_single_round_with_no_cognition_tools():
    brain = MockLlmClient(tool_calls_responses=[TRAVEL])
    game, ada = _world(llm_client=brain)  # cognition_tools defaults off

    command = observe_and_decide(game, ada, 0)

    assert command == "travel to Cafe"
    # Exactly ONE call_tools request -- the #485 single round, untouched.
    assert len(brain.tool_calls_log) == 1
    assert [t["name"] for t in brain.tool_calls_log[0]["tools"]] == [
        "travel",
        "perform",
    ]


def test_attach_agents_stamps_the_engine_flag_for_converse():
    # On: the engine's converse path reads agent.cognition_tools directly, so
    # the stamp alone is the whole converse wiring.
    _game, ada = _world(cognition_tools=True)
    assert ada.agent.cognition_tools is True
    # Off (default): the LLMAgent constructor default (False) is untouched.
    _game, ada = _world()
    assert ada.agent.cognition_tools is False


def test_normalized_schedule_carries_the_furniture_hint():
    from backend.build_world import _normalize_personas

    personas = [
        {
            "name": "Teacher",
            "emoji": "🧮",
            "schedule": [
                {"place": "Room", "activity": "teaching", "furniture": "blackboard"},
                {"place": "Hall", "activity": "resting"},  # no hint
            ],
        }
    ]
    _normalize_personas(personas)
    stops = personas[0]["schedule"]
    assert stops[0]["furniture"] == "blackboard"
    assert stops[1]["furniture"] is None  # absent hint defaults to None


def test_schedule_mock_client_exposes_current_stop_furniture():
    sched = ScheduleMockClient(
        [
            {
                "place": "Room",
                "activity": "teaching",
                "emoji": "🧮",
                "steps": 5,
                "furniture": "blackboard",
            },
            {"place": "Hall", "activity": "resting", "emoji": "🧮", "steps": None},
        ]
    )
    assert sched.furniture == "blackboard"
    sched.advance()
    assert sched.furniture is None  # next stop has no hint
