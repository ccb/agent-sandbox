"""Offline tests for periodic reflection (issue #84, NEXT-STEPS Phase D).

Cover the engine's reflection seam end to end without a model:

* the salience threshold (:func:`reflection.should_reflect`),
* the orchestration flow (:func:`reflection.reflect`) -- questions -> retrieval
  -> inference -> write-back -> reset -- against a fake reflector,
* the deterministic :class:`reflection.MockReflector`,
* the :class:`reflection.LLMReflector` against a scripted fake client (the real
  model is the same ``call_tool`` seam), and
* the ReAct-loop wiring (:func:`npc.maybe_reflect`).

Run with::

    uv run pytest tests/test_reflection.py -v
"""

from text_adventure_games.memory import DEFAULT_MAX_RECORDS, AgentMemory, MemoryKind
from text_adventure_games.npc import maybe_reflect
from text_adventure_games.reflection import (
    DEFAULT_REFLECTION_THRESHOLD,
    INSIGHT_TOOL,
    SALIENT_QUESTIONS_TOOL,
    LLMReflector,
    MockReflector,
    Reflection,
    Reflector,
    reflect,
    should_reflect,
)

# --- helpers ----------------------------------------------------------------


def _stream(owner="Klaus", n=8, importance=4.0, actor="Maria"):
    """A memory stream of *n* observations, enough to cross the default threshold
    when ``n * importance >= 30``."""
    mem = AgentMemory(owner=owner)
    for i in range(n):
        mem.add_observation(
            f"{actor} talked about the library project (round {i})",
            turn=i,
            importance=importance,
            actor=actor,
        )
    return mem


class _FakeReflector:
    """Records the calls it gets and returns canned questions/inferences."""

    def __init__(self, questions, inference_text="They care about the library."):
        self._questions = questions
        self._inference_text = inference_text
        self.questions_calls = []
        self.infer_calls = []

    def salient_questions(self, records):
        self.questions_calls.append(list(records))
        return list(self._questions)

    def infer(self, question, records):
        self.infer_calls.append((question, list(records)))
        return Reflection(
            text=self._inference_text, evidence_ids=[r.id for r in records]
        )


# --- threshold --------------------------------------------------------------


def test_should_reflect_threshold():
    mem = AgentMemory()
    assert should_reflect(mem) is False  # empty stream, 0 accrued
    mem.add_observation("x", turn=0, importance=DEFAULT_REFLECTION_THRESHOLD - 1)
    assert should_reflect(mem) is False
    mem.add_observation("y", turn=0, importance=1)
    assert should_reflect(mem) is True  # exactly at threshold counts


def test_should_reflect_custom_threshold():
    mem = AgentMemory()
    mem.add_observation("x", turn=0, importance=5)
    assert should_reflect(mem, threshold=5) is True
    assert should_reflect(mem, threshold=6) is False


# --- orchestration ----------------------------------------------------------


def test_reflect_creates_reflections_with_evidence():
    mem = _stream()
    reflector = _FakeReflector(["What should I make of Maria?"])
    created = reflect(mem, reflector, turn=8)

    assert len(created) == 1
    record = created[0]
    assert record.kind is MemoryKind.REFLECTION
    assert record.text == "They care about the library."
    # The cited evidence ids are stored on the reflection record.
    assert record.source_event_ids  # non-empty
    assert record in mem.records  # appended to the stream


def test_reflect_resets_accumulator():
    mem = _stream()
    assert mem.importance_since_reflection >= DEFAULT_REFLECTION_THRESHOLD
    reflect(mem, _FakeReflector(["Q?"]), turn=8)
    # Reset to 0 even though add_reflection itself accrued importance.
    assert mem.importance_since_reflection == 0.0


def test_reflect_caps_questions():
    mem = _stream()
    reflector = _FakeReflector(["Q1?", "Q2?", "Q3?", "Q4?", "Q5?"])
    reflect(mem, reflector, turn=8, max_questions=2)
    assert len(reflector.infer_calls) == 2


def test_reflect_empty_stream_is_noop_but_resets():
    mem = AgentMemory()
    mem.importance_since_reflection = 99.0  # pretend salience accrued elsewhere
    created = reflect(mem, _FakeReflector(["Q?"]), turn=0)
    assert created == []
    assert mem.importance_since_reflection == 0.0


def test_reflect_no_questions_is_noop():
    # A reflector that surfaces no salient questions produces no reflections and
    # never reaches the inference step -- but still resets the accumulator.
    mem = _stream()
    reflector = _FakeReflector([])  # no questions
    created = reflect(mem, reflector, turn=8)
    assert created == []
    assert reflector.infer_calls == []
    assert mem.importance_since_reflection == 0.0


def test_reflect_filters_blank_questions():
    # Blank / falsy questions are dropped before retrieval + inference.
    mem = _stream()
    reflector = _FakeReflector(["", None, "What should I make of Maria?"])
    reflect(mem, reflector, turn=8)
    assert [q for q, _ in reflector.infer_calls] == ["What should I make of Maria?"]


def test_reflect_retrieval_is_read_only():
    # Reflecting must not bump recency: a record's last_accessed_turn is unchanged
    # by the (touch=False) supporting retrieval the reflection pass does.
    mem = _stream()
    before = [r.last_accessed_turn for r in mem.records]
    reflect(mem, _FakeReflector(["What should I make of Maria?"]), turn=100)
    after = [r.last_accessed_turn for r in mem.records[: len(before)]]
    assert after == before


def test_reflect_drops_empty_inference():
    mem = _stream()

    class _BlankReflector(_FakeReflector):
        def infer(self, question, records):
            return Reflection(text="   ")  # whitespace only -> dropped

    created = reflect(mem, _BlankReflector(["Q?"]), turn=8)
    assert created == []


# --- plan memories are intentions, not experience (issue #777) ---------------


def test_reflection_input_excludes_plan_memories():
    # Regression for #777: the t0 day-plan (and #778's conversation commitments)
    # land in the stream as PLAN records -- *intentions*, not lived experience.
    # Shown to the reflector, they let an agent "conclude" things about stops it
    # has not reached (Sofia reflected on her scheduled dinner queasiness at
    # 08:27, mid-stop-0). Neither the question seed nor the per-question
    # supporting retrieval may put a plan record in front of the reflector.
    mem = _stream()
    mem.add_plan(
        "Plan: settle in for dinner with Maria at the hall, then head home",
        turn=8,
        importance=8.0,
    )
    reflector = _FakeReflector(["What should I make of Maria?"])
    reflect(mem, reflector, turn=9)

    shown = [r for call in reflector.questions_calls for r in call] + [
        r for _, records in reflector.infer_calls for r in records
    ]
    assert shown  # the pass really ran over records
    assert all(r.kind is not MemoryKind.PLAN for r in shown)


def test_plan_records_do_not_shrink_the_supporting_set():
    # #805 review: plans must be excluded *inside* retrieval (slots backfilled),
    # not stripped from its top-k output. Eight importance-8.0 commitments (the
    # #778 stream shape) out-rank every observation, so a post-filter hands the
    # reflector an empty supporting set and the pass silently goes dark; with
    # the ranking-side filter the observations fill all max_records slots.
    mem = _stream()
    for i in range(8):
        mem.add_plan(f"Plan: stop {i} with Maria", turn=8, importance=8.0)
    reflector = _FakeReflector(["What should I make of Maria?"])
    created = reflect(mem, reflector, turn=9)

    assert created  # the pass still produces a reflection
    (_, supporting), *_ = reflector.infer_calls
    assert len(supporting) == DEFAULT_MAX_RECORDS  # full width, no lost slots
    assert all(r.kind is not MemoryKind.PLAN for r in supporting)


def test_plan_records_do_not_shrink_the_seed_window():
    # Same shape for the question seed: filter, then slice. Plans clustered at
    # the stream's tail must not eat the window -- older lived records backfill
    # it, so the reflector still sees recent_window records.
    mem = _stream(n=3)
    for i in range(4):
        mem.add_plan(f"Plan: stop {i}", turn=3, importance=8.0)
    reflector = _FakeReflector(["What should I make of Maria?"])
    created = reflect(mem, reflector, turn=4, recent_window=4)

    assert created  # slice-then-filter left an empty seed and no reflection
    (seed,) = reflector.questions_calls
    assert [r.kind for r in seed] == [MemoryKind.OBSERVATION] * 3


def test_reflection_never_cites_an_unlived_plan_stop():
    # The live-run shape from #777: the ONLY mention of the day's distinctive
    # final stop is the plan record itself. MockReflector.infer summarizes the
    # records it is shown, so if the plan leaks into the supporting set, its
    # text leaks straight into the written reflection.
    mem = _stream()
    mem.add_plan(
        "Today's stops end with feeling queasy at dinner with Maria",
        turn=8,
        importance=8.0,
    )
    created = reflect(mem, MockReflector(), turn=9)
    assert created  # observations alone still yield a reflection
    assert all("queasy" not in r.text for r in created)


# --- MockReflector ----------------------------------------------------------


def test_mock_reflector_satisfies_protocol():
    assert isinstance(MockReflector(), Reflector)


def test_mock_reflector_questions_key_off_actors():
    mem = _stream(actor="Maria")
    questions = MockReflector().salient_questions(mem.records)
    assert questions == ["What should I make of Maria?"]


def test_mock_reflector_question_without_actors():
    mem = AgentMemory()
    mem.add_observation("the bell rang", turn=0, importance=2)  # no actor
    questions = MockReflector().salient_questions(mem.records)
    assert len(questions) == 1
    assert "?" in questions[0]


def test_mock_reflector_is_deterministic_end_to_end():
    created_a = reflect(_stream(), MockReflector(), turn=8)
    created_b = reflect(_stream(), MockReflector(), turn=8)
    assert [r.text for r in created_a] == [r.text for r in created_b]
    assert created_a and created_a[0].kind is MemoryKind.REFLECTION


# --- LLMReflector (scripted client) -----------------------------------------


class _ScriptedClient:
    """A fake ``LlmClient`` returning canned tool arguments by tool name
    (mirrors ``tests/test_planner.py``)."""

    def __init__(self, by_tool):
        self.by_tool = by_tool
        self.calls = []
        self.user_by_tool = {}

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append(tool["name"])
        self.user_by_tool[tool["name"]] = messages[-1]["content"] if messages else ""
        return self.by_tool.get(tool["name"])

    def chat(self, *args, **kwargs):
        return None

    def count_tokens(self, text):
        return len(text.split())


def test_llm_reflector_questions_and_inference():
    client = _ScriptedClient(
        {
            SALIENT_QUESTIONS_TOOL["name"]: {
                "questions": ["What should I make of Maria?", "  ", 5]
            },
            INSIGHT_TOOL["name"]: {
                "insight": "Maria is passionate about the library project.",
                "evidence": [1, 3],
            },
        }
    )
    reflector = LLMReflector(client)
    mem = _stream()

    questions = reflector.salient_questions(mem.records)
    assert questions == ["What should I make of Maria?"]  # blanks/non-strings dropped

    supporting = mem.records[:4]
    result = reflector.infer("What should I make of Maria?", supporting)
    assert result is not None
    assert result.text == "Maria is passionate about the library project."
    # Citations 1 and 3 map to the 1st and 3rd supporting records' ids.
    assert result.evidence_ids == [supporting[0].id, supporting[2].id]


def test_llm_reflector_full_flow_writes_back():
    client = _ScriptedClient(
        {
            SALIENT_QUESTIONS_TOOL["name"]: {"questions": ["What about Maria?"]},
            INSIGHT_TOOL["name"]: {"insight": "Maria values the library."},
        }
    )
    mem = _stream()
    created = reflect(mem, LLMReflector(client), turn=8)
    assert [r.text for r in created] == ["Maria values the library."]
    # No evidence cited -> falls back to citing every supporting record.
    assert created[0].source_event_ids


def test_llm_reflector_robust_to_malformed_results():
    # Missing tool result entirely (client returns None) -> degrade, never raise.
    reflector = LLMReflector(_ScriptedClient({}))
    mem = _stream()
    assert reflector.salient_questions(mem.records) == []
    assert reflector.infer("Q?", mem.records[:2]) is None
    # And a full pass over a dead client simply adds nothing.
    assert reflect(mem, reflector, turn=8) == []


def test_llm_reflector_drops_out_of_range_evidence():
    client = _ScriptedClient(
        {
            INSIGHT_TOOL["name"]: {
                "insight": "An insight.",
                # Items arrive schema-validated as ints now (#357), so the only
                # cases left are in-range vs out-of-range; 99 exceeds the 3
                # supporting records and is dropped by the semantic mapping.
                "evidence": [1, 2, 99],
            }
        }
    )
    supporting = _stream().records[:3]
    result = LLMReflector(client).infer("Q?", supporting)
    assert result.evidence_ids == [supporting[0].id, supporting[1].id]


def test_llm_reflector_infer_no_records_is_none():
    assert LLMReflector(_ScriptedClient({})).infer("Q?", []) is None


# --- ReAct-loop wiring (npc.maybe_reflect) ----------------------------------


class _FakeParser:
    def __init__(self):
        self.reflections = []

    def agent_reflection(self, owner, text):
        self.reflections.append((owner, text))


class _FakeGame:
    def __init__(self, turn):
        self.turn = turn
        self.parser = _FakeParser()


class _FakeAgent:
    """Minimal stand-in exposing the attributes maybe_reflect reads."""

    def __init__(self, memory, reflector, threshold=DEFAULT_REFLECTION_THRESHOLD):
        self.memory = memory
        self.reflector = reflector
        self.reflection_threshold = threshold


def test_maybe_reflect_noop_without_reflector():
    agent = _FakeAgent(_stream(), reflector=None)
    game = _FakeGame(turn=8)
    assert maybe_reflect(agent, game) == []
    assert game.parser.reflections == []


def test_maybe_reflect_noop_below_threshold():
    mem = AgentMemory(owner="Klaus")
    mem.add_observation("a quiet morning", turn=0, importance=2)  # below 30
    agent = _FakeAgent(mem, reflector=MockReflector())
    assert maybe_reflect(agent, _FakeGame(turn=1)) == []


def test_maybe_reflect_fires_and_traces_when_due():
    agent = _FakeAgent(_stream(), reflector=MockReflector())
    game = _FakeGame(turn=8)
    created = maybe_reflect(agent, game)
    assert created  # reflection(s) produced
    # Each new thought is traced on the private AGENT_REFLECTION channel.
    assert game.parser.reflections
    assert all(owner == "Klaus" for owner, _ in game.parser.reflections)
    # And the accumulator reset, so an immediate second call is a no-op.
    assert maybe_reflect(agent, game) == []
