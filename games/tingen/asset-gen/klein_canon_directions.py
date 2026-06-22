#!/usr/bin/env python3
"""Build canon Klein's 4-direction overworld set from the HANDMADE base.

Top-down RPG facings: down (toward camera) = the handmade base; up = back view; left = 3/4
side view; right = mirror(left). Only TWO new gens (left + up), each conditioned on the FULL
1024x1024 handmade file at HIGH input_fidelity so the brown fedora / trench / waistcoat / tie /
parcel / proportions / dense cozy-chibi mood carry across the turn. Right is a free h-flip.

Raw gens land in dir/_raw/. Then a NORMALIZE pass trims every facing, scales them all to one
common figure height, and pastes each onto an identical canvas, horizontally centered and
feet-aligned to a shared baseline -- so all four frames are the SAME size and the character
does not pop/grow when turning.

Out: out_image2/klein_canon/dir/{down,left,right,up}.png (normalized, same size)  +  _turnaround.png
"""

from __future__ import annotations

from PIL import Image, ImageDraw

import generate_tingen_image2 as g
from klein_char_experiment import _key

OUT = g.OUT_DIR / "klein_canon"
DIRS = OUT / "dir"
RAW = DIRS / "_raw"
# Condition on the FULL 1024x1024 handmade file (figure centered with margin) -- the
# edge-to-edge trimmed crop biases the model to fill the frame and lop off hat/feet.
BASE = OUT / "klein_canon_handmade.png"
QUALITY = "medium"

# normalized output framing
TARGET_H = 940  # figure (hat-crown -> shoe-sole) height in px, shared by all facings
PAD_TOP = 50
PAD_BOT = 50
PAD_X = 60

IDENT = (
    "the EXACT same cozy chibi character as the reference image -- identical brown fedora, "
    "black hair, open brown trench overcoat, dark waistcoat, muted dusty-red tie, dark trousers, "
    "brown shoes, the small wrapped parcel-notebook, identical colors, gently rounded ~2.5-heads "
    "proportions and dense moody somber style"
)
TAIL = (
    "CRITICAL FRAMING: show the COMPLETE figure from the very TOP of the hat down to the SOLES of "
    "BOTH shoes -- the whole body fully inside the frame, absolutely NOT cropped at the hat, waist, "
    "hips, thighs, knees, ankles or feet. Draw the character SMALL and zoomed OUT, occupying only "
    "the central area of the square canvas with LARGE empty transparent margins above the hat and "
    "below the shoes. idle standing pose, both feet planted, smooth clean cel-shading with soft "
    "painterly rendering and NO pixelation, isolated on a flat transparent background, no scenery, "
    "no ground, no cast shadow, no text, no logo, no border"
)
LEFT_PROMPT = (
    f"{IDENT}, but turned to FACE LEFT in a three-quarter side view, as if walking to the LEFT in a "
    f"top-down RPG; we see his left side and a left profile of his face. {TAIL}"
)
BACK_PROMPT = (
    f"{IDENT}, but seen from BEHIND, facing directly AWAY from the viewer as if walking up/away in a "
    f"top-down RPG; we see the BACK of his fedora, the back of his black hair and the back of his "
    f"trench coat -- his face is NOT visible, no face. {TAIL}"
)


def trim(im: Image.Image) -> Image.Image:
    b = im.getbbox()
    return im.crop(b) if b else im


def gen_raw(name: str, prompt: str) -> Image.Image | None:
    fp = RAW / f"{name}.png"
    if fp.exists():
        print(f"  skip {name} (raw exists)")
        return trim(Image.open(fp).convert("RGBA"))
    print(f"  GEN {name} ...")
    img = g.generate(prompt, "1024x1024", "transparent", QUALITY, [BASE], True)
    if not img:
        print(f"  FAILED {name}")
        return None
    fp.write_bytes(img)
    print(f"    OK -> _raw/{fp.name} ({len(img)//1024}KB)")
    return trim(Image.open(fp).convert("RGBA"))


def normalize(im: Image.Image, canvas_w: int, canvas_h: int) -> Image.Image:
    """Scale a trimmed figure to TARGET_H and paste centered + feet-aligned on a shared canvas."""
    s = TARGET_H / im.height
    r = im.resize((max(1, round(im.width * s)), TARGET_H), Image.LANCZOS)
    out = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    x = (canvas_w - r.width) // 2
    y = PAD_TOP  # top of figure; feet land at PAD_TOP + TARGET_H = canvas_h - PAD_BOT
    out.alpha_composite(r, (x, y))
    return out


def main() -> None:
    _key()
    RAW.mkdir(parents=True, exist_ok=True)
    if not BASE.exists():
        print(f"  MISSING base: {BASE}")
        return
    print("== canon Klein 4-way overworld set ==")

    down_raw = trim(Image.open(BASE).convert("RGBA"))
    left_raw = gen_raw("left", LEFT_PROMPT)
    up_raw = gen_raw("up", BACK_PROMPT)
    right_raw = (
        left_raw.transpose(Image.FLIP_LEFT_RIGHT) if left_raw is not None else None
    )

    raws = [
        ("down", down_raw),
        ("left", left_raw),
        ("right", right_raw),
        ("up", up_raw),
    ]
    present = [(n, im) for n, im in raws if im is not None]

    # shared canvas: scale every figure to TARGET_H, size the canvas to the widest one
    scaled_w = [round(im.width * (TARGET_H / im.height)) for _, im in present]
    canvas_w = max(scaled_w) + 2 * PAD_X
    canvas_h = TARGET_H + PAD_TOP + PAD_BOT
    print(
        f"  normalize -> canvas {canvas_w}x{canvas_h}, figure height {TARGET_H}px (feet aligned)"
    )

    norm: list[tuple[str, Image.Image]] = []
    for name, im in raws:
        if im is None:
            norm.append((name, None))
            continue
        n = normalize(im, canvas_w, canvas_h)
        n.save(DIRS / f"{name}.png")
        norm.append((name, n))

    # turnaround review sheet -- frames pasted at IDENTICAL scale to prove consistent sizing
    cell_w = canvas_w // 3
    cell_h = canvas_h // 3
    sheet = Image.new("RGBA", (4 * cell_w, cell_h + 28), (255, 0, 255, 255))
    d = ImageDraw.Draw(sheet)
    d.text(
        (6, 4),
        f"KLEIN 4-WAY  (down|left|right|up)  all {canvas_w}x{canvas_h}",
        fill=(0, 0, 0, 255),
    )
    for i, (label, im) in enumerate(norm):
        x = i * cell_w
        d.text((x + 6, 16), label, fill=(255, 255, 255, 255))
        if im is None:
            d.text((x + 6, cell_h // 2), "MISSING", fill=(255, 255, 255, 255))
            continue
        r = im.resize((cell_w, cell_h), Image.LANCZOS)
        sheet.alpha_composite(r, (x, 28))
    cpath = OUT / "_turnaround.png"
    sheet.save(cpath)
    print(f"  turnaround -> {cpath}")
    print("  done.")


if __name__ == "__main__":
    main()
