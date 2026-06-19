"""Offline tests for the per-run JSONL artifact (RunLog, usage.py Piece 3).

Writes to pytest's tmp_path -- no network, no SDK. Verifies the three line kinds
(header / call / summary), the summary-on-error guarantee, and the
numbers-only-vs-verbose toggle.

    pytest tests/test_usage_artifacts.py -v
"""

import json

from text_adventure_games.usage import CallRecord, RunLog, Usage, UsageLedger


def _read_lines(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _call_through(ledger, actor="troll", response="go north"):
    """Drive one record through the ledger (fires the RunLog streaming hook)."""
    rec = CallRecord(
        usage=Usage("anthropic", "claude-haiku-4-5", input_tokens=10, output_tokens=2),
        cost_usd=0.001,
        actor=actor,
    )
    ledger.record(
        rec,
        messages=[{"role": "user", "content": "what now?"}],
        response=response,
    )


def test_runlog_writes_header_calls_and_summary(tmp_path):
    path = tmp_path / "run.jsonl"
    led = UsageLedger()
    with RunLog(str(path), provider="mock", model="mock", seed=7) as log:
        log.attach(led)
        _call_through(led, actor="troll")
        _call_through(led, actor="guard")

    lines = _read_lines(path)
    assert lines[0]["kind"] == "run"
    assert lines[0]["provider"] == "mock" and lines[0]["seed"] == 7
    assert "started_at" in lines[0]
    assert [line["kind"] for line in lines[1:3]] == ["call", "call"]
    assert lines[-1]["kind"] == "summary"
    assert lines[-1]["calls"] == 2
    assert set(lines[-1]["by_actor"]) == {"troll", "guard"}


def test_runlog_writes_summary_even_when_run_raises(tmp_path):
    path = tmp_path / "run.jsonl"
    led = UsageLedger()
    try:
        with RunLog(str(path), provider="mock", model="mock") as log:
            log.attach(led)
            _call_through(led)
            raise RuntimeError("boom mid-run")
    except RuntimeError:
        pass  # the context manager must not suppress it
    lines = _read_lines(path)
    assert lines[0]["kind"] == "run"
    assert lines[-1]["kind"] == "summary"  # still written on the way out


def test_log_prompts_toggles_verbose_fields(tmp_path):
    # Numbers-only by default.
    quiet = tmp_path / "quiet.jsonl"
    led_q = UsageLedger()
    with RunLog(str(quiet), provider="mock", model="mock") as log:
        log.attach(led_q)
        _call_through(led_q)
    call = [line for line in _read_lines(quiet) if line["kind"] == "call"][0]
    assert "messages" not in call and "response" not in call
    assert "cost_usd" in call and "input_tokens" in call  # numbers always present

    # Verbose includes the transcript.
    loud = tmp_path / "loud.jsonl"
    led_l = UsageLedger()
    with RunLog(str(loud), provider="mock", model="mock", log_prompts=True) as log:
        log.attach(led_l)
        _call_through(led_l, response="go north")
    call = [line for line in _read_lines(loud) if line["kind"] == "call"][0]
    assert call["messages"] == [{"role": "user", "content": "what now?"}]
    assert call["response"] == "go north"


def test_runlog_detaches_hook_on_close(tmp_path):
    # After the artifact closes, a reused ledger must not write to a closed file.
    path = tmp_path / "run.jsonl"
    led = UsageLedger()
    with RunLog(str(path), provider="mock", model="mock") as log:
        log.attach(led)
        _call_through(led)
    assert led._on_record is None
    _call_through(led)  # would raise if the closed file's hook were still wired
