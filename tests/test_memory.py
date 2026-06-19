"""Tests for the per-agent episodic memory stream (issues #37 / #75).

Covers six things:

  A. The pure data model and serialization (``MemoryRecord`` / ``AgentMemory``).
  B. Deterministic scoring (recency / importance / keyword relevance).
  C. ``retrieve()`` -- ordering, last-accessed bookkeeping, the token budget,
     and the empty-render guard + render format.
  D. The mock-brain authoring rule: a rendered memory block must never contain a
     substring the mock ReAct brain keys on (mirrors ``test_knowledge.py``).
  E. ``ingest_events()`` visibility: own actions skipped, co-located actions and
     payload-naming events kept, other rooms ignored, idempotent advance.
  F. Integration with the ReAct loop: relevant memories enter the prompt, action
     outcomes are stored, and one NPC's memory never leaks into another's prompt
     or into the shared command history.

Run with pytest::

    pytest tests/test_memory.py -v
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.llm_client import MockLlmClient
from text_adventure_games.embedding_client import MockEmbeddingClient
from text_adventure_games.memory import (
    AgentMemory,
    MemoryKind,
    MemoryRecord,
    cosine_similarity,
    importance_score,
    recency_score,
    relevance_score,
    render_memories,
)
from text_adventure_games.npc import LLMAgent, react_behavior
from text_adventure_games.webapp.web_parser import WebParser

# Substrings the mock ReAct brain (llm_client.py) keys on. A rendered memory
# block becomes part of an NPC's observation, so it must contain none of these
# or it would spoof a mock-brain rule or the _player_present split. Kept in sync
# with the identical list in test_knowledge.py (the belief layer has the same
# rule). The mock lowercases the observation, so these match case-insensitively.
FORBIDDEN_CI = [
    "inventory",
    "characters here:",
    "growls",
    "snarls",
    "' failed:",
    "last warning",
    "you don't belong here",
    "leave this place, mortal",
    "doesn't have a weapon",
    "eats the fish",
]
# describe_for emits these verbatim (clock AM/PM, the Turn: line); the mock brain
# does not lower() these particular checks, so guard them case-sensitively.
FORBIDDEN_CS = ["AM", "PM", "Turn:"]


def _record(importance=1.0, created_turn=0, last_accessed_turn=None, text="x"):
    """A bare MemoryRecord for scoring tests (id/kind are irrelevant here)."""
    return MemoryRecord(
        id=0,
        kind=MemoryKind.OBSERVATION,
        text=text,
        created_turn=created_turn,
        last_accessed_turn=(
            created_turn if last_accessed_turn is None else last_accessed_turn
        ),
        importance=importance,
    )


# ----------------------------------------------------------------------
# A. Data model & serialization
# ----------------------------------------------------------------------


def test_memory_record_round_trips():
    r = MemoryRecord(
        id=1,
        kind=MemoryKind.REFLECTION,
        text="The player may be friendly.",
        created_turn=2,
        last_accessed_turn=3,
        importance=7.0,
        actor="troll",
        source_event_ids=[4, 5],
        tags={"player", "trust"},
    )
    assert MemoryRecord.from_primitive(r.to_primitive()) == r


def test_record_load_tolerates_missing_optional_keys():
    # A leaner/older record dict (only the required fields) must still load.
    data = {"id": 0, "kind": "observation", "text": "saw the player", "created_turn": 1}
    r = MemoryRecord.from_primitive(data)
    assert r.importance == 1.0
    assert r.last_accessed_turn == 1  # defaults to created_turn
    assert r.tags == set() and r.source_event_ids == []


def test_append_only_assigns_increasing_ids():
    mem = AgentMemory(owner="troll")
    r0 = mem.add_observation("saw the player", turn=0)
    r1 = mem.add_reflection("the player seems friendly", turn=1, evidence_ids=[0])
    r2 = mem.add_plan("stay near the bridge", turn=2)
    assert [r.id for r in mem.records] == [0, 1, 2]
    assert (r0.kind, r1.kind, r2.kind) == (
        MemoryKind.OBSERVATION,
        MemoryKind.REFLECTION,
        MemoryKind.PLAN,
    )
    # Append-only: a later write never mutates an earlier record.
    assert mem.records[0] is r0 and r0.text == "saw the player"


def test_add_accrues_importance_since_reflection():
    mem = AgentMemory()
    mem.add_observation("x", turn=0, importance=3)
    mem.add_reflection("y", turn=0, importance=5)
    assert mem.importance_since_reflection == 8.0


def test_agent_memory_round_trips():
    mem = AgentMemory(owner="troll")
    mem.add_observation("saw the player", turn=1, importance=2)
    mem.add_reflection("the player seems friendly", turn=2, evidence_ids=[0])
    mem.last_seen_event_index = 7

    restored = AgentMemory.from_primitive(mem.to_primitive())
    assert restored.owner == "troll"
    assert [r.text for r in restored.records] == [
        "saw the player",
        "the player seems friendly",
    ]
    assert restored.last_seen_event_index == 7
    assert restored.importance_since_reflection == mem.importance_since_reflection
    # The id counter survives load, so new records keep unique ids.
    assert restored.add_observation("z", turn=3).id == 2


# ----------------------------------------------------------------------
# B. Deterministic scoring (docs/design/agent-memory.md §6)
# ----------------------------------------------------------------------


def test_recency_decays_with_turn_distance():
    r = _record(created_turn=0)
    assert recency_score(r, turn=0) == 1.0
    assert recency_score(r, turn=1) < 1.0
    assert recency_score(r, turn=5) < recency_score(r, turn=1)
    # A turn before last-accessed can't make a memory "more than fresh".
    assert recency_score(r, turn=-3) == 1.0


def test_importance_normalization_handles_1_10_and_invalid():
    assert importance_score(_record(importance=1)) == 0.1
    assert importance_score(_record(importance=10)) == 1.0
    assert importance_score(_record(importance=11)) == 1.0  # clamp high
    assert importance_score(_record(importance=0)) == 0.0
    assert importance_score(_record(importance=-5)) == 0.0  # clamp low


def test_relevance_keyword_overlap():
    query = "hungry troll wants fish"
    related = relevance_score(query, "the troll is very hungry")
    unrelated = relevance_score(query, "a sunny day in the meadow")
    assert related > unrelated
    assert unrelated == 0.0
    # A query of only stop-words has nothing to be relevant to.
    assert relevance_score("the a of to", "anything at all") == 0.0
    assert relevance_score("fish", "fish") == 1.0


# ----------------------------------------------------------------------
# B2. Embedding relevance (issue #76)
# ----------------------------------------------------------------------


def test_cosine_similarity_basic():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    # A zero vector has no direction to compare -- 0, like keyword no-match.
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_default_retrieve_leaves_embeddings_none():
    """Without an embedding client, relevance stays keyword overlap and no record
    is ever embedded -- the pre-#76 behavior, byte-for-byte."""
    mem = AgentMemory(owner="troll")
    r = mem.add_observation("dragons guard the gold", turn=0)
    mem.retrieve("dragons", turn=0)
    assert r.embedding is None


def test_retrieve_with_embedding_client_caches_vectors():
    """With a client, retrieve embeds each record once and caches it on the
    record (so a second retrieval reuses it rather than re-embedding)."""
    mem = AgentMemory(owner="troll", embedding_client=MockEmbeddingClient())
    r = mem.add_observation("dragons guard the gold", turn=0)
    assert r.embedding is None
    mem.retrieve("dragons", turn=0)
    assert r.embedding == MockEmbeddingClient().embed(["dragons guard the gold"])[0]


def test_retrieve_with_embedding_client_is_deterministic_and_relevant():
    """The embedding path ranks a semantically related memory above an unrelated
    one, deterministically across runs."""

    def run():
        mem = AgentMemory(owner="troll", embedding_client=MockEmbeddingClient())
        related = mem.add_observation("dragons breathe fire", turn=10, importance=1)
        unrelated = mem.add_observation("the weather is nice", turn=10, importance=1)
        out = mem.retrieve("dragons", turn=10, max_records=2)
        return out, related, unrelated

    out1, related, unrelated = run()
    out2, _, _ = run()
    assert out1[0] is related
    assert out1.index(related) < out1.index(unrelated)
    assert [r.id for r in out1] == [r.id for r in out2]


def test_cached_embedding_round_trips():
    """A record's cached embedding survives serialization (the field was always
    serialized; #76 just populates it)."""
    mem = AgentMemory(owner="troll", embedding_client=MockEmbeddingClient())
    mem.add_observation("dragons guard the gold", turn=0)
    mem.retrieve("dragons", turn=0)
    restored = AgentMemory.from_primitive(mem.to_primitive())
    assert restored.records[0].embedding == mem.records[0].embedding
    assert restored.records[0].embedding is not None


# ----------------------------------------------------------------------
# C. retrieve() and render()
# ----------------------------------------------------------------------


def test_retrieve_returns_top_records_deterministic_order():
    mem = AgentMemory(owner="troll")
    relevant = mem.add_observation("dragons guard the gold", turn=10, importance=1)
    irrelevant = mem.add_observation("the weather is nice", turn=10, importance=1)
    best = mem.add_observation("dragons breathe fire", turn=10, importance=10)

    out = mem.retrieve("dragons", turn=10, max_records=3)
    assert out[0] is best  # relevance + top importance wins
    assert out.index(relevant) < out.index(irrelevant)


def test_retrieve_updates_last_accessed_turn():
    mem = AgentMemory(owner="troll")
    r = mem.add_observation("the player gave me a fish", turn=0)
    assert r.last_accessed_turn == 0
    mem.retrieve("fish", turn=5)
    assert r.last_accessed_turn == 5


def test_token_budget_limits_count():
    mem = AgentMemory(owner="troll")
    for i in range(5):
        mem.add_observation(f"memory {i} about apples and oranges", turn=0)
    generous = mem.retrieve("apples", turn=0, max_records=10, token_budget=10_000)
    tight = mem.retrieve("apples", turn=0, max_records=10, token_budget=10)
    assert len(generous) == 5
    assert 1 <= len(tight) < 5  # always keep at least one, but the budget bites


def test_render_empty_is_blank():
    # Load-bearing: an agent with nothing to recall gets a byte-identical prompt.
    assert AgentMemory().render() == ""
    assert render_memories([]) == ""


def test_render_format():
    mem = AgentMemory(owner="troll")
    mem.add_observation("The player gave me a fish.", turn=3)
    mem.add_reflection("The player may be friendly.", turn=4)
    rendered = mem.render()
    assert rendered.startswith("Relevant memories:")
    assert " - [observation, turn 3] The player gave me a fish." in rendered
    assert " - [reflection, turn 4] The player may be friendly." in rendered


# ----------------------------------------------------------------------
# D. Mock-brain authoring rule
# ----------------------------------------------------------------------


def test_memory_render_avoids_mock_brain_triggers():
    mem = AgentMemory(owner="troll")
    # Stage-3 event sentences are built from command summaries, not narration.
    mem.add_observation("player did: give fish to troll", turn=1)
    mem.add_observation("guard did: go north", turn=1)
    # Stage-4 outcome sentences, with a neutral failure reason.
    mem.add_observation('I tried "open door" and succeeded.', turn=2, importance=3)
    mem.add_observation(
        'I tried "go south" but it failed because there is no exit that way',
        turn=2,
        importance=4,
    )
    rendered = mem.render()
    lowered = rendered.lower()
    for bad in FORBIDDEN_CI:
        assert bad not in lowered, f"memory render leaked mock-brain trigger: {bad!r}"
    for bad in FORBIDDEN_CS:
        assert (
            bad not in rendered
        ), f"memory render leaked case-sensitive trigger: {bad!r}"


# ----------------------------------------------------------------------
# E. ingest_events() visibility
# ----------------------------------------------------------------------


@pytest.fixture
def ingest_world():
    """A 2-room world: player + troll in the Field, an owl in the Forest."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)

    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")
    owl = things.Character("owl", "a watchful owl", "I observe.")

    game = games.Game(field, player, characters=[troll, owl])
    field.add_character(troll)
    forest.add_character(owl)
    return game, player, troll, owl


def test_ingest_skips_own_actions(ingest_world):
    game, player, troll, owl = ingest_world
    mem = AgentMemory(owner="troll")
    game.log_event("troll", "growl", summary="growl player")
    assert mem.ingest_events(game, troll) == []  # own action -> recorded as outcome


def test_ingest_records_colocated_actor_event(ingest_world):
    game, player, troll, owl = ingest_world
    mem = AgentMemory(owner="troll")
    game.log_event("player", "go", summary="go north")  # player shares the Field
    added = mem.ingest_events(game, troll)
    assert len(added) == 1
    assert added[0].text == "player did: go north"
    assert added[0].source_event_ids == [0]


def test_ingest_ignores_events_in_other_locations(ingest_world):
    game, player, troll, owl = ingest_world
    mem = AgentMemory(owner="troll")
    game.log_event("owl", "hoot", summary="hoot")  # owl is in the Forest
    assert mem.ingest_events(game, troll) == []


def test_ingest_records_event_naming_agent_in_payload(ingest_world):
    game, player, troll, owl = ingest_world
    mem = AgentMemory(owner="troll")
    # The owl is in another room, but the event is *about* the troll.
    game.log_event(
        "owl", "warn", summary="hoots a warning", payload={"target": "troll"}
    )
    added = mem.ingest_events(game, troll)
    assert len(added) == 1
    assert added[0].text == "owl did: hoots a warning"


def test_ingest_advances_index_and_is_idempotent(ingest_world):
    game, player, troll, owl = ingest_world
    mem = AgentMemory(owner="troll")
    game.log_event("player", "go", summary="go north")
    assert len(mem.ingest_events(game, troll)) == 1
    assert mem.last_seen_event_index == len(game.events)
    # No new events -> a second call adds nothing.
    assert mem.ingest_events(game, troll) == []
    # A fresh event is picked up on the next call.
    game.log_event("player", "take", summary="take rock")
    assert len(mem.ingest_events(game, troll)) == 1


# ----------------------------------------------------------------------
# F. ReAct-loop integration
# ----------------------------------------------------------------------


@pytest.fixture
def react_world():
    """Field (player, troll, guard) --north--> Forest, with a WebParser."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)

    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")
    guard = things.Character("guard", "a stern guard", "I keep watch.")

    game = games.Game(field, player, characters=[troll, guard])
    field.add_character(troll)
    field.add_character(guard)
    game.set_parser(WebParser(game))
    return game, player, troll, guard


def _last_prompt(mock):
    """The user-message content of the agent's most recent LLM call."""
    return mock.calls[-1]["messages"][-1]["content"]


def test_relevant_prior_memory_enters_prompt(react_world):
    game, player, troll, guard = react_world
    mock = MockLlmClient(["go north"])
    agent = LLMAgent(mock, persona="I am a troll.")
    agent.memory.owner = "troll"
    agent.memory.add_observation("The player gave me a fish.", turn=0, importance=8)

    react_behavior(troll, game, agent)

    prompt = _last_prompt(mock)
    assert "Relevant memories:" in prompt
    assert "The player gave me a fish." in prompt


def test_failed_command_stored_as_memory(react_world):
    game, player, troll, guard = react_world
    mock = MockLlmClient(["go south"])  # no south exit -> fails
    agent = LLMAgent(mock, persona="I am a troll.")

    react_behavior(troll, game, agent, max_retries=0)

    failures = [
        r for r in agent.memory.records if "go south" in r.text and "failed" in r.text
    ]
    assert len(failures) == 1
    assert failures[0].importance == 4


def test_successful_command_stored_as_memory(react_world):
    game, player, troll, guard = react_world
    mock = MockLlmClient(["go north"])
    agent = LLMAgent(mock, persona="I am a troll.")

    react_behavior(troll, game, agent)

    assert any(
        'I tried "go north" and succeeded.' == r.text for r in agent.memory.records
    )


def test_one_npc_memory_not_in_another_npc_prompt(react_world):
    game, player, troll, guard = react_world
    secret = "The player gave me a fish."

    troll_agent = LLMAgent(MockLlmClient(["go north"]), persona="I am a troll.")
    troll_agent.memory.owner = "troll"
    troll_agent.memory.add_observation(secret, turn=0, importance=9)

    guard_mock = MockLlmClient(["go north"])
    guard_agent = LLMAgent(guard_mock, persona="I am a guard.")
    react_behavior(guard, game, guard_agent)

    guard_prompt = _last_prompt(guard_mock)
    assert secret not in guard_prompt
    assert "Relevant memories:" not in guard_prompt  # guard has no memories of its own


def test_memory_never_leaks_into_command_history(react_world):
    game, player, troll, guard = react_world
    secret = "The player gave me a fish."
    agent = LLMAgent(MockLlmClient(["go north"]), persona="I am a troll.")
    agent.memory.owner = "troll"
    agent.memory.add_observation(secret, turn=0, importance=9)

    react_behavior(troll, game, agent)

    history = " ".join(e["content"] for e in game.parser.command_history)
    assert secret not in history
    assert "Relevant memories:" not in history
