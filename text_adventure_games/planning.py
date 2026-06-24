"""Decomposable daily plans for agents (issue #83, NEXT-STEPS Phase D).

A :class:`DailyPlan` is the structured intention an agent forms for its day,
decomposed top-down across three levels (see ``docs/design/daily-planning.md``):

* **day outline** -- a handful of broad :class:`DayBlock`s ("morning: open the
  cafe"), no exact times;
* **hourly plan** -- one :class:`HourBlock` per in-sim hour;
* **minute plan** -- concrete :class:`Stop`s ``{place, activity, emoji, steps}``,
  the *only* level the step loop consumes (it is exactly the schedule shape the
  Smallville port already drives via ``advance()``).

Following the same restraint as ``memory.py`` and ``knowledge.py``, this module
is **pure data with no engine imports**: the dataclasses and the helper
functions below manipulate plans without ever touching a ``Game`` or
``Character``, so the whole thing unit-tests offline and reads easily. The
*cognition* that fills a plan in (generate / decompose / revise) lives behind the
:class:`Planner` protocol -- a deterministic mock for offline/CI runs, a real
LLM-backed planner for live runs -- exactly mirroring how ``llm_client.py`` pairs
an ``LlmClient`` protocol with a ``MockReActClient``.

Design invariant: **a plan is an intention, never a world mutation.** Nothing
here moves an agent or changes the world; a plan only *proposes* stops, and every
stop still has to pass the parser's precondition gate when the loop executes it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Data model (docs/design/daily-planning.md §5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DayBlock:
    """One broad block of the day outline -- a phrase, not a time."""

    label: str  # "morning", "midday", "afternoon", "evening"
    summary: str  # "open and run the cafe"


@dataclass(frozen=True)
class HourBlock:
    """What the agent intends to do during one in-sim hour."""

    start_hour: int  # in-sim hour of day, 0-23
    summary: str  # "tend the counter, then buy milk"


@dataclass(frozen=True)
class Stop:
    """A concrete minute-level stop -- the schedule entry the loop drives.

    Identical in shape to a ``world_data.yaml`` schedule stop, so committing a
    plan is just handing ``DailyPlan.stops`` to the agent's client. ``steps`` is
    a count of sim steps to perform ``activity`` for; ``None`` means "stay for the
    rest of the day" (the existing last-stop convention).
    """

    place: str  # must resolve to a known Location name when executed
    activity: str
    emoji: str | None = None
    steps: int | None = None  # None => stay put indefinitely

    def to_schedule_entry(self) -> dict:
        """The plain dict the Smallville client/loop already understands."""
        return {
            "place": self.place,
            "activity": self.activity,
            "emoji": self.emoji,
            "steps": self.steps,
        }

    @classmethod
    def from_schedule_entry(cls, entry: dict) -> "Stop":
        """Build a :class:`Stop` from a ``world_data.yaml``-style schedule dict."""
        return cls(
            place=entry["place"],
            activity=entry["activity"],
            emoji=entry.get("emoji"),
            steps=entry.get("steps"),
        )


@dataclass
class DailyPlan:
    """An agent's plan for the day, across all three levels.

    ``stops`` is the part the step loop consumes; ``day``/``hours`` are the
    higher-altitude reasoning, kept so retrieval, reflection, and revision can see
    the agent's intentions at every level (and written into the memory stream as
    ``MemoryKind.PLAN`` records -- see :func:`plan_memory_lines`).

    ``revision`` starts at 0 and is bumped every time :func:`replace_tail`
    rewrites the not-yet-executed tail of the plan.
    """

    day: list[DayBlock] = field(default_factory=list)
    hours: list[HourBlock] = field(default_factory=list)
    stops: list[Stop] = field(default_factory=list)
    revision: int = 0

    def to_primitive(self) -> dict:
        """Serialize to JSON-safe primitives (mirrors ``MemoryRecord``)."""
        return {
            "day": [asdict(b) for b in self.day],
            "hours": [asdict(h) for h in self.hours],
            "stops": [asdict(s) for s in self.stops],
            "revision": self.revision,
        }

    @classmethod
    def from_primitive(cls, data: dict) -> "DailyPlan":
        """Reconstruct a plan from :meth:`to_primitive` output.

        Tolerant of missing keys so leaner payloads still load (mirrors
        ``MemoryRecord.from_primitive`` / ``Knowledge.from_primitive``)."""
        return cls(
            day=[DayBlock(**b) for b in data.get("day", [])],
            hours=[HourBlock(**h) for h in data.get("hours", [])],
            stops=[Stop(**s) for s in data.get("stops", [])],
            revision=data.get("revision", 0),
        )


# ---------------------------------------------------------------------------
# Revision triggers (docs/design/daily-planning.md §8)
# ---------------------------------------------------------------------------

# The reasons a day's plan might be re-considered mid-run. The step loop tags a
# revision with one of these so a planner can react differently to each (an
# action that failed its preconditions vs. merely running behind the clock).
ACTION_FAILED = "action_failed"  # a travel/perform command failed the gate
PERCEPTION = "perception"  # a perceived memory contradicts the plan
BEHIND_SCHEDULE = "behind_schedule"  # still en route when the hour's budget ran out


@dataclass(frozen=True)
class RevisionTrigger:
    """Why, and when, the loop is offering a planner a chance to re-plan.

    ``reason`` is one of the module constants above; ``step`` is the sim step it
    fired on; ``detail`` is free text for context (e.g. the failed command or the
    parser's failure message). A :class:`Planner` reads this to decide whether and
    how to rewrite the plan's tail; a mock planner ignores it.
    """

    reason: str
    step: int
    detail: str = ""


# ---------------------------------------------------------------------------
# Planner protocol (docs/design/daily-planning.md §9)
# ---------------------------------------------------------------------------


@runtime_checkable
class Planner(Protocol):
    """How the step loop asks for and revises a plan.

    Two implementations are expected (cf. ``LlmClient`` / ``MockReActClient``):

    * a **mock** planner -- deterministic and offline, reproducing today's static
      schedule so the replay stays byte-identical (the project's iron rule);
    * an **LLM** planner -- generates and revises real plans from identity +
      memory, selected by the same provider gate as the brain.

    ``persona`` / ``memory`` / ``clock`` / ``trigger`` are passed by duck typing
    so this module keeps zero engine imports; an implementation reads whatever it
    needs off them.
    """

    def generate(self, persona, memory, clock) -> DailyPlan:
        """Produce a fresh plan for the day from identity + memory."""
        ...

    def revise(self, plan: DailyPlan, trigger, memory, clock) -> DailyPlan:
        """Return a plan whose *unstarted tail* reacts to ``trigger``.

        Must leave already-executed and currently-performing stops untouched
        (see :func:`replace_tail`); a no-op implementation may return ``plan``.
        """
        ...


# ---------------------------------------------------------------------------
# Pure helpers (docs/design/daily-planning.md §7-§8) -- no LLM, no engine
# ---------------------------------------------------------------------------


def validate_stops(
    stops: list[Stop], known_places: set[str]
) -> tuple[list[Stop], list[Stop]]:
    """Split ``stops`` into ``(kept, dropped)`` against the known location names.

    A stop is dropped when its ``place`` is not a known :class:`Location` name, or
    its ``steps`` is neither a positive int nor ``None``. Catching a hallucinated
    place here -- before it is committed to the schedule -- gives a clear, early
    signal instead of a parser failure deep in the loop (the same check
    ``build_world`` does for hand-authored places, moved into the planner).
    """
    kept: list[Stop] = []
    dropped: list[Stop] = []
    for stop in stops:
        steps_ok = stop.steps is None or (
            isinstance(stop.steps, int)
            and not isinstance(stop.steps, bool)
            and stop.steps > 0
        )
        if stop.place in known_places and steps_ok:
            kept.append(stop)
        else:
            dropped.append(stop)
    return kept, dropped


def replace_tail(plan: DailyPlan, after: int, new_stops: list[Stop]) -> DailyPlan:
    """Return a copy of ``plan`` with the stops after index ``after`` replaced.

    Stops ``0..after`` (inclusive) -- the executed ones and the one currently
    being performed -- are preserved verbatim; everything past ``after`` becomes
    ``new_stops``, and ``revision`` is bumped. This is the only sanctioned way to
    revise a plan mid-day, so memory, schedule, and the on-screen replay can never
    desync on a stop the agent has already started (design invariant §8).

    ``after = -1`` replaces the whole list (nothing executed yet).
    """
    if after < -1:
        raise ValueError(f"after must be >= -1, got {after}")
    kept = plan.stops[: after + 1]
    return replace(plan, stops=kept + list(new_stops), revision=plan.revision + 1)


def even_step_split(total: int, n: int) -> list[int]:
    """Split ``total`` steps into ``n`` positive parts that sum to exactly ``total``.

    Used by hourly -> minute decomposition to hand each stop a share of its
    hour's step budget when the planner doesn't specify exact durations. The
    remainder is spread one-per-part across the leading parts, so the result is as
    even as possible and always sums back to ``total`` (no drift).
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if total < n:
        raise ValueError(f"cannot split {total} steps into {n} positive parts")
    base, remainder = divmod(total, n)
    return [base + (1 if i < remainder else 0) for i in range(n)]


def plan_memory_lines(plan: DailyPlan) -> list[str]:
    """Render a plan as the natural-language lines to store as PLAN memories.

    One line per altitude the agent should be able to recall -- the day outline,
    each hour, and the concrete stops -- so retrieval surfaces "what I meant to do
    today" at whatever granularity a later decision needs. The caller adds each
    via ``AgentMemory.add_plan`` (this module stays memory-agnostic).
    """
    lines: list[str] = []
    if plan.day:
        outline = "; ".join(f"{b.label}: {b.summary}" for b in plan.day)
        lines.append(f"Today's outline -- {outline}.")
    for hour in plan.hours:
        lines.append(f"At {hour.start_hour:02d}:00 I plan to {hour.summary}.")
    if plan.stops:
        itinerary = ", then ".join(f"{s.activity} at {s.place}" for s in plan.stops)
        lines.append(f"My stops today: {itinerary}.")
    return lines
