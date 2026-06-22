#!/usr/bin/env python3
"""Redo the chibi Klein grounded in the CANON Tingen-arc detective look (LotM wiki ref),
instead of the later black-caped 'Fool' look. Same locked dense cozy-chibi style + somber
mood as before, but era-correct: brown trench, fedora, pinstripe waistcoat, muted red tie,
black hair, brown eyes, carrying a notebook/parcel.

Uses the cropped canon figure (out_image2/klein_canon/_ref_klein_tingen.png, made from
ref/wiki/Klein_Moretti_Beginning_of_the_Series.jpg) as a LOOSE restyle reference so the
outfit/identity carry while the prompt drives the chibi style. Generates N front variants
for selection BEFORE committing to a full turnaround/handoff.

Out: out_image2/klein_canon/front_v{1..N}.png
"""

from __future__ import annotations

import generate_tingen_image2 as g
from klein_char_experiment import COMMON, _key

OUT = g.OUT_DIR / "klein_canon"
REF = (
    OUT / "_ref_klein_tingen.png"
)  # cropped canon Tingen figure (made in the crop step)
QUALITY = "medium"
N = 3

IDENT = (
    "Klein Moretti as the early-series Tingen detective: a young man with neat black hair "
    "parted to the side and brown eyes, wearing an open brown/tan trench overcoat over a dark "
    "pinstripe waistcoat and a white shirt with a muted dusty-red tie, dark trousers and brown "
    "shoes, a brown wide-brimmed fedora hat, holding a small parcel-wrapped notebook"
)


def front_prompt() -> str:
    return (
        "a cozy chibi character with gently rounded proportions, a slightly oversized head on a "
        "small body about 2.5 heads tall, smooth clean cel-shading with soft painterly rendering "
        "and NO pixelation, three-quarter front view, simplified but expressive features with a "
        "serious, wary, faintly haunted expression -- brooding and somber, NOT cheerful and NOT "
        "playful, a dense moody atmosphere with a muted desaturated palette and small cold "
        "gaslight accents, heavy dramatic chiaroscuro shadows and a single warm rim light, "
        f"{IDENT}, wearing exactly one brown fedora on his head, " + COMMON
    )


def main() -> None:
    _key()
    OUT.mkdir(parents=True, exist_ok=True)
    if not REF.exists():
        print(f"  MISSING canon ref crop: {REF}")
        return
    print("== canon Tingen Klein chibi (front variants) ==")
    for i in range(1, N + 1):
        op = OUT / f"front_v{i}.png"
        if op.exists():
            print(f"  skip {op.name} (exists)")
            continue
        print(f"  GEN front v{i} ...")
        img = g.generate(
            front_prompt(), "1024x1024", "transparent", QUALITY, [REF], False
        )
        if not img:
            print("    FAILED")
            continue
        op.write_bytes(img)
        print(f"    OK ({len(img)//1024}KB) -> {op.name}")
    print("  done.")


if __name__ == "__main__":
    main()
