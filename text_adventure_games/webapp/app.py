import os
import uuid

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from text_adventure_games.webapp.web_parser import WebParser
from text_adventure_games.adventures import action_castle

app = Flask(__name__)
# Read the session secret from the environment so a real deployment never ships
# a hardcoded key. The fallback keeps local dev frictionless but is unsafe for
# anything public -- set FLASK_SECRET_KEY before exposing this app.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-insecure-key")

# Per-session game state: {session_id: {"game": Game, "messages": list, "command_history": list}}
game_sessions = {}


def get_llm_client():
    """Create an LLM client from environment variables, or return None."""
    from text_adventure_games.llm_client import client_from_env

    return client_from_env()


def get_embedding_client():
    """Create an embedding client from environment variables, or return None.

    ``EMBEDDING_PROVIDER=local`` (or ``=mock``) turns on semantic memory
    relevance; unset keeps the deterministic keyword default (issue #76)."""
    from text_adventure_games.embedding_client import embedding_client_from_env

    return embedding_client_from_env()


def new_game():
    llm = get_llm_client()
    game = action_castle.build_game(
        llm_client=llm, embedding_client=get_embedding_client()
    )
    if llm:
        from text_adventure_games.llm_parser import WebLlmParser

        narration_style = os.environ.get("LLM_NARRATION_STYLE")
        game.set_parser(WebLlmParser(game, llm, narration_style=narration_style))
    else:
        game.set_parser(WebParser(game))
    game.parser.parse_command("look")
    return game


def get_or_create_session():
    sid = session.get("sid")
    if sid is None or sid not in game_sessions:
        sid = str(uuid.uuid4())
        session["sid"] = sid
        game = new_game()
        game_sessions[sid] = {
            "game": game,
            "messages": game.parser.get_messages(),
            "command_history": [],
        }
    return game_sessions[sid]


@app.route("/", methods=["GET", "POST"])
def index():
    sess = get_or_create_session()
    game = sess["game"]
    messages = sess["messages"]
    command_history = sess["command_history"]

    if request.method == "POST":
        command = request.form.get("command", "")
        if command:
            command_history.append(command)
            game.do_command(command)
            messages.append({"type": "command", "text": f"> {command}"})
            messages.extend(game.parser.get_messages())

    game_over_description = None
    if game.is_game_over():
        game_over_description = game.game_over_description or "Game over."

    return render_template(
        "index.html",
        messages=messages,
        game_over=game.is_game_over(),
        game_over_description=game_over_description,
        command_history=command_history,
    )


@app.route("/world_state")
def world_state():
    """Serve the current world as a typed JSON snapshot (issue #90), so an
    out-of-process renderer (e.g. Godot) can poll the full state over HTTP -- the
    #9/#10 bridge endpoint. The per-message change feed is ``JSONRenderer``."""
    game = get_or_create_session()["game"]
    return jsonify(game.to_world_state().to_jsonable())


@app.route("/reset")
def reset():
    sid = session.get("sid")
    if sid and sid in game_sessions:
        game = new_game()
        game_sessions[sid] = {
            "game": game,
            "messages": game.parser.get_messages(),
            "command_history": [],
        }
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Host/port come from the environment so you can change them without editing
    # the source (e.g. PORT=5000, or HOST=0.0.0.0 to accept remote connections).
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    app.run(host=host, port=port)
