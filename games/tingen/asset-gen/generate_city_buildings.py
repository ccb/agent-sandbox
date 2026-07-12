#!/usr/bin/env python3
"""
Tingen city-map building sprite generator — gpt-image-1.

Per MAP_TUTORIAL.md Step 3b: for each canon building on my_assets/map_v3.png,
crop the labeled block as a CONTENT reference, pass the finished chapel
(my_assets/St_Selena_Chapel_v2.png) as the STYLE/angle anchor, and ask for a
single detailed iso building compound on a plain white background. The result
is then keyed transparent with key_building.py (KEY -> ERODE -> BLEED, autocrop).

Endpoint: POST /v1/images/edits (multipart, image[] refs). input_fidelity is
left LOW on purpose — high fidelity would lock the flat top-down angle of the
map crop; we want the 3/4 iso angle of the chapel anchor.

Usage:
  python3 generate_city_buildings.py --env-file '/path/to/.env' --dry-run
  python3 generate_city_buildings.py --env-file '...' --only laughing_eel --quality medium
  python3 generate_city_buildings.py --env-file '...' --quality high            # everything missing
  python3 generate_city_buildings.py --env-file '...' --only laughing_eel --force --suffix _v2

A running image count is kept in out_image2/buildings/_budget.json — the script
refuses to start a call beyond --budget-cap (default 40).
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import requests
from PIL import Image

HERE = Path(__file__).resolve().parent
MAP = HERE / "my_assets" / "map_v3.png"
STYLE_ANCHOR = HERE / "my_assets" / "St_Selena_Chapel_v2.png"
OUT = HERE / "out_image2" / "buildings"
CROPS = OUT / "crops"
KEYED = OUT / "keyed"
BUDGET_FILE = OUT / "_budget.json"
KEY_SCRIPT = HERE / "key_building.py"
API_EDITS = "https://api.openai.com/v1/images/edits"

CROP_SZ = 400  # px square cropped from the 1254x1254 map around each label

# name -> (label center on map_v3.png, building description for the prompt)
BUILDINGS: dict[str, tuple[tuple[int, int], str]] = {
    "laughing_eel": (
        (428, 694),
        "The Laughing Eel, a shabby three-storey corner tavern of soot-stained "
        "brick with a steep slate roof, chimney pots, a hanging blank pub sign, "
        "small warm-lit windows and a worn cobbled forecourt with a few barrels",
    ),
    "iron_cross_market": (
        (627, 610),
        "Iron Cross Market, an open cobbled market square: a tight cluster of "
        "weathered wooden market stalls with patched canvas awnings, crates, "
        "barrels, sacks and a hand-cart, ringed by a low kerb — an open plaza "
        "of stalls rather than one building",
    ),
    "raphael_cemetery": (
        (445, 1160),
        "Raphael Cemetery, a walled graveyard compound: a low aged stone "
        "perimeter wall with a wrought-iron entrance gate, rows of weathered "
        "headstones, a small mausoleum, bare trees and overgrown grass paths",
    ),
    "selena_almshouse": (
        (560, 209),
        "Selena's Almshouse, a long plain charitable brick almshouse of two "
        "storeys with a grey slate roof, regular rows of small windows, a "
        "modest arched entrance and a small bare front yard with a low fence",
    ),
    "tingen_docks": (
        (110, 1024),
        "Tingen Docks, a dockside compound: a large timber-and-brick dock "
        "warehouse with a gabled roof and hoist beam, standing on a stone quay "
        "edge with a short wooden pier, mooring bollards, coiled rope, crates "
        "and barrels at the water's edge",
    ),
    "river_wharves": (
        (1114, 1091),
        "the River Wharves, a row of two long low wharf sheds with rusted "
        "corrugated and tarred plank roofs on a stone quayside, open loading "
        "bays, stacked crates, barrels and a small dockside crane",
    ),
    "police_station": (
        (763, 811),
        "Tingen Police Station, a sturdy civic station house of grey stone and "
        "dark brick, two storeys, a hipped slate roof, a lamp over the arched "
        "entrance, barred ground-floor windows and a small walled side yard",
    ),
    "mr_frankys": (
        (951, 658),
        "Mr. Franky's, a narrow cramped Victorian lodging house of four "
        "storeys, grimy brick, mismatched patched roofs, crooked chimney pots, "
        "washing lines, a worn stoop and a small rubbish-strewn back yard",
    ),
    "coal_yard": (
        (199, 130),
        "the Coal Yard, an open industrial yard: large black coal heaps, a "
        "plank fence around the lot, a small brick weigh-shed with a sloped "
        "roof, a loading chute, a coal cart and scattered coal dust",
    ),
    "ironworks": (
        (1056, 136),
        "Mather & Son Ironworks, a heavy brick factory compound with a long "
        "gabled workshop hall, two tall smoking brick chimneys, a water tank, "
        "skylights, and a cluttered work yard with iron stock and carts",
    ),
    "globe_works": (
        (88, 610),
        "Globe Works, a mid-sized Victorian workshop factory: a long two-storey "
        "brick works building with a sawtooth and gabled roof, one smoking "
        "chimney stack, large workshop windows and a small gated work yard",
    ),
    # generic filler row-house variants (refs are unlabeled residential blocks)
    "rowhouse_a": (
        (500, 420),
        "a terrace block of dense soot-stained red-brick Victorian row houses, "
        "three storeys, steep dark slate roofs, many chimney pots, small sash "
        "windows, worn doorsteps along a cobbled pavement",
    ),
    "rowhouse_b": (
        (850, 950),
        "a terrace block of grimy working-class Victorian tenement houses, "
        "brown brick with faded painted shopfronts at the corner, patched "
        "slate roofs, chimney pots and washing strung between back yards",
    ),
    "rowhouse_c": (
        (300, 560),
        "a short terrace of weathered grey-and-red brick Victorian row houses "
        "with mixed roof heights, gabled dormers, chimney pots and tiny walled "
        "back yards with privies",
    ),
}

PROMPT_TMPL = (
    "A detailed hand-painted top-down three-quarter isometric view of {desc}, "
    "in a late Victorian Britain working-class district, muted industrial "
    "palette, soot-stained brick, aged stone, overcast British daylight, low "
    "saturation, subtle atmospheric grime. The first reference image is a crop "
    "of the city map showing this exact building block — stay true to its "
    "footprint, layout and rooflines. The second reference image is a finished "
    "building sprite from the same game: match its painting style, level of "
    "detail, camera angle and palette exactly, but depict THIS building, not a "
    "church. Single building compound only (the building plus its immediate "
    "grounds), centered, completely isolated on a plain pure-white background, "
    "no surrounding streets or neighbouring buildings, no people, no text, no "
    "lettering, no signage writing, no labels, no watermark, no frame."
)


def load_key(env_file: Path) -> str | None:
    import os

    k = os.environ.get("OPENAI_API_KEY")
    if k:
        return k.strip()
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == "OPENAI_API_KEY":
                return val.strip().strip('"').strip("'")
    except OSError as e:
        print(f"ERROR: cannot read env file {env_file}: {e}")
    return None


def make_crop(name: str, center: tuple[int, int]) -> Path:
    CROPS.mkdir(parents=True, exist_ok=True)
    dst = CROPS / f"{name}.png"
    im = Image.open(MAP)
    w, h = im.size
    cx, cy = center
    l = max(0, min(w - CROP_SZ, cx - CROP_SZ // 2))
    t = max(0, min(h - CROP_SZ, cy - CROP_SZ // 2))
    im.crop((l, t, l + CROP_SZ, t + CROP_SZ)).save(dst)
    return dst


def budget_used() -> int:
    if BUDGET_FILE.exists():
        return json.loads(BUDGET_FILE.read_text()).get("images", 0)
    return 0


def budget_add(n: int = 1) -> int:
    used = budget_used() + n
    BUDGET_FILE.write_text(json.dumps({"images": used}))
    return used


def generate_one(key: str, name: str, desc: str, crop: Path, quality: str) -> bytes | None:
    prompt = PROMPT_TMPL.format(desc=desc)
    files = [
        ("image[]", (crop.name, crop.read_bytes(), "image/png")),
        ("image[]", (STYLE_ANCHOR.name, STYLE_ANCHOR.read_bytes(), "image/png")),
    ]
    data = {
        "model": "gpt-image-1",
        "prompt": prompt,
        "size": "1536x1024",
        "quality": quality,
        "background": "opaque",
        "output_format": "png",
        "n": "1",
    }
    for attempt in range(4):
        try:
            resp = requests.post(
                API_EDITS,
                headers={"Authorization": f"Bearer {key}"},
                files=files,
                data=data,
                timeout=400,
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            wait = 5 * (attempt + 1)
            print(f"    network error ({e}) — waiting {wait}s")
            time.sleep(wait)
            continue
        if resp.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"    rate limited — waiting {wait}s")
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            print(f"    ERROR {resp.status_code}: {resp.text[:300]}")
            if resp.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            return None
        try:
            b64 = resp.json()["data"][0]["b64_json"]
        except (KeyError, IndexError, ValueError) as e:
            print(f"    ERROR parsing response: {e}")
            return None
        return base64.b64decode(b64)
    print("    ERROR: retries exhausted")
    return None


def key_out(src: Path, name: str) -> Path | None:
    """Run key_building.py; if the source already has alpha, flatten to white first."""
    KEYED.mkdir(parents=True, exist_ok=True)
    im = Image.open(src)
    if im.mode in ("RGBA", "LA") and im.getextrema()[-1][0] < 255:
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im.convert("RGBA"), (0, 0), im.convert("RGBA"))
        src = src.with_name(src.stem + "_white.png")
        flat.save(src)
    out = KEYED / f"{name}.png"
    r = subprocess.run(
        [sys.executable, str(KEY_SCRIPT), str(src), str(out), "--white", "222", "--erode", "2"],
        capture_output=True,
        text=True,
    )
    print("    " + (r.stdout.strip() or r.stderr.strip()))
    return out if r.returncode == 0 else None


def verify(path: Path) -> str:
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    corners = [im.getpixel(p)[3] for p in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]]
    alpha_ok = all(a == 0 for a in corners)
    bbox = im.getbbox()
    frac = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / (w * h) if bbox else 0
    return f"{w}x{h} corners_transparent={alpha_ok} bbox_frac={frac:.2f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, help="comma-separated building names")
    ap.add_argument("--quality", choices=["low", "medium", "high"], default="high")
    ap.add_argument("--env-file", type=Path, required=False,
                    default=Path("/Users/markma/Desktop/Yumina Master/yumina/.env"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--suffix", type=str, default="", help="output name suffix (iteration)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--budget-cap", type=int, default=40)
    ap.add_argument("--no-key", action="store_true", help="skip key_building step")
    args = ap.parse_args()

    names = list(BUILDINGS)
    if args.only:
        names = [n.strip() for n in args.only.split(",")]

    key = None
    if not args.dry_run:
        key = load_key(args.env_file)
        if not key:
            print("ERROR: OPENAI_API_KEY not found")
            sys.exit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(names, 1):
        if name not in BUILDINGS:
            print(f"  [{i}/{len(names)}] {name}: unknown, skipped")
            continue
        center, desc = BUILDINGS[name]
        raw = OUT / f"{name}{args.suffix}.png"
        print(f"  [{i}/{len(names)}] {name} -> {raw.name} (q={args.quality})")
        if raw.exists() and not args.force:
            print("    exists, skipping generation")
        else:
            if args.dry_run:
                print(f"    would call edits; prompt: {PROMPT_TMPL.format(desc=desc)[:120]}...")
                continue
            used = budget_used()
            if used >= args.budget_cap:
                print(f"    BUDGET CAP hit ({used}/{args.budget_cap}) — stopping")
                break
            crop = make_crop(name, center)
            t0 = time.time()
            img = generate_one(key, name, desc, crop, args.quality)
            if not img:
                print("    FAILED")
                continue
            raw.write_bytes(img)
            used = budget_add()
            print(f"    OK ({len(img)//1024}KB, {round(time.time()-t0)}s) budget={used}/{args.budget_cap}")
        if not args.no_key and not args.dry_run:
            keyed = key_out(raw, f"{name}{args.suffix}")
            if keyed:
                print(f"    keyed: {verify(keyed)}")

    print(f"\nTotal API images used so far: {budget_used()}")


if __name__ == "__main__":
    main()
