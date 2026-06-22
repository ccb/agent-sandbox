# Tingen — Character Animation Pipeline (v1) — Design

Status: approved design; implemented (Klein recipe-tuning pass complete).
Date: 2026-06-08 (model decision updated 2026-06-09 — see §10).
Scope: generate top-down 4-directional character animation **sheets** for a small
cast via gpt-image-2 (gpt-image-1 was the original plan; see §10), for later
slicing into Godot `SpriteFrames`.

Grounded in: [`asset-gen/STYLE_GUIDE.md`](../../../asset-gen/STYLE_GUIDE.md) (the
single source of truth for look/palette/canon), the existing hero generator
[`asset-gen/generate_tingen_image2.py`](../../../asset-gen/generate_tingen_image2.py),
and the side-view reference sheets in `~/Downloads/sprite_asset` (Sauske design
sheet + per-action 8-frame strips) used as **format inspiration only** (the game
is top-down, not side-scrolling).

---

## 1. Goal & non-goals

**Goal.** Stand up a repeatable pipeline that turns each character into (a) a
**design/model sheet** and (b) a set of **8-frame action sheets**, drawn as a
top-down ¾ RPG character, consistent across frames and across actions.

**v1 output is sheets only.** Raw design sheets + 8-frame action strips land in
`asset-gen/out_image2/anim/`, reviewed by eye, re-rolled as needed.

**Non-goals (explicitly deferred to a later pass):**
- Slicing strips into individual frame PNGs.
- Writing Godot `SpriteFrames` (`.tres`) resources.
- Converting `Player.tscn` from `Sprite2D` → `AnimatedSprite2D`.
- Audio, VFX overlays, in-engine wiring.

These are noted so the sheet layout below stays slice-friendly, but none are built
in v1.

---

## 2. The consistency problem (the load-bearing design decision)

gpt-image-1 has **no seed**. Reference images + `input_fidelity` are the only
consistency levers (already proven in the hero pipeline, STYLE_GUIDE §10).

Two consequences drive the whole design:

1. **All 8 frames of an action are generated in ONE API call** (a single
   horizontal strip), so the character is internally consistent across that
   action's frames. Generating 8 frames in 8 calls would flicker (different face,
   proportions, coat details each call).

2. **Cross-action consistency comes from the design sheet.** Every action sheet is
   generated with the character's design sheet as its reference at
   `input_fidelity:high`. The design sheet is the per-character "bible."

Rejected alternatives:
- **Frame-by-frame with a rolling reference** — 8× cost, identity drift with no
  seed, error accumulation. Rejected.
- **First/last keyframe + interpolation** — needs a tweening tool we don't have;
  off-model in-betweens. Out of scope.

---

## 3. Pipeline stages

### Stage A — Design sheet (1 generation per character)
- **Ref:** the existing approved hero sprite `out_image2/characters/<name>.png`
  (front-facing full body) at `input_fidelity:high`.
- **Output:** a model sheet that establishes the views the single front sprite
  lacks — **front (down), back (up), side** — plus a face close-up and a palette
  strip. Drawn in the crisp cel-shaded anime/manhua look (STYLE_GUIDE §10 CHAR).
- **Why it earns its place:** a top-down game needs back + side facings the hero
  front sprite doesn't show; the sheet both locks those and is a richer reference
  for action generation.

### Stage B — Action sheets (1 generation per action)
- **Ref:** the character's design sheet (Stage A) at `input_fidelity:high`.
- **Output:** **one image = one horizontal row of 8 evenly-spaced frames**, on a
  **flat neutral background with frame dividers** (reliable to slice later).
- **Prompt shape:** names the 8 keyframes explicitly so the model paces the
  motion, mirroring the Sauske strips' labeling
  (`NEUTRAL → WIND-UP → … → RECOVERY → RETURN`), adapted per action.
- **Camera:** ¾ top-down RPG character, slight high angle, so figures sit on the
  Stardew-style maps — NOT the eye-level framing of the current hero sprites.

### Stage C — Review & iterate
- Sheets land in `out_image2/anim/<character>/<action>.png`.
- Eyeball each for: 8 clean evenly-spaced cells, consistent scale + ground line,
  on-model character, readable motion arc. Re-roll failures.
- The **first character (Klein) is the recipe-tuning pass** — lock the prompt and
  background/divider treatment before batching the rest.

---

## 4. Camera & orientation

- **Locomotion (idle, walk):** top-down **4-directional** — `down`, `up`, `side`.
  Left/right are mirror images, so only `side` (right-facing) is generated and
  flipped in-engine later. 4 facings → 3 generated sheets.
- **Special actions (examine, talk, combat):** single facing (the one that reads
  best for that action — `down` for examine/talk/hurt/death, `side` for
  revolver_fire / paper_charm / enemy attack).

---

## 5. Cast (4, swappable)

| Key | Role | Existing hero ref |
|---|---|---|
| `player_detective` | Klein, protagonist — full action set | `out_image2/characters/player_detective.png` |
| `nighthawk_captain` | ally NPC | `out_image2/characters/nighthawk_captain.png` |
| `priest` | NPC | `out_image2/characters/priest.png` |
| `bieber_monster` | Beyonder enemy | `out_image2/characters/bieber_monster.png` |

If a hero sprite is missing for any key, regenerate it via the existing
`generate_tingen_image2.py --only <name>` first, or fall back to the canon/style
anchor that generator already uses.

---

## 6. Sheet matrix (8 frames each)

`side` = right-facing; left is an in-engine mirror.

| Character | idle | walk | examine | talk | combat | sheets |
|---|---|---|---|---|---|---|
| `player_detective` | down, up, side | down, up, side | down | down | revolver_fire, paper_charm, hurt, death | 12 |
| `nighthawk_captain` | down, up, side | down, up, side | down | down | — | 8 |
| `priest` | down, up, side | down, up, side | down | down | — | 8 |
| `bieber_monster` | down, side | down, up, side | — | — | attack, hurt, death | 8 |

Plus **4 design sheets** (one per character).

**Total: 4 design + 36 action = 40 sheets ≈ $10** at gpt-image-1 `high`
(~$0.25/image).

### Per-action keyframe intent (the 8 frames)
- **idle** (loop): subtle breathing / weight-shift — frames ease out and back to
  the start pose so it loops seamlessly.
- **walk** (loop): contact → passing → contact → passing cycle, 2 strides over 8
  frames, seamless loop.
- **examine**: NEUTRAL → reach/kneel → inspect (hold) → rise → RETURN.
- **talk** (loop): small gesture/head-and-hand motion, returns to neutral.
- **revolver_fire**: NEUTRAL → draw → aim → fire (muzzle) → recoil →
  follow-through → recover → RETURN.
- **paper_charm**: NEUTRAL → reach for charm → raise → cast (glyph) → release →
  recover → RETURN.
- **hurt**: NEUTRAL → impact flinch → stagger → recover → RETURN.
- **death**: NEUTRAL → hit → buckle → fall → collapsed (final frame holds).
- **enemy attack**: NEUTRAL → wind-up → lunge → strike (impact) → follow-through →
  recover → RETURN.

---

## 7. Output layout

```
asset-gen/out_image2/anim/
  player_detective/
    _design.png
    idle_down.png   idle_up.png   idle_side.png
    walk_down.png   walk_up.png   walk_side.png
    examine_down.png  talk_down.png
    revolver_fire_side.png  paper_charm_side.png  hurt_down.png  death_down.png
  nighthawk_captain/ …
  priest/ …
  bieber_monster/ …
```

A `manifest_anim.json` records, per sheet: character, action, facing, prompt,
ref(s), `input_fidelity`, size, frame count, endpoint — mirroring the existing
`manifest_image2.json` so re-runs are resumable (skip existing files; never
double-charge).

---

## 8. Implementation surface

A new generator script `asset-gen/generate_tingen_anim.py`, reusing the proven
plumbing of `generate_tingen_image2.py` (`/v1/images/edits` multipart with
`image[]` refs, key loading that never prints the key, retry/backoff on 429/5xx,
resumable manifest, `--dry-run` / `--only` / `--limit`). It adds:
- a **character × action × facing** job table (§6),
- the **design-sheet** prompt builder (Stage A) and **8-frame strip** prompt
  builder (Stage B) with explicit keyframe text (§6),
- a `--stage design|action` switch and a `--character <key>` filter so Klein can
  be run end-to-end first (§9),
- strip-oriented sizing (wide canvas for an 8-cell row) and the flat
  background-with-dividers treatment (§3 Stage B).

No changes to existing scripts, scenes, or assets in v1.

---

## 9. Staging (de-risk)

1. **Klein first, end-to-end** — 1 design sheet + 12 action sheets (≈ $3.25).
   Eyeball slice-ability, scale/ground-line consistency, motion quality, and
   on-model fidelity. Tune the prompt + background/divider recipe until solid.
2. **Lock the recipe**, then batch the other three characters (≈ $7).
3. Hand the reviewed sheets off; slicing + Godot wiring is a separate later spec.

---

## 10. Main risk & mitigation

**Risk:** gpt-image-1 may not reliably produce a clean, evenly-spaced,
consistent-scale 8-cell strip with a flat/transparent background — the inspiration
sheets are suspiciously tidy and may have been hand-assembled.

**Resolution (2026-06-09 — the risk materialized, then was solved by a model upgrade):**
The Klein recipe-tuning pass confirmed the risk on **gpt-image-1**: strips came back
with 3–6 scattered cells at inconsistent scale, never a clean 8 (the same failure the
Yumina/Itachi flux experiment documented). Prompt tuning did **not** fix it.
A/B testing the newly-available **gpt-image-2** produced clean, evenly-spaced, full-body
8-cell strips with a readable motion arc directly. The pipeline therefore **defaults to
gpt-image-2**; the design-sheet reference alone holds identity on the newer model.
Note gpt-image-2 **rejects** the `input_fidelity` parameter (a gpt-image-1-only lever),
so the generator sends it only when `--model gpt-image-1` is selected (kept as a
comparison fallback). The 4-frame fallback below was **not** needed.

**Mitigations (retained):**
- Render strips on a **flat neutral background with explicit frame dividers** so
  cells are findable even if spacing wobbles (robust to slice later).
- Prompt hard for "8 equal cells, single row, identical scale and ground line,
  same character in every cell."
- Treat the **Klein run as a recipe-tuning pass** — accept re-rolls; only batch
  the rest once the layout reliably holds.
- Fallback (unused) if one-shot strips prove too unreliable: drop to **4 frames/strip**
  (coarser but easier for the model to lay out) before considering the rejected
  per-frame approach.

---

## 11. Acceptance (per sheet)

In addition to STYLE_GUIDE §8 / §10 acceptance:
1. **8 cells**, single row, evenly spaced, same scale and ground line.
2. **On-model** — character matches its design sheet (face, wardrobe, palette);
   no identity drift across cells or across actions.
3. **Top-down ¾** character framing (not eye-level); reads on a Stardew-style map.
4. **Readable motion** — the keyframe arc (§6) is legible; loops (idle/walk) return
   to their start pose.
5. **Slice-friendly** — flat background, visible cell boundaries.
