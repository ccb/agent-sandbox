# Character Animation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `asset-gen/generate_tingen_anim.py`, a resumable generator that turns each of 4 characters into one design sheet plus a set of 8-frame action strips (40 sheets total) via gpt-image-2, ready for later slicing into Godot `SpriteFrames`.

> **Model decision (2026-06-09, see spec §10):** The original plan targeted gpt-image-1. The Klein recipe-tuning pass proved gpt-image-1 cannot lay out a clean 8-cell strip (it scattered 3–6 cells). The pipeline now defaults to **gpt-image-2**, which produces clean 8-cell strips from the design-sheet ref alone. gpt-image-2 rejects `input_fidelity`, so the generator's model-aware `generate()` sends that param only for `--model gpt-image-1` (a comparison fallback). The 4-frame fallback (Task 5 Step 4) was not needed.

**Architecture:** A new standalone script reuses the *low-level plumbing* of `generate_tingen_image2.py` (key loading, the retry/backoff `generate()` API call) by importing it, and adds its own character×action×facing job table, a two-stage prompt builder (Stage A design sheet, Stage B 8-frame strip), wide-strip sizing, and a resumable `manifest_anim.json`. Pure functions (job table, prompt builders, path/skip helpers) are unit-tested with pytest; the actual API generation is run manually and reviewed by eye, Klein first (the recipe-tuning pass) before batching the rest.

**Tech Stack:** Python 3, `requests`, Pillow, pytest 9; OpenAI `/v1/images/edits` (gpt-image-2 by default, multipart with `image[]` refs; `input_fidelity:high` only on the `--model gpt-image-1` fallback). Reuses `generate_tingen_image2.py`'s `load_key`; uses its own model-aware `generate()`.

**Source spec:** [`docs/superpowers/specs/2026-06-08-character-animation-pipeline-design.md`](../specs/2026-06-08-character-animation-pipeline-design.md)

---

## File Structure

| File | Responsibility |
|---|---|
| `asset-gen/generate_tingen_anim.py` (create) | The generator: data tables (cast, actions, sheet matrix), prompt builders, job iterator, ref/path/manifest helpers, CLI `main()`. Imports `load_key` + `generate` from `generate_tingen_image2`. |
| `asset-gen/conftest.py` (create) | Empty file so pytest puts `asset-gen/` on `sys.path`, letting tests `import generate_tingen_anim`. |
| `asset-gen/tests/test_generate_tingen_anim.py` (create) | Unit tests for the pure functions (job counts, prompt content, paths). |
| `asset-gen/out_image2/anim/<char>/*.png` (generated) | Output sheets. Not committed as code; produced by live runs in Tasks 5–6. |
| `asset-gen/out_image2/manifest_anim.json` (generated) | Resume ledger mirroring `manifest_image2.json`. |

**Reuse boundary:** the anim script imports `load_key` and `generate` from `generate_tingen_image2`. That module only does work under `if __name__ == "__main__"`, so importing it is side-effect-free. `generate()` reads the module-global `generate_tingen_image2.OPENAI_API_KEY`, so the anim script must set **that** global (not a local one) before generating — handled explicitly in Task 4.

---

## Task 1: Script skeleton + data tables + job iterator

**Files:**
- Create: `asset-gen/generate_tingen_anim.py`
- Create: `asset-gen/conftest.py`
- Test: `asset-gen/tests/test_generate_tingen_anim.py`

- [ ] **Step 1: Create the empty pytest path shim**

Create `asset-gen/conftest.py` with exactly this content (a one-line comment is fine; the file's existence is what matters):

```python
# Presence of this file puts asset-gen/ on sys.path so tests can import generate_tingen_anim.
```

- [ ] **Step 2: Create the script with constants, data tables, and the job iterator**

Create `asset-gen/generate_tingen_anim.py`:

```python
#!/usr/bin/env python3
"""
Tingen Character Animation Sheet Generator — gpt-image-1
========================================================
Turns each of a small cast into (A) a design/model sheet and (B) a set of
8-frame action strips, drawn as a top-down 3/4 RPG character, for later slicing
into Godot SpriteFrames.

Two stages (gpt-image-1 has NO seed; refs + input_fidelity are the only
consistency levers — see the design spec, §2):
  Stage A (design): ref = the approved hero sprite, input_fidelity=high.
  Stage B (action): ref = the character's Stage-A design sheet, high — so every
                    action is on-model and consistent across actions.

Each action sheet is ONE image = one horizontal row of 8 equal cells, on a flat
neutral background with dividers (robust to slice later).

Reuses generate_tingen_image2.py's proven key-loading + retry/backoff API call.

Usage:
  python3 generate_tingen_anim.py --dry-run                       # plan only
  python3 generate_tingen_anim.py --character player_detective    # Klein, both stages
  python3 generate_tingen_anim.py --stage design                  # all design sheets
  python3 generate_tingen_anim.py --stage action --character priest
  python3 generate_tingen_anim.py                                 # the whole set (40)

Cost (gpt-image-1 high ≈ $0.25/image): 4 design + 36 action = 40 ≈ $10.
"""
from __future__ import annotations

import sys
import json
import time
import argparse
from pathlib import Path

import generate_tingen_image2 as hero  # reuse load_key + generate (no import side effects)

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out_image2"
ANIM_DIR = OUT_DIR / "anim"
MANIFEST_PATH = OUT_DIR / "manifest_anim.json"
DEFAULT_ENV_FILE = hero.DEFAULT_ENV_FILE

# All sheets are wide strips (8 cells in a row). gpt-image-1's only landscape size.
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
```

- [ ] **Step 3: Write the failing tests for the data tables + iterator**

Create `asset-gen/tests/test_generate_tingen_anim.py`:

```python
import generate_tingen_anim as g


def test_cast_has_four_characters():
    assert set(g.ANIM_CAST) == {
        "player_detective", "nighthawk_captain", "priest", "bieber_monster"}


def test_sheet_counts_per_character():
    # design spec §6: 12 / 8 / 8 / 8 action sheets.
    def n(ch):
        return sum(len(v) for v in g.SHEETS[ch].values())
    assert n("player_detective") == 12
    assert n("nighthawk_captain") == 8
    assert n("priest") == 8
    assert n("bieber_monster") == 8


def test_total_jobs_all_stages():
    jobs = list(g.iter_anim_jobs("all", None))
    design = [j for j in jobs if j[0] == "design"]
    action = [j for j in jobs if j[0] == "action"]
    assert len(design) == 4
    assert len(action) == 36
    assert len(jobs) == 40


def test_stage_filter():
    assert len(list(g.iter_anim_jobs("design", None))) == 4
    assert len(list(g.iter_anim_jobs("action", None))) == 36


def test_character_filter():
    jobs = list(g.iter_anim_jobs("all", "player_detective"))
    assert all(j[1] == "player_detective" for j in jobs)
    assert len(jobs) == 13  # 1 design + 12 action
```

- [ ] **Step 4: Run the tests**

Run: `cd "asset-gen" && python3 -m pytest tests/test_generate_tingen_anim.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add asset-gen/generate_tingen_anim.py asset-gen/conftest.py asset-gen/tests/test_generate_tingen_anim.py
git commit -m "feat(anim): scaffold animation generator data tables + job iterator"
```

---

## Task 2: Prompt builders (design sheet + 8-frame strip)

**Files:**
- Modify: `asset-gen/generate_tingen_anim.py` (append two functions)
- Test: `asset-gen/tests/test_generate_tingen_anim.py` (append tests)

- [ ] **Step 1: Append the prompt builders to the script**

Append to `asset-gen/generate_tingen_anim.py` (after `iter_anim_jobs`):

```python
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
        "A single horizontal sprite-animation strip: one row of EXACTLY 8 equal cells "
        "separated by thin vertical divider lines, the cells evenly spaced and identical in "
        "size. "
        f"The SAME character in every cell — {c['desc']} — drawn at an identical scale on the "
        f"same ground line, {FACING_TEXT[facing]}, three-quarter top-down RPG camera with a "
        "slight high angle. "
        f"Across the 8 frames the character performs a '{action}' action: {a['keyframes']}."
        f"{loop_note} "
        f"{ANIM_LOOK} "
        "Flat plain light-gray background behind every cell, no scenery, no ground shadow, "
        "no text, no numbers, no labels, no outer frame, no border."
    )
```

- [ ] **Step 2: Append the failing tests**

Append to `asset-gen/tests/test_generate_tingen_anim.py`:

```python
def test_design_prompt_content():
    p = g.build_design_prompt("player_detective")
    assert "model sheet" in p
    assert "palette" in p
    assert "back view" in p
    assert "NO sepia" in p
    assert "Klein Moretti" in p


def test_action_prompt_has_eight_and_facing_and_keyframes():
    p = g.build_action_prompt("player_detective", "revolver_fire", "side")
    assert "8 equal cells" in p
    assert "right-facing side profile" in p
    assert "muzzle flash" in p          # from the revolver_fire keyframes
    assert "NO sepia" in p


def test_action_prompt_loop_note_only_for_loops():
    looped = g.build_action_prompt("priest", "idle", "down")
    oneshot = g.build_action_prompt("priest", "examine", "down")
    assert "loops seamlessly" in looped
    assert "loops seamlessly" not in oneshot


def test_action_prompt_facing_up_is_from_behind():
    p = g.build_action_prompt("nighthawk_captain", "walk", "up")
    assert "from behind" in p
```

- [ ] **Step 3: Run the tests**

Run: `cd "asset-gen" && python3 -m pytest tests/test_generate_tingen_anim.py -v`
Expected: all tests PASS (9 total now).

- [ ] **Step 4: Commit**

```bash
git add asset-gen/generate_tingen_anim.py asset-gen/tests/test_generate_tingen_anim.py
git commit -m "feat(anim): design-sheet and 8-frame strip prompt builders"
```

---

## Task 3: Output paths, ref resolution, and manifest skip helper

**Files:**
- Modify: `asset-gen/generate_tingen_anim.py` (append helpers)
- Test: `asset-gen/tests/test_generate_tingen_anim.py` (append tests)

- [ ] **Step 1: Append path + ref helpers to the script**

Append to `asset-gen/generate_tingen_anim.py`:

```python
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
```

- [ ] **Step 2: Append the failing tests**

Append to `asset-gen/tests/test_generate_tingen_anim.py`:

```python
from pathlib import Path


def test_output_paths():
    d = g.output_path("design", "priest", None, None)
    a = g.output_path("action", "priest", "walk", "side")
    assert d == g.ANIM_DIR / "priest" / "_design.png"
    assert a == g.ANIM_DIR / "priest" / "walk_side.png"


def test_design_ref_is_hero_sprite():
    r = g.resolve_ref("design", "bieber_monster")
    assert r == g.OUT_DIR / "enemies/bieber_monster.png"


def test_action_ref_is_design_sheet():
    r = g.resolve_ref("action", "player_detective")
    assert r == g.ANIM_DIR / "player_detective" / "_design.png"


def test_build_prompt_dispatches_by_kind():
    assert "model sheet" in g.build_prompt("design", "priest", None, None)
    assert "8 equal cells" in g.build_prompt("action", "priest", "idle", "down")
```

- [ ] **Step 3: Run the tests**

Run: `cd "asset-gen" && python3 -m pytest tests/test_generate_tingen_anim.py -v`
Expected: all tests PASS (13 total now).

- [ ] **Step 4: Commit**

```bash
git add asset-gen/generate_tingen_anim.py asset-gen/tests/test_generate_tingen_anim.py
git commit -m "feat(anim): output-path, ref-resolution, and prompt-dispatch helpers"
```

---

## Task 4: Wire the runner (CLI + `main`) and verify the dry-run plan

**Files:**
- Modify: `asset-gen/generate_tingen_anim.py` (append `main`)

This task wires the actual API loop. The generation call itself isn't unit-tested (it costs money and is non-deterministic); instead we verify the **dry-run plan** prints the correct 40-job table, and that `--stage action` warns when a design sheet is missing.

- [ ] **Step 1: Append `main()` to the script**

Append to `asset-gen/generate_tingen_anim.py`:

```python
# ── Runner ────────────────────────────────────────────────────────────────────
def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {"sheets": []}


def _record(manifest: dict, kind, char, action, facing, prompt, ref: Path) -> None:
    key = (char, kind, action, facing)
    manifest["sheets"] = [
        e for e in manifest["sheets"]
        if (e["character"], e["kind"], e.get("action"), e.get("facing")) != key
    ]
    manifest["sheets"].append({
        "character": char, "kind": kind, "action": action, "facing": facing,
        "path": str(output_path(kind, char, action, facing).relative_to(HERE)),
        "prompt": prompt, "ref": str(ref.relative_to(HERE)) if ref else None,
        "input_fidelity": "high", "size": SHEET_SIZE, "background": SHEET_BG,
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
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    args = ap.parse_args()

    jobs = list(iter_anim_jobs(args.stage, args.character))
    if args.limit:
        jobs = jobs[:args.limit]
    cost = {"low": 0.02, "medium": 0.05, "high": 0.25}.get(args.quality, 0.25)
    print("Tingen Character Animation Generator (gpt-image-1)")
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
        img = hero.generate(prompt, SHEET_SIZE, SHEET_BG, args.quality, [ref], high_fidelity=True)
        if img:
            fpath.write_bytes(img)
            _record(manifest, kind, char, action, facing, prompt, ref)
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
```

- [ ] **Step 2: Run the full unit-test suite (no regressions)**

Run: `cd "asset-gen" && python3 -m pytest tests/test_generate_tingen_anim.py -v`
Expected: all 13 tests PASS.

- [ ] **Step 3: Verify the dry-run plan prints 40 jobs**

Run: `cd "asset-gen" && python3 generate_tingen_anim.py --dry-run`
Expected: header shows `jobs : 40 sheets @ high (est. $10.00)`, then 40 numbered lines — 4 ending in `/_design` and 36 action lines (e.g. `player_detective/idle_down`, `bieber_monster/attack_side`). No API key is loaded in dry-run.

- [ ] **Step 4: Verify Klein-only dry-run scopes to 13 jobs**

Run: `cd "asset-gen" && python3 generate_tingen_anim.py --dry-run --character player_detective`
Expected: `jobs : 13 sheets` (1 design + 12 action), every line under `player_detective/`.

- [ ] **Step 5: Commit**

```bash
git add asset-gen/generate_tingen_anim.py
git commit -m "feat(anim): wire CLI runner, resumable manifest, and dry-run plan"
```

---

## Task 5: Klein recipe-tuning pass (LIVE, manual review)

The first character is the recipe-tuning pass (design spec §9.1). Generate Klein end-to-end, review by eye, and re-roll until the layout reliably holds **before** batching the rest. This is a manual, judgment step — there is no automated assertion for image quality.

**Files:**
- Generates: `asset-gen/out_image2/anim/player_detective/*.png` (+ `manifest_anim.json`)

- [ ] **Step 1: Generate Klein's design sheet first (Stage A)**

The action sheets reference the design sheet, so it must exist first.
Run: `cd "asset-gen" && python3 generate_tingen_anim.py --stage design --character player_detective`
Expected: `1 sheets`, writes `out_image2/anim/player_detective/_design.png`.

- [ ] **Step 2: Review the design sheet by eye**

Open `asset-gen/out_image2/anim/player_detective/_design.png`. Acceptance (design spec §11): shows front/back/side + face close-up + palette strip; on-model Klein (charcoal caped coat, gold eyes); top-down ¾ framing; cool palette, no sepia. If it fails, re-run Step 1 with `--force` until acceptable. Do not proceed until the design sheet is good — every action sheet inherits it.

- [ ] **Step 3: Generate Klein's 12 action sheets (Stage B)**

Run in the background (12 high-quality images ≈ 10–20 min; long generations must not block):
Run: `cd "asset-gen" && python3 generate_tingen_anim.py --stage action --character player_detective` with `run_in_background: true`.
Expected on completion: `12 generated`, files like `idle_down.png`, `walk_side.png`, `revolver_fire_side.png`, `death_down.png` under `anim/player_detective/`.

- [ ] **Step 4: Review the action strips against the acceptance checklist**

For each of the 12 strips check (design spec §11): 8 evenly-spaced cells, single row, identical scale + ground line; on-model and consistent with the design sheet; top-down ¾; readable motion arc; loops (idle/walk) return to the start pose; flat background with visible cell boundaries.
Re-roll any failures: `python3 generate_tingen_anim.py --stage action --character player_detective --force --limit 1` after temporarily narrowing, or re-run the whole character with `--force`.
If 8-cell strips prove unreliable even after prompt tuning, apply the spec's fallback (design spec §10): drop to 4 frames/strip — edit `ACTIONS` keyframe text and the prompt's "EXACTLY 8" to 4, re-run, re-review.

- [ ] **Step 5: Commit the reviewed Klein sheets + manifest**

```bash
git add asset-gen/out_image2/anim/player_detective asset-gen/out_image2/manifest_anim.json
git commit -m "feat(anim): Klein design sheet + 12 action strips (recipe-tuning pass)"
```

---

## Task 6: Batch the remaining three characters (LIVE)

Once Klein's recipe is locked (Task 5), batch the other three (design spec §9.2, ≈ $7).

**Files:**
- Generates: `asset-gen/out_image2/anim/{nighthawk_captain,priest,bieber_monster}/*.png`

- [ ] **Step 1: Generate the three design sheets first**

Run sequentially (design sheets gate their action sheets):
```bash
cd "asset-gen" && python3 generate_tingen_anim.py --stage design --character nighthawk_captain \
 && python3 generate_tingen_anim.py --stage design --character priest \
 && python3 generate_tingen_anim.py --stage design --character bieber_monster
```
Expected: three `_design.png` files written. Review each by eye (Task 5 Step 2 criteria); `--force` re-roll any that fail before proceeding.

- [ ] **Step 2: Batch the remaining action sheets in the background**

With all design sheets present, the resumable runner skips Klein's existing files and fills the other 24 action sheets.
Run: `cd "asset-gen" && python3 generate_tingen_anim.py --stage action` with `run_in_background: true`.
Expected on completion: `24 generated, 12 existing` (Klein's already done), `0 failed`.

- [ ] **Step 3: Review all remaining strips**

Apply the Task 5 Step 4 acceptance checklist to each new strip. Re-roll failures per character with `--force`.

- [ ] **Step 4: Final full-set dry-run confirms nothing is missing**

Run: `cd "asset-gen" && python3 generate_tingen_anim.py --dry-run` and confirm the manifest covers all 40 — or run the live command once more (it will report `40 existing, 0 generated`).

- [ ] **Step 5: Commit the full sheet set**

```bash
git add asset-gen/out_image2/anim asset-gen/out_image2/manifest_anim.json
git commit -m "feat(anim): design sheets + action strips for captain, priest, bieber_monster"
```

---

## Self-Review (completed during planning)

- **Spec coverage:** §2 consistency (refs + high fidelity) → Task 3 `resolve_ref` (design→hero sprite, action→design sheet) + Task 4 `high_fidelity=True`. §3 stages → Tasks 1–4 (data/prompts/runner) + Tasks 5–6 (generation). §4 4-directional + single-facing specials → `SHEETS`/`FACING_TEXT` (Task 1) + `build_action_prompt` (Task 2). §5 cast of 4 → `ANIM_CAST` (Task 1; bieber ref corrected to `enemies/`). §6 sheet matrix + keyframes → `SHEETS` + `ACTIONS` (Task 1), asserted 12/8/8/8 and 40 total. §7 output layout + manifest → `output_path` (Task 3) + `_record`/`manifest_anim.json` (Task 4). §8 reuse plumbing + `--stage`/`--character` → Task 1 import + Task 4 CLI. §9 staging (Klein first, lock, batch) → Tasks 5–6. §10 strip risk + 4-frame fallback → Task 5 Step 4. §11 acceptance → Task 5 Step 4 / Task 6 Step 3 review checklists.
- **Placeholder scan:** none — all code blocks and commands are complete.
- **Type consistency:** `iter_anim_jobs` yields `(kind, char, action, facing)`; consumed identically in `main`. `output_path`/`resolve_ref`/`build_prompt` share the same `(kind, char, action, facing)` signature. Manifest keyed on `(character, kind, action, facing)` in both `_record` and `_load_manifest` consumers. `SHEET_SIZE`/`SHEET_BG` defined once, used in `main` and `_record`.
```
