#!/usr/bin/env python3
"""Slice Mark's hand-approved 2x2 chibi-Klein sheet into a 4-way overworld set.

Input sheet (1024x1024, transparent bg) is a 2x2 grid of the SAME canon detective:
    TL = front / toward camera (DOWN)      TR = front-right 3/4 (unused)
    BL = LEFT profile (faces left)         BR = BACK / away (UP)

We take down=TL, left=BL, up=BR, and right = mirror(left) -- so left/right can NEVER
be reversed (right is literally left flipped). Each facing is trimmed to its alpha
bbox, scaled to one shared figure height, and pasted feet-aligned onto an identical
canvas, so the character does not pop/grow when turning (same contract as the old
klein_canon_directions.py, just sourced from the handmade sheet instead of API gens).

Out: out_image2/klein_canon/dir4/{down,left,right,up}.png  + _turnaround4.png
Also overwrites tingen/assets/characters/klein_{down,left,right,up}.png in place.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE / "out_image2" / "klein_canon"
SHEET = OUT / "klein_4way_sheet.png"
DIRS = OUT / "dir4"
GAME = HERE.parent / "tingen" / "assets" / "characters"

TARGET_H = 940  # shared figure height (hat-crown -> shoe-sole), px
PAD_TOP = 50
PAD_BOT = 50
PAD_X = 60


def trim(im: Image.Image) -> Image.Image:
    b = im.getbbox()
    return im.crop(b) if b else im


def quad(im: Image.Image, col: int, row: int, cw: int, ch: int) -> Image.Image:
    return im.crop((col * cw, row * ch, (col + 1) * cw, (row + 1) * ch))


def normalize(im: Image.Image, canvas_w: int, canvas_h: int) -> Image.Image:
    s = TARGET_H / im.height
    r = im.resize((max(1, round(im.width * s)), TARGET_H), Image.LANCZOS)
    out = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    out.alpha_composite(r, ((canvas_w - r.width) // 2, PAD_TOP))
    return out


def main() -> None:
    sheet = Image.open(SHEET).convert("RGBA")
    W, H = sheet.size
    cw, ch = W // 2, H // 2

    down = trim(quad(sheet, 0, 0, cw, ch))
    left = trim(quad(sheet, 0, 1, cw, ch))
    up = trim(quad(sheet, 1, 1, cw, ch))
    right = left.transpose(Image.FLIP_LEFT_RIGHT)
    facings = [("down", down), ("left", left), ("right", right), ("up", up)]

    for name, im in facings:
        print(f"  {name}: trimmed {im.size}")

    scaled_w = [round(im.width * (TARGET_H / im.height)) for _, im in facings]
    canvas_w = max(scaled_w) + 2 * PAD_X
    canvas_h = TARGET_H + PAD_TOP + PAD_BOT
    print(f"  canvas {canvas_w}x{canvas_h}, figure {TARGET_H}px, feet aligned")

    DIRS.mkdir(parents=True, exist_ok=True)
    norm: list[tuple[str, Image.Image]] = []
    for name, im in facings:
        n = normalize(im, canvas_w, canvas_h)
        n.save(DIRS / f"{name}.png")
        norm.append((name, n))

    # review sheet -- all four at identical scale to prove consistent sizing + facing
    cell_w, cell_h = canvas_w // 2, canvas_h // 2
    sheet_img = Image.new("RGBA", (4 * cell_w, cell_h + 28), (40, 40, 48, 255))
    d = ImageDraw.Draw(sheet_img)
    d.text(
        (6, 4),
        f"KLEIN 4-WAY (down|left|right|up)  each {canvas_w}x{canvas_h}",
        fill=(255, 255, 255, 255),
    )
    for i, (label, im) in enumerate(norm):
        x = i * cell_w
        d.text((x + 6, 16), label, fill=(120, 230, 160, 255))
        sheet_img.alpha_composite(im.resize((cell_w, cell_h), Image.LANCZOS), (x, 28))
    sheet_img.save(OUT / "_turnaround4.png")
    print(f"  turnaround -> {OUT / '_turnaround4.png'}")

    GAME.mkdir(parents=True, exist_ok=True)
    for name, _ in facings:
        (GAME / f"klein_{name}.png").write_bytes((DIRS / f"{name}.png").read_bytes())
        print(f"  -> game/{name}: klein_{name}.png")
    print("  done.")


if __name__ == "__main__":
    main()
