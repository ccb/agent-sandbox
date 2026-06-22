#!/usr/bin/env python3
"""
Cross-language prayer-adjudication parity helper (mirrors schema_parity_check.py).
==================================================================================
Imports the REAL prayer_adjudicator reference and runs it over a battery of prayer requests
read from a JSON-array file, printing ONE JSON object to stdout:

    {"verdicts": [[<outcome:str>, <severity:int>], ...]}

Invoked by tingen/tests/run_tests.gd:
    python3 agent-sidecar/prayer_parity_check.py <fixtures.json>
A file path (not inline JSON) so a quote-laden payload survives the argv. Pure stdlib.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prayer_adjudicator as pa  # noqa: E402  (the real reference under test)


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: prayer_parity_check.py <fixtures.json>"}))
        return 2
    try:
        fixtures = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"could not read fixtures: {exc}"}))
        return 2
    gods = pa.load_gods()
    verdicts = []
    for req in fixtures:
        v = pa.adjudicate_prayer(req, gods)
        verdicts.append([v["outcome"], v["severity"]])
    print(json.dumps({"verdicts": verdicts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
