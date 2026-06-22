from PIL import Image, ImageDraw, ImageFont
INV = 1/0.5833                      # scene unit -> image px
im = Image.open("out_image2/klein_room/room_blood.png").convert("RGB")
d = ImageDraw.Draw(im, "RGBA")
try: font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 24)
except Exception: font = ImageFont.load_default()
def box(cx, cy, w, h, color, label):
    x0 = (cx-w/2)*INV; y0 = (cy-h/2)*INV; x1 = (cx+w/2)*INV; y1 = (cy+h/2)*INV
    d.rectangle([x0,y0,x1,y1], outline=color, width=3)
    d.text((x0+3, y0+2), label, fill=color, font=font)
# furniture colliders (cyan)
C=(0,255,255,255)
for cx,cy,w,h,l in [(78,150,155,70,"desk"),(100,212,80,67,"chair"),(216,82,83,105,"shelf"),
    (352,130,105,70,"nstand1"),(390,167,204,265,"BED"),(685,85,174,114,"wardrobe"),
    (833,195,126,134,"dresser"),(515,351,95,85,"nstand2"),(670,336,110,75,"chest")]:
    box(cx,cy,w,h,C,l)
# interactable hotspots (yellow, 80x80 Area2D)
Y=(255,230,0,255)
for cx,cy,l in [(140,170,"NOTE"),(110,360,"GUN"),(775,250,"MIRROR"),(448,572,"DOOR")]:
    box(cx,cy,80,80,Y,l)
# player start (magenta dot)
import math
px,py=415*INV,470*INV
d.ellipse([px-8,py-8,px+8,py+8], fill=(255,0,255,255))
d.text((px+10,py-12),"player", fill=(255,0,255,255), font=font)
im.save("out_image2/klein_room/_collidermap.png")
print("ok")
