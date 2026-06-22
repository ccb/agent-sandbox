#!/usr/bin/env python3
"""Klein character ART-STYLE experiment (Mark): downscale / pixelate / cute-ify the
in-game characters (Stardew-style low-res sprite for gameplay, while the existing
1024x1536 anime sprite stays the hi-res dialogue portrait).  Start with Klein.

Round-1 spread: 4 distinct directions, each conditioned LOOSELY (low input_fidelity)
on the canon `klein1` ref so it keeps Klein's identity (black caped overcoat, top hat,
gold eyes) but adopts the new cute/low-res style.  Each raw gen is then auto-pixelized
(LANCZOS downscale -> palette quantize -> NEAREST upscale) so we see the ACTUAL in-game
low-res sprite, not just gpt's faux-pixel render.  A contact sheet (raw | pixelized) is
written on magenta so transparency is obvious.

medium quality (~$0.05/img) is plenty here: we downscale to ~64px anyway.

Out: out_image2/klein_char/<name>.png  +  _contact.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

import generate_tingen_image2 as g

OUT = g.OUT_DIR / "klein_char"
QUALITY = "medium"
SPRITE_H = 64  # target in-game sprite height (px) for the pixelized preview
PALETTE = 32  # colors for the pixel-art quantize

# Klein identity clause, reused so every direction stays recognizably Klein.
KLEIN = (
    "Klein Moretti, a young man with black hair swept back and glowing gold eyes, in a "
    "charcoal-black caped Inverness overcoat with a deep-violet lining, a white high collar and "
    "dark cravat, a brown leather shoulder-holster, a black top hat, holding a black cane"
)

COMMON = (
    "single character, one full-body figure standing in an idle pose, the whole figure from the "
    "top of the hat to the feet centered inside the frame with empty margin all around, fully "
    "isolated on a flat transparent background, no scenery, no ground, no cast shadow, no text, "
    "no logo, no frame, no border"
)

STYLES = {
    "A_stardew_pixel": (
        "a 16-bit pixel-art video-game character sprite in the style of Stardew Valley and classic "
        "SNES farming RPGs, cute chibi proportions about 2.5 heads tall, three-quarter front-facing "
        "overworld view, clean readable chunky pixels with a crisp pixel outline, cozy limited palette "
        "with warm gaslight tones, " + KLEIN + ", " + COMMON
    ),
    "B_cozy_chibi": (
        "an adorable cozy chibi character, big round head and small body about 2 heads tall, soft clean "
        "cel-shading, smooth vector-cute look (NOT pixelated), three-quarter front view, simplified "
        "charming features, warm gaslight palette, " + KLEIN + ", " + COMMON
    ),
    "C_hd2d_octopath": (
        "a detailed HD-2D pixel-art sprite in the style of Octopath Traveler and Triangle Strategy, "
        "about 3 heads tall, moody atmospheric pixel shading with soft rim light, three-quarter front "
        "view, more detailed than 8-bit, keeping an occult-detective gravitas yet small and charming, "
        + KLEIN
        + ", "
        + COMMON
    ),
    "D_snes_overworld": (
        "a tiny 16-bit SNES JRPG overworld sprite in the style of Chrono Trigger and early Pokemon, "
        "very small and simple super-deformed proportions, three-quarter front view, bold simple "
        "shapes that stay readable at small size, limited palette, "
        + KLEIN
        + ", "
        + COMMON
    ),
}


def _key() -> None:
    if not g.OPENAI_API_KEY:
        g.OPENAI_API_KEY = g.load_key(g.DEFAULT_ENV_FILE)
    if not g.OPENAI_API_KEY:
        sys.exit("ERROR: OPENAI_API_KEY not found")
    print(f"  key loaded ({len(g.OPENAI_API_KEY)} chars)")


def pixelize(src: Path, target_h: int = SPRITE_H, colors: int = PALETTE) -> Image.Image:
    """High-res gen -> genuine low-res pixel sprite: average down (LANCZOS), quantize the
    RGB to a small palette, binarize alpha for crisp sprite edges."""
    im = Image.open(src).convert("RGBA")
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
    out = Image.merge("RGBA", (*rgb.split(), a))
    return out


def main() -> None:
    _key()
    OUT.mkdir(parents=True, exist_ok=True)
    ref = g.prep_ref("klein1", headroom=0.0)  # cropped canon Klein (identity cue)
    refs = [ref] if ref else []
    print(f"  ref: {[p.name for p in refs] or 'NONE'}  fidelity=low  quality={QUALITY}")

    made = []
    for name, prompt in STYLES.items():
        fp = OUT / f"{name}.png"
        if fp.exists():
            print(f"  skip {name} (exists)")
            made.append(fp)
            continue
        print(f"  GEN {name} ...")
        img = g.generate(prompt, "1024x1024", "transparent", QUALITY, refs, False)
        if not img:
            print(f"  FAILED {name}")
            continue
        fp.write_bytes(img)
        made.append(fp)
        print(f"    OK -> {fp.name} ({len(img)//1024}KB)")

    # contact sheet: each row = raw | pixelized(up-nearest), on magenta
    if made:
        cell = 240
        cols = 2
        rows = len(made)
        sheet = Image.new("RGBA", (cols * cell + 120, rows * cell), (255, 0, 255, 255))
        from PIL import ImageDraw

        d = ImageDraw.Draw(sheet)
        for i, fp in enumerate(made):
            raw = Image.open(fp).convert("RGBA")
            s = min(cell / raw.width, cell / raw.height) * 0.92
            raw2 = raw.resize((int(raw.width * s), int(raw.height * s)), Image.LANCZOS)
            sheet.alpha_composite(
                raw2,
                (120 + (cell - raw2.width) // 2, i * cell + (cell - raw2.height) // 2),
            )
            pix = pixelize(fp)
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
            # save the pixelized sprite too (the real in-game asset preview)
            pix.resize((pw, ph), Image.NEAREST).save(
                OUT / f"{fp.stem}_px{SPRITE_H}.png"
            )
        d.text((124, 4), "RAW gen", fill=(0, 0, 0, 255))
        d.text(
            (124 + cell, 4), f"PIXELIZED {SPRITE_H}px (in-game)", fill=(0, 0, 0, 255)
        )
        cpath = OUT / "_contact.png"
        sheet.save(cpath)
        print(f"  contact -> {cpath}")


if __name__ == "__main__":
    main()
