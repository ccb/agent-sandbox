"""Smallville planners (issue #83, NEXT-STEPS Phase D).

The engine defines *what a plan is* and *how it is manipulated*
(``text_adventure_games.planning``); this module is the Smallville-specific
*cognition* that fills one in, behind the engine's :class:`Planner` protocol.

Two implementations are planned, mirroring the brain split in
``smallville_agents.py`` (mock vs. real LLM):

* :class:`MockPlanner` -- **the default, offline, deterministic planner.** It
  reproduces a persona's hand-authored ``world_data.yaml`` schedule exactly, so a
  default ``run_simulation`` produces byte-identical ``movement/*.json``. The YAML
  schedules become the mock's *fixture* rather than the only source of truth.
* ``LLMPlanner`` -- generates and revises real day -> hourly -> minute plans from
  identity + memory (rides on Phase A; not built yet, see
  ``docs/design/daily-planning.md`` §6-§9).

Scaffolding note: :class:`MockPlanner` is **not wired into the step loop yet** --
constructing one and calling :meth:`generate` is inert and changes no exported
frame. Wiring it through ``attach_agents`` / ``simulate`` (build-order step 3) is
the deliberate, determinism-critical follow-up.
"""

from __future__ import annotations

from text_adventure_games.planning import DailyPlan, Stop


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
        plans from the fixture alone, the way the current ``SmallvilleMockClient``
        decides from location alone.
        """
        return DailyPlan(stops=list(self._stops))

    def revise(
        self, plan: DailyPlan, trigger=None, memory=None, clock=None
    ) -> DailyPlan:
        """No-op: the static schedule never re-plans (keeps the replay identical)."""
        return plan
