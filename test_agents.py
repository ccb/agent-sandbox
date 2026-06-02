"""Tests for the Agent abstraction (issue #3). Fully isolated: no real Game."""

from text_adventure_games import things
from text_adventure_games.agents import Agent, LLMAgent, ScriptedAgent


class FakeLlmClient:
    """LlmClient stub: returns scripted responses in order, records calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, max_tokens=256, temperature=0.0):
        self.calls.append(messages)
        return self.responses.pop(0) if self.responses else None

    def count_tokens(self, text):
        return len(text) // 4


class StubParser:
    """Records commands; returns a fixed success value."""

    def __init__(self, succeed=True):
        self.succeed = succeed
        self.commands = []
        self.command_history = []

    def parse_command(self, command):
        self.commands.append(command)
        return self.succeed


class StubGame:
    def __init__(self, parser, turn=1):
        self.parser = parser
        self.turn = turn

    def describe_for(self, character):
        return f"You are {character.name}."


def make_npc(name="rat"):
    return things.Character(name, "a small rat", "I am a hungry rat.")


def test_observe_includes_describe_and_goals():
    agent = Agent(goals=["find the crown"])
    obs = agent.observe(make_npc(), StubGame(StubParser()))
    assert "You are rat." in obs
    assert "find the crown" in obs


def test_act_routes_command_and_returns_parser_result():
    parser = StubParser(succeed=True)
    agent = Agent()
    ok = agent.act("rat go north", StubGame(parser))
    assert ok is True
    assert parser.commands == ["rat go north"]


def test_remember_appends_memory_entry():
    agent = Agent()
    game = StubGame(StubParser(), turn=4)
    agent.remember(make_npc(), game, "obs", "rat go north", True)
    assert agent.memory == [
        {"turn": 4, "observation": "obs", "command": "rat go north", "ok": True}
    ]


def test_llmagent_decide_returns_first_line():
    agent = LLMAgent(FakeLlmClient(["go north\nbecause I want to leave"]))
    assert agent.decide("You are rat.", make_npc()) == "go north"


def test_llmagent_decide_empty_when_llm_fails():
    agent = LLMAgent(FakeLlmClient([]))  # chat() returns None
    assert agent.decide("obs", make_npc()) == ""


def test_llmagent_take_turn_routes_and_records():
    parser = StubParser(succeed=True)
    agent = LLMAgent(FakeLlmClient(["go north"]))
    agent.take_turn(make_npc(), StubGame(parser, turn=2))
    assert parser.commands == ["rat go north"]
    assert len(agent.memory) == 1
    assert agent.memory[0]["turn"] == 2
    assert agent.memory[0]["command"] == "rat go north"
    assert agent.memory[0]["ok"] is True


def test_llmagent_retries_with_reflection_on_failure():
    parser = StubParser(succeed=False)
    client = FakeLlmClient(["go north", "go south"])
    agent = LLMAgent(client, max_retries=1)
    agent.take_turn(make_npc(), StubGame(parser))
    assert parser.commands == ["rat go north", "rat go south"]
    assert len(agent.memory) == 2
    assert all(e["ok"] is False for e in agent.memory)
    retry_user_msg = client.calls[1][-1]["content"]
    assert "failed" in retry_user_msg


def test_scripted_agent_delegates_to_closure():
    seen = []
    agent = ScriptedAgent(lambda c, g: seen.append((c.name, g.turn)))
    agent.take_turn(make_npc(), StubGame(StubParser(), turn=3))
    assert seen == [("rat", 3)]


def test_llmagent_falls_back_when_llm_returns_nothing():
    fb_seen = []
    fallback = ScriptedAgent(lambda c, g: fb_seen.append(c.name))
    agent = LLMAgent(FakeLlmClient([]), fallback=fallback)  # LLM yields None
    agent.take_turn(make_npc(), StubGame(StubParser()))
    assert fb_seen == ["rat"]


def test_character_take_turn_prefers_agent_over_behavior():
    npc = make_npc()
    order = []
    npc.set_behavior(lambda c, g: order.append("behavior"))
    npc.set_agent(ScriptedAgent(lambda c, g: order.append("agent")))
    npc.take_turn(StubGame(StubParser()))
    assert order == ["agent"]


def test_character_take_turn_falls_back_to_behavior():
    npc = make_npc()
    order = []
    npc.set_behavior(lambda c, g: order.append("behavior"))
    npc.take_turn(StubGame(StubParser()))
    assert order == ["behavior"]


def test_npc_shim_exposes_agents_and_hybrid_falls_back():
    from text_adventure_games import npc

    assert hasattr(npc, "LLMAgent") and hasattr(npc, "ScriptedAgent")
    fb_seen = []
    behavior = npc.make_hybrid_behavior(
        FakeLlmClient([]), lambda c, g: fb_seen.append(c.name)
    )
    behavior(make_npc(), StubGame(StubParser()))
    assert fb_seen == ["rat"]
