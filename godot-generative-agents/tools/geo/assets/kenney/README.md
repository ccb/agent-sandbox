# Kenney RPG Urban Pack (CC0)

`tilemap_packed.png` is the packed tilesheet from Kenney's **RPG Urban Pack**
— 486 tiles, 16×16, no spacing (27 columns × 18 rows, 432×288 px).

- **Source:** https://kenney.nl/assets/rpg-urban-pack
  (mirror: https://opengameart.org/content/rpg-urban-pack)
- **License:** **CC0 1.0** (public domain). Attribution is appreciated but not
  required: "Credit Kenney.nl or www.kenney.nl".

CC0 is why this pack is committed here and used to **bake** real tiles into the
generated maps (`osm_to_tiled.py --theme urban`): unlike the Cute Fantasy pack
(non-commercial, no-redistribute), CC0 art is free to redistribute and derive.

The converter references this sheet whole as the Tiled tileset; the six map
categories map to tiles in it via `URBAN_TILES` in `osm_to_tiled.py`
(index = row × 27 + col). Current picks: ground=38, grass=6, water=61, path=87,
road=461, building=18.
