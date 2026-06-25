"""Headless HTTP server that drives the engine (issue #177).

Unit-tests the pure ``handle_request`` routing, plus one real HTTP round-trip on
an ephemeral port. Stdlib only; fully offline.
"""

import json
import threading
import urllib.request

from text_adventure_games import games, things
from text_adventure_games.server import handle_request, make_server


def _tiny():
    field = things.Location("Field", "An open field.")
    forest = things.Location("Forest", "A wood.")
    field.add_connection("north", forest)
    player = things.Character("player", "you", "I explore.")
    return games.Game(field, player, characters=[])


def test_health_reports_liveness_and_turn():
    status, payload = handle_request(_tiny(), "GET", "/health", None)
    assert status == 200
    assert payload["ok"] is True
    assert payload["turn"] == 0


def test_world_state_endpoint_returns_the_snapshot():
    status, payload = handle_request(_tiny(), "GET", "/world_state", None)
    assert status == 200
    assert payload["schema_version"] == "1.0"
    assert payload["player"] == "player"
    assert {loc["name"] for loc in payload["locations"]} == {"Field", "Forest"}


def test_command_runs_and_returns_events_plus_new_state():
    game = _tiny()
    body = json.dumps({"command": "go north"}).encode()
    status, payload = handle_request(game, "POST", "/command", body)
    assert status == 200
    assert any(e["channel"] == "narration" for e in payload["events"])
    player = next(
        c for c in payload["world_state"]["characters"] if c["name"] == "player"
    )
    assert player["location"] == "Forest"  # the snapshot reflects the move
    assert payload["game_over"] is False


def test_get_world_state_is_read_only():
    game = _tiny()
    a = handle_request(game, "GET", "/world_state", None)[1]
    b = handle_request(game, "GET", "/world_state", None)[1]
    assert a == b  # deterministic + unchanged
    assert game.turn == 0  # a GET never advanced the game


def test_query_string_is_ignored_in_routing():
    status, _ = handle_request(_tiny(), "GET", "/world_state?cache=0", None)
    assert status == 200


def test_missing_command_is_400():
    status, payload = handle_request(_tiny(), "POST", "/command", b"{}")
    assert status == 400
    assert "error" in payload


def test_bad_json_body_is_400():
    status, _ = handle_request(_tiny(), "POST", "/command", b"not json")
    assert status == 400


def test_unknown_path_is_404():
    status, payload = handle_request(_tiny(), "GET", "/nope", None)
    assert status == 404
    assert "error" in payload


def test_real_http_round_trip():
    game = _tiny()
    server = make_server(game, "127.0.0.1", 0)  # port 0 -> ephemeral
    _, port = server.server_address
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/world_state", timeout=5
        ) as resp:
            data = json.loads(resp.read())
        assert data["schema_version"] == "1.0"

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/command",
            data=json.dumps({"command": "go north"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        assert any(e["channel"] == "narration" for e in result["events"])
    finally:
        server.shutdown()
        server.server_close()


def test_non_string_command_is_400_and_does_not_run():
    game = _tiny()
    body = json.dumps({"command": ["go", "north"]}).encode()
    status, payload = handle_request(game, "POST", "/command", body)
    assert status == 400
    assert "error" in payload
    assert game.turn == 0  # not coerced into a real command


def test_blocked_command_returns_200_with_a_blocked_event():
    # A command the ENGINE rejects (failed precondition) is still a successful
    # request: 200, with the rejection surfaced as a BLOCKED event. (A 4xx means
    # a bad *request*, not a rejected *command* -- the renderer must tell them
    # apart.)
    status, payload = handle_request(
        _tiny(), "POST", "/command", json.dumps({"command": "go south"}).encode()
    )
    assert status == 200
    assert any(e["channel"] == "blocked" for e in payload["events"])
    assert payload["game_over"] is False


def test_engine_exception_returns_500_and_restores_renderer():
    game = _tiny()
    original = game.parser.renderer

    def boom(_command):
        raise RuntimeError("kaboom")

    game.do_command = boom
    status, payload = handle_request(
        game, "POST", "/command", json.dumps({"command": "x"}).encode()
    )
    assert status == 500
    assert "error" in payload
    assert game.parser.renderer is original  # restored despite the engine error
