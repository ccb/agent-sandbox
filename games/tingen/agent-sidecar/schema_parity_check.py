#!/usr/bin/env python3
"""
Cross-language schema-parity helper for the Godot test harness.
================================================================
Imports the REAL `sidecar` module (not a reimplementation) so the parity test
exercises the actual `load_schema()` / `validate_action()` the running sidecar
uses. Reimplementing validation here would just create a second thing to drift —
the whole point is to compare the engine against the sidecar's genuine code.

Usage (invoked by tingen/tests/run_tests.gd):
    python3 agent-sidecar/schema_parity_check.py <fixtures.json>

`<fixtures.json>` is the path to a file holding a JSON array of action dicts. (A
file path, not inline JSON, because passing a quote-laden JSON string through an
argv survives no shell intact.) Prints ONE JSON object to stdout (nothing else on
the success path, so the caller can parse it cleanly):

    {"schema": {"<verb>": ["<arg>", ...], ...},
     "verdicts": [[<ok:bool>, "<reason>"], ...]}

`schema` is the sidecar's loaded verb->required-args map; `verdicts[i]` is the
sidecar's (ok, reason) for `fixtures[i]`. Pure stdlib; importing `sidecar` does
not start the HTTP server (its main() is guarded by __main__).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Import the actual sidecar module from this file's directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sidecar  # noqa: E402  (the real module under test)


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: schema_parity_check.py <fixtures.json>"}))
        return 2
    try:
        fixtures = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"could not read fixtures: {exc}"}))
        return 2

    verbs = sidecar.load_schema()
    verdicts = [list(sidecar.validate_action(action, verbs)) for action in fixtures]
    print(json.dumps({"schema": verbs, "verdicts": verdicts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
