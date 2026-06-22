#!/usr/bin/env python3
"""Package the locked dense cozy-chibi Klein as a HAND-OFF for the animation agent's
generate_tingen_anim.py pipeline (which conditions Stage A on a hero ref and Stage B on
a design sheet).  Builds a chibi DESIGN SHEET in that pipeline's Stage-A format
(front | side | back full-body + face close-up + palette swatches, on flat warm-gray,
no text) so it can be dropped in as anim/player_detective/_design.png, and copies the
clean reference assets into one obvious handoff/ folder.

This writes ONLY into out_image2/klein_chibi/handoff/ -- it does NOT touch the anim
agent's generate_tingen_anim.py, their anim/ outputs, or player_detective.png.

Out: out_image2/klein_chibi/handoff/{klein_chibi_designsheet.png, klein_chibi_master.png,
     klein_walk96.png, klein_down/left/right/up.png}
"""

from __future__ import annotations

from PIL import Image, ImageDraw

import generate_tingen_image2 as g

CHIBI = g.OUT_DIR / "klein_chibi"
DIRS = CHIBI / "dir"
SETD = CHIBI / "set"
HANDOFF = CHIBI / "handoff"
BG = (224, 221, 217)  # flat warm-gray matching the anim pipeline's design sheets
SHEET = (1536, 1024)  # match SHEET_SIZE so it is a drop-in _design.png


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def fit(im: Image.Image, box_w: int, box_h: int) -> Image.Image:
    s = min(box_w / im.width, box_h / im.height)
    return im.resize(
        (max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS
    )


def _close(a, b, tol=26) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def palette(im: Image.Image, k: int = 6):
    rgb = Image.new("RGB", im.size, BG)
    rgb.paste(im.convert("RGB"), mask=im.split()[3])
    q = rgb.quantize(colors=k + 3, method=Image.FASTOCTREE).convert("RGB")
    counts = sorted(q.getcolors(maxcolors=1 << 20), reverse=True)
    out = []
    for _cnt, col in counts:
        if _close(col, BG):
            continue
        out.append(col)
        if len(out) >= k:
            break
    return out


def main() -> None:
    HANDOFF.mkdir(parents=True, exist_ok=True)
    down = trim(Image.open(DIRS / "down.png").convert("RGBA"))
    side = trim(Image.open(DIRS / "right.png").convert("RGBA"))  # right-facing profile
    back = trim(Image.open(DIRS / "up.png").convert("RGBA"))

    sheet = Image.new("RGBA", SHEET, (*BG, 255))

    # three full-body views across the top
    body_h = 660
    cols = [0.18, 0.45, 0.72]  # center x fractions for front/side/back
    for im, cx in zip((down, side, back), cols):
        v = fit(im, 360, body_h)
        x = int(SHEET[0] * cx) - v.width // 2
        sheet.alpha_composite(v, (x, 70))

    # face close-up (crop head region of the front view), bottom-right
    head = down.crop((0, 0, down.width, int(down.height * 0.5)))
    head = fit(trim(head), 340, 300)
    sheet.alpha_composite(
        head, (SHEET[0] - head.width - 60, SHEET[1] - head.height - 60)
    )

    # palette swatches, bottom-left
    d = ImageDraw.Draw(sheet)
    sw = 64
    x0, y0 = 70, SHEET[1] - sw - 70
    for i, col in enumerate(palette(down, 6)):
        d.rectangle(
            [x0 + i * (sw + 8), y0, x0 + i * (sw + 8) + sw, y0 + sw],
            fill=(*col, 255),
            outline=(60, 60, 60, 255),
        )

    out = HANDOFF / "klein_chibi_designsheet.png"
    sheet.convert("RGB").save(out)  # opaque, like their _design.png
    print(f"  design sheet -> {out}  {SHEET}")

    # copy the clean reference assets into the handoff folder
    copies = {
        "klein_chibi_master.png": CHIBI / "klein_chibi_master.png",
        "klein_walk96.png": SETD / "klein_walk96.png",
        "klein_down.png": DIRS / "down.png",
        "klein_left.png": DIRS / "left.png",
        "klein_right.png": DIRS / "right.png",
        "klein_up.png": DIRS / "up.png",
    }
    for name, src in copies.items():
        if src.exists():
            Image.open(src).convert("RGBA").save(HANDOFF / name)
            print(f"  copy -> handoff/{name}")
        else:
            print(f"  MISSING {src}")
    print(f"\n  handoff ready: {HANDOFF}")


if __name__ == "__main__":
    main()
