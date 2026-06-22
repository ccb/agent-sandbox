#!/usr/bin/env python3
"""Clean-key a building sprite off a near-white background into a transparent PNG.

Three steps, in order, because each fixes a different artifact:
  1. KEY     - mark border-connected near-white as background -> alpha 0
               (connected, so light pixels *inside* the building are kept)
  2. ERODE   - shrink the alpha edge by N px to drop the anti-aliased fringe ring
  3. BLEED   - fill every transparent pixel's RGB with its nearest opaque colour,
               so LINEAR texture filtering in the engine never samples white
               (this is the usual cause of a white halo around a cutout)

Reusable for any building sprite generated on a white/pale background.

Usage:
  python3 key_building.py SRC OUT [--white 222] [--erode 1]
"""

import argparse
import numpy as np
from PIL import Image


def erode(mask: np.ndarray, iters: int) -> np.ndarray:
    for _ in range(iters):
        m = mask.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            m &= np.roll(np.roll(mask, dy, 0), dx, 1)
        mask = m
    return mask


def nearest_color_fill(rgb: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    """Every pixel takes the colour of the nearest opaque pixel (edge bleed)."""
    try:
        from scipy import ndimage

        idx = ndimage.distance_transform_edt(
            ~opaque, return_distances=False, return_indices=True
        )
        return rgb[idx[0], idx[1]]
    except Exception:
        out = rgb.copy()
        filled = opaque.copy()
        for _ in range(40):
            if filled.all():
                break
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nbr_filled = np.roll(np.roll(filled, dy, 0), dx, 1)
                nbr_rgb = np.roll(np.roll(out, dy, 0), dx, 1)
                take = nbr_filled & ~filled
                out[take] = nbr_rgb[take]
                filled |= take
        return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument(
        "--white",
        type=int,
        default=222,
        help="min RGB channel value counted as background-white",
    )
    ap.add_argument(
        "--erode",
        type=int,
        default=2,
        help="px to shrink the alpha edge (kills the fringe ring)",
    )
    ap.add_argument(
        "--white-hole",
        type=int,
        default=236,
        dest="white_hole",
        help="remove ANY pixel >= this brightness, even enclosed ones "
        "(background showing through fence/railing/window gaps)",
    )
    a = ap.parse_args()

    arr = np.asarray(Image.open(a.src).convert("RGB"))
    nearwhite = arr.min(2) >= a.white

    # keep only near-white that touches the border -> background (preserves
    # legitimately-bright pixels enclosed by the building)
    try:
        from scipy import ndimage

        lbl, _ = ndimage.label(nearwhite)
        border = set(lbl[0]).union(lbl[-1], lbl[:, 0], lbl[:, -1])
        border.discard(0)
        bg = np.isin(lbl, list(border))
    except Exception:
        bg = nearwhite  # fallback: treat all near-white as background

    # also drop enclosed near-white pockets (background showing through gaps in a
    # fence / railing / window) that are not connected to the outer border
    bg = bg | (arr.min(2) >= a.white_hole)

    opaque = erode(~bg, a.erode)
    rgb = nearest_color_fill(arr, opaque)
    out = np.dstack([rgb, np.where(opaque, 255, 0)]).astype(np.uint8)

    res = Image.fromarray(out, "RGBA")
    res = res.crop(res.getbbox())
    res.save(a.out)
    print(f"saved {a.out}  size={res.size}  opaque={100*opaque.mean():.1f}%")


if __name__ == "__main__":
    main()
