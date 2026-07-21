"""Per-decision cognition trace at the gate (issue #359): the step loop builds
``st["trace"]`` = the brain's cognition consults (stashed on the agent by
``decide_with_action_tools``, Task 4) followed by the terminal
``{"kind": "action", "tool": <verb>, "ok": <gate result>}`` entry.

Fully offline, pure-function test. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_tool_trace_359.py -v
"""


def test_decision_trace_appends_action_entry():
    from backend.run_simulation import _decision_trace

    class A:  # a stand-in agent with consult trace
        last_trace = [{"kind": "recall", "arg": "'x'", "hits": 2}]

    t = _decision_trace(A(), "travel to UPenn:Library", ok=True)
    assert t[-1] == {"kind": "action", "tool": "travel", "ok": True}
    assert t[0]["kind"] == "recall"  # consults come first

    # A blocked decision with no consults (the mock's shape): one action entry.
    class B:
        last_trace = []

    assert _decision_trace(B(), "climb wall", ok=False) == [
        {"kind": "action", "tool": "climb", "ok": False}
    ]

    # Never crash without a command / without last_trace.
    assert _decision_trace(object(), "", ok=True) == [
        {"kind": "action", "tool": "", "ok": True}
    ]
