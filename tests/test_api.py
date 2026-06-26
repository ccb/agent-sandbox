"""The headless FastAPI backend that drives the engine (issue #179, #186).

Exercises the full app in-process via FastAPI's ``TestClient`` (no socket), plus
the pure ``run_command`` helper. Offline; requires the ``server`` extra (fastapi,
uvicorn) and ``httpx`` (TestClient) -- skipped cleanly if they're absent.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import create_app, run, run_command  # noqa: E402
from text_adventure_games import games, things  # noqa: E402


def _tiny():
    field = things.Location("Field", "An open field.")
    forest = things.Location("Forest", "A wood.")
    field.add_connection("north", forest)
    player = things.Character("player", "you", "I explore.")
    return games.Game(field, player, characters=[])


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
