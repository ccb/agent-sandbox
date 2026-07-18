"""Offline smoke for the #595 experiment harness: it runs end-to-end under the
scripted brain (no key), the outcome classifier is exercised, and a report is
produced. The research CLAIM (rate above control) is a manual, keyed run -- not
asserted here. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_boil_from_memory.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.penn.experiments.boil_from_memory import (  # noqa: E402
    classify_outcome,
    run_arm,
)
from backend.penn.scripted_brain import build_scripted_brains  # noqa: E402


class _C:
    def __init__(self, **props):
        self._p = props

    def get_property(self, k):
        return self._p.get(k, False)


def test_classify_outcome_reads_the_authoritative_flags():
    assert classify_outcome(_C(drank_boiled=1, drank_unboiled=0)) == "boiled_then_drank"
    assert classify_outcome(_C(drank_unboiled=1)) == "drank_raw"
    assert classify_outcome(_C()) == "neither"


def test_run_arm_smoke_with_scripted_brain():
    # A single scripted trial runs the whole harness plumbing offline.
    result = run_arm(
        seeded=True,
        trials=1,
        steps=20,
        make_client=lambda ledger: build_scripted_brains(ledger=ledger)[0],
    )
    assert set(result) >= {"boiled_then_drank", "drank_raw", "neither", "rate"}
    assert result["boiled_then_drank"] + result["drank_raw"] + result["neither"] == 1
