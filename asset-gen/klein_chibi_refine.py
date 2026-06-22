#!/usr/bin/env python3
"""Klein cozy-chibi REFINEMENT (Mark picked direction B, with a note: keep the cozy
chibi proportions + smooth cel-shade, but make the MOOD dense / somber / occult --
NOT cheerful or playful).  Also kills the duplicate-hat artifact from round 1.

Generates 3 stochastic variants of one refined "dense cozy chibi" prompt (medium
quality, conditioned LOOSELY on canon klein1 so identity carries), then pixelizes each
at 96px -- a touch higher than the 64px pixel direction, because this smoother
cel-shaded look needs the extra resolution so the brooding face doesn't muddy.

Contact sheet: each row = raw gen | pixelized(96px, NEAREST upscale), on magenta.

Out: out_image2/klein_chibi/<name>.png  +  _px96.png previews  +  _contact.png
"""

from __future__ import annotations

from PIL import Image, ImageDraw

import generate_tingen_image2 as g
from klein_char_experiment import COMMON, KLEIN, _key, pixelize

OUT = g.OUT_DIR / "klein_chibi"
QUALITY = "medium"
SPRITE_H = 96  # target in-game sprite height (px); higher than the 64px pixel look
PALETTE = 48  # more colors than the pixel direction, to keep soft cel-shading
N = 3  # stochastic variants of the same refined prompt

# Cozy chibi proportions (the B look) but with the mood dialed DENSE + somber, and an
# explicit single-hat / single-cane clause to remove the round-1 duplicate-hat artifact.
MOOD = (
    "a cozy chibi character with gently rounded proportions, a slightly oversized head on a small "
    "body about 2.5 heads tall, smooth clean cel-shading with soft painterly rendering and NO "
    "pixelation, three-quarter front view, simplified but expressive features wearing a serious, "
    "wary, faintly haunted expression -- brooding and somber, NOT cheerful, NOT playful, NOT "
    "grinning, mouth closed, a dense moody atmosphere with a muted desaturated palette of charcoal "
    "black, deep violet and cold amber gaslight, heavy dramatic chiaroscuro shadows and a single "
    "warm rim light, an air of quiet occult dread and weary detective gravitas, "
    + KLEIN
    + ", exactly one black top hat worn on his head and nothing in the other hand except resting "
    "on a single black cane, " + COMMON
)


def main() -> None:
    _key()
    OUT.mkdir(parents=True, exist_ok=True)
    ref = g.prep_ref("klein1", headroom=0.0)
    refs = [ref] if ref else []
    print(
        f"  ref: {[p.name for p in refs] or 'NONE'}  fidelity=low  quality={QUALITY}  n={N}"
    )

    made = []
    for i in range(1, N + 1):
        name = f"V{i}_dense_chibi"
        fp = OUT / f"{name}.png"
        if fp.exists():
            print(f"  skip {name} (exists)")
            made.append(fp)
            continue
        print(f"  GEN {name} ...")
        img = g.generate(MOOD, "1024x1024", "transparent", QUALITY, refs, False)
        if not img:
            print(f"  FAILED {name}")
            continue
        fp.write_bytes(img)
        made.append(fp)
        print(f"    OK -> {fp.name} ({len(img)//1024}KB)")

    if not made:
        return

    cell = 260
    cols = 2
    rows = len(made)
    sheet = Image.new("RGBA", (cols * cell + 120, rows * cell), (255, 0, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, fp in enumerate(made):
        raw = Image.open(fp).convert("RGBA")
        s = min(cell / raw.width, cell / raw.height) * 0.92
        raw2 = raw.resize((int(raw.width * s), int(raw.height * s)), Image.LANCZOS)
        sheet.alpha_composite(
            raw2, (120 + (cell - raw2.width) // 2, i * cell + (cell - raw2.height) // 2)
        )
        pix = pixelize(fp, target_h=SPRITE_H, colors=PALETTE)
        ph = int(cell * 0.9)
        pw = max(1, round(pix.width * ph / pix.height))
        pix2 = pix.resize((pw, ph), Image.NEAREST)
        sheet.alpha_composite(
            pix2,
            (
                120 + cell + (cell - pix2.width) // 2,
                i * cell + (cell - pix2.height) // 2,
            ),
        )
        d.text((6, i * cell + cell // 2), fp.stem, fill=(255, 255, 255, 255))
        pix.save(OUT / f"{fp.stem}_px{SPRITE_H}.png")
    d.text((124, 4), "RAW gen", fill=(0, 0, 0, 255))
    d.text((124 + cell, 4), f"PIXELIZED {SPRITE_H}px (in-game)", fill=(0, 0, 0, 255))
    cpath = OUT / "_contact.png"
    sheet.save(cpath)
    print(f"  contact -> {cpath}")


if __name__ == "__main__":
    main()
