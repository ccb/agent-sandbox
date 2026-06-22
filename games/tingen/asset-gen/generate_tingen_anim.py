#!/usr/bin/env python3
"""
Tingen Character Animation Sheet Generator — gpt-image-2
========================================================
Turns each of a small cast into (A) a design/model sheet and (B) a set of
8-frame action strips, drawn as a top-down 3/4 RPG character, for later slicing
into Godot SpriteFrames.

MODEL (recipe-tuning result, 2026-06-09): gpt-image-1 could NOT lay out a clean
8-cell strip — it scattered 3-6 cells at inconsistent scale (the same failure the
Yumina/Itachi flux experiment documented). gpt-image-2 produces clean, evenly
spaced, full-body 8-cell strips with a readable motion arc, so this generator
defaults to gpt-image-2. Note gpt-image-2 does NOT accept the `input_fidelity`
parameter (a gpt-image-1-only lever); the design-sheet reference alone holds
identity well on the newer model. `--model gpt-image-1` falls back to the old
behaviour (input_fidelity=high) for comparison.

Two stages (the image models have NO seed; reference images are the consistency
lever — see the design spec, §2):
  Stage A (design): ref = the approved hero sprite.
  Stage B (action): ref = the character's Stage-A design sheet — so every action
                    is on-model and consistent across actions.

Each action sheet is ONE image = one horizontal row of 8 equal cells, on a flat
neutral background with dividers (robust to slice later).

Reuses generate_tingen_image2.py's key-loading; uses its own model-aware API call.

Usage:
  python3 generate_tingen_anim.py --dry-run                       # plan only
  python3 generate_tingen_anim.py --character player_detective    # Klein, both stages
  python3 generate_tingen_anim.py --stage design                  # all design sheets
  python3 generate_tingen_anim.py --stage action --character priest
  python3 generate_tingen_anim.py --model gpt-image-1 ...         # old-model fallback
  python3 generate_tingen_anim.py                                 # the whole set (40)

Cost (high ≈ $0.25/image): 4 design + 36 action = 40 ≈ $10.
"""
from __future__ import annotations

import sys
import json
import time
import base64
import argparse
from pathlib import Path

import requests

import generate_tingen_image2 as hero  # reuse load_key (no import side effects)

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out_image2"
ANIM_DIR = OUT_DIR / "anim"
MANIFEST_PATH = OUT_DIR / "manifest_anim.json"
DEFAULT_ENV_FILE = hero.DEFAULT_ENV_FILE

API_EDITS = "https://api.openai.com/v1/images/edits"
# gpt-image-2 lays out clean 8-cell strips (gpt-image-1 scattered them). image-2
# rejects `input_fidelity`, so we only send that param for gpt-image-1.
DEFAULT_MODEL = "gpt-image-2"

# All sheets are wide strips (8 cells in a row). The only landscape size.
SHEET_SIZE = "1536x1024"
# Flat background so dividers/cells survive for slicing (transparency is unreliable
# for strips; we matte later if needed).
SHEET_BG = "opaque"

# Shared look — the cool painterly recipe proven on the hero cast (no sepia/yellow).
ANIM_LOOK = (
    "Richly detailed painterly anime / manhua illustration in the official Lord of the "
    "Mysteries art style, semi-realistic, polished volumetric cel-shading, muted COOL "
    "desaturated palette of neutral grays and cool tones with small restrained warm "
    "gaslight accents — NO sepia, NO yellow / amber color cast. Crisp, on-model, "
    "consistent character design across every cell."
)

# ── Cast (4). ref is relative to out_image2/. desc is a short identity line. ──
ANIM_CAST: dict = {
    "player_detective": {
        "ref": "characters/player_detective.png",
        "desc": ("Klein Moretti, a pale young European man in a charcoal-black caped "
                 "Inverness overcoat with deep-violet lining, white high-collar shirt and "
                 "dark cravat, black hair swept back, glowing gold eyes"),
    },
    "nighthawk_captain": {
        "ref": "characters/nighthawk_captain.png",
        "desc": ("a stern Nighthawk captain in a long dark double-breasted Inverness coat, "
                 "a brass badge, leather gloves and a top hat"),
    },
    "priest": {
        "ref": "characters/priest.png",
        "desc": ("a gaunt cathedral priest in a dark grey clerical cassock with a white "
                 "collar and a silver cross pendant, thinning grey hair"),
    },
    "bieber_monster": {
        "ref": "enemies/bieber_monster.png",
        "desc": ("a hulking ritual-warped Beyonder horror in a torn bloodstained Victorian "
                 "suit, distended muscle and bony growths, extra clawed limbs, one glowing-"
                 "red eye"),
    },
}

# ── Actions: the 8-frame keyframe intent + whether the strip loops. ──
ACTIONS: dict = {
    "idle": {"loop": True, "keyframes": (
        "a subtle idle breathing and weight-shift loop — NEUTRAL stance, a slow inhale "
        "rising, a slight sway, settle, a slow exhale falling, easing back to the NEUTRAL "
        "start pose")},
    "walk": {"loop": True, "keyframes": (
        "a seamless walk cycle of two strides — contact, passing, contact, passing across "
        "the 8 frames, arms and legs swinging naturally, returning to the start pose")},
    "examine": {"loop": False, "keyframes": (
        "NEUTRAL, reach and kneel down toward the ground, inspect closely (held), begin to "
        "rise, and RETURN to the neutral stance")},
    "talk": {"loop": True, "keyframes": (
        "a small talking-gesture loop — NEUTRAL, a gentle head-and-hand gesture outward, a "
        "second beat, and back to NEUTRAL")},
    "revolver_fire": {"loop": False, "keyframes": (
        "NEUTRAL, draw the revolver, raise and aim, FIRE with a muzzle flash, recoil kick, "
        "follow-through, recover, and RETURN to neutral")},
    "paper_charm": {"loop": False, "keyframes": (
        "NEUTRAL, reach for a paper charm, raise it overhead, CAST it with a glowing glyph, "
        "release, recover, and RETURN to neutral")},
    "hurt": {"loop": False, "keyframes": (
        "NEUTRAL, a sharp impact flinch, stagger backward, begin to recover, and RETURN to "
        "neutral")},
    "death": {"loop": False, "keyframes": (
        "NEUTRAL, take a hit, buckle at the knees, fall, and collapse — the final frame "
        "holds the collapsed pose")},
    "attack": {"loop": False, "keyframes": (
        "NEUTRAL, wind up, lunge forward, STRIKE at the moment of impact, follow-through, "
        "and recover")},
}

# ── Sheet matrix (design spec §6): character -> action -> facings to generate. ──
SHEETS: dict = {
    "player_detective": {
        "idle": ["down", "up", "side"], "walk": ["down", "up", "side"],
        "examine": ["down"], "talk": ["down"],
        "revolver_fire": ["side"], "paper_charm": ["side"], "hurt": ["down"], "death": ["down"],
    },
    "nighthawk_captain": {
        "idle": ["down", "up", "side"], "walk": ["down", "up", "side"],
        "examine": ["down"], "talk": ["down"],
    },
    "priest": {
        "idle": ["down", "up", "side"], "walk": ["down", "up", "side"],
        "examine": ["down"], "talk": ["down"],
    },
    "bieber_monster": {
        "idle": ["down", "side"], "walk": ["down", "up", "side"],
        "attack": ["side"], "hurt": ["down"], "death": ["down"],
    },
}

FACING_TEXT: dict = {
    "down": "facing toward the camera (facing down the screen)",
    "up": "seen from behind, facing away from the camera (facing up the screen)",
    "side": "in right-facing side profile (left is mirrored in-engine)",
}


# ── Job iterator ──────────────────────────────────────────────────────────────
def iter_anim_jobs(stage: str, character: str | None):
    """Yield (kind, char, action, facing). kind is 'design' or 'action'.

    stage in {'design', 'action', 'all'}. character filters to one cast key.
    """
    chars = [character] if character else list(ANIM_CAST)
    for ch in chars:
        if stage in ("design", "all"):
            yield ("design", ch, None, None)
        if stage in ("action", "all"):
            for action, facings in SHEETS[ch].items():
                for facing in facings:
                    yield ("action", ch, action, facing)


# ── Prompt builders ───────────────────────────────────────────────────────────
def build_design_prompt(char: str) -> str:
    c = ANIM_CAST[char]
    return (
        f"A top-down RPG character model sheet of {c['desc']}. "
        "Lay out the SAME character in clearly separated views on one sheet: a front view "
        "(facing the camera, downward), a back view (facing away, upward), a right-side "
        "profile view, a head-and-shoulders face close-up, and a small horizontal "
        "color-palette swatch strip of the costume's key colors. "
        "Three-quarter top-down RPG camera with a slight high angle, full body standing in "
        "a neutral pose, consistent proportions and an identical costume across every view. "
        f"{ANIM_LOOK} "
        "Flat plain light-gray studio background, evenly lit, no scenery, no props, no "
        "ground shadow, no text labels, no numbers, no frame, no border."
    )


def build_action_prompt(char: str, action: str, facing: str) -> str:
    c = ANIM_CAST[char]
    a = ACTIONS[action]
    loop_note = (" The pose in the last cell matches the first cell so the strip loops "
                 "seamlessly.") if a["loop"] else ""
    return (
        "A single horizontal sprite-animation strip: one row of EXACTLY 8 equal cells, "
        "evenly spaced and identical in size, with a slim uniform gutter — a narrow strip of "
        "empty flat background — between every pair of adjacent cells, and a thin vertical "
        "divider line centered in each gutter. The character never crosses a gutter or "
        "touches a divider; each pose sits fully inside its own cell. "
        f"The SAME character in every cell — {c['desc']} — drawn at an identical scale on the "
        f"same ground line, {FACING_TEXT[facing]}, three-quarter top-down RPG camera with a "
        "slight high angle. "
        f"Across the 8 frames the character performs a '{action}' action: {a['keyframes']}."
        f"{loop_note} "
        f"{ANIM_LOOK} "
        "Flat plain light-gray background behind every cell, no scenery, no ground shadow, "
        "no text, no numbers, no labels, no outer frame, no border."
    )


# ── Paths & refs ──────────────────────────────────────────────────────────────
def output_path(kind: str, char: str, action: str | None, facing: str | None) -> Path:
    if kind == "design":
        return ANIM_DIR / char / "_design.png"
    return ANIM_DIR / char / f"{action}_{facing}.png"


def resolve_ref(kind: str, char: str) -> Path:
    """Stage A conditions on the hero sprite; Stage B on the char's design sheet."""
    if kind == "design":
        return OUT_DIR / ANIM_CAST[char]["ref"]
    return output_path("design", char, None, None)


def build_prompt(kind: str, char: str, action: str | None, facing: str | None) -> str:
    if kind == "design":
        return build_design_prompt(char)
    return build_action_prompt(char, action, facing)


# ── Runner ────────────────────────────────────────────────────────────────────
def use_input_fidelity(model: str) -> bool:
    """Only gpt-image-1 accepts input_fidelity; gpt-image-2 rejects it (400)."""
    return model == "gpt-image-1"


def generate(prompt: str, size: str, background: str, quality: str,
             ref_paths: list[Path], model: str) -> bytes | None:
    """Model-aware /images/edits call mirroring hero.generate's retry/backoff.

    Sends input_fidelity=high only for gpt-image-1 (gpt-image-2 rejects it).
    Reads the API key from hero.OPENAI_API_KEY (set in main()).
    """
    data = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "background": background,
        "output_format": "png",
        "n": "1",
    }
    if use_input_fidelity(model):
        data["input_fidelity"] = "high"
    for attempt in range(4):
        try:
            files = [("image[]", (p.name, p.read_bytes(), "image/png")) for p in ref_paths]
            resp = requests.post(
                API_EDITS,
                headers={"Authorization": f"Bearer {hero.OPENAI_API_KEY}"},
                files=files, data=data, timeout=400,
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


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {"sheets": []}


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(HERE))
    except ValueError:
        return str(p)


def _record(manifest: dict, kind, char, action, facing, prompt, ref: Path, model: str) -> None:
    key = (char, kind, action, facing)
    manifest["sheets"] = [
        e for e in manifest["sheets"]
        if (e["character"], e["kind"], e.get("action"), e.get("facing")) != key
    ]
    manifest["sheets"].append({
        "character": char, "kind": kind, "action": action, "facing": facing,
        "path": _rel(output_path(kind, char, action, facing)),
        "prompt": prompt, "ref": _rel(ref) if ref else None,
        "model": model,
        "input_fidelity": "high" if use_input_fidelity(model) else None,
        "size": SHEET_SIZE, "background": SHEET_BG,
        "frame_count": 1 if kind == "design" else 8, "endpoint": "edits",
    })


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate Tingen character animation sheets")
    ap.add_argument("--dry-run", action="store_true", help="print plan, no API calls")
    ap.add_argument("--force", action="store_true", help="regenerate even if output exists")
    ap.add_argument("--stage", choices=["design", "action", "all"], default="all")
    ap.add_argument("--character", choices=list(ANIM_CAST), help="only this cast key")
    ap.add_argument("--limit", type=int, help="cap number of jobs (testing)")
    ap.add_argument("--quality", choices=["low", "medium", "high"], default="high")
    ap.add_argument("--model", choices=["gpt-image-2", "gpt-image-1"], default=DEFAULT_MODEL,
                    help="image model (default gpt-image-2; image-1 sends input_fidelity)")
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    args = ap.parse_args()

    jobs = list(iter_anim_jobs(args.stage, args.character))
    if args.limit is not None:
        jobs = jobs[:args.limit]
    cost = {"low": 0.02, "medium": 0.05, "high": 0.25}.get(args.quality, 0.25)
    print(f"Tingen Character Animation Generator ({args.model})")
    print(f"  output : {ANIM_DIR}")
    print(f"  jobs   : {len(jobs)} sheets @ {args.quality}  (est. ${len(jobs) * cost:.2f})")
    print(f"  mode   : {'DRY RUN' if args.dry_run else 'LIVE'}")

    if not args.dry_run:
        hero.OPENAI_API_KEY = hero.load_key(args.env_file)  # generate() reads hero's global
        if not hero.OPENAI_API_KEY:
            print(f"ERROR: OPENAI_API_KEY not found (env or {args.env_file})")
            sys.exit(1)
        print(f"  key    : loaded ({len(hero.OPENAI_API_KEY)} chars)")

    manifest = _load_manifest()
    done = skip = fail = 0
    for i, (kind, char, action, facing) in enumerate(jobs, 1):
        fpath = output_path(kind, char, action, facing)
        tag = f"{char}/{'_design' if kind == 'design' else f'{action}_{facing}'}"
        if fpath.exists() and not args.force:
            skip += 1
            continue
        ref = resolve_ref(kind, char)
        prompt = build_prompt(kind, char, action, facing)

        if args.dry_run:
            print(f"  [{i}/{len(jobs)}] {tag}  ref={ref.name}")
            print(f"        {prompt[:140]}...")
            continue

        if not ref.exists():
            # Action sheets need the design sheet first; design sheets need the hero sprite.
            hint = ("run --stage design for this character first"
                    if kind == "action" else "missing hero sprite")
            print(f"  [{i}/{len(jobs)}] {tag}  SKIP — ref not found ({ref.name}); {hint}")
            fail += 1
            continue

        fpath.parent.mkdir(parents=True, exist_ok=True)
        print(f"  [{i}/{len(jobs)}] {tag}  ref={ref.name} ({SHEET_SIZE}, {args.quality})")
        t0 = time.time()
        img = generate(prompt, SHEET_SIZE, SHEET_BG, args.quality, [ref], args.model)
        if img:
            fpath.write_bytes(img)
            _record(manifest, kind, char, action, facing, prompt, ref, args.model)
            MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
            done += 1
            print(f"    OK ({len(img)//1024}KB, {round(time.time()-t0)}s)")
        else:
            fail += 1
        time.sleep(0.3)

    print(f"\nDone: {done} generated, {skip} existing, {fail} failed/skipped")
    if not args.dry_run:
        print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
