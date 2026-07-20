# The Retro-Animation Workflow (a reproduction guide)

*Companion to `retro-animations.md` (the art-direction research). That doc says
WHY the cards look the way they do; this one says HOW to make another, from
blank idea to a card playing in the live game. Written so a fresh session with
no memory of the project can pick up the practice. Everything here was
exercised for real across cards 00–36; the file paths are live.*

## 0. The system in one paragraph

Every illustration ("card") is a **self-running SVG or canvas animation block**
in the prototype reel, `app/prototypes/retro-animations.html` — the single
source of truth. `app/gen_figures.py` mechanically extracts every block into
`app/figures.js`, a registry the game terminal draws from on demand (a test,
`tests/test_figures.py`, regenerates and compares, so figures.js can never
drift from the reel). The game engine cues cards through the **FIGURE
channel**: items, characters, and rooms carry a `figure` property whose value
is a card KEY, and story beats call `game.show_figure(key)` directly.
`./app/deploy_web.sh` builds and pushes the whole thing to
https://ccb.github.io/tomb-of-nassak-an-rah/ (the reel itself is served at
`/animations/`). The Playdate is a separate, smaller pipeline: five cards
pre-rendered to 1-bit imagetables by `playdate/tools/export_figures.py`.

## 1. Style influences (what a card is allowed to look like)

- **Rod Lord / Pearce Studios** (the HHGG TV guide graphics) — the master
  influence; see `retro-animations.md` §1 for the research. The practical
  rules that fall out of it:
  - *Line art on black*, transmitted-light glow. No solids; "more angular and
    with more lines rather than solids."
  - *Everything steps, nothing tweens.* A 12 fps step clock; movement is
    quantized (`q6 = x => Math.round(x / 6) * 6` in card 18) so motion reads
    as electronic redraw, not film.
  - *Text reveals letter-by-letter* (the `typeOn` mask-slot helper).
  - *Wipes with a bright leading edge*, never dissolves (the `wipe` helper
    opens every card).
  - *Busyness over complexity*: the drawing is simple; the LIFE comes from
    constant small events — callouts rotating, meters filling, labels typing,
    a counter ticking ("BREATHS SINCE INTERMENT: 147,460,000,006").
  - *The deadpan data-plate voice*: every card gets a corner classification
    ("EXOTICA / WEAPONS-GRADE PHILOSOPHY"), rotating callouts with dashed
    leader lines, and a typed FUNGUS-orange footer that lands a dry joke or
    a canon quote ("STOPPED ONLY BY LEAD.").
- **Leo Hunt halftone** — the `stipple()` dot-screen pattern used as the
  only "fill" (jar bodies, gel, sand). Never a flat fill.
- **CRT phosphor terminals** — the palette (§2) plus the page's scanline/
  vignette dressing (`.screen::after` in the reel's CSS).
- **Instructional-diagram language** — dimension leaders with arrowheads
  (the flinch test), materials tables, cutaway windows with dashed borders
  (`"stroke-dasharray": "4 3"`), swatch legends, SURVIVORS counters. When in
  doubt, draw the card as if a tomb-bureaucrat filed it.
- **Case-specific homages** — approved on request only: Oregon Trail for the
  zoxen (boxy horned oxen, covered-wagon canvas arcs); a mandrill photo for
  the baboon jar; a hurricane lantern for the ulfire lantern. When CCB sends
  a reference image, match its *anatomy*, then translate into the line
  vocabulary above.
- **Vaults of Vaarn** — all fiction and copy. Canon TEXT COMES FIRST: before
  designing a card, grep the adventure file for the item's description and
  quote it (the ulfire lantern's "shines through solid objects... stopped
  only by lead" *became* two whole cards).

## 2. The shared vocabulary (palette, helpers, anatomy)

Palette constants, defined once in the reel's IIFE:

```js
const PH = "#4db8ff";        // phosphor line
const PH_DIM = "#24587c";    // secondary/dashed/leader lines
const PH_BRIGHT = "#dff2ff"; // highlights, headers, teeth, glints
const FUNGUS = "#ff9a3c";    // the orange accent: gold fur, organs, footers
const BG = "#010304";        // the void
// also used ad hoc: "#ff5a5a" (crimson: seals, NO-symbols), "#cfefff" (GLASS)
```

Shared helpers (already in the reel; every block may use them):

- `clock(fn)` — the 12 fps step clock; `fn(t)` runs forever, `t` integer.
  Every block derives a cycle: `const T = t % 170;`
- `wipe(svg, w, h, t0, dur)` — returns `doWipe(T)`; call first in the tick.
- `typeOn(node, text, T, startFrame, cps)` — letter-by-letter with a `_`
  cursor.
- `label(svg, x, y, size, color)` — monospace `<text>`.
- `el(svg, name, attrs)` — element factory; parent is the first argument, so
  `el(group, ...)` nests.
- `stipple(svg, id, color, r)` — the halftone pattern; **the pattern id must
  be unique per card** ("dots-<key>") or two cards on one page will collide.
- `headGlyph(g, kind, cx)` — the small canopic stopper heads (BABOON, HUMAN,
  MANTIS, FALCON, JACKAL); `jarCard(...)` — the whole jar-close-up chassis
  (14/15/16/29/30 are all one helper call each).

Card anatomy, top to bottom (copy an existing block; 34 is a clean template):

```
header rule at y=34 ... typed hdr at (16,24,13,PH_BRIGHT)
corner class label, right-anchored at (624,24,10,PH_DIM)
[ the scene: 640 x 300-340 of drawing ]
rotating callouts: CALLS = [{at:[x,y], text}], dashed polyline leader to
  a right-anchored label at (624,64); rotate Math.floor(T/30) % CALLS.length
meters/gauges bottom-left (label + cells at 340-350)
typed footer, FUNGUS, centred-ish, late in the cycle
```

Text legibility rules (learned the hard way): headers 13px bright; footers
and labels 10px minimum; anything that must READ (a proverb, a banner) is
**12–13px PH_BRIGHT, never 10px PH_DIM** (the zoxen motto shipped dim and got
bounced). Right-anchored text starts no further left than fits: check
`x + chars*7px <= 630` or it clips (the 33 header/corner label collided; the
materials table clipped at x=470). ViewBoxes: 640x360 standard, 640x400 tall,
640x300 jar close-ups.

Strict-mode pitfalls (the page runs `"use strict"`): every variable needs
`const/let` (an implicit global THROWS and kills every block after it);
SVG elements have no writable `.dataset`; `Math.random()` is fine here (the
browser runs it) but keep motion deterministic in `t` so screenshots repro.

## 3. The workflow, step by step

### Step 1 — pick the subject and pull canon
Grep `text_adventure_games/adventures/tomb_of_nassak_an_rah.py` for the
item/room/NPC description, examine text, and any spoken lines. The best
footer is usually already written ("A knife by any honest measure").

### Step 2 — draft 3 diverse candidates on the review page
Candidates do NOT go in the reel. Build them on a separate page (this session
used `scratchpad/candidates.html`, assembled from the reel's extracted style
block + helper prelude — see §6). Three takes should differ in *concept*, not
polish: e.g. for the dagger — the specimen card, the lab-test diagram, the
decoded-inscription strip. Give each a slate number (`NN-A/B/C`), a `kind`
chip, and a spec paragraph selling the concept.

**Keep slate titles in sync with the blocks under them when revising** — a
redo that swaps animations but not titles caused a wrong card to ship.

### Step 3 — verify locally with headless Chromium
Playwright drives everything. The system python with playwright is
`/opt/homebrew/anaconda3/bin/python3` and the pinned browser is:

```python
pw.chromium.launch(executable_path=os.path.expanduser(
  "~/Library/Caches/ms-playwright/chromium_headless_shell-1208/"
  "chrome-headless-shell-mac-arm64/chrome-headless-shell"))
```

Check (a) `page.on("pageerror")` is empty and a sentinel like
`window.__cards_done` is true; (b) each `svg[id=...]` has child nodes;
(c) screenshots at MEANINGFUL frames — compute the wait from the cycle
(12 fps: frame = ms/1000*12; a shot at `T%cycle < 10` catches the wipe and
looks black — reshoot mid-cycle). Read the screenshots and actually LOOK at
them; compare against any reference image CCB provided.

TIMING GOTCHA: the reel page only ticks cards near the viewport (an
IntersectionObserver gates a single shared clock — the "reel-only plumbing"
block, which `gen_figures.py` strips when building `figures.js`). An
offscreen card sits frozen at t=0, so `scroll_into_view_if_needed()` FIRST,
then start counting frames from the scroll, not from page load. A page
built without that plumbing (e.g. a scratch candidates page with the old
free-running `clock`) still counts from load.

### Step 4 — publish for review, iterate
Publish the candidates page as its own Artifact (separate URL from the reel)
and give CCB the link with one-line concept summaries. He picks by slate
number and art-directs ("more triangular", "move the human jar one left",
"face only, golden"). Apply notes surgically; keep rejected takes on the page
until he explicitly retires them; archive superseded versions only if asked
(18-A existed for one round, then "the archive is git's job").

### Step 5 — ship the winner into the reel
1. Carve the winning block out of the candidates page, rename its element id
   to the final KEY (short, no variant suffix: `dagger`, `core`, `zoxen`) and
   uniquify its stipple/clipPath ids.
2. Retitle the typed header to name the subject (the reel is the game's
   catalog: "THE SYNTH-HUNTING DAGGER", not the working title).
3. Add a `<section>` (slate `NN — TITLE`, kind chip, spec paragraph ending in
   `<span class="attach">Attaches: VERB PHRASE.</span>`) placed near its
   subject's neighbors — page order is curated, not numeric (establishing
   states precede solves: 18-B before 18, 06-B before 06).
4. Insert the JS block before the `/* 23-25: the spawn of brain */` marker
   (plain blocks) — `jarCard(...)` calls go with the other jar calls.
5. Numbering: next free integer for a new subject, `NN-B` letters for
   variants of the same beat. Check the taken numbers:
   `grep -o 'slate"><h2>[^<]*' app/prototypes/retro-animations.html`.

### Step 6 — regenerate and wire the game
```bash
python3 app/gen_figures.py     # reel -> figures.js (prints the card census)
```
Then wire the trigger in the adventure file. The semantics matter:

| Cue | Mechanism | Dedupe |
|---|---|---|
| Room arrival | `room.set_property("figure", KEY)` | once per game; LOOK re-earns (forces) |
| Examine | `item.set_property("figure", KEY)` | forces every time |
| Take | same item property | once (examine can re-earn) |
| Wear | same item property (wearables) | forces every time (CCB: donning is as deliberate as examining) |
| Read | same item property (documents) | forces every time (CCB: poring over paperwork is as deliberate as examining) |
| Story beat | `g.show_figure(KEY)` in a trigger/action | once |
| Story beat, must always play | `g.show_figure(KEY, force=True)` | never muted |

Beats that bypass the Get action (e.g. the ego-core reveal adds to inventory
directly) do NOT auto-fire the take cue — call `show_figure` in the beat.
Talkers: put the call inside the character's `talk_text` callable.
**Audit warning:** one boot-time cue lived in `app/app_api.py`, not the
adventure file — grep BOTH when auditing (a duplicate opening card shipped
because of this).

### Step 7 — test, commit, deploy, verify
```bash
uv run python -m pytest -q          # full suite; test_figures.py guards drift
# smoke: build_game(), do the trigger command, assert KEY in game.figures_shown
git add -A && git commit            # style: card number + what it does + why
./app/deploy_web.sh                 # builds dist, pushes ccb.github.io (~1 min)
```
Verify live with a background until-loop:
`until curl -s .../figures.js | grep -q '_define("KEY"'; do sleep 10; done`.
Update the reel Artifact (same URL, same 📽️ favicon) by copying
`app/prototypes/retro-animations.html` over the scratchpad copy and
re-publishing.

## 4. Worked examples (three card archetypes)

**The specimen card** (16 falcon jar, 31 dagger, 34-B): subject huge and
centred, growth-rings/facets as interior detail, glints patrolling edges,
one physical behavior on loop (the coil turning by degrees; the grip closing;
LogLang flashing when gripped). Callouts name parts; the footer names the
moral.

**The process/beat card** (18 the seal, 34 the shard, 31-B the paradox):
a sequence with phases — `const T = t % 210` divided into acts, each act
gated by frame windows (`T < 90 ? LOGIC : T < 130 ? PARADOX : GLITCH`),
state changes stepped and quantized, an epilogue line typing late. Physics
must close: the fall arc ends where the burst happens; the reveal region is
bounded by the drawn beam lines exactly ("the beams ARE the boundary" — when
a boundary and its indicator are drawn separately they WILL disagree).

**The instructional plate** (31-C disadvantage, 33-D lead test, 36-B
butchery): a diagram proving a rule — dimension leaders, dice with real pips,
a materials table typing results, scent lines drifting to a pricked ear. The
punchline is the caption ("THE DISTANCE IS THE SAME IN EVERY TRIAL.").

## 5. The Playdate side (only when asked)

The device ships a small set of pre-rendered cards (currently 5:
`playdate/Source/images/figures/`). `playdate/tools/export_figures.py` drives
figures.js in headless Chromium, steps the 12 fps clock manually, strips
text (captions render natively on-device from `captions.lua`), lifts dim
phosphor `#24587c -> #4db8ff` so it survives 1-bit, **thresholds (never
dithers — Floyd–Steinberg re-rolls per frame and shimmers)**, grid-pads the
final imagetable row, and packs `KEY-table-384-240.png`. New device cards
need: the export run, a caption script in `captions.lua`, a showFigure call
in `slice.lua`, and a `pdc` rebuild (`PLAYDATE_SDK_PATH=~/Developer/PlaydateSDK`).

## 6. Rebuilding the candidates page from scratch

If the scratchpad copy is gone: extract from the reel (1) the `<style>` block,
(2) the constants+`clock` prelude (`const PH = ...` through the
`timers.push` line), (3) the SVG helpers (`/* SVG helpers (litho cards) */`
through the end of `wipe`, stopping before `headGlyph`). Wrap in
`(() => { "use strict"; ... })()`, add sections + blocks, end the IIFE with a
`window.__cards_done = true;` sentinel. Publish via the Artifact tool with a
🎞️ favicon (the reel keeps 📽️).

## 7. The full card census (as of this writing)

00 road · 01 tesseract · 02 blade · 03-C canopic-c · 04 jackal · 05 bats ·
05-C bats-c · 06/06-B cylinders · 08 glowstone · 09 silas · 10 hound ·
11-B sphere-b · 12 fungus · 13/13-C/13-E autarch family · 14 jar-mantis ·
15 jar-jackal · 16 jar-falcon · 17-C/17-D ext1c/ext1e · 18/18-B seal/seal-b ·
19-B mystic-b · 20 centipede · 21 epitaph · 23-25 spawn-a/b/c ·
26-28 guts-a/b/c · 29 jar-baboon · 30 jar-human · 31 dagger · 32 core ·
33 ulfire · 34 shard · 35 critch · 36/36-B zoxen/zoxen-b
(42 keys; `python3 app/gen_figures.py` prints the authoritative list.)

Unshipped candidates awaiting picks live on the candidates Artifact:
the merchant trio (37-A/B/C) and the unused Critch faces.
