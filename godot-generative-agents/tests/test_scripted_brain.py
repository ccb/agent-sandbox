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


from text_adventure_games.llm_client import ToolCallResult  # noqa: E402
from scripted_brain import ScriptedPennBrain  # noqa: E402


class _FakeSchedule:
    """Minimal stand-in for ScheduleMockClient's read surface."""

    def __init__(self, destination, activity):
        self.destination = destination
        self.activity = activity


def _decide_tools():
    # The two universal Penn verbs, shaped like action_tools_for's output.
    return [
        {
            "name": "travel",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "enum": ["Hobbs Cafe"]},
                    "reasoning": {"type": "string"},
                },
            },
        },
        {
            "name": "perform",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
            },
        },
    ]


def _call(brain, observation):
    brain.context["actor"] = "Maya"
    return brain.call_tools(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": observation},
        ],
        _decide_tools(),
        tool_choice="any",
    )


def test_decide_travels_when_not_yet_at_the_scheduled_place():
    brain = ScriptedPennBrain()
    brain.register_schedule("Maya", _FakeSchedule("Hobbs Cafe", "reading"))
    result = _call(brain, "THE GREEN\nsome description")  # first line != destination
    assert isinstance(result, ToolCallResult)
    call = result.tool_calls[0]
    assert call["name"] == "travel"
    assert call["arguments"]["destination"] == "Hobbs Cafe"


def test_decide_performs_when_already_at_the_scheduled_place():
    brain = ScriptedPennBrain()
    brain.register_schedule("Maya", _FakeSchedule("Hobbs Cafe", "reading"))
    result = _call(brain, "HOBBS CAFE\nsome description")  # first line == destination
    call = result.tool_calls[0]
    assert call["name"] == "perform"
    assert call["arguments"]["activity"] == "reading"


def test_decide_is_deterministic_and_pure_of_call_order():
    brain = ScriptedPennBrain()
    brain.register_schedule("Maya", _FakeSchedule("Hobbs Cafe", "reading"))
    a = _call(brain, "THE GREEN\nx").tool_calls[0]
    b = _call(brain, "THE GREEN\nx").tool_calls[0]
    assert a == b  # same prompt -> same call, no hidden counter
