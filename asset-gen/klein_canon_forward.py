#!/usr/bin/env python3
"""Tweak pass on the locked canon Klein: same full-body chibi detective, but facing the
viewer head-on with a level FORWARD gaze and a calmer, non-frowning expression (still
somber/serious, just not scowling). References the locked master + canon figure so the
look/outfit/proportions carry while the face direction + expression change.

Out: out_image2/klein_canon/fwd_v{1..N}.png
"""

from __future__ import annotations

import generate_tingen_image2 as g
from klein_canon_chibi import IDENT
from klein_char_experiment import COMMON, _key

OUT = g.OUT_DIR / "klein_canon"
MASTER = OUT / "klein_canon_master.png"  # locked fb_v1
REF = OUT / "_ref_klein_tingen.png"
QUALITY = "medium"
N = 3


def fwd_prompt() -> str:
    return (
        "a FULL-BODY cozy chibi character shown head to toe -- the ENTIRE figure from the top of "
        "the hat down to BOTH shoes is fully visible and centered with generous empty margin above "
        "the head and below the feet, absolutely NOT cropped at the legs or feet, both feet planted "
        "in an idle standing pose, gently rounded proportions, a slightly oversized head on a small "
        "body about 2.5 heads tall, smooth clean cel-shading with soft painterly rendering and NO "
        "pixelation, a straight-on FRONT view facing the viewer head-on with the head held level and "
        "both eyes looking directly FORWARD at the viewer, simplified but expressive features with a "
        "calm, composed, quietly confident expression and a relaxed neutral mouth -- gently serious "
        "but NOT frowning and NOT scowling, eyebrows relaxed, a dense moody atmosphere with a muted "
        "desaturated palette and small cold gaslight accents, soft dramatic chiaroscuro shadows and a "
        f"single warm rim light, {IDENT}, wearing exactly one brown fedora on his head, "
        + COMMON
    )


def main() -> None:
    _key()
    OUT.mkdir(parents=True, exist_ok=True)
    refs = [p for p in (MASTER, REF) if p.exists()]
    if not refs:
        print("  MISSING refs (klein_canon_master.png / _ref_klein_tingen.png)")
        return
    print("== canon Klein chibi: forward gaze + softer expression ==")
    for i in range(1, N + 1):
        op = OUT / f"fwd_v{i}.png"
        if op.exists():
            print(f"  skip {op.name} (exists)")
            continue
        print(f"  GEN forward v{i} ...")
        img = g.generate(fwd_prompt(), "1024x1024", "transparent", QUALITY, refs, False)
        if not img:
            print("    FAILED")
            continue
        op.write_bytes(img)
        print(f"    OK ({len(img)//1024}KB) -> {op.name}")
    print("  done.")


if __name__ == "__main__":
    main()
