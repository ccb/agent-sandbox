#!/usr/bin/env python3
"""Build Klein's 4-direction overworld walk set from the LOCKED V1 master.

Top-down RPG facings: down (toward camera) = the master itself; up = back view;
left = side view; right = mirror(left).  So only TWO new gens are needed (back + left),
each conditioned on klein_chibi_master.png at HIGH input_fidelity so the outfit, palette
and dense cozy-chibi proportions carry across the turnaround.  Right is a free h-flip.

Turnaround contact sheet (down | left | right | up), raw row + pixelized 96px row, on
magenta.  Per-facing trimmed PNGs land in out_image2/klein_chibi/dir/.

Out: out_image2/klein_chibi/dir/{down,left,right,up}.png  +  _turnaround.png
"""

from __future__ import annotations

from PIL import Image, ImageDraw

import generate_tingen_image2 as g
from klein_char_experiment import _key, pixelize

CHIBI = g.OUT_DIR / "klein_chibi"
DIRS = CHIBI / "dir"
MASTER = CHIBI / "klein_chibi_master.png"
QUALITY = "medium"
SPRITE_H = 96
PALETTE = 48

# Concise directional prompts -- short on purpose so they don't fight the high-fidelity
# ref; the ref carries identity, the prompt only redirects the facing.
IDENT = (
    "the EXACT same cozy chibi character as the reference image -- identical black top hat, "
    "charcoal caped Inverness overcoat, white collar, brown shoulder-holster, glowing gold eyes, "
    "black cane, identical colors, proportions and dense moody somber style"
)
TAIL = (
    "full body, idle standing pose, the whole figure centered with empty margin all around, "
    "isolated on a flat transparent background, no scenery, no ground, no cast shadow, no text, "
    "no logo, no border"
)
LEFT_PROMPT = (
    f"{IDENT}, but turned to FACE LEFT in a three-quarter side view, as if walking to the left in "
    f"a top-down RPG; we see his left side and profile. {TAIL}"
)
BACK_PROMPT = (
    f"{IDENT}, but seen from BEHIND, facing directly AWAY from the viewer as if walking up/away in "
    f"a top-down RPG; we see the BACK of his top hat, the back of his black hair and the back of his "
    f"caped overcoat -- his face is NOT visible, no face. {TAIL}"
)


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def gen_dir(name: str, prompt: str) -> Image.Image | None:
    fp = DIRS / f"{name}.png"
    if fp.exists():
        print(f"  skip {name} (exists)")
        return trim(Image.open(fp).convert("RGBA"))
    print(f"  GEN {name} ...")
    img = g.generate(prompt, "1024x1024", "transparent", QUALITY, [MASTER], True)
    if not img:
        print(f"  FAILED {name}")
        return None
    fp.write_bytes(img)
    print(f"    OK -> {fp.name} ({len(img)//1024}KB)")
    return trim(Image.open(fp).convert("RGBA"))


def main() -> None:
    _key()
    DIRS.mkdir(parents=True, exist_ok=True)

    down = trim(Image.open(MASTER).convert("RGBA"))
    down.save(DIRS / "down.png")
    left = gen_dir("left", LEFT_PROMPT)
    up = gen_dir("up", BACK_PROMPT)
    right = None
    if left is not None:
        right = left.transpose(Image.FLIP_LEFT_RIGHT)
        right.save(DIRS / "right.png")

    facings = [("down", down), ("left", left), ("right", right), ("up", up)]
    cell = 240
    cols = 4
    sheet = Image.new("RGBA", (cols * cell, 2 * cell + 24), (255, 0, 255, 255))
    d = ImageDraw.Draw(sheet)
    d.text((6, 4), "TURNAROUND  (raw top / pixelized 96px bottom)", fill=(0, 0, 0, 255))
    for i, (label, im) in enumerate(facings):
        x = i * cell
        d.text((x + 6, 16), label, fill=(255, 255, 255, 255))
        if im is None:
            d.text((x + 6, cell), "MISSING", fill=(255, 255, 255, 255))
            continue
        s = min(cell / im.width, cell / im.height) * 0.9
        raw2 = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        sheet.alpha_composite(
            raw2, (x + (cell - raw2.width) // 2, 24 + (cell - raw2.height) // 2)
        )
        # pixelize from the trimmed facing
        px = trim(_pixelize_im(im))
        ph = int(cell * 0.9)
        pw = max(1, round(px.width * ph / px.height))
        px2 = px.resize((pw, ph), Image.NEAREST)
        sheet.alpha_composite(
            px2, (x + (cell - px2.width) // 2, 24 + cell + (cell - px2.height) // 2)
        )
        px.save(DIRS / f"{label}_px{SPRITE_H}.png")
    cpath = CHIBI / "_turnaround.png"
    sheet.save(cpath)
    print(f"  turnaround -> {cpath}")


def _pixelize_im(im: Image.Image) -> Image.Image:
    """pixelize() takes a path; replicate its core on an in-memory image."""
    w, h = im.size
    nw = max(1, round(w * SPRITE_H / h))
    small = im.resize((nw, SPRITE_H), Image.LANCZOS)
    r, gg, b, a = small.split()
    rgb = (
        Image.merge("RGB", (r, gg, b))
        .quantize(colors=PALETTE, method=Image.FASTOCTREE)
        .convert("RGB")
    )
    a = a.point(lambda v: 255 if v >= 128 else 0)
    return Image.merge("RGBA", (*rgb.split(), a))


if __name__ == "__main__":
    main()
