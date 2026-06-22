# Tingen — Visual Style Guide

A pixel-art occult-detective game set in **Tingen City, Loen Kingdom** — the world of
*Lord of the Mysteries* (诡秘之主). This guide is the single source of truth for asset
generation. Every prompt, palette, and style preset below derives from canon and from a
critique of round-0 output.

Grounded in: the LotM donghua/manhua look (B.CMay Pictures), the novel's setting, and
the Klein Moretti character canon. Sources consulted: LotM Wiki (Klein Moretti, Tingen
City), donghua production notes (Victorian + steampunk + Lovecraftian, "dark muted
industrial grit vs. brightly saturated mysticism").

---

## 1. The One-Sentence North Star

> **Gaslit Victorian gloom — muted, foggy, desaturated — pierced by isolated pools of warm
> amber light and, rarely, the saturated glow of the occult.**

If an asset is just "dark," it's wrong. The signature is **contrast**: a cold, muted,
fog-gray world where warmth (gaslight) and the supernatural (eldritch color) are the only
saturated things in frame.

---

## 2. Era & World (lock this — it's the #1 round-0 error)

- **Period:** Loen ≈ **1890s–1900s Britain** (late-Victorian / Edwardian gaslamp fantasy),
  early-industrial + **steampunk** edge. **NOT** 1920s–30s American noir.
- **Wardrobe language (use these exact words):** frock coat, double-breasted overcoat,
  Inverness cape-coat, waistcoat, cravat/ascot, **bowler hat or top hat** (NOT fedora),
  high collar, leather gloves, walking cane, pocket watch on a chain.
- **Technology:** gas street-lamps, oil lamps, candles, revolvers, telegraph, steam &
  brick, the occasional **airship**/steam-train. **No** electric screens, TVs, modern
  furniture, plastics, neon.

### The two cities (corrected from official environment art)
- **TINGEN (廷根) — our primary setting.** A **mid-sized provincial cathedral-and-university
  town**, NOT a heavy-industrial port. Red-brick + **slate-roofed** buildings, cobblestone
  lanes, wrought-iron rails, a **river** splitting it into districts (North/East/West/South),
  a great twin-spired **Gothic cathedral** (Saint Selena's / 圣赛琳娜教堂), a **red-brick
  collegiate university** (Tingen University history dept — ivy, gas lamps, benches, green
  quads), modest docks. **Mood is NOT all grimdark:** there's real warmth and beauty —
  dawn-pink skies, brick red, golden-hour foliage — with the dread sitting *underneath*.
  Fog and gaslight, yes; dungeon, no.
- **BACKLAND / BACKLUND (贝克兰德) — the capital, a later-game location.** THE heavy
  steampunk megacity: forests of smokestacks, dockyard cranes, iron bridges, **airships**,
  smog, sprawling foggy skyline. Cooler, darker, grander, dirtier than Tingen. Reserve this
  look for capital scenes — don't paint Tingen with it.

**Tingen landmarks for scenes:** Saint Selena's Cathedral & plaza, Tingen University history
office, the Nighthawks/Blackthorn HQ, foggy harbor & warehouses, red-brick residential lanes,
taverns, the river embankment.

---

## 3. Palette (the "muted grit + saturated mystic" system)

**Rule of thumb:** ~70% cool desaturated base, ~25% warm gaslight pools, ~5% saturated
occult accent. The occult color should be the *only* fully-saturated thing on screen.

### Base — cool, muted, foggy (the mundane world)
- Fog blue-gray: `#3A4452` `#4F5B68` `#6B7888`
- Cold stone / wall: `#2B2F36` `#41474F`
- Night & shadow: `#15181F` `#20242C`

### Warm — gaslight & flame (the pools of safety)
- Sodium/amber glow: `#C8862F` `#D9A24A` `#E7B75F`
- Candle / ember: `#8A4A1C` `#B5611F`

### Environment — Tingen town (brick, slate, dawn — keeps the world from going all-grimdark)
- Brick / tile red: `#7A4034` `#9C5642` `#B97A5A`
- Slate roof blue-gray: `#414A55` `#566372`
- Aged stone / cathedral cream: `#8C8579` `#B3AC9C`
- Dawn / dusk sky wash: `#D98C7A` `#E6B79A` `#9FB0C4` (pink→peach→cool)
- Foliage / quad green (muted): `#46523A` `#6B7A4E`

### Wardrobe — Klein (corrected from official splash art)
Klein wears **charcoal-black, NOT brown.** Brown appears only as leather accents.
- Coat / suit charcoal-black: `#1C1E22` `#2A2D33` `#3A3E45`
- **Inverness cape lining — deep violet** (his signature accent): `#3A2A55` `#5B3A8A`
- White high-collar shirt: `#E6E4DC` `#C9C6BC`
- Brown leather (holster strap, boots): `#4A3526` `#6A4B33`
- Silver cane handle / buckles: `#9AA0A8` `#C7CCD2`

### Occult — Beyonder accent (use sparingly — the ONLY saturated thing on screen)
- **Fool / pathway sigil — luminous silver-white** (radiant linework): `#C9CDD4` `#EAF0F6`
- **Beyonder eyes — luminous gold** (Klein's glowing iris): `#E8B23A` `#F4D27A`
- **Blood-moon crimson** (Night-goddess / ritual / horror): `#7A0E18` `#C2222E` `#E0303C`
- Spirit teal / sickly green (apparitions, sigils): `#2F8E7E` `#7FAE3F`
- Mystic purple (Fool pathway, distortion): `#5B3A8A`

**Readability fix (round-0 was crushed to black):** lift the mid-tones. Shadows go to
`#15181F`, *not* pure black; keep at least a 3-value separation between a silhouette and
its background so sprites read on dark tiles.

---

## 4. Lighting & Mood

- **Single warm key light** (a lamp, a window, a candle) per scene, with long cool
  shadows and **volumetric fog** softening the background.
- **Atmosphere over detail:** haze, drifting fog, dust motes, rim-light on figures.
- **Tone:** grim, melancholic, uneasy — Gothic horror with a detective's composure.
  Not gore-forward, not jump-scare. Dread, not splatter.
- **Tonal range (don't paint everything black):** the world has daylight too. Exteriors
  (cathedral plaza, university quad, harbor at dawn) can be **warm and even beautiful** —
  golden hour, brick red, green trees — with menace implied, not shouted. Save the crushed
  near-black for interiors, night, ritual, and horror beats. Variety sells the dread.

---

## 5. Protagonist — the player detective ("Klein")

Canon Klein Moretti (from official splash art): **black hair swept back, pale refined
"scholarly" face, thin build, ~early-20s.** Eyes are brown normally; in his **Beyonder /
Fool state they glow luminous gold** — use the gold-eye version for the hero, it's iconic.

**Exact wardrobe (lock this):**
- **Caped Inverness / double-breasted overcoat, charcoal-black, with a deep-violet lining**
  that flares behind him (the purple is his signature pop of color).
- White high-collar shirt + dark cravat; dark waistcoat with a **pocket-watch chain**.
- **Brown leather shoulder-holster strap** across the chest holding a **revolver** at the hip.
- **Black cane with an ornate silver handle** (right hand) and a **black top hat**
  (top hat, NOT bowler, for Klein specifically).
- Dark trousers, black leather boots.

**Sprite brief:** full-body, centered, **idle stance** (relaxed, weight on the cane —
NOT gun-drawn action pose), **fills ~80% of frame height**, clean silhouette. Charcoal-black
with the violet cape-lining + a glint of gold eyes + silver cane so he reads against gloom.

**Portrait brief:** chest-up, three-quarter, **pixel art** (consistent with the set, not
painterly), black swept-back hair, pale composed face, **gold Beyonder eyes**, charcoal
high-collar coat with violet lining, single cool key light, dark fog background. The silver
Fool sigil may glow faintly behind. Brooding but controlled.

---

## 6. Cast, Enemies, Props, Tiles, UI — per-type direction

- **NPCs / cast:** same era wardrobe, class-coded — constables in Loen police helmets &
  capes, dockworkers in flat caps & rough wool, priests in cassocks (hood **down**, white
  clerical collar, face visible), widow in mourning black & veil, archivist in spectacles &
  ink-stained sleeves. Readable silhouettes. **Loen ≈ Victorian Britain, so the cast read as
  pale, fair-skinned Europeans with clearly-lit faces — never crushed dark.** (Round-3/4 fix:
  the muted/dark palette was rendering faces near-black, which read as the wrong ethnicity;
  every human prompt now states "fair pale Victorian European complexion, face clearly lit by
  a warm key light.")
- **Enemies / Beyonders:** Lovecraftian body-horror — distorted human anatomy, too many
  joints, shadow-flesh — but give each **one eerie saturated accent** (glowing eyes, a
  sigil, spilling mist) so it isn't black-on-black. Keep a clean readable silhouette.
- **Props / items:** single object, centered, clean alpha, period-correct (revolver,
  Antigonus notebook, pocket watch, oil lamp, tarot/divination cards, occult dagger,
  case file, talisman). Slight warm rim so they pop in inventory.
- **Tiles:** **seamless repeating textures**, flat top-down, **no props, no objects, no
  scene lighting, no lamps/plants/buildings.** This is the #2 round-0 error — `cobblestone`
  came out as a street scene. Must tile edge-to-edge (see §7 knobs).
- **Backgrounds = playable maps, NOT establishing shots:** every location is an **inclined
  three-quarter top-down map (Stardew Valley look)** — walkable ground seen from above with
  building fronts and objects standing upright toward the camera. Interiors = top-down room
  floors; exteriors = top-down street/courtyard blocks; even Backlund is a top-down
  industrial-dock district, not a skyline vista. (Round-4 fix: rounds 0–3 rendered eye-level
  vistas; the `environment` style is replaced by `topdown_map`.)
- **Klein's home (canon — WARM middle-class, NOT a dungeon):** the wake-up room is a
  **comfortable, lived-in bedroom** — ornate **carved-wood bed**, a writing desk with a
  **Tiffany stained-glass lamp**, bookshelf, wardrobe, mirror/dresser, rocking chair, rug,
  framed pictures, **golden light through tall lace-curtained windows**. The connected parlor
  is equally cozy: wood beams, chandelier, cream sofa, tea table with flowers. The
  transmigration **blood/horror is an overlay beat** (blood on the desk, the revolver, the
  note) on top of this warm room — the room itself is welcoming. This is the #1 round-0 fix.
- **Other interiors:** Nighthawks/Blackthorn HQ office, archive/library, warehouse, ritual
  chamber, tavern — all period, all gaslit.
- **Tingen has a district + time register — pick the right one per scene:**
  - **Nice (warm):** Saint Selena's Cathedral plaza (grand Gothic, cream stone, fountains),
    the university quad (red-brick collegiate Gothic, ivy, gas lamps, benches, trees),
    Klein's home, leafy residential lanes. Dawn/dusk and golden light welcome.
  - **Poor (gritty):** **Iron Cross Street (铁十字街)** — ramshackle leaning half-timber + brick
    slum, market awnings, stalls, washing lines, elevated rail, overcast gray-green sky,
    weathered rust-and-teal grime. Crowded, cluttered, lived-in poverty.
  - **Horror / night:** the same streets under a huge **blood-red moon** (crimson sky, near-
    black silhouettes, dread), and **Raphael Cemetery** (cold blue-gray fog, headstones, tall
    cypress, a central obelisk, mausoleums, lantern-lit stairs). This is where the crushed
    near-blacks + saturated crimson belong.
- **Backlund** exteriors (capital) = the heavy smokestack/crane/airship skyline — only for
  capital scenes, kept cooler & grander.
- **UI:** brass-and-ink Victorian frames; meters styled like apothecary gauges / pocket-
  watch faces; parchment dialogue boxes with a thin brass border. Muted, legible.

---

## 7. Translation to Retro Diffusion knobs

> **Pipeline split (decided round 5):** the **hero assets — characters, portraits and
> backgrounds — now generate via gpt-image-1 with reference conditioning (see §10),** not
> Retro Diffusion. RD pixel detail read too low for the important figures. **This §7
> (Retro Diffusion) now governs only props, tiles, UI and VFX.** The character/portrait/
> background rows below are retained for history.

Models: `retro-diffusion/rd-fast` (sprites/items/UI/vfx) and `retro-diffusion/rd-plus`
(tiles/backgrounds/hero detail). Real levers (confirmed from the model schema): **style
preset, seed, width/height, strength, tile_x/tile_y, input_palette, bypass_prompt_expansion.**
(There is **no** negative_prompt / guidance_scale / steps on these models.)

### Shared prompt scaffold (prepended/appended to every item)
- **STYLE:** `pixel art, late-Victorian gaslamp fantasy, occult-detective mystery, muted
  desaturated fog-gray palette with warm gaslight accents, atmospheric, moody, readable
  silhouette, 1890s Loen / steampunk, NOT modern, NOT 1930s noir`
- Per-type suffix (sprite = "full-body idle, fair pale Victorian complexion, face clearly
  lit, clean alpha, lifted midtones"; portrait = "chest-up pixel portrait, pale complexion,
  warm key light"; tile = "seamless tileable flat texture, no objects"; background =
  "inclined three-quarter top-down RPG map, walkable ground, building fronts upright"; etc.)

### Per-category settings

| Category    | Model   | style preset        | size | remove_bg | tile_x/y | bypass_expand | seed |
|-------------|---------|---------------------|------|-----------|----------|---------------|------|
| characters  | rd-fast | `detailed`          | 384  | yes       | no       | no            | per-char fixed |
| heroes (×~4)| rd-plus | `default`/`retro`   | 384  | yes       | no       | no            | per-char fixed |
| portraits   | rd-fast | `portrait`          | 384  | yes(or bg)| no       | no            | per-char fixed |
| enemies     | rd-fast | `detailed`          | 384  | yes       | no       | no            | per-char fixed |
| props/items | rd-plus | `topdown_asset`     | 384  | yes       | no       | **yes**       | per-item fixed |
| tiles       | rd-plus | `textured`          | 384  | no        | **yes**  | **yes**       | per-tile fixed |
| backgrounds | rd-plus | `topdown_map`       | 384  | no        | no       | no            | per-scene fixed |
| ui          | rd-plus | `ui_element`        | 384  | yes       | no       | **yes**       | per-item fixed |
| vfx         | rd-fast | `detailed`          | 384  | yes       | no       | no            | per-item fixed |

> **Size cap:** rd-fast and rd-plus both **hard-cap width/height at 384px** (512 is not
> possible). 384 is the max native detail; scale up in-engine with nearest-neighbor.

**Why these:**
- `detailed` (rd-fast) > `game_asset` → sharper faces/wardrobe, fixes the "mush face" sprite.
- `portrait` (rd-fast) → purpose-built bust framing; pair with "pixel art" to stop the
  painterly drift.
- `topdown_asset` (rd-plus) → clean single inventory object. (Note: the sibling
  `topdown_item` style is currently broken server-side — "Unable to run inference" — so
  we use `topdown_asset`, which renders one centered object cleanly.)
- `topdown_map` (rd-plus) → inclined three-quarter top-down location maps (the Stardew
  look). Replaces `environment`, which rendered eye-level establishing vistas, not the
  walkable playable scenes the game needs.
- **`textured` + `tile_x:true,tile_y:true` + `bypass_prompt_expansion:true`** → THE tile
  fix; literal prompt + true seamless edges, no model-invented lampposts/plants.
- **`bypass_prompt_expansion:true`** on tiles/props/ui → stops the model adding anachronistic
  junk (the TV, the street furniture). Left **off** for characters/scenes where expansion
  adds welcome richness.
- **Fixed per-asset `seed`** → a character looks the same across regenerations and across
  sprite↔portrait, and lets us re-roll deliberately rather than randomly.
- `width/height` = **384 everywhere — the model's hard cap** (rd-fast & rd-plus both max at
  384). Generate at 384 for max native detail, then scale **up** in Godot with
  **nearest-neighbor** (texture filter = nearest) for larger, crisp sprites. (Round-4 bump
  256 → 384 fixed the "figures too small / low detail" note.)
- `input_palette` → optional hard color-lock to the §3 palette once we're happy with forms
  (stretch lever; primary palette control is the prompt words + seed for now).

---

## 8. Acceptance checklist (every asset must pass)

1. **Era:** reads 1890s Loen, not 1930s noir or modern. Top hat / bowler, frock or
   Inverness coat, bustle gowns, parasols, ornate revolvers.
2. **Palette:** cool muted base + warm gaslight; occult is the only saturated color.
3. **Readability:** silhouette separates from background; shadows aren't pure black.
4. **Pixel consistency:** same pixel density & treatment across the whole set.
5. **On-canon:** Klein = black hair / gold Beyonder eyes / charcoal coat + violet lining /
   silver cane / top hat; rooms period-correct; no anachronisms.
6. **Function:** tiles tile seamlessly; sprites have clean alpha; items centered.

---

## 9. Official art reference (studied 2026-06-04)

Grounded in official 诡秘之主 art (Tencent / 天闻角川 donghua + game splash art) supplied by
the user. Two distinct rendering modes appear in canon — we borrow the *palette and costume*
from both but render everything in our own pixel style:

- **Cool splash mode:** character lit against a dark, desaturated blue-black hall/fog, with a
  glowing **silver pathway sigil** behind. Elegant, painterly, very dark. → our default for
  hero sprites & portraits.
- **Warm sepia poster mode:** aged-paper, foggy gaslamp Tingen street/interior, browns & tans,
  ornate brass revolver. → our reference for environment/background warmth.

**Confirmed character archetypes (reuse silhouettes & palettes):**
- **Klein Moretti (player):** see §5 — charcoal-black caped coat, violet lining, white collar,
  brown leather holster + revolver, silver-handled cane, black top hat, **gold Beyonder eyes**,
  silver Fool sigil. Splash background is cold & dark; poster is warm sepia.
- **Audrey Hall (high-class lady NPC ref):** blonde + green eyes, **sage-green & cream Victorian
  bustle gown** with brown corset waist, white gloves, parasol, green gem choker. Use this
  silhouette for the genteel-lady NPC; a **mourning-black** version = the widow witness.
- **Goddess of the Night (occult/deity/horror palette ref):** black lace veil + **silver
  constellations** on black, **blood-red moon**, gold double-eagle amulet, raven/scythe motifs.
  This is the master palette for ritual chambers, the descent-horror enemy, and occult VFX:
  **black + silver star-fleck + saturated crimson + a touch of gold.**

**Confirmed environment references (official concept/splash art):**
- **Backlund (贝克兰德), the capital:** dark industrial megacity — smokestacks, dockyard cranes,
  iron bridges, airships, smog. Cool/grand/dirty. Later-game only.
- **Tingen (廷根), our primary city:** provincial cathedral-and-university town — twin-spired
  Gothic cathedral over red-roof slate buildings, dawn-pink skies, a river + districts (official
  city map studied), modest docks. Warmer and gentler than Backlund.
- **Saint Selena's Cathedral (圣赛琳娜教堂):** grand cream-stone Gothic plaza, fountains, bright sky.
- **Tingen University history dept:** red-brick collegiate Gothic, ivy, gas lamps, benches, golden
  foliage — proof the world has warmth and beauty, not just gloom.
- **Klein's home (小康/comfortable version):** warm middle-class parlor + bedroom — carved wood,
  cream upholstery, Tiffany lamp, chandelier, lace curtains, golden window light. The canonical
  wake-up room. **Round-1 must replace the dungeon `wakeup_room` with this.**
- **Iron Cross Street (铁十字街):** poor ramshackle slum-market district — day = gritty/overcast,
  night = under a **blood-red moon**. The game's "wrong side of town."
- **Raphael Cemetery (拉斐尔墓园):** cold misty Gothic graveyard — cypress, obelisk, mausoleums,
  lantern-lit stairs. Night-investigation / occult scene.

**Scene-list updates for round 1 (fold into the generator's `backgrounds`/`tiles`):** rename/redo
`wakeup_room` → warm `klein_bedroom`; add `klein_parlor`, `iron_cross_street_day`,
`iron_cross_street_bloodmoon`, `raphael_cemetery`, `cathedral_plaza`, `university_quad`.

**Recurring motifs to sprinkle:** tarot cards (the pathway uses the Rider-Waite "The Magician"),
Fool number runes (1414), glowing geometric pathway sigils, pocket watches, gas-lamp halos in fog.

---

## 10. gpt-image-1 Hero Pipeline (illustrated heroes + painted backgrounds)

**Why (round 5):** Retro Diffusion's 384px pixel art is great for props/tiles/UI/VFX but read
too low-detail for the *important figures*. The hero assets moved to **gpt-image-1** (OpenAI
Images API), conditioned on the canon LotM reference art in `asset-gen/ref/`. Generator:
`generate_tingen_image2.py` → `asset-gen/out_image2/`. RD still owns props/tiles/UI/VFX (§7).

**What moved:** 19 characters + 9 portraits + 14 backgrounds.
- **Cast (19):** the base 17 **+ Audrey Hall + the Goddess of Darkness** (both have canon refs).
- **Portraits (9):** base 7 + Audrey + Goddess.

### Art direction (locked with Mark)
- **CHARACTERS = crisp anime / manhua illustration** faithful to the official LotM character
  art (cel-shaded, clean linework — NOT painterly, NOT photorealistic). Composited as
  transparent cutouts over the painted backgrounds.
- **BACKGROUNDS = painterly illustrated scenes** (match the painted canon location refs),
  split by game role:
  - **Establishing (6, eye-level)** — story beats: `klein_bedroom`, `klein_parlor`,
    `ritual_chamber`, `iron_cross_street_bloodmoon`, `backlund_skyline`, `warehouse_interior`.
  - **Top-down (8, inclined ¾ Stardew)** — explorable hubs: `iron_cross_street_day`,
    `cathedral_plaza`, `university_quad`, `raphael_cemetery`, `oldtown_street`, `hq_interior`,
    `library_archive`, `tavern_interior`.

### The endpoint & the one big constraint
- Use **`POST /v1/images/edits`** (multipart; accepts one or more `image[]` reference images).
  The plain `/generations` endpoint is text-only — used only when an item has no usable ref.
- **gpt-image-1 has NO seed.** Reference images + `input_fidelity` are the *only* consistency
  levers. Prompt detail + the right ref is how a character stays on-model across regenerations.

### The recipe (validated round 5 — copy this)
| Asset class | Refs passed | `input_fidelity` | Prompt shape |
|-------------|-------------|------------------|--------------|
| **Canon-ref char** (Klein, Audrey, Goddess) | the canon ref, **cropped** | **high** | "This exact person… match the reference's art style." |
| **No-ref NPC** (priest, widow, civilians…) | a clean anime **style anchor** (e.g. `player_detective_HIFI`) | **low** | "A distinct individual (NOT the ref person)… copy ONLY the rendering style… crisp cel-shaded anime, NOT painterly/photorealistic." |
| **Establishing BG** | the canon location ref, cropped | **high** | painted eye-level scene, "match the painted style of the reference." |
| **Top-down BG** | the canon location ref, cropped | **low** | "redraw from an inclined ¾ top-down (Stardew) angle, buildings upright, no horizon, no sky." |

Key lessons that produced this table:
- **`input_fidelity: high` is THE canon-faithfulness lever.** Without it (and with a painterly
  2nd ref diluting), Klein drifted far from `klein1`; with klein1-only + `high` + a
  style-matching prompt, the output landed on canon. (`player_detective_REFTEST` → far;
  `player_detective_HIFI` → faithful.)
- **No-ref NPCs need an explicit "cel-shaded anime, NOT painterly" push** or gpt-image-1's
  painterly default creeps back and breaks cast consistency (priest v1 painterly → v2 anime).
- **Top-down must use LOW fidelity** — the canon location refs are eye-level, and high fidelity
  clings to that framing and fights the overhead reframe. (`cathedral_plaza` proved low works.)
- **Crop the canon refs first** — they carry title cartouches / ornate frame borders / corner
  watermarks; cropping (`_refprep/`) stops the model copying that chrome.

### Ref → asset map
- **Characters:** `klein1`→player_detective/portrait_player; `audrey1`→audrey_hall/portrait_audrey;
  `goddess_of_darkness`→goddess_darkness/portrait_goddess; all other NPCs → style anchor only.
- **Establishing BG:** `kleinroom`→klein_bedroom, `kleinhouse`→klein_parlor,
  `goddess_of_darkness`→ritual_chamber (mood), `ironcrossstreet`→iron_cross_street_bloodmoon,
  `beckland`→backlund_skyline; `warehouse_interior` → interior palette anchor only.
- **Top-down BG:** `ironcrossstreet2`→iron_cross_street_day, `St-SelenaChurchTingen`→cathedral_plaza,
  `uni`→university_quad, `graveyard`→raphael_cemetery, `tingen_view`→oldtown_street;
  `hq_interior`/`library_archive`/`tavern_interior` → interior palette anchor only.

### Knobs & cost
- **Sizes:** characters `1024x1536`, portraits `1024x1024`, backgrounds `1536x1024`.
- **Background:** `transparent` for chars/portraits (clean cutouts), `opaque` for scenes.
- **Quality `high`** (≈$0.25/img). Full hero set (42) ≈ ~$10.
- Output is base64 PNG (`data[0].b64_json`); upscale/place in Godot as needed.

### Acceptance (in addition to §8)
7. **Characters read as one anime cast** — canon-ref heroes and no-ref NPCs share the crisp
   cel-shaded look; no painterly/realistic outliers.
8. **No identity bleed** — a no-ref NPC must never inherit Klein's face/coat from the style anchor.
9. **Top-down maps are genuinely inclined ¾ overhead** (walkable ground fills frame, no horizon),
   establishing scenes are eye-level and cinematic. Don't mix the two up per the role lists above.

### Run log & operational notes (run 1 — 2026-06-06)
Full 42-asset hero set generated and reviewed: 19 characters + 9 portraits + 14 backgrounds.
Total spend ≈ $11. All four recipe paths held; no style outliers, no identity bleed,
top-downs landed as walkable maps. Verified at full res: Klein (sprite + portrait),
Goddess portrait, cathedral_plaza / iron_cross_street_day / university_quad top-downs.

**Enemies (4) — added follow-up.** cultist_robed, bieber_monster, wraith_shadow, descent_horror.
No canon ref → rendered on the `player_detective_HIFI` style anchor at low fidelity via a dedicated
`ENEMY_STYLE` (drops the "pale fair-skinned European" trait, adds "occult-horror creature design")
and a "menacing enemy figure" prompt lead. They read as the same anime cast with no Klein bleed.
Run as `--category enemies`. Hero tier is now 46 assets (19 + 9 + 14 + 4).

Operational lessons for re-runs:
- **Latency is wildly variable.** Most images land in 60–130s, but outliers happen:
  `warehouse_interior` took 1427s (~24 min), `library_archive` 330s. Do **not** drive this
  with short foreground timeouts — run as background tasks (they can't time out) and wait
  for the completion notification.
- **Background tasks get reaped on a new user message / compaction**, but survive long idle
  stretches. The generator is resumable (skips existing files), so a reaped run loses nothing
  and never double-charges — just relaunch the same command.
- **`--limit` + `--treatment` gotcha:** `--limit` slices the front of the *full* category list
  *before* the treatment filter, so e.g. `--treatment topdown --limit 4` yields 0 jobs (the first
  4 items are all establishing). For a subset of one treatment, use `--treatment <t>` alone and
  let resumability skip the done ones.
- **OpenAI 500s are transient** — the built-in retry/backoff recovered `portrait_lady` on its own.
