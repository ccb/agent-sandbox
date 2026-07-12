#!/usr/bin/env python3
"""Generate a front-facing sprite for every Tingen NPC in the LOCKED cozy-chibi occult
style (conditioned loosely on the player_detective style anchor so the whole cast matches),
key/trim transparent, and stage under out_image2/cast_npcs/<id>.png.

Drop-in for the M16 per-NPC sprite seam: copy cast_npcs/<id>.png ->
tingen/assets/characters/<id>.png and NPC.gd shows it by convention.

Run from the MAIN LOOP (needs OPENAI_API_KEY; subagents are permission-walled on the env):
  python3 npc_sprites.py --env-file /path/to/.env   (REQUIRED; the file defines OPENAI_API_KEY)
Resumable (skips staged ids); budget-capped by MAX_GENS.
"""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image
import io

import generate_tingen_image2 as g
from rembg import remove, new_session

OUT = g.OUT_DIR / "cast_npcs"
RAW = OUT / "_raw"
_SESSION = None
STYLE_ANCHOR = g.OUT_DIR / "klein_canon/_ref_klein_tingen.png"
QUALITY = "medium"
MAX_GENS = 25

# Locked style preamble — matches the cast_chibi cozy-chibi cast + the painted city's moody palette.
STYLE = (
    "in the exact painterly style of the reference image: an elegant semi-realistic Chinese "
    "light-novel character illustration with realistic adult proportions about 7.5 heads tall, "
    "refined facial features, clean subtle linework with soft painterly rendering, a muted earthy "
    "Victorian palette of umber, sepia, charcoal, ivory and brass under soft hazy gaslight, fine "
    "fabric texture and tailoring detail, a grounded serious 1890s occult-noir costume, quiet "
    "dignified mood. A single full-body front-facing standing figure. CRITICAL FRAMING: the ENTIRE figure including the complete head and hat is fully inside the frame with a generous band of empty margin ABOVE the head and BELOW the boots - never crop the head, hat, or feet. Whole body visible from "
    "hat to boots with empty margin all around, centered. The figure stands against ONE solid "
    "flat neutral grey backdrop with no scenery, no emblem, no symbol, no text, no frame and no "
    "border - a plain backdrop only, one character only."
)

# Per-NPC identity — grounded in data/npcs.json personas.
NPCS: dict[str, str] = {
    "old_neil": "a gaunt sleepless alchemist in his sixties, ink-stained fingers, wire spectacles, wisps of grey hair, a threadbare dark waistcoat over rolled shirtsleeves",
    "clerk_voss": "a fastidious shipping clerk with oiled dark hair and an unnervingly calm face, a neat high-buttoned charcoal frock coat, a leather ledger tucked under one arm",
    "fishwife_dalia": "a broad-shouldered fishwife in an oilskin apron over rough wool, a headscarf, a ruddy weathered face, a gutting knife at her belt",
    "lamplighter_orin": "a weary lamplighter in his fifties with soot-smudged cuffs and a flat cap, holding a long brass lamplighter's pole",
    "dockhand_pell": "a tired dockhand with slumped shoulders in a rough canvas coat and a knit cap, calloused hands",
    "hawker_neille": "a leathery newspaper hawker with a satchel of pamphlets and fingerless gloves, a cap askew, a fan of newspapers under one arm",
    "maribel_hatch": "a sharp-eyed tavern keeper in an apron over a plum dress, sleeves rolled, a cloth over one shoulder",
    "constable_brom": "a beat constable in a dark custodian helmet and a caped police greatcoat with polished brass buttons, a wooden truncheon at his belt, a steady square face",
    "wm_tasker": "a broad dockside stevedore foreman with a thick moustache in a heavy work coat and leather gloves, a tally-clipboard in hand",
    "goodwife_perrin": "a laundress and char-woman in a plain grey dress and white apron, hair in a kerchief, a bundle of washing on one hip",
    "ledger_finch": "a young university records clerk in a brown jacket and round spectacles, holding one large book, tidy and quiet",
    "pip": "a small street urchin in an oversized ragged coat and a flat cap too big for him, worn boots, a quick sly grin",
    "hollis_vane": "a shabby-genteel out-of-work poet in a frayed frock coat gone at the elbows, a loose cravat, tousled hair, a flask in one hand",
    "sister_auber": "a cathedral lay-sister in a dark habit and white wimple, a steady kind face, a bread basket and ladle",
    "dr_aldous_crane": "a kindly greying physician in a dark tailcoat and waistcoat with wire spectacles and side-whiskers, a leather medical bag",
    "eulalia_vire": "a genteel widow society hostess in an elegant black mourning gown with jet beads and a lace collar, hair pinned up, a folded fan",
    "bram_kell": "a cheerful broad-armed Iron Cross butcher with a blood-flecked apron over rolled sleeves and a broad friendly face, a cleaver in one hand",
    "sable_wren": "a lean watchful thief-taker in a long dark riding coat and a wide-brim hat shadowing sharp eyes, a revolver holstered at the hip",
    "brother_cassian": "an earnest young curate with a hopeful open face in a black cassock and white collar, a small prayer book in both hands",
    "leland_mack": "a broad weathered dockside line-handler in an oilskin coat with a coil of rope over one shoulder and a boat hook, a quiet flat stare",
    "naya_brookes": "a small-time card-reader and spirit medium in a colorful fringed shawl over a dark dress, hoop earrings, a fan of tarot cards, a knowing half-smile",
}


def cut(raw_png: bytes) -> Image.Image:
    """Segment the character off ANY background with rembg (U2Net), then trim to the
    alpha bbox. Robust to the model's painterly gradient backdrops — no chroma reliance."""
    global _SESSION
    if _SESSION is None:
        _SESSION = new_session("u2net")
    out = remove(raw_png, session=_SESSION, post_process_mask=True)
    im = Image.open(io.BytesIO(out)).convert("RGBA")
    # De-fringe: erode the alpha edge 1px (drops the thin bg-colored halo rembg leaves),
    # then hard-cut anything still semi-transparent below a floor.
    from PIL import ImageFilter
    a = im.getchannel("A")
    a = a.filter(ImageFilter.MinFilter(3))
    a = a.point(lambda v: 0 if v < 40 else v)
    im.putalpha(a)
    bbox = im.getchannel("A").getbbox()
    return im.crop(bbox) if bbox else im


def main() -> None:
    # Retro B4: NO default key-file path (the old default hardcoded a sibling project's .env).
    # The key file must be named explicitly; key VALUES are never printed (presence check only).
    if "--env-file" not in sys.argv or sys.argv.index("--env-file") + 1 >= len(sys.argv):
        print("usage: python3 npc_sprites.py --env-file /path/to/.env [--rekey]")
        print("  --env-file is REQUIRED: a dotenv file defining OPENAI_API_KEY (value is never printed)")
        sys.exit(2)
    env = Path(sys.argv[sys.argv.index("--env-file") + 1])
    g.OPENAI_API_KEY = g.load_key(env)
    if not g.OPENAI_API_KEY:
        print(f"ERROR: no OPENAI_API_KEY found in {env}")
        sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    refs = [STYLE_ANCHOR] if STYLE_ANCHOR.exists() else []
    rekey_only = "--rekey" in sys.argv  # cut existing raws without generating
    print(f"[npc_sprites] anchor:{'y' if refs else 'n'} rekey_only:{rekey_only} out={OUT}")
    gens = 0
    for npc_id, ident in NPCS.items():
        rawp = RAW / f"{npc_id}.png"
        dst = OUT / f"{npc_id}.png"
        # 1) GENERATE (skip if the raw exists — the expensive artifact is preserved/resumable)
        if not rawp.exists() and not rekey_only:
            if gens >= MAX_GENS:
                print(f"[budget] hit MAX_GENS={MAX_GENS}, stopping (resume to continue)")
                break
            print(f"[{npc_id}] GEN ...")
            raw = g.generate(f"{ident}. {STYLE}", "1024x1536", "transparent", QUALITY, refs, False)
            gens += 1
            if not raw:
                print(f"[{npc_id}] FAILED (no bytes)")
                continue
            rawp.write_bytes(raw)
        if not rawp.exists():
            continue
        # 2) CUT (cheap, re-runnable — --rekey re-cuts all raws with no spend)
        im = cut(rawp.read_bytes())
        im.save(dst)
        print(f"[{npc_id}] cut -> {dst.name}  {im.size}  [{gens} gens]")
    print(f"[npc_sprites] done. raws:{len(list(RAW.glob('*.png')))}/{len(NPCS)} cut:{len(list(OUT.glob('*.png')))}/{len(NPCS)} gens:{gens}")


if __name__ == "__main__":
    main()
