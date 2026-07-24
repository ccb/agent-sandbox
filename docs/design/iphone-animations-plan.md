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

## Status

- **Plumbing landed** (`terminal.js`): `showFigure` measures the rendered
  `.figure` width and, under `MOBILE_FIGURE_W` (560px), draws `KEY-m` when it
  exists — otherwise the base card, so untwinned cards are unaffected.
- **Two twins shipped as proof:** `road-m` and `epitaph-m`, authored in the reel
  and regenerated into `figures.js` (`test_figures.py` green, 78 cards).
  Verified headless at a 356px phone column: no page errors, both animate their
  full beat, and `epitaph-m` carves the live `window.TombFigures.context` ledger
  (score / hints / cause) legibly. The scenes were **re-composed** (not scaled
  copies); a later pass can extract a shared scene helper if duplication grows.

## Open questions for CCB

- **Breakpoint feel:** switch at ~520–560px, or do you want the phone card even
  on a half-width laptop window (i.e. purely legibility-driven)?
- **Portrait height budget:** are you OK with phone cards being noticeably
  **taller** (more vertical scroll in the transcript) in exchange for big type,
  or should they stay close to the current height with fewer elements?
- **Scope:** twin all 77 eventually, or deliberately stop at the text-carrying
  subset and let spectacle cards ride the downscale?

## Where this stands (reset — twins to be reworked)

An autonomous pass hand-drew SVG twins for most cards; the art didn't meet the
bar, so it was **removed**. Only the two reference twins are kept —
**`road-m`** (the opening cart) and **`epitaph-m`** (the tombstone) — as working
templates. Everything else is to be redrawn later (with Fable). The **framework
below stays**; only the per-card images need authoring.

### The framework that remains (don't re-derive it)

- **Selection** — `terminal.js`: `showFigure` measures the rendered `.figure`
  width and, under `MOBILE_FIGURE_W` (560px), draws `KEY-m` if it exists, else
  the base card. So the game already prefers a phone twin whenever one exists;
  untwinned cards are unaffected. (Not yet wired live in the game build.)
- **The reel** — `/animations-iphone/`: a standalone page rendering every `KEY-m`
  twin at phone width. Build with `app/build_iphone_reel.py`; deploy with
  `./app/deploy_iphone_reel.sh` (pushes ONLY that dir — never the game).
- **A twin is just another card:** author a `KEY-m` block + `<svg id="KEY-m">`
  slate in `app/prototypes/retro-animations.html`; `gen_figures.py` extracts it,
  `test_figures.py` guards drift. Keep text **verbatim from the base card's
  canon** (headers/footers/callouts) — never invent copy.

### Image dimensions & font sizes (the spec to author to)

- **Canvas:** `viewBox="0 0 640 H"`, portrait, **H ≈ 720** (tall, to give the
  type room). The base cards are ~360–420 tall; the twin gets the extra height.
- **Why bigger type:** the 640-wide card is scaled to a ~356px phone column
  (**≈ 0.56×**), so authored px shrink by ~0.56 on screen. Author at **~2.5–3×**
  the desktop size. Rules of thumb (authored px → on-phone px):
  - **Header:** ~26–30px (→ ~15–17px). Header rule at `y=44`, header text `y≈34`.
  - **Body / callouts:** ~18–22px (→ ~10–12px), stacked left at `x≈40`.
  - **Footer / caption:** ~22–24px (→ ~12–13px), centered, wrapped to ≤2 lines
    so nothing exceeds `x≈610`.
  - **Minimum:** don't author below ~16px (→ ~9px) for anything that must read.
- **Layout:** subject up top (~y90–430), big-type furniture stacked below —
  one top-to-bottom reading axis, not text rung around the scene.
- **Selection breakpoint:** twin is chosen under **560px** rendered width; it
  renders down to ~340px (an older phone) and up to ~560px.
- Unique `stipple` id per card (`dots-<key>`); keep the motion vocabulary
  (`wipe` first, `typeOn` for text, stepped motion).

### Tooling still in the session scratchpad (handy, not required)

`integrate.py KEY...` splices `cards/KEY.js` + `KEY.slate` into the reel;
`vg.py KEY-m...` renders each at 356px, reports page errors / empty cards, and
writes a contact sheet to eyeball.
