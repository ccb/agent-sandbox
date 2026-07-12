# DESIGN — City fill rework (user-flagged)

**User complaint (verbatim intent):** "many buildings are either not at the right position, or
they are cut off and not full, please fix."

## STATUS (updated): un-slice pass DONE (`e3f6945`); regen + fine-placement REMAIN

The "cut off and not full" root cause is FIXED: `_trim_oversize.py` PAD was 8 map px, which sliced
Victorian rooflines (they overhang the painted footprint bbox far more than 8px) on 9 of 14
blocks. Now `PAD_OVERRIDE` recuts those from the untrimmed originals (cuts land in open street);
fill_11 went from a courtyard-only 416px slice to the full 717×849 rowhouse ring. Re-placed on the
fuller sprites, nudged 3 blocks clear of NPC waypoints, **12 legal FillBlock bodies, suite
1890/0/0**. Composite reads dense with full buildings.

**What REMAINS (needs OpenAI image budget + a visual tweak loop — do with fresh credit):**
- **Regenerate** fill_06 (source 2× too tall → squat ~120×102 map-px comp), fill_10, fill_14
  (unfaithful crop, currently dropped). Use `_generate_fill.py` (OpenAI env-file, main loop).
- **Hand-place** fill_03 (dropped — match score 0.387, sits on bram_kell's canal path; needs
  eyeballing against the map, or move the waypoint in npcs.json).
- **Fine-tune low-confidence positions**: fill_07 (0.31), fill_10 (0.22), fill_13 (0.28) — small
  world-px tweaks in `_tweaks.json`, verify by eye.
- The critic's 6 whole-map extras (`fill_diagnosis_verdicts.json` critic block): ~5 painted
  blocks the block-finder MISSED entirely (bottom-center St Raphael Cemetery district, a tenement
  SW of the police station, etc.). These need `_find_blocks.py` re-run with a lower threshold, or
  manual block addition — a genuinely additional pass beyond the 14.

The apply-loop protocol below still applies for those remaining items.

## 1. What the fill is

The reference painting `asset-gen/my_assets/map_v3.png` (1254×1254 map px) minus the bare-ground
`map_bg.png` yields 14 painted building blocks that the 20 landmark buildings don't cover.
Pipeline (all in `asset-gen/out_image2/buildings/fill/`):

```
_find_blocks.py      map_v3 vs map_bg diff -> _blocks.json (14 blocks, bboxes in map px)
_generate_fill.py    gpt-image-2 per block: map crop -> "more detailed, true to the provided
                     image" upscale on WHITE bg -> keyed via ../key_building.py --white 222
                     --erode 2 -> keyed/fill_NN.png  (needs OpenAI key: --env-file
                     '/Users/markma/Desktop/Yumina Master/yumina/.env'; RUN FROM THE MAIN LOOP,
                     subagent permission walls deny that path)
_place_fill.py       masked-NCC template match of each keyed sprite against map_v3 ->
                     _placements.json {world_center, world_scale, score, block_bbox, ...}
_trim_oversize.py    crops keyed sprites whose matched extent >> block bbox (image-2 cutouts
                     often keep NEIGHBOURING blocks). PAD = 8 map px. Originals -> keyed/orig/.
                     IDEMPOTENT: always re-trims from keyed/orig.
_apply_scene.py      writes FillBlockN bodies into tingen/scenes/City.tscn. Reads _placements.json
                     + _tweaks.json {name: {dx, dy, dscale, drop}} WORLD-px nudges. IDEMPOTENT:
                     strips every fill_* ext_resource / fill_block* sub_resource / FillBlock* node
                     then re-appends -> other nodes (interior doors!) survive. Copies sprites to
                     tingen/assets/props/. Embeds uids if .import files exist (re-run once after
                     godot --import).
_qa_render.py        renders current placements -> _fill_composite.png + _fill_overlay.png
                     (55% alpha over map_v3, 2x map res)
```

Coordinate spaces: **world = map px × 5** (CITY_SCALE). Composite/overlay = map px × 2.
Sprite px × `world_scale` = world px. `_tweaks.json` dx/dy/dscale are **world px**, applied on
top of `_placements.json`; `{"drop": true}` removes a block (fill_14 is dropped — its map crop
was an unfaithful top-edge sliver).

## 2. Why it's wrong (root causes, established)

1. **PAD=8 trim slices buildings.** `_trim_oversize.py` keeps only 8 map px beyond the painted
   bbox. Where the template match was imperfect, the crop lands INSIDE rooflines → the "cut off
   and not full" complaint. The untrimmed originals survive in `keyed/orig/` — recuts are free.
2. **NCC matching on non-pixel-faithful art.** gpt-image-2 "faithful" upscales stylize; masked
   NCC then lands on plausible-but-wrong offsets. Low scores = suspect positions:
   fill_02 = 0.327, fill_12 = 0.405, fill_05 = 0.583. Blocks hand-fitted in QA round 2
   (fill_04, 07, 10, 13) may still be off — they were fitted against the previous composite.
3. Some source generations may themselves be incomplete/wrong-content (top-edge blocks 02/07
   ride the map border; the model sometimes painted adjacent content). Regeneration is in
   budget (fill spend 28/52 images).

## 3. Diagnosis fan-out (ALREADY RUN — reuse the results)

A 14-judge visual QA workflow examined every block: side-by-side panels
(`_qa_panels/fill_NN_panel.png`: LEFT reference / RIGHT in-scene, title bar gives zoom + crop
origin) + a whole-map critic on `_fill_overlay.png`. Each judge returned a structured verdict:

```json
{"block", "position_verdict": "ok|off_slightly|off_badly|absent",
 "offset_map_px": {"dx", "dy"},  // + dx = move sprite right, in MAP px (world = ×5)
 "scale_factor", "sprite_verdict": "full|cut_off|wrong_content|missing",
 "cut_edges": ["top"...], "orig_is_better": bool, "severity": 0-3,
 "recommended_fix": "keep|retweak|recut_from_orig|recut_and_retweak|regenerate|place_missing",
 "confidence", "notes"}
```

**The verdicts are IN THIS DIRECTORY: `fill_diagnosis_verdicts.json`** (`{verdicts: [14],
critic: {extra_problems: [6], summary}}`). Summary table:

| block | position | sprite | sev | fix |
|---|---|---|---|---|
| fill_01 | off_slightly | full | 1 | retweak (dx −3, dy −1 map px) |
| fill_02 | off_slightly | cut_off (bottom) | 2 | recut_and_retweak |
| fill_03 | off_badly | cut_off (top,right) | 2 | recut_and_retweak (dy −24.5!) |
| fill_04 | off_slightly | cut_off (t,l,r) | 2 | recut_and_retweak (recut → residual ≈0) |
| fill_05 | off_slightly | cut_off (t,b,r) | 2 | recut_and_retweak (scale ×0.84!) |
| fill_06 | off_slightly | cut_off (bottom) | 2 | **regenerate** (source 2× too tall — squat ~120×102 map-px comp needed) |
| fill_07 | off_slightly | cut_off (l,b) | 2 | recut_and_retweak |
| fill_08 | off_slightly | cut_off | 2 | recut_and_retweak |
| fill_09 | off_slightly | cut_off | 2 | recut_and_retweak |
| fill_10 | ok | full | 2 | **regenerate** (see notes in JSON) |
| fill_11 | ok | cut_off | 3 | recut_from_orig |
| fill_12 | off_badly | cut_off | 3 | recut_and_retweak |
| fill_13 | off_badly | full | 2 | retweak |
| fill_14 | absent | wrong_content | 3 | **regenerate** (currently dropped) |

Read each block's `notes` in the JSON before acting — they carry exact recut boundaries
(e.g. fill_02: "recut from orig along the natural facade boundary ~map y 90-95, orig row
~240-260, then nudge ~4 map px left"), independent offset derivations, and two judge cautions:
(a) fill_05's PANEL title-bar coords were wrong (its offsets are in true map_v3 px — trust the
JSON, rebuild panels before the verify round); (b) fill_06's overrun currently HIDES its
neighbor's slice — fixing one exposes the other, so verify rounds must re-judge neighbors.
The critic's 6 whole-map extra_problems are in the same JSON.

If you need to re-run the fan-out after applying fixes (the verify round — you should):
the template is `WORKFLOWS.md` §2 and the panel builder is described in §4 below; ~15
judge-agents, no image budget.

## 4. The apply-loop (YOUR JOB — single writer, verify rounds)

Round protocol (repeat ≤4 rounds; each round is cheap):

1. **Partition verdicts**:
   - `keep` → nothing.
   - `retweak` → merge `offset_map_px×5` into `_tweaks.json` (ADD to existing entries — tweaks
     are absolute-cumulative on top of _placements.json, so read the current file first).
   - `recut_from_orig` / `recut_and_retweak` → edit `_trim_oversize.py` (make PAD a per-block
     dict, e.g. `PAD = {"default": 8, "fill_06": 28, ...}`, or skip trimming that block entirely
     when the judge says the orig has no neighbour-bleed) → re-run it → **re-run `_place_fill.py`**
     (a recut sprite has a new center; its old placement/tweak is stale — clear that block's
     `_tweaks.json` entry when you recut).
   - `regenerate` / `wrong_content` → re-run `_generate_fill.py` for those blocks only (it is
     resumable/skips existing; delete the block's files in `keyed/` + the `fill_NN_detailed.png`
     to force regen). Needs the OpenAI env-file (main loop only). Then key → place as above.
   - `place_missing` / critic's "large empty painted block" → check first whether it's one of
     the 4 waypoint-protected lots (npcs.json waypoints sit on them — moving DATA is allowed if
     you keep placements legal, but prefer leaving them bare).
2. **Apply**: `python3 _apply_scene.py` (it pre-checks placements-legal: no staged point/waypoint
   inside a fill collider, 20px clearance — it refuses rather than bury an NPC).
3. **Render + panels**: `python3 _qa_render.py`, then rebuild `_qa_panels/` (the panel-builder
   snippet lives in RUNLOG-adjacent history; 20 lines of PIL — reference crop left, composite
   crop right, min ~700px wide, zoom in title).
4. **Verify fan-out**: fresh judges on the new panels (same schema). Exit when every block is
   severity ≤1 AND the whole-map critic finds nothing new.
5. **Land it**: `godot --headless --path tingen --import` → full suite (`tests/run_tests.gd`) —
   the `[city buildings]` block asserts every FillBlock body (uniform scale, textured sprite,
   opaque-bbox collider coverage, placements-legal). Re-run `_apply_scene.py` once post-import to
   embed uids. Commit with a per-block table in the message (see `05a61d8` for format).

**Do not trust NCC scores as truth** — they are advisory. The judges' eyes (and yours: read the
panels yourself for at least the severity-3 blocks) are the acceptance gate. The user looks at
the composite; that is the contract.

## 5. Known traps

- `_apply_scene.py` strips ONLY `FillBlock*`/`fill_*` — interior door nodes survive. But if the
  interiors commit landed doors ON a FillBlock (shouldn't — doors belong to landmark buildings),
  they'd be stripped: `grep -i door tingen/scenes/City.tscn` before/after.
- After changing sprites in `tingen/assets/props/`, Godot needs `--import` before the suite sees
  textures (14 "textured Sprite2D" asserts fail otherwise — that's the import, not your bug).
- fill_03's +120y tweak exists because bram_kell's late-night canal waypoint moved onto that
  block mid-build. Placements-legal will catch regressions here.
- The map's top-edge blocks (02, 07) genuinely clip at the canvas: "full" for them means
  faithful-to-the-painting, not architecturally complete.
- Never run two `_apply_scene.py` invocations concurrently with anything else editing City.tscn
  (interiors agent). Single-writer discipline: coordinate via task messages.
