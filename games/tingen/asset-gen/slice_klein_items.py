#!/usr/bin/env python3
"""Slice the gpt-image-1 Klein items sheet into individual transparent prop PNGs.

The sheet came back RGB with a baked light-gray checkerboard background (the model
"drew" transparency instead of emitting alpha).  We key that out with a magic-wand
flood-fill from the image border (so contact shadows that touch the background are
removed, but light areas *inside* furniture are preserved), label the remaining
blobs, and crop each to its own RGBA file.  A magenta contact sheet is written for
visual review.

Out: out_image2/klein_room/items/item_##.png  +  items_contact.png
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
import scipy.ndimage as ndi

HERE = Path(__file__).resolve().parent
SRC = HERE / "out_image2" / "klein_room" / "items_sheet.png"
OUT = HERE / "out_image2" / "klein_room" / "items"
CONTACT = HERE / "out_image2" / "klein_room" / "items_contact.png"

MIN_AREA = 3000          # drop specks / keying noise
PAD = 6                  # px padding around each crop


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rgb = np.array(Image.open(SRC).convert("RGB")).astype(np.int16)
    h, w, _ = rgb.shape
    mx = rgb.max(2)
    mn = rgb.min(2)
    sat = mx - mn
    val = mx
    # "background-like": low saturation AND bright (white/gray checker + soft shadow).
    bg_like = (sat < 30) & (val > 165)

    # (a) Flood-fill background inward from the border: checker/shadow connected to
    # the edge becomes transparent (also removes the soft contact shadows that touch
    # the background under each piece).
    lbl, n = ndi.label(bg_like)
    border = set(np.unique(np.concatenate([lbl[0], lbl[-1], lbl[:, 0], lbl[:, -1]])))
    border.discard(0)
    bg_border = np.isin(lbl, list(border))

    # (b) Enclosed checker pockets the border flood-fill can't reach: the see-through
    # gaps between the chair slats/legs, the bed-headboard posts, the mirror arms.
    # The transparency checker is a NEUTRAL light gray (R approx = G approx = B) while
    # the furniture stays warm brown even in shadow, so a tight neutral+bright key
    # carves out those sealed gaps without eating the wood.  THIS removes the
    # "white space within" that Mark flagged.
    bg_checker = (sat < 18) & (val > 150)

    background = bg_border | bg_checker

    fg = ~background
    # tidy: close 1px pinholes in the foreground, then drop tiny noise blobs
    fg = ndi.binary_closing(fg, iterations=1)
    flbl, fn = ndi.label(fg)
    sizes = ndi.sum(np.ones_like(flbl), flbl, index=range(1, fn + 1))

    alpha = np.where(fg, 255, 0).astype(np.uint8)
    # feather the cut edge by 1px so there's no hard white halo
    edge = fg & ~ndi.binary_erosion(fg, iterations=1)
    alpha[edge] = 180

    rgba = np.dstack([rgb.astype(np.uint8), alpha])

    keep = [(i + 1, int(sizes[i])) for i in range(fn) if sizes[i] >= MIN_AREA]
    # order top-to-bottom, then left-to-right by blob centroid
    cents = ndi.center_of_mass(fg, flbl, [k for k, _ in keep])
    rows = []
    for (lab, area), (cy, cx) in zip(keep, cents):
        rows.append((lab, area, cy, cx))
    rows.sort(key=lambda r: (round(r[2] / 180), r[3]))  # band by ~180px rows, then x

    crops = []
    print(f"sheet {w}x{h}: {fn} blobs, {len(rows)} kept (area>={MIN_AREA})")
    for idx, (lab, area, cy, cx) in enumerate(rows, 1):
        ys, xs = np.where(flbl == lab)
        y0, y1 = max(0, ys.min() - PAD), min(h, ys.max() + 1 + PAD)
        x0, x1 = max(0, xs.min() - PAD), min(w, xs.max() + 1 + PAD)
        # within this bbox, only keep THIS blob's pixels opaque (avoid neighbor bleed)
        sub = rgba[y0:y1, x0:x1].copy()
        submask = (flbl[y0:y1, x0:x1] == lab)
        sub[~submask, 3] = 0
        im = Image.fromarray(sub, "RGBA")
        fp = OUT / f"item_{idx:02d}.png"
        im.save(fp)
        crops.append((fp, im.size, (x1 - x0, y1 - y0), area))
        print(f"  item_{idx:02d}  bbox={x1-x0}x{y1-y0}  area={area}")

    # contact sheet on magenta so cut quality is obvious
    cols = 4
    rows_n = (len(crops) + cols - 1) // cols
    cell = 360
    sheet = Image.new("RGBA", (cols * cell, rows_n * cell), (255, 0, 255, 255))
    for i, (fp, _, _, _) in enumerate(crops):
        im = Image.open(fp)
        s = min(cell / im.width, cell / im.height) * 0.92
        im2 = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))))
        cxp = (i % cols) * cell + (cell - im2.width) // 2
        cyp = (i // cols) * cell + (cell - im2.height) // 2
        sheet.alpha_composite(im2, (cxp, cyp))
    sheet.save(CONTACT)
    print(f"contact -> {CONTACT}")


if __name__ == "__main__":
    main()
