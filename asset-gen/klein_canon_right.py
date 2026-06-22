#!/usr/bin/env python3
"""Seed the 4-way sprite set: turn the LOCKED canon Klein (fb_v1 master) to FACE RIGHT.

Mark's "look forward" meant "make it look to the right" -- the right-facing view is the
seed for the future 4-direction overworld set (down=master, left=mirror(right), up=back).
Conditioned on klein_canon_master.png at HIGH input_fidelity so the brown fedora / trench /
waistcoat / tie / parcel / proportions / dense cozy-chibi mood all carry across the turn;
the prompt only redirects the facing. N right-facing candidates for selection.

Out: out_image2/klein_canon/right_v{1..N}.png  +  _right_compare.png
"""

from __future__ import annotations

from PIL import Image, ImageDraw

import generate_tingen_image2 as g
from klein_canon_chibi import IDENT
from klein_char_experiment import _key

OUT = g.OUT_DIR / "klein_canon"
MASTER = OUT / "klein_canon_master.png"  # locked fb_v1
QUALITY = "medium"
N = 3

REF_IDENT = (
    "the EXACT same cozy chibi character as the reference image -- identical brown fedora, "
    "black hair, open brown/tan trench overcoat, dark pinstripe waistcoat, muted dusty-red tie, "
    "dark trousers, brown shoes, the small wrapped parcel-notebook in hand, identical colors, "
    f"gently rounded ~2.5-heads-tall proportions and dense moody somber style; {IDENT}"
)
TAIL = (
    "a FULL-BODY figure shown head to toe -- the ENTIRE figure from the top of the hat down to "
    "BOTH shoes is fully visible and centered with generous empty margin above the head and below "
    "the feet, absolutely NOT cropped at the legs or feet, both feet planted in an idle standing "
    "pose, smooth clean cel-shading with soft painterly rendering and NO pixelation, isolated on a "
    "flat transparent background, no scenery, no ground, no cast shadow, no text, no logo, no border"
)


def right_prompt() -> str:
    return (
        f"{REF_IDENT}, but turned to FACE RIGHT in a three-quarter side view -- his head and body "
        "are rotated toward the RIGHT side of the frame and his gaze looks to the RIGHT, we see his "
        "right side and a three-quarter profile of his face, NOT facing the viewer head-on. "
        + TAIL
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
    print("== canon Klein chibi: RIGHT-facing (4-way seed) ==")
    imgs: list[tuple[str, Image.Image]] = []
    for i in range(1, N + 1):
        op = OUT / f"right_v{i}.png"
        if op.exists():
            print(f"  skip {op.name} (exists)")
            imgs.append((op.name, trim(Image.open(op).convert("RGBA"))))
            continue
        print(f"  GEN right v{i} ...")
        img = g.generate(
            right_prompt(), "1024x1024", "transparent", QUALITY, [MASTER], True
        )
        if not img:
            print("    FAILED")
            continue
        op.write_bytes(img)
        print(f"    OK ({len(img)//1024}KB) -> {op.name}")
        imgs.append((op.name, trim(Image.open(op).convert("RGBA"))))

    # side-by-side compare: master (down) + each right candidate
    base = trim(Image.open(MASTER).convert("RGBA"))
    panels = [("master(down)", base)] + imgs
    cell = 280
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
    cpath = OUT / "_right_compare.png"
    sheet.save(cpath)
    print(f"  compare -> {cpath}")
    print("  done.")


if __name__ == "__main__":
    main()
