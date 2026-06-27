"""Offline unit tests for the LLM usage/cost layer (usage.py).

No SDK, no network, no API key: the data model, the price table, the ledger, and
the shared record helper are all pure Python. The mock path records a zero-cost
Usage, which is how the accounting path is exercised for free.

    pytest tests/test_usage.py -v
"""

from types import SimpleNamespace

import pytest

from text_adventure_games import usage
from text_adventure_games.usage import (
    CallRecord,
    Usage,
    UsageLedger,
    price,
    prompt_sha256,
    record_call,
)

# --- Usage --------------------------------------------------------------


def test_total_input_tokens_sums_uncached_write_and_read():
    u = Usage(
        provider="anthropic",
        model="claude-haiku-4-5",
        input_tokens=100,
        cache_creation_input_tokens=20,
        cache_read_input_tokens=5,
    )
    assert u.total_input_tokens == 125


def test_from_openai_maps_prompt_and_completion_tokens():
    raw = SimpleNamespace(prompt_tokens=300, completion_tokens=40)
    u = Usage.from_openai("gpt-4o-mini", raw)
    assert (u.input_tokens, u.output_tokens) == (300, 40)
    # OpenAI has no cache fields.
    assert u.cache_creation_input_tokens == 0 and u.cache_read_input_tokens == 0


def test_from_anthropic_reads_cache_fields_defensively():
    # A response with no cache fields (caching off) still maps cleanly to 0.
    raw = SimpleNamespace(input_tokens=400, output_tokens=18)
    u = Usage.from_anthropic("claude-haiku-4-5", raw)
    assert (u.input_tokens, u.output_tokens) == (400, 18)
    assert u.cache_read_input_tokens == 0

    raw2 = SimpleNamespace(
        input_tokens=10, output_tokens=5, cache_read_input_tokens=390
    )
    u2 = Usage.from_anthropic("claude-haiku-4-5", raw2)
    assert u2.cache_read_input_tokens == 390


def test_none_raw_usage_yields_zero_record():
    assert Usage.from_openai("gpt-4o-mini", None).input_tokens == 0
    assert Usage.from_anthropic("claude-haiku-4-5", None).input_tokens == 0


# --- price() ------------------------------------------------------------


def test_price_input_and_output_at_table_rates():
    # haiku-4-5 = $1/$5 per 1M tokens.
    u = Usage("anthropic", "claude-haiku-4-5", input_tokens=1_000_000)
    assert price("claude-haiku-4-5", u) == pytest.approx(1.0)
    u2 = Usage("anthropic", "claude-haiku-4-5", output_tokens=1_000_000)
    assert price("claude-haiku-4-5", u2) == pytest.approx(5.0)


def test_price_cache_write_and_read_multipliers():
    # Cache write = 1.25x input (5m) / 2x (1h); cache read = 0.10x input.
    write = Usage(
        "anthropic", "claude-haiku-4-5", cache_creation_input_tokens=1_000_000
    )
    assert price("claude-haiku-4-5", write) == pytest.approx(1.25)
    assert price("claude-haiku-4-5", write, ttl="1h") == pytest.approx(2.0)
    read = Usage("anthropic", "claude-haiku-4-5", cache_read_input_tokens=1_000_000)
    assert price("claude-haiku-4-5", read) == pytest.approx(0.10)


def test_price_unknown_model_warns_once_and_costs_zero(capsys):
    usage._PRICE_WARNED.discard("totally-made-up-model")
    u = Usage("anthropic", "totally-made-up-model", input_tokens=1_000_000)
    assert price("totally-made-up-model", u) == 0.0
    out = capsys.readouterr().out
    assert "no price" in out and "totally-made-up-model" in out
    # Second call for the same model is silent (warn once over a long run).
    price("totally-made-up-model", u)
    assert capsys.readouterr().out == ""


# --- UsageLedger --------------------------------------------------------


def _rec(actor, cost, turn=0):
    return CallRecord(
        usage=Usage("mock", "mock"), cost_usd=cost, actor=actor, turn=turn
    )


def test_ledger_totals_and_by_actor():
    led = UsageLedger()
    led.record(_rec("troll", 0.10))
    led.record(_rec("troll", 0.05))
    led.record(_rec("guard", 0.20))
    assert led.total_cost_usd() == pytest.approx(0.35)
    assert led.totals_by_actor() == pytest.approx({"troll": 0.15, "guard": 0.20})


def test_ledger_unattributed_calls_land_under_one_key():
    led = UsageLedger()
    led.record(CallRecord(usage=Usage("mock", "mock"), cost_usd=0.0))
    assert "(unattributed)" in led.totals_by_actor()


def test_ledger_summary_shape():
    led = UsageLedger()
    led.record(
        CallRecord(
            usage=Usage(
                "anthropic", "claude-haiku-4-5", input_tokens=10, output_tokens=2
            ),
            cost_usd=0.001,
            actor="troll",
        )
    )
    s = led.summary()
    assert s["kind"] == "summary"
    assert s["calls"] == 1
    assert s["by_actor"] == {"troll": 0.001}
    assert s["input_tokens"] == 10 and s["output_tokens"] == 2


# --- UsageLedger cost ceiling / kill-switch (issue #183) ----------------


def test_ledger_no_ceiling_is_never_over_budget():
    led = UsageLedger()  # default: no ceiling
    led.record(_rec("troll", 9.99))
    assert led.over_budget() is False
    assert led.remaining_budget_usd() is None


def test_ledger_over_budget_trips_at_or_above_ceiling():
    led = UsageLedger(max_cost_usd=0.10)
    led.record(_rec("troll", 0.04))
    assert led.over_budget() is False  # under the ceiling
    assert led.remaining_budget_usd() == pytest.approx(0.06)
    led.record(_rec("troll", 0.06))  # now exactly at the ceiling
    assert led.over_budget() is True  # >= trips it
    assert led.remaining_budget_usd() == pytest.approx(0.0)


def test_ledger_remaining_budget_clamped_at_zero_on_overshoot():
    led = UsageLedger(max_cost_usd=0.10)
    led.record(_rec("troll", 0.25))  # overshoot the ceiling
    assert led.over_budget() is True
    assert led.remaining_budget_usd() == 0.0  # never negative


# --- record_call (the shared helper) ------------------------------------


def test_record_call_mock_is_zero_cost_and_attributed():
    led = UsageLedger()
    rec = record_call(
        led,
        {"actor": "troll", "turn": 3, "attempt": 1},
        "mock",
        "mock",
        None,  # raw_usage None -> zero Usage
        [{"role": "user", "content": "hi"}],
        "go north",
    )
    assert rec.cost_usd == 0.0
    assert (rec.actor, rec.turn, rec.attempt) == ("troll", 3, 1)
    assert rec.prompt_sha256 is not None
    assert len(led.records) == 1


def test_record_call_none_ledger_is_noop():
    # Adapters built without a ledger (defensive getattr -> None) must not crash.
    assert record_call(None, {}, "mock", "mock", None, [], "x") is None


def test_record_call_prices_real_usage():
    led = UsageLedger()
    raw = SimpleNamespace(input_tokens=1_000_000, output_tokens=0)
    rec = record_call(led, {}, "anthropic", "claude-haiku-4-5", raw, [], "hi")
    assert rec.cost_usd == pytest.approx(1.0)


# --- prompt_sha256 ------------------------------------------------------


def test_prompt_sha256_is_stable_and_key_order_independent():
    a = [{"role": "user", "content": "hi"}]
    b = [{"content": "hi", "role": "user"}]  # same data, different key order
    assert prompt_sha256(a) == prompt_sha256(b)
    c = [{"role": "user", "content": "bye"}]
    assert prompt_sha256(a) != prompt_sha256(c)
