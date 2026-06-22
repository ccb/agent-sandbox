#!/usr/bin/env python3
"""Slice the Klein items sheet into individual transparent prop PNGs — rembg variant.

The June-9 regen of items_sheet.png came back on a DARK WARM-BROWN vignette backdrop
(not the light-gray checker the original slice_klein_items.py keys out).  The backdrop
shares the wooden furniture's hue, so a bright/neutral colour-key can't separate it.
Instead we matte the whole sheet with rembg (general u2net foreground model), then
label the connected foreground blobs and crop each piece to its own RGBA file.

This PRESERVES each object's tilt and painted detail (Mark's ask); rembg keeps the
soft shadow attached to each piece as long as it reads as foreground.  A magenta
contact sheet is written for visual review.

Out: out_image2/klein_room/items/item_##.png  +  items_contact.png
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
import scipy.ndimage as ndi
from rembg import remove, new_session

HERE = Path(__file__).resolve().parent
SRC = HERE / "out_image2" / "klein_room" / "items_sheet.png"
OUT = HERE / "out_image2" / "klein_room" / "items"
CONTACT = HERE / "out_image2" / "klein_room" / "items_contact.png"

MIN_AREA = 4000          # drop specks / keying noise
PAD = 8                  # px padding around each crop
ALPHA_TH = 80            # alpha >= this counts as foreground (raw u2net mask)

try:
    SESSION = new_session("u2net")
except Exception as e:  # noqa: BLE001
    print(f"u2net unavailable ({e}); falling back to isnet-anime")
    SESSION = new_session("isnet-anime")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    src_img = Image.open(SRC).convert("RGBA")
    # RAW u2net matte (no alpha_matting): keeps clean black gaps between the well-spaced
    # pieces so connected-component labelling splits them cleanly.  alpha_matting + hole
    # filling bridged neighbouring pieces into one giant blob, so both are omitted.
    cut = remove(src_img, session=SESSION)
    rgba = np.array(cut)
    h, w = rgba.shape[:2]
    alpha = rgba[:, :, 3]

    fg = alpha >= ALPHA_TH
    flbl, fn = ndi.label(fg)
    sizes = ndi.sum(np.ones_like(flbl), flbl, index=range(1, fn + 1))
    keep = [(i + 1, int(sizes[i])) for i in range(fn) if sizes[i] >= MIN_AREA]

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
