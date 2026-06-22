from PIL import Image
im = Image.open("out_image2/klein_room/_scenegrid.png")
W, H = im.size
# 2x2 quadrants, upscale 1.4x for readability
quads = {"TL": (0,0,W//2,H//2), "TR": (W//2,0,W,H//2),
         "BL": (0,H//2,W//2,H), "BR": (W//2,H//2,W,H)}
for name,(x0,y0,x1,y1) in quads.items():
    c = im.crop((x0,y0,x1,y1))
    c = c.resize((int(c.width*1.4), int(c.height*1.4)), Image.LANCZOS)
    c.save(f"out_image2/klein_room/_q_{name}.png")
print("ok")
