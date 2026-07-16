#!/usr/bin/env python3
"""Animation STRIPS for monster combat_forms (N6 Pass 2): 8-frame side-view sheets,
1536x1024, generated via gpt-image then keyed + per-frame bbox-normalized so
CombatExecutor's full-frame-height scaling renders figures at standee scale (fixes
the D-A6 trap: raw gens leave figures at ~35-45% of frame height).
Run from the MAIN LOOP:  python3 anim_strips.py --env-file /path/to/.env [--only wren_predator_attack_side]
Stage: out_image2/anim_strips/<name>.png  ->  copy to tingen/assets/anim/ when placed.
"""
from __future__ import annotations
import sys, io
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
import generate_tingen_image2 as g
from rembg import remove, new_session

OUT = g.OUT_DIR / "anim_strips"
RAW = OUT / "_raw"
QUALITY = "medium"
_SESSION = None
FRAME_W, SHEET_W, SHEET_H = 192, 1536, 1024
CONTENT_H = 0.86  # normalized figure height within each frame after bbox-crop

STRIP = (
    "An 8-frame 2D game animation SPRITE SHEET, one single horizontal row of exactly 8 equal "
    "columns, the SAME creature in every frame at the SAME scale and the SAME ground line, "
    "side view facing right, frames read left to right as one smooth motion; the creature stays STRICTLY in profile facing right in EVERY frame, never turning toward or away from the camera, keeping the same full silhouette mass in all 8 frames. Grim painterly "
    "semi-realistic Victorian-occult horror style (soot, ash, oxblood, bone), matching a "
    "Lord-of-the-Mysteries Beyonder-horror bestiary. Each frame: the ENTIRE creature fully "
    "inside its column with clear margin, never cropped, never touching column edges. Flat "
    "solid neutral grey background, no panel borders, no numbers, no text."
)

SUBJECTS: dict[str, tuple[str, str]] = {
    # name: (creature description, motion description)
    "wren_predator_attack_side": (
        "a tall gaunt Beyonder hunter-horror in a tattered dark riding coat, fanged hunting maw, too-long clawed arms, a broken revolver fused to one hand",
        "a lunging claw attack: crouch, coil, lunge forward with claws sweeping, follow-through, recover to a hunting stance",
    ),
    "mack_beast_attack_side": (
        "a hulking barnacled harbor-horror with waterlogged grey flesh, a lamprey-toothed maw, living rope coils and rusted hooks growing from its hunched back",
        "a heavy overhead hook-and-rope slam: rear up, swing the hooked arm down, impact crouch, drag back, resettle",
    ),
    "neil_monster_attack_side": (
        "a gaunt hunched scholar-horror whose torso is split open into a starlit void, extra pale eyes on brow and hands, constellation-light and torn parchment trailing",
        "a star-rite cast: raise both hands, the void chest flaring brighter, hurl a mote of starlight forward, robes and parchment blown back, settle",
    ),
    "finch_monster_attack_side": (
        "a young clerk-horror with parchment skin crawling with occult script, black star-ink eyes, an open glowing book fused into his chest, ledger-ribbons spiralling",
        "an ink-flood cast performed STANDING IN PLACE with feet planted on the same spot in every frame (no walking, no stepping): clutch the chest-book, pages flare bright, sweep one arm casting a lash of black ink forward, ribbons whipping, then recover — with a WIDE empty gap separating each of the 8 columns, figures never close together or overlapping",
    ),
    "beyond_hunter_attack_side": (
        "a spectral stalking figure in a wide black coat and brimmed hat, face a smear of static shadow with pale pinprick eyes, elongated grasping fingers, half-dissolving into gray fog",
        "a phasing grasp attack: dissolve slightly into fog, glide forward, both elongated hands snatching out, re-form, settle back",
    ),
}

def key_and_normalize(raw_png: bytes) -> Image.Image:
    """GRID-ADAPTIVE cut: the model often ignores 'one row of 8' (draws 2 rows / panel
    borders). So: global-key the flat grey bg, find figure components, cluster into rows,
    take the best row of poses, and rebuild a clean 1x8 sheet with every figure scaled to
    CONTENT_H on a shared baseline (kills the D-A6 full-height-scaling trap)."""
    im = Image.open(io.BytesIO(raw_png)).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    # CORNER-SAMPLED key: the 4 corners are always background (framing prompt guarantees
    # margin); key by color-distance to each corner's color. Dominant-color keying is a
    # trap — on dark creatures the creature itself becomes a top color (mack_beast bug).
    H0, W0 = a.shape[:2]
    corners = [a[8, 8], a[8, W0 - 9], a[H0 - 9, 8], a[H0 - 9, W0 - 9]]
    bg = np.zeros(a.shape[:2], dtype=bool)
    for c in corners:
        bg |= (np.abs(a - c).sum(axis=2) < 55)
    # panel fills can differ from the outer margin: also key the single most common
    # color IF it is corner-like (close to a corner color), never a creature-dark.
    q = (a // 8 * 8).reshape(-1, 3)
    colors, counts = np.unique(q, axis=0, return_counts=True)
    mode = colors[counts.argmax()].astype(np.int16)
    if min(np.abs(mode - c).sum() for c in corners) < 90:
        bg |= (np.abs(a - mode).sum(axis=2) < 55)
    fg = ~bg
    frac = fg.mean()
    if frac < 0.02 or frac > 0.65:
        # fallback: u2net segmentation of the whole sheet
        global _SESSION
        if _SESSION is None:
            _SESSION = new_session("u2net")
        seg = Image.open(io.BytesIO(remove(raw_png, session=_SESSION, post_process_mask=True))).convert("RGBA")
        seg = seg.resize(im.size)
        fg = np.asarray(seg.getchannel("A")) > 40
        bg = ~fg
    from scipy import ndimage
    fg = ndimage.binary_opening(fg, iterations=2)
    # merge detached extremities (claw tips, debris) into their figure before labeling
    lab, n = ndimage.label(ndimage.binary_dilation(fg, iterations=10))
    if n == 0:
        raise RuntimeError("no figures found after keying")
    figs = []
    H, W = fg.shape
    for k in range(1, n + 1):
        ys, xs = np.where(lab == k)
        if len(ys) < 0.0015 * H * W:   # noise
            continue
        figs.append((xs.mean(), ys.mean(), xs.min(), ys.min(), xs.max(), ys.max(), k))
    if not figs:
        raise RuntimeError("no figure-sized components")
    # cluster rows by center-y (simple 1D split at the largest gap)
    ys_sorted = sorted(f[1] for f in figs)
    gaps = [(ys_sorted[i + 1] - ys_sorted[i], i) for i in range(len(ys_sorted) - 1)]
    rows = [figs]
    if gaps and max(gaps)[0] > H * 0.18:
        cut = ys_sorted[max(gaps)[1]]
        rows = [[f for f in figs if f[1] <= cut], [f for f in figs if f[1] > cut]]
    row = max(rows, key=len)                    # the row with the most poses
    row.sort(key=lambda f: f[0])                # left-to-right motion order
    # junk filter: drop fragments wildly off the row's median figure size
    hs = sorted(f[5] - f[3] for f in row)
    med_h = hs[len(hs) // 2]
    row = [f for f in row if 0.72 * med_h <= (f[5] - f[3]) <= 1.5 * med_h]
    if len(row) > 8:
        idx = np.linspace(0, len(row) - 1, 8).round().astype(int)
        row = [row[i] for i in idx]
    rgba = np.dstack([np.asarray(im), np.where(bg, 0, 255).astype(np.uint8)])
    keyed = Image.fromarray(rgba, "RGBA")
    ach = keyed.getchannel("A").filter(ImageFilter.MinFilter(3)).point(lambda v: 0 if v < 40 else v)
    keyed.putalpha(ach)
    out = Image.new("RGBA", (SHEET_W, SHEET_H), (0, 0, 0, 0))
    target_h = int(SHEET_H * CONTENT_H)
    baseline = SHEET_H - int(SHEET_H * (1 - CONTENT_H) / 2)
    # ONE uniform scale for every frame (consistent creature size across the motion):
    # the largest scale at which the tallest figure fits target_h AND the widest fits the frame.
    sc = min(min(target_h / (f[5] - f[3] + 1), (FRAME_W * 0.94) / (f[4] - f[2] + 1)) for f in row)
    for i8 in range(8):
        f = row[i8] if i8 < len(row) else row[-1]   # pad-repeat if the row is short
        x0, y0, x1, y1 = int(f[2]), int(f[3]), int(f[4]) + 1, int(f[5]) + 1
        fig = keyed.crop((x0, y0, x1, y1))
        own = (lab[y0:y1, x0:x1] == f[6])           # this component's pixels only
        fa = np.asarray(fig.getchannel("A")).copy()
        fa[~own] = 0
        fig.putalpha(Image.fromarray(fa))
        fig = fig.resize((max(1, int(fig.width * sc)), max(1, int(fig.height * sc))))
        x = i8 * FRAME_W + (FRAME_W - fig.width) // 2
        out.paste(fig, (x, baseline - fig.height), fig)
    return out

def main() -> None:
    if "--env-file" not in sys.argv or sys.argv.index("--env-file") + 1 >= len(sys.argv):
        print("usage: python3 anim_strips.py --env-file /path/to/.env [--only <name>]")
        sys.exit(2)
    g.OPENAI_API_KEY = g.load_key(Path(sys.argv[sys.argv.index("--env-file") + 1]))
    if not g.OPENAI_API_KEY:
        print("ERROR: no key"); sys.exit(1)
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    for name, (creature, motion) in SUBJECTS.items():
        if only and name != only:
            continue
        rawp = RAW / f"{name}.png"
        if not rawp.exists():
            print(f"[{name}] GEN ...")
            form = name.rsplit("_attack_side", 1)[0]
            standee = Path("/Users/markma/Desktop/Internship/Purm 2026/Tingen-Game/tingen/assets/enemies") / f"{form}.png"
            refs = [standee] if standee.exists() else []
            raw = g.generate(f"{STRIP} The creature (match the reference image exactly): {creature}. "
                             f"The motion across the 8 frames: {motion}.",
                             "1536x1024", "opaque", QUALITY, refs, False)
            if not raw:
                print(f"[{name}] FAILED"); continue
            rawp.write_bytes(raw)
        try:
            key_and_normalize(rawp.read_bytes()).save(OUT / f"{name}.png")
            print(f"[{name}] keyed+normalized -> {name}.png")
        except Exception as e:
            print(f"[{name}] CUT FAILED: {e} (raw kept for re-cut)")
    print(f"[anim_strips] done. {len(list(OUT.glob('*.png')))} staged")

if __name__ == "__main__":
    main()
