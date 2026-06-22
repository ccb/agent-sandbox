# assets/

Drop-in target for the generated pixel-art library (produced by
`../asset-gen/generate_tingen_assets.py` → `../asset-gen/out/{category}/`).

Folders mirror the asset-gen categories: `characters/`, `props/`, `tiles/`,
`ui/`, `portraits/`, `backgrounds/`, `enemies/`.

Until real art lands, every sprite in the scenes is a **stub**: the default
Godot `icon.svg` tinted per-entity via the node's `modulate`, and floors/walls
are solid `Polygon2D` rectangles. To swap in real art, copy the PNGs here and
repoint each `Sprite2D.texture` (e.g. the player to
`assets/characters/player_detective_0.png`). Set the texture filter to
**Nearest** so the 384px pixel art stays crisp.
