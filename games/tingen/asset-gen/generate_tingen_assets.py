#!/usr/bin/env python3
"""
Tingen Asset Generator
======================
Generates the vertical-slice pixel-art asset library for the Tingen Mystery
game via Replicate's Retro Diffusion models (same pipeline Yumina uses).

Outputs to:  asset-gen/out/{category}/{name}_{variant}.png   (OUTSIDE tingen/ Godot project)

Every prompt / style / palette here derives from STYLE_GUIDE.md (the single
source of truth, grounded in Lord of the Mysteries canon).

Models:
  - retro-diffusion/rd-fast  -> sprites, portraits, enemies, vfx (384px, alpha)
  - retro-diffusion/rd-plus  -> props, tiles, backgrounds, ui    (384px)
  NOTE: both models hard-cap width/height at 384px. For larger in-game assets,
  scale up with crisp nearest-neighbor (in Godot set texture filter = nearest).

Real Retro Diffusion levers (confirmed from the model schema):
  style preset, seed, width/height, remove_bg, tile_x, tile_y,
  bypass_prompt_expansion, input_palette, strength, input_image.
  (There is NO negative_prompt / guidance_scale / steps on these models.)

Token:
  Reads REPLICATE_API_TOKEN from the environment, else from --env-file
  (default: the Yumina repo .env). The token value is never printed.

Usage:
  python3 generate_tingen_assets.py --test                 # round-1 representative slice
  python3 generate_tingen_assets.py --dry-run              # print plan, no API calls
  python3 generate_tingen_assets.py                        # full curated inventory
  python3 generate_tingen_assets.py --category characters  # one category
  python3 generate_tingen_assets.py --limit 2              # cap items/category (testing)

Cost: rd-fast ~$0.003/img, rd-plus ~$0.01/img. Full inventory ~$0.65.

Requires: pip install requests
"""

from __future__ import annotations  # 3.9-safe PEP 604 "X | None" annotations

import os
import sys
import json
import time
import zlib
import argparse
import requests
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "out"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
DEFAULT_ENV_FILE = Path("/Users/markma/Desktop/Yumina/.env")

MODEL_FAST = "retro-diffusion/rd-fast"   # sprites / portraits / enemies / vfx  (alpha)
MODEL_PLUS = "retro-diffusion/rd-plus"   # props / tiles / backgrounds / ui

# ── Shared prompt scaffolds (STYLE_GUIDE.md §7) ────────────────
# Full aesthetic scaffold appended to every CHARACTER / SCENE prompt so the
# whole set reads as one world: gaslit Victorian gloom + saturated occult.
TINGEN_STYLE = (
    "pixel art, late-Victorian gaslamp fantasy, occult-detective mystery, "
    "muted desaturated fog-gray palette with warm gaslight accents, "
    "atmospheric, moody, readable silhouette, 1890s Loen, steampunk edge, "
    "NOT modern, NOT 1930s noir"
)
# Tiles get their own lean scaffold (no character/silhouette words that confuse a texture).
TILE_STYLE = (
    "pixel art, muted desaturated palette, seamless tileable flat ground texture, "
    "top-down, evenly lit, no objects, no characters, no buildings, no lighting effects"
)
VFX_STYLE = (
    "pixel art, single isolated visual effect, centered on solid black background, "
    "no scenery, no buildings, no objects, no landscape, no street"
)
# Backgrounds are walkable game maps, NOT eye-level establishing shots: inclined
# three-quarter top-down (Stardew Valley look) — ground seen from above, objects
# and building fronts standing upright toward the camera.
BG_STYLE = (
    "pixel art, top-down RPG game map, inclined three-quarter top-down perspective "
    "like Stardew Valley, late-Victorian gaslamp occult-detective mood, "
    "muted desaturated fog-gray palette with warm gaslight accents, 1890s Loen"
)

# Humans read as pale Victorian Europeans (LotM's Loen ~ a Victorian-British empire);
# the muted/dark palette was crushing faces, so complexion + a lit face are explicit.
SPRITE_SUFFIX   = "full-body game character sprite, single character, idle stance, fills the frame, clean alpha, fair pale Victorian European complexion, face clearly lit by a warm key light, rim light separating the figure from the background, lifted readable midtones, not a pure-black silhouette"
ENEMY_SUFFIX    = "full-body game enemy sprite, single creature, fills the frame, clean alpha, rim light separating the figure from the background, lifted readable midtones, not a pure-black silhouette"
PORTRAIT_SUFFIX = "chest-up three-quarter pixel portrait, dialogue avatar, fair pale Victorian European complexion, face clearly lit by a warm key light, soft muted dark foggy background"
TILE_SUFFIX     = "just the ground surface, repeating texture"
BG_SUFFIX       = "top-down game level map, walkable ground area seen from an inclined overhead angle, buildings and objects drawn upright facing the camera, detailed pixel art tilemap, no eye-level horizon, no sky vista"
SCENE_SUFFIX    = "atmospheric establishing scene, detailed pixel art, volumetric fog, moody cinematic lighting"
PROP_SUFFIX     = "single inventory item, centered, clean edges, neutral background, slight warm rim light"
ICON_SUFFIX     = "clean game UI element, single centered, ornate Victorian brass and ink"
VFX_SUFFIX      = "visual effect sprite on transparent background, centered, glowing"

REPLICATE_API_TOKEN: str | None = None  # set in main()


# ── Tingen vertical-slice inventory (every entry tracks STYLE_GUIDE.md) ──
# Per category: model ("fast"/"plus"), style preset, size, remove_bg, knob flags,
#   variants, suffix, scaffold (optional), items{name: prompt}.
# Seeds are derived per (name, variant) in seed_for() so a character looks the
# same across regenerations and we can re-roll deliberately, not randomly.

CATEGORIES: dict = {
    # ── Named cast + NPC archetypes (overworld sprites) ──
    "characters": {
        "model": "fast", "style": "detailed", "size": 384, "remove_bg": True,
        "variants": 1, "suffix": SPRITE_SUFFIX,
        "items": {
            # PLAYER — canon Klein Moretti (STYLE_GUIDE §5, locked wardrobe).
            "player_detective": (
                "Klein Moretti, young man in his early twenties, pale refined scholarly face, "
                "black hair swept back, luminous glowing gold Beyonder eyes, "
                "wearing a charcoal-black caped Inverness overcoat with a deep violet flaring lining, "
                "white high-collar shirt and dark cravat, dark waistcoat with a pocket-watch chain, "
                "brown leather shoulder-holster strap across the chest with a revolver at the hip, "
                "holding a black cane with an ornate silver handle, black top hat, dark trousers, black boots, "
                "calm composed idle stance leaning on the cane"
            ),
            "nighthawk_captain": "stern Nighthawk investigator captain, long dark double-breasted Inverness coat, brass badge, leather gloves, brass oil lantern, top hat, authoritative bearing",
            "archivist": "elderly university archivist, round brass spectacles, ink-stained scholar's frock coat and waistcoat, clutching an old leather tome",
            "suspect_bieber": "gaunt obsessed ritual scholar, wild bloodshot eyes, dishevelled Victorian suit and waistcoat, gripping a cursed leather notebook",
            "informant": "shifty tavern informant, flat cap, worn wool coat and waistcoat, sly knowing grin",
            "priest": "gaunt cathedral priest, no hood, bareheaded, thinning grey hair, clearly visible pale gaunt lit face, dark grey clerical cassock with a white clerical collar, silver cross pendant, solemn weary expression, lighter grey midtone values, NOT a black hooded silhouette",
            "witness_widow": "grieving widow in a dark grey Victorian mourning gown and lace veil, holding a parasol, face and figure clearly lit, lighter midtone values, NOT a black silhouette, plain background",
            "lady_genteel": "Loen gentlewoman in a faded muted sage-green and cream Victorian bustle gown, white gloves, holding a parasol, blonde hair in an updo, dignified, dull weathered fabric, gritty painterly pixel art, muted desaturated, NOT vibrant, NOT anime, NOT cartoon",
            "npc_investigator": "plainclothes Nighthawk investigator, dark overcoat and waistcoat, top hat, notebook in hand",
            "npc_civilian_man": "ordinary working-class Loen townsman, flat cap, waistcoat, rolled sleeves",
            "npc_civilian_woman": "ordinary Loen townswoman, long skirt, shawl and bonnet, clearly lit, lighter midtone values, NOT a black silhouette",
            "npc_laborer": "weary dockside laborer, rough wool clothes, rolled sleeves, heavy boots",
            "npc_constable": "uniformed Loen city constable, tall custodian helmet, caped greatcoat, truncheon",
            "npc_dockworker": "burly dockworker, oilskin coat and cap, coiled rope over the shoulder",
            "npc_drunkard": "stumbling drunkard in shabby Victorian clothes, bottle in hand, dishevelled",
            "npc_street_urchin": "ragged street urchin child, oversized patched coat, flat cap, barefoot",
            "npc_cultist_hidden": "ordinary Loen citizen with a faint unsettling stare, concealed cultist, plain coat",
        },
    },
    # ── Dialogue portraits for the named cast ──
    "portraits": {
        "model": "fast", "style": "portrait", "size": 384, "remove_bg": True,
        "variants": 1, "suffix": PORTRAIT_SUFFIX,
        "items": {
            "portrait_player": (
                "Klein Moretti, pale composed scholarly face, black hair swept back, "
                "striking bright yellow-gold eyes, golden iris color, "
                "charcoal-black high-collar overcoat with deep violet lining, "
                "white collar and dark cravat, brooding controlled expression"
            ),
            "portrait_captain": "stern Nighthawk captain, weathered face, brass-badged dark coat, top hat",
            "portrait_archivist": "elderly archivist, round spectacles, kindly wary expression, ink-stained collar",
            "portrait_suspect": "gaunt obsessed scholar, wild bloodshot eyes, sweating, dishevelled collar",
            "portrait_priest": "gaunt cathedral priest, hollow solemn eyes, silver cross, black cassock",
            "portrait_widow": "grieving widow, black lace mourning veil, sorrowful eyes",
            "portrait_lady": "Loen gentlewoman, blonde hair in an updo, green eyes, faded muted sage-green high-collar gown, composed expression, gritty painterly pixel art, muted desaturated palette, NOT vibrant, NOT anime, NOT cartoon",
        },
    },
    # ── Enemies / supernatural (each keeps ONE saturated accent on the gloom) ──
    "enemies": {
        "model": "fast", "style": "detailed", "size": 384, "remove_bg": True,
        "variants": 1, "suffix": ENEMY_SUFFIX,
        "items": {
            "cultist_robed": "hooded occult cultist in dark ritual robes, ceremonial dagger, faint glowing sigil accent",
            "bieber_monster": "hulking ritual-warped monster, partial transformation, torn Victorian clothes, occult growths and too many limbs, one eerie glowing accent",
            "wraith_shadow": "translucent shadow wraith, tattered drifting robes, hollow glowing eyes",
            "descent_horror": "eldritch partial-descent horror, writhing impossible geometry, scattered glowing eyes, oppressive, single saturated crimson accent",
        },
    },
    # ── Props / clue objects / interactables (rd-plus, literal prompt) ──
    "props": {
        # NOTE: rd-plus `topdown_item` is currently broken server-side ("Unable to run
        # inference"); `topdown_asset` gives a clean single centered object — use it.
        "model": "plus", "style": "topdown_asset", "size": 384, "remove_bg": True,
        "bypass_expand": True, "variants": 1, "suffix": PROP_SUFFIX,
        "items": {
            "revolver": "antique ornate brass-and-steel service revolver",
            "antigonus_notebook": "sinister antique occult notebook, strange glowing sigils on a cracked leather cover",
            "cracked_mirror": "old standing mirror with a cracked surface, wooden frame",
            "blood_pool": "a flat dark red puddle of spilled blood, overhead top-down view, simple floor decal, no walls, no room",
            "oil_lamp": "brass oil lamp with a warm flame",
            "case_file": "tied bundle of investigation case files and papers",
            "evidence_photo": "a single old sepia photograph print, rectangular photo with a white border, flat object, no building",
            "occult_dagger": "ceremonial occult dagger with engraved sigils",
            "talisman_paper": "yellowed paper talisman inked with red occult symbols",
            "ledger_book": "thick leather accounting ledger",
            "writing_desk": "small wooden writing desk with papers and an inkwell",
            "simple_bed": "ornate carved-wood bed with a quilted blanket",
            "door_wood": "weathered wooden door, slightly ajar",
            "door_iron": "heavy riveted iron warehouse door",
            "bookshelf": "tall bookshelf crammed with old volumes",
            "archive_shelf": "dusty archive shelf of rolled scrolls and boxes",
            "wooden_crate": "stacked wooden shipping crates",
            "barrel": "wooden storage barrel",
            "candle": "melting candle with a small flame",
            "pocket_watch": "ornate brass pocket watch on a chain",
        },
    },
    # ── Seamless ground tiles (rd-plus, true edges, literal prompt) ──
    "tiles": {
        "model": "plus", "style": "textured", "size": 384, "remove_bg": False,
        "tile_x": True, "tile_y": True, "bypass_expand": True,
        "variants": 1, "suffix": TILE_SUFFIX, "scaffold": TILE_STYLE,
        "items": {
            "cobblestone_wet": "wet grey cobblestone street",
            "wood_floor": "worn wooden plank floor",
            "archive_carpet": "faded patterned carpet of an old library",
            "warehouse_concrete": "cracked industrial concrete floor with oil stains",
            "ritual_stone": "stone floor with faint chalk occult circle markings",
            "brick_alley": "flat dark red brick paving stones, wet, overhead top-down ground texture",
            "dead_grass": "muddy dead grass and dirt of poor outskirts",
        },
    },
    # ── Scene backgrounds / establishing rooms (rd-plus, larger) ──
    "backgrounds": {
        "model": "plus", "style": "topdown_map", "size": 384, "remove_bg": False,
        "variants": 1, "suffix": BG_SUFFIX, "scaffold": BG_STYLE,
        "items": {
            # All framed as walkable top-down maps (Stardew look): interiors = room floors,
            # exteriors = street/courtyard blocks. WARM middle-class home (STYLE_GUIDE §6).
            "klein_bedroom": "top-down view of Klein Moretti's warm cozy middle-class bedroom, wooden floorboards, ornate carved-wood bed with a quilt, writing desk and chair, bookshelf, wardrobe, dresser, patterned rug, warm amber lamplight, lived-in",
            "klein_parlor": "top-down view of a cozy middle-class Victorian parlor floor, patterned rug, cream sofa and armchairs, round tea table with flowers, fireplace, bookshelves, plank floor, warm lamplight",
            "hq_interior": "top-down view of the Nighthawks investigators headquarters office floor, wooden desks and chairs, an evidence board, filing cabinets, brass oil lamps, plank floor, gaslit",
            "library_archive": "top-down view of a vast university archive hall floor, long rows of towering bookshelves, reading desks, carpet runners, candlelight, dim and dusty",
            "warehouse_interior": "top-down view of a dockside warehouse floor, stacked wooden crates and barrels, chains, support pillars, cold cracked concrete floor, shafts of fog",
            "ritual_chamber": "top-down view of a hidden occult ritual chamber floor, large chalk summoning circle, black candles, silver sigils, dark stone floor, blood-red glow, oppressive",
            "tavern_interior": "top-down view of a cozy gaslit Loen tavern floor, wooden tables and benches, a long bar counter, fireplace, plank floor, warm amber light",
            "oldtown_street": "top-down view of a foggy cobblestone Tingen old-town street block, red-brick and timber buildings lining the lane, gas street lamps, wrought-iron rails, market crates",
            "university_quad": "top-down view of the Tingen University quad, green lawn courtyard, stone paths, benches, trees, ringed by red-brick collegiate Gothic buildings, gas lamps, calm",
            "cathedral_plaza": "top-down view of Saint Selena's Cathedral plaza, large cobblestone square, central stone fountain, the grand cream-stone Gothic cathedral along one side, benches, lamp posts",
            "iron_cross_street_day": "top-down view of the Iron Cross Street slum market block by day, narrow muddy lane, ramshackle leaning brick and half-timber buildings, market stalls and awnings, washing lines, crates, weathered grime, crowded",
            "iron_cross_street_bloodmoon": "top-down view of the Iron Cross Street slum block at night under a blood-red moon, dark crimson-lit muddy lane, leaning derelict buildings, deep shadows, dread and occult horror",
            "raphael_cemetery": "top-down view of Raphael Cemetery grounds at night, rows of weathered headstones, winding stone paths, a central stone obelisk, mausoleums, cypress trees, cold blue-grey fog, lantern light",
            # Capital, later-game only — heavy steampunk stays OFF of Tingen.
            "backlund_skyline": "top-down view of a Backlund industrial dockyard district, grid of cobblestone streets, brick factories with smokestacks, canals with moored barges, iron bridges, dock cranes, smog and grime",
        },
    },
    # ── UI / HUD (rd-plus, literal prompt) ──
    "ui": {
        "model": "plus", "style": "ui_element", "size": 384, "remove_bg": True,
        "bypass_expand": True, "variants": 1, "suffix": ICON_SUFFIX,
        "items": {
            "meter_corruption": "occult corruption gauge icon, creeping purple taint symbol",
            "meter_panic": "public panic gauge icon, frightened crowd symbol",
            "meter_fatigue": "investigator fatigue gauge icon, weary eye symbol",
            "meter_cult": "cult readiness gauge icon, dark ritual symbol",
            "meter_beyond": "attention-of-the-beyond gauge icon, watching eldritch eye",
            "clock_face": "ornate antique pocket-watch clock face HUD element",
            "dialogue_frame": "ornate Victorian dialogue box frame, parchment with a thin brass border",
            "board_pin": "red push pin for an investigation board",
            "map_marker": "glowing location marker pin for a city map",
            "tool_icon": "occult investigation tool icon, brass instrument",
            "notification_frame": "small ornate notification banner frame",
            "inventory_slot": "empty ornate inventory slot frame",
        },
    },
    # ── VFX / overlays ──
    "vfx": {
        # Isolated overlays: literal prompt + black-bg scaffold so the model draws ONLY
        # the effect (round-2 full pass rendered these as mini-scenes with lampposts/houses).
        "model": "fast", "style": "detailed", "size": 384, "remove_bg": True,
        "bypass_expand": True, "variants": 1, "suffix": "", "scaffold": VFX_STYLE,
        "items": {
            "muzzle_flash": "bright orange-yellow gunshot muzzle flash burst",
            "blood_splatter": "spray of dark red blood splatter droplets",
            "occult_glow": "glowing silver-violet occult rune circle",
            "fog_wisp": "soft curl of drifting grey fog",
            "distortion_sigil": "flickering glowing occult rune sigil",
            "candle_flame": "single small candle flame",
        },
    },
}

# Representative slice for --test: validates the round-4 changes — pale Victorian
# complexion (no more crushed-dark faces), the 384px bump, and the inclined
# top-down (Stardew) backgrounds, across interiors + exteriors.
TEST_PICKS = [
    ("characters", "player_detective"),      # Klein: pale skin + 384px detail
    ("characters", "npc_civilian_woman"),    # era townswoman (was crushing dark)
    ("characters", "priest"),                # was crushing pure-black
    ("portraits", "portrait_player"),        # Klein portrait: pale skin + gold eyes
    ("portraits", "portrait_widow"),         # era portrait skin check
    ("backgrounds", "klein_bedroom"),        # interior top-down room
    ("backgrounds", "cathedral_plaza"),      # exterior top-down landmark
    ("backgrounds", "iron_cross_street_day"),# exterior top-down slum block
    ("props", "pocket_watch"),               # 384px prop detail
    ("tiles", "cobblestone_wet"),            # 384px seamless tile
]


# ── Deterministic per-asset seeds ───────────────────────────────
# Stable hash of the name → a fixed seed, offset by variant so v0/v1 differ.
# Add to SEED_OVERRIDES to deliberately re-roll a single asset between rounds.
SEED_OVERRIDES: dict = {
    # Re-rolls for round 2 (round-1 draw was off-canon / unreadable).
    "portrait_player": 70707070,   # round-1 seed drew red eyes; re-roll + gold-eye prompt
    "npc_constable": 31313131,     # round-1 seed crushed to black; re-roll + rim-light suffix
    # Re-rolls for round 3 (full-pass draws were off-style / unreadable / mis-rendered).
    "lady_genteel": 52010101,      # was bright cartoon-anime; re-roll + muted-pixel prompt
    "portrait_lady": 52010202,     # same cartoon issue
    "priest": 52010303,            # crushed to pure black
    "witness_widow": 52010404,     # too dark + uncut background
    "npc_civilian_woman": 52010505,# too dark
    "blood_pool": 52010606,        # came out as a diorama, not a floor decal
    "evidence_photo": 52010707,    # came out as a building, not a photo
}


def seed_for(name: str, variant: int = 0) -> int:
    if name in SEED_OVERRIDES:
        return SEED_OVERRIDES[name] + variant * 7919
    return (zlib.crc32(name.encode()) + variant * 7919) % 2_000_000_000


# ── Token loading (never printed) ──────────────────────────────

def load_token(env_file: Path) -> str | None:
    tok = os.environ.get("REPLICATE_API_TOKEN")
    if tok:
        return tok.strip()
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == "REPLICATE_API_TOKEN":
                return val.strip().strip('"').strip("'")
    except OSError as e:
        print(f"ERROR: could not read env file {env_file}: {e}")
    return None


# ── Replicate plumbing (adapted from Yumina generate-sprites.py) ──

def download_image(url: str) -> bytes | None:
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.content
            print(f"    download failed: HTTP {resp.status_code}")
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"    download failed: {e}")
        if attempt < 2:
            time.sleep(2 * (attempt + 1))
    return None


def poll_prediction(pred_url: str) -> bytes | None:
    for tick in range(180):
        time.sleep(1)
        try:
            poll = requests.get(pred_url, headers={"Authorization": f"Bearer {REPLICATE_API_TOKEN}"}, timeout=15)
            pdata = poll.json()
        except (requests.ConnectionError, requests.Timeout, ValueError) as e:
            if tick % 10 == 0:
                print(f"    poll retry ({e})")
            continue
        status = pdata.get("status")
        if status == "succeeded":
            output = pdata.get("output")
            if output:
                img_url = output[0] if isinstance(output, list) else output
                return download_image(img_url)
            print("    ERROR: no output image")
            return None
        if status in ("failed", "canceled"):
            print(f"    ERROR: prediction {status}: {pdata.get('error', '')}")
            return None
    print("    ERROR: prediction timed out")
    return None


def generate_image(prompt: str, model_key: str, style: str, width: int, height: int,
                   remove_bg: bool, seed: int | None = None, tile_x: bool = False,
                   tile_y: bool = False, bypass_expand: bool = False) -> bytes | None:
    model = MODEL_PLUS if model_key == "plus" else MODEL_FAST
    input_data: dict = {
        "prompt": prompt,
        "style": style,
        "width": width,
        "height": height,
        "remove_bg": remove_bg,
    }
    if seed is not None:
        input_data["seed"] = seed
    if tile_x:
        input_data["tile_x"] = True
    if tile_y:
        input_data["tile_y"] = True
    if bypass_expand:
        input_data["bypass_prompt_expansion"] = True

    for attempt in range(5):
        try:
            resp = requests.post(
                f"https://api.replicate.com/v1/models/{model}/predictions",
                headers={
                    "Authorization": f"Bearer {REPLICATE_API_TOKEN}",
                    "Content-Type": "application/json",
                    "Prefer": "wait",
                },
                json={"input": input_data},
                timeout=120,
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            wait = 5 * (attempt + 1)
            print(f"    network error ({e}) — waiting {wait}s")
            time.sleep(wait)
            continue

        if resp.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"    rate limited — waiting {wait}s")
            time.sleep(wait)
            continue

        if resp.status_code not in (200, 201, 202):
            print(f"    ERROR: {resp.status_code} {resp.text[:200]}")
            if resp.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            return None

        data = resp.json()
        if data.get("status") == "succeeded":
            output = data.get("output")
            if output:
                img_url = output[0] if isinstance(output, list) else output
                return download_image(img_url)
        pred_url = data.get("urls", {}).get("get")
        if pred_url:
            return poll_prediction(pred_url)
        print("    ERROR: no prediction URL")
        return None
    print("    ERROR: retries exhausted")
    return None


def build_prompt(spec: dict, base: str) -> str:
    parts = [base]
    suffix = spec.get("suffix")
    if suffix:
        parts.append(suffix)
    scaffold = spec.get("scaffold", TINGEN_STYLE)
    if scaffold:
        parts.append(scaffold)
    return ", ".join(parts)


def cost_of(spec: dict) -> float:
    return 0.01 if spec["model"] == "plus" else 0.003


# ── Runner ─────────────────────────────────────────────────────

def iter_jobs(active: dict, limit: int | None, test: bool):
    if test:
        for cat, name in TEST_PICKS:
            spec = active[cat]
            yield cat, spec, name, spec["items"][name], 0
        return
    for cat, spec in active.items():
        items = list(spec["items"].items())
        if limit:
            items = items[:limit]
        for name, base in items:
            for v in range(spec["variants"]):
                yield cat, spec, name, base, v


def main():
    global REPLICATE_API_TOKEN
    ap = argparse.ArgumentParser(description="Generate Tingen vertical-slice assets")
    ap.add_argument("--dry-run", action="store_true", help="print plan, no API calls")
    ap.add_argument("--test", action="store_true", help="generate the representative test slice")
    ap.add_argument("--force", action="store_true", help="regenerate even if the output file already exists")
    ap.add_argument("--category", type=str, help="only this category")
    ap.add_argument("--limit", type=int, help="cap items per category")
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE, help="path to .env with REPLICATE_API_TOKEN")
    args = ap.parse_args()

    active = CATEGORIES
    if args.category:
        if args.category not in CATEGORIES:
            print(f"unknown category: {args.category}\navailable: {', '.join(CATEGORIES)}")
            sys.exit(1)
        active = {args.category: CATEGORIES[args.category]}

    jobs = list(iter_jobs(active, args.limit, args.test))
    est = sum(cost_of(s) for _, s, _, _, _ in jobs)
    print(f"Tingen Asset Generator")
    print(f"  output : {OUTPUT_DIR}")
    print(f"  jobs   : {len(jobs)} images")
    print(f"  est.   : ${est:.2f}")
    print(f"  mode   : {'DRY RUN' if args.dry_run else ('TEST' if args.test else 'LIVE')}")

    if not args.dry_run:
        REPLICATE_API_TOKEN = load_token(args.env_file)
        if not REPLICATE_API_TOKEN:
            print(f"ERROR: REPLICATE_API_TOKEN not found (env or {args.env_file})")
            sys.exit(1)
        print(f"  token  : loaded ({len(REPLICATE_API_TOKEN)} chars)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {"assets": []}
    existing = {(e["category"], e["name"], e["variant"]) for e in manifest["assets"]}

    done = skip = fail = 0
    for i, (cat, spec, name, base, v) in enumerate(jobs, 1):
        out_dir = OUTPUT_DIR / cat
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{name}_{v}.png"
        fpath = out_dir / fname
        prompt = build_prompt(spec, base)
        seed = seed_for(name, v)

        if fpath.exists() and not args.force:
            skip += 1
            continue

        if args.dry_run:
            print(f"  [{i}/{len(jobs)}] {cat}/{fname} (seed {seed}): {prompt[:80]}...")
            continue

        print(f"  [{i}/{len(jobs)}] {cat}/{fname} ({spec['model']}/{spec['style']}, {spec['size']}px, seed {seed})...")
        img = generate_image(
            prompt, spec["model"], spec["style"], spec["size"], spec["size"], spec["remove_bg"],
            seed=seed,
            tile_x=spec.get("tile_x", False),
            tile_y=spec.get("tile_y", False),
            bypass_expand=spec.get("bypass_expand", False),
        )
        if img:
            fpath.write_bytes(img)
            entry = {"category": cat, "name": name, "variant": v,
                     "path": f"out/{cat}/{fname}", "prompt": prompt,
                     "model": spec["model"], "style": spec["style"], "size": spec["size"],
                     "seed": seed, "alpha": spec["remove_bg"],
                     "tile": bool(spec.get("tile_x") or spec.get("tile_y"))}
            manifest["assets"] = [e for e in manifest["assets"]
                                  if (e["category"], e["name"], e["variant"]) != (cat, name, v)]
            manifest["assets"].append(entry)
            MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
            done += 1
            print(f"    OK ({len(img)//1024}KB)")
        else:
            fail += 1
        time.sleep(0.4)

    print(f"\nDone: {done} generated, {skip} existing, {fail} failed")
    if not args.dry_run:
        print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
