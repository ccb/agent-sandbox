"""Offline tests for the cognition tools (issue #358).

Cover the three acceptance bullets, plus the guard rails:

* recall-then-act: an agent offered ``recall`` alongside the action tools calls
  it, gets a tool_result carrying its OWN memories (and only its own), then
  acts; the retrieval round cap is enforced with an is_error budget message;
* converse: a dialogue line grounded in a memory the agent chose to recall;
* default-off: with the flag unset, no cognition tool is ever offered and the
  converse path never touches the tool loop (the rest of byte-identical is the
  existing suite staying green);
* source gating (no memory/knowledge/plan -> tool not offered) and graceful
  degradation (a raising tool becomes an is_error tool_result, never a crash).

Run with::

    uv run pytest tests/test_cognition_tools.py -v
"""

from text_adventure_games import conversation as convo
from text_adventure_games import games, things
from text_adventure_games.config import AgentConfig
from text_adventure_games.knowledge import Knowledge
from text_adventure_games.llm_client import MockLlmClient
from text_adventure_games.npc import (
    COGNITION_BUDGET,
    LLMAgent,
    ScriptedAgent,
    build_npc_context,
    cognition_toolset,
    decide_and_route,
    make_react_behavior,
)
from text_adventure_games.planning import DailyPlan, Stop

# --- helpers ----------------------------------------------------------------

# Scripted call_tools replies (the same MockLlmClient queue idiom the #355/#356
# suites use; MockReActClient inherits this queue from MockLlmClient).
RECALL = {
    "tool_calls": [{"name": "recall", "arguments": {"query": "the player", "k": 2}}]
}
GO_NORTH = {
    "tool_calls": [
        {"name": "go", "arguments": {"reasoning": "move on", "arguments": "north"}}
    ]
}

COGNITION_NAMES = {"recall", "query_knowledge", "read_plan"}


def _scene():
    """A hall (north -> yard) with the player and an NPC friend."""
    hall = things.Location("Hall", "A stone hall.")
    yard = things.Location("Yard", "A grassy yard.")
    hall.add_connection("north", yard)
    player = things.Character("player", "the player", "I explore.")
    friend = things.Character("friend", "a friend", "I am friendly.")
    game = games.Game(hall, player, characters=[friend])
    hall.add_character(friend)
    return game, player, friend


def _agent(client, *, on=True):
    agent = LLMAgent(client, persona="I am friendly.", cognition_tools=on)
    return agent


def _result_blocks(logged_messages):
    """Every tool_result block visible in one logged call_tools request."""
    return [
        b
        for m in logged_messages
        if isinstance(m["content"], list)
        for b in m["content"]
        if b["type"] == "tool_result"
    ]


# --- acceptance 1: recall-then-act, own memories only, cap enforced ----------


def test_recall_then_act_sees_only_own_memories():
    game, player, friend = _scene()
    client = MockLlmClient(tool_calls_responses=[RECALL, GO_NORTH])
    agent = _agent(client)
    agent.action_names = list(game.parser.actions)
    agent.memory.add_observation(
        "I saw the player sharpening a sword.", turn=0, importance=5
    )
    # Another agent's private memory must never surface in this agent's recall.
    other = _agent(MockLlmClient())
    other.memory.add_observation("SECRET: the vault code is 1234.", turn=0)

    acted = decide_and_route(friend, game, agent, build_npc_context(friend, game))

    assert acted is True
    assert friend.location.name == "Yard"  # the agent recalled, then acted
    # recall was offered ALONGSIDE the action tools (knowledge/plan have no
    # source on this agent, so those tools were correctly not offered).
    offered = {t["name"] for t in client.tool_calls_log[0]["tools"]}
    assert "recall" in offered and "go" in offered
    assert "query_knowledge" not in offered and "read_plan" not in offered
    # Round 2's request carries the recall tool_result with the agent's own
    # memory -- and nothing from the other agent's stream.
    results = _result_blocks(client.tool_calls_log[1]["messages"])
    assert any(
        "sharpening a sword" in str(b["content"]) and not b["is_error"] for b in results
    )
    assert all("vault code" not in str(b["content"]) for b in results)


def test_recall_round_cap_enforced_with_budget_error():
    game, player, friend = _scene()

    def always_recall(messages, tools, tool_choice, max_tokens, temperature):
        return {"tool_calls": [{"name": "recall", "arguments": {"query": "player"}}]}

    client = MockLlmClient(tool_calls_responses=always_recall)
    agent = _agent(client)
    agent.action_names = list(game.parser.actions)
    agent.memory.add_observation("I saw the player.", turn=0)

    acted = decide_and_route(friend, game, agent, build_npc_context(friend, game))

    assert acted is False  # it never chose an action
    # Cognition rounds ride on top of the historical 1 + max_retries budget.
    assert len(client.tool_calls_log) == 2 + COGNITION_BUDGET
    # The first COGNITION_BUDGET recalls succeeded; every later one was refused
    # with an is_error budget message telling the agent to act.
    results = _result_blocks(client.tool_calls_log[-1]["messages"])
    ok = [b for b in results if not b["is_error"]]
    refused = [b for b in results if b["is_error"]]
    assert len(ok) == COGNITION_BUDGET
    assert refused and "Retrieval budget exhausted" in str(refused[0]["content"])


def test_query_knowledge_answers_from_the_characters_beliefs():
    game, player, friend = _scene()
    friend.knowledge.add("The tower door is locked.", topic="tower")
    friend.knowledge.add("The cook hides a spare key.", topic="kitchen")
    ask = {"tool_calls": [{"name": "query_knowledge", "arguments": {"topic": "tower"}}]}
    client = MockLlmClient(tool_calls_responses=[ask, GO_NORTH])
    agent = _agent(client)
    agent.action_names = list(game.parser.actions)

    acted = decide_and_route(friend, game, agent, build_npc_context(friend, game))

    assert acted is True
    results = _result_blocks(client.tool_calls_log[1]["messages"])
    answer = next(str(b["content"]) for b in results if not b["is_error"])
    assert "The tower door is locked." in answer
    assert "cook" not in answer  # only the asked topic, not every belief


# --- toolset gating + formatting (unit level) --------------------------------


def test_cognition_toolset_offers_only_attached_nonempty_sources():
    agent = _agent(MockLlmClient())  # empty memory, no plan
    tools, execute = cognition_toolset(agent, knowledge=Knowledge(owner="x"))
    assert tools == []  # nothing to consult -> nothing offered
    assert execute("recall", {"query": "x"}) is None  # not a cognition call


def test_cognition_toolset_full_sources_and_read_plan_format():
    agent = _agent(MockLlmClient())
    agent.memory.add_observation("I opened the cafe.", turn=1)
    agent.plan = DailyPlan(stops=[Stop(place="Hall", activity="sweep")])
    knowledge = Knowledge(owner="friend")
    knowledge.add("The tower door is locked.", topic="tower")
    traced = []
    tools, execute = cognition_toolset(
        agent, knowledge=knowledge, turn=2, trace=traced.append
    )
    assert {t["name"] for t in tools} == COGNITION_NAMES

    text, is_error, done = execute("read_plan", {})
    assert (is_error, done) == (False, False)
    assert "sweep at Hall" in text  # planning.plan_memory_lines formatting

    text, is_error, done = execute("recall", {"query": "cafe"})
    assert not is_error and "I opened the cafe." in text

    # The budget is per executor (per decision episode): a third call this
    # episode is refused, so we take a fresh toolset for the no-match probe.
    _, fresh_execute = cognition_toolset(agent, knowledge=knowledge, turn=2)
    text, is_error, done = fresh_execute("query_knowledge", {"topic": "moat"})
    assert not is_error and "no beliefs about 'moat'" in text

    # Each successful call produced one summary trace line.
    assert traced == ["read_plan() -> 1 lines", "recall('cafe') -> 1 memories"]


def test_cognition_tool_exception_becomes_is_error_and_agent_still_acts():
    game, player, friend = _scene()
    client = MockLlmClient(tool_calls_responses=[RECALL, GO_NORTH])
    agent = _agent(client)
    agent.action_names = list(game.parser.actions)
    agent.memory.add_observation("I saw the player.", turn=0)

    def boom(**kwargs):
        raise RuntimeError("index corrupted")

    agent.memory.retrieve = boom

    acted = decide_and_route(friend, game, agent, build_npc_context(friend, game))

    assert acted is True  # the failed recall never crashed the turn
    results = _result_blocks(client.tool_calls_log[1]["messages"])
    assert any(
        b["is_error"] and "index corrupted" in str(b["content"]) for b in results
    )


# --- acceptance 2: a dialogue line grounded in a recalled memory -------------


def _dialogue_pair(alice_agent):
    plaza = things.Location("Plaza", "the plaza")
    alice = things.Character("alice", "alice", "")
    bob = things.Character("bob", "bob", "")
    player = things.Character("player", "you", "")
    plaza.add_character(alice)
    plaza.add_character(bob)
    plaza.add_character(player)
    alice.set_agent(alice_agent)
    bob.set_agent(ScriptedAgent(lambda obs: None))  # silent partner
    game = games.Game(plaza, player, characters=[alice, bob])
    return game, alice, bob


def test_converse_line_grounded_in_recalled_memory():
    # The responder speaks a line composed FROM the recall tool_result it was
    # handed -- so the assertion genuinely proves the dialogue is grounded in
    # what the agent chose to recall, not in anything pre-scripted.
    def responder(messages, tools, tool_choice, max_tokens, temperature):
        recalled = None
        for m in messages:
            if isinstance(m["content"], list):
                for b in m["content"]:
                    if b["type"] == "tool_result" and not b["is_error"]:
                        recalled = str(b["content"])
        if recalled is None:
            return {"tool_calls": [{"name": "recall", "arguments": {"query": "bob"}}]}
        line = "I remember -- " + recalled.splitlines()[-1].strip()
        return {
            "tool_calls": [
                {"name": "speak", "arguments": {"utterance": line, "done": True}}
            ]
        }

    client = MockLlmClient(tool_calls_responses=responder)
    agent = _agent(client)
    agent.memory.add_observation("bob said he loves gardening.", turn=0, importance=5)
    game, alice, bob = _dialogue_pair(agent)

    result = convo.converse(game, alice, bob, turn=1)

    assert [name for name, _ in result.lines] == ["alice"]  # done=True ended it
    assert "loves gardening" in result.lines[0][1]
    # The recall was buffered for the AGENT_* trace (emitted by the convo loop).
    assert any(t.startswith("recall('bob')") for t in agent.last_cognition_trace)


def test_converse_flag_on_without_sources_falls_back_to_plain_speak():
    client = MockLlmClient(tool_responses=[{"utterance": "hi", "done": True}])
    agent = _agent(client)  # flag on, but empty memory and no plan
    game, alice, bob = _dialogue_pair(agent)
    result = convo.converse(game, alice, bob, turn=0)
    assert [t for _, t in result.lines] == ["hi"]
    assert client.tool_calls_log == []  # no tool-loop request was made


# --- acceptance 3: default-off leaves today's paths untouched ----------------


def test_flag_off_offers_no_cognition_tools_even_with_sources():
    game, player, friend = _scene()
    friend.knowledge.add("The tower door is locked.", topic="tower")
    client = MockLlmClient(tool_calls_responses=[GO_NORTH])
    agent = LLMAgent(client, persona="I am friendly.")  # default: flag off
    agent.action_names = list(game.parser.actions)
    agent.memory.add_observation("I saw the player.", turn=0)
    agent.plan = DailyPlan(stops=[Stop(place="Hall", activity="sweep")])

    acted = decide_and_route(friend, game, agent, build_npc_context(friend, game))

    assert acted is True
    offered = {t["name"] for t in client.tool_calls_log[0]["tools"]}
    assert not (COGNITION_NAMES & offered)


def test_flag_off_converse_never_touches_the_tool_loop():
    client = MockLlmClient(tool_responses=[{"utterance": "hi", "done": True}])
    agent = LLMAgent(client)  # default: flag off
    agent.memory.add_observation("bob loves gardening.", turn=0)
    line = agent.converse("You are talking with bob.", "bob")
    assert line == "hi"
    assert client.tool_calls_log == []  # call_tools never invoked
    assert client.tool_calls[0]["tool"]["name"] == "speak"  # today's exact path


# --- config wiring: the flag flows through make_react_behavior ---------------


def test_agent_config_flag_wires_cognition_tools_into_live_turn():
    game, player, friend = _scene()
    wait = {"tool_calls": [{"name": "wait", "arguments": {"arguments": ""}}]}
    client = MockLlmClient(tool_calls_responses=[GO_NORTH, RECALL, wait])
    friend.set_behavior(
        make_react_behavior(client, config=AgentConfig(cognition_tools=True))
    )

    friend.take_turn(game)  # turn 1: no memories yet, so recall is not offered
    assert "recall" not in {t["name"] for t in client.tool_calls_log[0]["tools"]}
    assert friend.location.name == "Yard"

    friend.take_turn(game)  # turn 2: the success memory exists -> recall offered
    offered = {t["name"] for t in client.tool_calls_log[1]["tools"]}
    assert "recall" in offered
    # The agent recalled its own turn-1 memory, then acted (wait) as usual.
    results = _result_blocks(client.tool_calls_log[2]["messages"])
    assert any(
        'I tried "go north" and succeeded.' in str(b["content"]) for b in results
    )
