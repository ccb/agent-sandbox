"""Offline tests for LLM client resilience (issue #260).

Covers the retry-with-backoff loop, the per-call timeout / disabled-SDK-retry
plumbing, and the API-key preflight. No network, no real SDK, no API key: the
adapters are exercised by injecting a fake ``_client`` whose ``create`` raises
transient errors on a schedule, and ``__init__`` is exercised by monkeypatching
a fake ``anthropic`` / ``openai`` module into ``sys.modules``.
"""

import json
import sys
from types import SimpleNamespace

import pytest

from text_adventure_games.llm_client import (
    AnthropicClient,
    LlmConfig,
    OpenAIClient,
    _backoff_delay,
    _is_retryable,
    _retry_after,
    _RETRY_MAX_DELAY,
    client_from_env,
    create_llm_client,
)
from text_adventure_games.usage import UsageLedger

# --- Fakes --------------------------------------------------------------


class _Transient(Exception):
    """A stand-in provider error carrying an HTTP status (and optional
    Retry-After header), the way the real SDK exceptions do."""

    def __init__(self, status_code=429, retry_after=None):
        super().__init__(f"transient {status_code}")
        self.status_code = status_code
        if retry_after is not None:
            self.response = SimpleNamespace(headers={"retry-after": str(retry_after)})


class _ScheduledCreate:
    """A fake ``create`` that raises the given exceptions in order, then returns
    ``response``. Records how many times it was called."""

    def __init__(self, raises, response=None):
        self._raises = list(raises)
        self._response = response
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        if self._raises:
            raise self._raises.pop(0)
        return self._response


def _openai_chat_response(text):
    message = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def _openai_tool_response(args):
    call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(args)))
    message = SimpleNamespace(content=None, tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def _anthropic_chat_response(text):
    return SimpleNamespace(content=[SimpleNamespace(text=text)], usage=None)


def _anthropic_tool_response(args):
    block = SimpleNamespace(type="tool_use", input=args)
    return SimpleNamespace(content=[block], usage=None)


def _openai(create, *, max_retries=2, ledger=None):
    c = OpenAIClient.__new__(OpenAIClient)  # skip __init__ (needs the SDK)
    c._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    c._model = "gpt-4o-mini"
    c._verbose = False
    c._tokenizer = None
    c._max_retries = max_retries
    c._sleep = lambda *a, **k: None  # no real backoff in tests
    c.ledger = ledger or UsageLedger()
    c.context = {}
    return c


def _anthropic(create, *, max_retries=2, ledger=None):
    c = AnthropicClient.__new__(AnthropicClient)
    c._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    c._model = "claude-haiku-4-5"
    c._verbose = False
    c._max_retries = max_retries
    c._sleep = lambda *a, **k: None
    c.ledger = ledger or UsageLedger()
    c.context = {}
    return c


MSG = [{"role": "user", "content": "hi"}]
TOOL = {
    "name": "choose_action",
    "description": "Pick a command.",
    "parameters": {
        "type": "object",
        "properties": {"action": {"type": "string"}},
        "required": ["action"],
    },
}


# --- Retry classification helpers --------------------------------------


def test_is_retryable_by_status():
    assert _is_retryable(_Transient(429))
    assert _is_retryable(_Transient(408))
    assert _is_retryable(_Transient(409))
    assert _is_retryable(_Transient(500))
    assert _is_retryable(_Transient(503))
    assert not _is_retryable(_Transient(400))
    assert not _is_retryable(_Transient(404))


def test_is_retryable_by_class_name():
    # No status attribute -- classified by the exception class name.
    assert _is_retryable(type("RateLimitError", (Exception,), {})())
    assert _is_retryable(type("APITimeoutError", (Exception,), {})())
    assert _is_retryable(type("APIConnectionError", (Exception,), {})())
    assert not _is_retryable(RuntimeError("boom"))
    assert not _is_retryable(ValueError("bad"))


def test_retry_after_parses_header():
    assert _retry_after(_Transient(429, retry_after=3)) == 3.0
    assert _retry_after(_Transient(429)) is None  # no response/headers
    assert _retry_after(RuntimeError("x")) is None


def test_backoff_delay_prefers_retry_after_and_caps():
    assert _backoff_delay(0, retry_after=2.0) == 2.0
    # Server hint is still capped at the max delay.
    assert _backoff_delay(0, retry_after=10_000) == _RETRY_MAX_DELAY
    # Computed backoff is bounded by the cap for large attempts.
    assert _backoff_delay(50) <= _RETRY_MAX_DELAY


# --- Retry behavior: OpenAI --------------------------------------------


def test_openai_chat_retries_then_succeeds():
    create = _ScheduledCreate(
        [_Transient(429), _Transient(503)], _openai_chat_response("hello")
    )
    client = _openai(create)
    assert client.chat(MSG) == "hello"
    assert create.calls == 3  # two transient failures, then success


def test_openai_chat_exhausts_retries_returns_none():
    create = _ScheduledCreate([_Transient(429)] * 5)  # always transient
    client = _openai(create, max_retries=2)
    assert client.chat(MSG) is None
    assert create.calls == 3  # max_retries=2 -> 3 attempts total


def test_openai_chat_non_retryable_not_retried():
    create = _ScheduledCreate([_Transient(400)] * 5)  # client error -> no retry
    client = _openai(create)
    assert client.chat(MSG) is None
    assert create.calls == 1


def test_openai_chat_runtime_error_non_retryable():
    create = _ScheduledCreate([RuntimeError("boom")] * 5)
    client = _openai(create)
    assert client.chat(MSG) is None
    assert create.calls == 1


def test_openai_call_tool_retries_then_succeeds():
    create = _ScheduledCreate(
        [_Transient(429)], _openai_tool_response({"action": "go north"})
    )
    client = _openai(create)
    assert client.call_tool(MSG, TOOL) == {"action": "go north"}
    assert create.calls == 2


# --- Retry behavior: Anthropic -----------------------------------------


def test_anthropic_chat_retries_then_succeeds():
    create = _ScheduledCreate(
        [_Transient(429), _Transient(429)], _anthropic_chat_response("hi there")
    )
    client = _anthropic(create)
    assert client.chat(MSG) == "hi there"
    assert create.calls == 3


def test_anthropic_call_tool_retries_then_succeeds():
    create = _ScheduledCreate(
        [_Transient(500)], _anthropic_tool_response({"action": "wait"})
    )
    client = _anthropic(create)
    assert client.call_tool(MSG, TOOL) == {"action": "wait"}
    assert create.calls == 2


def test_anthropic_exhausts_retries_returns_none():
    create = _ScheduledCreate([_Transient(429)] * 5)
    client = _anthropic(create, max_retries=1)
    assert client.chat(MSG) is None
    assert create.calls == 2  # max_retries=1 -> 2 attempts


# --- Observability: retries land in the ledger -------------------------


def test_retries_recorded_in_ledger():
    ledger = UsageLedger()
    create = _ScheduledCreate(
        [_Transient(429), _Transient(429)], _openai_chat_response("ok")
    )
    client = _openai(create, ledger=ledger)
    assert client.chat(MSG) == "ok"
    # Every attempt is counted: two failed retries + the success.
    assert ledger.summary()["calls"] == 3
    assert [r.attempt for r in ledger.records] == [0, 1, 2]
    # Failed attempts are zero-cost (a rejected call bills nothing).
    assert all(r.cost_usd == 0 for r in ledger.records)


def test_first_try_success_records_one_call():
    ledger = UsageLedger()
    create = _ScheduledCreate([], _openai_chat_response("ok"))
    client = _openai(create, ledger=ledger)
    assert client.chat(MSG) == "ok"
    assert ledger.summary()["calls"] == 1
    assert ledger.records[0].attempt == 0


# --- __init__ plumbing: timeout + disabled SDK retries -----------------


def test_openai_init_passes_timeout_and_disables_sdk_retries(monkeypatch):
    captured = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))
    client = OpenAIClient(
        LlmConfig(provider="openai", api_key="k", timeout_sec=8.0, max_retries=5)
    )
    assert captured["timeout"] == 8.0
    assert captured["max_retries"] == 0  # SDK retries off; we own the loop
    assert client._max_retries == 5


def test_anthropic_init_passes_timeout_and_disables_sdk_retries(monkeypatch):
    captured = {}

    class _FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropic)
    )
    client = AnthropicClient(
        LlmConfig(provider="anthropic", api_key="k", timeout_sec=12.5, max_retries=3)
    )
    assert captured["timeout"] == 12.5
    assert captured["max_retries"] == 0
    assert client._max_retries == 3


# --- Preflight ----------------------------------------------------------


def _fake_module(name, ctor_attr, monkeypatch):
    """Inject a fake provider module so __init__ runs without the real SDK."""
    monkeypatch.setitem(
        sys.modules, name, SimpleNamespace(**{ctor_attr: lambda **k: object()})
    )


def test_openai_preflight_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    _fake_module("openai", "OpenAI", monkeypatch)
    client = OpenAIClient(LlmConfig(provider="openai"))
    with pytest.raises(ValueError, match="No API key"):
        client.preflight()


def test_anthropic_preflight_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    _fake_module("anthropic", "Anthropic", monkeypatch)
    client = AnthropicClient(LlmConfig(provider="anthropic"))
    with pytest.raises(ValueError, match="No API key"):
        client.preflight()


def test_preflight_with_key_offline_is_noop(monkeypatch):
    """A resolvable key + no LLM_PREFLIGHT => preflight makes no network call."""
    monkeypatch.delenv("LLM_PREFLIGHT", raising=False)
    _fake_module("anthropic", "Anthropic", monkeypatch)
    client = AnthropicClient(LlmConfig(provider="anthropic", api_key="k"))

    def _boom():
        raise AssertionError("preflight should not ping when LLM_PREFLIGHT is unset")

    client._client = SimpleNamespace(models=SimpleNamespace(list=_boom))
    client.preflight()  # must not raise


def test_preflight_live_ping_failure_raises(monkeypatch):
    monkeypatch.setenv("LLM_PREFLIGHT", "1")
    _fake_module("anthropic", "Anthropic", monkeypatch)
    client = AnthropicClient(LlmConfig(provider="anthropic", api_key="k"))

    def _boom():
        raise RuntimeError("401 unauthorized")

    client._client = SimpleNamespace(models=SimpleNamespace(list=_boom))
    with pytest.raises(ValueError, match="preflight failed"):
        client.preflight()


def test_preflight_live_ping_success(monkeypatch):
    monkeypatch.setenv("LLM_PREFLIGHT", "1")
    _fake_module("anthropic", "Anthropic", monkeypatch)
    client = AnthropicClient(LlmConfig(provider="anthropic", api_key="k"))
    client._client = SimpleNamespace(models=SimpleNamespace(list=lambda: ["ok"]))
    client.preflight()  # must not raise


def test_mock_preflight_is_noop():
    client = create_llm_client(LlmConfig(provider="mock"))
    assert client.preflight() is None  # never touches the network


# --- client_from_env integration ---------------------------------------


def test_client_from_env_no_provider_returns_none(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert client_from_env() is None


def test_client_from_env_mock_ok(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    client = client_from_env()
    assert client is not None
    assert client.preflight() is None


def test_client_from_env_real_provider_missing_key_returns_none(monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _fake_module("anthropic", "Anthropic", monkeypatch)
    assert client_from_env() is None
    assert "No API key" in capsys.readouterr().out


def test_client_from_env_reads_resilience_vars(monkeypatch):
    captured = {}

    class _FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MAX_RETRIES", "7")
    monkeypatch.setenv("LLM_API_TIMEOUT_SEC", "5")
    monkeypatch.delenv("LLM_PREFLIGHT", raising=False)
    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropic)
    )
    client = client_from_env()
    assert client is not None
    assert getattr(client, "_max_retries") == 7
    assert captured["timeout"] == 5.0
    assert captured["max_retries"] == 0
