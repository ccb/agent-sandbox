"""Auto-generated walkthrough for 'Jungle Adventure'.

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
    'unbuckle seatbelt',
    'get backpack',
    'wear backpack',
    'get lighter',
    'get compass',
    'out',
    'search wreckage',
    'get rifle',
    'jungle',
    'south',
    'enter warriors hut',
    'give rifle to warriors',
    'get spear',
    'exit warriors hut',
    'enter womens hut',
    'get skirt',
    'exit womens hut',
    'west',
    'search nest',
    'get egg',
    'west',
    'cave',
    'get fang',
    'get bones',
    'out',
    'east',
    'east',
    'enter witch doctors hut',
    'give fang to witch doctor',
    'get necklace',
    'wear necklace',
    'exit witch doctors hut',
    'cook egg',
    'north',
    'east',
    'east',
    'north',
    'use lighter on bush',
    'south',
    'south',
    'put bones on altar',
    'south',
    'give egg to monkey',
    'get skull',
    'north',
    'north',
    'north',
    'wait for helicopter',
    'enter helicopter',
]
EXPECTS_WIN = True
MODULE_FILENAME = 'ja.py'
MODULE_STEM = 'ja'


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
        assert game.is_won() is True, (
            f"walkthrough did not win; last command results: {results[-5:]}"
        )
    else:
        assert not game.is_won(), "walkthrough unexpectedly won"


if __name__ == "__main__":
    test_walkthrough_wins()
    print("walkthrough OK")
