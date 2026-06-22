"""Auto-generated walkthrough for 'Action Castle II'.

Plays a winning command sequence through the generated module and
asserts that ``game.is_won() == True``. This file is the
extractor's own self-test -- if it fails, the LLM spec drifted from
the source rules.

Run as a script:
    uv run python <this file>
or via pytest:
    uv run pytest <this file>
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

WALKTHROUGH = [
    "get slippers",
    "out",
    "drop penny in well",
    "east",
    "south",
    "board boat",
    "get blanket",
    "north",
    "west",
    "west",
    "give blanket to rosemary",
    "east",
    "east",
    "north",
    "get axe",
    "south",
    "west",
    "south",
    "give axe to smith",
    "north",
    "east",
    "south",
    "south",
    "give slippers to hermit",
    "north",
    "north",
    "north",
    "east",
    "enter moat",
    "move stone",
    "enter tunnel",
    "south",
    "wake dragon",
    "choose wits",
    "answer a wise man",
    "choose sword",
    "get sword",
    "north",
    "east",
    "up",
    "up",
    "up",
    "give sword to king",
    "accept",
]
EXPECTS_WIN = True
MODULE_FILENAME = "action_castle_ii.py"
MODULE_STEM = "action_castle_ii"


def _load_game_module():
    here = Path(__file__).resolve().parent
    path = here / MODULE_FILENAME
    spec = importlib.util.spec_from_file_location(MODULE_STEM, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_walkthrough():
    """Play the sequence and return (game, per-command results)."""
    mod = _load_game_module()
    game = mod.build_game()
    results = []
    for cmd in WALKTHROUGH:
        ok = game.do_command(cmd)
        results.append((cmd, ok))
        if game.is_game_over():
            break
    return game, results


def test_walkthrough_wins():
    game, results = run_walkthrough()
    if EXPECTS_WIN:
        assert (
            game.is_won() is True
        ), f"walkthrough did not win; last command results: {results[-5:]}"
    else:
        assert not game.is_won(), "walkthrough unexpectedly won"


if __name__ == "__main__":
    test_walkthrough_wins()
    print("walkthrough OK")
