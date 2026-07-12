#!/usr/bin/env python3
"""Body sprites for the monster combat_forms (M16 per-form seam: assets/enemies/<form>.png).
Same proven pipeline as npc_sprites.py — gpt-image portrait + rembg cutout — in the ritual-warped
Beyonder-horror style anchored on the existing bieber_monster. Run from the MAIN LOOP.
  python3 monster_sprites.py --env-file /path/to/.env   (REQUIRED; the file defines OPENAI_API_KEY)
Stage under out_image2/cast_monsters/<form>.png; copy to tingen/assets/enemies/<form>.png.
"""
from __future__ import annotations
import sys, io
from pathlib import Path
from PIL import Image, ImageFilter
import generate_tingen_image2 as g
from rembg import remove, new_session

OUT = g.OUT_DIR / "cast_monsters"
RAW = OUT / "_raw"
STYLE_ANCHOR = g.OUT_DIR / "enemies/bieber_monster.png" if (g.OUT_DIR / "enemies/bieber_monster.png").exists() else (Path("/Users/markma/Desktop/Internship/Purm 2026/Tingen-Game/tingen/assets/enemies/bieber_monster.png"))
QUALITY = "medium"
_SESSION = None

STYLE = (
    "in a grim painterly semi-realistic Lord-of-the-Mysteries horror-illustration style, a muted "
    "desaturated Victorian-occult palette (soot, ash, oxblood, bile-green, bone) with faint eerie "
    "underlight, unsettling and menacing and NOT cute. A single full-body front-facing standing "
    "creature. CRITICAL FRAMING: the ENTIRE creature is fully inside the frame with a generous band "
    "of empty margin above and below - never crop it. It stands against ONE solid flat neutral grey "
    "backdrop, no scenery, no emblem, no text, no frame, one creature only."
)

MONSTERS: dict[str, str] = {
    "wren_predator": "a ritual-warped Beyonder hunter-horror that was once a lean thief-taker: a tall gaunt figure in a tattered dark riding coat, its face split into a fanged hunting maw, too-long clawed arms, and pale hunter's eyes glowing cold, a broken revolver fused to one warped hand",
    "mack_beast": "a ritual-warped Beyonder harbor-horror that was once a broad dockside line-handler: a hulking barnacled brute with waterlogged grey flesh, a lamprey-toothed maw, coils of living rope and rusted hooks growing from its hunched back and arms, dripping brine",
    "cult_thrall": "a cultist who lost control mid-rite: a hunched robed figure in torn dark ritual robes, its face melting into a featureless screaming mask, thin over-long limbs and cracked ash-grey skin, faint occult sigils burning under the skin",
    "descended_avatar": "the half-landed avatar of an outer god: a looming humanoid silhouette of shadow and dim starlight wrapped in ragged ceremonial cloth, a featureless haloed head, several faint extra arms, radiating a cold uncanny gloom",
    "beyond_hunter": "a Beyond-touched hunter sent to kill a rogue Beyonder: a spectral stalking figure in a wide black coat and brimmed hat, its face a smear of static shadow with two pale pinprick eyes, elongated grasping fingers, half-dissolving into gray fog",
    "neil_monster": "a Hermit-pathway scholar warped by forbidden knowledge — a gaunt hunched old man in a threadbare dark waistcoat whose body has split open into a starlit void, extra pale eyes opening across his brow and hands, wisps of constellation-light and torn parchment trailing from him, wire spectacles cracked over a too-wide grin",
    "auber_monster": "a Death-pathway lay-sister consumed by grave-power — a tall shrouded figure in a tattered dark habit and rotted grey wimple, her face a hollow porcelain death-mask weeping grave-dust, skeletal hands gripping a smoking censer that trails black funerary smoke, faint spectral mourning faces surfacing in the smoke around her",
    "crane_monster": "a Spectator-pathway physician warped into an all-seeing horror — a stooped greying man in a blood-spattered dark tailcoat whose head has bloomed into a dense cluster of unblinking human eyes, more eyes opening across his hands and down his shirtfront, his wire spectacles multiplied into a crown of cracked lenses, an open empty leather medical bag hanging from one hand",
    "finch_monster": "a Hermit-pathway university records-clerk consumed by forbidden knowledge — a young man in a torn brown jacket and cracked round spectacles whose skin has turned to pale parchment crawling with shifting occult script, his eyes two black wells of star-ink, ribbons of torn ledger-pages and glowing sigils spiralling out of an open book fused into his chest, his lower jaw unhinged into a small void of drifting text",
}

def cut(raw_png: bytes) -> Image.Image:
    global _SESSION
    if _SESSION is None:
        _SESSION = new_session("u2net")
    im = Image.open(io.BytesIO(remove(raw_png, session=_SESSION, post_process_mask=True))).convert("RGBA")
    a = im.getchannel("A").filter(ImageFilter.MinFilter(3)).point(lambda v: 0 if v < 40 else v)
    im.putalpha(a)
    bbox = im.getchannel("A").getbbox()
    return im.crop(bbox) if bbox else im

def main() -> None:
    # Retro B4: NO default key-file path (the old default hardcoded a sibling project's .env).
    # The key file must be named explicitly; key VALUES are never printed (presence check only).
    if "--env-file" not in sys.argv or sys.argv.index("--env-file") + 1 >= len(sys.argv):
        print("usage: python3 monster_sprites.py --env-file /path/to/.env")
        print("  --env-file is REQUIRED: a dotenv file defining OPENAI_API_KEY (value is never printed)")
        sys.exit(2)
    env = Path(sys.argv[sys.argv.index("--env-file") + 1])
    g.OPENAI_API_KEY = g.load_key(env)
    if not g.OPENAI_API_KEY:
        print(f"ERROR: no OPENAI_API_KEY found in {env}"); sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    refs = [STYLE_ANCHOR] if STYLE_ANCHOR.exists() else []
    for fid, ident in MONSTERS.items():
        rawp = RAW / f"{fid}.png"
        if not rawp.exists():
            print(f"[{fid}] GEN ...")
            raw = g.generate(f"{ident}. {STYLE}", "1024x1536", "transparent", QUALITY, refs, False)
            if not raw:
                print(f"[{fid}] FAILED"); continue
            rawp.write_bytes(raw)
        cut(rawp.read_bytes()).save(OUT / f"{fid}.png")
        print(f"[{fid}] cut -> {fid}.png")
    print(f"[monster_sprites] done. cut:{len(list(OUT.glob('*.png')))}/{len(MONSTERS)}")

if __name__ == "__main__":
    main()
