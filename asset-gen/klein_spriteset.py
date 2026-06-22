#!/usr/bin/env python3
"""Assemble Klein's 4 directional views into a game-ready, feet-aligned sprite set.

Inputs: out_image2/klein_chibi/dir/{down,left,right,up}.png (the locked turnaround).
Each is trimmed, pixelized to a uniform 96px height, then bottom-centered on a common
WxH canvas so Klein is the same size and his feet sit on the same baseline whichever
way he faces -- exactly what a top-down facing-swap needs.

Out:
  out_image2/klein_chibi/set/klein_{down,left,right,up}.png  (individual frames)
  out_image2/klein_chibi/set/klein_walk96.png                (4-frame horizontal strip)
  out_image2/klein_chibi/_set_preview.png                    (magenta preview)
"""

from __future__ import annotations

from PIL import Image, ImageDraw

import generate_tingen_image2 as g

CHIBI = g.OUT_DIR / "klein_chibi"
DIRS = CHIBI / "dir"
SET = CHIBI / "set"
SPRITE_H = 96
PALETTE = 48
ORDER = ["down", "left", "right", "up"]


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def pixelize_im(
    im: Image.Image, target_h: int = SPRITE_H, colors: int = PALETTE
) -> Image.Image:
    w, h = im.size
    nw = max(1, round(w * target_h / h))
    small = im.resize((nw, target_h), Image.LANCZOS)
    r, gg, b, a = small.split()
    rgb = (
        Image.merge("RGB", (r, gg, b))
        .quantize(colors=colors, method=Image.FASTOCTREE)
        .convert("RGB")
    )
    a = a.point(lambda v: 255 if v >= 128 else 0)
    return Image.merge("RGBA", (*rgb.split(), a))


def main() -> None:
    SET.mkdir(parents=True, exist_ok=True)

    frames = {}
    for label in ORDER:
        fp = DIRS / f"{label}.png"
        if not fp.exists():
            print(f"  MISSING {label} ({fp})")
            continue
        frames[label] = trim(pixelize_im(trim(Image.open(fp).convert("RGBA"))))

    if not frames:
        print("  no frames -- run klein_directions.py first")
        return

    H = max(f.height for f in frames.values())
    W = max(f.width for f in frames.values())
    print(f"  {len(frames)} frames, common canvas {W}x{H}")

    canvases = {}
    for label, f in frames.items():
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        c.alpha_composite(f, ((W - f.width) // 2, H - f.height))  # bottom-centered
        c.save(SET / f"klein_{label}.png")
        canvases[label] = c

    strip = Image.new("RGBA", (W * len(ORDER), H), (0, 0, 0, 0))
    for i, label in enumerate(ORDER):
        if label in canvases:
            strip.alpha_composite(canvases[label], (i * W, 0))
    strip.save(SET / "klein_walk96.png")
    print(f"  strip {strip.size} -> set/klein_walk96.png")

    # magenta preview, frames upscaled x3 NEAREST with labels
    scale = 3
    pad = 16
    pw, ph = W * scale, H * scale
    prev = Image.new(
        "RGBA", (len(ORDER) * (pw + pad) + pad, ph + 40), (255, 0, 255, 255)
    )
    d = ImageDraw.Draw(prev)
    d.text((6, 4), "KLEIN 4-DIR SPRITE SET (96px, x3 nearest)", fill=(0, 0, 0, 255))
    for i, label in enumerate(ORDER):
        x = pad + i * (pw + pad)
        if label in canvases:
            big = canvases[label].resize((pw, ph), Image.NEAREST)
            prev.alpha_composite(big, (x, 24))
        d.text((x + 4, ph + 26), label, fill=(255, 255, 255, 255))
    ppath = CHIBI / "_set_preview.png"
    prev.save(ppath)
    print(f"  preview -> {ppath}")


if __name__ == "__main__":
    main()
