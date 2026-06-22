#!/usr/bin/env python3
"""Minimal edit on the LOCKED canon Klein (fb_v1 master): keep the WHOLE figure exactly
as-is -- same front-facing body, head, pose, outfit, framing, lighting, expression --
and change ONLY the EYES so the gaze looks to the RIGHT. Nothing else changes.

Conditioned on klein_canon_master.png at HIGH input_fidelity for maximum faithfulness;
the prompt asks for a single localized change (eyes glance right). N candidates so Mark
can pick the one that moved ONLY the eyes.

Out: out_image2/klein_canon/eyesR_v{1..N}.png  +  _eyesR_compare.png
"""

from __future__ import annotations

from PIL import Image, ImageDraw

import generate_tingen_image2 as g
from klein_char_experiment import _key

OUT = g.OUT_DIR / "klein_canon"
MASTER = OUT / "klein_canon_master.png"  # locked fb_v1
QUALITY = "medium"
N = 3


def eyes_prompt() -> str:
    return (
        "the EXACT same full-body cozy chibi character as the reference image, pixel-for-pixel "
        "identical in every way -- identical brown fedora, black hair, open brown/tan trench "
        "overcoat, dark pinstripe waistcoat, muted dusty-red tie, dark trousers, brown shoes, the "
        "small wrapped parcel-notebook in the same hand, identical front-facing head and body, "
        "identical idle standing pose, identical full-body framing and margins, identical somber "
        "expression, identical colors, proportions, cel-shading and dramatic lighting. Change "
        "ABSOLUTELY NOTHING except the EYES: the eyes now glance to the RIGHT -- both irises and "
        "pupils shifted toward the RIGHT side of the eyes -- while the head stays facing the viewer "
        "exactly as in the reference. Do not rotate the head or body, do not change the pose, outfit "
        "or framing. Keep the full figure head-to-shoes, isolated on a flat transparent background, "
        "no scenery, no ground, no cast shadow, no text, no border."
    )


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def main() -> None:
    _key()
    OUT.mkdir(parents=True, exist_ok=True)
    if not MASTER.exists():
        print(f"  MISSING master: {MASTER}")
        return
    print("== canon Klein chibi: eyes-to-the-RIGHT (minimal edit) ==")
    imgs: list[tuple[str, Image.Image]] = []
    for i in range(1, N + 1):
        op = OUT / f"eyesR_v{i}.png"
        if op.exists():
            print(f"  skip {op.name} (exists)")
            imgs.append((op.name, trim(Image.open(op).convert("RGBA"))))
            continue
        print(f"  GEN eyesR v{i} ...")
        img = g.generate(
            eyes_prompt(), "1024x1024", "transparent", QUALITY, [MASTER], True
        )
        if not img:
            print("    FAILED")
            continue
        op.write_bytes(img)
        print(f"    OK ({len(img)//1024}KB) -> {op.name}")
        imgs.append((op.name, trim(Image.open(op).convert("RGBA"))))

    base = trim(Image.open(MASTER).convert("RGBA"))
    panels = [("master(orig)", base)] + imgs
    cell = 300
    sheet = Image.new("RGBA", (len(panels) * cell, cell + 28), (255, 0, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(panels):
        x = i * cell
        d.text((x + 6, 6), label, fill=(255, 255, 255, 255))
        s = min(cell / im.width, cell / im.height) * 0.92
        r = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        sheet.alpha_composite(
            r, (x + (cell - r.width) // 2, 28 + (cell - r.height) // 2)
        )
    cpath = OUT / "_eyesR_compare.png"
    sheet.save(cpath)
    print(f"  compare -> {cpath}")
    print("  done.")


if __name__ == "__main__":
    main()
