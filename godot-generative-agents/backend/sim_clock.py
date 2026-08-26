"""Map the sim's step counter onto clock time (issue #83, NEXT-STEPS Phase D §10).

The sim runs on a fine, continuous-ish clock -- one step is ``sec_per_step``
seconds (10 by default), and the run starts at a real ``start_dt`` -- while plans
are authored in *clock time* (hours of the day). :class:`SimClock` is the single
conversion between the two, so "plan in hours" and "drive in steps" never drift
apart (the goal of design doc §10).

Why not the engine's :class:`~text_adventure_games.clock.GameClock`? That clock
works in whole *minutes per turn* and has no wall-clock ``datetime`` anchor; the
port needs *seconds per step* and the same ``start_dt + step * sec_per_step``
instant the exporter already stamps onto every frame. :class:`SimClock` is that
formula, named and reusable, kept as pure data with no engine imports.

One shared :class:`SimClock` now drives the loop's clock-gated behavior: the
plan revision triggers in ``run_simulation.step()`` and the decide-context
block (#580) -- ``serve_penn`` threads it through every live tick too.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

SECONDS_PER_HOUR = 3600


@dataclass(frozen=True)
class SimClock:
    """Convert between sim steps and clock time for one run.

    ``start_dt`` is the in-game time at step 0; ``sec_per_step`` is how many
    seconds of in-game time each step advances (matches
    ``run_simulation``'s ``--sec-per-step`` and ``exporter.SEC_PER_STEP``).
    Stateless: every method derives its answer from ``(start_dt, sec_per_step)``
    and a step number -- the loop owns the actual step counter.
    """

    start_dt: datetime.datetime
    sec_per_step: int = 15

    def __post_init__(self):
        if self.sec_per_step <= 0:
            raise ValueError(f"sec_per_step must be positive, got {self.sec_per_step}")

    def time_at(self, step: int) -> datetime.datetime:
        """The in-game wall-clock time at ``step``.

        Identical to the instant ``exporter.write_simulation`` stamps onto frame
        ``step`` (``start_dt + step * sec_per_step`` seconds), so the navbar time,
        a memory's timestamp, and a plan's clock all agree.
        """
        return self.start_dt + datetime.timedelta(seconds=step * self.sec_per_step)

    def hour_at(self, step: int) -> int:
        """The hour of day (0-23) at ``step`` -- which hour block the agent is in."""
        return self.time_at(step).hour

    def steps_for_seconds(self, seconds: int) -> int:
        """How many whole steps fit in ``seconds`` of in-game time.

        The fundamental duration conversion: a plan that wants an activity to last
        ``seconds`` (or an hour, via :attr:`steps_per_hour`) becomes this many
        ``Stop.steps``. Floor division, so it never over-runs the budget.
        """
        if seconds < 0:
            raise ValueError(f"seconds must be >= 0, got {seconds}")
        return seconds // self.sec_per_step

    def minutes_for_steps(self, steps: int) -> int:
        """How many whole minutes ``steps`` spans -- the reverse conversion.

        The decide-context block (#580) phrases stop durations in minutes;
        keeping the arithmetic here (not inlined at call sites) preserves this
        class as the single steps<->time conversion point.
        """
        if steps < 0:
            raise ValueError(f"steps must be >= 0, got {steps}")
        return steps * self.sec_per_step // 60

    @property
    def steps_per_hour(self) -> int:
        """Steps in one in-game hour (360 at the 10s/step default).

        The budget hourly -> minute decomposition (design doc §7) splits across a
        block's stops via ``planning.even_step_split``.
        """
        return self.steps_for_seconds(SECONDS_PER_HOUR)

    def hour_starts(self, num_steps: int) -> list[tuple[int, int]]:
        """The ``(step, hour_of_day)`` at the start of each hour the run spans.

        Step 0 first, then every :attr:`steps_per_hour` while still inside the
        run. This is the spine of the day -> hourly decomposition: one
        :class:`~text_adventure_games.planning.HourBlock` per entry, each tagged
        with the hour-of-day to plan for and the step it begins at.

        A run shorter than an hour still yields the opening ``(0, start_hour)``.
        """
        if num_steps <= 0:
            return []
        per_hour = self.steps_per_hour
        return [(step, self.hour_at(step)) for step in range(0, num_steps, per_hour)]
