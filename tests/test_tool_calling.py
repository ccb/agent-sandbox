"""Offline tests for the structured tool-calling interface (issue #44).

No network, no SDK, no API key: provider adapters are tested by injecting a
fake SDK object; the mocks and consumers are tested with MockLlmClient.
"""

from types import SimpleNamespace

from text_adventure_games.llm_client import (
    AnthropicClient,
    OpenAIClient,
    _to_anthropic_tool,
    _to_openai_tool,
)

# A normalized, provider-agnostic tool dict (the shape call_tool accepts).
CHOOSE = {
    "name": "choose_action",
    "description": "Choose the single game command to perform this turn.",
    "parameters": {
        "type": "object",
        "properties": {"action": {"type": "string"}},
        "required": ["action"],
    },
}


# --- Fake provider SDKs -------------------------------------------------


class _FakeOpenAISDK:
    """Stands in for openai.OpenAI: records create() kwargs, returns canned."""

    def __init__(self, response):
        self._response = response
        self.created_kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.created_kwargs = kwargs
        return self._response


class _RaisingOpenAISDK:
    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        raise RuntimeError("boom")


class _FakeAnthropicSDK:
    def __init__(self, response):
        self._response = response
        self.created_kwargs = None
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.created_kwargs = kwargs
        return self._response


class _RaisingAnthropicSDK:
    def __init__(self):
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        raise RuntimeError("boom")


def _make_openai(fake_sdk):
    client = OpenAIClient.__new__(OpenAIClient)  # skip __init__ (needs the SDK)
    client._client = fake_sdk
    client._model = "gpt-4o-mini"
    client._verbose = False
    client._tokenizer = None
    return client


def _make_anthropic(fake_sdk):
    client = AnthropicClient.__new__(AnthropicClient)
    client._client = fake_sdk
    client._model = "claude-sonnet-4-20250514"
    client._verbose = False
    return client


# --- Translation helpers ------------------------------------------------


def test_to_openai_tool_shape():
    t = _to_openai_tool(CHOOSE)
    assert t["type"] == "function"
    assert t["function"]["name"] == "choose_action"
    assert t["function"]["parameters"] == CHOOSE["parameters"]


def test_to_anthropic_tool_shape():
    t = _to_anthropic_tool(CHOOSE)
    assert t["name"] == "choose_action"
    assert t["input_schema"] == CHOOSE["parameters"]


# --- OpenAI adapter -----------------------------------------------------


def test_openai_call_tool_returns_parsed_args_and_forces_tool():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(arguments='{"action": "go north"}')
                        )
                    ]
                )
            )
        ]
    )
    fake = _FakeOpenAISDK(response)
    client = _make_openai(fake)

    result = client.call_tool([{"role": "user", "content": "hi"}], CHOOSE)

    assert result == {"action": "go north"}
    assert fake.created_kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "choose_action"},
    }
    assert fake.created_kwargs["tools"][0]["function"]["name"] == "choose_action"


def test_openai_call_tool_no_tool_call_returns_none():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=None))]
    )
    client = _make_openai(_FakeOpenAISDK(response))
    assert client.call_tool([{"role": "user", "content": "hi"}], CHOOSE) is None


def test_openai_call_tool_exception_returns_none():
    client = _make_openai(_RaisingOpenAISDK())
    assert client.call_tool([{"role": "user", "content": "hi"}], CHOOSE) is None


# --- Anthropic adapter --------------------------------------------------


def test_anthropic_call_tool_returns_input_and_forces_tool():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input={"action": "attack player"})]
    )
    fake = _FakeAnthropicSDK(response)
    client = _make_anthropic(fake)

    result = client.call_tool(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ],
        CHOOSE,
    )

    assert result == {"action": "attack player"}
    assert fake.created_kwargs["tool_choice"] == {
        "type": "tool",
        "name": "choose_action",
    }
    assert fake.created_kwargs["system"] == "sys"
    assert fake.created_kwargs["tools"][0]["input_schema"] == CHOOSE["parameters"]


def test_anthropic_call_tool_no_tool_use_returns_none():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="just chatting")]
    )
    client = _make_anthropic(_FakeAnthropicSDK(response))
    assert client.call_tool([{"role": "user", "content": "hi"}], CHOOSE) is None


def test_anthropic_call_tool_exception_returns_none():
    client = _make_anthropic(_RaisingAnthropicSDK())
    assert client.call_tool([{"role": "user", "content": "hi"}], CHOOSE) is None
