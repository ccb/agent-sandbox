"""Regression for issue #545: Thing.to_primitive() must serialize the commands
set in a stable order. Dumping via list(self.commands) orders by PYTHONHASHSEED,
so the same world serialized in two processes could differ byte-for-byte and
break save/load determinism. sorted() pins it (as `aliases` already does).
"""

import os
import subprocess
import sys

# Distinct strings whose set-iteration order is hash-seed-sensitive; add-order is
# intentionally not sorted so a buggy list(set) dump varies across seeds.
_SNIPPET = (
    "from text_adventure_games.things.base import Thing\n"
    "t = Thing('x', 'x')\n"
    "for c in ['zeta','alpha','mu','beta','omega','gamma','delta','kappa']:\n"
    "    t.add_command_hint(c)\n"
    "print(t.to_primitive()['commands'])\n"
)


def _commands_dump(hashseed):
    out = subprocess.run(
        [sys.executable, "-c", _SNIPPET],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": str(hashseed)},
        check=True,
    )
    return out.stdout.strip()


def test_commands_serialization_is_hashseed_stable():
    dumps = {_commands_dump(seed) for seed in (0, 1, 2)}
    assert len(dumps) == 1, f"commands order varies by PYTHONHASHSEED: {dumps}"
