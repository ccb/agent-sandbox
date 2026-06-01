import os
import uuid

from flask import Flask, render_template, request, redirect, session, url_for
from text_adventure_games.webapp.web_parser import WebParser
from homeworks.hw1_solution import action_castle

app = Flask(__name__)
app.secret_key = "action-castle-secret-key"

# Per-session game state: {session_id: {"game": Game, "messages": list, "command_history": list}}
game_sessions = {}


def get_llm_client():
    """Create an LLM client from environment variables, or return None."""
    provider = os.environ.get("LLM_PROVIDER")
    if not provider:
        return None
    try:
        from text_adventure_games.llm_client import LlmConfig, create_llm_client

        config = LlmConfig(
            provider=provider,
            api_key=os.environ.get("LLM_API_KEY"),
            model=os.environ.get("LLM_MODEL"),
            base_url=os.environ.get("LLM_BASE_URL"),
            verbose=os.environ.get("LLM_VERBOSE", "").lower() in ("1", "true"),
        )
        return create_llm_client(config)
    except (ImportError, ValueError) as e:
        print(f"Warning: Could not create LLM client: {e}")
        return None


def new_game():
    llm = get_llm_client()
    game = action_castle.build_game(llm_client=llm)
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
    app.run(port=8080)
