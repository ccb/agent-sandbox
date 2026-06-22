from PIL import Image
im = Image.open("out_image2/klein_room/_ingame_blood.png")  # 1280x720
# room spans roughly x 103..1177, y 2..718 at zoom 1.2
room = im.crop((103, 2, 1177, 718)).resize((1074, 716), Image.LANCZOS)
room.save("out_image2/klein_room/_ingame_blood_room.png")
# zoom on player (center-bottom ~ scene (415,470) -> capture px)
# scene->capture: cx = 103 + (sx)*1.2 ; cy = 2 + (sy)*1.2  (since room top-left scene(0,0)=capture(103,2))
def s2c(sx, sy): return (103 + sx*1.2, 2 + sy*1.2)
px, py = s2c(415, 470)
pl = im.crop((int(px-90), int(py-150), int(px+90), int(py+40))).resize((360, 380), Image.LANCZOS)
pl.save("out_image2/klein_room/_ingame_blood_player.png")
print("player capture px", px, py)
