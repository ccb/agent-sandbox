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

## 6. The small screen: text budget

400×240 with a readable font is roughly 40 characters × 11 transcript lines
-- about 450 characters visible at once. Our room descriptions routinely run
3-4× that. Scrolling works but reading four screens per room is not Playdate-
native. The plan:

- **A terse text pass, kept in the Python source.** Every location and
  examinable gains an optional `pd_text` (or `brief_text`) variant, capped at
  ~50 words, written by hand during the content port -- the port IS the
  editing pass, but the variants live in the canonical Python content so the
  two engines share one source and the web could grow a BRIEF mode for free.
- **The Infocom precedent**: VERBOSE on first visit (full text, crank to
  read), BRIEF on revisits (name, one salient line, exits). SUPERBRIEF as a
  setting. Revisit text is where most of the squeeze is won.
- **Writing rule for terse variants**: front-load the interactable nouns --
  on Playdate the description doubles as the noun lane's table of contents.
  Anything named should be examinable; anything examinable should be named.
- Status/score/exits move to a persistent one-line bar (already our web
  statusbar), not repeated in prose.

## 7. Lane coverage: the verb/noun audit

Today's suggestions channel is honest but incomplete: the VERB row is 18
curated words, and the tomb has custom actions (BUTCHER, PRAY/SAY, PRY, FIX,
FEED, GIVE ... TO, POUR ... INTO, REMEMBER, KICK) that never appear. On the
web a player can always type; on Playdate, **a verb not in the lane does not
exist**. So:

- **Audit tooling first**: a build-time script walks (a) the parser's full
  action registry incl. `custom_actions`, (b) the WIN walkthrough, and (c)
  every `ACTION_ALIASES` phrase, and reports which verbs/nouns a composer
  could never have produced. This runs in CI so new content can't strand a
  verb again.
- **Context verbs**: things already carry `add_command_hint` ("read
  prayers") -- promote that into the suggestions channel as a per-scope verb
  contribution: BUTCHER appears only with a corpse in scope, SAY/PRAY only
  where prayers are, POUR only holding the blood. This is diegetic (the
  thing itself advertises its affordance) and keeps the resting lane short.
- **Grammar templates**: multiword commands need composer slots, driven by a
  small verb table: `GIVE _ TO _`, `THROW _ <direction>`, `POUR _ INTO _`,
  `SAY <prayer>`. After picking GIVE the noun lane fills, then a TO lane of
  characters. No free connectors; the template supplies them.
- Hidden-until-SEARCH stays hidden -- the lanes must never spoil (they
  already honor perception; the audit checks coverage, not secrets).

## 8. Lane ranking: judicious, stable, un-spoiling

Three principles, in tension, resolved in this order:

1. **Stability beats optimality.** Reranking every turn destroys the
   player's spatial memory of the lane. Base order is FIXED and learnable:
   EXITS in compass order (n/s/e/w/up/down/in/out); VERBS in one curated
   order that never changes; NOUNS grouped -- room things in description
   order, then characters, then carried items (a separator tick between
   groups, d-pad up/down jumps groups, crank moves within).
2. **Bounded recency, visually fenced.** At most the LAST TWO used verbs get
   pinned above the fixed verb order, behind a tick mark -- a bounded,
   predictable convenience (take/examine loops) that never reshuffles the
   rest. Nothing else self-sorts.
3. **Salience is diegetic, never oracular.** A noun may be boosted only by
   what the fiction has already foregrounded: mentioned in the CURRENT room
   text -> room group front (that is what description order gives us for
   free). We never rank by what progresses the game -- the lane must not be
   a walkthrough. Context verbs (§7) appear on scope, which is information
   the prose already gave; that is as far as "smart" goes.

Practical caps: 3 visible words per lane (crank scrolls, detent per word),
the composed line always visible above, and the resting state of the noun
lane starts at the top of the room group -- so a glance shows exits, the
top verbs, and the room's leading nouns without any cranking.

## 9. Milestones

- **M0 -- spike**: install SDK, run Simulator, render scrolling text +
  a crank-driven word lane, sideload to CCB's device. Exit: composing
  "GO NORTH" on hardware.
- **M1 -- mini-engine**: rooms/items/properties/inventory, Go/Look/Take/
  Drop/Examine, suggestions, transcript, datastore saves (seed+journal).
- **M2 -- composer**: the full three-lane UI, meta verbs, hold-B clear,
  docked-crank scrollback.
- **M2.5 -- coverage audit**: the lane audit script in CI; suggestions()
  grows context verbs (command-hint promotion) and grammar templates.
- **M3 -- content**: the tomb ported room-by-room (start with Wreck ->
  Exterior -> Youth vertical slice) WITH the terse-text pass as it goes,
  then the trigger set; parity harness green on the WIN walkthrough.
- **M4 -- figures**: exporter + imagetable playback, ILLUSTRATIONS toggle.
- **M5 -- systems**: wounds/slots, hints (the HINT menu is naturally
  crank-scrollable), death/epitaph + restart.
- **M6 -- ship**: device soak, itch sideload build, Catalog submission.

## 10. Open questions for CCB

- Sound? The device has a synth API; the web terminal's beeps would port,
  and the crank could literally click like a ratchet when scrolling.
- Session length: Playdate play sessions skew short -- lean harder on the
  autosave-every-turn we already do.
- Scope check: vertical slice (M0-M2 + three rooms) before committing to the
  full content port.
