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
    # Boost the type before capture: reel labels are sized for a monitor;
    # at 0.6x they land at ~6 device px. 1.7x (with tightened tracking)
    # puts them at ~11 px -- readable 1-bit -- without touching geometry.
    # (Canvas-drawn text is untouched; those cards await small masters.)
    page.evaluate(
        """() => {
          const K = 2.3;
          const texts = [];
          document.querySelectorAll('#stage text').forEach((t) => {
            const y = parseFloat(t.getAttribute('y') || '0');
            if (t.getAttribute('text-anchor') === 'end' && y < 30) {
              t.setAttribute('display', 'none'); // topline chrome: cut
              return;
            }
            const fs = parseFloat(t.getAttribute('font-size') || '10');
            const nfs = Math.round(fs * K);
            t.setAttribute('font-size', nfs);
            t.setAttribute('letter-spacing', '0.5');
            if (y > 350) { // footer band: wrapped per-frame, not shrunk
              t.dataset.footer = '1';
              t.dataset.fs = nfs;
              t.dataset.oy = y;
            }
            texts.push({ t, y, fs: nfs });
          });
          // bigger type needs more leading: labels sharing a column (same
          // x + anchor) get re-spaced so they can't overlap
          const cols = {};
          texts.forEach((e) => {
            const key = (e.t.getAttribute('text-anchor') || 'start') + '|'
              + (e.t.getAttribute('x') || '0');
            (cols[key] = cols[key] || []).push(e);
          });
          for (const key in cols) {
            const col = cols[key].sort((a, b) => a.y - b.y);
            for (let i = 1; i < col.length; i++) {
              const need = col[i - 1].y + col[i - 1].fs * 1.15;
              if (col[i].y < need) {
                col[i].y = need;
                col[i].t.setAttribute('y', need);
              }
            }
          }
          // per-frame footer wrap: typeOn rewrites these nodes every tick,
          // so re-split the current string into tspans before each capture
          window.__wrapFooters = () => {
            document.querySelectorAll('#stage text[data-footer]').forEach((t) => {
              const s = (t.textContent || '').trimEnd();
              if (!s) return;
              const fs = parseFloat(t.dataset.fs);
              const est = fs * 0.62 + 0.5; // char width, letterspaced
              const maxChars = Math.floor(600 / est);
              if (s.length <= maxChars) return;
              const words = s.split(' ');
              const lines = [];
              let cur = '';
              words.forEach((w) => {
                if ((cur + ' ' + w).trim().length > maxChars) {
                  if (cur) lines.push(cur);
                  cur = w;
                } else {
                  cur = cur ? cur + ' ' + w : w;
                }
              });
              if (cur) lines.push(cur);
              const lh = fs * 1.1;
              t.textContent = '';
              t.setAttribute('y',
                Math.min(parseFloat(t.dataset.oy), 394 - (lines.length - 1) * lh));
              const x = t.getAttribute('x');
              lines.forEach((ln, i) => {
                const sp = document.createElementNS(
                  'http://www.w3.org/2000/svg', 'tspan');
                sp.setAttribute('x', x);
                sp.setAttribute('dy', i === 0 ? 0 : lh);
                sp.textContent = ln;
                t.appendChild(sp);
              });
            });
          };
        }"""
    )
    stage = page.locator("#stage")
    # pre-roll past the reveal wipe (cards open covered; ~12 ticks clears it)
    for _ in range(14):
        page.evaluate("window.TombFigures._tickAll()")
    cells = []
    for _ in range(frames):
        page.evaluate("window.__wrapFooters()")
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
