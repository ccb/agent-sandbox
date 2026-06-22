# Generating the Tingen Map — End-to-End Tutorial

How the Tingen city map was made with **gpt-image-1**, from a blank prompt to the
two production layers the game actually uses:

1. **The labeled overview map** (`map_v3.png`) — the look-at / fast-travel map.
2. **The bare ground** (`map_bg.png`) — the walkable floor, with buildings stripped,
   onto which individual building sprites (e.g. `St_Selena_Chapel`) are stamped.

Everything runs through `generate_tingen_image2.py` (the gpt-image-1 pipeline) or the
same OpenAI Images API called directly. Hand-made layers live in `my_assets/`.

---

## 0. Setup

```bash
pip install requests pillow
export OPENAI_API_KEY=sk-...        # or put OPENAI_API_KEY=... in the .env the script reads
```

Two endpoints, picked automatically by whether you pass a reference image:

| Endpoint | When | Body |
|---|---|---|
| `POST /v1/images/edits` | you have a reference image | **multipart**, `image[]=@ref.png` |
| `POST /v1/images/generations` | no reference | **JSON** |

gpt-image-1 has **no seed**. The *only* levers for consistency are (a) the reference
image(s) and (b) `input_fidelity` (`low`|`high`). Burn this into your brain — it drives
every step below.

Cost (approx): `low` ~$0.02 · `medium` ~$0.05 · `high` ~$0.25 per image. Draft on `low`,
finalize on `high`.

---

## 1. Generate the base district map

### The hard problem
A prompt asking for a "top-down map" **always drifts to a ¾/oblique angle** — we tried 7
style variants and every one came out tilted. Prose alone cannot hold a true 90° overhead.

### The fix: a flat reference at `input_fidelity=high`
Feed a flat-overhead image (here `ref/tingen_map.png`) as the reference and set
`input_fidelity=high`. High fidelity **locks the straight-down angle** to the reference.
This is the `district_flat` treatment in the pipeline.

> Trade-off: high fidelity also tends to inherit the reference's **palette and contrast**.
> See Step 2 — that's exactly the contrast fight.

### Via the pipeline
```bash
python3 generate_tingen_image2.py \
  --category backgrounds --treatment district_flat \
  --only oldtown_core_flat3 --quality high
```
Output → `out_image2/backgrounds/oldtown_core_flat3.png`, logged in `manifest_image2.json`.
Add `--dry-run` to preview the plan (no spend), `--force` to regenerate over an existing file.

### The raw API call (what the pipeline does under the hood)
```bash
curl https://api.openai.com/v1/images/edits \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F model=gpt-image-1 \
  -F 'image[]=@ref/tingen_map.png;type=image/png' \
  -F size=1536x1024 \
  -F quality=high \
  -F background=opaque \
  -F output_format=png \
  -F input_fidelity=high \
  -F n=1 \
  -F prompt="a large highly detailed city district map seen from directly straight above at a TRUE flat 90-degree birds-eye angle ... only rooftops and streets seen flat from above, NO perspective, NO tilt, NO isometric angle, NO building fronts ..."
```
The response is base64 PNG:
```python
import base64, requests
r = requests.post(... )                       # as above
png = base64.b64decode(r.json()["data"][0]["b64_json"])
open("oldtown_core_flat3.png", "wb").write(png)
```
Ref-less version (no `image[]`, JSON body, hits `/v1/images/generations`):
```bash
curl https://api.openai.com/v1/images/generations \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"gpt-image-1","prompt":"...","size":"1536x1024","quality":"high","background":"opaque","output_format":"png","n":1}'
```

---

## 2. Polish with image2 (iterate on the prompt)

The first flat map came out a **monochrome orange wash** — "the contrast is very broken."
Cause: the high-fidelity reference + a global "golden daylight" instruction collapsed
streets and roofs to one mid-orange value.

**The contrast fix that worked** — force a light-vs-dark split *in the prompt*:

- **Streets:** PALE, almost-white, cool-grey paving — explicitly *not* golden/amber/orange,
  and *lighter than every roof*.
- **Roofs:** a vivid **patchwork** — warm terracotta/brick-red placed right next to dark
  charcoal-slate / near-black / blue-grey, plus verdigris teal and green gardens, so any two
  adjacent buildings differ sharply in **both hue and brightness**.
- Add the negative list: `NOT a monochrome wash, NOT one hue, NOT one brightness, NOT hazy,
  NOT low-contrast`.

This lives in `BG_DISTRICT_FLAT` in the script. Iterate by editing that string and re-running
with `--force --quality low` until the composition reads, then one final `--quality high`.

> No seed means each run differs. Keep the reference + `input_fidelity=high` constant so the
> *layout* stays stable while you tune the palette wording.

---

## 3. Relabel place names to Tingen canon

The generated map has fictional/garbled labels. Relabel them to canon (Iron Cross Market,
Saint Selena's Cathedral, Blackthorn Security Co., The Laughing Eel, the Docks, …).

### Image-to-image relabel (same `/v1/images/edits` call)
Pass the **map itself** as the reference at `input_fidelity=high` so the art/layout is
preserved, and instruct it to change *only* the labels:
```bash
curl https://api.openai.com/v1/images/edits \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F model=gpt-image-1 -F 'image[]=@map_v2.png;type=image/png' \
  -F size=1536x1024 -F quality=high -F input_fidelity=high -F output_format=png -F n=1 \
  -F prompt="Keep this exact map — same style, same layout, same top-down angle. Change ONLY the text labels to: Iron Cross Market, The Laughing Eel, Saint Selena's Cathedral, ... Spell every label exactly as written. Make no other changes."
```

### ⚠ The text caveat
AI image tools **garble lettering** (our first map literally produced "GREENMARKET SQUARK").
For a handful of district labels this is unreliable. Two safer routes:
- **Label at the district level only** (~5 names), then fix spelling by hand.
- **Generate the map label-free** and add the text yourself in Preview / Photopea (sharp,
  correct, free). This is the recommended route for final art.

Verify names against canon in `tingen_npc_roster.md` / `tingen_mystery_pixel_game_gdd.md §6.2`
before baking them in (e.g. the Cathedral and the Docks are *separate districts* from Iron Cross).

---

## 4. "Scrape" the buildings → bare ground

The walkable layer needs the **streets only**, with buildings removed, so building sprites can
be stamped on top (Step 5). Two ways:

**A. API edit (strip in place).** Feed the labeled/clean map as the reference at
`input_fidelity=high` (to keep the exact street geometry) and prompt the removal:
```bash
curl https://api.openai.com/v1/images/edits \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F model=gpt-image-1 -F 'image[]=@map_v3.png;type=image/png' \
  -F size=1254x1254 -F quality=high -F input_fidelity=high -F output_format=png -F n=1 \
  -F prompt="Remove ALL buildings, rooftops and labels. Keep ONLY the cobblestone streets, lanes, squares and the empty ground lots between them, in the exact same layout. Flat top-down. Empty paved/dirt lots where buildings were."
```
→ `map_bg.png` (the bare ground). This is what's in `my_assets/map_bg.png`.

**B. ChatGPT image UI.** The same edit can be done in the ChatGPT image tool by uploading the
map and asking to remove buildings — that's how the current `map_bg.png` was produced. Same
model, just a different front-end.

> The empty lots don't need much detail: in the final scene they're covered by building
> sprites. The bare ground really only needs to read as **streets**.

---

## 5. Extract building sprites + compose the walkable scene

Each building is a **self-contained iso compound** (the building + its immediate grounds, e.g.
`St_Selena_Chapel_v2.png` = church + churchyard + fence).

### Key out the background → transparent PNG
Building sprites often arrive on a solid white background (no alpha). Flood-fill from the
corners (preserves white *inside* the building) and autocrop:
```python
from PIL import Image, ImageDraw
im = Image.open("my_assets/St_Selena_Chapel_v2.png").convert("RGB")
w, h = im.size
SENT = (255, 0, 255)
for c in [(0,0),(w-1,0),(0,h-1),(w-1,h-1),(w//2,0),(w//2,h-1),(0,h//2),(w-1,h//2)]:
    ImageDraw.floodfill(im, c, SENT, thresh=45)        # flood the connected white bg
rgba = im.convert("RGBA"); px = rgba.load()
for y in range(h):
    for x in range(w):
        r,g,b,_ = px[x,y]
        if (r,g,b) == SENT or min(r,g,b) >= 240:        # bg + enclosed near-white gaps
            px[x,y] = (0,0,0,0)
rgba.crop(rgba.getbbox()).save("tingen/assets/props/chapel.png")
```

### Compose in Godot
- **Ground:** `map_bg.png` as a `Sprite2D`, `scale ≈ 5`, `texture_filter = 2` (Linear, smooth
  upscale of painted art).
- **Building:** the keyed sprite, stamped on a lot, `texture_filter = 2`.
- **Klein:** `klein_down.png` at `scale 0.069`, `offset (0,-470)`; camera `zoom ≈ 1.5`.
- Keep the camera at **gameplay zoom** — the iso-building-on-top-down-ground angle mismatch
  only shows when zoomed out, so use the labeled `map_v3.png` as the separate overview map and
  never show the wide composite.
- Still TODO per building: collision (footprint + fence), and Y-sort so Klein hides behind it.

**Angle rule:** every building sprite must be drawn at the **same iso angle** and a fixed
Klein-to-doorway scale, or they won't sit together.

---

## File map

| File | Role |
|---|---|
| `generate_tingen_image2.py` | the gpt-image-1 pipeline (Steps 1–2) |
| `ref/tingen_map.png` | flat-overhead reference that locks the 90° angle |
| `out_image2/backgrounds/*` | generated maps + manifest |
| `my_assets/map_v3.png` | labeled overview map (Step 3) |
| `my_assets/map_bg.png` | bare ground / walkable floor (Step 4) |
| `my_assets/St_Selena_Chapel_v2.png` | example building compound (Step 5) |

---

### TL;DR
flat ref + `input_fidelity=high` to lock the 90° angle → tune palette (pale streets vs
patchwork roofs) for contrast → relabel to canon (prefer manual text) → edit-strip the
buildings to get `map_bg` → key building sprites transparent and stamp them on the ground in
Godot at a locked iso angle, camera held at gameplay zoom.
