# Two-Version Animation Cards: Desktop + iPhone

*Companion to `retro-animation-workflow.md` (how a card is made) and
`retro-animations.md` (why they look the way they do). This doc reasons through
**how to give each card a phone-legible twin** without disturbing the desktop
look CCB already signed off on. Nothing here is wired yet — it is the plan.*

## 1. Why the text goes tiny (the actual mechanism)

A card is not a bitmap. Each is a **fixed-width vector/canvas block** — almost
all `["svg", 640, H]`, a few `["canvas", 640, H]` (see `META` in `figures.js`).
The terminal draws it into `<div class="figure">` and CSS does:

```css
#output .figure           { max-width: 640px; }
#output .figure svg,
#output .figure canvas    { width: 100%; height: auto; }
```

So the card is authored in a **640-unit coordinate space** and then scaled
uniformly to whatever the column is wide.

- **Laptop:** the column (`#crt`, `max-width: 52rem ≈ 832px`) lets `.figure`
  reach its full 640px → **scale ≈ 1.0**. A 13px header renders at ~13px, a
  10px footer at ~10px. This is the size the cards were tuned for — it looks
  great, as you said.
- **iPhone:** the column is ~340–375px wide → the whole 640 card scales to
  **~0.53×**. Every font shrinks with it: 13px → ~7px, 10px → ~5.3px. The
  art still reads; the **text does not**.

The root cause is therefore not the drawings — it's that **type authored in a
640 space is downscaled past its legibility floor** on a narrow column. No CSS
trick fixes this: the phone is physically narrow, and horizontal-scrolling an
animation is a non-starter. The type has to be **re-authored bigger for phones**
— which is exactly why two versions is the right instinct, and why "the text
doesn't have to be the same" is the freedom that makes it tractable.

## 2. What the architecture already gives us for free

Three properties of the current design make this much cheaper than it looks:

1. **The registry is already per-key dimensioned.** `META[key] = [kind, w, h]`
   and cards already ship at different heights (300 jar close-ups, 360 standard,
   400/420 tall). A phone twin at, say, `["svg", 640, 760]` (taller, to use the
   phone's portrait space) needs **zero registry/renderer changes** — `.render`
   + `width:100%` already handle any aspect.
2. **The engine is agnostic.** The engine cues a bare KEY on the `figure`
   channel; `showFigure(key)` in `terminal.js` does the drawing. **All variant
   selection is client-side.** No adventure-file, no `app_api.py`, no engine
   change — the whole feature lives in `terminal.js` + `figures.js` (+ the reel).
3. **Cards are independent blocks with shared helpers.** A twin can reuse the
   *scene* drawing (the line-art creature/object — the expensive, art-directed
   part) and only re-lay the **furniture** (header, rotating callouts, meters,
   footer). The furniture is where all the small text lives.

## 3. The chosen approach: keyed twins that reuse the scene

**Author a second block per card, keyed `KEY-m`** (`-m` = mobile), in the reel,
extracted by `gen_figures.py` exactly like any card, guarded by
`test_figures.py`. `showFigure` picks `KEY-m` when the column is narrow, else
`KEY`; if no twin exists yet, it falls back to `KEY` (so rollout is incremental).

Weighed against the alternatives:

| Option | Verdict |
|---|---|
| **A. Keyed `-m` twins (chosen)** | Total art-direction freedom per card (matches "text needn't match"); reuses existing per-key sizing + registry; incremental (ship one card at a time); engine untouched. Cost: a second block per card and ~2× `figures.js` size for twinned cards. |
| B. One block, `mode`-branching internals | Least duplication, but every one of the 77 `build` fns must be rewritten mode-aware and the two layouts stay entangled — hard to art-direct, invasive, risky. |
| C. CSS-only (cap width / overflow-scroll) | Rejected: a phone can't be made wider; scrolling an animation is bad UX. |
| D. Blind global font-bump on phones | Rejected: positions are hand-tuned; the doc's own war stories are about clipping/collisions. A blind ×2.5 guarantees overlap. |

The chosen approach is really **A structured to steal E's reuse**: the twin is
a *portrait recomposition* that calls the same scene-drawing code, then wraps it
in phone furniture. True duplication is confined to the furniture.

### The phone card's shape (the recipe)

- **Keep width 640, grow height** (e.g. 640×720–900). Same `width:100%` fill,
  no aspect surprises, scene coordinates reusable as-is. The extra vertical room
  is what buys legible type.
- **Author type at ~2.5–3× desktop px.** At a 340px column, 640→0.53×, so to
  land a real ~15px you author ~28px; a real ~18px heading → ~34px. Rule of
  thumb: **desktop-px × 2.6 ≈ phone-authored-px** for a ~15px physical result.
- **Cut the rotating callouts.** Rotating dashed-leader callouts assume a lean-in
  reader with time; on a phone, make the one or two that matter **static and
  large**, stacked under the scene. Drop the rest (the canon footer usually
  carries the joke alone).
- **Stack, don't ring.** Desktop rings text around the scene (corner class,
  right-anchored callouts, bottom meters). Phone: scene on top, a single column
  of big captions/footer beneath. One reading axis, top-to-bottom.
- **Preserve the dynamic hooks.** `epitaph-m` must still read
  `window.TombFigures.context` (score/hints/cause); state-branching cards
  (`ulfire` lit/unlit, jar `OPEN`) keep their branches. The motion vocabulary
  (12fps step clock, `wipe`, `typeOn`) is unchanged — it scales fine; only the
  type sizing and layout differ.

## 4. Selection: measure the column, don't sniff the device

Switch on the **actual rendered width**, not "is it an iPhone." The failure is
"card scaled below its legibility floor," which also happens in a narrow desktop
window — and a device sniff would miss that and mishandle tablets/foldables.

In `showFigure`, the box is in the DOM before `render`, so its width is known:

```js
const wantMobile = box.clientWidth < MOBILE_W;      // ~520–560px, tune live
const useKey = (wantMobile && F.has(key + "-m")) ? key + "-m" : key;
F.render(useKey, box);
```

- **Threshold ≈ 520–560px.** Full-size is 640 (scale 1.0). Switch once scale
  drops under ~0.85 (13px → <11px). Tune against a real phone.
- **Already-rendered cards are transcript history — leave them.** New cards use
  the current width; no need to re-render past ones on rotate/resize (possible
  later, not worth the complexity now).
- Respect the existing `illustrations` off-switch and `reducedMotion` path
  unchanged.

## 5. Which cards actually need a twin (triage, not all 77)

Twin the **text-carrying** cards first; pure-spectacle cards (a wipe + a
one-word-labelled creature) survive the downscale. Priority by how many players
see them and how much *must-read* text they carry:

- **Tier 1 — everyone, text-heavy:** `road` (00, opening), `epitaph` (death,
  carries the live ledger), `critch` (advice proverbs), boot/title, the jar
  close-ups (`jar-*`), `hound` (10). ~10–15 cards likely cover the majority of
  what a typical run sees.
- **Tier 2 — data-plate / proverb cards:** the instructional plates, the
  Exotica specimen cards with real callouts (`dagger`, `core`, `ulfire`,
  `shard`), the memory series.
- **Tier 3 — the long tail**, added as bandwidth allows.

`figures.js` only grows for cards that actually get a twin — the tail costs
nothing until twinned.

## 6. Workflow / testing deltas

- Author `KEY-m` blocks in `app/prototypes/retro-animations.html` with their own
  `<section>` slate (`NN-m — TITLE (phone)`); `gen_figures.py` extracts them
  unchanged; `test_figures.py` still guards drift.
- **Preview at true size.** The headless-Chromium check must shoot the twin at a
  **phone column width** (e.g. a 360px viewport), not 640 — the whole point is
  the downscaled result. Add a phone-width pass to the screenshot step.
- **Playdate is unaffected** — separate 400×240 1-bit pipeline; do **not** export
  `-m` cards to the device.
- A tiny unit check that every `KEY-m` has a base `KEY`, and (optionally) a lint
  that Tier-1 keys all have twins.

## 7. Proposed rollout

1. **Plumbing + one proof card.** Add the width-measured selection to
   `showFigure`, the `MOBILE_W` constant, and the phone-width preview step; twin
   **one** card end-to-end (`road` or `epitaph`) and verify on a real iPhone.
2. **Tier 1.** Twin the ~10–15 everyone-sees cards; deploy; re-check on device.
3. **Tier 2 → 3** incrementally; fallback keeps untwinned cards working.

## Open questions for CCB

- **Breakpoint feel:** switch at ~520–560px, or do you want the phone card even
  on a half-width laptop window (i.e. purely legibility-driven)?
- **Portrait height budget:** are you OK with phone cards being noticeably
  **taller** (more vertical scroll in the transcript) in exchange for big type,
  or should they stay close to the current height with fewer elements?
- **Scope:** twin all 77 eventually, or deliberately stop at the text-carrying
  subset and let spectacle cards ride the downscale?
