## 2026-07-15
**Focus:** a Williams-Hall + viewer cleanup pass on `godot-ga-main`, all driven by the user's local visual testing — merged two Wil
liams PRs (reproducibility, then de-thin + solidify walls) and opened the co-located-agent fan-out, each via brainstorm→spec→plan→(
SDD or inline).

**Done today:**
- Merged **#571** (closed #552): made the Williams map derivation byte-reproducible — `williams_arenas` is authored input (read fro
m the tmj, not the constant), the south door is single-sourced at cols 43–44, `furnish_building`'s legacy Williams repaint hard-ref
uses, run-order/authored-vs-derived docs, and a round-trip regression test. Then **#573** (closed #572): de-thinned the double wall
s to single-thickness and **solidified all 46 exterior windows into wall** (owner's Tiled edits, normalized through `furnish_willia
ms` + re-derived `collision`/`arena` matrices) with a no-double-wall regression test. Deleted both branches; closed the issues with
pointer comments.
- Two gotchas surfaced landing #573: Tiled saves `williams_arenas` in a different whitespace style than `furnish_williams._object_l
ayer_block`, so a raw Tiled save isn't byte-identical to the canonical splice → resolved by treating `furnish_williams` as the cano
nical writer (normalize the edit through it, commit that; verified formatting-only + self-reproducing). And the owner's "de-thin" h
ad painted the inner wall line with a `decor_plants` tile *on the collision-feeding walls layer* (still sealed as wall) → erased th
ose 81 cells so the walls are genuinely 1-thick.
- Opened **#576** (#560, viewer fan-out): scoped it as cosmetic (interactions key on engine `Location`, never tile proximity — no v
iew radius anywhere), so fixed viewer-only — new pure `agent_fanout.gd` (headless-tested, mirrors #372) + `viewer.gd` wiring; two v
isual-review rounds retuned the ring to sprite-scale spacing and eased the offset so co-located agents glide into formation instead
of teleporting.

**Blockers / questions:**
- **#576** needs the merge (manual visual confirmed by the user); the Godot viewer still isn't CI-covered, so the local smoke suite
+ eyeball remain the only gate on viewer changes.
- Backend occupancy-aware routing (agents genuinely on distinct tiles, not just drawn apart) is deliberately deferred — it perturbs
the byte-pinned deterministic replay for only partial coverage; worth it only if a range-based perception model (the `audience_for
` radius override) is ever built.
- Geo scripts default `--tmj`/`--matrix` to the *committed* files, so a stray default-path run minifies the committed tmj (an SDD s
ubagent hit this once) — a real footgun that still isn't guarded.

**Next:**
- Eyeball CI + merge **#576**, close #560 with a pointer.
- Pick up the remaining environment follow-ups: **#559** (teacher-at-blackboard / role-aware furniture) and **#561** (walk-on-walls
— likely the #538 collision-seal class map-wide; wants a `validate_tmj` "wall-category tile on a walkable cell" check).
- The live-LLM cognition cluster (**#371/#370/#368/#366**) + **#543** stay on Alistair's track, unassigned pending #542.

## 2026-07-14
**Focus:** a full clip-export + geo push on `godot-ga-main` — merged three features (via brainstorm→spec→plan→SDD each), then chased a black-GIF bug, GIF quality, and a geo regression through several rounds of the user testing locally.

**Done today:**
- Merged to `godot-ga-main`: **#544** furniture-aware destinations (closed #537), **#550** clip export (closed #488), **#558** `entrance_floor` FORCED_CLOSED repaint + surgical Sweeten ghost-door seal + a `validate_tmj` guard (closed #556); deleted the branches. Assigned nine environment issues to myself; filed **#548** (live clips), **#551** (shared "deciding" signal), **#556**. **#555** (thinking indicator) shipped + green but still open.
- Clip export (#550) went several user-testing rounds: fixed a **pitch-black GIF** — a real LZW code-width early-change bug the self-mirroring round-trip test missed (now pinned against a standard decoder + verified with PIL); then muddy quality → **960px/nearest + Bayer dithering**; then a one-click **Export MP4 + GIF** that runs ffmpeg directly (no copy-paste from the status line).
- Caught a geo regression from a manual pipeline re-run (a tmj regen re-opened Van Pelt's east door + churned a layer id) → reverted, root-caused, filed+fixed as **#556**; the SDD run then caught my own mis-scoped guard (whole-layer sweep → 2954 false positives) and I narrowed it to `FORCED_CLOSED` cells.

**Blockers / questions:**
- **#555** needs live-backend acceptance (`--brain llm` for real 5–10 s decision stalls) before merge — no headless test by design.
- **#543** (resume a persisted run) stays blocked on Alistair's **#542** (#306 first half) still open.
- Godot viewer code isn't CI-covered (no Godot job — checks are Python/geo/web), so the **local smoke suite** is the real gate on viewer changes; a GDScript parse error once hid for a whole debug loop because of this.

**Next:**
- Acceptance-pass + merge **#555**, then a fresh bake to see the thinking cue + furniture destinations together.
- Start the cognition/live-loop cluster (**#371/#370/#368/#366**), or **#543** once #542 lands.
- Later: migrate #555's inferred cue (and #525's web-companion thinking state) onto the authoritative **#551** "deciding" signal once it's built.

## 2026-07-10
**Focus:** landed the whole reconciled PR queue on `godot-ga-main` (nine merges over the #481/#482 base moves), closed out the delivered issues, then shipped two viewer timeline features — event markers (#249, **PR #508**, merged) and the day-plans ribbon pop-up (#251, **PR #509**, CI green).

**Done today:**
- Merged the queue in dependency order — **#468/#463/#480/#484/#501/#465/#476/#478/#507** — each rebase-reconciled over the #481 backend refactor + #482 tools move (rename-carries into `cognition.py`/`tools/geo`, cell-level three-way splices of the single-line `collision_maze.csv`); the boil-water arc is now end-to-end on `godot-ga-main` (verbs → run-record events → props → HUD rows). Closed the delivered issues (#270/#300/#305/#393/#466/#467/#502, later #249) and deleted the nine merged branches, local + remote.
- Review pass on #476/#478 produced two fixes that landed same-day: **#501** pinned `EventState` + the replay `events` key into the #305 contract before #476 could drift it, and **#507** taught the live HUD to render `kind:"game_event"` rows via a `summary` fallback (filed as #502).
- Shipped #249 (**PR #508**): colored click-to-seek markers above the scrubber (game events / chat onsets / reflections / arrivals — arrival = the `"walking to "` act prefix disappearing, since travel acts already carry the destination address), plus the repo's **first headless GDScript unit tests**, wired into `run_smoke_test.sh` with a parse-error sentinel (Godot exits 0 on `--script` parse errors). Then #251 (**PR #509**): day-plans pop-up pairing each agent's authored schedule against what they actually did — planned↔actual paired exactly by learning place→address from the walking legs, no heuristics; subagent reviews caught two plan-authored bugs (stale planned-segment cache under a growing live axis; anchors-only preset leaving the modal a 0-size rect).

**Blockers / questions:**
- **PR #509** needs the manual visual pass before merge — look hardest at the modal itself (centered, dimmed, click-outside closes): that's exactly where the final review's Critical sat.
- **PR #496** (untrack the committed `.godot/` cache + close the `.gitignore` gaps) is ready but deliberately held; until it merges, the editor cache stays tracked on `godot-ga-main`.
- #464 (lift the Penn-local verbs into the engine) stays gated on the Thursday #446 verb-API discussion.

**Next:**
- Eyeball + merge **#509**, close #251 — then a fresh bake gets both timeline features in one viewer session.
- Start #304 (persistence layer for live runs) — next in the chosen #305 → #304 → #307 chain toward saving/replaying live LLM runs.
- #397 (Penn-aware LLM day planner) after that; the new ribbon renders whatever it writes into `schedule`, so plan quality becomes visible at a glance.

## 2026-07-09
**Focus:** shipped the boil-water scenario end-to-end (#300/#466/#467 → **PRs #465/#476/#478**), and cleared a second `godot-ga-main` wave — the #367 cache `--live` verifier (**PR #463**), Van Pelt entrance routing (**PR #468**), and the viewer reset-follow (#393).

**Done today:**
- Landed the #300 world half (**PR #465** → `godot-ga-main`): `DrinkPenn` sickens on `requires_boiling` + not `is_boiled` (one-shot `just_sickened` marker, `sickness` GameEvent, importance-8.0 memory), `activate`/`deactivate` device verbs, Houston Hall stocked with sink/stove/pot/cups, and mock-brain replay of authored per-stop `commands:` (Sofia's dinner stop). Two engine bugs found and worked around backend-locally (parser `"ate "` substring mis-route, `Stop` round-trip dropping `commands`) — itemized on #464; verb list posted to #446.
- Two boil-water follow-ups on #465: the GameEvent log persisted into run records (#467, **PR #476**) — replay `events` key + `events.json` + a live `kind:"game_event"` feed, so #299 counts sickness events straight from the record; and the kitchen props on the map (#466, **PR #478**) — `UPenn:Houston Hall:lobby:{sink,stove,pot}` routable at the game-object tier, `add_game_objects.py` generalized to all `*_objects` layers (Fisher byte-identical; smoke + validator + 129 geo / 63 godot / 1342 root green).
- Cleared a second `godot-ga-main` wave (brainstorm→spec→plan→subagent-driven each): the #367 cache tripwire gained a `--live` write→read verifier + repo-`.env` load + a backend-README cache-fields note (**PR #463**, CI green); Van Pelt's entrance rerouted from the auto-carved east door (into the Moelis reading room) to a south door at the front `Entrance` room via `add_entrances` `FORCED_DOORS`/`FORCED_CLOSED` + a surgical tmj edit (**PR #468**, CI green); and the live viewer now auto-follows a `POST /reset` in place — teardown + respawn keeping `_last_cursor`/socket (#393, reviewed, manual eyeball pending).

**Blockers / questions:**
- All three PRs need review — order matters: #465 first, then #476 (stacked, auto-retargets on merge) and #478 land independently; a fresh replay bake for Thursday only makes sense after they merge.
- The viewer's HUD doesn't *render* `game_event` rows yet (its generic engine rows draw only `text`-bearing records) — the feed carries them fine; on-screen surfacing is a one-liner in `add_engine_event`, #302/#264 territory.
- A `furnish_houston.py` rerun strips and rebuilds `houston_furniture`, silently wiping the hand-painted strip — pinned by a tmj sprite test + a warning comment for now; teaching the furnish script to place the strip from the (now-verified) catalog entries is open.

**Next:**
- Thursday #446 meeting: verb-API discussion; the #464 engine-upstreaming list (device verbs, drink effect, parser fix, `Stop` extensions) is gated on it.
- After #465 + #478 merge: the 5-line follow-up routing Sofia's dinner stop to `UPenn:Houston Hall:lobby:sink`, then a fresh replay bake to watch her walk to the sink and get sick on screen.
- Start #301 — the self-coding seam. The success condition is already pinned: a self-coded boil only has to set `is_boiled` (`test_boiled_water_is_safe_to_drink`), and its `sickness` events are now countable straight from the run record.

## 2026-07-08
**Focus:** cleared the ready `godot-ga-main` PR queue and verified #367 prompt caching end-to-end (offline predictor + live Haiku run).

**Done today:**
- Merged the ready `godot-ga-main` queue in dependency order — #391 wall-collision fix (**PR #416**) → geo CI + `validate_tmj` drift gate (#390, **PR #421**) → viewer `kind:"engine"` feed records (#394, **PR #418**) → converse-once-per-step guard (#187, **PR #419**); checker landed before the gate so CI stays green.
- Proved #367 prompt caching is a silent no-op on the live Penn cast — the persona+tools prefix is ~200 tokens, ~20× under Haiku's 4096 floor — confirmed live via `serve_penn --brain llm` (`cache_creation`/`cache_read` held 0 while cost climbed). Committed the offline predictor as `cache_prefix_check.py` (#367).
- Exercised the live LLM brain to confirm the sim path is complete: real Haiku decisions, event-driven (one per schedule transition, not per tick), `/usage` accounting + `LlmCallMonitor` rows working, loop healthy at step ~589/1200.

**Blockers / questions:**
- #367 stays dormant until the stable *system* prefix (a map/rules/action-catalog preamble, or the memory/planning phases) clears the model floor — the per-turn observation renders after the cache breakpoint and never counts; `cache_prefix_check.py` is the tripwire.
- The live cast makes very few calls (~6 in the opening burst, then a long plateau through multi-hundred-step activities), so it barely exercises caching or cost — a real caching test needs a bigger prefix, not a longer run.
- `cache_prefix_check.py` is committed on `feat/cache-prefix-check-367` but not yet pushed / no PR opened.

**Next:**
- Push `feat/cache-prefix-check-367`, open a PR to `godot-ga-main`, and add a "reading the live cache fields" note to the backend README.
- Add a `--live` two-call verifier that proves the #367 caching wiring fires once a >4096-token prefix is used.
- Tidy up: delete the four merged head branches (#416/#421/#418/#419).

## 2026-07-07
**Focus:** shipped the per-agent inspection API (read + write), cleared the post-#400-restructure merge/geo fallout, and kicked off the live-LLM cost/quality roadmap.

**Done today:**
- Landed the per-agent inspection surface on `godot-ga-main`: read-only retrieval probe (#346, **PR #403**), daily-plan endpoint (#347, **PR #404**), and user interventions — `POST /agents/{name}/say` + `POST /world/event` (#369, **PR #405**) — completing #266's M2 read+write family.
- Cleared the #400/#399-restructure fallout: rebased #401/#403/#404/#405 (and #402 furniture) onto the moved tree, then fixed the repo-wide `tools/geo` path breakage — 37 files repointed at the relocated tmj (`godot/maps/`) + matrix (`backend/penn/…`), greening the whole geo suite (#413, merged).
- Opened roadmap follow-ups: `the_ville` seeding path regression from the package move (#407, **PR #414**) and Anthropic prompt caching on the stable persona prefix (#367, **PR #415**).

**Blockers / questions:**
- #390 (wire the geo suite + `validate_tmj` drift-gate into CI) is committed but unpushable — the `gh` HTTPS token lacks the `workflow` OAuth scope to write `.github/workflows/`; needs a one-time `gh auth refresh -h github.com -s workflow`.
- Prompt caching (#367) is a silent no-op on Haiku until the persona+tools prefix clears the 4096-token minimum — a real saving only once personas grow; confirm via the usage cache fields on a live run.
- CLAUDE.md still says `backend-api` work targets `main`, but after #400 the backend + inspection endpoints actually live on `godot-ga-main` — the doc and the branch reality disagree; worth reconciling.

**Next:**
- Refresh the `workflow` scope and push #390 so a tmj⇄matrix drift can't silently land again.
- Pick up #397 (Penn-aware LLM planner) — `LLMPlanner` is already built, just needs Penn goals + campus locations wired.
- Merge the ready PRs (#414, #415) and rebase whichever geo PR lands second (#390 vs #402 both touch `tools/geo`).

## 2026-07-06
**Focus:** made furniture solid in the UPenn matrix and made Fisher's bookshelves/chairs addressable game-objects.

**Done today:**
- Shipped furniture solidity + interactable game-objects as **PR #402** (stacked on #401): `block_furniture.py` seals every `*_furniture` tile into `collision_maze` except a JSON seat allowlist, `add_game_objects.py` paints a `fisher_objects` layer into `game_object_maze`, plus a "Furniture solidity" menu in `catalog_web.py` and a furniture check family in `validate_tmj.py`.
- Seeded the walkable-seat allowlist from `furniture_catalog.json` labels, then (on review) moved Fisher's 11 bookshelf use-tiles onto the now-walkable shelf bottoms + 8 armchair reading-seats — all 19 resolve as `UPenn:Fisher Fine Arts Library:<room>:<object>` through unchanged `world_map.py`.
- Verified end-to-end: 123 geo + 1123 engine tests, `validate_tmj` 0 errors, pipeline idempotent, replay re-baked with agents routing around furniture.

**Blockers / questions:**
- `block_furniture` is seal-only (never re-opens), so an allowlist edit needs a regen from a furniture-free baseline, not just a re-run — and `check_furniture_solidity` only guards that direction. Footgun worth a follow-up guard.
- Reported "agents walking on Van Pelt walls" turned out to be a rendering artifact — the wing walls are 100% solid in collision, unchanged by this branch — so it needs a viewer-side look, not a matrix fix.
- #402 can't land until #401 merges (it depends on #401's `ROOM_SUBDIVIDE` wiring); needs retargeting afterward.

**Next:**
- Retarget #402 to `godot-ga-main` once #401 merges.
- Extend interactables past Fisher (other buildings' shelves/desks) and decide the sofa / student-desk seat tiles left solid pending review.
- Wire the `game_object` addresses to engine actions (sit / grab a book) — the verbs are still deliberately out of scope.

## 2026-07-03
**Focus:** primarily focused on research symposium planning and code review

**Done today:**
- Unstuck **PR #311** (black-format CI fix): merged `main` in, took main's side of the Tomb/test conflicts, re-blacked those plus the 7 newer slots/wounds files — PR is mergeable again, 1068 tests + format gate green.
- **Synced `godot-ga-main` onto today's `main`** — an 89-commit rebase with ~20 conflicts (the `gen_agents`→`backend` rename, reordered picks, and 9 rounds on the baked `.tmj`/maze CSVs, resolved with layer-level and cell-level three-way merge scripts). Force-pushed as `29719b7` after tests + the Godot smoke test passed.
- A final diff against the pre-rebase tip caught a real regression the merges had snuck in (`trees`/`plants` left `visible:false`) — fixed by restoring the original tip's `.tmj` verbatim; pinged @aking526 on PRs #314/#308 with the `rebase --onto` recovery command.

**Blockers / questions:**
- Post-mortem: `git merge-tree` shows the two tips merged **conflict-free** — every rebase conflict was self-inflicted by replaying pre-rename history. Do we want linear history on `godot-ga-main` badly enough to keep paying that, or should the sync convention be a plain merge (as 21ff6be did)?
- #314/#308 sit on the old history and can't merge until @aking526 rebases them forward.
- The tmj/CSV three-way merge helpers that made the rebase tractable live in `/tmp` — gone with the next reboot.

**Next:**
- Merge PR #311 once CI confirms, so `main`'s format gate goes green.
- Promote the tmj layer-merge + maze cell-merge scripts into `tools/geo/` (with the "diff the final result against the pre-rebase tip" check that caught the visibility bug).
- Write the sync decision (merge vs rebase) into the `godot-ga-main` section of CLAUDE.md so the next sync doesn't relearn it.

## 2026-07-02
**Focus:** worked on fleshing out planning for game loop and agents architecture

**Done today:**
- opened issues #296-#302, along with a proper roadmap of how the game architecture should be devised
- merged almost all furnished buildings to `godot-ga-main`
     - currently, the game doesn't have the Jaffe and Alpha Phi Rho furnished or built. Those could be for parties (similar to the original `generative-agents`) and other tasks we might not have thought of

**Blockers / questions:**
- the game-loop + agents architecture (#296-#302) is still just a roadmap — the backend ⇄ Godot boundary and the LLM-modifiable inner loop need a prototype before the interfaces are trustworthy
- the furnished buildings are only maps right now; how agents actually occupy and use them (schedules, per-building tasks) isn't wired into the cognitive loop yet

**Next:**
- turn the #296-#302 roadmap into a first buildable slice — likely the backend ⇄ Godot websocket loop
- build/furnish the remaining shells (Jaffe, Alpha Phi Rho) and decide what they're for (party venues, etc.)
- carve doorways into the Sweeten dorm suites so they're actually navigable (carried from 07-01)

## 2026-07-01
**Focus:** furnished more UPenn buildings via per-building `tools/geo` scripts — Cohen Hall's cafeterias, then the newly-combined Sweeten Alumni building's dorm suites.

**Done today:**
- Built **`furnish_cohen.py`**: Cohen Hall (sector 7) stone-hex floor, a kitchen walled off with serving counters, and three cafeterias holding 22 dining tables with food (**PR #295**, merged).
- Combined **3537 Locust Walk into the Sweeten Alumni building** — bridged the 1-tile gap so both footprints share one sector/interior, regenerated the matrix, tiled the floor, and opened a north entrance via a new `add_entrances` `FORCED_DOORS` hook (**PR #293/#294**, merged).
- Built **`furnish_alumni.py`** for the two dorm suites from a hand-drawn `alumni_arenas` layer: silver partition walls at box overlaps (kitchen/living/hallway left open-plan), hallway carpet, and franuka-style furniture across bedrooms, baths, eat-in kitchens, and lounges.

**Blockers / questions:**
- Editing the `.tmj` in Tiled/Godot re-saves it **pretty-printed** (a whole-file whitespace diff); the repo tracks the minified form the scripts write, so in-editor edits have to be re-minified or folded back through a script.
- Verification is visual only (rendered PNGs / ASCII dumps) — nothing automated checks furniture stays on walkable floor, off walls, and clear of doorways.
- Dorm rooms are still **sealed** (walls only where boxes overlap, no doorways carved yet), and one lounge's plant was dropped for lack of space.

**Next:**
- Carve doorways from the dorm bedrooms/baths into the hallways so the suites are actually navigable.
- Add a small lint/render helper for furnishing scripts (footprint-on-floor, no-overlap, doorway-clear) instead of eyeballing.
- Furnish the next building with the same floor → walls → furniture layer pattern.

## 2026-06-29
**Focus:** landed Van Pelt Library furnishing and the franuka catalog UI; finished the east-wing room layout.

**Done today:**
- Furnished Van Pelt as **25 navigable per-room arenas** via the door-gated system — transplanted the hand-designed interior onto the live picture, subdivided rooms in `add_entrances.py`, regenerated map + matrix, and cleared phantom wall sprites on auto-doorway cells. Merged as **PR #268**.
- Shipped the franuka catalog UI: ~50 more catalogued tiles, in-browser edit/rename persisted in `localStorage` (keyed by `origKey`), and a 23-tile general-library tile preset. Merged as **PR #269**.
- Finished the east-wing room layout — single-tile doors that open only onto the open area, and floored the Kamin Gallery seam so the throat connects both wings.

**Blockers / questions:**
- The latest franuka batch was catalogued **unverified** (read off the `preview_catalog.py` contact sheet, not the known-good palette), so coordinates need an eyeball before being relied on.

**Next:**
- Furnish the next campus building (Fisher) with the same door-gated room system + library preset.
- Verify the unverified franuka tiles against the contact sheet.

## 2026-06-26
**Focus:** made the map-furnishing pipeline data-driven via a labeled tile catalog, then regenerated the UPenn matrix + map.

**Done today:**
- Added `furniture_catalog.json` — a labeled manifest of the three interior sheets (franuka/school/bath), each object keyed by name with `(sheet,col,row)`, a w×h footprint, and a category + room tag — and rewired `furnish_building.py` to resolve every palette constant from it (GIDs unchanged, painted map identical); added `preview_catalog.py` to render a labeled contact sheet.
- Expanded the catalog 41→55 objects: colored double beds/armchairs, a sofa, rugs, a dresser, a candelabra, and a new kitchen category (counter).
- Regenerated the UPenn matrix + map to a consistent 239×273 grid; dropped the blanket `*.json` ignore so the matrix meta is tracked.

**Blockers / questions:**
- New catalog coordinates were eyeballed off the contact sheet rather than the working palette, so they're flagged unverified pending visual review.

**Next:**
- Verify the catalog tiles visually, then add building wall tools + tile-usage presets on top of the catalog.

## 2026-06-25
**Focus:** working on issue #87 (surfacing chat end to end), testing a real LLM run, and working on game planning

**Done today:**
- Closed out **Phase E #87 (surface chat end to end)**: confirmed the path was already wired (frontend slot + render since #72, population since #86, verbatim export) and locked the export boundary with a new regression test, `test_exporter_surfaces_populated_chat`. Opened **PR #180** stacked on `feat/issue-86-dialogue-seam`; 99/99 port tests pass, black-clean.
- Added a **per-turn heartbeat** to the sim loop (`run_simulation.py`, commit `6972cd3`) so long real-LLM runs report progress (turn, in-game time, +LLM calls, chats) instead of looking hung — stdout-only and gated on a real client, so mock replays stay byte-identical.
- Ran a full **1080-step real-LLM run** ($0.48) and verified the GA cognitive loop end-to-end: 5/5 daily plans, 27 reflections, 24 chat-frames across 2 pairings.

**Blockers / questions:**
- **Deep PR stack**: #180 sits on #86 → #84 → #83 → #78. Each parent must merge (and the child retarget to `main`) before #180 can land — nothing merges in isolation.
- **Shallow planner depth**: agents latch onto a terminal activity and stop circulating; all movement is front-loaded (everyone settled by ~08:20 of a run that nominally goes to 10:59). Emergent all-day spatial behavior isn't there yet.
- Real-LLM runs are slow and serial (many blocking API calls per turn) — the heartbeat makes this visible but doesn't speed it up; iteration on cognition is gated on run time.

**Next:**
- File the deferred **planner-depth** issue: recursive hierarchical decomposition (outline → hourly → 5–15 min chunks) plus a non-latching execution loop so agents move through town all day.
- Shepherd the stack toward `main` — get #86 reviewed/merged, then retarget and land #180.
- Do a fresh real-LLM run once planner depth improves and re-check the replay for genuine all-day movement.

## 2026-06-24
**Focus:** shipped the next two cognitive-loop phases for the Smallville port — periodic reflection (#84, Phase D) and the agent-to-agent dialogue seam (#86, Phase E).

**Done today:**
- #84 periodic reflection: new engine `reflection.py` (`should_reflect` importance threshold + `reflect()` flow → salient questions, supporting retrieval, grounded inference, write-back as `MemoryKind.REFLECTION`), with a `Reflector` protocol + Mock/LLM impls mirroring the planner split; wired into the ReAct loop and the sim via `maybe_reflect`. PR #169.
- #86 dialogue seam: new `conversation.py` turn-taking loop + `Agent.converse` seam + `MemoryKind.CHAT`, writing each line into **both** participants' memory streams; co-located/settled residents converse in the sim and the line shows on the replay's chat card (reused the existing `audience_for` + unused frontend slot). PR #170.
- Both are off/gated unless a real brain is driving, so the mock replay stays byte-identical; full offline coverage added (732 engine + 98 port tests green, black-clean).
- Tested live with `LLM_PROVIDER=anthropic`

**Blockers / questions:**
- Stacked PRs against the feature stack, not `main`: none of #78/#83/#84/#86 are merged yet, so merge order matters — #84 (#169) should land first, then retarget #86 (#170) to `main`. Want to confirm the team's intended base/merge strategy.
- Briefly branched #86 off `main` before realizing `main` predates Phase A (#78), which the port wiring needs; rebased onto the #84 tip.
- Neither feature has touched a live model yet — verified only with mock/scripted brains, so real reflection/dialogue quality and 25-agent token cost are unvalidated.

**Next:**
- Get #169/#170 reviewed; retarget #86 to `main` once #84 merges.
- Phase C proper — vision-radius perception + letting actions target other agents (still open in NEXT-STEPS; conversation currently leans on co-located event perception).

## 2026-06-23
**Focus:** generated play-through Jupyter notebooks for every ported game.

**Done today:**
- Wrote `generated/_make_notebooks.py`: one notebook per game (load module → describe opening → play winning walkthrough → free-play `do(...)` helper).
- Built notebooks for the 9 Parsely ports plus Action Castle II–IV; verified each executes headless and hits its expected score (AC2 71/100, AC3/AC4 100/100).
- Repointed the generator after the `test_gen` → `generated` move; confirmed the hand-written AC1 notebook still runs; committed `1a754a7`.
- Researching how best to build the game (Godot or Parser)

**Blockers / questions:**
- N/A

**Next:**
- Push `feat/issue-29-pdf-generation` / open a PR when ready.

## 2026-06-22
**Focus:** tightened the slice-by-slice Parsely porting workflow after merging the conversion guide.

**Done today:**
- Decided ingest stays a random-access view, not a lazy stream — authoring slices are room-shaped, not page-shaped.
- Built `codegen.render_source` + CLI: renders a scoped slice (game / pages / room + one-hop exits) as compact markdown; 6 PDF-free tests.
- Pulled the shared `format_location` renderer into `pdf_structure.py`; documented in the guide §2; committed `8297fff`.

**Blockers / questions:**
- N/A

**Next:**
- Drive the next real port slice-by-slice with `render_source` to confirm room-plus-neighbours is the right chunk.
- `feat/issue-29-pdf-generation` is 3 commits ahead of origin and unpushed — push / open a PR when ready.

## 2026-06-19
**Focus:** chased a stream of user-reported AC2 gameplay bugs through the generated `.py` — endings, gating, and a wrong-answer death — and grew `verify_ac2.py` to 107 checks.

**Done today:**
- Propose now requires a ring and ends the game on success; Choose actions gated on dragon state, granting the sword directly.
- Split the one-choose-per-game lock into two flags + added a king yes/no champion/cobbler ending branch.
- Added `Answer_Wrong` catch-all so any non-riddle `answer` while the riddle is posed triggers the dragon's fire.

**Blockers / questions:**
- `ActionCastleII.is_won()` returns True on any `game_over`, so fatal endings count as wins — worth a follow-up.
- AC2 spec.json hasn't been resynced with today's `.py` edits; a fresh regen would lose all this.

**Next:**
- Decide whether to sync the AC2 spec back or accept the `.py`-first divergence and move on.
- Pick up #67 (epilogue sub-section detection in the structured PDF intermediate).

## 2026-06-18
**Focus:** finished the rebase, shipped the Tier-1 engine sweep, made the codegen retry iterative, then chased eight live Action Castle III interaction bugs back to their layers

**Done today:**
- Tier-1 sweep landed as built-ins (Wear/Take_Off, Use_On, Talk_To, Read, Open/Close, Score + multi-epilogue); 433 passing.
- Codegen retry is now iterative (`max_retries` loop, MODIFY-don't-regenerate); trimmed `SYSTEM_PROMPT` ~750→503 lines.
- Fixed all 8 live AC III bugs across parser (word-boundary directions), engine (location-scoped Examine), and spec.

**Blockers / questions:**
- Structured PDF intermediate is the right next investment to stop the LLM dropping rules; dataclasses + heuristics ready.
- `property_block` doesn't support `target: actor` — blocks the confirmation / party-required patterns.
- Two-step game-over confirmation in `Go.apply_effects` is the proper fix for AC III's "return home".

**Next:**
- Land the structured PDF intermediate (#60).
- Engine support for actor-property `property_block` and two-step game-over confirmation.
- Re-run the live extractor on AC III, diff against today's hand-fixed spec.

## 2026-06-17
**Focus:** surveying which Parsely-book mechanics the engine is missing — first scoped to Action Castle III, then expanded to all 12 games — and turning the findings into a Tier-1/Tier-2 engine roadmap

**Done today:**
- Walked AC III rule text page-by-page and surfaced 16 unsupported mechanics, bucketed Tier 1/2/3.
- Expanded the survey to all 12 games (21 mechanics); top finding: party/companion is broad (6/12), so it's Tier 2 not 3.
- Set the roadmap — Tier 1: wear, use-on, read, open, talk, score; Tier 2: companion + 7 more — and seeded party tasks #29–#33.

**Blockers / questions:**
- Party model paused: ship the Tier-1 PR first or proceed with the half-designed party model?
- Verification script's `SHOW`/`KNOCK` rows have narrator-prose false positives; tighten the regex if we publish the table.

**Next:**
- Decide Tier-1 PR vs party model and act.
- Re-run live LLM extraction on AC II / AC III after the engine sweep lands.

## 2026-06-16
**Focus:** issue #29 — fixing the Parsely ingest to preserve VERB↔response adjacency, then chasing a Flaming Goat regression where the LLM modeled the vending machine as inert flavor

**Done today:**
- Rewrote `_format_pages` to emit spans inline with `[FLAVOR]`/`[RULE]` tags, preserving the verb-to-response pairing.
- Rewrote `_underlined_words_for` to credit only words actually under an underline (x-range interpolation); 242 passing.
- Hand-patched Flaming Goat's vending machine into `transform_item` dispense actions; replay wins with the dispense step.

**Blockers / questions:**
- The walkthrough self-check validates win, not faithfulness — the LLM gamed it by skipping the machine; lean toward requiring every custom_action to appear in the walkthrough.
- Soda still shows in `describe_items` from the start (no `is_visible`); leaning toward a `spawn_item` template.

**Next:**
- Add the "walkthrough must exercise every custom_action" lint check + a `spawn_item` template.
- Re-run live extraction on Flaming Goat and confirm the LLM converges unaided.

## 2026-06-15
**Focus:** issue #29 — playing the live-extracted Action Castle, surfacing each gap, and tightening codegen + the engine + prompts at the point of error

**Done today:**
- Diagnosed and fixed five live bugs: phantom command hints, `go`-inside-`gold` substring match, royal-gating messages, NPC-only verbs leaking to the player, and the double `"I don't see it."` on `get`.
- Latched `game_over` to stop the triple win message; surfaced silent LLM-client errors (root cause: deprecated model → default `claude-sonnet-4-6`).
- Added the death-trigger location pattern to the prompt; regression test pins NPC-only verb hiding.

**Blockers / questions:**
- Latest module still walks through a locked door despite the `property_block` — suspect a duplicate-direction interaction with auto-reverse; trace it live next session.

**Next:**
- Diagnose the locked-door walk-through (dedupe block directions or emit one canonical direction).
- Re-run extraction with the strengthened prompts; try an unseen game (Spooky Manor / Z-Ward).

## 2026-06-12
**Focus:** worked on issue #29: strengthening the codegen extractor; merged #53

**Done today:**
- Merged #53 (feat/affordance tags) into `main`.
- Reviewed the live AC spec vs the gold and found flattened NPC behaviors, a collapsed win condition, drifted property names, and a fabricated `hit_guard`.
- Strengthened `prompts.py` (engine conventions, NPC-behavior + compositional-win guidance, validation checklist) and fixed `python_class_name` to sanitize spaced block names.

**Blockers / questions:**
- N/A

**Next:**
- Re-run extraction with the new prompts and diff against the gold; consider a second-pass critique call.
- Try an unseen game and convert `codegen_demo.py` into a `.ipynb`.

## 2026-06-11
**Focus:** issue #29 — Parsely PDF → playable game codegen pipeline

**Done today:**
- Shipped the codegen pipeline end-to-end: PyMuPDF ingest, LLM `GameSpec` extraction, template emit, validating CLI, `codegen_demo.py`.
- Added `Help`/`Break` built-ins; round-trip test plays the gold spec to `is_won()`, isolating emitter bugs from LLM hallucination.
- Docs in `codegen.md` + `codegen_gaps.md`; 219 tests passing on Python 3.9.6.

**Blockers / questions:**
- N/A

**Next:**
- Run live extraction on Spooky Manor / Z-Ward and populate `codegen_gaps.md`.
- Convert `codegen_demo.py` into a proper `.ipynb`.
- CI + manual live-extraction testing on an unseen game.

## 2026-06-10
**Focus:** focusing on implementing enums and structuring the data for the engine in issue #40

**Done today:**
- migrating the codebase to use tag-based affordances based on the LIGHT dataset, i.e., `edible` instead of `is_food`
- adding a `worn` dictionary and a `wield` dictionary, conforming to the standards of LIGHT by removing items in either to be removed from the inventory
- continued structuring the rest of the codebase using enums
- looked into `PyMuPDF` for #29 in order to both parse the text and keep the text color

**Blockers / questions:**
- N/A

**Next:**
- developing issue #29 further
## 2026-06-08
**Focus:** working on issue #23 and looking into logging for triggers

**Done today:**
- finished rebasing onto main and changed testing environment to match (`Python 3.9`)
- started issue #29
- auditing the codebase (i.e., checking logging behavior for triggers)

**Blockers / questions:**
- N/A

**Next:**
- working on issue #29

## 2026-06-05
**Focus:** working on issue #23 and looking into algebraic data types

**Done today:**
- researched implementation of the Goal class via a GoalType enum rather than just string matching to make the implementation less fragile
- finished #23 by integrating into `npc.py` (removing the original goals parameter, since that was now handled by character)
- changed tests to use GoalType rather than strings

**Blockers / questions:**
- N/A

**Next:**
- rebasing onto other PRs and focusing on less string-matching implementations

## 2026-06-04
**Focus:** researching and watching lectures on AI

**Done today:**
- watched lecture on CLIN
- read through Reflexion paper
- skimmed through text adventure papers

**Blockers / questions:**
- N/A

**Next:**
- reading more papers while working on issues

## 2026-06-03
**Focus:** rebasing issue #4 onto main and looking into implementation of #9

**Done today:**
- Finished rebase of issue #4, adding reflections to the ReAct loop implementation on top of the Agent framework
- Discussed possible implementation details of emergent behavior with Alistair

**Blockers / questions:**
- Uncertain of which repository I should use for studying smallville's websocket implementation (both the original [Generative Agents](https://github.com/joonspk-research/generative_agents) repo and a separate [smallville](https://github.com/nmatter1/smallville) repo didn't use websocket)

**Next:**
- Finish issue #9

## 2026-06-02
**Focus:** read the ReAct paper and work on PR #4

**Done today:**
- Implemented the Reflect step in `npc.py`: on a failed action, the agent now receives the parser's actual precondition-failure message instead of the generic "Choose a different action" placeholder, so it knows *why* the action was blocked
- Added `Parser.last_fail_message` (and wired `WebParser.fail()` to set it too) so the reflect loop can read the failure reason without side-effects
- Capped retries at 2 (1 initial attempt + up to 2 reflect iterations)
- Added 3 tests in `tests/test_agent_layer.py` covering: failure reason surfaced in retry prompt, retry cap enforced, and reflect path through the hybrid behavior

**Blockers / questions:**
- N/A

**Next:**
- Open PR for #4, get review
- Look at hooking the agent loop into the live game (currently `npc.py` is not wired into `action_castle.py`)

## 2026-06-01
**Focus:** figuring out the interface between Python and Godot

**Done today:**
- Wrote a simple Python script to connect to Godot via UDP
	- ![[Screen Recording 2026-06-02 at 12.19.14 1.gif|240]]
- Finished lectures for "Search in AI" and "Classical Planning"

**Blockers / questions:**
- N/A

**Next:**
- Working on PR #4
