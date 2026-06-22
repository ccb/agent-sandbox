#!/usr/bin/env python3
"""Chibi-fy the rest of the cast (nighthawk_captain, priest, bieber_monster) into the
SAME locked dense cozy-chibi style as Klein, and package each as a Stage-A design sheet
for the animation agent's generate_tingen_anim.py pipeline.

Per character: gen FRONT (loose restyle of the existing hero sprite so identity carries),
then SIDE + BACK conditioned on that new front at HIGH fidelity for turnaround
consistency, mirror side->right, and composite a design sheet (front | side | back +
face close-up + palette) on flat warm-gray -- a drop-in anim/<char>/_design.png.

Writes ONLY under out_image2/cast_chibi/ -- touches no anim-agent files.

Out: out_image2/cast_chibi/<char>/{front,side,back,right}.png
     out_image2/cast_chibi/_handoff/{<char>_chibi_designsheet.png, <char>_chibi_master.png}
"""

from __future__ import annotations

from PIL import Image, ImageDraw

import generate_tingen_image2 as g
from klein_char_experiment import COMMON, _key

OUT = g.OUT_DIR / "cast_chibi"
HANDOFF = OUT / "_handoff"
QUALITY = "medium"
BG = (224, 221, 217)
SHEET = (1536, 1024)

CAST: dict = {
    "nighthawk_captain": {
        "ref": g.OUT_DIR / "characters/nighthawk_captain.png",
        "prop": "a slightly oversized head on a small body about 2.5 heads tall",
        "expr": "stern, grim and resolute",
        "ident": (
            "a stern Nighthawk captain in a black top hat and a long dark double-breasted caped "
            "Inverness overcoat with a brass shield badge on the chest, black leather gloves, "
            "holding a glowing brass oil lantern in one hand, square-jawed"
        ),
    },
    "priest": {
        "ref": g.OUT_DIR / "characters/priest.png",
        "prop": "a slightly oversized head on a small body about 2.5 heads tall",
        "expr": "solemn, severe and hollow-eyed",
        "ident": (
            "a gaunt balding cathedral priest with thinning grey hair and sunken cheeks, in a "
            "long dark clerical cassock buttoned down the front with a white collar and a silver "
            "cross pendant on a chain"
        ),
    },
    "bieber_monster": {
        "ref": g.OUT_DIR / "enemies/bieber_monster.png",
        "prop": "a big heavy head and a hulking compact hunched body about 3 heads tall",
        "expr": "eerie, menacing and unsettling, NOT cute and NOT friendly",
        "ident": (
            "a ritual-warped Beyonder horror with a gaunt rotted face and a single glowing red "
            "eye, a torn tattered grey Victorian suit and waistcoat, and a radiating crown of "
            "antler-like bony branch growths sprawling from its back and shoulders, long clawed "
            "limbs"
        ),
    },
}


def front_prompt(c: dict) -> str:
    return (
        f"a cozy chibi character with gently rounded proportions, {c['prop']}, smooth clean "
        "cel-shading with soft painterly rendering and NO pixelation, three-quarter front view, "
        f"simplified but expressive features with a {c['expr']} expression, a dense moody "
        "atmosphere with a muted desaturated palette and small cold gaslight accents, heavy "
        f"dramatic chiaroscuro shadows and a single warm rim light, {c['ident']}, "
        + COMMON
    )


def dir_prompt(c: dict, facing: str) -> str:
    ident = (
        "the EXACT same cozy chibi character as the reference image -- identical outfit, colors, "
        f"proportions and dense moody style; {c['ident']}"
    )
    tail = (
        "full body, idle standing pose, centered with empty margin all around, isolated on a flat "
        "transparent background, no scenery, no ground, no cast shadow, no text, no border"
    )
    if facing == "left":
        return f"{ident}, but turned to FACE LEFT in a three-quarter side view showing the left side and profile. {tail}"
    return (
        f"{ident}, but seen from BEHIND, facing directly AWAY from the viewer; we see the back of "
        f"the head/hat and the back of the costume, the face is NOT visible. {tail}"
    )


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def fit(im: Image.Image, bw: int, bh: int) -> Image.Image:
    s = min(bw / im.width, bh / im.height)
    return im.resize(
        (max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS
    )


def _close(a, b, tol=26) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def palette(im: Image.Image, k: int = 6):
    rgb = Image.new("RGB", im.size, BG)
    rgb.paste(im.convert("RGB"), mask=im.split()[3])
    q = rgb.quantize(colors=k + 3, method=Image.FASTOCTREE).convert("RGB")
    out = []
    for _cnt, col in sorted(q.getcolors(maxcolors=1 << 20), reverse=True):
        if _close(col, BG):
            continue
        out.append(col)
        if len(out) >= k:
            break
    return out


def build_sheet(front, side, back, out_path) -> None:
    sheet = Image.new("RGBA", SHEET, (*BG, 255))
    for im, cx in zip((front, side, back), (0.18, 0.45, 0.72)):
        v = fit(im, 360, 660)
        sheet.alpha_composite(v, (int(SHEET[0] * cx) - v.width // 2, 70))
    head = fit(trim(front.crop((0, 0, front.width, int(front.height * 0.5)))), 340, 300)
    sheet.alpha_composite(
        head, (SHEET[0] - head.width - 60, SHEET[1] - head.height - 60)
    )
    d = ImageDraw.Draw(sheet)
    sw, x0, y0 = 64, 70, SHEET[1] - 64 - 70
    for i, col in enumerate(palette(front, 6)):
        d.rectangle(
            [x0 + i * 72, y0, x0 + i * 72 + sw, y0 + sw],
            fill=(*col, 255),
            outline=(60, 60, 60, 255),
        )
    sheet.convert("RGB").save(out_path)


def gen(prompt, refs, hi):
    return g.generate(prompt, "1024x1024", "transparent", QUALITY, refs, hi)


def main() -> None:
    _key()
    HANDOFF.mkdir(parents=True, exist_ok=True)
    for name, c in CAST.items():
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        if not c["ref"].exists():
            print(f"  SKIP {name}: hero ref missing ({c['ref']})")
            continue
        print(f"\n== {name} ==")

        fp = d / "front.png"
        if not fp.exists():
            print("  GEN front (restyle hero) ...")
            img = gen(front_prompt(c), [c["ref"]], False)
            if not img:
                print("  FAILED front -> skip character")
                continue
            fp.write_bytes(img)
            print(f"    OK front ({len(img)//1024}KB)")

        for facing, label in (("left", "side"), ("back", "back")):
            op = d / f"{label}.png"
            if op.exists():
                continue
            print(f"  GEN {label} (high-fid on front) ...")
            img = gen(dir_prompt(c, facing), [fp], True)
            if not img:
                print(f"  FAILED {label}")
                continue
            op.write_bytes(img)
            print(f"    OK {label} ({len(img)//1024}KB)")

        front = trim(Image.open(fp).convert("RGBA"))
        if (d / "side.png").exists():
            side = trim(Image.open(d / "side.png").convert("RGBA"))
            right = side.transpose(Image.FLIP_LEFT_RIGHT)
            right.save(d / "right.png")
        else:
            side = right = None
        back = (
            trim(Image.open(d / "back.png").convert("RGBA"))
            if (d / "back.png").exists()
            else None
        )

        front.save(HANDOFF / f"{name}_chibi_master.png")
        if side is not None and back is not None:
            build_sheet(front, right, back, HANDOFF / f"{name}_chibi_designsheet.png")
            print(f"  design sheet -> _handoff/{name}_chibi_designsheet.png")
        else:
            print(f"  WARN {name}: missing side/back, design sheet skipped")

    print(f"\n  cast handoff ready: {HANDOFF}")


if __name__ == "__main__":
    main()
