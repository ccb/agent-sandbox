#!/usr/bin/env python3
"""The picked v1 chibi Klein came out cropped at the thighs. Regenerate it as a TRUE
FULL-BODY sprite (head-to-shoes) in the same look, using the picked v1 plus the canon
Tingen full-body figure as references so the face/outfit/style carry while the framing
opens up to show the whole figure with margin below the feet.

Out: out_image2/klein_canon/fb_v{1..N}.png
"""

from __future__ import annotations

import generate_tingen_image2 as g
from klein_canon_chibi import IDENT  # reuse the canon Tingen identity
from klein_char_experiment import COMMON, _key

OUT = g.OUT_DIR / "klein_canon"
V1 = OUT / "front_v1.png"
REF = OUT / "_ref_klein_tingen.png"
QUALITY = "medium"
N = 3


def fb_prompt() -> str:
    return (
        "a FULL-BODY cozy chibi character shown head to toe -- the ENTIRE figure from the top of "
        "the hat down to BOTH shoes is fully visible and centered with generous empty margin above "
        "the head and below the feet, absolutely NOT cropped at the legs, knees or feet, both feet "
        "planted in an idle standing pose, gently rounded proportions, a slightly oversized head on "
        "a small body about 2.5 heads tall, smooth clean cel-shading with soft painterly rendering "
        "and NO pixelation, three-quarter front view, simplified but expressive features with a "
        "serious, wary, faintly haunted expression -- brooding and somber, NOT cheerful and NOT "
        "playful, a dense moody atmosphere with a muted desaturated palette and small cold gaslight "
        "accents, heavy dramatic chiaroscuro shadows and a single warm rim light, "
        f"{IDENT}, wearing exactly one brown fedora on his head, " + COMMON
    )


def main() -> None:
    _key()
    OUT.mkdir(parents=True, exist_ok=True)
    refs = [p for p in (V1, REF) if p.exists()]
    if not refs:
        print("  MISSING refs (front_v1.png / _ref_klein_tingen.png)")
        return
    print("== full-body canon Klein chibi (reframe of v1) ==")
    for i in range(1, N + 1):
        op = OUT / f"fb_v{i}.png"
        if op.exists():
            print(f"  skip {op.name} (exists)")
            continue
        print(f"  GEN full-body v{i} ...")
        img = g.generate(fb_prompt(), "1024x1024", "transparent", QUALITY, refs, False)
        if not img:
            print("    FAILED")
            continue
        op.write_bytes(img)
        print(f"    OK ({len(img)//1024}KB) -> {op.name}")
    print("  done.")


if __name__ == "__main__":
    main()
