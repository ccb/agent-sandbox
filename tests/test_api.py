"""The headless FastAPI backend that drives the engine (issue #179, #186).

Exercises the full app in-process via FastAPI's ``TestClient`` (no socket), plus
the pure ``run_command`` helper. Offline; requires the ``server`` extra (fastapi,
uvicorn) and ``httpx`` (TestClient) -- skipped cleanly if they're absent.
"""

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
