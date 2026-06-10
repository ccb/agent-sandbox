"""Offline tests for the structured tool-calling interface (issue #44).

No network, no SDK, no API key: provider adapters are tested by injecting a
fake SDK object; the mocks and consumers are tested with MockLlmClient.
"""

from types import SimpleNamespace

from text_adventure_games.llm_client import (
    AnthropicClient,
    MockLlmClient,
    OpenAIClient,
    SELECT_OPTION_TOOL,
    _to_anthropic_tool,
    _to_openai_tool,
)
from text_adventure_games.npc import build_choose_action_tool

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


def test_build_choose_action_tool_with_names_has_enum():
    tool = build_choose_action_tool(["go", "attack", "get"])
    assert tool["name"] == "choose_action"
    props = tool["parameters"]["properties"]
    assert props["action"]["enum"] == ["go", "attack", "get"]
    assert tool["parameters"]["required"] == ["action"]
    assert "reasoning" in props and "arguments" in props


def test_build_choose_action_tool_empty_names_omits_enum():
    tool = build_choose_action_tool([])
    assert "enum" not in tool["parameters"]["properties"]["action"]


def test_select_option_tool_shape():
    assert SELECT_OPTION_TOOL["name"] == "select_option"
    idx = SELECT_OPTION_TOOL["parameters"]["properties"]["index"]
    assert idx["type"] == "integer"
    assert SELECT_OPTION_TOOL["parameters"]["required"] == ["index"]


# --- MockLlmClient.call_tool (Task 3) -----------------------------------


def test_mock_call_tool_returns_scripted_dict_and_records():
    client = MockLlmClient(tool_responses=[{"index": 1}])
    result = client.call_tool([{"role": "user", "content": "x"}], SELECT_OPTION_TOOL)
    assert result == {"index": 1}
    assert client.tool_calls[0]["tool"] is SELECT_OPTION_TOOL
    assert client.tool_calls[0]["max_tokens"] == 256


def test_mock_call_tool_defaults_to_none():
    client = MockLlmClient()
    assert (
        client.call_tool([{"role": "user", "content": "x"}], SELECT_OPTION_TOOL) is None
    )


def test_mock_call_tool_callable_reacts_to_args():
    def responder(messages, tool, max_tokens, temperature):
        return {"action": "look", "arguments": ""}

    client = MockLlmClient(tool_responses=responder)
    assert client.call_tool([], SELECT_OPTION_TOOL) == {
        "action": "look",
        "arguments": "",
    }


def test_mock_chat_and_tool_queues_are_independent():
    # chat() draws from `responses`; call_tool() from `tool_responses`.
    client = MockLlmClient(responses=["chat reply"], tool_responses=[{"index": 0}])
    assert client.call_tool([], SELECT_OPTION_TOOL) == {"index": 0}
    assert client.chat([]) == "chat reply"


# --- MockReActClient.call_tool (Task 4) ---------------------------------

from text_adventure_games.llm_client import MockReActClient

_TROLL_SYSTEM = (
    "You are an NPC in a text adventure game.\n"
    "Persona: I am the troll. I guard the drawbridge."
)
_DRAWBRIDGE_OBS = (
    "DRAWBRIDGE\n"
    "You are standing on one side of a drawbridge.\n"
    "Characters here:\n"
    " * The player - a hero.\n"
    "Inventory:\n"
    " * club - a heavy club\n"
    "Turn: 3"
)


def test_mock_react_call_tool_returns_structured_decision():
    client = MockReActClient()
    messages = [
        {"role": "system", "content": _TROLL_SYSTEM},
        {"role": "user", "content": _DRAWBRIDGE_OBS},
    ]
    result = client.call_tool(messages, build_choose_action_tool(["growl", "attack"]))
    assert result["action"] == "growl"
    assert result["arguments"] == "player"
    assert result["reasoning"]  # a non-empty explanation
    assert client.tool_calls  # the call was recorded


def test_mock_react_call_tool_splits_multiword_arguments():
    # After snarling, the troll's first attack omits the weapon; the reflected
    # prompt makes it name the club -> "attack player with club".
    client = MockReActClient()
    reflected_obs = (
        _DRAWBRIDGE_OBS
        + "\n  Game: Troll snarls and bares its teeth at The player."
        + "\n\nYour previous command 'attack player' failed: "
        "troll doesn't have a weapon.\n"
        "Reflect on why it failed and choose a different action."
    )
    messages = [
        {"role": "system", "content": _TROLL_SYSTEM},
        {"role": "user", "content": reflected_obs},
    ]
    result = client.call_tool(messages, build_choose_action_tool(["attack"]))
    assert result["action"] == "attack"
    assert result["arguments"] == "player with club"


def test_mock_react_call_tool_returns_none_for_unknown_prompt():
    client = MockReActClient()
    messages = [
        {"role": "system", "content": "You narrate a text adventure game."},
        {"role": "user", "content": "The player waits."},
    ]
    assert client.call_tool(messages, build_choose_action_tool([])) is None


def test_mock_react_call_tool_returns_none_when_player_absent():
    client = MockReActClient()
    alone = _DRAWBRIDGE_OBS.replace(" * The player - a hero.\n", "")
    messages = [
        {"role": "system", "content": _TROLL_SYSTEM},
        {"role": "user", "content": alone},
    ]
    assert client.call_tool(messages, build_choose_action_tool([])) is None


def test_mock_react_call_tool_keeps_multiword_verb_intact():
    # The ghost's escalated command is "ghost touch player" -- a two-word verb.
    # With the verb in the tool's enum, the split must keep "ghost touch" whole
    # (action), not break it into "ghost" + "touch player", so the mock matches
    # what a real enum-constrained tool-calling model would return.
    client = MockReActClient()
    ghost_system = (
        "You are an NPC in a text adventure game.\n"
        "Persona: I am the ghost. I will haunt this dungeon."
    )
    haunted_obs = (
        "DUNGEON\n"
        "Characters here:\n"
        " * The player - a hero.\n"
        "  Game: The ghost wails: Leave this place, mortal!\n"
        "Turn: 2"
    )
    messages = [
        {"role": "system", "content": ghost_system},
        {"role": "user", "content": haunted_obs},
    ]
    result = client.call_tool(
        messages, build_choose_action_tool(["ghost touch", "haunt"])
    )
    assert result["action"] == "ghost touch"
    assert result["arguments"] == "player"


# --- LLMAgent structured decision path (Task 5) -------------------------

from text_adventure_games.npc import LLMAgent


def test_llm_agent_decide_uses_structured_path():
    client = MockLlmClient(
        tool_responses=[
            {"reasoning": "r", "action": "attack", "arguments": "player with club"}
        ]
    )
    agent = LLMAgent(client, persona="I am the troll.")
    agent.action_names = ["attack", "go"]

    assert agent.decide("an observation") == "attack player with club"
    assert agent.last_reasoning == "r"
    assert client.tool_calls  # used the tool
    assert not client.calls  # did NOT fall back to chat


def test_llm_agent_structured_builds_enum_from_action_names():
    captured = {}

    def responder(messages, tool, max_tokens, temperature):
        captured["tool"] = tool
        captured["system"] = messages[0]["content"]
        return {"action": "go", "arguments": "north"}

    client = MockLlmClient(tool_responses=responder)
    agent = LLMAgent(client, persona="I wander.")
    agent.action_names = ["go", "attack"]

    assert agent.decide("obs") == "go north"
    action = captured["tool"]["parameters"]["properties"]["action"]
    assert action["enum"] == ["go", "attack"]
    # The structured system message omits the two-line Reasoning/Action format.
    assert "Reply with exactly two lines" not in captured["system"]
    assert "Persona: I wander." in captured["system"]


def test_llm_agent_falls_back_to_freetext_when_no_call_tool():
    # A bare chat-only client (no call_tool attribute) keeps today's behavior.
    class ChatOnly:
        def __init__(self):
            self.calls = []

        def chat(self, messages, max_tokens=256, temperature=0.0):
            self.calls.append(messages)
            return "Reasoning: because\nAction: go north"

        def count_tokens(self, text):
            return len(text) // 4

    agent = LLMAgent(ChatOnly())
    assert agent.decide("obs") == "go north"
    assert agent.last_reasoning == "because"


def test_llm_agent_falls_back_when_call_tool_returns_none():
    client = MockLlmClient(
        responses=["Reasoning: r\nAction: look"], tool_responses=[None]
    )
    agent = LLMAgent(client)
    agent.action_names = ["look"]

    assert agent.decide("obs") == "look"
    assert client.tool_calls  # tried the tool first
    assert client.calls  # then fell back to chat


def test_llm_agent_action_names_defaults_empty():
    agent = LLMAgent(MockLlmClient())
    assert agent.action_names == []
