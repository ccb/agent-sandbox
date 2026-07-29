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

from types import SimpleNamespace

from text_adventure_games.memory import AgentMemory, MemoryKind
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


# --- temporal provenance (issues #777 / #815) -------------------------------


def test_reflection_input_includes_plan_memories():
    # #815 re-admits plans so the model can reason forward over intentions.
    mem = _stream()
    plan = mem.add_plan(
        "Plan: settle in for dinner with Maria at the hall, then head home",
        turn=8,
        importance=8.0,
    )
    reflector = _FakeReflector(["What are my dinner intentions with Maria?"])
    reflect(mem, reflector, turn=9)

    (seed,) = reflector.questions_calls
    (_, supporting), *_ = reflector.infer_calls
    assert plan in seed
    assert plan in supporting


def test_plan_only_stream_can_reflect():
    mem = AgentMemory()
    plan = mem.add_plan(
        "Plan: visit Maria at the hall tomorrow",
        turn=0,
        importance=DEFAULT_REFLECTION_THRESHOLD,
    )
    reflector = _FakeReflector(["What do I intend to do with Maria?"])

    assert should_reflect(mem)
    created = reflect(mem, reflector, turn=1)

    assert created
    assert reflector.questions_calls == [[plan]]
    assert reflector.infer_calls[0][1] == [plan]


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


def test_mock_reflector_preserves_plan_as_intention_without_prompt_markers():
    mem = AgentMemory()
    plan = mem.add_plan("visit Maria tomorrow", turn=0, importance=8.0)

    result = MockReflector().infer("What comes next?", [plan])

    assert result is not None
    assert "intended: visit Maria tomorrow" in result.text
    assert "[intended]" not in result.text


# --- LLMReflector (scripted client) -----------------------------------------


class _ScriptedClient:
    """A fake ``LlmClient`` returning canned tool arguments by tool name
    (mirrors ``tests/test_planner.py``)."""

    def __init__(self, by_tool):
        self.by_tool = by_tool
        self.calls = []
        self.user_by_tool = {}
        self.messages_by_tool = {}

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append(tool["name"])
        self.user_by_tool[tool["name"]] = messages[-1]["content"] if messages else ""
        self.messages_by_tool[tool["name"]] = list(messages)
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


def test_llm_reflector_numbers_records_with_temporal_provenance():
    mem = AgentMemory()
    records = [
        mem.add_observation("I attended the lecture.", turn=0),
        mem.add_chat("Professor Tanaka invited me to office hours.", turn=1),
        mem.add_reflection("Professor Tanaka seems supportive.", turn=2),
        mem.add_plan("Visit office hours tomorrow.", turn=3),
        SimpleNamespace(text="legacy record with no kind"),
        SimpleNamespace(text="record from a future kind", kind="dream"),
    ]

    assert LLMReflector._numbered(records) == (
        "1. [lived] I attended the lecture.\n"
        "2. [conversation] Professor Tanaka invited me to office hours.\n"
        "3. [inferred] Professor Tanaka seems supportive.\n"
        "4. [intended] Visit office hours tomorrow.\n"
        "5. [lived] legacy record with no kind\n"
        "6. [memory] record from a future kind"
    )


class _TemporalContractClient:
    """A deterministic stand-in that exposes whether #815's prompt contract
    distinguishes a future invitation from a completed office-hours visit."""

    def __init__(self):
        self.messages_by_tool = {}

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        name = tool["name"]
        self.messages_by_tool[name] = list(messages)
        if name == SALIENT_QUESTIONS_TOOL["name"]:
            return {"questions": ["What happened with Professor Tanaka's invitation?"]}
        if name == INSIGHT_TOOL["name"]:
            system = messages[0]["content"]
            user = messages[-1]["content"]
            contract_present = (
                "[conversation]" in user
                and "Never treat a future event" in system
                and "unless a [lived] record explicitly confirms it" in system
            )
            if contract_present:
                return {
                    "insight": (
                        "Professor Tanaka invited me to office hours; the visit "
                        "has not been established as completed."
                    ),
                    "evidence": [1],
                }
            return {
                "insight": "I visited Professor Tanaka during office hours.",
                "evidence": [1],
            }
        return None


def test_chat_invitation_is_not_reflected_as_a_completed_visit():
    # Verbatim relationship note from the R9 cassette cited by #815. It is a
    # CHAT record even though it contains a future invitation.
    mem = AgentMemory()
    note = mem.add_chat(
        "Professor Tanaka is welcoming and passionate about physics, especially "
        "gravitational waves. He invited me to visit his office hours if I have "
        "questions after the lecture. He also mentioned the Kamin Gallery as "
        "worth checking out. He seems like a great resource for learning more "
        "about the topics that interest me.",
        turn=0,
        importance=8.0,
        partner="Professor Tanaka",
    )
    client = _TemporalContractClient()

    created = reflect(mem, LLMReflector(client), turn=1)

    assert created
    assert "invited me to office hours" in created[0].text
    assert "I visited" not in created[0].text
    infer_user = client.messages_by_tool[INSIGHT_TOOL["name"]][-1]["content"]
    assert f"1. [conversation] {note.text}" in infer_user


def test_llm_reflector_strips_echoed_prompt_markers_from_insight():
    client = _ScriptedClient(
        {
            SALIENT_QUESTIONS_TOOL["name"]: {"questions": ["What do I intend?"]},
            INSIGHT_TOOL["name"]: {
                "insight": (
                    "[inferred] I remain [intended] to visit after the "
                    "[conversation] invitation."
                ),
                "evidence": [1],
            },
        }
    )
    mem = _stream()

    created = reflect(mem, LLMReflector(client), turn=8)

    assert created
    assert created[0].text == "I remain to visit after the invitation."
    assert "[" not in created[0].text and "]" not in created[0].text


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
