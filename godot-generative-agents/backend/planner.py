"""Daily planners (issue #83, NEXT-STEPS Phase D).

The engine defines *what a plan is* and *how it is manipulated*
(``text_adventure_games.planning``); this module is the sim-specific
*cognition* that fills one in, behind the engine's :class:`Planner` protocol.

Two implementations are planned, mirroring the brain split in
``cognition.py`` (mock vs. real LLM):

* :class:`MockPlanner` -- **the default, offline, deterministic planner.** It
  reproduces a persona's hand-authored world-YAML schedule exactly, so a
  default ``run_simulation`` produces byte-identical ``movement/*.json``. The YAML
  schedules become the mock's *fixture* rather than the only source of truth.
* :class:`LLMPlanner` -- generates and revises real day -> hourly -> minute plans
  from identity + memory, over the engine's ``LlmClient`` seam (design doc §6-§9).
  It is written against that protocol and tested with a deterministic fake client,
  so the real model is just a ``client_from_env()`` swap once Phase A lands -- the
  planner needs no further changes. The provider gate in ``run_simulation.main``
  only selects it for a real (non-mock) provider, so the offline default keeps
  using :class:`MockPlanner` and the replay stays byte-identical.
"""

from __future__ import annotations

from text_adventure_games.planning import (
    DailyPlan,
    DayBlock,
    HourBlock,
    Stop,
    validate_stops,
)

from .prompt_templates import render


class MockPlanner:
    """Deterministic planner that replays a persona's static schedule.

    Built from one normalized persona spec (``build_world._normalize_personas``
    guarantees a uniform ``schedule`` list of ``{place, activity, emoji, steps}``
    stops). :meth:`generate` turns those stops straight into a :class:`DailyPlan`;
    it deliberately leaves the higher ``day`` / ``hours`` levels empty -- the mock
    has no day outline to decompose, only the authored minute plan. :meth:`revise`
    is a no-op: the static day never reacts, which is exactly what keeps the
    offline replay byte-identical.
    """

    def __init__(self, persona: dict):
        self._stops = [Stop.from_schedule_entry(entry) for entry in persona["schedule"]]

    def generate(self, persona=None, memory=None, clock=None) -> DailyPlan:
        """Return the authored schedule as a (minute-level only) plan.

        The arguments the :class:`~text_adventure_games.planning.Planner` protocol
        passes (identity / memory / clock) are accepted but ignored -- the mock
        plans from the fixture alone, the way the current ``ScheduleMockClient``
        decides from location alone.
        """
        return DailyPlan(stops=list(self._stops))

    def revise(
        self, plan: DailyPlan, trigger=None, memory=None, clock=None
    ) -> DailyPlan:
        """No-op: the static schedule never re-plans (keeps the replay identical)."""
        return plan


# ---------------------------------------------------------------------------
# LLMPlanner -- real generation over the engine's LlmClient seam (design §6-§9)
# ---------------------------------------------------------------------------

# Structured tools (normalized {name, description, parameters} dicts, the shape
# llm_client.call_tool translates per provider). Forcing the model to return
# validated JSON for each level beats scraping prose -- the same reason the LLM
# parser uses SELECT_OPTION_TOOL.
DAY_OUTLINE_TOOL = {
    "name": "day_outline",
    "description": "Sketch the day as 4-6 broad blocks. No exact times yet.",
    "parameters": {
        "type": "object",
        "properties": {
            "blocks": {
                "type": "array",
                "description": "Each item is a JSON object, not a string.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "description": "morning / midday / afternoon / evening",
                        },
                        "summary": {"type": "string"},
                    },
                    "required": ["label", "summary"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["blocks"],
        "additionalProperties": False,
    },
}

HOURLY_TOOL = {
    "name": "hourly_plan",
    "description": "Expand the day outline into one line per in-game hour.",
    "parameters": {
        "type": "object",
        "properties": {
            "hours": {
                "type": "array",
                "description": "Each item is a JSON object, not a string.",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_hour": {
                            "type": "integer",
                            "description": "hour of day, 0-23",
                        },
                        "summary": {"type": "string"},
                    },
                    "required": ["start_hour", "summary"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["hours"],
        "additionalProperties": False,
    },
}

MINUTE_TOOL = {
    "name": "minute_plan",
    "description": (
        "Turn the plan into concrete stops: where to go, what to do there, and "
        "for how many minutes to stay before moving on (omit minutes on the last "
        "stop to stay put). Use only known places."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "stops": {
                "type": "array",
                "description": "Each item is a JSON object with the fields below, not a string.",
                "items": {
                    "type": "object",
                    "properties": {
                        "place": {"type": "string"},
                        "activity": {"type": "string"},
                        "emoji": {"type": "string"},
                        "minutes": {
                            "type": "integer",
                            "description": (
                                "In-game minutes spent AT this place. Travel time "
                                "to get here is charged separately, on top of this."
                            ),
                        },
                    },
                    # emoji/minutes stay genuinely optional (missing minutes means
                    # "stay put"), so this tool is best-effort, not OpenAI strict
                    # (#357) -- forcing every field required would change that
                    # meaning. additionalProperties:false still tightens
                    # validation; the arguments are type-checked either way.
                    "required": ["place", "activity"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["stops"],
        "additionalProperties": False,
    },
}


def median_travel_minutes(world_map, addresses, clock) -> int | None:
    """Median pairwise walk cost between *addresses*, in in-game minutes (#795).

    Chebyshev tile gap between each pair's first tile, which -- since the walk
    advances one tile per step -- is the minimum number of steps that walk can
    take. A lower bound, deliberately: the prompt that consumes it says "at
    least about N minutes", and running real A* for every location pair at
    every _build would cost real time for a number the model only needs to be
    directionally right about.

    Returns None when there is no map, no clock, or fewer than two addresses
    with known tiles -- the caller then omits the clause rather than inventing
    a constant.
    """
    if world_map is None or clock is None:
        return None
    anchors = []
    for address in addresses:
        tiles = world_map.tiles_for(address) if address else set()
        if tiles:
            anchors.append(min(tiles))  # min() keeps this deterministic
    if len(anchors) < 2:
        return None
    gaps = sorted(
        max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        for i, a in enumerate(anchors)
        for b in anchors[i + 1 :]
    )
    median_tiles = gaps[len(gaps) // 2]
    return clock.minutes_for_steps(median_tiles) or None


class LLMPlanner:
    """Generate and revise a day's plan with a real model (design doc §6-§9).

    Drives the three-level decomposition through structured tool calls on an
    engine ``LlmClient``: day outline -> hourly -> minute stops, each conditioned
    on the level above. ``revise`` re-runs the minute level given the trigger; the
    step loop (:func:`cognition.maybe_revise_plan`) re-anchors the executed
    prefix, so this planner only has to propose a sensible full-day stop list.

    Robust by construction: a missing or malformed tool result degrades to an
    empty level rather than raising, and every generated stop is checked against
    ``known_places`` (``planning.validate_stops``) so a hallucinated location is
    dropped before it reaches the schedule -- never the parser. With no
    ``known_places`` given, validation is skipped (the caller passes the world's
    location names; tests may omit them).
    """

    def __init__(
        self,
        client,
        known_places=frozenset(),
        *,
        clock=None,
        num_steps=None,
        max_tokens: int = 700,
        travel_minutes: int | None = None,
    ):
        self.client = client
        self.known_places = set(known_places)
        # When both are given (a :class:`~backend.sim_clock.SimClock` and the run
        # length in steps), the plan is bounded to the hours the run actually
        # covers -- so the model plans 8-11am for a 3-hour run instead of a generic
        # full day, which is tighter and cheaper. With neither, it plans an
        # open-ended day.
        self.clock = clock
        self.num_steps = num_steps
        self.max_tokens = max_tokens
        # #795: median cross-campus walk cost in minutes, computed from this
        # world's own map (see median_travel_minutes). None -> the minute
        # prompt omits the travel clause rather than fabricating a constant.
        self.travel_minutes = travel_minutes

    # -- the three generation levels -----------------------------------------

    def generate(self, persona, memory=None, clock=None) -> DailyPlan:
        # ``clock`` is accepted for the Planner protocol; the run-bounded clock is
        # configured on the instance (see __init__), so we read that.
        persona_text = self._persona_text(persona)
        mem = self._memory_block(memory, "what matters for my day today", turn=0)
        day = self._day_outline(persona_text, mem)
        # #795: the retrieved block goes to EVERY level, not just the outline.
        # The agent's own commitments (seeded at t=0 by attach_agents, importance
        # 5.0) are what name the places it is obliged to be at; passing them only
        # to _day_outline meant place and duration were chosen two lossy
        # summarisation hops later, and an authored obligation -- "setting up for
        # an afternoon guest lecture at Irvine Auditorium" -- simply vanished.
        hours = self._hourly(persona_text, day, mem)
        stops = self._minute(persona_text, hours, mem)
        return DailyPlan(day=day, hours=hours, stops=stops)

    def revise(
        self, plan: DailyPlan, trigger=None, memory=None, clock=None
    ) -> DailyPlan:
        reason = getattr(trigger, "reason", "") or ""
        detail = getattr(trigger, "detail", "") or ""
        step = getattr(trigger, "step", 0)
        mem = self._memory_block(memory, detail or "what changed", turn=step)
        current = "; ".join(f"{s.place}: {s.activity}" for s in plan.stops) or "(none)"
        user = (
            f"Your plan so far: {current}.\n"
            f"Something changed -- {reason}: {detail}.\n"
            f"{self._memory_line(mem)}"
            f"{self._places_line()}"
            "Give a revised full list of stops for the day, keeping the ones that "
            "have already happened and changing the rest."
        )
        stops = self._minute_from_user(user)
        if not stops:
            return plan  # nothing usable -> signal "no change" to the loop
        return DailyPlan(
            day=plan.day, hours=plan.hours, stops=stops, revision=plan.revision + 1
        )

    # -- per-level prompts + parsing -----------------------------------------

    def _day_outline(self, persona_text: str, mem: str) -> list[DayBlock]:
        user = (
            f"{persona_text}\n{self._window_line()}{self._memory_line(mem)}"
            "Sketch your day as a few broad blocks."
        )
        result = self._call(user, DAY_OUTLINE_TOOL)
        blocks = []
        # Arguments are schema-validated in the client (#357): each block is an
        # object with string label/summary. A missing key or invalid reply yields
        # {} here (call_tool returned None), so the loop just produces no blocks
        # and generation degrades to the static fallback. The truthiness guard
        # only skips an empty-string label/summary.
        for b in result.get("blocks") or []:
            label, summary = b.get("label"), b.get("summary")
            if label and summary:
                blocks.append(DayBlock(label=label, summary=summary))
        return blocks

    def _hourly(
        self, persona_text: str, day: list[DayBlock], mem: str = ""
    ) -> list[HourBlock]:
        outline = "; ".join(f"{b.label}: {b.summary}" for b in day) or "(none)"
        hours_hint = ""
        if self.clock is not None and self.num_steps is not None:
            hours = [h for _, h in self.clock.hour_starts(self.num_steps)]
            if hours:
                hours_hint = f"Plan only these hours of the day: {hours}.\n"
        user = (
            f"{persona_text}\n{self._window_line()}{self._memory_line(mem)}"
            f"Your day outline: {outline}.\n"
            f"{hours_hint}Give one line per hour."
        )
        result = self._call(user, HOURLY_TOOL)
        hours = []
        # Validated upstream (#357): start_hour is an int, summary a string.
        # `is not None` (not truthiness) so a legitimate hour 0 and an empty
        # summary are both kept (an empty summary renders harmlessly).
        for h in result.get("hours") or []:
            hour, summary = h.get("start_hour"), h.get("summary")
            if hour is not None and summary is not None:
                hours.append(HourBlock(start_hour=hour, summary=summary))
        return hours

    def _minute(
        self, persona_text: str, hours: list[HourBlock], mem: str = ""
    ) -> list[Stop]:
        plan = (
            "; ".join(f"{h.start_hour:02d}:00 {h.summary}" for h in hours) or "(none)"
        )
        user = (
            f"{persona_text}\n{self._window_line()}{self._travel_line()}"
            f"{self._memory_line(mem)}"
            f"Your hourly plan: {plan}.\n{self._places_line()}"
            "Turn it into concrete stops."
        )
        return self._minute_from_user(user)

    def _minute_from_user(self, user: str) -> list[Stop]:
        result = self._call(user, MINUTE_TOOL)
        stops = []
        # Validated upstream (#357): place/activity are strings, emoji is a
        # string-or-null, minutes an int-or-null. The one remaining check is the
        # *semantic* one -- a non-positive or null duration means "stay put"
        # -- which the schema can't express (OpenAI strict mode drops `minimum`).
        for s in result.get("stops") or []:
            place, activity = s.get("place"), s.get("activity")
            if not (place and activity):
                continue
            minutes = s.get("minutes")
            if not (
                isinstance(minutes, int)
                and not isinstance(minutes, bool)
                and minutes > 0
            ):
                steps = None
            elif self.clock is not None:
                # #795: the model answers in minutes -- a unit it has intuition
                # for -- and we convert once, here. Stop.steps stays the internal
                # unit, so nothing downstream changes.
                steps = self.clock.steps_for_seconds(minutes * 60) or None
            else:
                # No clock (tests that omit one): read the value as steps, which
                # is exactly what this field meant before #795.
                steps = minutes
            stops.append(
                Stop(
                    place=place,
                    activity=activity,
                    emoji=s.get("emoji"),
                    steps=steps,
                )
            )
        if self.known_places:
            stops, _dropped = validate_stops(stops, self.known_places)
        return stops

    # -- small seam helpers ---------------------------------------------------

    def _call(self, user: str, tool: dict) -> dict:
        messages = [
            {"role": "system", "content": render("plan_system")},
            {"role": "user", "content": user},
        ]
        result = self.client.call_tool(messages, tool, max_tokens=self.max_tokens)
        return result or {}

    @staticmethod
    def _persona_text(persona) -> str:
        if isinstance(persona, dict):
            return persona.get("persona") or persona.get("name") or "a town resident"
        return str(persona)

    @staticmethod
    def _memory_block(memory, query: str, turn: int) -> str:
        if memory is None:
            return ""
        try:
            records = memory.retrieve(query=query, turn=turn)
        except Exception:
            return ""
        return "\n".join(f"- {r.text}" for r in (records or []))

    @staticmethod
    def _memory_line(mem: str) -> str:
        return f"You remember:\n{mem}\n" if mem else ""

    def _places_line(self) -> str:
        if not self.known_places:
            return ""
        return f"Known places: {', '.join(sorted(self.known_places))}.\n"

    def _window_line(self) -> str:
        """Tell the model the clock window the run covers, so it plans only that.

        Empty unless both a clock and a run length were given (e.g. tests omit
        them) -- then the plan is open-ended, as before."""
        if self.clock is None or self.num_steps is None:
            return ""
        start = self.clock.time_at(0).strftime("%H:%M")
        end = self.clock.time_at(self.num_steps).strftime("%H:%M")
        return f"This simulation runs from {start} to {end} today; plan only that window.\n"

    def _travel_line(self) -> str:
        """Tell the model travel is not free, when we know what it costs.

        Empty when no hint was computed -- an omitted clause beats a
        fabricated constant."""
        if not self.travel_minutes:
            return ""
        return (
            "`minutes` is time spent AT a place; travel to get there is charged "
            f"on top of it, and crossing campus takes at least about "
            f"{self.travel_minutes} minutes.\n"
        )
