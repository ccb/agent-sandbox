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

from backend.actions import TalkTo  # noqa: E402
from backend.prompt_templates import render  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    ACTION_TAG,
    RECENT_ACTION_TEXT_MAX,
    RECENT_ACTIONS_MAX,
    attach_agents,
    maybe_converse,
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


def _bo_persona():
    return {
        "name": "Bo",
        "home": "The Green",
        "persona": "I am Bo, Ada's labmate.",
        "emoji": "\U0001f9d1",
        "start_tile": [0, 0],
        "destination": "Cafe",
        "activity": "reading a novel",
        "schedule": [
            {
                "place": "Cafe",
                "activity": "reading a novel",
                "emoji": None,
                "steps": None,
            }
        ],
    }


class _OneLineConvoBrain:
    """Speaks one line, then ends the conversation. Same shape as
    test_universal_verbs_614's ``_ScriptedConvoBrain`` -- the closest existing
    talk_to harness -- trimmed to the single exchange this test needs."""

    def __init__(self, line):
        self._line = line
        self.context: dict = {}

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        if tool["name"] == "conversation_outcome":
            return {"plans_changed": False}
        if self._line is not None:
            line, self._line = self._line, None
            return {"utterance": line, "done": True}
        return {}


def test_a_completed_conversation_is_tagged_and_reaches_the_block():
    # #826 review, Important 1: remember_outcome deliberately returns early for
    # talk_to (Phase 1.5 of maybe_converse owns both branches), and its
    # *failure* branch (a dropped request) routes back into
    # remember_outcome(fail_reason=...) and IS tagged -- see
    # test_a_blocked_attempt_is_tagged_too above. But the success branch's own
    # add_observation, written the instant a requested conversation actually
    # opens, was missing tags={ACTION_TAG}: a talk that really happened never
    # showed up in "Recently, you:", while a dropped one did. Drive a real
    # talk_to -> maybe_converse open (the pattern in test_universal_verbs_614's
    # test_talk_to_memory_is_written_only_when_the_conversation_opens) rather
    # than asserting on the add_observation call in isolation.
    personas = [_personas()[0], _bo_persona()]
    game, chars = build_world(None, personas, LOCATIONS)
    game.parser.add_action(TalkTo)
    brain = _OneLineConvoBrain("Hey Bo, quick question about the exam.")
    attach_agents(chars, personas, llm_client=brain)
    ada, bo = chars["Ada"], chars["Bo"]
    cafe = game.locations["Cafe"]
    for ch in (ada, bo):
        if ch.location is not None:
            ch.location.remove_character(ch)
        cafe.add_character(ch)
    order = ["Ada", "Bo"]
    state = {n: {"performing": True, "path": [], "chat": None} for n in order}
    frame = {n: {} for n in order}

    assert game.parser.parse_command("talk_to Bo about the exam", actor=ada)
    maybe_converse(game, chars, state, frame, 0, {}, order, active={})

    record = next(r for r in ada.agent.memory.records if "talk to Bo" in r.text)
    assert record.text == "I went to talk to Bo about the exam."
    assert ACTION_TAG in record.tags

    got = recent_actions_block(ada.agent, 0, SimClock(START))
    assert "I went to talk to Bo about the exam." in got


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


def test_block_keeps_only_the_newest_of_each_repeated_action():
    # #826 review: #636 writes a failure memory every tick a gate blocks the
    # SAME re-picked action, and deliberately does not dedupe at write time. Un-
    # deduped here, the agent most likely to be stuck -- exactly this block's
    # target -- would spend all three slots on identical failure lines and lose
    # the history that shows it is stuck in the first place.
    _game, ada = _ada()
    _act(ada.agent, "I traveled to Cafe.", 0)
    _act(ada.agent, "I am grabbing coffee.", 60)
    for turn in (120, 180, 240):
        _act(ada.agent, 'I tried "get latte" but it didn\'t work: not here.', turn)
    got = recent_actions_block(ada.agent, 360, SimClock(START))
    assert got == (
        "Recently, you:\n"
        ' - 20 min ago: I tried "get latte" but it didn\'t work: not here.\n'
        " - 50 min ago: I am grabbing coffee.\n"
        " - 60 min ago: I traveled to Cafe."
    )


def test_block_collapses_whitespace_and_caps_length_in_record_text():
    # #826 review, minor 6: reflection.prompty's `read` variant embeds an
    # item's whole read_text verbatim -- authored world data of arbitrary
    # length that may carry a newline, which would deform this block's
    # one-line-per-action shape. Latent today (no Penn location authors
    # read_text), cheap to guard against here rather than at every author.
    _game, ada = _ada()
    # \r\n and a tab, not just \n: authored data carries every whitespace class,
    # and a bare \r breaks a rendered line just as a newline does.
    long_text = 'I read the flyer. It said: "' + ("x" * 300) + '\r\n\tmore"'
    _act(ada.agent, long_text, 0)
    got = recent_actions_block(ada.agent, 0, SimClock(START))
    assert len(got.splitlines()) == 2  # header + exactly one action line
    assert not (set("\r\n\t") & set(got.splitlines()[1]))
    action_line = got.splitlines()[1]
    assert len(action_line) <= len(" - just now: ") + RECENT_ACTION_TEXT_MAX


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
