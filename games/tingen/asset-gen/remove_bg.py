#!/usr/bin/env python3
"""Cut the gpt-image-1 character/enemy sprites out onto true transparent alpha.

gpt-image-1 ignores `background:transparent` and paints a light-gray/white (or
dark vignette) backdrop.  We matte it out with rembg's `isnet-anime` model —
purpose-built for cel-shaded anime/manhua art, so it keeps flowing hair, veils
and smoke far better than a flood-fill colour key.

Originals are preserved under out_image2/_opaque/<category>/ before the
transparent version is written back in place (same asset path, now RGBA), so a
re-matte is always possible.

Usage:
  python3 remove_bg.py --sample goddess_darkness audrey_hall wraith_shadow  # preview only
  python3 remove_bg.py --category characters          # whole category, in place
  python3 remove_bg.py                                 # characters + enemies
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PIL import Image
from rembg import remove, new_session

HERE = Path(__file__).resolve().parent
OUT = HERE / "out_image2"
BACKUP = OUT / "_opaque"
PREVIEW = OUT / "_cutout_preview"
CATEGORIES = ["characters", "enemies"]

# isnet-anime: best for our cel-shaded cast; falls back to u2net if unavailable.
try:
    SESSION = new_session("isnet-anime")
except Exception as e:  # noqa: BLE001
    print(f"isnet-anime unavailable ({e}); falling back to u2net")
    SESSION = new_session("u2net")


def cutout(src: Path) -> Image.Image:
    img = Image.open(src).convert("RGBA")
    # alpha matting refines the hair/smoke fringe at a modest speed cost.
    return remove(img, session=SESSION, alpha_matting=True,
                  alpha_matting_foreground_threshold=240,
                  alpha_matting_background_threshold=10,
                  alpha_matting_erode_size=2)


def on_checker(im: Image.Image, cell: int = 16) -> Image.Image:
    """Composite an RGBA over a gray checker so the cut quality is visible."""
    w, h = im.size
    bg = Image.new("RGBA", (w, h), (245, 245, 245, 255))
    px = bg.load()
    for y in range(h):
        for x in range(w):
            if (x // cell + y // cell) % 2:
                px[x, y] = (205, 205, 205, 255)
    bg.alpha_composite(im)
    return bg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", choices=CATEGORIES, help="only this category")
    ap.add_argument("--sample", nargs="+", help="preview these item names only (no in-place write)")
    args = ap.parse_args()

    if args.sample:
        PREVIEW.mkdir(parents=True, exist_ok=True)
        for cat in CATEGORIES:
            for name in args.sample:
                src = OUT / cat / f"{name}.png"
                if not src.exists():
                    continue
                cut = cutout(src)
                cut.save(PREVIEW / f"{name}.png")
                on_checker(cut).convert("RGB").save(PREVIEW / f"{name}_checker.png")
                print(f"preview {cat}/{name} -> {PREVIEW/(name+'_checker.png')}")
        return

    cats = [args.category] if args.category else CATEGORIES
    n = 0
    for cat in cats:
        d = OUT / cat
        bdir = BACKUP / cat
        bdir.mkdir(parents=True, exist_ok=True)
        for src in sorted(d.glob("*.png")):
            backup = bdir / src.name
            if not backup.exists():
                shutil.copy2(src, backup)        # preserve opaque original once
            cut = cutout(backup)                 # always matte from the opaque source
            cut.save(src)
            n += 1
            print(f"  cut {cat}/{src.name}")
    print(f"\nDone: {n} sprites matted to transparent (originals in {BACKUP})")


if __name__ == "__main__":
    main()
