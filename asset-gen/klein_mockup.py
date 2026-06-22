#!/usr/bin/env python3
"""Composite the LOCKED V1 dense cozy-chibi Klein into the real in-game room
(room_blood.png) at the player's spawn point, so Mark can judge the look + scale
in context.  Produces both the crisp master (idealized) and the true low-res 96px
in-game sprite (what actually renders), and saves clean trimmed asset files.

Scale math: RoomPhoto is drawn non-centered at 0.5833, so scene_units = image_px *
0.5833  ->  image_px = scene_units * 1.714.  Player spawns at scene (415, 470).

Out: out_image2/klein_chibi/_in_room_raw.png, _in_room_px.png,
     klein_chibi_master.png (trimmed full-res), klein_chibi_sprite96.png (trimmed px)
"""

from __future__ import annotations

from PIL import Image

import generate_tingen_image2 as g
from klein_char_experiment import pixelize

CHIBI = g.OUT_DIR / "klein_chibi"
ROOM = g.OUT_DIR / "klein_room" / "room_blood.png"
V1 = CHIBI / "V1_dense_chibi.png"

SCENE_TO_PX = 1.0 / 0.5833  # ~1.714
FEET = (415.0, 502.0)  # player spawn (scene units), feet on the floor
HEIGHT_UNITS = 92.0  # Klein's on-screen height in scene units (a bit > the old 69)
SPRITE_H = 96  # low-res in-game pixel height


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def place(room: Image.Image, spr: Image.Image, resample) -> Image.Image:
    target_px = round(HEIGHT_UNITS * SCENE_TO_PX)
    w = max(1, round(spr.width * target_px / spr.height))
    spr2 = spr.resize((w, target_px), resample)
    cx = round(FEET[0] * SCENE_TO_PX)
    feet_y = round(FEET[1] * SCENE_TO_PX)
    out = room.copy()
    out.alpha_composite(spr2, (cx - spr2.width // 2, feet_y - spr2.height))
    return out


def main() -> None:
    room = Image.open(ROOM).convert("RGBA")
    print(
        f"  room {room.size}  feet(px)=({round(FEET[0]*SCENE_TO_PX)},"
        f"{round(FEET[1]*SCENE_TO_PX)})  klein_h(px)={round(HEIGHT_UNITS*SCENE_TO_PX)}"
    )

    raw = trim(Image.open(V1).convert("RGBA"))
    px = trim(pixelize(V1, target_h=SPRITE_H, colors=48))

    # clean game-ready assets
    raw.save(CHIBI / "klein_chibi_master.png")
    px.save(CHIBI / "klein_chibi_sprite96.png")
    print(f"  master {raw.size} -> klein_chibi_master.png")
    print(f"  sprite {px.size} -> klein_chibi_sprite96.png")

    place(room, raw, Image.LANCZOS).save(CHIBI / "_in_room_raw.png")
    place(room, px, Image.NEAREST).save(CHIBI / "_in_room_px.png")
    print("  mockups -> _in_room_raw.png (crisp), _in_room_px.png (true low-res)")


if __name__ == "__main__":
    main()
