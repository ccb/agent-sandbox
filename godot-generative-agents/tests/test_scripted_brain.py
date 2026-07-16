"""The scripted full-feature mock brain (#563): a deterministic, key-free brain
that reaches every llm_client-gated Penn path. Fully offline. Run from the repo
root::

    uv run pytest godot-generative-agents/tests/test_scripted_brain.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_penn_live.py: the Penn sim modules are run as scripts.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402


def test_resolve_llm_scripted_is_a_distinct_keyless_outcome():
    # scripted is neither the mock None nor a paid dict.
    assert serve_penn.resolve_llm(None, "scripted") == serve_penn.SCRIPTED
    assert serve_penn.resolve_llm(None, "mock") is None
    assert serve_penn._is_paid(serve_penn.resolve_llm(None, "scripted")) is False
    assert serve_penn._is_paid(None) is False
    # scripted needs no key even if the world declares an llm block.
    assert (
        serve_penn.resolve_llm({"provider": "anthropic"}, "scripted")
        == serve_penn.SCRIPTED
    )
