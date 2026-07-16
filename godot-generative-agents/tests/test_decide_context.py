"""The decide-prompt context block (issue #580).

Pins the always-on context slice a live brain gets on every decision --
sim time, the plan's current stop, elapsed time on it -- and the plumbing
that renders it only when the step loop threads a SimClock, so the
deterministic mock bake stays byte-identical.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_decide_context.py -v
"""

import datetime
import sys
from pathlib import Path

# Same import shim as test_cognition_wiring.py: the Penn sim modules are run
# as scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.prompt_templates import render  # noqa: E402

# ------------------------------------------------------- the pinned wording


def test_render_pins_the_full_block():
    assert render(
        "decide_context",
        time="Monday 12:05 PM",
        place="Houston Hall",
        activity="eating lunch",
        minutes=40,
        elapsed=15,
    ) == (
        "Right now it is Monday 12:05 PM.\n"
        "Your plan's current stop: eating lunch at Houston Hall (planned ~40 min). "
        "You have been on this stop for 15 min."
    )


def test_render_drops_the_optional_clauses():
    # minutes=None: the schedule says stay indefinitely -- no planned clause.
    # elapsed=0: the stop just began -- no elapsed sentence.
    assert render(
        "decide_context",
        time="Monday 08:00 AM",
        place="The Quad",
        activity="stretching",
        minutes=None,
        elapsed=0,
    ) == (
        "Right now it is Monday 08:00 AM.\n"
        "Your plan's current stop: stretching at The Quad."
    )
