"""Overlay a SCENE-coordinate grid on room_blood.png so I can read furniture
footprints directly in Godot scene units. image_px * 0.5833 = scene unit.
Grid lines every 64 scene units; labels every 128 scene units."""
from PIL import Image, ImageDraw, ImageFont
S = 0.5833            # image_px -> scene unit
INV = 1.0 / S         # scene unit -> image_px
im = Image.open("out_image2/klein_room/room_blood.png").convert("RGB")
W, H = im.size        # 1536 x 1024
d = ImageDraw.Draw(im)
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 22)
except Exception:
    font = ImageFont.load_default()
# vertical lines at scene x = 0,64,128...
sx = 0
while sx * INV <= W:
    px = int(sx * INV)
    col = (0, 255, 255) if sx % 128 == 0 else (0, 140, 140)
    d.line([(px, 0), (px, H)], fill=col, width=1 if sx % 128 else 2)
    if sx % 128 == 0:
        d.text((px + 2, 2), str(sx), fill=(255, 255, 0), font=font)
    sx += 64
sy = 0
while sy * INV <= H:
    py = int(sy * INV)
    col = (0, 255, 255) if sy % 128 == 0 else (0, 140, 140)
    d.line([(0, py), (W, py)], fill=col, width=1 if sy % 128 else 2)
    if sy % 128 == 0:
        d.text((2, py + 2), str(sy), fill=(255, 255, 0), font=font)
    sy += 64
im.save("out_image2/klein_room/_scenegrid.png")
print(f"image {W}x{H} -> scene {round(W*S)}x{round(H*S)}")
