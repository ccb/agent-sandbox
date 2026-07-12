# Tomb of Nassak An-Rah on Playdate

Research + port plan (CCB, 2026-07). Branch: `feat/playdate`.

## 1. The platform

- **Hardware**: 400×240 **1-bit** display (no grays -- dither is the palette),
  ARM Cortex-M7 @ 168 MHz, 16 MB RAM, 4 GB flash. Inputs: d-pad, A/B, the
  **crank**, accelerometer. No keyboard, no touch.
- **SDK**: free download (macOS/Windows/Linux), **Lua** and C APIs, `pdc`
  compiler, a Simulator with keyboard-equivalent controls and profiling.
  Docs: "Inside Playdate" (Lua), "Inside Playdate with C", "Designing for
  Playdate". License: Playdate SDK License (permissive for shipping games).
- **Distribution**: free **sideload** to any device (play.date account upload
  or USB), itch.io as the community norm, and the curated **Catalog**
  (Panic review). Unique `bundleID` required.
- **Pulp** (the web-based maker) is a toy for this purpose -- room-based
  scripting, no real text layout. Not a fit; we use the SDK.
- **Prior art**: text games exist and work on the device (The Simorgh, Thy
  Dungeonman, robotfindskitten ports) -- all avoid free typing in favor of
  menus. There IS a `playdate.keyboard` on-screen keyboard (d-pad/crank
  driven) usable as a fallback for naming/save slots, but it is far too slow
  to be the primary way to play a parser game.

## 2. Why this game can work there

Two properties of our engine were built for other reasons and happen to be
exactly what a keyboard-less parser game needs:

1. **The suggestions channel.** `app_api.suggestions()` already computes, per
   turn, the complete honest word set: curated VERBS, perception-gated NOUNS
   (nothing you can't see), and EXITS. On the web these are tap-chips; on
   Playdate they are the entire input method.
2. **The (seed, journal) save model.** A save is a seed plus a command list.
   Tiny, deterministic, trivially serialized to Playdate's datastore.

And the figures: the litho cards are line art + halftone stipple at 12 fps --
they are practically *native* 1-bit art. 640×400 and 400×240 share nothing,
but 640×400 scaled ×0.6 → 384×240 fits with margins. Dithered, they will look
like they were drawn for the device.

## 3. Input design: the Composer

The crank is the parser.

```
+----------------------------------------------+
| HALL OF YOUTH                    45/145  T:31 |
|                                               |
|  (transcript -- crank scrolls when docked     |
|   cursor is here; d-pad UP/DOWN pages)        |
|                                               |
+-----------------------------------------------+
| > THROW DATES_                                |
|   [EXITS]   [VERBS]   [NOUNS]      <- d-pad ◄► |
|    north     take      dates      <- crank    |
|    south    >throw<    crates                 |
|    up        drop      glowstone              |
+-----------------------------------------------+
```

- **Crank** scrolls the active word lane (detented via `getCrankTicks`);
  **d-pad ◄►** switches lanes (EXITS / VERBS / NOUNS); **A** appends the
  highlighted word to the command line; **B** deletes the last word (hold B:
  clear). **A on an empty line with an exit highlighted** = just go.
- A composed line submits with A when the composer predicts completeness
  (verb alone like LOOK/INVENTORY, or verb+noun), else A keeps appending --
  same grammar the chips already taught us.
- Meta verbs (SAVE / RESTORE / HINT / SCRIPT) live at the top of VERBS.
- `playdate.keyboard` only for the rare free-text (naming a save).
- The crank docked = scroll the transcript. Undocked = compose. The gesture
  IS the mode.

## 4. Architecture options

**A. Lua re-implementation (recommended).** A slim `mini-engine` in Lua:
rooms/items/characters as tables, properties, inventory+slots/wounds,
triggers as Lua closures, the suggestions computation, and a composer parser
that only needs exact verb+noun matching (the composer can never produce a
typo). The tomb's CONTENT is hand-ported: descriptions and data mechanically,
the ~40 custom actions/triggers by hand (they are Python closures; no honest
auto-export exists). Estimate: the engine core is small (the hard 20% of our
Python engine is parsing free text, which the composer deletes); the content
port is the long pole.

**B. C core.** Only if Lua profiling shows problems. 168 MHz runs Lua text
games comfortably; not expected.

**C. MicroPython on device.** Experimental ports exist in the community; 16 MB
RAM makes it plausible but it is unproven, unsupported, and would still need
the whole UI layer written against the C API. Not worth the risk. (Revisit
only if the Lua content port proves miserable.)

**Parity harness**: the Python game stays the source of truth. A test runs the
WIN walkthrough through both engines (Python directly; Lua via `pdc`-less
headless Lua with the SDK shims stubbed) and diffs room-by-room state:
location, score, inventory names, turn count. Divergence fails CI.

## 5. The figures on 1-bit

Pipeline (build-time, from the reel -- same single-source rule as
`gen_figures.py`):

1. `gen_playdate_figures.py` drives headless Chromium over the reel, steps
   each card's clock (the cards are already quantized to 12 fps ticks), and
   captures N frames of its loop at 640×400.
2. Downscale to 384×240, threshold/dither (Atkinson) to 1-bit, write PNG
   frame strips -> Playdate **imagetables**.
3. On device: a figure plays its imagetable at 12 fps in a framed panel above
   the transcript, then holds its last frame (the Road/title card already
   plays-once by design). Budget: 1-bit 384×240 = 11.5 KB/frame raw; a
   120-frame loop ≈ 1.4 MB on flash, streamed -- fine on 4 GB, loaded
   one-at-a-time within 16 MB.
4. The FIGURE channel maps 1:1: the Lua engine cues the same keys.

Cards that are interactive on the web (glowstone click) map to A-button.

## 6. Milestones

- **M0 -- spike**: install SDK, run Simulator, render scrolling text +
  a crank-driven word lane, sideload to CCB's device. Exit: composing
  "GO NORTH" on hardware.
- **M1 -- mini-engine**: rooms/items/properties/inventory, Go/Look/Take/
  Drop/Examine, suggestions, transcript, datastore saves (seed+journal).
- **M2 -- composer**: the full three-lane UI, meta verbs, hold-B clear,
  docked-crank scrollback.
- **M3 -- content**: the tomb ported room-by-room (start with Wreck ->
  Exterior -> Youth vertical slice), then the trigger set; parity harness
  green on the WIN walkthrough.
- **M4 -- figures**: exporter + imagetable playback, ILLUSTRATIONS toggle.
- **M5 -- systems**: wounds/slots, hints (the HINT menu is naturally
  crank-scrollable), death/epitaph + restart.
- **M6 -- ship**: device soak, itch sideload build, Catalog submission.

## 7. Open questions for CCB

- Sound? The device has a synth API; the web terminal's beeps would port,
  and the crank could literally click like a ratchet when scrolling.
- Session length: Playdate play sessions skew short -- lean harder on the
  autosave-every-turn we already do.
- Scope check: vertical slice (M0-M2 + three rooms) before committing to the
  full content port.
