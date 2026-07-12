#!/usr/bin/env python3
"""Export reel cards as Playdate imagetables (M4 PoC; docs section 5).

The reel (via app/figures.js -- the generated registry, single source of
truth) renders each card in headless Chromium; the card's own 12 fps step
clock is driven MANUALLY (stop the interval, call _tickAll per frame) so
frames are deterministic. Each frame is scaled to fit 384x240, letterboxed
on black, Floyd-Steinberg dithered to 1-bit, and packed into a grid PNG
named <key>-table-384-240.png -- which pdc compiles into an imagetable the
device animates at 12 fps.

Run:  python3 playdate/tools/export_figures.py road=204 glowstone=60 guts-a=72
"""

import io
import os
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIGURES_JS = os.path.join(REPO, "app", "figures.js")
OUT = os.path.join(REPO, "playdate", "Source", "images", "figures")
EXE = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium_headless_shell-1208/"
    "chrome-headless-shell-mac-arm64/chrome-headless-shell"
)
CELL_W, CELL_H, COLS = 384, 240, 12

HARNESS = """<!doctype html><meta charset="utf-8">
<body style="margin:0;background:#000">
<div id="stage" style="width:640px"></div>
<script src="file://%s"></script>
</body>"""


def export(page, key, frames):
    # a set_content page (about:blank origin) may not load file:// scripts;
    # navigate to a real file so the script tag resolves
    import tempfile

    harness = os.path.join(tempfile.gettempdir(), "pd_fig_harness.html")
    with open(harness, "w") as fh:
        fh.write(HARNESS % FIGURES_JS)
    page.goto("file://" + harness)
    page.wait_for_function("window.TombFigures !== undefined")
    page.evaluate(
        """() => {
          CanvasRenderingContext2D.prototype.fillText = function () {};
          CanvasRenderingContext2D.prototype.strokeText = function () {};
        }"""
    )
    ok = page.evaluate(
        """(key) => {
          const F = window.TombFigures;
          if (!F.has(key)) return false;
          F.render(key, document.getElementById('stage'));
          if (F._timer) { clearInterval(F._timer); F._timer = null; }
          return true;
        }""",
        key,
    )
    if not ok:
        raise SystemExit(f"no card named {key}")
    # NATIVE-TEXT LAYER: the device renders all words itself (real
    # Playdate fonts, content/captions.lua), so the export strips every
    # label -- svg text hidden, canvas text no-opped -- leaving pure
    # geometry for the imagetable.
    page.evaluate(
        """() => {
          document.querySelectorAll('#stage text')
            .forEach((t) => t.setAttribute('display', 'none'));
          // dim phosphor (#24587c) falls below the 1-bit threshold -- the
          // wagon's canopy, the dunes. Lift it to full phosphor: at 1-bit,
          // hierarchy is carried by stroke weight, not tone.
          document.querySelectorAll('#stage [stroke="#24587c"]')
            .forEach((e) => e.setAttribute('stroke', '#4db8ff'));
          document.querySelectorAll('#stage [fill="#24587c"]')
            .forEach((e) => e.setAttribute('fill', '#4db8ff'));
        }"""
    )
    stage = page.locator("#stage")
    # pre-roll past the reveal wipe (cards open covered; ~12 ticks clears it)
    for _ in range(14):
        page.evaluate("window.TombFigures._tickAll()")
    cells = []
    for _ in range(frames):
        shot = Image.open(io.BytesIO(stage.screenshot())).convert("L")
        scale = min(CELL_W / shot.width, CELL_H / shot.height)
        shot = shot.resize(
            (int(shot.width * scale), int(shot.height * scale)), Image.LANCZOS
        )
        cell = Image.new("L", (CELL_W, CELL_H), 0)
        cell.paste(shot, ((CELL_W - shot.width) // 2, (CELL_H - shot.height) // 2))
        # THRESHOLD, not error-diffusion: line art wants crisp stable
        # strokes. Floyd-Steinberg re-rolls per frame (shimmering sand,
        # text chewed to mush); a fixed cutoff keeps black black, keeps
        # the dim phosphor lines, and never flickers.
        cells.append(cell.point(lambda v: 255 if v >= 55 else 0, mode="1"))
        page.evaluate("window.TombFigures._tickAll()")
    # pad the final row with copies of the last frame: the device's
    # imagetable length counts grid CELLS, and a hold on an empty padding
    # cell shows black instead of the tableau
    while len(cells) % COLS != 0:
        cells.append(cells[-1])
    rows = (len(cells) + COLS - 1) // COLS
    grid = Image.new("1", (CELL_W * COLS, CELL_H * rows), 0)
    for i, cell in enumerate(cells):
        grid.paste(cell, ((i % COLS) * CELL_W, (i // COLS) * CELL_H))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{key}-table-{CELL_W}-{CELL_H}.png")
    grid.save(path)
    print(f"{key}: {len(cells)} frames -> {os.path.relpath(path, REPO)}")


def main():
    jobs = []
    for arg in sys.argv[1:]:
        key, _, n = arg.partition("=")
        jobs.append((key, int(n or 60)))
    if not jobs:
        jobs = [("road", 204), ("glowstone", 60), ("guts-a", 72)]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=EXE)
        page = browser.new_page(viewport={"width": 700, "height": 500})
        for key, frames in jobs:
            export(page, key, frames)
        browser.close()


if __name__ == "__main__":
    main()
