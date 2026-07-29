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

from copy import deepcopy
from dataclasses import replace

from text_adventure_games.planning import (
    DailyPlan,
    DayBlock,
    HourBlock,
    IMMEDIATE_URGENCY,
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
                        # #821: the hourly level already pinned some stops to a
                        # clock hour; without somewhere to put that hour it
                        # survived into this level as prose only, and the
                        # arithmetic that has to land the stop on it went
                        # unchecked. Declared here so the model can hand the
                        # anchor back and _anchor_correction can verify it.
                        "start_hour": {
                            "type": "integer",
                            "description": (
                                "Hour of day (0-23) this stop must BEGIN at, "
                                "copied from your hourly plan. Set it only for a "
                                "stop pinned to a clock time (a lecture, a "
                                "meeting); omit it for everything else."
                            ),
                        },
                    },
                    # emoji/minutes/start_hour stay genuinely optional (missing
                    # minutes means "stay put", missing start_hour means "no fixed
                    # time"), so this tool is best-effort, not OpenAI strict
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

# Immediate conversation commitments (#829) need a stronger response contract
# than the ordinary "revised full list": the model names the one stop that must
# execute next and returns only the later tail. LLMPlanner then preserves the
# executed/current prefix itself instead of asking the model to reproduce it.
_MINUTE_STOP_SCHEMA = deepcopy(
    MINUTE_TOOL["parameters"]["properties"]["stops"]["items"]
)
IMMEDIATE_REVISION_TOOL = {
    "name": "immediate_plan_revision",
    "description": (
        "Turn a commitment that starts as soon as the conversation ends into "
        "the next concrete stop, followed by any later stops. Return only the "
        "unstarted tail; do not repeat completed or current stops."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "next_stop": deepcopy(_MINUTE_STOP_SCHEMA),
            "later_stops": {
                "type": "array",
                "description": (
                    "Optional stops after next_stop, in execution order. Do not "
                    "include completed/current stops."
                ),
                "items": deepcopy(_MINUTE_STOP_SCHEMA),
            },
        },
        "required": ["next_stop", "later_stops"],
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


# How far past its pinned hour a stop may be projected to start before the plan
# is sent back for a fix (#821). A calibration knob, not a magic number: it sits
# on top of a travel estimate that is deliberately a *lower* bound
# (median_travel_minutes above), so the projection already errs early and this
# only has to absorb the wobble. Raise it if real runs re-ask on plans that turn
# out fine; lower it if late arrivals still get through.
_ANCHOR_TOLERANCE_MINUTES = 15


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

    The minute level is checked twice over, because a stop can be perfectly
    well-formed and still wrong: :meth:`_anchor_correction` re-does the model's
    clock arithmetic against the hour it pinned the stop to, and sends the plan
    back once with the numbers when the stop provably can't be reached in time
    (#821). Only ``generate`` runs that check -- ``revise`` shares the parsing but
    not the premise, since a revised tail starts from wherever the agent has
    actually got to, not from the window's opening time.
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
        # a morning guest lecture at Irvine Auditorium" -- simply vanished.
        hours = self._hourly(persona_text, day, mem)
        stops = self._minute(persona_text, hours, mem)
        return DailyPlan(day=day, hours=hours, stops=stops)

    def revise(
        self, plan: DailyPlan, trigger=None, memory=None, clock=None
    ) -> DailyPlan:
        reason = getattr(trigger, "reason", "") or ""
        detail = getattr(trigger, "detail", "") or ""
        step = getattr(trigger, "step", 0)
        urgency = getattr(trigger, "urgency", "normal") or "normal"
        current_stop_index = getattr(trigger, "current_stop_index", None)
        mem = self._memory_block(memory, detail or "what changed", turn=step)
        if urgency == IMMEDIATE_URGENCY and isinstance(current_stop_index, int):
            return self._revise_immediate(plan, detail, current_stop_index, reason, mem)
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
            day=plan.day,
            hours=plan.hours,
            stops=stops,
            revision=plan.revision + 1,
        )

    def _revise_immediate(
        self,
        plan: DailyPlan,
        commitment: str,
        current_stop_index: int,
        reason: str,
        mem: str,
    ) -> DailyPlan:
        """Put a binding conversation commitment first in the unstarted tail.

        The tool returns ``next_stop`` separately from ``later_stops`` so its
        semantic role is machine-readable. The protected prefix comes from the
        existing plan, never from model output; cognition re-applies the same
        guard when committing it.
        """
        if not (-1 <= current_stop_index < len(plan.stops)):
            return plan
        labelled = []
        for index, stop in enumerate(plan.stops):
            if index < current_stop_index:
                status = "completed"
            elif index == current_stop_index:
                status = "current"
            else:
                status = "upcoming"
            labelled.append(f"{index}. {status}: {stop.activity} at {stop.place}")
        plan_text = "\n".join(labelled) or "(no stops)"
        user = (
            f"Your plan and its real execution position:\n{plan_text}\n"
            f"Something changed -- {reason}: {commitment}.\n"
            f"{self._memory_line(mem)}"
            f"{self._places_line()}"
            "This commitment is immediate: it starts as soon as the "
            "conversation ends. Turn it into `next_stop`. Return only what "
            "remains after the current stop in `later_stops`; do not repeat "
            "completed or current stops. `next_stop` must not carry a future "
            "start hour."
        )
        tail = self._immediate_tail_from_user(user)
        if not tail:
            return plan
        # #838 gates schedule advancement on start_hour. An immediate stop is
        # due now by definition, so a model-supplied future anchor must not
        # recreate #829 at the next seam.
        tail[0] = replace(tail[0], start_hour=None)
        stops = plan.stops[: current_stop_index + 1] + tail
        return DailyPlan(
            day=plan.day,
            hours=plan.hours,
            stops=stops,
            revision=plan.revision + 1,
            immediate_next=True,
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
        hours = self._window_hours()
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
            # #795: stops execute back-to-back from step 0, so hitting a
            # time-critical stop (e.g. a 10:00 lecture) is arithmetic the model
            # has to do itself -- nothing else in this prompt says stops run in
            # sequence or that travel time stacks on top of each one's duration.
            "Stops run back-to-back starting at the window's opening time, so "
            "each stop's minutes plus the travel to reach the next stop is what "
            "determines when that next stop begins -- choose durations that "
            "land any time-critical stop at its intended hour.\n"
            f"{self._memory_line(mem)}"
            f"Your hourly plan: {plan}.\n{self._places_line()}"
            "Turn it into concrete stops."
        )
        stops = self._minute_from_user(user)
        # #821: the model just did clock arithmetic in its head. Check it, and
        # hand back the numbers if it doesn't work out. Deliberately after
        # _minute_from_user, so the budget is spent on the stops that survived
        # validate_stops rather than on ones already dropped.
        correction = self._anchor_correction(stops)
        if correction:
            # ponytail: one corrective round, and the answer is taken as-is --
            # re-checking it would mean looping against a paid call. If real runs
            # show the retry missing too, re-check once more before squeezing the
            # durations deterministically (planning.even_step_split is right
            # there), but a silent squeeze invents stop lengths the model never
            # chose, which is what #795 argued against.
            stops = self._minute_from_user(user + correction) or stops
        return stops

    def _minute_from_user(self, user: str) -> list[Stop]:
        result = self._call(user, MINUTE_TOOL)
        return self._stops_from_entries(result.get("stops") or [])

    def _immediate_tail_from_user(self, user: str) -> list[Stop]:
        result = self._call(user, IMMEDIATE_REVISION_TOOL)
        next_stop = result.get("next_stop")
        if not isinstance(next_stop, dict):
            return []
        first = self._stops_from_entries([next_stop])
        if not first:
            return []
        later = result.get("later_stops")
        if not isinstance(later, list):
            later = []
        return first + self._stops_from_entries(later)

    def _stops_from_entries(self, entries) -> list[Stop]:
        """Parse and validate minute-shaped stop dictionaries."""
        stops = []
        # Validated upstream (#357): place/activity are strings, emoji is a
        # string-or-null, minutes an int-or-null. The one remaining check is the
        # *semantic* one -- a non-positive or null duration means "stay put"
        # -- which the schema can't express (OpenAI strict mode drops `minimum`).
        for s in entries:
            if not isinstance(s, dict):
                continue
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
                    # #821: kept raw. _anchor_correction decides what counts as
                    # a usable hour with one set-membership test, which also
                    # rejects a bool, a 99 and a -1 -- so there is nothing to
                    # guard here.
                    start_hour=s.get("start_hour"),
                )
            )
        if self.known_places:
            stops, _dropped = validate_stops(stops, self.known_places)
        return stops

    def _anchor_correction(self, stops: list[Stop]) -> str:
        """Say why a pinned stop can't be reached on time, or ``""`` if it can.

        Stops execute back-to-back from the window's opening time, so a stop the
        hourly level pinned to a clock hour is reachable only if the dwell before
        it, plus the walks between, fits in the gap. That is arithmetic the model
        was asked to do in its head (#795) and which nothing checked: in a live
        run 96 minutes of stops plus three campus walks put a 10:00 lecture at
        10:56, and the agent never arrived (#821).

        Deliberately a *lower* bound on arrival. Travel is a median
        (:func:`median_travel_minutes`), consecutive stops at the same place are
        charged no walk at all, and the first walk -- home to the first stop -- is
        not charged either, because a doorstep step is nothing like a
        cross-campus one. So this reports only "late even optimistically", never
        "early": an early projection carries no information when the real walk is
        longer than the estimate, and re-asking on one would spend a call to make
        a fine plan worse.

        Only the first *offending* anchor is reported: the later ones cascade
        from it, and fixing the first re-flows everything after it anyway. An
        anchor the plan does meet is skipped, never a stopping point -- the
        model tags each clock-pinned stop it has, and the earliest tag is
        usually the window's opening hour, which is trivially on time.
        """
        # No clock means `minutes` were read as steps (see _minute_from_user),
        # so there is no wall clock to be late against.
        if self.clock is None or self.num_steps is None:
            return ""
        hours = set(self._window_hours())
        travel = self.travel_minutes or 0  # None on the run_simulation path
        opening = self.clock.time_at(0)
        opening_minute = opening.hour * 60 + opening.minute
        for i, stop in enumerate(stops):
            # Unpinned (None), or pinned to an hour outside the run -- a model
            # error a re-ask can't repair. One membership test also disposes of
            # a bool, a 99 and a -1, so nothing here needs a type guard.
            if stop.start_hour not in hours:
                continue
            dwell, walks = 0, 0
            for k, before in enumerate(stops[:i]):
                if before.steps is None:
                    # "Stay for the rest of the day" before an anchored stop
                    # doesn't make it late, it makes it never happen -- and
                    # minutes_for_steps(None) would raise straight out of
                    # generate(), which attach_agents calls unguarded.
                    # Named, not numbered: this list is post-validate_stops, so
                    # an ordinal here can point at the wrong stop in the list
                    # the model actually wrote.
                    return (
                        f'\nThat does not work: the stop "{before.activity}" at '
                        f"{before.place} has no `minutes`, which means staying "
                        f'there for the rest of the day, so "{stop.activity}" '
                        f"at {stop.place} -- pinned to {stop.start_hour:02d}:00 "
                        f"-- never happens. Give every stop before it a "
                        f"duration in minutes.\n"
                    )
                dwell += self.clock.minutes_for_steps(before.steps)
                if stops[k + 1].place != before.place:
                    walks += travel  # consecutive stops at one place: no walk
            arrival = opening_minute + dwell + walks
            anchor = stop.start_hour * 60
            if anchor < opening_minute:
                # That hour began before the run did, so it means tomorrow's.
                # Rolling it forward keeps a window spanning midnight honest
                # without a case of its own, and makes a run that opened
                # mid-hour (08:30) read its own opening hour as far-early
                # rather than 30 minutes late -- an anchor no re-ask can meet.
                anchor += 1440
            # Plain subtraction: a circular difference would wrap an overrun of
            # more than 12 hours around into "early" and wave it through.
            late = arrival - anchor
            if late <= _ANCHOR_TOLERANCE_MINUTES:
                continue
            return (
                f'\nThat does not work: "{stop.activity}" at {stop.place} is '
                f"pinned to {stop.start_hour:02d}:00, but the stops before it "
                f"total {dwell} minutes and "
                f"the walks between them cost at least {walks} more, so you "
                f"would only get there about "
                f"{(arrival // 60) % 24:02d}:{arrival % 60:02d}. You have about "
                f"{max(0, dwell - late)} minutes of stop time to spend before "
                f"it. Redo the stops -- shorten them, or drop one -- and keep "
                f"start_hour on the pinned stop.\n"
            )
        return ""

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

    def _window_hours(self) -> list[int]:
        """The hours of the day this run actually covers, or ``[]``.

        One definition, two readers: the hourly prompt tells the model to plan
        only these, and :meth:`_anchor_correction` refuses to act on a pinned
        hour outside them. Empty unless both a clock and a run length were given
        (tests may omit them), which is also the signal that there is no window
        to check against."""
        if self.clock is None or self.num_steps is None:
            return []
        return [h for _, h in self.clock.hour_starts(self.num_steps)]

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
