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


def _tool_result_msg():
    # Shape run_tool_loop appends after a cognition call (see test_cognition_wiring).
    return {
        "role": "user",
        "content": [{"type": "tool_result", "is_error": False, "content": "a memory"}],
    }


def test_decide_recalls_first_then_acts_when_cognition_offered():
    brain = ScriptedPennBrain()
    brain.register_schedule("Maya", _FakeSchedule("Hobbs Cafe", "reading"))
    tools = _decide_tools() + [
        {
            "name": "recall",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        }
    ]
    brain.context["actor"] = "Maya"
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "THE GREEN\nx"},
    ]
    # Round 1: no tool_result yet -> recall.
    first = brain.call_tools(msgs, tools, tool_choice="any")
    assert first.tool_calls[0]["name"] == "recall"
    # Round 2: a tool_result is present -> the action.
    first_round_call = first.tool_calls[0]
    msgs2 = msgs + [
        {"role": "assistant", "content": [{"type": "tool_use", "name": "recall"}]},
        _tool_result_msg(),
    ]
    second = brain.call_tools(msgs2, tools, tool_choice="any")
    assert second.tool_calls[0]["name"] == "travel"


def test_converse_branch_speaks_when_speak_is_offered():
    brain = ScriptedPennBrain()
    brain.context["actor"] = "Maya"
    speak_tool = {
        "name": "speak",
        "parameters": {
            "type": "object",
            "properties": {
                "utterance": {"type": "string"},
                "done": {"type": "boolean"},
            },
        },
    }
    result = brain.call_tools(
        [{"role": "user", "content": "Priya is here."}], [speak_tool], tool_choice="any"
    )
    call = result.tool_calls[0]
    assert call["name"] == "speak"
    assert call["arguments"]["utterance"]  # non-empty line
    assert call["arguments"]["done"] is True


def test_call_tool_speak_fallback_returns_an_utterance():
    brain = ScriptedPennBrain()
    brain.context["actor"] = "Maya"
    speak_tool = {
        "name": "speak",
        "parameters": {
            "type": "object",
            "properties": {"utterance": {"type": "string"}},
        },
    }
    result = brain.call_tool([{"role": "user", "content": "hi"}], speak_tool)
    assert result["utterance"]


from scripted_brain import build_scripted_brains  # noqa: E402
from text_adventure_games.reflection import (
    SALIENT_QUESTIONS_TOOL,
    INSIGHT_TOOL,
)  # noqa: E402


def test_build_scripted_brains_returns_brain_and_reflector():
    brain, reflector = build_scripted_brains()
    assert isinstance(brain, ScriptedPennBrain)
    q = reflector.call_tool(
        [{"role": "user", "content": "recent memories"}], SALIENT_QUESTIONS_TOOL
    )
    assert isinstance(q["questions"], list) and q["questions"]
    i = reflector.call_tool(
        [{"role": "user", "content": "question + memories"}], INSIGHT_TOOL
    )
    assert i["insight"] and isinstance(i["evidence"], list)


def test_scripted_brains_share_a_ledger_when_passed_one():
    from text_adventure_games.usage import UsageLedger

    ledger = UsageLedger()
    brain, reflector = build_scripted_brains(ledger=ledger)
    assert brain.ledger is ledger and reflector.ledger is ledger


from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents  # noqa: E402

_LOCATIONS = [
    {"name": "The Green", "description": "lawn", "address": None, "hub": True},
    {"name": "Cafe", "description": "coffee", "address": "T:Cafe:counter"},
]


def _personas():
    return [
        {
            "name": "Ada",
            "home": "The Green",
            "persona": "I am Ada.",
            "emoji": "\U0001f4d6",
            "start_tile": [0, 0],
            "destination": "Cafe",
            "activity": "reading",
            "schedule": [
                {
                    "place": "Cafe",
                    "activity": "reading",
                    "emoji": "\U0001f4d6",
                    "steps": None,
                }
            ],
        }
    ]


def test_attach_agents_registers_schedules_on_a_scripted_brain():
    brain, _ = build_scripted_brains()
    personas = _personas()
    chars = build_world(None, personas, _LOCATIONS)[1]
    attach_agents(chars, personas, llm_client=brain, cognition_tools=True)
    assert "Ada" in brain._schedules
    assert brain._schedules["Ada"] is chars["Ada"].agent.schedule


def test_attach_agents_is_a_noop_for_a_client_without_register_schedule():
    from text_adventure_games.llm_client import MockLlmClient

    plain = MockLlmClient()  # no register_schedule -> must not raise
    personas = _personas()
    chars = build_world(None, personas, _LOCATIONS)[1]
    attach_agents(chars, personas, llm_client=plain)  # no error


from serve_penn import PennStepper  # noqa: E402


def test_stepper_under_scripted_wires_the_scripted_brains():
    stepper = PennStepper(num_steps=5, llm=serve_penn.SCRIPTED)
    assert isinstance(stepper.llm_client, ScriptedPennBrain)
    assert stepper.reflector_client is not None
    assert stepper.cognition_tools is True
    # The brain got its schedules from _build -> attach_agents.
    assert stepper.llm_client._schedules
    # Both clients record into the run ledger.
    assert stepper.llm_client.ledger is stepper.ledger
    # self.llm is the "scripted" sentinel (a truthy string, not a dict) --
    # meta()'s "llm" field must treat it as free (_is_paid), not index into
    # it like a real llm: dict, or this raises TypeError (#563 review nit).
    assert stepper.meta()["llm"] is None


def test_stepper_default_mock_is_still_brainless():
    stepper = PennStepper(num_steps=5)  # --brain mock
    assert stepper.llm_client is None
    assert stepper.reflector_client is None
