"""Offline tests for wiring per-agent memory into the Smallville sim (issue #75).

The engine's memory stream (``text_adventure_games/memory.py``) is exercised in
the engine suite (``tests/test_memory.py``). These tests cover the *port-side*
wiring: the custom step loop (``run_simulation.simulate``) drives the engine's
decision seam directly rather than through ``react_behavior``, so the
perceive -> retrieve -> remember loop is reproduced by the helpers in
``backend.smallville_agents``. They mirror sections E (event visibility) and F
(loop integration) of ``tests/test_memory.py``, adapted to the Smallville cast.

Everything here is fully offline (mock client, ``build_world`` or the synthetic
maze fixture) and deterministic. Run from ``generative-agents``::

    uv run pytest tests/test_memory_wiring.py -v
"""

import pytest

from backend.build_world import PERSONAS, build_world
from backend.run_simulation import simulate
from backend.smallville_agents import (
    attach_agents,
    observe_and_decide,
    remember_outcome,
)
from backend.world_map import WorldMap
from synthetic_ville import build_synthetic_ville
from text_adventure_games.embedding_client import MockEmbeddingClient
from text_adventure_games.memory import MemoryKind

# Substrings the mock brain keys on (copied from tests/test_memory.py): a memory
# block becomes part of the observation prompt, so a rendered memory must never
# echo them or it could spoof a decision.
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
FORBIDDEN_CS = ["AM", "PM", "Turn:"]


@pytest.fixture(scope="module")
def world_map(tmp_path_factory):
    ville = build_synthetic_ville(str(tmp_path_factory.mktemp("ville")))
    return WorldMap(ville)


def _observation_seen_by(char):
    """The last observation string the agent's mock client was handed.

    The structured (tool) route is the one LLMAgent.decide prefers, so the
    observation is the final user message of the last recorded tool call.
    """
    return char.agent.llm_client.tool_calls[-1]["messages"][-1]["content"]


# --------------------------------------------------------------------------
# Determinism: memory must not change the replay
# --------------------------------------------------------------------------


def test_memory_wiring_preserves_frame_contract(world_map):
    # Same structural invariants as test_simulate_frames_match_contract: folding
    # memory into the observation must not perturb the movement frames.
    frames = simulate(world_map, num_steps=12)
    assert len(frames) == 12
    names = {p["name"] for p in PERSONAS}
    for frame in frames:
        assert set(frame.keys()) == names
        for entry in frame.values():
            assert isinstance(entry["movement"], list) and len(entry["movement"]) == 2
            assert all(isinstance(c, int) for c in entry["movement"])
            assert isinstance(entry["pronunciatio"], str) and entry["pronunciatio"]
            assert (
                isinstance(entry["description"], str) and " @ " in entry["description"]
            )
            assert entry["chat"] is None


def test_simulate_is_deterministic_with_memory(world_map):
    # Each simulate() builds its own game + fresh memories, so two runs must be
    # byte-for-byte identical -- no memory state leaks across runs, and the
    # retrieved-memory block never sways the deterministic travel/perform call.
    assert simulate(world_map, num_steps=20) == simulate(world_map, num_steps=20)


def test_simulate_reaches_activity_unchanged(world_map):
    # The believability block sits after the environment text, below the line the
    # mock reads, so Isabella still arrives and settles in within 40 steps.
    frames = simulate(world_map, num_steps=40)
    assert "tending the cafe counter" in frames[-1]["Isabella Rodriguez"]["description"]


def test_simulate_with_embedding_client_replay_is_byte_identical(world_map):
    # Semantic memory relevance (issue #76) must not change the *replay*: the mock
    # brain decides from the location line alone, so sprite movement, emoji, and
    # labels stay byte-for-byte identical with or without embeddings. The one field
    # embeddings *do* change is the per-agent "memories" panel (issue #109) -- with
    # vision-radius perception (#82) each agent forms enough memories that semantic
    # vs keyword relevance surface a different top-k. That divergence is the whole
    # point of embeddings, so it's excluded from this replay comparison.
    def replay(frames):
        return [
            {
                name: {k: v for k, v in entry.items() if k != "memories"}
                for name, entry in frame.items()
            }
            for frame in frames
        ]

    baseline = simulate(world_map, num_steps=20)
    with_embeddings = simulate(
        world_map, num_steps=20, embedding_client=MockEmbeddingClient()
    )
    assert replay(with_embeddings) == replay(baseline)


def test_embedding_client_reaches_retrieval():
    # Wiring check: with an embedding client attached, the first decide() runs the
    # embedding relevance path, which embeds and caches each record's vector. The
    # seeded plan memory at t=0 should come back with an embedding populated.
    game, chars = build_world()
    attach_agents(chars, PERSONAS, embedding_client=MockEmbeddingClient())
    char = chars[PERSONAS[0]["name"]]
    observe_and_decide(game, char, step=0)
    assert any(r.embedding is not None for r in char.agent.memory.records)


# --------------------------------------------------------------------------
# Seeding: one plan per persona at t=0
# --------------------------------------------------------------------------


def test_attach_seeds_one_plan_per_persona():
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    for spec in PERSONAS:
        agent = chars[spec["name"]].agent
        plans = [r for r in agent.memory.records if r.kind == MemoryKind.PLAN]
        assert len(plans) == 1
        plan = plans[0]
        assert plan.created_turn == 0
        assert plan.importance == 5.0
        assert agent.memory.owner == spec["name"]
        assert spec["destination"] in plan.text
        assert spec["activity"] in plan.text


def test_seeded_plans_avoid_mock_brain_triggers():
    # A future world_data.yaml edit must not introduce a persona whose plan would
    # spoof the mock brain once rendered into an observation.
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    for spec in PERSONAS:
        block = chars[spec["name"]].agent.memory.render()
        low = block.lower()
        for bad in FORBIDDEN_CI:
            assert bad not in low, f"{spec['name']}: {bad!r} in memory render"
        for bad in FORBIDDEN_CS:
            assert bad not in block, f"{spec['name']}: {bad!r} in memory render"


# --------------------------------------------------------------------------
# Remembering one's own actions (the first-person outcome)
# --------------------------------------------------------------------------


def test_travel_records_first_person_observation():
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    isabella = chars["Isabella Rodriguez"]
    game.turn = 0
    cmd = observe_and_decide(game, isabella, 0)
    assert cmd.startswith("travel")
    assert game.parser.parse_command(cmd, actor=isabella)
    remember_outcome(isabella, cmd, 0)

    own = [
        r
        for r in isabella.agent.memory.records
        if r.text == "I traveled to Hobbs Cafe."
    ]
    assert len(own) == 1
    assert own[0].kind == MemoryKind.OBSERVATION
    assert own[0].importance == 2.0
    assert own[0].created_turn == 0


def test_perform_records_activity_observation():
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    isabella = chars["Isabella Rodriguez"]
    # Travel to the cafe, then perform there.
    game.turn = 0
    travel = observe_and_decide(game, isabella, 0)
    game.parser.parse_command(travel, actor=isabella)
    remember_outcome(isabella, travel, 0)
    game.turn = 1
    perform = observe_and_decide(game, isabella, 1)
    assert perform.startswith("perform")
    assert game.parser.parse_command(perform, actor=isabella)
    remember_outcome(isabella, perform, 1)

    texts = [r.text for r in isabella.agent.memory.records]
    assert "I am tending the cafe counter." in texts


def test_memory_grows_as_agent_works_through_schedule():
    # The payoff of schedules (issue #83): an agent that works through several
    # stops keeps laying down new first-person memories, instead of the single
    # travel + perform a frozen one-stop agent would have. We drive the *logical*
    # transitions the step loop makes -- at each stop decide travel then perform,
    # record the outcome, then advance -- skipping only the visual tile walk.
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    isabella = chars["Isabella Rodriguez"]
    client = isabella.agent.llm_client
    # Isabella's stops are at distinct places, so each is one travel + one perform.
    for stop in range(len(client.schedule)):
        for _ in range(2):
            cmd = observe_and_decide(game, isabella, stop)
            assert game.parser.parse_command(cmd, actor=isabella)
            remember_outcome(isabella, cmd, stop)
        client.advance()

    texts = [r.text for r in isabella.agent.memory.records]
    activities = {t for t in texts if t.startswith("I am ")}
    travels = {t for t in texts if t.startswith("I traveled to ")}
    # Several distinct activities + destinations -- a stream that grew with the
    # day, not the lone pair a single-activity agent would be stuck with.
    assert len(activities) >= 3
    assert len(travels) >= 3


def test_own_action_not_double_perceived():
    # The engine logs a GameEvent for the move; ingest_events must skip the
    # actor's OWN event (it's already a first-person memory) -- no double-count.
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    isabella = chars["Isabella Rodriguez"]
    game.turn = 0
    cmd = observe_and_decide(game, isabella, 0)
    game.parser.parse_command(cmd, actor=isabella)
    remember_outcome(isabella, cmd, 0)

    assert isabella.agent.memory.ingest_events(game, isabella) == []
    # Exactly one memory of the move (the first-person one); no third-person echo.
    move_records = [
        r
        for r in isabella.agent.memory.records
        if "Hobbs Cafe" in r.text and "travel" in r.text.lower()
    ]
    assert move_records == [
        r for r in move_records if r.text == "I traveled to Hobbs Cafe."
    ]
    assert not any(
        r.text.startswith("Isabella Rodriguez did:")
        for r in isabella.agent.memory.records
    )


# --------------------------------------------------------------------------
# The believability win: perceiving a co-located resident
# --------------------------------------------------------------------------


def _both_at_cafe(game, chars):
    """Drive Isabella and Maria to Hobbs Cafe via the engine, logging events."""
    isabella, maria = chars["Isabella Rodriguez"], chars["Maria Lopez"]
    assert game.parser.parse_command("travel to Hobbs Cafe", actor=isabella)
    assert game.parser.parse_command("travel to Hobbs Cafe", actor=maria)
    assert isabella.location is maria.location  # same room now
    return isabella, maria


def test_resident_perceives_colocated_resident():
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    isabella, maria = _both_at_cafe(game, chars)

    # Maria, co-located, perceives Isabella's logged arrival -- and not her own.
    perceived = maria.agent.memory.ingest_events(game, maria)
    texts = [r.text for r in perceived]
    assert "Isabella Rodriguez did: travel to Hobbs Cafe" in texts
    assert all(not t.startswith("Maria Lopez did:") for t in texts)
    assert all(r.kind == MemoryKind.OBSERVATION for r in perceived)


def test_perceived_memory_enters_observation():
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    isabella, maria = _both_at_cafe(game, chars)

    # Maria deliberates again: the perception is folded in and retrieved into the
    # observation she reasons over -- but memory is context, not authority, so the
    # deterministic decision (she's at the cafe -> perform) is unchanged.
    game.turn = 1
    cmd = observe_and_decide(game, maria, 1)
    observation = _observation_seen_by(maria)
    assert "Relevant memories:" in observation
    assert "Isabella Rodriguez did: travel to Hobbs Cafe" in observation
    assert cmd.startswith("perform")


def test_resident_ignores_event_in_other_location():
    # Klaus, away at the college, perceives nothing of Isabella's cafe arrival.
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    isabella, klaus = chars["Isabella Rodriguez"], chars["Klaus Mueller"]
    assert game.parser.parse_command("travel to Hobbs Cafe", actor=isabella)
    assert isabella.location is not klaus.location
    assert klaus.agent.memory.ingest_events(game, klaus) == []


def test_one_resident_memory_not_in_anothers_prompt():
    # Privacy: a distinctive, high-importance memory of one resident never leaks
    # into another resident's observation (separate AgentMemory per agent).
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    isabella, klaus = chars["Isabella Rodriguez"], chars["Klaus Mueller"]
    secret = "a private daydream about rare imported coffee beans"
    isabella.agent.memory.add_observation(secret, turn=0, importance=9.0)

    game.turn = 1
    observe_and_decide(game, klaus, 1)
    assert secret not in _observation_seen_by(klaus)
