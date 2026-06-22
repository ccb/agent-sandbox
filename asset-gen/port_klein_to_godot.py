#!/usr/bin/env python3
"""Copy the approved v2 Klein cut-outs + bare-room backdrop into the Godot project.

Build step (no API cost): takes the offline-composed v2 assets from
out_image2/klein_room/ and drops the *finished* PNGs into tingen/assets/ under
the names IntroRoom.tscn references.  Keeps generation assets OUTSIDE tingen/ --
only the final PNGs are copied in.

  - room_bare.png  -> assets/tiles/klein_floor.png   (resized to the 896x597 tile)
  - items/item_##.png -> assets/props/klein_*.png     (per ITEM_MAP below)

The June-9 regen of items_sheet.png (sliced via slice_klein_rembg.py) yielded 11
pieces and — unlike the earlier sheet — NO standalone bookshelf and NO wall cabinet,
so klein_bookshelf.png / klein_cabinet.png from the prior run are left untouched
(same warm Victorian palette).  The 2nd (chimney) oil lamp item_09 is unused for now
(IntroRoom has a single Lamp prop).

Also prints the Rug Sprite2D transform (it can't use the Prop feet-anchor because
a rug must Y-sort BEHIND all furniture, so it's a plain Sprite2D at position.y=0).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
KR = HERE / "out_image2" / "klein_room"
ITEMS = KR / "items"
BARE = KR / "room_bare.png"

GODOT = HERE.parent / "tingen"
PROPS = GODOT / "assets" / "props"
TILES = GODOT / "assets" / "tiles"

TILE_W, TILE_H = 896, 597     # wood_floor_tileset.tres region/tile size

# June-9 rembg slice order -> destination filename in assets/props/.
ITEM_MAP = {
    "item_04.png": "klein_bed.png",         # carved bed, green-tan quilt + pillows
    "item_02.png": "klein_desk.png",        # writing desk (lamp + open book baked on)
    "item_05.png": "klein_lamp.png",        # gourd oil lamp, rounded glass shade
    "item_01.png": "klein_chair.png",       # slatted-back wooden chair
    "item_03.png": "klein_wardrobe.png",    # tall two-door wardrobe
    "item_06.png": "klein_nightstand.png",  # nightstand with a drawer
    "item_10.png": "klein_vanity.png",      # dresser with oval swivel mirror
    "item_08.png": "klein_chest.png",       # low wooden chest / trunk
    "item_11.png": "klein_picture.png",     # framed wall picture / panel
    "item_07.png": "klein_rug.png",         # patterned rug
    # item_09 = 2nd (chimney) oil lamp -> unused; bookshelf/cabinet kept from prior run
}


def main() -> None:
    assert BARE.exists(), f"missing {BARE}"
    PROPS.mkdir(parents=True, exist_ok=True)
    TILES.mkdir(parents=True, exist_ok=True)

    # 1) bare room -> floor tile (exact tile size so the single 0:0 cell fills it)
    bare = Image.open(BARE).convert("RGB").resize((TILE_W, TILE_H), Image.LANCZOS)
    floor_dst = TILES / "klein_floor.png"
    bare.save(floor_dst)
    print(f"floor  {BARE.name} -> {floor_dst.relative_to(GODOT)}  ({TILE_W}x{TILE_H})")

    # 2) cut-outs -> props
    for src_name, dst_name in ITEM_MAP.items():
        src = ITEMS / src_name
        assert src.exists(), f"missing {src}"
        dst = PROPS / dst_name
        shutil.copyfile(src, dst)
        print(f"prop   {src_name} -> {dst.relative_to(GODOT)}")

    # 3) Rug transform (Sprite2D at position.y=0 so it sorts to the very back).
    #    We want the rug texture centred on screen at (448, 400), height 210px.
    rug = Image.open(ITEMS / "item_07.png")
    scale = 210.0 / rug.height
    offset_y = round(400.0 / scale, 1)
    print("\nRug Sprite2D (paste into IntroRoom.tscn):")
    print(f"  position = Vector2(448, 0)")
    print(f"  scale    = Vector2({scale:.4f}, {scale:.4f})")
    print(f"  offset   = Vector2(0, {offset_y})   # rug img {rug.width}x{rug.height}")


if __name__ == "__main__":
    main()
