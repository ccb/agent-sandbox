"""Per-call-site model tiering (issue #368).

The "role" the caller stamps into ``client.context`` (the same key the ledger
and monitor use for attribution) picks the request model from
``LlmConfig.models_by_role``; unlisted roles -- and clients with no map -- use
the client's default model. Adapters are built via ``__new__`` with a fake SDK
``create``, the same pattern as tests/test_llm_client_resilience.py.
"""

from types import SimpleNamespace

import pytest

from text_adventure_games.llm_client import AnthropicClient, OpenAIClient
from text_adventure_games.usage import UsageLedger

MSG = [{"role": "user", "content": "hi"}]

TIERS = {"plan": "claude-sonnet-4-6", "reflect": "claude-sonnet-4-6"}


class _CaptureCreate:
    """Fake SDK ``create``: records each call's ``model`` kwarg, returns a
    canned response."""

    def __init__(self, response):
        self._response = response
        self.models = []

    def __call__(self, **kwargs):
        self.models.append(kwargs["model"])
        return self._response


def _anthropic_usage(input_tokens=0, output_tokens=0):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )


def _anthropic_response(text="ok", usage=None):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], usage=usage
    )


def _anthropic(create, models_by_role=None, ledger=None):
    c = AnthropicClient.__new__(AnthropicClient)  # skip __init__ (needs the SDK)
    c._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    c._model = "claude-haiku-4-5"
    c._models_by_role = models_by_role
    c._verbose = False
    c._max_retries = 0
    c._sleep = lambda *a, **k: None
    c.ledger = ledger or UsageLedger()
    c.context = {}
    return c


def _openai_response(text="ok"):
    message = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def _openai(create, models_by_role=None, ledger=None):
    c = OpenAIClient.__new__(OpenAIClient)
    c._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    c._model = "gpt-4o-mini"
    c._models_by_role = models_by_role
    c._verbose = False
    c._tokenizer = None
    c._max_retries = 0
    c._sleep = lambda *a, **k: None
    c.ledger = ledger or UsageLedger()
    c.context = {}
    return c


def test_stamped_role_picks_the_tier_model_and_records_it():
    create = _CaptureCreate(_anthropic_response(usage=_anthropic_usage()))
    client = _anthropic(create, models_by_role=TIERS)
    client.context.update({"actor": "a", "role": "plan"})
    assert client.chat(MSG) == "ok"
    assert create.models == ["claude-sonnet-4-6"]
    rec = client.ledger.records[0]
    assert rec.usage.model == "claude-sonnet-4-6"
    assert rec.role == "plan"


def test_tier_model_is_priced_at_its_own_rate():
    # 1M input tokens at claude-sonnet-4-6 = $3.00 (usage.py PRICES), proving
    # record_call prices the per-call model, not the client default.
    create = _CaptureCreate(
        _anthropic_response(usage=_anthropic_usage(input_tokens=1_000_000))
    )
    client = _anthropic(create, models_by_role=TIERS)
    client.context["role"] = "plan"
    client.chat(MSG)
    assert client.ledger.records[0].cost_usd == pytest.approx(3.00)


def test_unlisted_role_and_missing_role_use_the_default_model():
    create = _CaptureCreate(_anthropic_response())
    client = _anthropic(create, models_by_role=TIERS)
    client.context["role"] = "decide"  # not in the map
    client.chat(MSG)
    client.context.pop("role")  # no role stamped at all
    client.chat(MSG)
    assert create.models == ["claude-haiku-4-5", "claude-haiku-4-5"]


def test_no_map_and_no_attribute_fall_back_to_the_default_model():
    create = _CaptureCreate(_anthropic_response())
    client = _anthropic(create, models_by_role=None)
    client.context["role"] = "plan"
    client.chat(MSG)
    # Doubles built via __new__ may not set the attribute at all
    # (test_llm_client_resilience.py's helpers): must not raise.
    del client._models_by_role
    client.chat(MSG)
    assert create.models == ["claude-haiku-4-5", "claude-haiku-4-5"]


def test_call_tools_routes_by_role_too():
    block = SimpleNamespace(type="tool_use", id="c1", name="t", input={"x": 1})
    create = _CaptureCreate(SimpleNamespace(content=[block], usage=None))
    client = _anthropic(create, models_by_role=TIERS)
    client.context["role"] = "reflect"
    tool = {"name": "t", "description": "d", "parameters": {"type": "object"}}
    result = client.call_tools(MSG, [tool], tool_choice={"name": "t"})
    assert result.tool_calls[0]["arguments"] == {"x": 1}
    assert create.models == ["claude-sonnet-4-6"]


def test_openai_adapter_routes_by_role():
    create = _CaptureCreate(_openai_response())
    client = _openai(create, models_by_role={"plan": "gpt-4o"})
    client.context["role"] = "plan"
    client.chat(MSG)
    client.context["role"] = "decide"
    client.chat(MSG)
    assert create.models == ["gpt-4o", "gpt-4o-mini"]
