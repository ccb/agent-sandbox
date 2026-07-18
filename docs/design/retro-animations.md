# Retro Animations for the Tomb Terminal

*Branch: `feat/retro-animations`. Companion to issue #430 (Rod Lord × Leo Hunt
art direction). Status: design.*

## 1. What Rod Lord actually did (research)

The HHGG "computer graphics" were **hand-made cel animation engineered to look
electronic** — Pearce Studios, six people, ~45 minutes of material in ~3
months, BAFTA-winning. The technique, from Lord's own accounts:

- **Litho film, not painted cels.** Black Rotring pen line art on celluloid,
  then **photographically reversed** in the darkroom to clear lines on solid
  black. Letraset/IBM-typewriter text, reversed the same way. "Cleaner and
  more vivid" than paint.
- **Backlit on a rostrum camera.** The reversed litho sat on a lightbox, so
  every line and fill is *transmitted light* — that's the luminous, monitor-
  like glow. Color came from **gel filters cut to fit the clear areas**.
- **Text reveals by mask.** A card mask with a clear slot, walked across the
  text a frame at a time — the letter-by-letter teletype feel.
- **Wipes, not dissolves.** Transitions were "a swift horizontal or vertical
  wipe **with a bright incoming leading edge**" — reads as electronics, not
  film.
- **Angular, line-heavy design.** BBC designer Douglas Burd pushed the art
  "more angular and with more lines rather than solids" to kill any cartoon
  feel.
- **Busyness over complexity.** The underlying animation was "necessarily
  very simple and basic"; the *feeling* of activity came from constant small
  events — labels appearing, arrows extending, diagrams annotating
  themselves.

Every one of those has a direct, cheap web equivalent. The insight to steal
is not "draw like 1981" — it's **diagram + label + reveal**: the Guide never
showed a picture, it showed an *explanation happening*.

## 2. Two styles, one surface

### Style A — "Guide entry" cards (the Rod Lord translation)

SVG, hand-authored, luminous-on-black:

| Rod Lord | Web equivalent |
|---|---|
| Backlit litho line art | SVG strokes in phosphor colors on `#020608`, `filter: drop-shadow` glow |
| Gel-filter fills | Flat translucent fills (`fill-opacity: .25–.4`), 2–3 colors max |
| Mask-slot text reveal | `clip-path` rect animated in steps, or per-`tspan` reveal on a timer |
| Wipe with bright leading edge | A 2px bright rect sweeping ahead of a clipping wipe |
| Angular, line-heavy | Straight segments + hard arcs only; no curves that read "drawn" |
| Busyness | Staggered label/arrow/callout timeline; something happens every ~400ms |
| Hand-made frame steps | `animation-timing-function: steps(n)` everywhere; nothing tweens smoothly |

Palette: our blue phosphor (`#4db8ff`) as the master line color, Vaarn orange
for the fungus/danger annotations, white for the bright wipe edge. Labels in
the terminal's monospace, ALL CAPS, with index numbers and leader lines —
Guide diagrams were basically annotated patents.

### Style B — Rotating wireframes (the "3D from illustrations" idea)

A **dependency-free canvas renderer** (~150 lines: project vertices, rotate Y
slowly, draw edges). No three.js — the site is CSP-strict/self-contained, and
we don't need faces, materials, or lighting: **outlines only** is the look.
The existing CRT dressing (scanlines, flicker, glow) composites over the
canvas for free.

Mesh pipeline, in order of preference:

1. **Hand-model the hero objects** (Blender, minutes each — they're simple
   solids): the tomb slab with its three faces, the coffin sphere, a canopic
   jar, the glowstone. Export edge lists as tiny JSON (`{v: [[x,y,z]...],
   e: [[i,j]...]}`), hundreds of bytes each.
2. **Image→3D models from the illustrations** (TripoSR/Meshy-class tools,
   run offline) → decimate hard in Blender → export edges. Worth trying for
   organic shapes (the Fungal Horror), but raw meshes are noisy; expect
   cleanup. This is the literal "create 3D objects from illustrations" path
   and it's viable, just not the cheapest first step.
3. **Procedural specials.** The manifold box wants to be a **tesseract
   projection** — a rotating 4D→2D wireframe is 30 lines of math and is
   *exactly* the hypergeometry the game now describes. This one can't be
   modeled from an illustration because that's the joke.

Hidden-line removal is what separates "80s vector display" from "mess": for
convex-ish hero objects, backface culling on the source faces before edge
extraction is enough; skip true HLR.

### Shared surface

One `<figure class="illust">` block that both styles render into, three uses:

- **Inline in the transcript** — `EXAMINE <hero item>` emits a `figure`
  event alongside the text (new payload channel from `app_api`, carrying an
  animation id; JS looks it up in a registry). Text remains primary; the
  figure is an Infocom-box-art moment, not a requirement.
- **Title screen** — the tomb slab wireframe slowly rotating under the
  title, or a Guide-card of the tomb annotating itself.
- **Endings** — win: the coffin whole, rotating; death: the wheel of bats.

All behind a settings toggle (`ILLUSTRATIONS: ON/OFF`), consistent with every
other piece of dressing, and off in `textsize: large` accessibility mode by
default? (decide with CCB).

## 3. Recommendation & build order

Style A is the identity; Style B is the garnish. But B is *much* cheaper to
prototype (one renderer, tiny meshes) and the tesseract manifold box is the
single highest-delight object in the game right now. So:

1. **M1 — wireframe renderer + tesseract manifold box** (canvas, steps-quantized
   rotation, CRT overlay; behind the toggle; triggered on `examine manifold box`).
   Proves the surface, the payload channel, and the settings plumbing.
2. **M2 — title screen**: tomb slab wireframe (hand-modeled, 3 faces marked).
3. **M3 — first Guide card** (SVG template + timeline helper): THE CANOPIC
   SYSTEM — five jars, organ routing diagram, mask-reveal labels. The
   template is the deliverable; the card proves it.
4. **M4 — a card or wireframe for each remaining hero object** as art gets
   made (this is where the Leo Hunt cross from #430 comes in — his
   illustration style redrawn angular, litho-luminous).

Costs: M1–M3 are code-shaped and testable (renderer math unit-tests; registry
wiring through `panel_data`-style payloads). M4 is art-shaped and open-ended.
Risks: none to the game core — the figure channel is additive, the toggle
defaults can ship conservative, and the wheel stays zero-dependency.

## 4. Sources

- Interview with Rod Lord — douglasadams.eu/interview-with-rod-lord/
  (litho reversal, gels, mask slots, wipes, Burd's "more angular" note)
- rodlord.com (galleries; technique pages have moved around)
- BBC/British Comedy Guide retrospectives (team size, schedule, awards)
