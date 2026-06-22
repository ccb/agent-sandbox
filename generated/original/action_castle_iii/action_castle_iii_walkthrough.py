"""Auto-generated walkthrough for 'Action Castle III'.

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
    'west',
    'talk to elf',
    'invite elf',
    'west',
    'cast sleep',
    'take bow',
    'give bow to elf',
    'east',
    'south',
    'fill waterskin',
    'light lantern',
    'enter cavern',
    'drop backpack',
    'enter fissure',
    'examine bundle',
    'take baby',
    'exit fissure',
    'take backpack',
    'east',
    'take mushroom',
    'west',
    'exit cavern',
    'north',
    'west',
    'cook stew',
    'give stew to baby',
    'east',
    'south',
    'enter cavern',
    'east',
    'south',
    'shoot spider',
    'free dwarf',
    'invite dwarf',
    'west',
    'down',
    'show baby',
    'east',
    'give baby to queen',
    'west',
    'up',
    'east',
    'north',
    'west',
    'up',
    'north',
    'east',
    'east',
    'up',
    'invite wizard',
    'down',
    'down',
    'search',
    'take pendant',
    'east',
    'look up',
    'use wand on ooze',
    'pick lock',
    'take crown',
    'open spiked door',
    'east',
    'free cleric',
    'give waterskin to cleric',
    'invite cleric',
    'give pendant to cleric',
    'down',
    'west',
    'south',
    'turn undead',
    'take spell book',
    'north',
    'east',
    'up',
    'west',
    'give spell book to wizard',
    'east',
    'west',
    'south',
    'west',
    'north',
    'east',
    'east',
    'west',
    'north',
    'give crown to queen',
    'take javelin',
    'west',
    'up',
    'east',
    'north',
    'west',
    'up',
    'north',
    'east',
    'east',
    'down',
    'east',
    'open spiked door',
    'east',
    'down',
    'west',
    'south',
    'throw javelin at demon',
    'push cultist into pit',
    'east',
    'up',
    'east',
    'up',
    'west',
    'north',
    'west',
    'north',
]
EXPECTS_WIN = True
MODULE_FILENAME = 'action_castle_iii.py'
MODULE_STEM = 'action_castle_iii'


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
