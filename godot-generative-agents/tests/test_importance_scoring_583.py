"""LLM-scored memory importance / poignancy (issue #583).

A backend-side scoring pass replaces the hardcoded importance constants with
model-scored 1-10 poignancy, batched into one call per agent-tick, with the
constants as the fallback floor and a hard no-op for the mock brain.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_importance_scoring_583.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_conversation_consequences_582.py: the Penn sim modules
# run as scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.prompt_templates import render  # noqa: E402
from backend import cognition  # noqa: E402
from text_adventure_games.memory import AgentMemory  # noqa: E402
from text_adventure_games.reflection import (  # noqa: E402
    DEFAULT_REFLECTION_THRESHOLD,
    should_reflect,
)
from text_adventure_games.things import Character  # noqa: E402


class _ScoreBrain:
    """A real-shaped brain: answers one score_memories call with a scripted dict
    and records the tools it was asked for (to assert the batch is ONE call)."""

    def __init__(self, result):
        self._result = result
        self.context: dict = {}
        self.tools_called: list[str] = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.tools_called.append(tool["name"])
        return self._result


def _char_with(brain, *, mock=False):
    """A bare LLMAgent-shaped stub carrying just what score_new_memories reads.

    ``mock=True`` makes the brain identity-equal to agent.schedule, reproducing
    the mock-brain wiring (attach_agents sets brain = schedule when no client is
    supplied), so the scorer must self-gate to a no-op.
    """
    char = Character("Maria Lopez", "Maria", "")
    agent = type("A", (), {})()
    agent.llm_client = brain
    agent.schedule = brain if mock else object()
    agent.max_tokens = 256
    agent.memory = AgentMemory(owner=char.name)
    agent._structured_system_message = lambda: "You are Maria Lopez."
    char.set_agent(agent)
    return char


def test_tool_schema_shape():
    tool = cognition.IMPORTANCE_SCORE_TOOL
    assert tool["name"] == "score_memories"
    scores = tool["parameters"]["properties"]["scores"]
    assert scores["type"] == "array"
    item = scores["items"]
    assert set(item["properties"]) == {"id", "score"}
    assert item["required"] == ["id", "score"]
    assert tool["parameters"]["required"] == ["scores"]


def test_scored_records_carry_the_models_numbers_in_one_call():
    brain = _ScoreBrain({"scores": [{"id": 0, "score": 9}, {"id": 1, "score": 3}]})
    char = _char_with(brain)
    char.agent.memory.add_observation("I traveled to the Cafe.", turn=1, importance=2.0)
    char.agent.memory.add_observation("I saw Ayesha nearby.", turn=1, importance=1.0)

    cognition.score_new_memories(char, step=1)

    recs = char.agent.memory.records
    assert [r.importance for r in recs] == [9.0, 3.0]  # model's numbers, not 2/1
    assert brain.tools_called == ["score_memories"]  # exactly one batched call
    assert brain.context["role"] == "score"  # ledger role stamped


def test_malformed_reply_falls_back_to_the_constants():
    # A non-dict reply and a dict missing "scores" both leave the constants intact
    # and DON'T mark records scored (so a transient failure retries next decide).
    for bad in (None, "oops", {"nope": []}):
        brain = _ScoreBrain(bad)
        char = _char_with(brain)
        char.agent.memory.add_observation("I did wait.", turn=1, importance=2.0)
        cognition.score_new_memories(char, step=1)
        rec = char.agent.memory.records[0]
        assert rec.importance == 2.0  # floor stands
        assert not rec.metadata.get(cognition._IMPORTANCE_SCORED)  # will retry


def test_out_of_range_scores_are_clamped_and_omitted_ids_keep_the_floor():
    # id 0 over-range -> clamped to 10; id 1 omitted by the model -> constant kept
    # but still marked scored (we asked; don't re-ask).
    brain = _ScoreBrain({"scores": [{"id": 0, "score": 99}]})
    char = _char_with(brain)
    char.agent.memory.add_observation("Momentous thing.", turn=1, importance=2.0)
    char.agent.memory.add_observation("Filler.", turn=1, importance=1.0)

    cognition.score_new_memories(char, step=1)

    recs = char.agent.memory.records
    assert recs[0].importance == 10.0  # clamped
    assert recs[1].importance == 1.0  # omitted -> floor
    assert all(r.metadata.get(cognition._IMPORTANCE_SCORED) for r in recs)


def test_boolean_id_does_not_collide_with_real_id_1():
    # bool is an int subclass and True == 1 with the same hash, so a {"id": true}
    # entry must be rejected -- not silently applied to the record whose real id
    # is 1. Only a boolean entry is sent, so under the bug by_id[True]=9 would
    # score record 1 to 9.0; the fix leaves it at its floor.
    brain = _ScoreBrain({"scores": [{"id": True, "score": 9}]})
    char = _char_with(brain)
    char.agent.memory.add_observation("id 0.", turn=1, importance=2.0)  # id 0
    char.agent.memory.add_observation("id 1.", turn=1, importance=2.0)  # id 1

    cognition.score_new_memories(char, step=1)

    assert char.agent.memory.records[1].importance == 2.0  # floor, not the bogus 9


def test_locked_records_are_never_scored():
    # A ground-truth record (e.g. the #300 sickness signal) carries the lock flag;
    # the scorer must skip it entirely and never send it to the model.
    brain = _ScoreBrain({"scores": [{"id": 0, "score": 1}, {"id": 1, "score": 1}]})
    char = _char_with(brain)
    locked = char.agent.memory.add_observation("I got sick.", turn=1, importance=8.0)
    locked.metadata[cognition._IMPORTANCE_LOCKED] = True
    char.agent.memory.add_observation("I traveled.", turn=1, importance=2.0)

    cognition.score_new_memories(char, step=1)

    assert char.agent.memory.records[0].importance == 8.0  # untouched
    assert char.agent.memory.records[1].importance == 1.0  # scored


def test_mock_brain_is_a_no_op():
    # brain IS agent.schedule (the mock wiring). The scorer must not call and must
    # leave importances at their constants -> the bake stays byte-identical.
    brain = _ScoreBrain({"scores": [{"id": 0, "score": 10}]})
    char = _char_with(brain, mock=True)
    char.agent.memory.add_observation("I traveled.", turn=1, importance=2.0)

    cognition.score_new_memories(char, step=1)

    assert brain.tools_called == []  # never called
    assert char.agent.memory.records[0].importance == 2.0  # constant untouched


def test_reflection_fires_on_scored_importance_not_a_fixed_count():
    # Four mundane observations (constant 2.0 each = 8.0) sit well under the 30.0
    # reflection threshold. Scoring them momentous (9 each) pushes the accumulator
    # over the threshold -> reflection becomes due on *scored* salience.
    brain = _ScoreBrain({"scores": [{"id": i, "score": 9} for i in range(4)]})
    char = _char_with(brain)
    for _ in range(4):
        char.agent.memory.add_observation("A small thing.", turn=1, importance=2.0)
    memory = char.agent.memory

    assert memory.importance_since_reflection == 8.0
    assert not should_reflect(memory, DEFAULT_REFLECTION_THRESHOLD)  # 8 < 30

    cognition.score_new_memories(char, step=1)

    # Accumulator adjusted by the deltas: 8.0 + 4*(9-2) = 36.0
    assert memory.importance_since_reflection == 36.0
    assert should_reflect(memory, DEFAULT_REFLECTION_THRESHOLD)  # 36 >= 30


def test_importance_score_prompt_renders_the_batch():
    # Pin the exact rendered output (repo convention: prompt renders are pinned
    # verbatim, like test_conversation_consequences_582 / test_decide_context), so
    # a reworded template can't drift past a substring check.
    text = render(
        "importance_score",
        memories=[
            {"id": 0, "text": "I traveled to the Cafe."},
            {"id": 1, "text": "I saw Ayesha nearby."},
        ],
    )
    assert text == (
        "Rate how significant each of these memories is to you, from 1 "
        "(mundane) to 10 (momentous):\n"
        "\n"
        "[0] I traveled to the Cafe.\n"
        "[1] I saw Ayesha nearby.\n"
        "\n"
        "Then call score_memories with a 1-10 score for every id above."
    )


def test_remember_outcome_locks_the_sickness_signal():
    # The #300 drink outcome is ground truth the model can't see from text, so
    # remember_outcome must flag it locked -> the scorer skips it. The sick branch
    # renders from the drunk item (not the location), so a bare char + the
    # just_sickened property is enough -- no world build needed.
    char = _char_with(_ScoreBrain({"scores": []}))
    char.set_property("just_sickened", True)  # just_recovered defaults False

    cognition.remember_outcome(char, "drink water", step=1)

    rec = char.agent.memory.records[-1]
    assert rec.importance == 8.0
    assert rec.metadata.get(cognition._IMPORTANCE_LOCKED) is True


def test_relationship_note_is_locked():
    # The #582 relationship note (8.0) is a deliberate signal; lock it so the
    # scorer can't re-guess it down.
    from text_adventure_games.memory import MemoryKind
    from text_adventure_games.planning import DailyPlan, Stop

    class _NoteBrain:
        context: dict = {}

        def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
            return {"plans_changed": False, "relationship_note": "A dear friend."}

    class _Planner:
        def generate(self, persona=None, memory=None, clock=None):
            return DailyPlan(stops=[Stop(place="Cafe", activity="reading", steps=5)])

        def revise(self, plan, trigger=None, memory=None, clock=None):
            return plan

    char = _char_with(_NoteBrain())
    char.agent.planner = _Planner()
    char.agent.plan = char.agent.planner.generate()

    cognition.apply_conversation_outcome(char, "Ayesha Khan", "t", step=2)

    notes = [r for r in char.agent.memory.records if r.kind == MemoryKind.CHAT]
    assert len(notes) == 1
    assert notes[0].metadata.get(cognition._IMPORTANCE_LOCKED) is True


def test_step_loop_scores_between_outcome_and_reflect():
    # The step loop imports score_new_memories and calls it in the resolve block,
    # ordered remember_outcome ... score_new_memories ... maybe_reflect.
    import backend.run_simulation as rs

    assert hasattr(rs, "score_new_memories")
    src = Path(rs.__file__).read_text()
    i_outcome = src.index("remember_outcome(char, command, step_idx)")
    i_score = src.index("score_new_memories(char, step_idx)")
    i_reflect = src.index("maybe_reflect(char.agent, game)")
    assert i_outcome < i_score < i_reflect


def test_reflection_and_plan_records_are_not_rescored():
    # Regression (final review): the scorer targets OBSERVATION/CHAT only.
    # reflect() zeroes importance_since_reflection after appending REFLECTION
    # records, so re-scoring a reflection (or a PLAN) on a later tick would leak
    # its delta into the fresh window and skew reflection cadence.
    brain = _ScoreBrain(
        {
            "scores": [
                {"id": 0, "score": 10},
                {"id": 1, "score": 10},
                {"id": 2, "score": 10},
            ]
        }
    )
    char = _char_with(brain)
    mem = char.agent.memory
    obs = mem.add_observation("I traveled.", turn=1, importance=2.0)  # id 0
    refl = mem.add_reflection("Life is good.", turn=1, importance=6.0)  # id 1
    plan = mem.add_plan("Go to the cafe.", turn=1, importance=5.0)  # id 2
    mem.importance_since_reflection = 0.0  # simulate a reflect() reset

    cognition.score_new_memories(char, step=1)

    assert obs.importance == 10.0  # observation re-scored
    assert refl.importance == 6.0  # reflection untouched
    assert plan.importance == 5.0  # plan untouched
    # Accumulator moved only by the observation delta (10 - 2 = 8), not by the
    # reflection/plan (which would have leaked 10-6 and 10-5 into a reset window).
    assert mem.importance_since_reflection == 8.0
