"""LLM-scored memory importance / poignancy (issue #583).

A backend-side scoring pass replaces the hardcoded importance constants with
model-scored 1-10 poignancy, batched into one call per agent-tick, with the
constants as the fallback floor and a hard no-op for the mock brain.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_importance_scoring_583.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_conversation_consequences_582.py: the Penn sim modules
# run as scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.prompt_templates import render  # noqa: E402


def test_importance_score_prompt_renders_the_batch():
    # Pin the exact rendered output (repo convention: prompt renders are pinned
    # verbatim, like test_conversation_consequences_582 / test_decide_context), so
    # a reworded template can't drift past a substring check.
    text = render(
        "importance_score",
        memories=[
            {"id": 0, "text": "I traveled to the Cafe."},
            {"id": 1, "text": "I saw Ayesha nearby."},
        ],
    )
    assert text == (
        "Rate how significant each of these memories is to you, from 1 "
        "(mundane) to 10 (momentous):\n"
        "\n"
        "[0] I traveled to the Cafe.\n"
        "[1] I saw Ayesha nearby.\n"
        "\n"
        "Then call score_memories with a 1-10 score for every id above."
    )
