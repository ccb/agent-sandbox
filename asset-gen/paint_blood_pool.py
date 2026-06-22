#!/usr/bin/env python3
"""Repaint IntroRoom's blood pool as a guaranteed-clean straight-alpha RGBA PNG.

Why: the ported `blood_pool_0.png` rendered as a bright MAGENTA blob in Godot,
even though its import settings are byte-identical to a known-good prop
(klein_bed.png) and the project is not in a linear/HDR-2D colour space.  The blob
had the correct pool SHAPE but wrong COLOUR and was immune to self_modulate -- the
signature of bad RGB data hiding under the keyed-out transparent edges (a left-over
from removing gpt-image-1's baked checkerboard).  With `process/fix_alpha_border=
true`, Godot bleeds that stray colour inward, which is what tints the pool.

Fix: paint a fresh pool where the ENTIRE RGB plane is solid wine and only the ALPHA
channel carries the shape.  Colour fringing then becomes impossible regardless of
filtering or alpha-border fixing.  Matches the original canvas size so the
IntroRoom node transform (pos 455,482  scale 0.5) is unchanged.

Out: overwrites tingen/assets/props/blood_pool_0.png  (used ONLY by IntroRoom.tscn)
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
DST = HERE.parent / "tingen" / "assets" / "props" / "blood_pool_0.png"


def main() -> None:
    assert DST.exists(), f"missing {DST}"

    # --- inspect the broken original (diagnostic) ---------------------------
    orig = Image.open(DST)
    W, H = orig.size
    print(f"orig: size={orig.size} mode={orig.mode}")
    o = orig.convert("RGBA")
    px = o.load()
    cx0, cy0 = W // 2, H // 2
    print(f"  centre px            = {px[cx0, cy0]}")
    # sample a ring of edge pixels: where alpha is low, what is the RGB?
    edge_samples = []
    for dx, dy in ((0, -H // 3), (W // 3, 0), (0, H // 3), (-W // 3, 0)):
        x, y = max(0, min(W - 1, cx0 + dx)), max(0, min(H - 1, cy0 + dy))
        edge_samples.append((px[x, y]))
    print(f"  edge px (N,E,S,W)    = {edge_samples}")
    # what RGB lives under fully-transparent pixels? (the magenta suspect)
    transp = [px[x, y] for x in (1, W // 2, W - 2) for y in (1, H - 2)
              if px[x, y][3] == 0]
    print(f"  RGB under alpha==0   = {transp[:6]}")

    # --- repaint: RGB = solid wine everywhere, ALPHA = pool shape -----------
    random.seed(7)
    base = (104, 16, 24)   # wet wine
    dark = (54, 7, 13)     # deep centre

    # alpha mask: organic pool from overlapping ellipses + a few droplets
    alpha = Image.new("L", (W, H), 0)
    ad = ImageDraw.Draw(alpha)
    cx, cy = W // 2, int(H * 0.54)
    for _ in range(16):
        rx = random.randint(int(W * 0.16), int(W * 0.33))
        ry = random.randint(int(H * 0.11), int(H * 0.23))
        ox = cx + random.randint(-int(W * 0.12), int(W * 0.12))
        oy = cy + random.randint(-int(H * 0.09), int(H * 0.09))
        ad.ellipse([ox - rx, oy - ry, ox + rx, oy + ry], fill=255)
    for _ in range(7):                       # satellite droplets
        r = random.randint(3, 11)
        ox = cx + random.randint(-int(W * 0.40), int(W * 0.40))
        oy = cy + random.randint(-int(H * 0.32), int(H * 0.32))
        ad.ellipse([ox - r, oy - r, ox + r, oy + r], fill=255)
    alpha = alpha.filter(ImageFilter.GaussianBlur(max(1.0, W * 0.012)))

    # rgb: wine everywhere, darkened toward the centre for a deep-pool read
    rgb = Image.new("RGB", (W, H), base)
    rad = Image.new("L", (W, H), 0)
    rd = ImageDraw.Draw(rad)
    maxr = int(min(W, H) * 0.40)
    rd.ellipse([cx - maxr, cy - maxr, cx + maxr, cy + maxr], fill=170)
    rad = rad.filter(ImageFilter.GaussianBlur(max(1.0, W * 0.05)))
    rgb = Image.composite(Image.new("RGB", (W, H), dark), rgb, rad)

    # faint glossy highlight (kept subtle) -- still pure wine family
    gloss = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(gloss)
    gd.ellipse([cx - int(W * 0.10), cy - int(H * 0.12),
                cx + int(W * 0.02), cy - int(H * 0.02)], fill=46)
    gloss = gloss.filter(ImageFilter.GaussianBlur(max(1.0, W * 0.02)))
    rgb = Image.composite(Image.new("RGB", (W, H), (140, 34, 42)), rgb, gloss)

    out = Image.merge("RGBA", (*rgb.split(), alpha))
    out.save(DST)
    print(f"painted clean wine pool -> {DST.name}  ({W}x{H}, RGB solid wine)")


if __name__ == "__main__":
    main()
