#!/usr/bin/env python3
"""
Tingen "Hero" Asset Generator — gpt-image-1 (OpenAI Images API)
===============================================================
Generates the *important figures* — named/NPC characters, dialogue portraits and
scene backgrounds — at high quality via gpt-image-1, conditioned on the canon
Lord-of-the-Mysteries reference art in asset-gen/ref/.

Why a second generator (vs generate_tingen_assets.py / Retro Diffusion):
  RD pixel art is great for props / tiles / UI / VFX, but the *hero* assets read
  too low-detail.  gpt-image-1 + reference images gives canon-faithful characters
  and richly painted scenes.  Props/tiles/UI/VFX stay on the RD pipeline.

LOCKED art direction (decided with Mark, see STYLE_GUIDE.md):
  - CHARACTERS  = crisp anime / manhua illustration faithful to the canon art,
                  recipe: canon ref (cropped) + input_fidelity=high + a prompt that
                  tells the model to MATCH THE REFERENCE'S STYLE.  Proven on
                  player_detective_HIFI.png — close to klein1, not the painterly drift.
  - BACKGROUNDS = painterly illustrated scenes (match the painted location refs),
                  split into 6 EYE-LEVEL establishing scenes + 8 INCLINED TOP-DOWN
                  (Stardew) walkable maps.
  - CAST        = 19 characters (17 base + Audrey Hall + Goddess of Darkness),
                  9 dialogue portraits, 4 enemies (Beyonder creatures / cultists).
  - ENEMIES     = same crisp anime rendering as the cast (style anchor, no canon ref),
                  but monstrous/eldritch occult-horror designs.

Endpoint:
  POST https://api.openai.com/v1/images/edits   (multipart; accepts image[] refs)
  Falls back to /v1/images/generations only for items with NO usable ref.

Key levers:
  size (1024x1024 | 1024x1536 | 1536x1024), quality (low|medium|high),
  background (transparent|opaque), output_format, input_fidelity (low|high),
  and — crucially, since gpt-image-1 has NO seed — one or more reference images.

Token:
  Reads OPENAI_API_KEY from the environment, else from --env-file
  (default: the Yumina repo .env).  The key value is never printed.

Usage:
  python3 generate_tingen_image2.py --dry-run                 # plan only, no API
  python3 generate_tingen_image2.py --only player_detective   # single item
  python3 generate_tingen_image2.py --category characters     # one category
  python3 generate_tingen_image2.py --category backgrounds --treatment topdown
  python3 generate_tingen_image2.py                           # the whole hero set
  python3 generate_tingen_image2.py --quality medium          # cheaper draft pass

Cost (gpt-image-1, approx): low ~$0.02, medium ~$0.05, high ~$0.25 / image.
  Full hero set (19 + 9 + 14 = 42) at high ≈ ~$10.

Requires: pip install requests pillow
"""

from __future__ import annotations

import os
import sys
import json
import time
import base64
import argparse
from pathlib import Path

import requests
from PIL import Image

HERE = Path(__file__).resolve().parent
REF_DIR = HERE / "ref"
OUT_DIR = HERE / "out_image2"
PREP_DIR = OUT_DIR / "_refprep"  # cropped (de-framed) reference images
MANIFEST_PATH = OUT_DIR / "manifest_image2.json"
DEFAULT_ENV_FILE = Path("/Users/markma/Desktop/Yumina/.env")

API_EDITS = "https://api.openai.com/v1/images/edits"
API_GEN = "https://api.openai.com/v1/images/generations"

OPENAI_API_KEY: str | None = None  # set in main()

# ── Reference crop boxes (fractions: left, top, right, bottom) ────────────────
# Canon refs carry title cartouches / ornate frame borders / corner watermarks.
# We crop those off once so the model conditions on the figure/scene, not chrome.
REF_CROPS: dict = {
    "klein1": (0.10, 0.00, 1.00, 1.00),  # left vertical title strip (克莱恩·莫雷蒂)
    "audrey1": (0.07, 0.06, 0.93, 0.96),
    "audrey2": (0.07, 0.06, 0.93, 0.96),
    "goddess_of_darkness": (0.06, 0.05, 0.94, 0.97),
}
FRAME_INSET = (0.065, 0.075, 0.935, 0.925)  # default for framed location refs

# Painterly samples we already made — reused as STYLE anchors where no canon
# location ref exists (keeps the palette/treatment consistent across the set).
STYLE_INTERIOR = OUT_DIR / "klein_bedroom_TEST.png"
STYLE_EXTERIOR = OUT_DIR / "iron_cross_street_day_TEST.png"
# Character style anchor for no-canon-ref NPCs (a clean anime full-body in our look).
STYLE_CHAR = OUT_DIR / "player_detective_HIFI.png"

# ── Prompt scaffolds ──────────────────────────────────────────────────────────
LOTM = (
    "late-Victorian gaslamp-fantasy occult-detective world of Lord of the Mysteries "
    "(Tingen City, the Loen Empire which is like Victorian Britain)"
)

# Characters: richly detailed painterly anime/manhua illustration, faithful to canon official art.
# (Round 6 — Mark: no-ref NPCs read too flat/"AI-like" and sepia-tinted vs the canon trio;
#  push painterly realism + detail, kill the yellow/amber/olive cast, and stop cropping heads.)
CHAR_STYLE = (
    f"richly detailed painterly anime / manhua illustration in the exact art style of the "
    f"official Lord of the Mysteries character artwork, semi-realistic proportions and faces, "
    f"polished volumetric cel-shading with soft painterly rendering, detailed fabric folds and "
    f"material texture, fine rendering detail, NOT flat, NOT minimal, NOT a cheap thick-outline "
    f"cartoon, NOT photorealistic, NOT a 3D render, {LOTM}, pale fair-skinned European, muted "
    f"COOL desaturated palette of neutral grays and cool tones, small restrained warm gaslight "
    f"accents only, overall neutral and cool — NO sepia tone, NO yellow / amber / olive color "
    f"cast, NO brown monochrome wash, dramatic cool key lighting"
)
CHAR_SUFFIX = (
    "full-body video game character sprite, single character, standing idle stance, the "
    "ENTIRE figure from the very top of the head down to the feet is fully inside the image "
    "and centered, with clear empty margin above the head and below the feet, nothing cropped, "
    "the head must not touch or exceed the top edge, fully isolated on a transparent "
    "background, no background scenery, no backdrop, no gradient, no ground shadow, no text, "
    "no logo, no frame, no border"
)
PORTRAIT_SUFFIX = (
    "chest-up character portrait, dialogue avatar, looking toward the viewer, the whole "
    "head including the top of the hair is fully inside the frame with margin above it, "
    "not cropped, fully isolated on a transparent background, no backdrop, no gradient, "
    "no text, no logo, no frame"
)

# Enemies: same crisp anime/manhua rendering as the cast, but monstrous/eldritch
# occult-horror designs (no "human European" trait) so they sit beside the cast.
ENEMY_STYLE = (
    f"richly detailed painterly anime / manhua illustration in the exact art style of the "
    f"official Lord of the Mysteries artwork, polished volumetric cel-shading with soft "
    f"painterly rendering and fine detail, NOT flat, NOT a cheap thick-outline cartoon, NOT "
    f"photorealistic, NOT a 3D render, {LOTM}, eerie menacing occult-horror creature design, "
    f"muted COOL desaturated palette with a single saturated occult accent, overall neutral "
    f"and cool — NO sepia, NO yellow / amber / olive color cast, dramatic ominous cool key lighting"
)
ENEMY_SUFFIX = (
    "full-body video game enemy sprite, single creature, menacing pose, the ENTIRE creature "
    "from top to bottom is fully inside the image and centered, with clear empty margin on "
    "all sides, nothing cropped, fully isolated on a transparent background, no backdrop, "
    "no gradient, no text, no logo, no frame, no border"
)

# Backgrounds: painterly illustrated scenes (match the painted location refs).
BG_ESTABLISH = (
    f"detailed painterly illustrated environment art, eye-level cinematic establishing "
    f"shot, {LOTM}, muted desaturated fog-gray palette with warm gaslight accents, "
    f"volumetric fog, moody atmospheric lighting, no text, no frame, no border, no people"
)
BG_TOPDOWN = (
    f"detailed painterly illustrated RPG game map, FLAT TRUE TOP-DOWN view seen from "
    f"directly straight above at a 90-degree bird's-eye angle like a classic top-down RPG "
    f"(The Legend of Zelda, Pokemon, RPG Maker), the floor / ground plane fills the entire "
    f"frame and is seen flat, every object and furniture piece viewed from directly overhead "
    f"showing only its top surface and footprint, NO perspective, NO incline, NO three-quarter "
    f"or isometric angle, objects are NOT drawn upright and do NOT face the camera, NO visible "
    f"building fronts, NO wall faces, NO horizon, NO sky, walkable ground fills the frame, "
    f"{LOTM}, muted desaturated fog-gray palette with warm gaslight accents, no text, no frame, "
    f"no border, no people"
)

# District maps: a STRICT flat top-down (true 90-degree bird's-eye) town map — only
# rooftops + streets, NO building fronts (those caused the isometric drift). Keeps
# building VARIETY + strong color CONTRAST, but is STYLE-AGNOSTIC: the per-variant
# art style is injected via each item's own prompt (see OLDTOWN_CONTENT + STYLE_*).
# (Round 3 — Mark: wants TRUE top-down, broken contrast fixed, and several art styles
#  to compare.)
BG_DISTRICT = (
    f"a large highly detailed top-down town district map, seen from directly straight above "
    f"at a true 90-degree flat bird's-eye angle looking straight down onto the rooftops and "
    f"streets like a classic overhead RPG world-map / city map, the cobblestone streets and "
    f"rooftops fill the entire frame seen perfectly flat, every building viewed from directly "
    f"overhead showing only its roof and footprint, NO perspective, NO incline, NO "
    f"three-quarter or isometric angle, NO visible building fronts or wall faces, NO horizon, "
    f"NO sky. The district is densely packed with a richly VARIED mix of distinct late-Victorian "
    f"/ 1890s rooftops — every roof a different size, shape, colour and material so NO two "
    f"buildings look the same and there are NO repeated identical blocks and NO uniform grid: "
    f"red-clay tile roofs, blue-grey slate roofs, a cross-shaped chapel roof with a steeple, "
    f"gabled, hipped and mansard roofs, chimney pots, inner courtyards, small green gardens and "
    f"trees, a market square with awninged stalls, winding lanes and alleys. Clear separation "
    f"and STRONG value contrast between roofs, streets and greenery so every building reads "
    f"distinctly, crisp and fully readable, {LOTM}, no text, no frame, no border, no people"
)

# District map, TRUE flat 90-degree variant (round 4 — Mark: the 7 oblique variants all
# drifted off true top-down and the colours were too muted/cold). Anchored on a flat
# overhead reference at HIGH input_fidelity to LOCK the straight-down angle, then a WARM
# SUNLIT saturated palette (extracted from Mark's bright Mediterranean/Levantine city refs:
# golden daylight, cream-gold stone, terracotta + teal/turquoise roofs, lush green).
BG_DISTRICT_FLAT = (
    f"a large, highly detailed top-down city district map seen from directly straight "
    f"above at a TRUE flat 90-degree bird's-eye angle, looking perfectly straight down onto "
    f"the rooftops and streets exactly like a vertical aerial photograph or a classic flat "
    f"overhead strategy-game map, the streets and rooftops fill the entire frame seen "
    f"completely flat, every building shown only as its roof and footprint from straight "
    f"overhead, absolutely NO perspective, NO tilt, NO oblique or three-quarter or isometric "
    f"angle, NO visible building fronts, walls or facades, NO building sides, NO horizon and "
    f"NO sky — only rooftops and streets seen flat from above. Densely packed with a richly "
    f"VARIED mix of distinct late-Victorian rooftops of every size, shape and material: a "
    f"cross-shaped chapel roof with a steeple, gabled, hipped and mansard roofs, chimney "
    f"pots, inner courtyards, gardens, trees, a market square with awninged stalls, winding "
    f"lanes and alleys. "
    f"STRONG HIGH-CONTRAST colour with a clear full light-to-dark value range — this is the "
    f"single most important quality and it must NOT be a flat uniform single-hue image: the "
    f"streets, lanes, alleys and squares are a PALE almost-WHITE light cool-grey paving "
    f"stone, distinctly desaturated and much LIGHTER than every roof — definitely NOT golden, "
    f"NOT amber, NOT orange streets; the ground must stay pale and neutral so the coloured "
    f"roofs stand out boldly against it — while the rooftops form a vivid PATCHWORK of "
    f"distinctly different colours and brightnesses set against those pale streets: warm "
    f"terracotta-orange and brick-red roofs placed right NEXT TO plenty of DARK "
    f"charcoal-slate, near-black and deep blue-grey roofs, plus rich verdigris teal and "
    f"turquoise roofs and dark-green roofs, and lush saturated green garden squares and "
    f"trees — so any two adjacent buildings always differ sharply in both colour and "
    f"brightness and every single building reads as its own separate, crisply outlined "
    f"block. Bright clear daylight with sharp clean crisp edges and well-defined dark shadows "
    f"in the narrow lanes for depth, warm terracotta roofs glowing against cool pale streets, "
    f"vibrant and saturated and fully readable — NOT a monochrome orange wash, NOT all one "
    f"hue, NOT all one brightness, NOT hazy, NOT blurry, NOT soft-focus, NOT muted, NOT "
    f"grey-and-foggy, NOT dark, NOT low-contrast. {LOTM}, no text, no frame, no border, no "
    f"people"
)

# Shared Old Town Core content (identical across every style variant so they compare
# fairly); the art style is appended per-variant from the STYLE_* strings below.
OLDTOWN_CONTENT = (
    "the Old Town Core, the dense historic heart of Tingen City, as a detailed top-down map: "
    "a maze of winding cobblestone lanes, alleys, courtyards and a central market square around "
    "one long main market street (Iron Cross Street). A rich varied jumble of late-Victorian "
    "rooftops of every shape and colour over a butcher, a baker, a chemist, three corner "
    "taverns, a brick lodging-house, a grey-stone townhouse, a steepled brick chapel and a "
    "civic stone police station. The market square holds a round stone well and colourful "
    "awninged stalls; a tall iron elevated-railway viaduct crosses one side; gas street-lamps "
    "line the lanes; small green gardens, trees and a canal with a footbridge edge the district"
)

# Seven art-style treatments to compare (round 3). Described by extracted visual
# ELEMENTS only — the source works are deliberately not named in the prompt.
STYLE_CEL = (
    "Rendered in a clean flat cel-shaded anime style — bold crisp dark outlines, flat blocks "
    "of bright saturated colour with simple two-tone cel shading, minimal gradients, a vivid "
    "graphic high-contrast look"
)
STYLE_PAINT = (
    "Rendered in a rich painterly thick-brush digital-paint style — visible textured impasto "
    "brushstrokes, layered saturated colours, dramatic moody colored lighting with strong "
    "contrast, a cinematic hand-painted graphic-novel look"
)
STYLE_RETRO90 = (
    "Rendered in a nostalgic 1990s retro hand-painted anime style — slightly grainy film "
    "texture, a warm vintage palette of saturated but gently faded colours, gouache-painted "
    "backgrounds, soft retro cel print quality"
)
STYLE_STORYBOOK = (
    "Rendered in a soft lush hand-painted storybook style — gentle naturalistic "
    "gouache-and-watercolour backgrounds, warm inviting earthy colours, cozy whimsical detail, "
    "soft natural daylight, billowing painterly foliage"
)
STYLE_CINEMATIC = (
    "Rendered in a luminous hyper-detailed cinematic anime style — glowing atmospheric light, "
    "richly saturated jewel-like colours, crisp ultra-detailed rendering, dramatic radiant "
    "daylight glow and gentle bloom, photoreal lighting on a painted scene"
)
STYLE_WATERCOLOR = (
    "Rendered as a soft watercolour painting — translucent bleeding washes of pigment, visible "
    "cold-press paper texture, loose wet edges, luminous light tones punctuated by pops of "
    "saturated colour, delicate and hand-painted"
)
STYLE_INKWASH = (
    "Rendered as an elegant East-Asian ink-wash painting — expressive black sumi brushwork and "
    "soft grey ink gradients, generous negative space, restrained selective colour accents, "
    "calligraphic linework on warm rice-paper"
)


# ── Cast / scenes (descriptions track STYLE_GUIDE.md + LotM canon) ────────────
# Each item: prompt description, plus optional "ref" (canon content reference key).
# Items with a canon ref use input_fidelity=high to lock likeness; ref-less items
# pass a STYLE anchor (loose) and a "different person/place" instruction.

CHARACTERS: dict = {
    "player_detective": {
        "ref": "klein1",
        "prompt": (
            "Klein Moretti, a pale young European man in his early twenties, black hair swept "
            "back, luminous glowing gold eyes, a charcoal-black caped Inverness overcoat with a "
            "deep-violet flaring lining, white high-collar shirt and dark cravat, dark waistcoat "
            "with a pocket-watch chain, a brown leather shoulder-holster with a revolver, holding "
            "a black cane with an ornate silver handle and a black top hat, calm composed idle stance"
        ),
    },
    "audrey_hall": {
        "ref": "audrey1",
        "prompt": (
            "Audrey Hall, an elegant young aristocratic Loen noblewoman, golden-blonde hair styled "
            "up, bright blue eyes, a refined high-collar Victorian day dress in muted cream and "
            "soft blue, white gloves, poised graceful bearing, gentle confident expression"
        ),
    },
    "goddess_darkness": {
        "ref": "goddess_of_darkness",
        "prompt": (
            "the Goddess of Darkness / Night, a serene otherworldly divine woman, long flowing black "
            "hair, a star-strewn midnight-black gown, faint silver-violet celestial glow, calm "
            "transcendent expression, occult majesty"
        ),
    },
    "nighthawk_captain": {
        "prompt": "a stern Nighthawk investigator captain, long dark double-breasted Inverness coat, brass badge, leather gloves, a brass oil lantern, top hat, authoritative bearing"
    },
    "archivist": {
        "prompt": "an elderly university archivist, round brass spectacles, an ink-stained scholar's frock coat and waistcoat, clutching an old leather tome, kindly wary"
    },
    "suspect_bieber": {
        "prompt": "a gaunt obsessed ritual scholar, wild bloodshot eyes, a dishevelled Victorian suit and waistcoat, gripping a cursed leather notebook, sweating"
    },
    "informant": {
        "prompt": "a shifty tavern informant, flat cap, worn wool coat and waistcoat, a sly knowing grin"
    },
    "priest": {
        "prompt": "a gaunt cathedral priest, bareheaded with thinning grey hair, a clearly visible pale gaunt face, a dark grey clerical cassock with a white clerical collar, a silver cross pendant, solemn weary expression"
    },
    "witness_widow": {
        "prompt": "a grieving widow in a dark grey Victorian mourning gown and lace veil, holding a parasol, sorrowful dignified bearing"
    },
    "lady_genteel": {
        "prompt": "a Loen gentlewoman in a faded muted sage-green and cream Victorian bustle gown, white gloves, holding a parasol, brown hair in an updo, dignified"
    },
    "npc_investigator": {
        "prompt": "a plainclothes Nighthawk investigator, a dark overcoat and waistcoat, top hat, a notebook in hand"
    },
    "npc_civilian_man": {
        "prompt": "an ordinary working-class Loen townsman, flat cap, waistcoat, rolled shirtsleeves"
    },
    "npc_civilian_woman": {
        "prompt": "an ordinary Loen townswoman, a long skirt, a shawl and bonnet, plain and weary"
    },
    "npc_laborer": {
        "prompt": "a weary dockside laborer, rough wool clothes, rolled sleeves, heavy boots"
    },
    "npc_constable": {
        "prompt": "a uniformed Loen city constable, a tall custodian helmet, a caped greatcoat, a truncheon"
    },
    "npc_dockworker": {
        "prompt": "a burly dockworker, an oilskin coat and cap, a coil of rope over the shoulder"
    },
    "npc_drunkard": {
        "prompt": "a stumbling drunkard in shabby Victorian clothes, a bottle in hand, dishevelled"
    },
    "npc_street_urchin": {
        "prompt": "a ragged street-urchin child, an oversized patched coat, a flat cap, barefoot"
    },
    "npc_cultist_hidden": {
        "prompt": "an ordinary Loen citizen with a faint unsettling stare, a concealed cultist, a plain coat"
    },
}

PORTRAITS: dict = {
    "portrait_player": {
        "ref": "klein1",
        "prompt": "Klein Moretti, a pale composed scholarly face, black hair swept back, striking bright gold eyes, a charcoal-black high-collar overcoat with deep-violet lining, white collar and dark cravat, brooding controlled expression",
    },
    "portrait_audrey": {
        "ref": "audrey1",
        "prompt": "Audrey Hall, a graceful young noblewoman, golden-blonde hair styled up, bright blue eyes, a cream-and-soft-blue high-collar Victorian dress, poised gentle expression",
    },
    "portrait_goddess": {
        "ref": "goddess_of_darkness",
        "prompt": "the Goddess of Darkness, a serene divine woman, long black hair, faint silver-violet celestial glow, calm transcendent expression",
    },
    "portrait_captain": {
        "prompt": "a stern Nighthawk captain, a weathered face, a brass-badged dark coat, a top hat"
    },
    "portrait_archivist": {
        "prompt": "an elderly archivist, round spectacles, a kindly wary expression, an ink-stained collar"
    },
    "portrait_suspect": {
        "prompt": "a gaunt obsessed scholar, wild bloodshot eyes, sweating, a dishevelled collar"
    },
    "portrait_priest": {
        "prompt": "a gaunt cathedral priest, hollow solemn eyes, a silver cross, a black cassock with a white collar"
    },
    "portrait_widow": {
        "prompt": "a grieving widow, a black lace mourning veil, sorrowful eyes"
    },
    "portrait_lady": {
        "prompt": "a Loen gentlewoman, brown hair in an updo, green eyes, a faded muted sage-green high-collar gown, a composed expression"
    },
}

# Enemies — Beyonder creatures / cultists (no canon ref → render via style anchor only).
ENEMIES: dict = {
    "cultist_robed": {
        "prompt": "a hooded occult cultist, a deep-hooded dark ritual robe with the face lost in shadow, clutching a ceremonial occult dagger, a faint glowing crimson sigil on the chest, a menacing cultic stance"
    },
    "bieber_monster": {
        "prompt": "a hulking ritual-warped horror, a man caught mid-transformation into a monster, a torn bloodstained Victorian suit, distended muscle and bony occult growths, too many clawed limbs, one eerie glowing-red eye, hunched and menacing"
    },
    "wraith_shadow": {
        "prompt": "a translucent shadow wraith, a ghostly spectral figure of drifting black smoke and tattered floating burial robes, hollow glowing pale-blue eyes, a half-incorporeal body, eerie and weightless"
    },
    "descent_horror": {
        "prompt": "an eldritch partial-Descent horror, a writhing mass of impossible non-Euclidean geometry and dark tendrils, scattered glowing crimson eyes across its form, oppressive otherworldly dread, a single saturated crimson accent glow"
    },
}

# Backgrounds carry a "treatment": "establish" (eye-level) or "topdown" (Stardew).
BACKGROUNDS: dict = {
    # ── establishing (eye-level painterly scenes; key story beats) ──
    "klein_bedroom": {
        "treatment": "establish",
        "ref": "kleinroom",
        "prompt": "Klein Moretti's warm cozy middle-class bedroom, an ornate carved-wood bed with a quilt, a writing desk and chair, a bookshelf, a wardrobe and dresser, a patterned rug, warm amber lamplight, rain on the window, lived-in",
    },
    "klein_parlor": {
        "treatment": "establish",
        "ref": "kleinhouse",
        "prompt": "a cozy middle-class Victorian parlor, a patterned rug, a cream sofa and armchairs, a round tea table with flowers, a fireplace, bookshelves, warm lamplight",
    },
    "ritual_chamber": {
        "treatment": "establish",
        "ref": "goddess_of_darkness",
        "prompt": "a hidden occult ritual chamber, a large chalk summoning circle on a dark stone floor, black candles, silver sigils, a blood-red glow, oppressive dread",
    },
    "iron_cross_street_bloodmoon": {
        "treatment": "establish",
        "ref": "ironcrossstreet",
        "prompt": "the Iron Cross Street slum at night under a blood-red moon, a dark crimson-lit muddy lane, leaning derelict brick and half-timber buildings, deep shadows, occult horror",
    },
    "backlund_skyline": {
        "treatment": "establish",
        "ref": "beckland",
        "prompt": "the industrial capital Backlund at dusk, brick factories with smokestacks, canals and iron bridges, dock cranes, a grand skyline under heavy smog and grime",
    },
    "warehouse_interior": {
        "treatment": "establish",
        "ref": None,
        "prompt": "a dockside warehouse interior, stacked wooden crates and barrels, hanging chains, support pillars, a cold cracked-concrete floor, shafts of fog and dim light",
    },
    # ── topdown (inclined 3/4 walkable maps; explorable hubs) ──
    "iron_cross_street_day": {
        "treatment": "topdown",
        "ref": "ironcrossstreet2",
        "prompt": "the Iron Cross Street slum market block by day, a narrow muddy lane, ramshackle leaning brick and half-timber buildings, market stalls and awnings, washing lines, crates, weathered grime",
    },
    "cathedral_plaza": {
        "treatment": "topdown",
        "ref": "St-SelenaChurchTingen",
        "prompt": "the plaza before Saint Selena's Cathedral, a large cobblestone square, a central stone fountain, the grand cream-stone Gothic cathedral along one side, benches and lamp posts",
    },
    # Saint Selena's nave — INTERIOR (Cassian/Auber, the "miracles", ritual evidence).
    # Generated in two views so Mark can pick: topdown = walkable floor (HQ-style),
    # establish = grand eye-level card. Render the winner at --quality high.
    "cathedral_nave": {
        "treatment": "topdown",
        "ref": None,
        "prompt": "the interior nave of Saint Selena's Cathedral, the Church of the Goddess of the Night — a vast hall of polished BLACK veined marble, a central aisle of dark marble flanked by two rows of dark pews, the bases of slender silver-veined black marble columns, a raised chancel with a black marble altar, tall silver candelabra and a silver crescent-moon emblem, cool silver-blue moonlight and faint pools of indigo and violet stained-glass light on the gleaming black marble floor, sparse and elegant, serene and solemn, hushed sacred stillness, cold lunar palette, NOT warm-toned, NO red carpet, NO gold",
    },
    "cathedral_nave_card": {
        "treatment": "establish",
        "ref": None,
        "prompt": "the soaring interior nave of Saint Selena's Cathedral, the Church of the Goddess of the Night — seen down a central aisle of polished BLACK veined marble toward a black marble altar crowned by a silver crescent moon, towering slender black marble columns and pointed silver-traced arches, a great lunar rose-window of indigo, violet and silver glass, cool silver moonlight and drifting incense, dark pews, elegant and austere, profoundly serene and solemn, hushed sacred grandeur, cold lunar palette, NOT warm-toned, NO gold, NO red",
    },
    "university_quad": {
        "treatment": "topdown",
        "ref": "uni",
        "prompt": "the Tingen University quad, a green lawn courtyard, stone paths, benches and trees, ringed by red-brick collegiate Gothic buildings and gas lamps",
    },
    "raphael_cemetery": {
        "treatment": "topdown",
        "ref": "graveyard",
        "prompt": "Raphael Cemetery grounds at night, rows of weathered headstones, winding stone paths, a central stone obelisk, mausoleums, cypress trees, cold blue-grey fog, lantern light",
    },
    "oldtown_street": {
        "treatment": "topdown",
        "ref": "tingen_view",
        "prompt": "a foggy cobblestone Tingen old-town street block, red-brick and timber buildings lining the lane, gas street lamps, wrought-iron rails, market crates",
    },
    # District-scale top-down map of the Old Town Core (Iron Cross / market heart).
    # Uses the `district` treatment (true top-down + bright + forced building variety);
    # the tingen_map survey ref supplies only the loose overhead street grid.
    "oldtown_core_district": {
        "treatment": "district",
        "ref": "tingen_map",
        "prompt": (
            "the Old Town Core, the dense historic heart of Tingen City — a maze of winding "
            "cobblestone lanes, alleys, courtyards and small squares around one long main "
            "market street (Iron Cross Street). Fill it with a rich VARIED mix of distinct "
            "late-Victorian buildings, every one different: tall ornate red-brick terraced "
            "townhouses with bay windows and gabled facades, humble timber-and-plaster "
            "cottages, painted shopfronts (a butcher, a baker, a fortune-teller's stall, a "
            "chemist), three corner taverns with hanging signs, a brick terraced lodging-house, "
            "a discreet grey-stone townhouse on a side street, a steepled brick chapel, and a "
            "columned civic stone police station. A central cobblestone market square holds a "
            "round stone well and rows of colorful market stalls with crates and a horse-cart. "
            "A tall iron elevated-railway viaduct crosses one side, black cast-iron gas "
            "street-lamps and wrought-iron railings line every lane, small trees and front "
            "gardens dot the courtyards, and a canal with a low stone embankment and a small "
            "footbridge runs along one edge. Richly colored warm late-Victorian architecture "
            "with intricate, varied rooftop and street detail"
        ),
    },
    # Seven art-style variants of the same Old Town Core district (round 3) — identical
    # content (OLDTOWN_CONTENT) + a different STYLE_* each, so Mark can compare styles fairly.
    "oldtown_core_cel": {
        "treatment": "district",
        "ref": "tingen_map",
        "prompt": f"{OLDTOWN_CONTENT}. {STYLE_CEL}",
    },
    "oldtown_core_paint": {
        "treatment": "district",
        "ref": "tingen_map",
        "prompt": f"{OLDTOWN_CONTENT}. {STYLE_PAINT}",
    },
    "oldtown_core_retro90": {
        "treatment": "district",
        "ref": "tingen_map",
        "prompt": f"{OLDTOWN_CONTENT}. {STYLE_RETRO90}",
    },
    "oldtown_core_storybook": {
        "treatment": "district",
        "ref": "tingen_map",
        "prompt": f"{OLDTOWN_CONTENT}. {STYLE_STORYBOOK}",
    },
    "oldtown_core_cinematic": {
        "treatment": "district",
        "ref": "tingen_map",
        "prompt": f"{OLDTOWN_CONTENT}. {STYLE_CINEMATIC}",
    },
    "oldtown_core_watercolor": {
        "treatment": "district",
        "ref": "tingen_map",
        "prompt": f"{OLDTOWN_CONTENT}. {STYLE_WATERCOLOR}",
    },
    "oldtown_core_inkwash": {
        "treatment": "district",
        "ref": "tingen_map",
        "prompt": f"{OLDTOWN_CONTENT}. {STYLE_INKWASH}",
    },
    # Round 4: TRUE flat 90-degree top-down + warm sunlit palette. `district_flat`
    # treatment locks the straight-down angle via HIGH input_fidelity on a flat
    # overhead reference. `_flat` uses the on-disk tingen_map survey map; `_flat_ref`
    # uses Mark's flat aerial city-map reference (saved as oldtown_angle_ref) which
    # already renders rooftops, so it should give the cleanest true-overhead result.
    "oldtown_core_flat": {
        "treatment": "district_flat",
        "ref": "tingen_map",
        "prompt": OLDTOWN_CONTENT,
    },
    "oldtown_core_flat_ref": {
        "treatment": "district_flat",
        "ref": "oldtown_angle_ref",
        "prompt": OLDTOWN_CONTENT,
    },
    # Round 4b: contrast fix — same locked flat angle (high-fidelity tingen_map), but the
    # scaffold now forces pale streets vs a light+dark roof patchwork to kill the orange wash.
    "oldtown_core_flat2": {
        "treatment": "district_flat",
        "ref": "tingen_map",
        "prompt": OLDTOWN_CONTENT,
    },
    # Round 4c: cool PALE streets vs warm/dark roof patchwork (complementary contrast) + crisp
    # edges — best on-disk shot at fixing value contrast before falling back to image-1 ref.
    "oldtown_core_flat3": {
        "treatment": "district_flat",
        "ref": "tingen_map",
        "prompt": OLDTOWN_CONTENT,
    },
    "hq_interior": {
        "treatment": "topdown",
        "ref": None,
        "prompt": "the Nighthawks investigators' headquarters hall inside a grand building, an elegant antique steampunk records office, the rectangular room is fully enclosed and bordered along all four outer edges by thick tall polished silvery-black marble walls seen from directly above, a polished black marble floor with shining white veining and soft silver highlights filling the center, a logical sensible records-office layout: a few paired writing desks with chairs, tall black filing cabinets and bookshelves lined neatly against the marble walls, a long central meeting table, a stately black evidence board framed in polished silver mounted flat against one wall, one piece of silver-and-glass steampunk apparatus with gauges on a side table, just one or two antique silver candelabra for light, sparse tidy and orderly not cluttered, lustrous polished black marble with shiny white veining and gleaming silver fittings, sophisticated antique refined and aesthetically pleasing, a sleek monochrome black-and-silver palette, black with shiny white and gleaming silver, clearly and evenly lit with a soft cool silver-white glow so the whole room is bright enough to read everything, NO brown wood, NO warm amber or gold, NO brass, NO green or teal or olive tint, NO clutter, NO excessive lights, NO scattered candles",
    },
    "library_archive": {
        "treatment": "topdown",
        "ref": None,
        "prompt": "a flat true top-down floor plan of an enormous grand university library seen from directly straight overhead at a 90-degree bird's-eye angle looking straight down at the floor, the expansive warm honey-wood plank floor fills the entire frame seen perfectly flat, the room bordered along all four outer edges by a thin neat rim of mahogany bookshelves seen from directly above, the main floor covered by a big regular 3 by 3 grid of nine long rectangular bookshelf stacks each seen from directly overhead as a flat-topped block showing the tops of the shelves and neat rows of book-spines, clear wide walkable aisles with red-and-gold patterned carpet runners between the stacks like a real library stacks section, a long flat-topped librarian's reception desk counter near the entrance along the bottom edge seen from above, a study area to one side with several long reading tables seen from directly above showing their flat tabletops with small green banker's lamps and tucked-in chairs, a flat-topped wooden card-catalogue cabinet against one wall, bright warm pools of golden sunlight cast across the floor, warm honey-brown mahogany wood with aged gold and deep-red carpets, a cozy welcoming bright scholarly antique library, very bright airy and evenly lit with abundant warm golden light so every part of the floor is clearly and fully readable, a bright warm inviting cheerful glow, everything viewed from directly overhead showing only flat top surfaces and footprints, NO perspective, NO incline, NO three-quarter or isometric angle, NO visible shelf fronts, NO wall faces, NO window faces, NO upright furniture, NO darkness, NO gloom, NO dark corners, NO vignette, NO cold blue or grey tint, NO marble, NO black palette, NO people",
    },
    "tavern_interior": {
        "treatment": "topdown",
        "ref": None,
        "prompt": "a cozy gaslit Loen tavern floor, wooden tables and benches, a long bar counter, a fireplace, a plank floor, warm amber light",
    },
}

CATEGORY_DEFAULTS: dict = {
    "characters": {
        "items": CHARACTERS,
        "size": "1024x1536",
        "background": "transparent",
        "suffix": CHAR_SUFFIX,
        "style": CHAR_STYLE,
        "style_anchor": STYLE_CHAR,
    },
    "portraits": {
        "items": PORTRAITS,
        "size": "1024x1024",
        "background": "transparent",
        "suffix": PORTRAIT_SUFFIX,
        "style": CHAR_STYLE,
        "style_anchor": STYLE_CHAR,
    },
    "enemies": {
        "items": ENEMIES,
        "size": "1024x1536",
        "background": "transparent",
        "suffix": ENEMY_SUFFIX,
        "style": ENEMY_STYLE,
        "style_anchor": STYLE_CHAR,
    },
    "backgrounds": {
        "items": BACKGROUNDS,
        "size": "1536x1024",
        "background": "opaque",
        "suffix": "",
        "style": None,
        "style_anchor": None,
    },  # per-item below
}


# ── Reference prep (crop frames/text once) ────────────────────────────────────
def prep_ref(key: str, headroom: float = 0.0) -> Path | None:
    """Return a path to a de-framed copy of ref/<key>.png (cached in _refprep).

    headroom > 0 pads empty neutral space above (and a little below) the cropped
    figure, so that input_fidelity=high reproduces that margin instead of cropping
    the head.  The canon character refs are tall figures whose head sits near the
    top edge; without this pad, high fidelity clings to that tight framing and
    clips the head/hat/veil (round-6 fix for goddess + audrey)."""
    src = REF_DIR / f"{key}.png"
    if not src.exists():
        print(f"    WARN: ref not found: {src}")
        return None
    suffix = f"_hr{int(headroom*100)}" if headroom > 0 else ""
    dst = PREP_DIR / f"{key}{suffix}.png"
    if dst.exists():
        return dst
    PREP_DIR.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    w, h = im.size
    l, t, r, b = REF_CROPS.get(key, FRAME_INSET)
    cropped = im.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
    if headroom > 0:
        cw, ch = cropped.size
        # Inset the figure with a clear margin on every side (extra on top) so the
        # subject sits smaller inside the ref; high fidelity then has to keep the
        # whole head — padding top alone wasn't enough (round-6 redo).
        pad_top = int(ch * headroom)
        pad_bot = int(ch * headroom * 0.55)
        pad_side = int(cw * headroom * 0.6)
        canvas = Image.new(
            "RGB", (cw + 2 * pad_side, ch + pad_top + pad_bot), (130, 134, 140)
        )
        canvas.paste(cropped, (pad_side, pad_top))
        canvas.save(dst)
    else:
        cropped.save(dst)
    return dst


def resolve_refs(cat: str, name: str, spec: dict) -> tuple[list[Path], bool]:
    """Return (ref_paths, high_fidelity). Canon ref -> high fidelity (lock likeness).
    No canon ref -> a loose STYLE anchor (keep look, NOT identity)."""
    ref_key = spec.get("ref")
    if ref_key:
        # Canon character/portrait refs are tall full figures: pad headroom so
        # high fidelity keeps the head in frame instead of cropping it.
        headroom = 0.30 if cat in ("characters", "portraits") else 0.0
        p = prep_ref(ref_key, headroom=headroom)
        # Top-down backgrounds keep fidelity LOW: the canon location refs are
        # eye-level, and high fidelity would override the required flat
        # directly-overhead top-down reframing.  The ref still informs architecture + palette.
        hi = not (
            cat == "backgrounds" and spec.get("treatment") in ("topdown", "district")
        )
        return ([p] if p else []), hi
    # ref-less: choose a style anchor
    if cat == "backgrounds":
        anchor = (
            STYLE_INTERIOR if spec.get("treatment") == "establish" else STYLE_EXTERIOR
        )
        # interiors vs exteriors: hq/library/tavern/warehouse are interiors
        if name in (
            "hq_interior",
            "library_archive",
            "tavern_interior",
            "warehouse_interior",
        ):
            anchor = STYLE_INTERIOR
        # HQ wants a cool antique black-and-silver palette, not the warm
        # klein_bedroom anchor — match the desaturated Backlund cityscape ref.
        if name == "hq_interior":
            anchor = REF_DIR / "beckland.png"
    else:
        anchor = STYLE_CHAR
    return ([anchor] if anchor and Path(anchor).exists() else []), False


def build_prompt(cat: str, name: str, spec: dict, has_canon_ref: bool) -> str:
    desc = spec["prompt"]
    if cat == "backgrounds":
        treatment = spec.get("treatment")
        style = {
            "establish": BG_ESTABLISH,
            "topdown": BG_TOPDOWN,
            "district": BG_DISTRICT,
            "district_flat": BG_DISTRICT_FLAT,
        }.get(treatment, BG_TOPDOWN)
        if has_canon_ref:
            lead = "Reimagine the place in the reference image as: "
            if treatment == "establish":
                tail = "Match the painted illustration style and palette of the reference. "
            elif treatment == "district":
                tail = (
                    "Use ONLY the overhead street-grid layout and bird's-eye viewpoint of the "
                    "reference map as a loose guide for the road network; do NOT copy the "
                    "reference's uniform identical blocks and do NOT copy its pale flat "
                    "monochrome palette. Render the entire district in the specific art style "
                    "described above, letting that style govern the medium, colour palette, "
                    "linework and finish, as one cohesive, highly varied town map full of "
                    "unique detailed buildings. "
                )
            elif treatment == "district_flat":
                tail = (
                    "Keep ONLY the flat straight-down overhead viewpoint and the dense "
                    "street-and-rooftop layout of the reference image; redraw every building "
                    "as a fully rendered warm sunlit late-Victorian rooftop seen from directly "
                    "above. Do NOT keep the reference's pale muted grey-brown colours — "
                    "recolour the entire map into bright warm golden daylight with glowing "
                    "cream-and-gold streets, terracotta and teal rooftops and lush green "
                    "gardens, richly saturated and luminous. "
                )
            else:
                tail = (
                    "Keep the architecture and palette of the reference but redraw it from the "
                    "flat directly-overhead true top-down angle described. "
                )
        else:
            lead = ""
            tail = "Match the painted illustration style and palette of the reference image. "
        return f"{lead}{desc}. {tail}{style}."
    # characters / portraits
    base = CATEGORY_DEFAULTS[cat]
    if has_canon_ref:
        lead = "This exact person from the reference image: "
        tail = "Match the art style of the reference exactly. "
    else:
        lead = (
            "A menacing enemy figure (NOT the person in the reference image): "
            if cat == "enemies"
            else "A distinct individual (NOT the person in the reference image): "
        )
        tail = (
            "Copy ONLY the rendering technique and level of fine detail of the reference image — "
            "its painterly polish, volumetric shading and detailed texture — but NEVER its face, "
            "hair, clothing, or color palette. Render this as a distinct individual with the same "
            "richly detailed, semi-realistic painterly anime finish as the reference, NOT flat, NOT "
            "a thick-outline cartoon. "
        )
    return f"{lead}{desc}. {tail}{base['style']}. {base['suffix']}."


# ── Token loading (never printed) ─────────────────────────────────────────────
def load_key(env_file: Path) -> str | None:
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
        print(f"ERROR: could not read env file {env_file}: {e}")
    return None


# ── API call ──────────────────────────────────────────────────────────────────
def generate(
    prompt: str,
    size: str,
    background: str,
    quality: str,
    ref_paths: list[Path],
    high_fidelity: bool,
) -> bytes | None:
    data = {
        "model": "gpt-image-1",
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "background": background,
        "output_format": "png",
        "n": "1",
    }
    for attempt in range(4):
        try:
            if ref_paths:
                files = [
                    ("image[]", (p.name, p.read_bytes(), "image/png"))
                    for p in ref_paths
                ]
                d = dict(data)
                if high_fidelity:
                    d["input_fidelity"] = "high"
                resp = requests.post(
                    API_EDITS,
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files=files,
                    data=d,
                    timeout=400,
                )
            else:
                resp = requests.post(
                    API_GEN,
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=data,
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


# ── Runner ────────────────────────────────────────────────────────────────────
def iter_jobs(active: dict, only: str | None, treatment: str | None, limit: int | None):
    only_set = {n.strip() for n in only.split(",")} if only else None
    for cat, base in active.items():
        items = list(base["items"].items())
        if limit:
            items = items[:limit]
        for name, spec in items:
            if only_set and name not in only_set:
                continue
            if (
                treatment
                and cat == "backgrounds"
                and spec.get("treatment") != treatment
            ):
                continue
            yield cat, base, name, spec


def cost_of(quality: str) -> float:
    return {"low": 0.02, "medium": 0.05, "high": 0.25}.get(quality, 0.25)


def main():
    global OPENAI_API_KEY
    ap = argparse.ArgumentParser(
        description="Generate Tingen hero assets via gpt-image-1"
    )
    ap.add_argument("--dry-run", action="store_true", help="print plan, no API calls")
    ap.add_argument(
        "--force", action="store_true", help="regenerate even if output exists"
    )
    ap.add_argument(
        "--category", choices=list(CATEGORY_DEFAULTS), help="only this category"
    )
    ap.add_argument(
        "--only",
        type=str,
        help="only this item name (or a comma-separated list of names)",
    )
    ap.add_argument(
        "--treatment",
        choices=["establish", "topdown", "district", "district_flat"],
        help="backgrounds: only this treatment",
    )
    ap.add_argument("--limit", type=int, help="cap items per category (testing)")
    ap.add_argument("--quality", choices=["low", "medium", "high"], default="high")
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    args = ap.parse_args()

    active = CATEGORY_DEFAULTS
    if args.category:
        active = {args.category: CATEGORY_DEFAULTS[args.category]}

    jobs = list(iter_jobs(active, args.only, args.treatment, args.limit))
    est = len(jobs) * cost_of(args.quality)
    print("Tingen Hero Asset Generator (gpt-image-1)")
    print(f"  output : {OUT_DIR}")
    print(f"  jobs   : {len(jobs)} images @ {args.quality}")
    print(f"  est.   : ${est:.2f}")
    print(f"  mode   : {'DRY RUN' if args.dry_run else 'LIVE'}")

    if not args.dry_run:
        OPENAI_API_KEY = load_key(args.env_file)
        if not OPENAI_API_KEY:
            print(f"ERROR: OPENAI_API_KEY not found (env or {args.env_file})")
            sys.exit(1)
        print(f"  key    : loaded ({len(OPENAI_API_KEY)} chars)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = (
        json.loads(MANIFEST_PATH.read_text())
        if MANIFEST_PATH.exists()
        else {"assets": []}
    )

    done = skip = fail = 0
    for i, (cat, base, name, spec) in enumerate(jobs, 1):
        out_dir = OUT_DIR / cat
        out_dir.mkdir(parents=True, exist_ok=True)
        fpath = out_dir / f"{name}.png"
        if fpath.exists() and not args.force:
            skip += 1
            continue

        ref_paths, high_fidelity = resolve_refs(cat, name, spec)
        has_canon = bool(spec.get("ref"))
        prompt = build_prompt(cat, name, spec, has_canon)
        size = base["size"]
        background = base["background"]
        treat = spec.get("treatment", "")
        tag = f"{cat}/{name}" + (f" [{treat}]" if treat else "")
        refnote = (
            f"refs={[p.name for p in ref_paths]} fid={'high' if high_fidelity else 'low'}"
            if ref_paths
            else "no-ref (generations)"
        )

        if args.dry_run:
            print(f"  [{i}/{len(jobs)}] {tag} ({size}, {background}) {refnote}")
            print(f"        {prompt[:150]}...")
            continue

        print(
            f"  [{i}/{len(jobs)}] {tag} ({size}, {background}, {args.quality}) {refnote}"
        )
        t0 = time.time()
        img = generate(prompt, size, background, args.quality, ref_paths, high_fidelity)
        if img:
            fpath.write_bytes(img)
            manifest["assets"] = [
                e
                for e in manifest["assets"]
                if not (e["category"] == cat and e["name"] == name)
            ]
            manifest["assets"].append(
                {
                    "category": cat,
                    "name": name,
                    "path": f"out_image2/{cat}/{name}.png",
                    "prompt": prompt,
                    "size": size,
                    "background": background,
                    "quality": args.quality,
                    "refs": [p.name for p in ref_paths],
                    "input_fidelity": "high" if high_fidelity else "low",
                    "treatment": treat,
                    "endpoint": "edits" if ref_paths else "generations",
                }
            )
            MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
            done += 1
            print(f"    OK ({len(img)//1024}KB, {round(time.time()-t0)}s)")
        else:
            fail += 1
        time.sleep(0.3)

    print(f"\nDone: {done} generated, {skip} existing, {fail} failed")
    if not args.dry_run:
        print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
