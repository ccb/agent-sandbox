#!/usr/bin/env python3
"""Assemble app/dist/: the self-contained web terminal (design §4).

Builds the engine wheel (pure Python, zero runtime deps -- the engine's heavy
imports are all lazy/optional, guarded by the blocked-imports audit in
tests/test_web_terminal.py) and copies the terminal sources beside it, plus a
manifest so terminal.js can find the wheel by its versioned name.

    uv run python app/build_dist.py
    python -m http.server -d app/dist 8000   # then play at localhost:8000

The identical dist/ is what the iOS shell bundles (M4) and what deploys to a
static host for the web version.
"""

import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DIST = os.path.join(HERE, "dist")


def main() -> int:
    os.makedirs(DIST, exist_ok=True)
    for stale in glob.glob(os.path.join(DIST, "*.whl")):
        os.remove(stale)
    subprocess.run(["uv", "build", "--wheel", "-o", DIST], cwd=REPO, check=True)
    wheels = sorted(glob.glob(os.path.join(DIST, "*.whl")))
    if not wheels:
        print("no wheel produced", file=sys.stderr)
        return 1
    wheel = os.path.basename(wheels[-1])
    for name in ("index.html", "terminal.css", "terminal.js", "app_api.py"):
        shutil.copy(os.path.join(HERE, name), DIST)
    with open(os.path.join(DIST, "manifest.json"), "w") as fh:
        json.dump({"wheel": wheel}, fh)
    print(f"dist/ ready: {wheel} + terminal ({DIST})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
