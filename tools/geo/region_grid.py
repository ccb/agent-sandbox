#!/usr/bin/env python3
"""Render an enlarged, coordinate-labeled grid of a tile sheet (or a sub-region)
so a human/LLM can read off exact (col,row) for cataloging.

    uv run --with pillow python tools/geo/region_grid.py <sheet> <tile_px> \
        [--cols c0 c1] [--rows r0 r1] [--scale N] [--out path]

Axis labels run along the top (cols) and left (rows); a faint grid separates
cells. This is a dev/QA tool, not used by the game.
"""

from __future__ import annotations

import argparse
import os

from PIL import Image, ImageDraw  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAPS = os.path.join(REPO, "godot-generative-agents", "godot", "maps")
KENNEY = os.path.join(HERE, "assets", "kenney")


def resolve(name: str) -> str:
    for root in (MAPS, KENNEY, HERE, "."):
        p = os.path.join(root, name)
        if os.path.exists(p):
            return p
    raise SystemExit(f"sheet not found: {name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("tile", type=int)
    ap.add_argument("--cols", type=int, nargs=2)
    ap.add_argument("--rows", type=int, nargs=2)
    ap.add_argument("--scale", type=int, default=20)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    im = Image.open(resolve(a.sheet)).convert("RGBA")
    SHEET_C, SHEET_R = im.width // a.tile, im.height // a.tile
    c0, c1 = a.cols if a.cols else (0, SHEET_C - 1)
    r0, r1 = a.rows if a.rows else (0, SHEET_R - 1)
    nc, nr = c1 - c0 + 1, r1 - r0 + 1

    S = a.scale
    cell = a.tile * S
    MARGIN = 22
    W = MARGIN + nc * cell
    H = MARGIN + nr * cell
    canvas = Image.new("RGBA", (W, H), (28, 28, 34, 255))

    region = im.crop((c0 * a.tile, r0 * a.tile, (c1 + 1) * a.tile, (r1 + 1) * a.tile))
    # checker bg so transparent tiles are visible
    chk = Image.new("RGBA", region.size, (44, 44, 54, 255))
    region = Image.alpha_composite(chk, region)
    region = region.resize((nc * cell, nr * cell), Image.NEAREST)
    canvas.paste(region, (MARGIN, MARGIN))

    d = ImageDraw.Draw(canvas)
    for i in range(nc + 1):
        x = MARGIN + i * cell
        d.line([(x, MARGIN), (x, H)], fill=(90, 90, 110, 160))
    for j in range(nr + 1):
        y = MARGIN + j * cell
        d.line([(MARGIN, y), (W, y)], fill=(90, 90, 110, 160))
    for i in range(nc):
        d.text(
            (MARGIN + i * cell + cell // 2 - 6, 6), str(c0 + i), fill=(255, 235, 120)
        )
    for j in range(nr):
        d.text(
            (4, MARGIN + j * cell + cell // 2 - 6), str(r0 + j), fill=(255, 235, 120)
        )

    out = a.out or os.path.join(HERE, "out", f"grid_{os.path.splitext(a.sheet)[0]}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    canvas.save(out)
    print(f"wrote {out}  ({W}x{H}px, cols {c0}-{c1} rows {r0}-{r1})")


if __name__ == "__main__":
    main()
