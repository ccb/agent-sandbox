"""Bounded importance-scoring retries (issue #759).

#583/#647's scorer deliberately keeps no cursor, so a malformed reply retries
next tick -- but unbounded, a persistently failing brain (gap 1) or a brain
that never answers score_memories at all (gap 2, --brain scripted) re-sent an
ever-growing batch every tick. Two bounds fix that: at most SCORE_BATCH_MAX
records per send, and retirement at the constant floor after
SCORE_MAX_ATTEMPTS failed sends -- while a recovery before retirement still
scores the whole backlog.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_scoring_batch_bound_759.py -v
"""

import math
import re
import sys
from pathlib import Path

# Same import shim as test_importance_scoring_583.py: the Penn sim modules run
# as scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend import cognition  # noqa: E402
from scripted_brain import build_scripted_brains  # noqa: E402
from text_adventure_games.memory import AgentMemory  # noqa: E402
from text_adventure_games.things import Character  # noqa: E402


def _batch_size(messages) -> int:
    """How many memories rode this send: one rendered "[id] text" line each."""
    content = messages[-1]["content"]
    return len(re.findall(r"^\[\d+\] ", content, flags=re.M))


class _FlakyBrain:
    """A real-shaped brain whose reply is settable per tick (fail -> recover).

    ``result`` may be a fixed value (None simulates the persistent failure) or
    the string "echo", which scores every id the prompt lists to 9 -- the
    shape a recovered real brain produces. Records each send's batch size so
    tests can assert the batch stays bounded.
    """

    def __init__(self, result=None):
        self.result = result
        self.context: dict = {}
        self.batch_sizes: list[int] = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.batch_sizes.append(_batch_size(messages))
        if self.result == "echo":
            ids = re.findall(r"^\[(\d+)\] ", messages[-1]["content"], flags=re.M)
            return {"scores": [{"id": int(i), "score": 9} for i in ids]}
        return self.result


def _char_with(brain):
    """The test_importance_scoring_583 stub: a bare LLMAgent-shaped carrier."""
    char = Character("Maria Lopez", "Maria", "")
    agent = type("A", (), {})()
    agent.llm_client = brain
    agent.schedule = object()  # distinct from the brain -> the identity gate opens
    agent.max_tokens = 256
    agent.memory = AgentMemory(owner=char.name)
    agent._structured_system_message = lambda: "You are Maria Lopez."
    char.set_agent(agent)
    return char


def test_persistent_failure_caps_the_batch_and_retires_records():
    # Gap 1: a backlog well past the cap, against a brain that always fails.
    # Every send must stay <= SCORE_BATCH_MAX, each record rides at most
    # SCORE_MAX_ATTEMPTS sends, and once everything is retired the scorer goes
    # quiet -- instead of re-sending a batch that grows by the tick.
    n = 2 * cognition.SCORE_BATCH_MAX + 10
    brain = _FlakyBrain(None)
    char = _char_with(brain)
    for i in range(n):
        char.agent.memory.add_observation(f"thing {i}.", turn=1, importance=2.0)

    for step in range(20):  # well past full retirement
        cognition.score_new_memories(char, step=step)

    # Bounded: no send ever exceeded the cap (per-tick token cost stays flat).
    assert brain.batch_sizes, "the scorer never sent anything"
    assert max(brain.batch_sizes) <= cognition.SCORE_BATCH_MAX
    # Each cap-sized group rides SCORE_MAX_ATTEMPTS sends, then retires.
    expected = math.ceil(n / cognition.SCORE_BATCH_MAX) * cognition.SCORE_MAX_ATTEMPTS
    assert len(brain.batch_sizes) == expected
    # Retired at the constant floor, marked scored -- never asked again.
    recs = char.agent.memory.records
    assert all(r.importance == 2.0 for r in recs)
    assert all(r.metadata.get(cognition._IMPORTANCE_SCORED) for r in recs)


def test_transient_failure_still_retries_then_scores_the_backlog():
    # The retry-on-malformed intent (#647) survives the bounds: two failures sit
    # under SCORE_MAX_ATTEMPTS, so the third tick's recovery scores everything.
    assert cognition.SCORE_MAX_ATTEMPTS > 2  # the premise of this test
    brain = _FlakyBrain(None)
    char = _char_with(brain)
    for i in range(3):
        char.agent.memory.add_observation(f"thing {i}.", turn=1, importance=2.0)

    cognition.score_new_memories(char, step=1)  # fails
    cognition.score_new_memories(char, step=2)  # fails
    brain.result = "echo"  # recovers
    cognition.score_new_memories(char, step=3)

    assert brain.batch_sizes == [3, 3, 3]  # retried, never grew
    assert [r.importance for r in char.agent.memory.records] == [9.0, 9.0, 9.0]


def test_backlog_larger_than_the_cap_drains_across_ticks():
    # A healthy brain facing an over-cap backlog scores it cap-sized batch by
    # batch: everything still gets scored, just across successive ticks.
    n = cognition.SCORE_BATCH_MAX + 5
    brain = _FlakyBrain("echo")
    char = _char_with(brain)
    for i in range(n):
        char.agent.memory.add_observation(f"thing {i}.", turn=1, importance=2.0)

    cognition.score_new_memories(char, step=1)
    assert brain.batch_sizes == [cognition.SCORE_BATCH_MAX]
    cognition.score_new_memories(char, step=2)
    assert brain.batch_sizes == [cognition.SCORE_BATCH_MAX, 5]

    assert all(r.importance == 9.0 for r in char.agent.memory.records)


def test_retired_records_never_ride_again_but_new_memories_score():
    # After retirement the pipeline isn't wedged: a later recovery scores new
    # memories, and the retired record neither rides the send nor re-scores.
    brain = _FlakyBrain(None)
    char = _char_with(brain)
    char.agent.memory.add_observation("stuck thing.", turn=1, importance=2.0)

    for step in range(cognition.SCORE_MAX_ATTEMPTS + 1):  # fail to retirement
        cognition.score_new_memories(char, step=step)
    assert len(brain.batch_sizes) == cognition.SCORE_MAX_ATTEMPTS

    brain.result = "echo"
    char.agent.memory.add_observation("new thing.", turn=9, importance=2.0)
    cognition.score_new_memories(char, step=9)

    assert brain.batch_sizes[-1] == 1  # only the new record rode
    recs = char.agent.memory.records
    assert recs[0].importance == 2.0  # retired: constant floor stands
    assert recs[1].importance == 9.0  # new memory scored


def test_scripted_brain_answers_score_memories():
    # Gap 2 at the root (#647's documented follow-up): the scripted brain now
    # answers the scorer with the schema-valid "no overrides" instead of None.
    brain, _reflector = build_scripted_brains()
    result = brain.call_tool(
        [{"role": "user", "content": "[0] thing."}], cognition.IMPORTANCE_SCORE_TOOL
    )
    assert result == {"scores": []}


def test_scripted_brain_clears_the_batch_in_one_ask():
    # End-to-end shape of gap 2: under the scripted brain the batch clears on
    # the first ask (records keep their constant floors but are marked scored),
    # so the second tick sends nothing -- previously the same batch re-sent,
    # one record larger, every tick.
    brain, _reflector = build_scripted_brains()
    char = _char_with(brain)
    char.agent.memory.add_observation("I traveled.", turn=1, importance=2.0)
    char.agent.memory.add_observation("I saw Ayesha.", turn=1, importance=1.0)

    cognition.score_new_memories(char, step=1)
    cognition.score_new_memories(char, step=2)

    score_asks = [c for c in brain.tool_calls if c["tool"]["name"] == "score_memories"]
    assert len(score_asks) == 1  # asked once, cleared, never re-sent
    recs = char.agent.memory.records
    assert [r.importance for r in recs] == [2.0, 1.0]  # floors untouched
    assert all(r.metadata.get(cognition._IMPORTANCE_SCORED) for r in recs)
