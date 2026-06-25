"""Headless HTTP server that drives a :class:`~text_adventure_games.games.Game`
from an out-of-process front-end (issue #177).

A 2D / Godot renderer (or any client) polls state, receives the change feed, and
submits commands over HTTP -- without embedding Python or sharing memory. The
engine and any LLM stay server-side. Stdlib only (``http.server``), so it adds
no dependency and is distinct from the Flask webapp (which serves HTML).

    from text_adventure_games.server import serve
    serve(build_game(), port=8080)      # then: GET /world_state, POST /command

Endpoints, composing the world-state export (#90):

* ``GET /health``        -> ``{"ok": true, "turn": N}``
* ``GET /world_state``   -> the typed ``WorldState`` snapshot
* ``POST /command``      body ``{"command": "go north"}`` -> the resulting
  change-feed records, the new snapshot, and ``game_over``.

``GET`` requests are read-only; ``POST /command`` advances the game by exactly
one command. Routing lives in the pure :func:`handle_request` so it is testable
without binding a socket.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .reporting import JSONRenderer


def handle_request(game, method: str, path: str, body):
    """Route one request to ``(status_code, response_dict)``.

    Pure aside from ``POST /command``, which advances *game* by one command.
    *body* is the raw request bytes (or ``None`` for a GET)."""
    path = path.split("?", 1)[0]  # ignore any query string

    if method == "GET" and path == "/health":
        return 200, {"ok": True, "turn": game.turn}

    if method == "GET" and path == "/world_state":
        return 200, game.to_world_state().to_jsonable()

    if method == "POST" and path == "/command":
        try:
            data = json.loads(body or b"{}")
        except (json.JSONDecodeError, TypeError, ValueError):
            return 400, {"error": "invalid JSON body"}
        if not isinstance(data, dict):
            return 400, {"error": "body must be a JSON object"}
        command = str(data.get("command", "")).strip()
        if not command:
            return 400, {"error": "missing 'command'"}

        # Capture this command's output as a change feed, restoring whatever
        # renderer was in place so the server never disturbs the game's config.
        feed = JSONRenderer()
        previous = game.parser.renderer
        game.parser.set_renderer(feed)
        try:
            game.do_command(command)
        finally:
            game.parser.set_renderer(previous)
        return 200, {
            "events": feed.drain(),
            "world_state": game.to_world_state().to_jsonable(),
            "game_over": game.is_game_over(),
        }

    return 404, {"error": "not found"}


class _Handler(BaseHTTPRequestHandler):
    """Thin HTTP adapter: parse the request, delegate to :func:`handle_request`,
    write the JSON response. The :class:`Game` is read off ``self.server.game``."""

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        status, payload = handle_request(self.server.game, "GET", self.path, None)
        self._send(status, payload)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        status, payload = handle_request(self.server.game, "POST", self.path, body)
        self._send(status, payload)

    def log_message(self, *args) -> None:  # keep pytest / CI output quiet
        pass


def make_server(game, host: str = "127.0.0.1", port: int = 8080):
    """A configured (not-yet-serving) ``ThreadingHTTPServer`` bound to *game*.

    Use ``port=0`` for an ephemeral port (e.g. in tests); the chosen port is on
    ``server.server_address``. Call ``server.serve_forever()`` to run it."""
    server = ThreadingHTTPServer((host, port), _Handler)
    server.game = game
    return server


def serve(game, host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the HTTP server for *game* until interrupted (Ctrl-C)."""
    make_server(game, host, port).serve_forever()
