"""The headless FastAPI backend that drives the engine (issue #179, #186).

Exercises the full app in-process via FastAPI's ``TestClient`` (no socket), plus
the pure ``run_command`` helper. Offline; requires the ``server`` extra (fastapi,
uvicorn) and ``httpx`` (TestClient) -- skipped cleanly if they're absent.
"""

import threading
import time
import urllib.parse
from collections import Counter

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from backend.api import (  # noqa: E402
    _demo_game,
    _demo_stepper,
    create_app,
    run,
    run_command,
)
from backend.cognition import (  # noqa: E402
    memories_for_frame,
    memory_stream_for_persona,
)
from text_adventure_games import games, things  # noqa: E402
from text_adventure_games.npc import ScriptedAgent  # noqa: E402
from text_adventure_games.planning import (  # noqa: E402
    DailyPlan,
    DayBlock,
    HourBlock,
    Stop,
    replace_tail,
)
from text_adventure_games.usage import UsageLedger  # noqa: E402


def _tiny():
    field = things.Location("Field", "An open field.")
    forest = things.Location("Forest", "A wood.")
    field.add_connection("north", forest)
    player = things.Character("player", "you", "I explore.")
    return games.Game(field, player, characters=[])


def _with_agent(name="gardener"):
    """A tiny world plus one NPC whose agent carries two seeded memories.

    Mirrors ``_demo_game``'s pattern: a do-nothing ``ScriptedAgent`` (never
    acts) holding a real ``AgentMemory``, seeded the way ``backend/seed.py``
    seeds personas (observations at turn 0). Returns ``(game, npc)`` so tests
    can also reach the agent directly."""
    field = things.Location("Field", "An open field.")
    forest = things.Location("Forest", "A wood.")
    field.add_connection("north", forest)
    player = things.Character("player", "you", "I explore.")
    npc = things.Character(name, "a quiet resident", "I live here.")
    field.add_character(npc)
    agent = ScriptedAgent(lambda observation: None, persona=npc.persona)
    agent.memory.owner = npc.name
    agent.memory.add_observation("I saw the sun rise.", turn=0, importance=3.0)
    agent.memory.add_plan("Walk to the forest.", turn=0)
    npc.set_agent(agent)
    return games.Game(field, player, characters=[npc]), npc


def _client(game=None, **kwargs):
    return TestClient(create_app(game or _tiny(), **kwargs))


# --- GET endpoints --------------------------------------------------------


def test_health_reports_liveness_and_turn():
    resp = _client().get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "turn": 0}


def test_world_state_endpoint_returns_the_snapshot():
    payload = _client().get("/world_state").json()
    assert payload["schema_version"] == "1.0"
    assert payload["player"] == "player"
    assert {loc["name"] for loc in payload["locations"]} == {"Field", "Forest"}


def test_get_world_state_is_read_only():
    game = _tiny()
    client = _client(game)
    a = client.get("/world_state").json()
    b = client.get("/world_state").json()
    assert a == b  # deterministic + unchanged
    assert game.turn == 0  # a GET never advanced the game


# --- POST /command --------------------------------------------------------


def test_command_runs_and_returns_events_plus_new_state():
    payload = _client().post("/command", json={"command": "go north"}).json()
    assert any(e["channel"] == "narration" for e in payload["events"])
    player = next(
        c for c in payload["world_state"]["characters"] if c["name"] == "player"
    )
    assert player["location"] == "Forest"  # the snapshot reflects the move
    assert payload["game_over"] is False


def test_blocked_command_returns_200_with_a_blocked_event():
    # A command the ENGINE rejects (failed precondition) is still a successful
    # request: 200, with the rejection surfaced as a BLOCKED event.
    resp = _client().post("/command", json={"command": "go south"})
    assert resp.status_code == 200
    payload = resp.json()
    assert any(e["channel"] == "blocked" for e in payload["events"])
    assert payload["game_over"] is False


def test_missing_command_is_422():
    assert _client().post("/command", json={}).status_code == 422


def test_empty_command_is_422():
    assert _client().post("/command", json={"command": "  "}).status_code in (
        200,  # stripped to empty only after validation; min_length sees the spaces
        422,
    )
    # A truly empty string fails min_length=1 outright.
    assert _client().post("/command", json={"command": ""}).status_code == 422


def test_non_string_command_is_422_and_does_not_run():
    game = _tiny()
    resp = _client(game).post("/command", json={"command": ["go", "north"]})
    assert resp.status_code == 422
    assert game.turn == 0  # never coerced into a real command


def test_bad_json_body_is_422():
    resp = _client().post(
        "/command", content="not json", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 422


def test_unknown_path_is_404():
    assert _client().get("/nope").status_code == 404


def test_engine_exception_returns_500_and_restores_renderer():
    game = _tiny()
    original = game.parser.renderer

    def boom(_command):
        raise RuntimeError("kaboom")

    game.do_command = boom
    resp = _client(game).post("/command", json={"command": "x"})
    assert resp.status_code == 500
    assert game.parser.renderer is original  # restored despite the engine error


# --- GET /agents/{name}/memory (#298) --------------------------------------


def test_memory_endpoint_returns_seeded_stream():
    game, _npc = _with_agent()
    payload = _client(game).get("/agents/gardener/memory").json()
    assert set(payload) == {"persona", "turn", "count", "memories"}
    assert payload["persona"] == "gardener"
    assert payload["turn"] == 0
    assert payload["count"] == len(payload["memories"]) == 2
    for entry in payload["memories"]:
        assert set(entry) == {"kind", "importance", "text", "created_turn"}
    # Chronological append order, exactly as seeded.
    assert [m["kind"] for m in payload["memories"]] == ["observation", "plan"]


def test_memory_matches_memory_stream_for_persona():
    # The endpoint and the replay bake must emit the same stream: both go
    # through memory_stream_for_persona, so a baked memory_streams block and a
    # live fetch of the same agent can never drift apart.
    game, npc = _with_agent()
    payload = _client(game).get("/agents/gardener/memory").json()
    assert payload["memories"] == memory_stream_for_persona(npc.agent)


def test_memory_grows_mid_run():
    # The acceptance test for #298: memories formed DURING a run are visible
    # without waiting for any end-of-run export.
    game, npc = _with_agent()
    client = _client(game)
    before = client.get("/agents/gardener/memory").json()
    npc.agent.memory.add_observation("The player walked past me.", turn=1)
    after = client.get("/agents/gardener/memory").json()
    assert after["count"] == before["count"] + 1
    assert after["memories"][-1]["text"] == "The player walked past me."
    assert after["memories"][-1]["created_turn"] == 1
    assert after["memories"][: before["count"]] == before["memories"]


def test_memory_unknown_character_is_404():
    game, _npc = _with_agent()
    resp = _client(game).get("/agents/nobody/memory")
    assert resp.status_code == 404
    assert "unknown" in resp.json()["detail"]


def test_memory_character_without_agent_is_404():
    # The player exists but has no agent bound -- there is no stream to read,
    # which is a different failure from an unknown name (distinct detail).
    game, _npc = _with_agent()
    resp = _client(game).get("/agents/player/memory")
    assert resp.status_code == 404
    assert "no agent" in resp.json()["detail"]


def test_memory_requires_auth_when_token_configured():
    game, _npc = _with_agent()
    client = _client(game, auth_token="s3cret")
    assert client.get("/agents/gardener/memory").status_code == 401
    ok = client.get(
        "/agents/gardener/memory", headers={"Authorization": "Bearer s3cret"}
    )
    assert ok.status_code == 200


def test_memory_get_is_read_only():
    game, npc = _with_agent()
    client = _client(game)
    a = client.get("/agents/gardener/memory").json()
    b = client.get("/agents/gardener/memory").json()
    assert a == b
    assert game.turn == 0  # never advanced the game
    assert len(npc.agent.memory.records) == 2  # never wrote a memory


def test_memory_persona_name_with_space():
    # Real casts use full names ("Maya Chen"); the client URL-encodes the
    # space. Names are exact-match and case-sensitive -- no fuzzy matching.
    game, _npc = _with_agent(name="Maya Chen")
    client = _client(game)
    assert client.get("/agents/Maya%20Chen/memory").json()["persona"] == "Maya Chen"
    assert client.get("/agents/maya%20chen/memory").status_code == 404


def test_demo_game_serves_a_memory_stream():
    # Protects the README curl walkthrough: the stock demo world must expose
    # the gardener's seeded stream with no LLM or API key.
    payload = TestClient(create_app(_demo_game())).get("/agents/gardener/memory").json()
    assert payload["count"] >= 1
    assert {m["kind"] for m in payload["memories"]} == {"observation", "plan"}


# --- GET /agents/{name}/memory filters: since_turn / kind / limit (#345) ---


def _rich_stream(name="gardener"):
    """A world whose one agent carries a known 5-memory stream spanning three
    turns and three kinds, so the #345 selectors have something to slice.

    Append order (== chronological):
        t0 observation, t0 plan, t1 observation, t2 reflection, t2 observation
    """
    field = things.Location("Field", "An open field.")
    player = things.Character("player", "you", "I explore.")
    npc = things.Character(name, "a quiet resident", "I live here.")
    field.add_character(npc)
    agent = ScriptedAgent(lambda observation: None, persona=npc.persona)
    agent.memory.owner = npc.name
    agent.memory.add_observation("The sun rose.", turn=0, importance=3.0)
    agent.memory.add_plan("Tend the field.", turn=0)
    agent.memory.add_observation("A stranger passed.", turn=1)
    agent.memory.add_reflection("The field is calm.", turn=2, importance=4.0)
    agent.memory.add_observation("Dusk settled.", turn=2)
    npc.set_agent(agent)
    return games.Game(field, player, characters=[npc]), npc


def test_memory_no_filter_omits_total_and_is_unchanged():
    # The #345 headline: a no-argument read is byte-identical to #298 -- no
    # `total` key, the whole stream, same shape.
    game, _npc = _rich_stream()
    payload = _client(game).get("/agents/gardener/memory").json()
    assert set(payload) == {"persona", "turn", "count", "memories"}  # no `total`
    assert payload["count"] == len(payload["memories"]) == 5


def test_memory_since_turn_returns_only_newer_records():
    game, _npc = _rich_stream()
    payload = (
        _client(game).get("/agents/gardener/memory", params={"since_turn": 1}).json()
    )
    assert payload["count"] == 2  # the two turn-2 records
    assert payload["total"] == 5  # "showing 2 of 5"
    assert all(m["created_turn"] > 1 for m in payload["memories"])


def test_memory_since_turn_empty_tail_is_a_prompt_200():
    # Acceptance: once a poller is caught up, the incremental fetch returns an
    # empty list promptly -- not a 404, not an error.
    game, _npc = _rich_stream()
    payload = (
        _client(game).get("/agents/gardener/memory", params={"since_turn": 2}).json()
    )
    assert payload["memories"] == []
    assert payload["count"] == 0
    assert payload["total"] == 5


def test_memory_kind_filter_selects_one_kind():
    game, _npc = _rich_stream()
    client = _client(game)
    obs = client.get("/agents/gardener/memory", params={"kind": "observation"}).json()
    assert obs["count"] == 3
    assert {m["kind"] for m in obs["memories"]} == {"observation"}
    assert obs["total"] == 5
    assert (
        client.get("/agents/gardener/memory", params={"kind": "plan"}).json()["count"]
        == 1
    )


def test_memory_unknown_kind_is_422_not_empty():
    # An unrecognised kind is a validation error, never a silently-empty stream.
    game, _npc = _rich_stream()
    resp = _client(game).get("/agents/gardener/memory", params={"kind": "banana"})
    assert resp.status_code == 422


def test_memory_limit_returns_newest_k_in_order():
    # limit keeps the tail (newest) of the stream, still chronological.
    game, npc = _rich_stream()
    full = memory_stream_for_persona(npc.agent)
    payload = _client(game).get("/agents/gardener/memory", params={"limit": 2}).json()
    assert payload["count"] == 2
    assert payload["memories"] == full[-2:]
    assert payload["total"] == 5


def test_memory_limit_must_be_positive():
    game, _npc = _rich_stream()
    resp = _client(game).get("/agents/gardener/memory", params={"limit": 0})
    assert resp.status_code == 422


def test_memory_filters_compose():
    # "newest observation formed after turn 0" -- all three selectors at once,
    # applied since_turn -> kind -> limit.
    game, _npc = _rich_stream()
    payload = (
        _client(game)
        .get(
            "/agents/gardener/memory",
            params={"since_turn": 0, "kind": "observation", "limit": 1},
        )
        .json()
    )
    assert payload["count"] == 1
    assert payload["total"] == 5
    only = payload["memories"][0]
    assert only["kind"] == "observation"
    assert only["created_turn"] == 2  # the newest observation after turn 0
    assert only["text"] == "Dusk settled."


def test_memory_since_turn_aligns_with_the_reported_cursor():
    # The intended incremental-poll loop: take the `turn` a read reports, then
    # re-fetch with since_turn=that turn to get exactly what formed after it.
    game, _npc = _rich_stream()
    client = _client(game)
    cursor = client.get("/health").json()["turn"]  # 0
    fresh = client.get("/agents/gardener/memory", params={"since_turn": cursor}).json()
    assert fresh["count"] == 3  # the turn-1 and turn-2 records
    assert all(m["created_turn"] > cursor for m in fresh["memories"])


# --- GET /agents roster (#344) ---------------------------------------------


def test_agents_roster_lists_only_agent_bound_characters():
    # The roster is the discovery list for /agents/{name}/memory: only
    # characters with a mind bound appear. The player (no agent) is absent.
    game, _npc = _with_agent()
    payload = _client(game).get("/agents").json()
    assert set(payload) == {"turn", "agents"}
    assert payload["turn"] == 0
    assert [a["name"] for a in payload["agents"]] == ["gardener"]


def test_agents_roster_entry_shape():
    game, _npc = _with_agent()
    (entry,) = _client(game).get("/agents").json()["agents"]
    assert set(entry) == {"name", "persona", "location", "memory_count", "kind_counts"}
    assert entry["name"] == "gardener"
    assert entry["persona"] == "I live here."  # Character(name, description, persona)
    assert entry["location"] == "Field"
    assert entry["memory_count"] == 2
    assert entry["kind_counts"] == {"observation": 1, "plan": 1}


def test_agents_roster_empty_world_is_not_an_error():
    # A world with no agent-bound characters (just the player) is well-formed,
    # not a 404/500: an empty list, so a client renders "no agents".
    payload = _client(_tiny()).get("/agents").json()
    assert payload == {"turn": 0, "agents": []}


def test_agents_roster_names_round_trip_to_memory_route():
    # Acceptance: every name the roster returns works verbatim (URL-encoded)
    # against /agents/{name}/memory -- including a full name with a space.
    game, _npc = _with_agent(name="Maya Chen")
    client = _client(game)
    roster = client.get("/agents").json()["agents"]
    assert [a["name"] for a in roster] == ["Maya Chen"]
    for entry in roster:
        encoded = urllib.parse.quote(entry["name"])
        assert client.get(f"/agents/{encoded}/memory").status_code == 200


def test_agents_roster_counts_match_the_memory_stream():
    # The roster tally must agree with the stream the memory route then serves,
    # so a sidebar badge and the opened panel can never disagree. Checked
    # against an independent Counter, not the helper the endpoint uses.
    game, npc = _with_agent()
    (entry,) = _client(game).get("/agents").json()["agents"]
    stream = memory_stream_for_persona(npc.agent)
    assert entry["memory_count"] == len(stream)
    assert entry["kind_counts"] == dict(Counter(m["kind"] for m in stream))


def test_agents_roster_reflects_mid_run_growth():
    # Like the memory route, the roster reads live objects: a memory formed
    # during the run bumps the count with no end-of-run export.
    game, npc = _with_agent()
    client = _client(game)
    before = client.get("/agents").json()["agents"][0]
    npc.agent.memory.add_reflection("The field is peaceful.", turn=1, importance=4.0)
    after = client.get("/agents").json()["agents"][0]
    assert after["memory_count"] == before["memory_count"] + 1
    assert after["kind_counts"]["reflection"] == 1


def test_agents_roster_requires_auth_when_token_configured():
    game, _npc = _with_agent()
    client = _client(game, auth_token="s3cret")
    assert client.get("/agents").status_code == 401
    ok = client.get("/agents", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_agents_roster_get_is_read_only():
    game, npc = _with_agent()
    client = _client(game)
    a = client.get("/agents").json()
    b = client.get("/agents").json()
    assert a == b
    assert game.turn == 0  # never advanced the game
    assert len(npc.agent.memory.records) == 2  # never wrote a memory


def test_demo_game_lists_exactly_the_gardener():
    # #344 acceptance on the stock demo world: exactly one entry (the gardener),
    # the player absent -- runnable with no LLM or API key.
    payload = TestClient(create_app(_demo_game())).get("/agents").json()
    assert [a["name"] for a in payload["agents"]] == ["gardener"]
    assert payload["agents"][0]["memory_count"] == 3


# --- GET /agents/{name}/knowledge (#348) -----------------------------------


def _seed_beliefs(npc):
    """Seed *npc* with a prior, a learned belief, and a topic-carrying one.

    Mirrors how ``backend/seed.py`` seeds knowledge: priors up front
    (``learned_turn`` None, the way #79 seeds spatial knowledge) plus beliefs
    learned during play (stamped with the turn). Returns *npc* for chaining."""
    npc.add_belief("The tower to the north is locked.")  # a prior
    npc.add_belief("There are strange runes on the door.", topic="runes")  # + topic
    npc.knowledge.learn("The gate opened at dawn.", turn=3)  # learned mid-run
    return npc


def test_knowledge_endpoint_returns_seeded_beliefs():
    game, npc = _with_agent()
    _seed_beliefs(npc)
    payload = _client(game).get("/agents/gardener/knowledge").json()
    assert set(payload) == {"persona", "turn", "count", "beliefs"}
    assert payload["persona"] == "gardener"
    assert payload["turn"] == 0
    assert payload["count"] == len(payload["beliefs"]) == 3
    for belief in payload["beliefs"]:
        assert set(belief) == {"text", "topic", "learned_turn"}
    # Priors (learned_turn None) and a learned belief (learned_turn set) coexist.
    learned = [b["learned_turn"] for b in payload["beliefs"]]
    assert learned == [None, None, 3]


def test_knowledge_beliefs_match_to_primitive():
    # The endpoint emits the save-file belief shape verbatim -- Knowledge's own
    # serializer -- so a wire read and a save file can never drift apart.
    game, npc = _with_agent()
    _seed_beliefs(npc)
    payload = _client(game).get("/agents/gardener/knowledge").json()
    assert payload["beliefs"] == npc.knowledge.to_primitive()["beliefs"]


def test_knowledge_reflects_beliefs_learned_mid_run():
    # The acceptance test for #348: beliefs learned DURING a run are visible,
    # stamped with learned_turn, alongside the untouched priors.
    game, npc = _with_agent()
    npc.add_belief("The field lies south of the forest.")  # a prior
    client = _client(game)
    before = client.get("/agents/gardener/knowledge").json()
    npc.knowledge.learn("A stranger camped by the north path.", turn=2)
    after = client.get("/agents/gardener/knowledge").json()
    assert after["count"] == before["count"] + 1
    assert after["beliefs"][-1]["text"] == "A stranger camped by the north path."
    assert after["beliefs"][-1]["learned_turn"] == 2
    assert after["beliefs"][: before["count"]] == before["beliefs"]


def test_knowledge_empty_belief_set_is_200_not_error():
    # A persona whose knowledge was never seeded (the fresh-checkout case where
    # #79 seeding no-ops) is an empty belief set, not an error.
    game, _npc = _with_agent()
    payload = _client(game).get("/agents/gardener/knowledge").json()
    assert payload["count"] == 0
    assert payload["beliefs"] == []


def test_knowledge_topic_filter():
    game, npc = _with_agent()
    _seed_beliefs(npc)
    client = _client(game)
    # ?topic= narrows to beliefs carrying that exact perception key.
    runes = client.get("/agents/gardener/knowledge", params={"topic": "runes"}).json()
    assert runes["count"] == 1
    assert runes["beliefs"][0]["topic"] == "runes"
    # An unmatched topic is an empty set, not a 404 (the character exists).
    none = client.get("/agents/gardener/knowledge", params={"topic": "nope"}).json()
    assert none["count"] == 0
    assert none["beliefs"] == []


def test_knowledge_unknown_character_is_404():
    game, _npc = _with_agent()
    resp = _client(game).get("/agents/nobody/knowledge")
    assert resp.status_code == 404
    assert "unknown" in resp.json()["detail"]


def test_knowledge_character_without_agent_is_404():
    # Knowledge lives on every character, but the /agents/ family reads a *mind*:
    # the player has no agent bound, so it 404s like the memory sibling does.
    game, _npc = _with_agent()
    resp = _client(game).get("/agents/player/knowledge")
    assert resp.status_code == 404
    assert "no agent" in resp.json()["detail"]


def test_knowledge_requires_auth_when_token_configured():
    game, npc = _with_agent()
    _seed_beliefs(npc)
    client = _client(game, auth_token="s3cret")
    assert client.get("/agents/gardener/knowledge").status_code == 401
    ok = client.get(
        "/agents/gardener/knowledge", headers={"Authorization": "Bearer s3cret"}
    )
    assert ok.status_code == 200


def test_knowledge_get_is_read_only():
    # Two reads with no turn between them are identical, and reading never
    # advances the game or mutates the belief set.
    game, npc = _with_agent()
    _seed_beliefs(npc)
    client = _client(game)
    a = client.get("/agents/gardener/knowledge").json()
    b = client.get("/agents/gardener/knowledge").json()
    assert a == b
    assert game.turn == 0
    assert len(npc.knowledge.beliefs) == 3


def test_knowledge_persona_name_with_space():
    game, npc = _with_agent(name="Maya Chen")
    _seed_beliefs(npc)
    client = _client(game)
    payload = client.get("/agents/Maya%20Chen/knowledge").json()
    assert payload["persona"] == "Maya Chen"
    assert client.get("/agents/maya%20chen/knowledge").status_code == 404


def test_demo_game_serves_a_belief_set():
    # Protects the README curl walkthrough: the stock demo gardener ships with a
    # prior (learned_turn null) and a learned belief (learned_turn set).
    payload = (
        TestClient(create_app(_demo_game())).get("/agents/gardener/knowledge").json()
    )
    assert payload["count"] >= 2
    learned = [b["learned_turn"] for b in payload["beliefs"]]
    assert None in learned  # a prior known up front
    assert any(t is not None for t in learned)  # and one learned mid-run


# --- GET /agents/{name}/retrieval (#346) -----------------------------------


def test_retrieval_returns_scored_memories():
    game, npc = _with_agent()
    payload = (
        _client(game).get("/agents/gardener/retrieval", params={"q": "sun"}).json()
    )
    assert set(payload) == {"persona", "turn", "query", "count", "memories"}
    assert payload["persona"] == "gardener"
    assert payload["turn"] == 0
    assert payload["query"] == "sun"
    assert payload["count"] == len(payload["memories"]) >= 1
    for entry in payload["memories"]:
        assert set(entry) == {"kind", "importance", "text", "created_turn"}


def test_retrieval_matches_the_underlying_retriever():
    # The endpoint is a thin wrapper over AgentMemory.retrieve(touch=False) piped
    # through memories_for_frame, so a probe and a direct read-only retrieval
    # return the same records in the same order.
    game, npc = _with_agent()
    expected = memories_for_frame(
        npc.agent.memory.retrieve(query="forest", turn=game.turn, touch=False)
    )
    payload = (
        _client(game).get("/agents/gardener/retrieval", params={"q": "forest"}).json()
    )
    assert payload["memories"] == expected


def test_retrieval_ranks_the_relevant_memory_first():
    # With recency and importance held equal, keyword relevance is the only
    # differentiator -- so the memory that shares a word with the cue leads.
    game, npc = _with_agent()
    npc.agent.memory.records.clear()
    npc.agent.memory.add_observation("I lit the lantern.", turn=0, importance=5.0)
    npc.agent.memory.add_observation("I crossed the river.", turn=0, importance=5.0)
    payload = (
        _client(game).get("/agents/gardener/retrieval", params={"q": "lantern"}).json()
    )
    assert payload["memories"][0]["text"] == "I lit the lantern."


def test_retrieval_is_read_only_and_does_not_bump_recency():
    # The acceptance test for #346: probing runs touch=False, so it never bumps
    # last_accessed_turn -- inspecting what would surface can't perturb the very
    # recency it measures. The GET also never advances the game.
    game, npc = _with_agent()
    game.turn = 5  # pretend the sim has advanced past the seeded memories
    before = [r.last_accessed_turn for r in npc.agent.memory.records]
    payload = (
        _client(game).get("/agents/gardener/retrieval", params={"q": "sun"}).json()
    )
    after = [r.last_accessed_turn for r in npc.agent.memory.records]
    assert after == before  # touch=False: the probe left recency untouched
    assert payload["turn"] == 5
    assert game.turn == 5  # a GET never advanced the game
    # Contrast: the decision-time (touch=True) path WOULD bump recency to now,
    # which is exactly what the probe deliberately avoids.
    npc.agent.memory.retrieve(query="sun", turn=5, touch=True)
    assert [r.last_accessed_turn for r in npc.agent.memory.records] != before


def test_retrieval_limit_caps_the_result():
    game, npc = _with_agent()
    for i in range(4):
        npc.agent.memory.add_observation(f"note {i}", turn=0, importance=1.0)
    payload = (
        _client(game)
        .get("/agents/gardener/retrieval", params={"q": "note", "limit": 1})
        .json()
    )
    assert payload["count"] == 1


def test_retrieval_requires_a_query():
    # The cue is the whole point of a probe: no ?q= is a bad request, not an
    # empty ranking.
    game, _npc = _with_agent()
    assert _client(game).get("/agents/gardener/retrieval").status_code == 422
    assert (
        _client(game).get("/agents/gardener/retrieval", params={"q": ""}).status_code
        == 422
    )


def test_retrieval_empty_stream_is_200_not_error():
    # An agent bound but with no memories yet is an empty probe, not a 500.
    game, npc = _with_agent()
    npc.agent.memory.records.clear()
    payload = (
        _client(game).get("/agents/gardener/retrieval", params={"q": "anything"}).json()
    )
    assert payload["count"] == 0
    assert payload["memories"] == []


def test_retrieval_unknown_character_is_404():
    game, _npc = _with_agent()
    resp = _client(game).get("/agents/nobody/retrieval", params={"q": "x"})
    assert resp.status_code == 404
    assert "unknown" in resp.json()["detail"]


def test_retrieval_character_without_agent_is_404():
    # Like the memory/knowledge siblings, the /agents/ family reads a *mind*: the
    # player has no agent bound, so there is no retriever to probe.
    game, _npc = _with_agent()
    resp = _client(game).get("/agents/player/retrieval", params={"q": "x"})
    assert resp.status_code == 404
    assert "no agent" in resp.json()["detail"]


def test_retrieval_requires_auth_when_token_configured():
    game, _npc = _with_agent()
    client = _client(game, auth_token="s3cret")
    assert (
        client.get("/agents/gardener/retrieval", params={"q": "sun"}).status_code == 401
    )
    ok = client.get(
        "/agents/gardener/retrieval",
        params={"q": "sun"},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert ok.status_code == 200


# --- GET /agents/{name}/plan (#347) ----------------------------------------


def _seed_plan(npc):
    """Attach a DailyPlan the way the sim builder does (``agent.plan``).

    A small but complete plan -- a day block, an hour block, and two stops --
    so the endpoint has all three altitude levels to serialize. Returns the
    plan for chaining."""
    plan = DailyPlan(
        day=[DayBlock(label="morning", summary="tend the garden")],
        hours=[HourBlock(start_hour=8, summary="water the beds, then gather wood")],
        stops=[
            Stop(place="Field", activity="water the tall grass", emoji="💧", steps=3),
            Stop(place="Forest", activity="gather kindling", emoji="🪵", steps=2),
        ],
    )
    npc.agent.plan = plan
    return plan


def test_plan_endpoint_returns_the_daily_plan():
    game, npc = _with_agent()
    _seed_plan(npc)
    payload = _client(game).get("/agents/gardener/plan").json()
    assert set(payload) == {"persona", "turn", "revision", "plan"}
    assert payload["persona"] == "gardener"
    assert payload["turn"] == 0
    assert payload["revision"] == 0  # freshly generated, not yet revised
    assert set(payload["plan"]) == {"day", "hours", "stops", "revision"}
    assert [s["place"] for s in payload["plan"]["stops"]] == ["Field", "Forest"]


def test_plan_matches_to_primitive():
    # The endpoint emits DailyPlan.to_primitive() verbatim -- the same shape the
    # bake writes to personas/<name>/daily_plan.json -- so a live read and the
    # baked artifact can never drift apart.
    game, npc = _with_agent()
    plan = _seed_plan(npc)
    payload = _client(game).get("/agents/gardener/plan").json()
    assert payload["plan"] == plan.to_primitive()
    assert payload["revision"] == plan.revision


def test_plan_reflects_a_mid_run_revision():
    # The acceptance test for #347: after a plan is revised mid-run, revision
    # increments and the new tail is visible; the executed head is preserved.
    game, npc = _with_agent()
    _seed_plan(npc)
    client = _client(game)
    before = client.get("/agents/gardener/plan").json()
    assert before["revision"] == 0
    # replace_tail is the sanctioned mid-day revision (what maybe_revise_plan
    # commits): keep stop 0, rewrite the rest, bump revision.
    npc.agent.plan = replace_tail(
        npc.agent.plan,
        after=0,
        new_stops=[Stop(place="Field", activity="rake the leaves", steps=4)],
    )
    after = client.get("/agents/gardener/plan").json()
    assert after["revision"] == 1
    stops = after["plan"]["stops"]
    assert stops[0]["place"] == "Field"  # the executed head is preserved verbatim
    assert stops[0]["activity"] == "water the tall grass"
    assert stops[-1]["activity"] == "rake the leaves"  # the new tail appears


def test_plan_absent_when_agent_never_planned():
    # A bound agent whose brain never planned (a bare ScriptedAgent, agent.plan
    # unset) is a 200 with plan/revision null -- absent, not an error, since a
    # plan may still be generated later (like "no memories yet" is a 200 []).
    game, _npc = _with_agent()
    payload = _client(game).get("/agents/gardener/plan").json()
    assert payload == {
        "persona": "gardener",
        "turn": 0,
        "revision": None,
        "plan": None,
    }


def test_plan_unknown_character_is_404():
    game, _npc = _with_agent()
    resp = _client(game).get("/agents/nobody/plan")
    assert resp.status_code == 404
    assert "unknown" in resp.json()["detail"]


def test_plan_character_without_agent_is_404():
    # Like the memory/knowledge siblings, the /agents/ family reads a *mind*: the
    # player has no agent bound, so there is no plan to read.
    game, _npc = _with_agent()
    resp = _client(game).get("/agents/player/plan")
    assert resp.status_code == 404
    assert "no agent" in resp.json()["detail"]


def test_plan_get_is_read_only():
    game, npc = _with_agent()
    _seed_plan(npc)
    client = _client(game)
    a = client.get("/agents/gardener/plan").json()
    b = client.get("/agents/gardener/plan").json()
    assert a == b  # deterministic + unchanged
    assert game.turn == 0  # a GET never advanced the game


def test_plan_requires_auth_when_token_configured():
    game, npc = _with_agent()
    _seed_plan(npc)
    client = _client(game, auth_token="s3cret")
    assert client.get("/agents/gardener/plan").status_code == 401
    ok = client.get("/agents/gardener/plan", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_plan_persona_name_with_space():
    game, npc = _with_agent(name="Maya Chen")
    _seed_plan(npc)
    client = _client(game)
    assert client.get("/agents/Maya%20Chen/plan").json()["persona"] == "Maya Chen"
    assert client.get("/agents/maya%20chen/plan").status_code == 404


# --- #186 security posture ------------------------------------------------


def test_oversized_body_is_413():
    huge = {"command": "x" * (70 * 1024)}  # over the 64 KiB cap
    assert _client().post("/command", json=huge).status_code == 413


def test_auth_required_when_token_configured():
    client = _client(auth_token="s3cret")
    assert client.get("/health").status_code == 401  # no header
    assert (
        client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    ok = client.get("/health", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_no_auth_required_by_default():
    assert _client().get("/health").status_code == 200  # loopback dev default


def test_run_refuses_non_loopback_bind_without_token(monkeypatch):
    monkeypatch.delenv("SIM_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="non-loopback"):
        run(_tiny(), host="0.0.0.0")  # would expose an unauthenticated API


# --- the pure helper ------------------------------------------------------


def test_run_command_advances_and_restores_renderer():
    game = _tiny()
    original = game.parser.renderer
    result = run_command(game, "go north")
    assert game.parser.renderer is original
    assert result["game_over"] is False
    assert any(e["channel"] == "narration" for e in result["events"])


# --- the live surface: loop + feed + run control (#349/#262) --------------
#
# These tests inject a fake SimStepper and run the loop for real (10 ms
# ticks) inside ``with TestClient(app):`` -- the loop rides the lifespan, so a
# bare TestClient never starts it. Every wait polls with a deadline; there are
# no bare sleeps standing in for synchronization.


class _FakeStepper:
    """A deterministic SimStepper: agent "a" walks east one tile per tick."""

    def __init__(self, finish_after=None, ledger=None):
        self._step = 0
        self.finish_after = finish_after
        self.reset_calls = 0
        self.ledger = ledger

    @property
    def step(self):
        return self._step

    def meta(self):
        return {
            "tile_px": 8,
            "width": 4,
            "height": 4,
            "personas": [{"name": "a", "emoji": "@"}],
        }

    def tick(self):
        if self.finish_after is not None and self._step >= self.finish_after:
            return None
        frame = {"a": {"x": self._step, "y": 0, "act": "walking @ demo", "e": "@"}}
        self._step += 1
        return frame

    def reset(self):
        self._step = 0
        self.reset_calls += 1


def _live_client(stepper=None, game=None, **kwargs):
    """A TestClient over a live app. Use as ``with _live_client() as c:``."""
    kwargs.setdefault("tick_seconds", 0.01)
    return TestClient(
        create_app(game or _tiny(), stepper=stepper or _FakeStepper(), **kwargs)
    )


def _wait_for_events(client, predicate, timeout=5.0, headers=None):
    """Poll ``GET /events?since=0`` until *predicate*(events) holds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = client.get("/events?since=0", headers=headers).json()["events"]
        if predicate(events):
            return events
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the change feed")


def _frame_count(events):
    return sum(e["kind"] == "frame" for e in events)


def test_live_disabled_by_default():
    c = _client()  # no stepper: the command-driven API, byte-identical
    assert c.get("/live").json() == {
        "enabled": False,
        "running": False,
        "paused": False,
        "step": None,
        "cursor": 0,
        "tick_seconds": None,
        "meta": None,
    }
    assert c.get("/events").json() == {
        "latest_cursor": 0,
        "oldest_cursor": None,
        "events": [],
    }
    for path in ("/pause", "/resume", "/reset"):
        assert c.post(path).status_code == 409  # no loop to control
    assert c.get("/usage").json()["available"] is False
    assert c.get("/health").json()["ok"] is True
    assert c.post("/command", json={"command": "go north"}).status_code == 200


def test_shutdown_hidden_unless_opted_in():
    # The generic API never exposes remote shutdown: 404, exactly like a route
    # that does not exist -- with or without a live loop.
    assert _client().post("/shutdown").status_code == 404
    with _live_client() as c:
        assert c.post("/shutdown").status_code == 404


def test_shutdown_pauses_the_loop_and_fires_the_hook():
    # serve_penn opts in (allow_shutdown=True): the viewer POSTs /shutdown on
    # window close, so the sim -- and its spend -- stops with nobody watching.
    # Tests inject on_shutdown; the default SIGINTs the server process.
    fired = threading.Event()
    with _live_client(allow_shutdown=True, on_shutdown=fired.set) as c:
        _wait_for_events(c, lambda evs: _frame_count(evs) >= 1)  # day is running
        assert c.post("/shutdown").json() == {"ok": True}
        data = c.get("/live").json()
        assert data["paused"] is True  # spend stopped before the process exits
        assert fired.wait(timeout=5.0)


def test_start_paused_holds_frames_until_resume():
    # create_app(start_paused=True) -- serve_penn's --brain llm default: the
    # loop is alive and serving, but the first tick (with a real brain, the
    # first PAID model call) waits for POST /resume (the viewer's Start).
    with _live_client(start_paused=True) as c:
        _wait_for_events(c, lambda evs: any(e["kind"] == "status" for e in evs))
        data = c.get("/live").json()
        assert data["running"] is True
        assert data["paused"] is True
        assert data["step"] == 0
        assert _frame_count(c.get("/events?since=0").json()["events"]) == 0
        assert c.post("/resume").status_code == 200
        _wait_for_events(c, lambda evs: _frame_count(evs) >= 2)  # the day runs


def test_live_handshake_reports_meta_and_state():
    with _live_client() as c:
        _wait_for_events(c, lambda evs: len(evs) >= 1)  # loop task has started
        data = c.get("/live").json()
        assert data["enabled"] is True
        assert data["running"] is True
        assert data["paused"] is False
        assert data["tick_seconds"] == 0.01
        assert data["meta"]["personas"] == [{"name": "a", "emoji": "@"}]


def test_loop_appends_frames_with_contiguous_cursors():
    with _live_client() as c:
        events = _wait_for_events(c, lambda evs: _frame_count(evs) >= 3)
        cursors = [e["cursor"] for e in events]
        assert cursors == list(range(1, len(cursors) + 1))  # 1-based, no holes
        assert events[0] == {
            "cursor": 1,
            "kind": "status",
            "reason": "started",
            "running": True,
            "paused": False,
            "step": 0,
        }
        frames = [e for e in events if e["kind"] == "frame"]
        assert [f["step"] for f in frames[:3]] == [0, 1, 2]
        assert frames[0]["agents"]["a"]["x"] == 0


def test_events_since_returns_only_newer_and_empty_tail_promptly():
    with _live_client() as c:
        events = _wait_for_events(c, lambda evs: len(evs) >= 3)
        mid = events[1]["cursor"]
        tail = c.get(f"/events?since={mid}").json()
        assert tail["events"] and all(e["cursor"] > mid for e in tail["events"])
        latest = c.get("/events").json()["latest_cursor"]
        far = c.get(f"/events?since={latest + 10_000}").json()
        assert far["events"] == []  # an empty tail answers at once


def test_ws_receives_pushed_frames():
    with _live_client() as c:
        with c.websocket_connect("/ws?since=0") as ws:
            first = ws.receive_json()
            assert first["kind"] == "status" and first["reason"] == "started"
            record = ws.receive_json()
            while record["kind"] != "frame":  # skip any interleaved statuses
                record = ws.receive_json()
            assert record["agents"]["a"]["act"] == "walking @ demo"


def test_ws_reconnect_backfill_no_gap_no_dupes():
    """The #262 acceptance: kill the socket, catch up over HTTP, re-attach --
    the concatenated cursor sequence has no gap and no duplicate."""
    with _live_client() as c:
        seen = []
        with c.websocket_connect("/ws?since=0") as ws:
            for _ in range(3):
                seen.append(ws.receive_json())
        last = seen[-1]["cursor"]
        # ...socket gone; the loop keeps stepping...
        _wait_for_events(c, lambda evs: evs and evs[-1]["cursor"] > last + 1)
        seen.extend(c.get(f"/events?since={last}").json()["events"])  # catch up
        last = seen[-1]["cursor"]
        with c.websocket_connect(f"/ws?since={last}") as ws:  # re-attach
            seen.append(ws.receive_json())
        cursors = [r["cursor"] for r in seen]
        assert cursors == list(range(cursors[0], cursors[0] + len(cursors)))


def test_ws_auth_header_or_query_token():
    with _live_client(auth_token="s3cret") as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws"):
                pass  # no token: refused before the handshake completes
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws?token=wrong"):
                pass
        headers = {"Authorization": "Bearer s3cret"}
        with c.websocket_connect("/ws?since=0", headers=headers) as ws:
            assert ws.receive_json()["cursor"] == 1  # Godot's door: the header
        with c.websocket_connect("/ws?since=0&token=s3cret") as ws:
            assert ws.receive_json()["cursor"] == 1  # the browser's door


def test_pause_stops_frames_resume_restarts():
    with _live_client() as c:
        _wait_for_events(c, lambda evs: _frame_count(evs) >= 1)
        state = c.post("/pause").json()
        assert state["paused"] is True and state["running"] is True
        time.sleep(0.05)  # let any tick already in flight land
        settled = c.get("/events").json()["latest_cursor"]
        time.sleep(0.05)
        assert c.get("/events").json()["latest_cursor"] == settled  # silence
        assert c.post("/resume").json()["paused"] is False
        _wait_for_events(
            c,
            lambda evs: any(
                e["kind"] == "frame" and e["cursor"] > settled for e in evs
            ),
        )


def test_reset_restarts_steps_but_not_cursors():
    stepper = _FakeStepper()
    with _live_client(stepper=stepper) as c:
        _wait_for_events(c, lambda evs: _frame_count(evs) >= 2)
        c.post("/pause")  # quiesce so the reset state is deterministic
        state = c.post("/reset").json()
        assert stepper.reset_calls == 1
        assert state["step"] == 0
        cursor_at_reset = state["cursor"]
        assert cursor_at_reset >= 4  # started + 2 frames + paused came before
        c.post("/resume")
        events = _wait_for_events(
            c,
            lambda evs: any(
                e["kind"] == "frame" and e["cursor"] > cursor_at_reset for e in evs
            ),
        )
        restarted = [
            e for e in events if e["kind"] == "frame" and e["cursor"] > cursor_at_reset
        ]
        assert restarted[0]["step"] == 0  # steps rewound; cursors never do


def test_finished_stepper_pauses_the_loop():
    with _live_client(stepper=_FakeStepper(finish_after=2)) as c:
        events = _wait_for_events(
            c,
            lambda evs: any(
                e["kind"] == "status" and e["reason"] == "finished" for e in evs
            ),
        )
        assert _frame_count(events) == 2
        assert c.get("/live").json()["paused"] is True


def test_command_409_while_running_allowed_when_paused():
    with _live_client() as c:
        _wait_for_events(c, lambda evs: _frame_count(evs) >= 1)
        refused = c.post("/command", json={"command": "go north"})
        assert refused.status_code == 409
        assert "pause" in refused.json()["detail"]
        c.post("/pause")
        assert c.post("/command", json={"command": "go north"}).status_code == 200


def test_usage_zeroed_when_no_ledger():
    with _live_client() as c:
        usage = c.get("/usage").json()
        assert usage["available"] is False
        assert usage["over_budget"] is False
        assert usage["calls"] == 0 and usage["total_cost_usd"] == 0.0


def test_usage_reports_ledger_summary():
    ledger = UsageLedger(max_cost_usd=5.0)
    with _live_client(stepper=_FakeStepper(ledger=ledger)) as c:
        usage = c.get("/usage").json()
        assert usage["available"] is True
        assert usage["kind"] == "summary"
        assert usage["over_budget"] is False
        assert usage["max_cost_usd"] == 5.0
        assert usage["remaining_budget_usd"] == 5.0
        # Exactly the summary() keys the Godot run-monitor HUD (#264) renders.
        for key in (
            "calls",
            "total_cost_usd",
            "by_actor",
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            assert key in usage


def test_live_routes_require_auth_when_token_configured():
    with _live_client(auth_token="s3cret") as c:
        assert c.get("/live").status_code == 401
        assert c.get("/events").status_code == 401
        assert c.get("/usage").status_code == 401
        for path in ("/pause", "/resume", "/reset"):
            assert c.post(path).status_code == 401
        ok = {"Authorization": "Bearer s3cret"}
        assert c.get("/live", headers=ok).status_code == 200


def test_lifespan_shutdown_stops_loop():
    stepper = _FakeStepper()
    with _live_client(stepper=stepper) as c:
        _wait_for_events(c, lambda evs: _frame_count(evs) >= 1)
    ticked_to = stepper.step  # the client exited: lifespan cancelled the loop
    time.sleep(0.05)
    assert stepper.step == ticked_to


def test_demo_stepper_advances_world_and_memory():
    """The #349 acceptance shape, in miniature: with the loop's stepper and no
    key anywhere, the world advances on its own and an agent's memory grows."""
    game = _demo_game()
    stepper = _demo_stepper(game)
    gardener = game.characters["gardener"]
    before = len(memory_stream_for_persona(gardener.agent))
    first = stepper.tick()
    second = stepper.tick()
    assert first["player"] != second["player"]  # north, then back south
    assert game.turn > 0  # real commands ran through the engine
    assert len(memory_stream_for_persona(gardener.agent)) == before + 2
    assert stepper.drain_events()  # engine records captured for the feed


# --- POST /agents/{name}/say + POST /world/event: interventions (#369) ------


def test_say_delivers_a_chat_memory():
    # The acceptance path: an utterance to an agent lands in its memory as a
    # chat-kind record, visible via GET /agents/{name}/memory (#298).
    game, npc = _with_agent()
    client = _client(game)
    resp = client.post(
        "/agents/gardener/say", json={"text": "The market closes at noon."}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"persona", "turn", "reply", "cursor"}
    assert body["persona"] == "gardener"
    assert body["reply"] is None  # the mock brain doesn't talk back (#261 fills it)
    assert body["cursor"] >= 1
    mem = client.get("/agents/gardener/memory").json()
    chat = [m for m in mem["memories"] if m["kind"] == "chat"]
    assert len(chat) == 1
    assert chat[0]["text"] == 'someone said to me: "The market closes at noon."'


def test_say_uses_the_given_speaker():
    game, npc = _with_agent()
    _client(game).post(
        "/agents/gardener/say",
        json={"text": "Meet me at the fountain.", "speaker": "Alistair"},
    )
    texts = [r.text for r in npc.agent.memory.records if r.kind.value == "chat"]
    assert texts == ['Alistair said to me: "Meet me at the fountain."']


def test_say_pushes_onto_the_heard_buffer():
    # Mirrors the Say action: the line shows up in the character's heard buffer,
    # so it surfaces in the agent's next observation like any overheard speech.
    game, npc = _with_agent()
    _client(game).post("/agents/gardener/say", json={"text": "Hello there."})
    assert any("Hello there." in line for line in npc.heard)


def test_say_appears_in_the_change_feed():
    # The utterance is also published as an intervention record, so a viewer
    # following the feed sees the human speak.
    game, npc = _with_agent()
    client = _client(game)
    client.post(
        "/agents/gardener/say", json={"text": "Rain is coming.", "speaker": "Alistair"}
    )
    events = client.get("/events?since=0").json()["events"]
    says = [e for e in events if e.get("intervention") == "say"]
    assert len(says) == 1
    assert says[0]["kind"] == "intervention"
    assert says[0]["name"] == "gardener"
    assert says[0]["speaker"] == "Alistair"
    assert says[0]["text"] == "Rain is coming."


def test_say_unknown_character_is_404():
    game, _npc = _with_agent()
    resp = _client(game).post("/agents/nobody/say", json={"text": "hi"})
    assert resp.status_code == 404
    assert "unknown" in resp.json()["detail"]


def test_say_character_without_agent_is_404():
    game, _npc = _with_agent()
    resp = _client(game).post("/agents/player/say", json={"text": "hi"})
    assert resp.status_code == 404
    assert "no agent" in resp.json()["detail"]


def test_say_empty_text_is_422():
    game, _npc = _with_agent()
    assert (
        _client(game).post("/agents/gardener/say", json={"text": ""}).status_code == 422
    )
    assert _client(game).post("/agents/gardener/say", json={}).status_code == 422


def test_say_requires_auth_when_token_configured():
    game, _npc = _with_agent()
    client = _client(game, auth_token="s3cret")
    assert client.post("/agents/gardener/say", json={"text": "hi"}).status_code == 401
    ok = client.post(
        "/agents/gardener/say",
        json={"text": "hi"},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert ok.status_code == 200


def test_say_delivers_while_the_loop_is_running():
    # The #369 acceptance criterion, with the #349 loop live: the utterance lands
    # at the next tick boundary (under the shared lock) and shows up in memory.
    game, npc = _with_agent()
    with _live_client(game=game) as c:
        _wait_for_events(c, lambda evs: _frame_count(evs) >= 1)  # loop is stepping
        assert (
            c.post(
                "/agents/gardener/say", json={"text": "A stranger is asking for you."}
            ).status_code
            == 200
        )
        mem = c.get("/agents/gardener/memory").json()
        assert any(
            m["kind"] == "chat" and "stranger is asking" in m["text"]
            for m in mem["memories"]
        )


def test_world_event_appends_to_the_feed():
    game, npc = _with_agent()
    client = _client(game)
    resp = client.post(
        "/world/event", json={"text": "A storm rolls in.", "location": "Field"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"turn", "location", "perceived_by", "cursor"}
    assert body["location"] == "Field"
    assert body["perceived_by"] == ["gardener"]  # in range at Field
    events = client.get("/events?since=0").json()["events"]
    world = [e for e in events if e.get("intervention") == "world_event"]
    assert len(world) == 1
    assert world[0]["kind"] == "intervention"
    assert world[0]["text"] == "A storm rolls in."
    assert world[0]["location"] == "Field"


def test_world_event_is_perceived_by_a_colocated_agent():
    # The event enters game.events with the location as its origin, so the agent
    # folds it into memory at its next perceive() -- its next decision point.
    game, npc = _with_agent()
    _client(game).post(
        "/world/event", json={"text": "A bell tolls nearby.", "location": "Field"}
    )
    added = npc.agent.memory.perceive(game, npc)
    assert any("bell tolls nearby" in r.text.lower() for r in added)


def test_world_event_without_location_is_feed_only():
    # No location => a feed-only announcement: it lands in the feed but no agent
    # perceives it (there is no origin room to see).
    game, npc = _with_agent()
    client = _client(game)
    body = client.post("/world/event", json={"text": "The day begins."}).json()
    assert body["location"] is None
    assert body["perceived_by"] == []
    assert any(
        e.get("intervention") == "world_event"
        for e in client.get("/events?since=0").json()["events"]
    )
    assert npc.agent.memory.perceive(game, npc) == []  # nobody perceives it


def test_world_event_unknown_location_is_404():
    # A typo shouldn't silently vanish: a given-but-unknown location is a 404.
    game, _npc = _with_agent()
    resp = _client(game).post(
        "/world/event", json={"text": "x", "location": "Atlantis"}
    )
    assert resp.status_code == 404
    assert "unknown location" in resp.json()["detail"]


def test_world_event_empty_text_is_422():
    game, _npc = _with_agent()
    assert _client(game).post("/world/event", json={"text": ""}).status_code == 422
    assert _client(game).post("/world/event", json={}).status_code == 422


def test_world_event_requires_auth_when_token_configured():
    game, _npc = _with_agent()
    client = _client(game, auth_token="s3cret")
    assert client.post("/world/event", json={"text": "x"}).status_code == 401
    ok = client.post(
        "/world/event", json={"text": "x"}, headers={"Authorization": "Bearer s3cret"}
    )
    assert ok.status_code == 200


def test_world_event_appears_in_the_feed_while_the_loop_is_running():
    game, npc = _with_agent()
    with _live_client(game=game) as c:
        _wait_for_events(c, lambda evs: _frame_count(evs) >= 1)  # loop is stepping
        assert (
            c.post(
                "/world/event", json={"text": "Thunder cracks.", "location": "Field"}
            ).status_code
            == 200
        )
        events = _wait_for_events(
            c, lambda evs: any(e.get("intervention") == "world_event" for e in evs)
        )
        world = [e for e in events if e.get("intervention") == "world_event"]
        assert world[-1]["text"] == "Thunder cracks."
