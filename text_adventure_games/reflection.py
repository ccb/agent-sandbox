"""Periodic reflection: synthesize recent memories into higher-level thoughts.

issue #84, NEXT-STEPS Phase D.

Raw observations give an agent *continuity* ("on turn 3 the player gave me a
fish"); reflection gives it *generalization* ("the player seems friendly"). The
Generative Agents paper (Park et al., 2023) periodically turns a window of recent
memories into a few higher-level inferences and writes them *back* into the
memory stream, where retrieval can surface them like any other memory. This
module is that step.

It is deliberately **distinct from the Reflect step in ``npc.py``** (issue #4):
that one reflects on a single command *failure* to pick a better next action.
This is *periodic memory synthesis* -- it fires on a cadence (when accumulated
importance crosses a threshold; see :func:`should_reflect`) and reasons over the
whole recent stream, not one failed command.

Following the same restraint as ``memory.py`` and ``planning.py``, this module is
**pure orchestration with no engine imports**: it reads and writes an
``AgentMemory`` purely through its public API (``records`` /
``importance_since_reflection`` / :meth:`~text_adventure_games.memory.AgentMemory.
retrieve` / :meth:`~text_adventure_games.memory.AgentMemory.add_reflection`) by
duck typing, so it unit-tests offline and reads easily. The *cognition* that
proposes questions and inferences lives behind the :class:`Reflector` protocol --
a deterministic :class:`MockReflector` for offline/CI runs, an
:class:`LLMReflector` for live runs -- exactly mirroring how ``planning.py`` pairs
a ``Planner`` protocol with a mock and an LLM implementation, and how
``llm_client.py`` pairs ``LlmClient`` with ``MockReActClient``.

Design invariant, inherited from ``memory.py``: **reflection only ever appends.**
A reflection is a new ``MemoryKind.REFLECTION`` record citing the memories it
rests on; nothing is edited or evicted (that subtractive "dreaming" / compaction
angle is a separate, later capability -- see issue #84's thread). The memory
stream stays an honest, append-only log.

See ``docs/design/agent-memory.md`` §7.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from . import prompt_templates

# --- Reflection tuning (docs/design/agent-memory.md §7) ----------------------
# Reflect once accumulated importance since the last reflection crosses this.
# The paper's scale; AgentMemory.importance_since_reflection sums the 1-10
# poignancy of every record added since the last reflect() reset.
DEFAULT_REFLECTION_THRESHOLD = 30.0
# How many of the most recent records seed the "what's salient?" question step.
DEFAULT_RECENT_WINDOW = 50
# A reflection pass asks at most this many salient questions (one inference each).
DEFAULT_MAX_QUESTIONS = 3
# Synthesized thoughts are fairly salient by default (mid 1-10 scale), so they
# surface in later retrievals without drowning out momentous raw observations.
DEFAULT_REFLECTION_IMPORTANCE = 6.0


@dataclass
class Reflection:
    """One synthesized higher-level thought and the memories it rests on.

    ``evidence_ids`` are the ids of the :class:`~text_adventure_games.memory.
    MemoryRecord`\\ s that support the inference, stored on the resulting
    ``REFLECTION`` record so a reader can trace a thought back to its grounds
    (the paper's "citations"). ``importance`` is on the same 1-10 poignancy scale
    as every other record.
    """

    text: str
    evidence_ids: list[int] = field(default_factory=list)
    importance: float = DEFAULT_REFLECTION_IMPORTANCE


@runtime_checkable
class Reflector(Protocol):
    """How :func:`reflect` asks for the two cognitive steps of a reflection.

    Two implementations are expected (cf. ``Planner`` / ``MockReActClient``):

    * a **mock** reflector -- deterministic and offline, so reflection works in
      tests and free local runs with no model;
    * an **LLM** reflector -- real synthesis over the engine's ``LlmClient`` seam,
      selected by the same provider gate as the decision brain.

    The protocol is split into the paper's two steps so :func:`reflect` can do the
    retrieval *between* them (gather the memories that support each question)
    while the model/mock only handles the language:

    1. :meth:`salient_questions` -- given recent records, what should I ask?
    2. :meth:`infer` -- given a question and its supporting records, what's the
       one-line inference?

    ``records`` are passed by duck typing (each item exposes ``.text`` / ``.id`` /
    ``.actor``), so this module keeps zero engine imports.
    """

    def salient_questions(self, records) -> list[str]:
        """Return a few high-level questions the recent ``records`` raise."""
        ...

    def infer(self, question: str, records) -> Reflection | None:
        """Return one inference answering ``question`` from its supporting
        ``records``, or ``None`` when nothing usable can be said."""
        ...


# ---------------------------------------------------------------------------
# Threshold + orchestration (docs/design/agent-memory.md §7) -- no LLM, no engine
# ---------------------------------------------------------------------------


def should_reflect(memory, threshold: float = DEFAULT_REFLECTION_THRESHOLD) -> bool:
    """Has enough importance accrued since the last reflection to reflect again?

    Reads ``memory.importance_since_reflection`` -- the running sum
    ``AgentMemory`` keeps of every record's importance since the last
    :func:`reflect` reset -- and compares it to ``threshold``. The cadence is
    "salience-driven, not clock-driven": a quiet stretch of mundane observations
    reflects rarely, a burst of momentous events reflects soon after.
    """
    return getattr(memory, "importance_since_reflection", 0.0) >= threshold


def reflect(
    memory,
    reflector: Reflector,
    turn: int,
    *,
    recent_window: int = DEFAULT_RECENT_WINDOW,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
    default_importance: float = DEFAULT_REFLECTION_IMPORTANCE,
) -> list:
    """Run one reflection pass over ``memory`` and append the thoughts it yields.

    The paper's flow (docs/design/agent-memory.md §7):

    1. Take the ``recent_window`` most recent records as the seed.
    2. Ask the ``reflector`` for the salient questions they raise (capped at
       ``max_questions``).
    3. For each question, *retrieve* the memories that best support it (a
       read-only retrieval -- ``touch=False`` -- so reflecting never disturbs the
       recency the decision loop depends on).
    4. Ask the ``reflector`` for one grounded inference per question.
    5. Store each inference as a ``MemoryKind.REFLECTION`` record citing its
       supporting memory ids.
    6. Reset ``importance_since_reflection`` so the next pass waits for fresh
       salience.

    Returns the list of reflection records created (possibly empty -- a reflector
    that proposes no questions, or whose inferences are all unusable, simply adds
    nothing). The accumulator is reset either way, so a model that returns nothing
    won't be re-hit every turn; reflection just waits for importance to build
    again.
    """
    recent = memory.records[-recent_window:]
    if not recent:
        memory.importance_since_reflection = 0.0
        return []

    questions = [q for q in reflector.salient_questions(recent) if q][:max_questions]
    created = []
    for question in questions:
        # Read-only: gathering grounds for a thought must not bump recency, or a
        # reflection pass would quietly reshuffle what the next decision retrieves.
        supporting = memory.retrieve(query=question, turn=turn, touch=False)
        if not supporting:
            continue
        result = reflector.infer(question, supporting)
        if result is None or not result.text.strip():
            continue
        evidence = result.evidence_ids or [r.id for r in supporting]
        created.append(
            memory.add_reflection(
                result.text.strip(),
                turn=turn,
                evidence_ids=evidence,
                importance=(
                    result.importance
                    if result.importance is not None
                    else default_importance
                ),
            )
        )
    # Step 6: reset *after* adding, so the reflections' own importance (which
    # add_reflection accrued) is discarded from the accumulator -- the next pass
    # measures only genuinely new experience (design doc §7, step 6).
    memory.importance_since_reflection = 0.0
    return created


# ---------------------------------------------------------------------------
# MockReflector -- deterministic, offline (cf. backend.planner.MockPlanner)
# ---------------------------------------------------------------------------


class MockReflector:
    """Deterministic reflector that needs no model and no network.

    It is intentionally simple and grounded, not clever: it keys questions off
    the *actors* the agent has been encountering (the most meaningful recurring
    subject in a stream of observations), and phrases each inference as a plain
    summary of the memories that support it. That is enough to exercise the whole
    reflection loop -- threshold, questions, retrieval, inference, write-back --
    for free in tests and offline runs, the same role ``MockReActClient`` plays
    for the decision brain.
    """

    def __init__(self, max_questions: int = DEFAULT_MAX_QUESTIONS):
        self.max_questions = max_questions

    def salient_questions(self, records) -> list[str]:
        """One question per recurring actor, newest-mentioned first; else a
        single generic question so a reflection still happens with no named
        actors. Deterministic: ties break by most-recent mention."""
        # Count by actor, but remember the latest index each actor appears at so
        # equally-frequent actors order by recency (stable + deterministic).
        counts: Counter = Counter()
        last_seen: dict[str, int] = {}
        for index, record in enumerate(records):
            actor = getattr(record, "actor", None)
            if actor:
                counts[actor] += 1
                last_seen[actor] = index
        ordered = sorted(counts, key=lambda a: (counts[a], last_seen[a]), reverse=True)
        questions = [f"What should I make of {actor}?" for actor in ordered]
        if not questions:
            questions = ["What have I been doing, and what does it add up to?"]
        return questions[: self.max_questions]

    def infer(self, question: str, records) -> Reflection | None:
        """Summarize the (already-retrieved) supporting records into one thought,
        citing them all. Returns ``None`` only when there is nothing to ground a
        thought in."""
        if not records:
            return None
        snippets = "; ".join(r.text.rstrip(".") for r in records[:3])
        text = f'Reflecting on "{question}" — lately: {snippets}.'
        return Reflection(
            text=text,
            evidence_ids=[r.id for r in records],
            importance=DEFAULT_REFLECTION_IMPORTANCE,
        )


# ---------------------------------------------------------------------------
# LLMReflector -- real synthesis over the engine's LlmClient seam (design §7)
# ---------------------------------------------------------------------------

# Structured tools (normalized {name, description, parameters} dicts, the shape
# llm_client.call_tool translates per provider). Forcing validated JSON beats
# scraping prose -- the same reason LLMPlanner and the LLM parser use tools.
SALIENT_QUESTIONS_TOOL = {
    "name": "salient_questions",
    "description": (
        "List the 2-3 most salient high-level questions the recent memories "
        "raise about the agent, the people around it, or its situation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "description": "Each item is a question string.",
                "items": {"type": "string"},
            }
        },
        "required": ["questions"],
    },
}

INSIGHT_TOOL = {
    "name": "record_insight",
    "description": (
        "Record one short high-level insight that answers the question, grounded "
        "only in the supporting memories, citing the numbers that support it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "insight": {
                "type": "string",
                "description": "one short sentence inferred from the memories",
            },
            "evidence": {
                "type": "array",
                "description": "the 1-based numbers of the supporting memories",
                "items": {"type": "integer"},
            },
        },
        "required": ["insight"],
    },
}


class LLMReflector:
    """Synthesize reflections with a real model (design doc §7).

    Drives the paper's two steps through structured tool calls on an engine
    ``LlmClient``: :meth:`salient_questions` asks for the questions a window of
    memories raises; :meth:`infer` asks for one grounded inference per question.
    :func:`reflect` does the retrieval in between and writes the results back.

    Robust by construction, like ``LLMPlanner``: a missing or malformed tool
    result degrades to "no questions" / "no inference" rather than raising, so a
    flaky model just produces fewer (or no) reflections instead of crashing a run.
    It is written against the ``LlmClient`` seam and tested with a scripted fake
    client, so swapping in a live model is a ``client_from_env()`` change with no
    edits here.
    """

    def __init__(self, client, *, max_tokens: int = 400):
        self.client = client
        self.max_tokens = max_tokens

    def salient_questions(self, records) -> list[str]:
        user = (
            "Here are recent things you have experienced:\n"
            f"{self._numbered(records)}\n"
            "Given only these, what are the most salient high-level questions you "
            "could now answer about yourself, others, or your situation?"
        )
        result = self._call(user, SALIENT_QUESTIONS_TOOL)
        questions = result.get("questions") if isinstance(result, dict) else None
        if not isinstance(questions, list):
            return []
        return [q.strip() for q in questions if isinstance(q, str) and q.strip()]

    def infer(self, question: str, records) -> Reflection | None:
        if not records:
            return None
        user = (
            f"Question: {question}\n\n"
            f"Supporting memories:\n{self._numbered(records)}\n"
            "State one short insight that answers the question, grounded only in "
            "these memories, and cite the numbers that support it."
        )
        result = self._call(user, INSIGHT_TOOL)
        if not isinstance(result, dict):
            return None
        text = result.get("insight")
        if not isinstance(text, str) or not text.strip():
            return None
        evidence = self._map_evidence(result.get("evidence"), records)
        return Reflection(
            text=text.strip(),
            evidence_ids=evidence or [r.id for r in records],
            importance=DEFAULT_REFLECTION_IMPORTANCE,
        )

    # -- prompt + parsing helpers (mirror LLMPlanner) ------------------------

    @staticmethod
    def _numbered(records) -> str:
        """A 1-based numbered list of record texts -- the model cites by number,
        and :meth:`_map_evidence` maps those numbers back to real record ids."""
        return "\n".join(f"{i}. {r.text}" for i, r in enumerate(records, start=1))

    @staticmethod
    def _map_evidence(evidence, records) -> list[int]:
        """Map the model's 1-based citation numbers back to record ids.

        Tolerant of the model citing strings ("2"), out-of-range numbers, or
        nothing at all -- anything unusable is dropped, and :meth:`infer` falls
        back to citing every supporting record when the result is empty.
        """
        if not isinstance(evidence, list):
            return []
        ids: list[int] = []
        for value in evidence:
            number = LLMReflector._coerce_int(value)
            if number is not None and 1 <= number <= len(records):
                ids.append(records[number - 1].id)
        return ids

    @staticmethod
    def _coerce_int(value) -> int | None:
        """An int from an int or plain numeric string, else ``None`` (bools are
        not ints here) -- mirrors ``LLMPlanner._coerce_int``."""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
            return int(value.strip())
        return None

    def _call(self, user: str, tool: dict) -> dict:
        messages = [
            {"role": "system", "content": prompt_templates.render("reflect_system")},
            {"role": "user", "content": user},
        ]
        result = self.client.call_tool(messages, tool, max_tokens=self.max_tokens)
        return result or {}
