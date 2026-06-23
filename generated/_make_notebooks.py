"""One-off generator: build a play-through Jupyter notebook for each ported game.

Every game module exposes ``build_game()`` and a walkthrough list, so every
notebook is the same shape: load the module by file path, describe the opening
room, play the winning walkthrough turn-by-turn, report the final score, then
leave a ``do("...")`` helper for free play. Run from anywhere:

    uv run python generated/_make_notebooks.py

Covers the hand-ported Parsely games under ``generated/`` and the Action Castle
sequels (AC2–AC4) under ``text_adventure_games/adventures/``. The AC1 notebook
in ``notebooks/hw1_solution/`` is hand-written and is intentionally left alone.
"""

from __future__ import annotations

import ast
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "generated"
ADVENTURES = ROOT / "text_adventure_games" / "adventures"


def title_of(slug: str) -> str:
    """blackboard_jungle -> Blackboard Jungle."""
    return " ".join(w.capitalize() for w in slug.split("_"))


def docstring_blurb(module_path: Path, stop_markers: tuple[str, ...]) -> str:
    """The story summary from a module docstring: everything up to the first
    implementation-notes paragraph (matched by *stop_markers*), trimmed."""
    doc = ast.get_docstring(ast.parse(module_path.read_text())) or ""
    cut = len(doc)
    for marker in stop_markers:
        i = doc.find(marker)
        if i != -1:
            cut = min(cut, i)
    doc = doc[:cut]
    lines = doc.strip().splitlines()
    if lines and ("ported to the" in lines[0] or "on the text_adventure" in lines[0]):
        lines = lines[1:]
    return "\n".join(lines).strip()


# Each spec: (title, blurb, path-to-.py, output-.ipynb, WALKTHROUGH attr name).
def _specs() -> list[dict]:
    specs: list[dict] = []

    # Hand-ported Parsely games -- blurb from the docstring (cut before the
    # "Authored the way..." implementation notes).
    for slug in [
        "blackboard_jungle",
        "dangertown_beatdown",
        "flaming_goat",
        "jungle_adventure",
        "pumpkin_town",
        "six_gun_showdown",
        "space_station",
        "spooky_manor",
        "z_ward",
    ]:
        py = GENERATED / slug / f"{slug}.py"
        specs.append(
            {
                "title": title_of(slug),
                "blurb": docstring_blurb(py, ("Authored the way",)),
                "py": py,
                "out": GENERATED / slug / f"{slug}.ipynb",
                "walkthrough": "WALKTHROUGH",
            }
        )

    # Action Castle sequels. Their docstrings are implementation-heavy, so we
    # give them a short hand-written blurb. AC2's primary solve is the champion
    # ending; AC3 has a single WALKTHROUGH.
    specs.append(
        {
            "title": "Action Castle II — Return to Action Castle",
            "blurb": (
                "The sequel to Action Castle, ported from Parsely. You return to "
                "the castle and work toward the *champion* ending — besting the "
                "dragon (by wits or by steel), answering its riddle, and winning "
                "the king's favor. This notebook plays the champion walkthrough; "
                "the module also ships a `WALKTHROUGH_MARRIAGE` for the alternate "
                "ending."
            ),
            "py": ADVENTURES / "action_castle_2.py",
            "out": ADVENTURES / "action_castle_2.ipynb",
            "walkthrough": "WALKTHROUGH_CHAMPION",
        }
    )
    specs.append(
        {
            "title": "Action Castle III — Beneath Action Castle",
            "blurb": (
                "The third Action Castle, ported from Parsely — a party-based "
                "dungeon crawl. You recruit four companions (an elf, a dwarf, a "
                "cleric, and a wizard), each unlocking an ability-verb, and clear "
                "ability-gated obstacles down to a Chaos demon. The game ends when "
                "you head north for home; your progress picks one of several "
                "epilogues. This walkthrough scores a perfect 100/100."
            ),
            "py": ADVENTURES / "action_castle_3.py",
            "out": ADVENTURES / "action_castle_3.ipynb",
            "walkthrough": "WALKTHROUGH",
        }
    )
    specs.append(
        {
            "title": "Action Castle IV — Escape from Action Castle",
            "blurb": (
                "The fourth Action Castle, ported from Parsely — a road-trip. The "
                "Princess escapes her tower (cut hair → braid a rope → climb out "
                "the window) and rides off through the woods, a ranch, and a biker "
                "bar. There are two winning endings: settle as a rancher (+40) or "
                "ride off down the highway (+50). This walkthrough takes the "
                "highway for a perfect 100/100."
            ),
            "py": ADVENTURES / "action_castle_4.py",
            "out": ADVENTURES / "action_castle_4.ipynb",
            "walkthrough": "WALKTHROUGH_WIN",
        }
    )
    return specs


def build_notebook(spec: dict) -> nbf.NotebookNode:
    title = spec["title"]
    blurb = spec["blurb"]
    walk = spec["walkthrough"]
    py_rel = spec["py"].relative_to(ROOT).as_posix()
    py_name = spec["py"].name

    nb = nbf.v4.new_notebook()
    md = nbf.v4.new_markdown_cell
    code = nbf.v4.new_code_cell

    walk_note = ""
    if walk != "WALKTHROUGH":
        walk_note = f" (here, `mod.{walk}`)"

    nb.cells = [
        md(
            f"# {title}\n\n"
            f"{blurb}\n\n"
            "---\n\n"
            "This notebook drives the game through its winning walkthrough so "
            "you can read the story unfold turn-by-turn, then lets you take the "
            f"controls. The game logic lives in `{py_rel}`; here we just *play* it."
        ),
        md(
            "## 1. Load the game\n\n"
            "We add the repo root to the path (so `text_adventure_games` "
            "imports) and load the game module by file path — the same trick "
            "the test suite uses, so it works no matter where Jupyter was "
            "started from."
        ),
        code(
            "import sys\n"
            "import importlib.util\n"
            "from pathlib import Path\n"
            "\n"
            "# Walk up from the working directory to the repo root (the folder\n"
            "# that contains `text_adventure_games/`).\n"
            "root = Path.cwd().resolve()\n"
            'while not (root / "text_adventure_games").is_dir() and root != root.parent:\n'
            "    root = root.parent\n"
            "sys.path.insert(0, str(root))\n"
            "\n"
            f'game_file = root / "{py_rel}"\n'
            f'spec = importlib.util.spec_from_file_location("{spec["py"].stem}_nb", game_file)\n'
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            'print("loaded", game_file.name)'
        ),
        md(
            "## 2. Build the world and look around\n\n"
            "`build_game()` assembles every room, item, and character and wires "
            "up the custom actions. `look` describes where you start."
        ),
        code(
            "game = mod.build_game()\n"
            'game.parser.parse_command("look")\n'
            'print(f"\\nScore: {game.score}/{game.max_score}")'
        ),
        md(
            "## 3. Play the winning walkthrough\n\n"
            f"The walkthrough{walk_note} is the list of commands that solves the "
            "game. We build a fresh world and feed it the commands one at a time, "
            "printing each command (`>>>`) above the game's response so you can "
            "follow the solution."
        ),
        code(
            "game = mod.build_game()\n"
            'game.parser.parse_command("look")\n'
            "\n"
            f"for cmd in mod.{walk}:\n"
            '    print(f"\\n>>> {cmd}")\n'
            "    game.do_command(cmd)\n"
            "    if game.is_game_over():\n"
            "        break\n"
            "\n"
            'print("\\n" + "=" * 60)\n'
            'print(f"WON: {game.is_won()}   GAME OVER: {game.is_game_over()}")\n'
            'print(f"SCORE: {game.score}/{game.max_score}")'
        ),
        md(
            "## 4. Take the controls\n\n"
            'Start a fresh game and drive it yourself. Call `do("...")` with '
            "any command — `look`, `go north`, `get lamp`, `inventory`, "
            "`examine door`, and so on. Re-run the build cell to start over.\n\n"
            "(For a classic blocking prompt-loop instead, call "
            "`game.game_loop()`.)"
        ),
        code(
            "game = mod.build_game()\n"
            "\n"
            "def do(command):\n"
            '    """Run one command against the live game."""\n'
            "    game.do_command(command)\n"
            "\n"
            'do("look")'
        ),
        code('do("inventory")'),
    ]
    nb.metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python"},
    }
    return nb


def main() -> None:
    for spec in _specs():
        nb = build_notebook(spec)
        nbf.write(nb, spec["out"])
        print("wrote", spec["out"].relative_to(ROOT))


if __name__ == "__main__":
    main()
