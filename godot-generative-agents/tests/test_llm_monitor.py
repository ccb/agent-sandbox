"""The terminal LLM-request monitor (backend/llm_monitor.py).

Pins the contracts the live-LLM MVP stands on:

* :class:`RoleTaggedLedger` is a WRITE-THROUGH view -- every record lands in
  the shared base ledger first (so ``GET /usage``, the cost kill-switch, and
  an attached ``RunLog`` see exactly what they always did), and only then is
  a line printed;
* role attribution is static for single-role clients and live (via
  ``bind_context``) for the shared decide/converse brain client;
* a broken monitor can never break, or lose the accounting of, a model call;
* ``serve_penn.PennStepper`` wires the monitor so the deterministic mock brain
  already exercises the whole path offline, and the call counter survives
  ``reset()`` alongside the ledger.

Fully offline (mock clients record zero-cost usage). Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_llm_monitor.py -v
"""

import io
import json
import sys
from pathlib import Path

# serve_penn / penn_world live in the Godot tree and are run as scripts (no
# package); import them off backend/penn/, the way test_penn_live.py does.
_PENN_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_PENN_DIR))

from backend.llm_monitor import LlmCallMonitor, RoleTaggedLedger  # noqa: E402
from text_adventure_games.llm_client import MockLlmClient  # noqa: E402
from text_adventure_games.usage import (  # noqa: E402
    CallRecord,
    RunLog,
    Usage,
    UsageLedger,
)


def _view(role="decide", stream=None, base=None):
    """A (base ledger, monitor, view) triple wired the way serve_penn does it."""
    base = base or UsageLedger()
    monitor = LlmCallMonitor(stream=stream or io.StringIO())
    return base, monitor, RoleTaggedLedger(base, monitor, role)


# ---------------------------------------------------------- write-through


def test_records_land_in_the_base_ledger_not_the_view():
    stream = io.StringIO()
    base, monitor, view = _view(stream=stream)
    client = MockLlmClient(["hello"], ledger=view)
    assert client.chat([{"role": "user", "content": "hi"}]) == "hello"
    assert len(base.records) == 1  # the base is the single source of truth
    assert view.records == []  # the view is a conduit, never a store
    assert monitor.calls == 1
    (line,) = [l for l in stream.getvalue().splitlines() if l.lstrip().startswith("#")]
    assert "decide" in line and "mock" in line
    assert f"Σ ${base.total_cost_usd():.6f}" in line  # printed total == /usage total


def test_summary_and_kill_switch_read_the_base():
    base = UsageLedger(max_cost_usd=5.0)
    _, _, view = _view(base=base)
    client = MockLlmClient(["ok"], ledger=view)
    client.chat([{"role": "user", "content": "hi"}])
    assert base.summary()["calls"] == 1
    assert not base.over_budget()  # mock is free; the ceiling is the base's job


# -------------------------------------------------------- role attribution


def test_static_role_tags_single_role_clients():
    stream = io.StringIO()
    _, _, view = _view(role="reflect", stream=stream)
    MockLlmClient(["insight"], ledger=view).chat([{"role": "user", "content": "?"}])
    assert "reflect" in stream.getvalue()


def test_bound_context_resolves_the_role_per_call():
    # The brain client is shared between decide and converse; the call sites
    # stamp context["role"] per call and the view reads it live.
    stream = io.StringIO()
    _, _, view = _view(role="decide", stream=stream)
    client = MockLlmClient(["a", "b", "c"], ledger=view)
    view.bind_context(client.context)

    client.context.update({"actor": "Diego Torres", "turn": 3, "role": "decide"})
    client.chat([{"role": "user", "content": "?"}])
    client.context.update({"actor": "Diego Torres", "turn": 4, "role": "converse"})
    client.chat([{"role": "user", "content": "?"}])
    client.context.pop("role")  # no stamp -> the static tag is the fallback
    client.chat([{"role": "user", "content": "?"}])

    lines = [l for l in stream.getvalue().splitlines() if l.lstrip().startswith("#")]
    # A row splits to ["#", "<n>", "<time>", "<role>", ...].
    assert [l.split()[3] for l in lines] == ["decide", "converse", "decide"]


# ------------------------------------------------------------- resilience


def test_a_broken_monitor_never_breaks_or_loses_the_call():
    class _Boom(io.StringIO):
        def write(self, *_):
            raise RuntimeError("terminal went away")

    base, _, view = _view(stream=_Boom())
    client = MockLlmClient(["still fine"], ledger=view)
    assert client.chat([{"role": "user", "content": "hi"}]) == "still fine"
    assert len(base.records) == 1  # delegate-first: the record was stored


def test_runlog_coexists_with_the_monitor(tmp_path):
    # RunLog owns the base ledger's _on_record hook; the monitor must not
    # claim it. One call -> exactly one JSONL "call" line AND one printed row.
    stream = io.StringIO()
    base, monitor, view = _view(stream=stream)
    path = tmp_path / "run.jsonl"
    with RunLog(str(path), provider="mock", model="mock") as log:
        log.attach(base)
        MockLlmClient(["hi"], ledger=view).chat([{"role": "user", "content": "?"}])
    kinds = [json.loads(l)["kind"] for l in path.read_text().splitlines()]
    assert kinds.count("call") == 1
    assert monitor.calls == 1


# -------------------------------------------------------------- formatting


def _rec(
    actor: str | None = "Diego Torres",
    turn: int | None = 118,
    latency_ms: float | None = 731.0,
):
    usage = Usage(
        provider="anthropic",
        model="claude-haiku-4-5",
        input_tokens=176,
        output_tokens=102,
        cache_creation_input_tokens=912,
        cache_read_input_tokens=0,
    )
    return CallRecord(
        usage=usage, cost_usd=0.001238, turn=turn, actor=actor, latency_ms=latency_ms
    )


def test_row_contents():
    line = LlmCallMonitor._fmt_row(7, "12:05:02", "decide", _rec(), 0.02141)
    for token in (
        "#    7",
        "12:05:02",
        "decide",
        "Diego Torres",
        "t  118",
        "claude-haiku-4-5",
        "in   1088",  # 176 uncached + 912 cache-write + 0 cache-read
        "912w/",
        "out  102",
        "731ms",
        "$0.001238",
        "Σ $0.021410",
    ):
        assert token in line, f"missing {token!r} in {line!r}"


def test_row_placeholders_for_missing_fields():
    # The mock provider reports no latency; attach-time calls have no turn.
    line = LlmCallMonitor._fmt_row(
        1, "00:00:00", "plan", _rec(actor=None, turn=None, latency_ms=None), 0.0
    )
    assert " -" in line and "t    -" in line


def test_columns_align_across_rows():
    # The whole point of the fixed widths: every field starts at the same
    # column no matter how the values vary row to row.
    a = LlmCallMonitor._fmt_row(1, "09:00:00", "decide", _rec(), 0.001238)
    b = LlmCallMonitor._fmt_row(
        999, "09:00:01", "converse", _rec(actor="S", turn=0, latency_ms=None), 1.25
    )
    assert a.index("Σ") == b.index("Σ")
    assert a.index("claude-haiku-4-5") == b.index("claude-haiku-4-5")


def test_drain_returns_then_clears_the_buffer():
    _, monitor, view = _view()
    client = MockLlmClient(["x", "y"], ledger=view)
    client.chat([{"role": "user", "content": "?"}])
    client.chat([{"role": "user", "content": "?"}])
    drained = monitor.drain()
    assert [d["call_no"] for d in drained] == [1, 2]
    # Everything a viewer needs to render the terminal's row rides the record.
    assert {"role", "cum_cost_usd", "model", "time"} <= set(drained[0])
    assert monitor.drain() == []  # cleared


# ------------------------------------------------- PennStepper integration


def test_stepper_monitor_prints_mock_decides_and_survives_reset():
    from penn_world import build_penn_world
    from serve_penn import PennStepper

    stream = io.StringIO()
    monitor = LlmCallMonitor(stream=stream)
    stepper = PennStepper(num_steps=5, world=build_penn_world(), monitor=monitor)
    stepper.tick()
    # Step 0: every agent is idle -> one decide record (and one line) each.
    assert monitor.calls == len(stepper.order)
    assert len(stepper.ledger.records) == len(stepper.order)
    out = stream.getvalue()
    for name in stepper.order:
        assert name[:18] in out
    assert "decide" in out and "Σ $0.000000" in out  # the mock brain is free

    before = monitor.calls
    stepper.reset()
    assert stepper.monitor.calls == before  # counter survives, like the ledger
    stepper.tick()
    assert monitor.calls == before + len(stepper.order)  # and keeps counting
