"""Thinking depth via ``effort``, and the request payload it produces (#760).

Current Claude models dropped the two knobs the engine had been sending for
years: the fixed ``budget_tokens`` thinking budget is gone (depth is an
``output_config.effort`` level now), and ``temperature``/``top_p``/``top_k``
are rejected outright with a 400. Both facts are invisible until a live run
burns real money failing every call, so they are pinned here.

Adapters are built via ``__new__`` with a fake SDK ``create``, the same pattern
as tests/test_model_tiering.py and tests/test_llm_client_resilience.py.
"""

from types import SimpleNamespace

import pytest

from text_adventure_games.llm_client import AnthropicClient
from text_adventure_games.usage import PRICES, Usage, UsageLedger, price

MSG = [{"role": "user", "content": "hi"}]
TOOL = {
    "name": "go",
    "description": "move",
    "parameters": {"type": "object", "properties": {}},
}


class _CaptureCreate:
    """Fake SDK ``create``: records the full kwargs of every call."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _response(blocks=None):
    return SimpleNamespace(
        content=blocks or [SimpleNamespace(type="text", text="ok")],
        usage=SimpleNamespace(
            input_tokens=1,
            output_tokens=1,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


def _anthropic(create, model="claude-haiku-4-5", effort=None):
    c = AnthropicClient.__new__(AnthropicClient)  # skip __init__ (needs the SDK)
    c._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    c._model = model
    c._models_by_role = None
    c._effort = effort
    c._verbose = False
    c._max_retries = 0
    c._schema_repair = False
    c._sleep = lambda *a, **k: None
    c.ledger = UsageLedger()
    c.context = {}
    return c


# --- default: nothing changes -------------------------------------------------


@pytest.mark.parametrize("method", ["chat", "call_tools"])
def test_no_effort_keeps_the_old_payload(method):
    """The whole feature is opt-in: with no effort and a pre-thinking model the
    request is exactly what it has always been. This is what keeps existing
    Haiku runs -- and the #640 byte-identity bake guard -- unchanged."""
    create = _CaptureCreate(_response())
    client = _anthropic(create)

    if method == "chat":
        client.chat(MSG, max_tokens=128, temperature=0.7)
    else:
        client.call_tools(MSG, [TOOL], max_tokens=128, temperature=0.7)

    sent = create.calls[0]
    assert sent["max_tokens"] == 128
    assert sent["temperature"] == 0.7
    assert "thinking" not in sent
    assert "output_config" not in sent


# --- effort set ---------------------------------------------------------------


@pytest.mark.parametrize("method", ["chat", "call_tools"])
def test_effort_sends_adaptive_thinking_and_drops_temperature(method):
    """``budget_tokens`` is gone on current models; depth is an effort level.
    ``temperature`` must disappear in the same breath -- sending it to a model
    that rejects sampling params 400s every single call."""
    create = _CaptureCreate(_response())
    client = _anthropic(create, model="claude-sonnet-5", effort="medium")

    if method == "chat":
        client.chat(MSG, max_tokens=128, temperature=0.7)
    else:
        client.call_tools(MSG, [TOOL], max_tokens=128, temperature=0.7)

    sent = create.calls[0]
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"] == {"effort": "medium"}
    assert "temperature" not in sent
    assert "budget_tokens" not in sent


@pytest.mark.parametrize("method", ["chat", "call_tools"])
def test_thinking_raises_the_max_tokens_floor(method):
    """``max_tokens`` caps thinking AND the reply together. The decide call site
    passes 128 -- enough to think and return nothing at all -- so a thinking run
    must floor it, or every decision dies silently with no tool_use block."""
    create = _CaptureCreate(_response())
    client = _anthropic(create, model="claude-sonnet-5", effort="medium")

    if method == "chat":
        client.chat(MSG, max_tokens=128, temperature=0.0)
    else:
        client.call_tools(MSG, [TOOL], max_tokens=128, temperature=0.0)

    assert create.calls[0]["max_tokens"] >= 1024


def test_generous_call_site_budget_is_not_lowered():
    """The floor only ever raises: a caller asking for more keeps it."""
    create = _CaptureCreate(_response())
    client = _anthropic(create, model="claude-sonnet-5", effort="medium")
    client.chat(MSG, max_tokens=64000, temperature=0.0)
    assert create.calls[0]["max_tokens"] == 64000


def test_sampling_params_dropped_for_new_models_without_effort():
    """A model that rejects sampling params does so whether or not we asked to
    think -- so `--model claude-sonnet-5` alone must not 400 on every call."""
    create = _CaptureCreate(_response())
    client = _anthropic(create, model="claude-sonnet-5")
    client.chat(MSG, max_tokens=128, temperature=0.7)
    assert "temperature" not in create.calls[0]


def test_effort_applies_to_the_tiered_model_not_the_default():
    """Tiering picks the model per call (#368); the payload has to follow the
    model that call actually routes to."""
    create = _CaptureCreate(_response())
    client = _anthropic(create, model="claude-haiku-4-5")
    client._models_by_role = {"plan": "claude-sonnet-5"}

    client.context["role"] = "plan"
    client.chat(MSG, max_tokens=128, temperature=0.7)
    assert create.calls[0]["model"] == "claude-sonnet-5"
    assert "temperature" not in create.calls[0]

    client.context["role"] = "decide"  # untiered -> the default Haiku
    client.chat(MSG, max_tokens=128, temperature=0.7)
    assert create.calls[1]["model"] == "claude-haiku-4-5"
    assert create.calls[1]["temperature"] == 0.7


# --- reading a thinking reply -------------------------------------------------


def test_chat_reads_past_a_leading_thinking_block():
    """A thinking model puts its thinking block first. Indexing content[0]
    blindly raises, and chat()'s bare except turns that into a None -- a good
    reply mistaken for a brain outage."""
    create = _CaptureCreate(
        _response(
            [
                SimpleNamespace(type="thinking", thinking="hmm"),
                SimpleNamespace(type="text", text="the answer"),
            ]
        )
    )
    client = _anthropic(create, model="claude-sonnet-5", effort="medium")
    assert client.chat(MSG, max_tokens=128) == "the answer"


def test_call_tools_reads_past_a_leading_thinking_block():
    create = _CaptureCreate(
        _response(
            [
                SimpleNamespace(type="thinking", thinking="hmm"),
                SimpleNamespace(type="tool_use", id="t1", name="go", input={"x": 1}),
            ]
        )
    )
    client = _anthropic(create, model="claude-sonnet-5", effort="medium")
    result = client.call_tools(MSG, [TOOL], max_tokens=128)
    assert [c["name"] for c in result.tool_calls] == ["go"]


# --- the budget kill-switch ---------------------------------------------------


def test_sonnet_5_is_priced():
    """An unpriced model costs $0, which silently disarms --max-cost: the run
    would never trip its ceiling. Any model we actually run has to be in the
    table."""
    assert "claude-sonnet-5" in PRICES
    cost = price(
        "claude-sonnet-5",
        Usage(
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=1_000_000,
            output_tokens=0,
        ),
    )
    assert cost > 0
