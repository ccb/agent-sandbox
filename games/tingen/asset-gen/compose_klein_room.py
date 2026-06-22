#!/usr/bin/env python3
"""Lay the cleaned Klein cut-outs onto the bare room to recreate room.png's scene.

This is an OFFLINE placement harness: it composites items/item_*.png onto
room_bare.png using the SAME convention Godot's Prop.gd uses at runtime --
each sprite is scaled so its HEIGHT == icon_px and anchored at its FEET
(bottom-centre) on the node's (x, y).  So once the composite matches room.png,
the (x, y, icon_px) numbers below port straight into IntroRoom.tscn.

Canvas is the 896x597 floor-tile space (Godot world units); the camera shows
y 0..560.  Painter's order = back-to-front by feet-y (rug always first).

Out: out_image2/klein_room/_compose_preview.png
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
KR = HERE / "out_image2" / "klein_room"
ITEMS = KR / "items"
BARE = KR / "room_bare.png"
OUT = KR / "_compose_preview.png"

W, H = 896, 597          # floor-tile space == Godot world units
CAM_H = 560              # visible camera height (draw a guide line here)

# (item file, centre_x, feet_y, icon_px height, flip_h, flip_v, label)
# feet_y = the floor-contact point (bottom-centre) of the piece, matching
# Prop.gd: node at (x, y), sprite offset (0, -h/2) -> sprite bottom sits on y.
# flip_h mirrors left-right so a canonically-drawn piece faces into the room from
# the opposite wall (left-wall pieces need it); in Godot this is sprite flip_h.
#
# v2 sheet (14 faithful cut-outs re-extracted from room.png):
#   01 wall cabinet  02 bookshelf  03 bed  04 oil lamp(round shade)  05 open book
#   06 wardrobe  07 desk  08 chair  09 stained-glass lamp  10 chimney lamp on stand
#   11 dresser+mirror  12 chest  13 framed picture  14 rug
RUG = ("item_14.png", 448, 505, 210, False, False, "rug")   # drawn first, flat
# Floor-standing + wall-hung furniture, painted back-to-front by feet_y.
PROPS = [
    ("item_13.png", 480, 120, 95,  False, False, "framed picture"), # back wall, hung high
    ("item_01.png", 130, 205, 150, False, False, "wall cabinet"),   # LEFT wall, hung
    ("item_02.png", 320, 235, 250, False, False, "bookshelf"),      # back wall, left-of-centre
    ("item_06.png", 725, 258, 305, False, False, "wardrobe"),       # top-right corner
    ("item_07.png", 150, 360, 215, False, False, "desk"),           # LEFT wall
    ("item_10.png", 615, 360, 150, False, False, "nightstand+lamp"),# right of bed
    ("item_11.png", 810, 365, 215, False, False, "dresser"),        # RIGHT wall (oval mirror)
    ("item_08.png", 250, 455, 175, False, False, "chair"),          # LEFT, faces desk
    ("item_03.png", 448, 455, 300, False, False, "bed"),            # dead centre
    ("item_12.png", 565, 505, 125, False, False, "chest"),          # foot of bed
]
# Accessories that sit ON a piece of furniture -> always drawn last, on top of
# their host (a smaller feet_y would otherwise sort them *behind* it).
ACCESSORIES = [
    ("item_05.png", 150, 300, 55, False, False, "open book"),  # on the desk
    ("item_04.png", 195, 300, 95, False, False, "oil lamp"),   # on the desk
    ("item_09.png", 810, 235, 80, False, False, "table lamp"), # on the dresser
]


def paste_feet(canvas: Image.Image, fp: Path, cx: int, fy: int, icon_px: int,
               fh: bool = False, fv: bool = False) -> None:
    im = Image.open(fp).convert("RGBA")
    if fh:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if fv:
        im = im.transpose(Image.FLIP_TOP_BOTTOM)
    s = icon_px / im.height
    w2, h2 = max(1, round(im.width * s)), max(1, round(im.height * s))
    im2 = im.resize((w2, h2), Image.LANCZOS)
    canvas.alpha_composite(im2, (round(cx - w2 / 2), round(fy - h2)))


def main() -> None:
    canvas = Image.open(BARE).convert("RGBA").resize((W, H), Image.LANCZOS)

    # rug flat on the floor, behind all furniture
    paste_feet(canvas, ITEMS / RUG[0], RUG[1], RUG[2], RUG[3], RUG[4], RUG[5])

    # furniture back-to-front so nearer pieces overlap farther ones
    for fp_name, cx, fy, px, fh, fv, _ in sorted(PROPS, key=lambda r: r[2]):
        paste_feet(canvas, ITEMS / fp_name, cx, fy, px, fh, fv)

    # accessories last, on top of whatever furniture they rest on
    for fp_name, cx, fy, px, fh, fv, _ in ACCESSORIES:
        paste_feet(canvas, ITEMS / fp_name, cx, fy, px, fh, fv)

    # faint guide line at the camera's bottom edge (y=560)
    px = canvas.load()
    for x in range(W):
        if 0 <= CAM_H < H:
            px[x, CAM_H] = (255, 0, 0, 90)

    canvas.convert("RGB").save(OUT)
    print(f"preview -> {OUT}  ({W}x{H}, red line = camera bottom y={CAM_H})")


if __name__ == "__main__":
    main()
