"""The headless FastAPI backend that drives the engine (issue #179, #186).

Exercises the full app in-process via FastAPI's ``TestClient`` (no socket), plus
the pure ``run_command`` helper. Offline; requires the ``server`` extra (fastapi,
uvicorn) and ``httpx`` (TestClient) -- skipped cleanly if they're absent.
"""

import urllib.parse
from collections import Counter

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import _demo_game, create_app, run, run_command  # noqa: E402
from backend.smallville_agents import memory_stream_for_persona  # noqa: E402
from text_adventure_games import games, things  # noqa: E402
from text_adventure_games.npc import ScriptedAgent  # noqa: E402


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
