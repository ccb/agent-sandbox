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


PYODIDE_VERSION = "0.26.4"
PYODIDE_CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
# The five files the browser runtime needs; everything else in the full
# distribution is optional packages the Tomb never imports.
PYODIDE_FILES = (
    "pyodide.js",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
)


def _vendor_pyodide() -> None:
    """Download the Pyodide runtime into dist/pyodide/ so the bundle is fully
    offline -- required for the iOS app (design §4), optional for the web."""
    import urllib.request

    vendor = os.path.join(DIST, "pyodide")
    os.makedirs(vendor, exist_ok=True)
    for name in PYODIDE_FILES:
        target = os.path.join(vendor, name)
        if os.path.exists(target):
            continue
        print(f"fetching {name} ...")
        urllib.request.urlretrieve(PYODIDE_CDN + name, target)


def main() -> int:
    with_pyodide = "--with-pyodide" in sys.argv
    os.makedirs(DIST, exist_ok=True)
    for stale in glob.glob(os.path.join(DIST, "*.whl")):
        os.remove(stale)
    subprocess.run(["uv", "build", "--wheel", "-o", DIST], cwd=REPO, check=True)
    wheels = sorted(glob.glob(os.path.join(DIST, "*.whl")))
    if not wheels:
        print("no wheel produced", file=sys.stderr)
        return 1
    wheel = os.path.basename(wheels[-1])
    # figures.js regenerates from the reel every build (single source of truth)
    sys.path.insert(0, HERE)
    import gen_figures

    gen_figures.generate()
    for name in (
        "index.html",
        "terminal.css",
        "terminal.js",
        "app_api.py",
        "figures.js",
    ):
        shutil.copy(os.path.join(HERE, name), DIST)
    # the animation-prototype reel ships as a shareable subpage
    reel = os.path.join(HERE, "prototypes", "retro-animations.html")
    if os.path.exists(reel):
        os.makedirs(os.path.join(DIST, "animations"), exist_ok=True)
        shutil.copy(reel, os.path.join(DIST, "animations", "index.html"))
    manifest = {"wheel": wheel}
    if with_pyodide:
        _vendor_pyodide()
        manifest["pyodideBase"] = "./pyodide/"
    with open(os.path.join(DIST, "manifest.json"), "w") as fh:
        json.dump(manifest, fh)
    kind = "offline (pyodide vendored)" if with_pyodide else "CDN runtime"
    print(f"dist/ ready: {wheel} + terminal, {kind} ({DIST})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
