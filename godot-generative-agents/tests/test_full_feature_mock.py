"""End-to-end feature coverage for the scripted mock brain (#563).

Runs the Penn stepper on --brain scripted to completion and asserts every
llm_client-gated feature is actually POPULATED (not merely contract-shaped):
the tool loop, cognition tools, conversation (CHAT memories), reflection, and a
non-empty usage ledger. This is the test that goes red when the offline mock
drifts behind the backend again. Fully offline -- no keys, no spend.

    uv run pytest godot-generative-agents/tests/test_full_feature_mock.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402
from serve_penn import PennStepper  # noqa: E402
from backend.cognition import memory_stream_for_persona  # noqa: E402
from text_adventure_games.memory import MemoryKind  # noqa: E402


def _run(steps=400):
    stepper = PennStepper(num_steps=steps, llm=serve_penn.SCRIPTED)
    # Post-#662 recalibration: with perception tile-gated, this scripted day
    # accrues slightly less importance than the old room-granular one -- the
    # second Diego/Sofia conversation used to fire across 19 tiles of Irvine
    # Auditorium (exactly the #662 bug) and its CHAT importance was what pushed
    # the day over the engine's default reflection threshold (30). The
    # legitimate day tops out just under it, so pin the per-agent threshold
    # (the documented ``maybe_reflect`` seam) at a level this day reaches.
    for char in stepper.chars.values():
        char.agent.reflection_threshold = 25.0
    for _ in range(steps):
        stepper.tick()
    return stepper


def _all_memories(stepper):
    out = []
    for char in stepper.chars.values():
        out.extend(memory_stream_for_persona(char.agent))
    return out


def test_scripted_run_populates_every_gated_feature():
    stepper = _run()

    # 1. The brain reached the per-verb tool loop (decide went through call_tools).
    assert stepper.llm_client.tool_calls_log, "brain never reached the tool loop"

    # 2. Cognition tools were offered, and a recall call was actually returned
    #    (a request whose messages carry a recall tool_result proves round 2 ran).
    offered_recall = any(
        "recall" in {t.get("name") for t in c["tools"]}
        for c in stepper.llm_client.tool_calls_log
    )
    assert offered_recall, "cognition tools never offered"
    used_recall = any(
        isinstance(m.get("content"), list)
        and any(b.get("type") == "tool_result" for b in m["content"])
        for c in stepper.llm_client.tool_calls_log
        for m in c["messages"]
    )
    assert used_recall, "cognition tool (recall) never actually ran"

    mems = _all_memories(stepper)
    kinds = {m["kind"] for m in mems}

    # 3. Conversation produced CHAT memories (real converse ran, not the injector).
    assert MemoryKind.CHAT.value in kinds, "no CHAT memories -- conversation dark"

    # 4. Reflection wrote memories. The recalibrated threshold (25, see _run)
    #    is only honest while the legitimate day accrues in the 25-30 band:
    #    above the pinned threshold, below the engine default of 30 that the
    #    phantom Irvine conversation used to cross. Assert the band directly so
    #    a future importance-weighting change fails HERE, at the real
    #    invariant, instead of silently hollowing out the reflection assert --
    #    if this trips, re-derive the threshold rather than patching either
    #    assert (#669 review).
    day_totals = {}
    for char in stepper.chars.values():
        stream = memory_stream_for_persona(char.agent)
        day_totals[char.name] = sum(
            m["importance"] for m in stream if m["kind"] != MemoryKind.REFLECTION.value
        )
    top = max(day_totals.values())
    assert 25 <= top < 30, f"day importance profile drifted: {day_totals}"
    assert MemoryKind.REFLECTION.value in kinds, "no reflection memories"

    # 5. The usage ledger is non-empty (GET /usage surface populated offline).
    assert stepper.ledger.summary()["calls"] > 0, "empty usage ledger"


def test_scripted_run_is_deterministic():
    a = _run(steps=120)
    b = _run(steps=120)
    # Same seed/run -> identical memory streams (spot-check the texts).
    assert [m["text"] for m in _all_memories(a)] == [
        m["text"] for m in _all_memories(b)
    ]
