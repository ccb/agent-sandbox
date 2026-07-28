"""The agent's own recent actions, in its decide prompt (issue #826).

An agent's retrieved memories can be entirely intentions -- retrieve(touch=True)
keeps refreshing importance-8.0 commitment memories while its own 2.0 outcome
records decay out of contention -- so it re-forms the same intention at every
arrival, believing an errand it never performed is done. This block guarantees
its own last few actions are visible, without touching retrieval scoring.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_recent_actions_826.py -v
"""

import datetime
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
    RECENT_ACTIONS_MAX,
    attach_agents,
    recent_actions_block,
    remember_outcome,
)
from backend.sim_clock import SimClock  # noqa: E402

START = datetime.datetime(2023, 2, 13, 8, 0, 0)

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


def _ada():
    personas = _personas()
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas)
    return game, chars["Ada"]


def _act(agent, text, turn):
    """An own-action memory, exactly as remember_outcome writes one."""
    agent.memory.add_observation(text, turn=turn, importance=2.0, tags={ACTION_TAG})


# ------------------------------------------------------- the tag at the source


def test_remember_outcome_tags_its_record_as_an_action():
    _game, ada = _ada()
    remember_outcome(ada, "travel to Cafe", 7)
    record = ada.agent.memory.records[-1]
    assert ACTION_TAG in record.tags
    assert record.created_turn == 7


def test_a_blocked_attempt_is_tagged_too():
    # #636's failure memory is also the agent's own history: "I tried X and it
    # didn't work" is exactly what should stop it re-choosing X.
    _game, ada = _ada()
    remember_outcome(ada, "get moon", 9, fail_reason="There is no moon here.")
    record = ada.agent.memory.records[-1]
    assert ACTION_TAG in record.tags
    assert "didn't work" in record.text


def test_perceived_memories_are_not_tagged():
    # The block is the agent's OWN history; a presence observation is not.
    _game, ada = _ada()
    ada.agent.memory.add_observation("I see a bench nearby.", turn=1, importance=1.0)
    assert ACTION_TAG not in ada.agent.memory.records[-1].tags


# ------------------------------------------------------------- the block unit


def test_block_is_empty_without_a_clock():
    _game, ada = _ada()
    _act(ada.agent, "I traveled to Cafe.", 0)
    assert recent_actions_block(ada.agent, 10, None) == ""


def test_block_is_empty_without_any_tagged_record():
    _game, ada = _ada()
    ada.agent.memory.add_observation("I see a bench nearby.", turn=1, importance=1.0)
    assert recent_actions_block(ada.agent, 10, SimClock(START)) == ""


def test_block_lists_the_newest_actions_first_with_elapsed_minutes():
    _game, ada = _ada()
    _act(ada.agent, "I am grabbing coffee.", 0)  # 360 steps back = 60 min
    _act(ada.agent, "I traveled to Cafe.", 300)  # 60 steps back = 10 min
    got = recent_actions_block(ada.agent, 360, SimClock(START))
    assert got == (
        "Recently, you:\n"
        " - 10 min ago: I traveled to Cafe.\n"
        " - 60 min ago: I am grabbing coffee."
    )


def test_block_shows_just_now_for_a_same_minute_action():
    _game, ada = _ada()
    _act(ada.agent, "I traveled to Cafe.", 358)
    got = recent_actions_block(ada.agent, 360, SimClock(START))
    assert got == "Recently, you:\n - just now: I traveled to Cafe."


def test_block_caps_at_the_configured_count():
    _game, ada = _ada()
    for turn in range(10):
        _act(ada.agent, f"I did thing {turn}.", turn)
    got = recent_actions_block(ada.agent, 100, SimClock(START))
    assert len(got.splitlines()) == RECENT_ACTIONS_MAX + 1  # + the header line
    assert "I did thing 9." in got
    assert "I did thing 6." not in got


# ------------------------------------------------------------- pinned wording


def test_render_pins_the_block():
    assert render(
        "recent_actions",
        actions=[
            {"minutes": 57, "text": "I traveled to Van Pelt — Moelis Reading Room."},
            {"minutes": 67, "text": "I am grabbing a quick coffee with maya."},
            {"minutes": 0, "text": "I studied genetics for 30 minutes."},
        ],
    ) == (
        "Recently, you:\n"
        " - 57 min ago: I traveled to Van Pelt — Moelis Reading Room.\n"
        " - 67 min ago: I am grabbing a quick coffee with maya.\n"
        " - just now: I studied genetics for 30 minutes."
    )


# ------------------------------------------------- the decide-prompt wiring

from backend.cognition import memories_for_frame, observe_and_decide  # noqa: E402
from text_adventure_games.llm_client import (  # noqa: E402
    MockLlmClient,
    ToolCallResult,
)

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


def _ada_with_brain(brain):
    personas = _personas()
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=brain)
    return game, chars["Ada"]


def test_decide_prompt_carries_the_block_before_the_memories():
    brain = MockLlmClient(tool_calls_responses=[TRAVEL])
    game, ada = _ada_with_brain(brain)
    _act(ada.agent, "I traveled to Cafe.", 300)

    command = observe_and_decide(game, ada, 360, clock=SimClock(START))

    assert command == "travel to Cafe"
    user = brain.tool_calls_log[0]["messages"][-1]["content"]
    assert "Recently, you:\n - 10 min ago: I traveled to Cafe." in user
    # Own history first, then what retrieval surfaced.
    assert user.index("Recently, you:") < user.index("Relevant memories:")
    # The first non-empty line is still the location: the deterministic mock's
    # first-line read is untouched.
    first = next(line for line in user.splitlines() if line.strip())
    assert "Recently" not in first


def test_no_clock_means_no_block_in_the_prompt():
    brain = MockLlmClient(tool_calls_responses=[TRAVEL])
    game, ada = _ada_with_brain(brain)
    _act(ada.agent, "I traveled to Cafe.", 300)

    observe_and_decide(game, ada, 360)  # the pre-#826 call shape

    user = brain.tool_calls_log[0]["messages"][-1]["content"]
    assert "Recently, you:" not in user


def test_the_block_does_not_shift_which_memories_surface():
    # The two frame-visible outputs of a decide -- the command and the retrieved
    # memories -- must be identical with and without a clock. Retrieval must keep
    # querying the PLAIN environment text; frames embed the retrieved list, so a
    # shifted query would change the mock bake.
    brain1 = MockLlmClient(tool_calls_responses=[TRAVEL])
    game1, ada1 = _ada_with_brain(brain1)
    _act(ada1.agent, "I traveled to Cafe.", 300)
    plain = observe_and_decide(game1, ada1, 360)

    brain2 = MockLlmClient(tool_calls_responses=[TRAVEL])
    game2, ada2 = _ada_with_brain(brain2)
    _act(ada2.agent, "I traveled to Cafe.", 300)
    clocked = observe_and_decide(game2, ada2, 360, clock=SimClock(START))

    assert plain == clocked == "travel to Cafe"
    assert memories_for_frame(ada1.agent.last_retrieved) == memories_for_frame(
        ada2.agent.last_retrieved
    )
