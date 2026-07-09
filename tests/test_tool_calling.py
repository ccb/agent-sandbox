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
    # Resilience attrs the real __init__ would set (issue #260). A no-op sleep
    # keeps any retry test instant; RuntimeError("boom") stays non-retryable.
    client._max_retries = 2
    client._sleep = lambda *a, **k: None
    return client


def _make_anthropic(fake_sdk):
    client = AnthropicClient.__new__(AnthropicClient)
    client._client = fake_sdk
    client._model = "claude-sonnet-4-20250514"
    client._verbose = False
    client._max_retries = 2
    client._sleep = lambda *a, **k: None
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
    # The system prompt is sent as a cache_control block, not a bare string (#367).
    assert fake.created_kwargs["system"] == [
        {"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}
    ]
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


# --- Usage accounting in the real adapters (usage.py Piece 1) ------------
#
# The __new__-built fakes above skip __init__, so they have no ledger/context;
# we attach one here. record_call reads both defensively, so the existing tests
# stay green while these confirm exactly one record is captured per call, with
# the provider's token counts mapped through.

from text_adventure_games.usage import UsageLedger


def _with_ledger(client):
    client.ledger = UsageLedger()
    client.context = {"actor": "troll", "turn": 3}
    return client.ledger


def test_openai_chat_records_one_usage():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="go north"))],
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=8),
    )
    client = _make_openai(_FakeOpenAISDK(response))
    ledger = _with_ledger(client)

    assert client.chat([{"role": "user", "content": "hi"}]) == "go north"
    assert len(ledger.records) == 1
    rec = ledger.records[0]
    assert (rec.usage.input_tokens, rec.usage.output_tokens) == (120, 8)
    assert rec.actor == "troll" and rec.turn == 3
    assert rec.cost_usd > 0  # gpt-4o-mini is in the price table


def test_openai_call_tool_records_one_usage():
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
        ],
        usage=SimpleNamespace(prompt_tokens=200, completion_tokens=5),
    )
    client = _make_openai(_FakeOpenAISDK(response))
    ledger = _with_ledger(client)

    assert client.call_tool([{"role": "user", "content": "hi"}], CHOOSE) == {
        "action": "go north"
    }
    assert len(ledger.records) == 1
    assert ledger.records[0].usage.input_tokens == 200


def test_anthropic_chat_records_one_usage():
    response = SimpleNamespace(
        content=[SimpleNamespace(text="growl player")],
        usage=SimpleNamespace(input_tokens=412, output_tokens=18),
    )
    client = _make_anthropic(_FakeAnthropicSDK(response))
    client._model = "claude-haiku-4-5"
    ledger = _with_ledger(client)

    assert client.chat([{"role": "user", "content": "hi"}]) == "growl player"
    assert len(ledger.records) == 1
    assert ledger.records[0].usage.output_tokens == 18


def test_anthropic_chat_marks_system_prompt_cacheable():
    # #367: chat() sends the system prompt as an ephemeral cache_control block so
    # the stable persona prefix is written once and re-read cheaply thereafter.
    response = SimpleNamespace(content=[SimpleNamespace(text="ok")])
    fake = _FakeAnthropicSDK(response)
    client = _make_anthropic(fake)

    client.chat(
        [
            {"role": "system", "content": "You are a quiet gardener."},
            {"role": "user", "content": "hi"},
        ]
    )

    assert fake.created_kwargs["system"] == [
        {
            "type": "text",
            "text": "You are a quiet gardener.",
            "cache_control": {"type": "ephemeral"},
        }
    ]


def test_anthropic_no_system_omits_the_field():
    # No system message => no `system` kwarg at all (don't send an empty block).
    response = SimpleNamespace(content=[SimpleNamespace(text="ok")])
    fake = _FakeAnthropicSDK(response)
    client = _make_anthropic(fake)

    client.chat([{"role": "user", "content": "hi"}])

    assert "system" not in fake.created_kwargs


def test_anthropic_call_tool_records_cache_read_into_ledger_and_summary():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input={"action": "attack player"})],
        usage=SimpleNamespace(
            input_tokens=10, output_tokens=6, cache_read_input_tokens=400
        ),
    )
    client = _make_anthropic(_FakeAnthropicSDK(response))
    client._model = "claude-haiku-4-5"
    ledger = _with_ledger(client)

    assert client.call_tool([{"role": "user", "content": "hi"}], CHOOSE) == {
        "action": "attack player"
    }
    assert len(ledger.records) == 1
    # The cache-read field flows from the response through to the summary, which
    # is how Piece 2 (caching) will later be proven to fire.
    assert ledger.records[0].usage.cache_read_input_tokens == 400
    assert ledger.summary()["cache_read_input_tokens"] == 400


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


# --- Task 6: action_names wired from parser into agent factories ---------

from text_adventure_games import games, things, turns
from text_adventure_games.npc import make_react_behavior


def _troll_game():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    troll = things.Character("troll", "a troll", "I am the troll. I guard here.")
    game = games.Game(room, player, characters=[troll])
    room.add_character(troll)
    return game, player, troll


def test_make_react_behavior_sets_action_names_from_parser():
    game, player, troll = _troll_game()
    seen = {}

    def responder(messages, tool, max_tokens, temperature):
        seen["enum"] = tool["parameters"]["properties"]["action"].get("enum")
        return {"action": "look", "arguments": ""}

    client = MockLlmClient(tool_responses=responder)
    troll.set_behavior(make_react_behavior(client))
    troll.take_turn(game)

    assert seen["enum"], "action_names were not propagated to the tool enum"
    assert isinstance(seen["enum"], list) and len(seen["enum"]) > 0


def test_gather_intents_sets_action_names_on_agent():
    game, player, troll = _troll_game()
    seen = {}

    def responder(messages, tool, max_tokens, temperature):
        seen["enum"] = tool["parameters"]["properties"]["action"].get("enum")
        return {"action": "look", "arguments": ""}

    agent = LLMAgent(MockLlmClient(tool_responses=responder))
    troll.set_agent(agent)

    turns.gather_intents(game)

    assert seen["enum"], "gather_intents did not set action_names"
    assert agent.action_names  # populated on the agent itself


# --- Task 7: LlmParser._pick_option structured tool calling path --------

from text_adventure_games.llm_parser import LlmParser


def _make_parser(client):
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    game = games.Game(room, player, characters=[])
    return LlmParser(game, client)


def test_pick_option_structured_returns_indexed_value():
    client = MockLlmClient(tool_responses=[{"index": 1}])
    parser = _make_parser(client)
    options = {"first": "A", "second": "B", "third": "C"}

    assert parser._pick_option("pick one", options, "the second") == "B"
    assert client.tool_calls  # used the select_option tool
    assert not client.calls  # did not fall back to chat


def test_pick_option_out_of_range_falls_back_to_regex():
    # call_tool yields a bad index -> fall through to chat()+regex, which
    # returns "1" -> the 2nd option's value.
    client = MockLlmClient(responses=["1"], tool_responses=[{"index": 99}])
    parser = _make_parser(client)
    options = {"first": "A", "second": "B"}

    assert parser._pick_option("pick one", options, "second") == "B"
    assert client.tool_calls and client.calls  # tried tool, then chat


def test_pick_option_non_int_index_falls_back_to_regex():
    client = MockLlmClient(responses=["0"], tool_responses=[{"index": "nope"}])
    parser = _make_parser(client)
    options = {"first": "A", "second": "B"}

    assert parser._pick_option("pick one", options, "first") == "A"


def test_pick_option_bool_index_falls_back_to_regex():
    # bool is a subclass of int, so True must NOT be accepted as index 1.
    # The structured result is rejected and we fall through to chat()+regex,
    # which returns "0" -> the first option's value.
    client = MockLlmClient(responses=["0"], tool_responses=[{"index": True}])
    parser = _make_parser(client)
    options = {"first": "A", "second": "B"}

    assert parser._pick_option("pick one", options, "first") == "A"
    assert client.tool_calls and client.calls  # tried tool, then chat


def test_pick_option_no_call_tool_uses_regex_unchanged():
    class ChatOnly:
        def __init__(self):
            self.calls = []

        def chat(self, messages, max_tokens=256, temperature=0.0):
            self.calls.append(messages)
            return "0"

        def count_tokens(self, text):
            return len(text) // 4

    parser = _make_parser(ChatOnly())
    options = {"first": "A", "second": "B"}
    assert parser._pick_option("pick one", options, "first") == "A"


# --- #354: plural call_tools (model chooses among several tools) ----------

import json

from text_adventure_games.llm_client import (
    ToolCallResult,
    run_tool_loop,
    limit_context_length,
    _anthropic_tool_choice,
    _content_to_text,
    _openai_tool_choice,
)


def test_openai_tool_choice_maps():
    assert _openai_tool_choice("auto") == "auto"
    assert _openai_tool_choice("any") == "required"
    assert _openai_tool_choice({"name": "t"}) == {
        "type": "function",
        "function": {"name": "t"},
    }


def test_anthropic_tool_choice_maps():
    assert _anthropic_tool_choice("auto") == {"type": "auto"}
    assert _anthropic_tool_choice("any") == {"type": "any"}
    assert _anthropic_tool_choice({"name": "t"}) == {"type": "tool", "name": "t"}


def test_openai_call_tools_collects_multiple_calls():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="c1",
                            function=SimpleNamespace(name="t1", arguments='{"x": 1}'),
                        ),
                        SimpleNamespace(
                            id="c2",
                            function=SimpleNamespace(name="t2", arguments='{"y": 2}'),
                        ),
                    ],
                )
            )
        ]
    )
    fake = _FakeOpenAISDK(response)
    client = _make_openai(fake)

    result = client.call_tools(
        [{"role": "user", "content": "hi"}],
        [CHOOSE, SELECT_OPTION_TOOL, CHOOSE],
        tool_choice="any",
    )

    assert fake.created_kwargs["tool_choice"] == "required"  # "any" -> required
    assert len(fake.created_kwargs["tools"]) == 3
    assert [c["id"] for c in result.tool_calls] == ["c1", "c2"]  # ALL, not just [0]
    assert result.tool_calls[0] == {"id": "c1", "name": "t1", "arguments": {"x": 1}}
    assert result.tool_calls[1]["arguments"] == {"y": 2}


def test_anthropic_call_tools_collects_all_tool_use_blocks():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="thinking"),
            SimpleNamespace(type="tool_use", id="u1", name="t1", input={"x": 1}),
            SimpleNamespace(type="tool_use", id="u2", name="t2", input={"y": 2}),
        ]
    )
    fake = _FakeAnthropicSDK(response)
    client = _make_anthropic(fake)

    result = client.call_tools(
        [{"role": "user", "content": "hi"}],
        [CHOOSE, SELECT_OPTION_TOOL, CHOOSE],
        tool_choice="any",
    )

    assert fake.created_kwargs["tool_choice"] == {"type": "any"}
    assert len(fake.created_kwargs["tools"]) == 3
    assert [c["id"] for c in result.tool_calls] == ["u1", "u2"]  # both, not just first
    assert result.tool_calls[0] == {"id": "u1", "name": "t1", "arguments": {"x": 1}}
    assert result.text == "thinking"  # prose alongside the tool calls


def test_openai_call_tools_no_calls_and_exception():
    resp = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="hello", tool_calls=None))
        ]
    )
    result = _make_openai(_FakeOpenAISDK(resp)).call_tools(
        [{"role": "user", "content": "hi"}], [CHOOSE]
    )
    assert result.tool_calls == [] and result.text == "hello"
    assert (
        _make_openai(_RaisingOpenAISDK()).call_tools(
            [{"role": "user", "content": "hi"}], [CHOOSE]
        )
        is None
    )


def test_anthropic_call_tools_no_calls_and_exception():
    resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="hello")])
    result = _make_anthropic(_FakeAnthropicSDK(resp)).call_tools(
        [{"role": "user", "content": "hi"}], [CHOOSE]
    )
    assert result.tool_calls == [] and result.text == "hello"
    assert (
        _make_anthropic(_RaisingAnthropicSDK()).call_tools(
            [{"role": "user", "content": "hi"}], [CHOOSE]
        )
        is None
    )


def test_call_tools_records_one_usage_openai():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="c1",
                            function=SimpleNamespace(name="t", arguments='{"a": 1}'),
                        )
                    ],
                )
            )
        ],
        usage=SimpleNamespace(prompt_tokens=150, completion_tokens=7),
    )
    client = _make_openai(_FakeOpenAISDK(response))
    ledger = _with_ledger(client)

    client.call_tools([{"role": "user", "content": "hi"}], [CHOOSE], tool_choice="any")
    assert len(ledger.records) == 1
    assert ledger.records[0].usage.input_tokens == 150


def test_call_tools_records_one_usage_anthropic():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", id="u", name="t", input={"a": 1})],
        usage=SimpleNamespace(
            input_tokens=90, output_tokens=4, cache_read_input_tokens=50
        ),
    )
    client = _make_anthropic(_FakeAnthropicSDK(response))
    client._model = "claude-haiku-4-5"
    ledger = _with_ledger(client)

    client.call_tools([{"role": "user", "content": "hi"}], [CHOOSE], tool_choice="any")
    assert len(ledger.records) == 1
    assert ledger.records[0].usage.cache_read_input_tokens == 50


# --- call_tool stays a forced-single wrapper over call_tools --------------


def test_call_tool_still_forces_single_via_call_tools_openai():
    # The wrapper must produce the exact forced-single wire shape as before.
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            id="c1",
                            function=SimpleNamespace(
                                name="choose_action", arguments='{"action": "go"}'
                            ),
                        )
                    ]
                )
            )
        ]
    )
    fake = _FakeOpenAISDK(response)
    assert _make_openai(fake).call_tool(
        [{"role": "user", "content": "hi"}], CHOOSE
    ) == {"action": "go"}
    assert fake.created_kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "choose_action"},
    }
    assert len(fake.created_kwargs["tools"]) == 1


# --- #354: MockLlmClient.call_tools ---------------------------------------


def test_mock_call_tools_scripts_result_and_logs():
    client = MockLlmClient(
        tool_calls_responses=[
            {"tool_calls": [{"name": "choose_action", "arguments": {"action": "go"}}]}
        ]
    )
    result = client.call_tools(
        [{"role": "user", "content": "x"}], [CHOOSE], tool_choice="any"
    )
    assert isinstance(result, ToolCallResult)
    assert result.tool_calls[0]["name"] == "choose_action"
    assert result.tool_calls[0]["arguments"] == {"action": "go"}
    assert result.tool_calls[0]["id"]  # a synthesized id fills in
    assert client.tool_calls_log[0]["tool_choice"] == "any"


def test_mock_call_tools_defaults_to_none():
    assert MockLlmClient().call_tools([], [CHOOSE]) is None


def test_mock_call_tools_callable():
    def responder(messages, tools, tool_choice, max_tokens, temperature):
        return ToolCallResult(
            text=None, tool_calls=[{"id": "1", "name": "t", "arguments": {}}]
        )

    assert (
        MockLlmClient(tool_calls_responses=responder)
        .call_tools([], [CHOOSE])
        .tool_calls[0]["name"]
        == "t"
    )


def test_mock_call_tools_queue_separate_from_tool_responses():
    # call_tool draws from tool_responses; call_tools from tool_calls_responses.
    client = MockLlmClient(
        tool_responses=[{"index": 0}],
        tool_calls_responses=[{"tool_calls": [{"name": "a", "arguments": {}}]}],
    )
    assert client.call_tool([], SELECT_OPTION_TOOL) == {"index": 0}
    assert client.call_tools([], [CHOOSE]).tool_calls[0]["name"] == "a"
    assert len(client.tool_calls) == 1 and len(client.tool_calls_log) == 1


# --- #354: MockReActClient.call_tools -------------------------------------


def test_mock_react_call_tools_returns_one_choose_action_call():
    client = MockReActClient()
    messages = [
        {"role": "system", "content": _TROLL_SYSTEM},
        {"role": "user", "content": _DRAWBRIDGE_OBS},
    ]
    result = client.call_tools(
        messages, [build_choose_action_tool(["growl", "attack"])], tool_choice="any"
    )
    assert len(result.tool_calls) == 1
    args = result.tool_calls[0]["arguments"]
    assert args["action"] == "growl" and args["arguments"] == "player"
    assert result.tool_calls[0]["name"] == "choose_action"


def test_mock_react_call_tools_reconstructs_reflection_from_conversation():
    # A loop-shaped conversation: base obs (troll snarled), then the failed
    # 'attack player' tool_use + an is_error tool_result. The brain must
    # reconstruct npc._reflect's string and escalate to 'attack player with club'.
    client = MockReActClient()
    base_obs = (
        _DRAWBRIDGE_OBS + "\n  Game: Troll snarls and bares its teeth at The player."
    )
    messages = [
        {"role": "system", "content": _TROLL_SYSTEM},
        {"role": "user", "content": base_obs},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "choose_action",
                    "arguments": {"action": "attack", "arguments": "player"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "troll doesn't have a weapon.",
                    "is_error": True,
                }
            ],
        },
    ]
    result = client.call_tools(messages, [build_choose_action_tool(["attack"])])
    args = result.tool_calls[0]["arguments"]
    assert args["action"] == "attack" and args["arguments"] == "player with club"


# --- #355: block-shaped message content translation ----------------------


def test_content_to_text_flattens_blocks():
    assert _content_to_text("plain") == "plain"
    out = _content_to_text(
        [
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "id": "t", "name": "n", "arguments": {"a": 1}},
            {
                "type": "tool_result",
                "tool_use_id": "t",
                "content": "res",
                "is_error": True,
            },
        ]
    )
    assert "hello" in out and "res" in out and '"a": 1' in out


def test_anthropic_call_tools_translates_block_messages():
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])
    fake = _FakeAnthropicSDK(response)
    client = _make_anthropic(fake)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "choose_action",
                    "arguments": {"action": "go north"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "no exit",
                    "is_error": True,
                }
            ],
        },
    ]
    client.call_tools(messages, [CHOOSE], tool_choice="any")
    sent = fake.created_kwargs["messages"]
    assert sent[0] == {"role": "user", "content": "hi"}  # system lifted out
    assert sent[1]["role"] == "assistant"
    assert sent[1]["content"][0] == {
        "type": "tool_use",
        "id": "t1",
        "name": "choose_action",
        "input": {"action": "go north"},  # arguments -> input
    }
    assert sent[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "t1",
        "content": "no exit",
        "is_error": True,  # carried
    }


def test_openai_call_tools_translates_block_messages():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))
        ]
    )
    fake = _FakeOpenAISDK(response)
    client = _make_openai(fake)
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "choose_action",
                    "arguments": {"action": "go north"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "no exit",
                    "is_error": True,
                }
            ],
        },
    ]
    client.call_tools(messages, [CHOOSE], tool_choice="auto")
    sent = fake.created_kwargs["messages"]
    assert sent[0] == {"role": "user", "content": "hi"}
    assert sent[1]["role"] == "assistant"
    assert sent[1]["tool_calls"][0]["id"] == "t1"
    assert sent[1]["tool_calls"][0]["function"]["name"] == "choose_action"
    # arguments serialized to a JSON string on the OpenAI wire
    assert json.loads(sent[1]["tool_calls"][0]["function"]["arguments"]) == {
        "action": "go north"
    }
    # tool_result -> role:"tool" message, is_error folded into the content
    assert sent[2] == {
        "role": "tool",
        "tool_call_id": "t1",
        "content": "Error: no exit",
    }
    assert fake.created_kwargs["tool_choice"] == "auto"


def test_anthropic_rstrip_guarded_for_block_content():
    # A list-content assistant turn must not crash (only string content is
    # rstripped inline); text-block text is still rstripped for the assistant.
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])
    fake = _FakeAnthropicSDK(response)
    client = _make_anthropic(fake)
    messages = [
        {"role": "assistant", "content": [{"type": "text", "text": "thinking...  "}]},
        {"role": "user", "content": "go"},
    ]
    client.call_tools(messages, [CHOOSE])
    assert fake.created_kwargs["messages"][0]["content"][0] == {
        "type": "text",
        "text": "thinking...",
    }


def test_limit_context_length_handles_block_content():
    counter = lambda s: len(s.split())
    messages = [
        {"role": "user", "content": "one two three"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "x", "arguments": {"k": "v"}}
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "some result text",
                    "is_error": False,
                }
            ],
        },
    ]
    assert limit_context_length(messages, 1000, counter) == messages  # all fit
    assert (
        limit_context_length(messages, 3, counter) == messages[-1:]
    )  # tight -> newest


# --- #355: run_tool_loop --------------------------------------------------


def test_run_tool_loop_stops_on_done():
    client = MockLlmClient(
        tool_calls_responses=[
            {"tool_calls": [{"id": "c1", "name": "act", "arguments": {"action": "go"}}]}
        ]
    )
    calls = []

    def execute(name, args):
        calls.append((name, args))
        return ("ok", False, True)  # terminal success

    messages = [{"role": "user", "content": "start"}]
    run_tool_loop(client, messages, [CHOOSE], execute, max_rounds=4)

    assert len(client.tool_calls_log) == 1  # no wasted extra round-trip
    assert calls == [("act", {"action": "go"})]
    assert messages[-2]["role"] == "assistant"
    assert messages[-2]["content"][0]["type"] == "tool_use"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"][0]["type"] == "tool_result"


def test_run_tool_loop_retries_on_is_error_then_succeeds():
    client = MockLlmClient(
        tool_calls_responses=[
            {
                "tool_calls": [
                    {"id": "c1", "name": "act", "arguments": {"action": "bad"}}
                ]
            },
            {
                "tool_calls": [
                    {"id": "c2", "name": "act", "arguments": {"action": "good"}}
                ]
            },
        ]
    )

    def execute(name, args):
        if args["action"] == "bad":
            return ("nope", True, False)  # is_error -> retry in conversation
        return ("ok", False, True)

    messages = [{"role": "user", "content": "start"}]
    run_tool_loop(client, messages, [CHOOSE], execute, max_rounds=4)

    assert len(client.tool_calls_log) == 2
    # Round 2's request carries round 1's tool_use + an is_error tool_result.
    round2 = client.tool_calls_log[1]["messages"]
    blocks = [b for m in round2 if isinstance(m["content"], list) for b in m["content"]]
    assert any(
        b["type"] == "tool_use" and b["arguments"] == {"action": "bad"} for b in blocks
    )
    assert any(
        b["type"] == "tool_result" and b["is_error"] and b["content"] == "nope"
        for b in blocks
    )


def test_run_tool_loop_caps_at_max_rounds():
    def responder(messages, tools, tool_choice, max_tokens, temperature):
        return {
            "tool_calls": [{"id": "c", "name": "act", "arguments": {"action": "x"}}]
        }

    client = MockLlmClient(tool_calls_responses=responder)

    def execute(name, args):
        return ("fail", True, False)  # never succeeds

    messages = [{"role": "user", "content": "start"}]
    run_tool_loop(client, messages, [CHOOSE], execute, max_rounds=3)
    assert len(client.tool_calls_log) == 3  # hard cap enforced


def test_run_tool_loop_stops_when_no_tool_call():
    client = MockLlmClient(
        tool_calls_responses=[{"text": "just chatting", "tool_calls": []}]
    )
    called = []

    def execute(name, args):
        called.append(name)
        return ("x", False, True)

    messages = [{"role": "user", "content": "start"}]
    result = run_tool_loop(client, messages, [CHOOSE], execute, max_rounds=4)
    assert len(client.tool_calls_log) == 1
    assert called == []  # execute never ran
    assert result.text == "just chatting"
    assert len(messages) == 1  # no turns appended


# --- #356: per-action tool schemas from the action registry ---------------

from text_adventure_games import actions
from text_adventure_games.npc import (
    command_from_args,
    command_from_tool_call,
    tools_for,
)


class _Wave(actions.Action):
    """A tiny custom action declaring a typed ARGUMENTS_SCHEMA, used to prove a
    game-defined action is exposed as a tool with no extra wiring and routes
    through its own precondition gate."""

    ACTION_NAME = "wave"
    ACTION_DESCRIPTION = "Wave at someone here"
    ACTION_ALIASES = ["greet"]
    ARGUMENTS_SCHEMA = {
        "target": {
            "type": "character",
            "description": "who to wave at",
            "required": True,
        },
    }

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        looker = actor if actor is not None else game.player
        self.target = self.character_in_room(command, looker)

    def check_preconditions(self):
        return self.was_matched(self.target, "There is no one here to wave at.")

    def apply_effects(self):
        self.target.set_property("waved_at", True)
        self.parser.ok(f"{self.actor.name} waves at {self.target.name}.")


class _Survey(actions.Action):
    """Custom action exercising all three scope-category slot kinds at once."""

    ACTION_NAME = "survey"
    ACTION_DESCRIPTION = "Survey the surroundings"
    ARGUMENTS_SCHEMA = {
        "who": {"type": "character", "description": "a person here"},
        "what": {"type": "item", "description": "an item in reach"},
        "way": {"type": "direction", "description": "an exit"},
        "note": {"type": "string", "description": "free-form note"},
    }

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self):
        return True

    def apply_effects(self):
        self.parser.ok("surveyed")


def _scope_scene():
    """A hall (north -> yard) with the player, a friend here, a stranger away,
    a lamp here, and a coin carried -- so scope enums have a known answer."""
    hall = things.Location("Hall", "A stone hall.")
    yard = things.Location("Yard", "A grassy yard.")
    hall.add_connection("north", yard)
    player = things.Character("player", "the player", "I explore.")
    friend = things.Character("friend", "a friend", "I am friendly.")
    stranger = things.Character("stranger", "a stranger", "I lurk elsewhere.")
    lamp = things.Item("lamp", "a lamp", "A brass lamp.")
    lamp.set_property("gettable", True)
    coin = things.Item("coin", "a coin", "A gold coin.")
    hall.add_item(lamp)
    game = games.Game(hall, player, characters=[friend, stranger])
    hall.add_character(friend)
    yard.add_character(stranger)
    player.add_to_inventory(coin)
    return game, player, friend


def test_tools_for_derives_one_tool_per_registered_action():
    game, player, _ = _scope_scene()
    tools = tools_for(game.parser)
    names = {t["name"] for t in tools}
    # Every registered verb becomes a tool, and the comma-sequence wrapper is
    # the one thing dropped (it exists for the engine, not for an agent).
    assert "go" in names and "get" in names and "wait" in names
    assert "sequence" not in names
    # Each tool is a normalized dict with an object parameter schema.
    go = next(t for t in tools if t["name"] == "go")
    assert go["parameters"]["type"] == "object"
    assert "reasoning" in go["parameters"]["properties"]


def test_tools_for_undeclared_action_uses_freetext_arguments():
    # An action with no ARGUMENTS_SCHEMA (the built-ins) falls back to a single
    # free-text `arguments` field -- the same contract choose_action used.
    game, _, _ = _scope_scene()
    tools = tools_for(game.parser)
    go = next(t for t in tools if t["name"] == "go")
    props = go["parameters"]["properties"]
    assert props["arguments"]["type"] == "string"
    assert go["parameters"]["required"] == []


def test_tools_for_folds_aliases_into_description():
    game, _, _ = _scope_scene()
    game.parser.add_action(_Wave)
    wave = next(t for t in tools_for(game.parser) if t["name"] == "wave")
    assert "aliases: greet" in wave["description"]


def test_tools_for_declared_schema_becomes_typed_slots_no_extra_wiring():
    # Registering the action is the ONLY wiring -- it is then a tool with its
    # declared slots and required list, derived straight from the registry.
    game, _, _ = _scope_scene()
    game.parser.add_action(_Wave)
    wave = next(t for t in tools_for(game.parser) if t["name"] == "wave")
    props = wave["parameters"]["properties"]
    assert "target" in props and "arguments" not in props  # typed, not free text
    assert wave["parameters"]["required"] == ["target"]


def test_tools_for_scope_enum_offers_only_in_scope_entities():
    # The #356 acceptance: a slot enum is populated from what the actor can
    # currently see -- friend here (not the stranger away), the lamp + carried
    # coin, and the single north exit.
    game, player, _ = _scope_scene()
    game.parser.add_action(_Survey)
    survey = next(
        t for t in tools_for(game.parser, actor=player) if t["name"] == "survey"
    )
    props = survey["parameters"]["properties"]
    assert props["who"]["enum"] == ["friend"]  # stranger is in another room
    assert props["what"]["enum"] == ["coin", "lamp"]
    assert props["way"]["enum"] == ["north"]
    # A plain-typed slot passes through untouched (no enum).
    assert props["note"]["type"] == "string" and "enum" not in props["note"]


def test_tools_for_no_actor_leaves_scope_slots_unconstrained():
    # Without an actor there is no scope to read, so scope slots stay plain
    # strings (the derivation still succeeds -- it just can't narrow them).
    game, _, _ = _scope_scene()
    game.parser.add_action(_Survey)
    survey = next(t for t in tools_for(game.parser) if t["name"] == "survey")
    assert "enum" not in survey["parameters"]["properties"]["who"]


def test_tools_for_drops_enum_when_scope_exceeds_cap():
    # A too-large scope drops the enum rather than truncating (which would make a
    # valid entity unnameable) -- the slot degrades to free text.
    game, player, _ = _scope_scene()
    hall = player.location
    for i in range(30):
        it = things.Item(f"pebble{i}", "a pebble", "A small pebble.")
        hall.add_item(it)
    game.parser.add_action(_Survey)
    survey = next(
        t
        for t in tools_for(game.parser, actor=player, max_enum=20)
        if t["name"] == "survey"
    )
    assert "enum" not in survey["parameters"]["properties"]["what"]


def test_tools_for_names_filter_and_unknown_verb_gets_generic_tool():
    # `names` curates the set; a name with no registered action still gets a
    # generic free-text tool, so action_names stays the authoritative menu.
    game, _, _ = _scope_scene()
    tools = tools_for(game.parser, names=["go", "growl"])
    assert {t["name"] for t in tools} == {"go", "growl"}
    growl = next(t for t in tools if t["name"] == "growl")
    assert growl["parameters"]["properties"]["arguments"]["type"] == "string"


def test_command_from_args_freetext_and_connectors():
    # Undeclared -> "<verb> <arguments>".
    assert command_from_args("go", {"arguments": "north"}, None) == "go north"
    # Declared schema -> slots joined in order, each after its connector word.
    schema = {
        "target": {"type": "character"},
        "weapon": {"type": "item", "connector": "with"},
    }
    cmd = command_from_args("attack", {"target": "player", "weapon": "club"}, schema)
    assert cmd == "attack player with club"
    # A missing optional slot is simply skipped.
    assert command_from_args("attack", {"target": "player"}, schema) == "attack player"


def test_command_from_tool_call_handles_both_shapes():
    game, _, _ = _scope_scene()
    game.parser.add_action(_Wave)
    # choose_action fallback: verb in args['action'].
    assert (
        command_from_tool_call(
            "choose_action", {"action": "go", "arguments": "north"}, game.parser
        )
        == "go north"
    )
    # per-action tool: verb IS the tool name, slots from ARGUMENTS_SCHEMA.
    assert (
        command_from_tool_call("wave", {"target": "friend"}, game.parser)
        == "wave friend"
    )


def test_tools_for_names_are_provider_valid():
    # Provider APIs require tool names to match ^[A-Za-z0-9_-]{1,64}$ (no spaces),
    # but the registry keys multi-word verbs with spaces ("adopt goal", "take
    # off"). Every derived tool name must be provider-valid or a real-key run 400s
    # on its first decision -- the mode #356 exists for.
    import re as _re

    game, _, _ = _scope_scene()
    for tool in tools_for(game.parser):
        assert _re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", tool["name"]
        ), f"invalid provider tool name: {tool['name']!r}"


def test_multiword_verb_tool_name_round_trips_through_routing():
    # A multi-word default verb ("adopt goal") is exposed under a sanitized name,
    # and command_from_tool_call recovers the SPOKEN verb so the assembled command
    # still routes -- the sanitization is invisible to the parser.
    game, _, _ = _scope_scene()
    adopt = next(t for t in tools_for(game.parser) if t["name"] == "adopt_goal")
    assert " " not in adopt["name"]  # sanitized for the provider wire
    assert (
        command_from_tool_call("adopt_goal", {"arguments": "be brave"}, game.parser)
        == "adopt goal be brave"
    )


def test_mock_react_call_tools_answers_per_action_toolset():
    # The mock must answer the N-tools shape offline: it picks the tool NAMED for
    # the verb its brain chose and fills the free-text arguments.
    client = MockReActClient()
    tools = tools_for_stub("growl", "attack")
    messages = [
        {"role": "system", "content": _TROLL_SYSTEM},
        {"role": "user", "content": _DRAWBRIDGE_OBS},
    ]
    result = client.call_tools(messages, tools, tool_choice="any")
    call = result.tool_calls[0]
    assert call["name"] == "growl"  # the tool, not a choose_action wrapper
    assert call["arguments"]["arguments"] == "player"


def test_mock_react_call_tools_matches_multiword_verb_tool():
    client = MockReActClient()
    ghost_system = (
        "You are an NPC in a text adventure game.\n"
        "Persona: I am the ghost. I will haunt this dungeon."
    )
    haunted_obs = (
        "DUNGEON\nCharacters here:\n * The player - a hero.\n"
        "  Game: The ghost wails: Leave this place, mortal!\nTurn: 2"
    )
    messages = [
        {"role": "system", "content": ghost_system},
        {"role": "user", "content": haunted_obs},
    ]
    result = client.call_tools(messages, tools_for_stub("ghost touch", "haunt"))
    call = result.tool_calls[0]
    assert call["name"] == "ghost touch"  # multi-word verb kept whole
    assert call["arguments"]["arguments"] == "player"


def test_mock_react_call_tools_reconstructs_reflection_across_per_action_call():
    # The prior tool_use is NAMED "attack" (no 'action' key), so the mock must
    # read the verb from the block name to rebuild "attack player" and escalate.
    client = MockReActClient()
    base_obs = (
        _DRAWBRIDGE_OBS + "\n  Game: Troll snarls and bares its teeth at The player."
    )
    messages = [
        {"role": "system", "content": _TROLL_SYSTEM},
        {"role": "user", "content": base_obs},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "attack",  # per-action tool, verb in the NAME
                    "arguments": {"arguments": "player"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "troll doesn't have a weapon.",
                    "is_error": True,
                }
            ],
        },
    ]
    result = client.call_tools(messages, tools_for_stub("attack"))
    call = result.tool_calls[0]
    assert call["name"] == "attack"
    assert call["arguments"]["arguments"] == "player with club"


def test_mock_react_call_tools_declines_when_no_tool_matches_verb():
    # The brain chooses "growl player" but only an "attack" tool is offered ->
    # decline (None), so the caller can fall back to its single-tool path.
    client = MockReActClient()
    messages = [
        {"role": "system", "content": _TROLL_SYSTEM},
        {"role": "user", "content": _DRAWBRIDGE_OBS},
    ]
    assert client.call_tools(messages, tools_for_stub("attack")) is None


def tools_for_stub(*names):
    """A minimal per-action toolset (free-text `arguments`) for mock tests."""
    return [
        {
            "name": n,
            "description": n,
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string"},
                    "arguments": {"type": "string"},
                },
                "required": [],
            },
        }
        for n in names
    ]


def test_custom_action_tool_routes_through_precondition_gate_unchanged():
    # Acceptance #1: a game with a custom ARGUMENTS_SCHEMA action, driven by a
    # mock that decides via that per-action tool, routes through the SAME
    # precondition gate -- schemas shape the phrasing, the gate still decides.
    # The friend NPC (in the hall with the player) waves at the player.
    game, player, friend = _scope_scene()
    game.parser.add_action(_Wave)

    # A scripted per-action tool call: verb = tool NAME, typed slot filled.
    good = {"tool_calls": [{"name": "wave", "arguments": {"target": "player"}}]}
    client = MockLlmClient(tool_calls_responses=[good])
    friend.set_behavior(make_react_behavior(client))

    friend.take_turn(game)

    # The custom action's effect applied -> it passed check_preconditions() after
    # the per-action tool call assembled and routed "wave player".
    assert player.get_property("waved_at") is True


def test_custom_action_tool_precondition_still_gates_bad_target():
    # Name a target that isn't here: the schema let the model *say* it, but the
    # precondition gate still rejects the ACT (was_matched fails).
    from text_adventure_games.npc import build_npc_context, decide_and_route

    game, player, friend = _scope_scene()
    game.parser.add_action(_Wave)

    # 'ghost' is no one in the hall -> character_in_room returns None -> gate
    # fails every attempt. A callable keeps returning the bad call for each retry.
    def always_bad(messages, tools, tool_choice, max_tokens, temperature):
        return {"tool_calls": [{"name": "wave", "arguments": {"target": "ghost"}}]}

    client = MockLlmClient(tool_calls_responses=always_bad)
    agent = LLMAgent(client, persona="I am friendly.")
    agent.action_names = list(game.parser.actions)

    acted = decide_and_route(friend, game, agent, build_npc_context(friend, game))

    assert acted is False  # every attempt was gated, never routed to an effect
    assert not player.get_property("waved_at")
