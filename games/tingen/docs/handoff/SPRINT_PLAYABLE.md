# SPRINT — First Playable (2026-07-03, autonomous)

Goal: **a playable vertical slice of the v2 game** — boot → the first-ten-minutes opening →
fight (visible, audible-later) → the four meters create tension → advance your Sequence once →
reach Ritual Night → win/lose → restart. Driven autonomously via a milestone pipeline; every
milestone is TDD + adversarial review + a gameplay/verify pass, committed on green.

Authoritative design: `tingen_game_direction_v2.md` (v2.3, forks locked in §13). Build discipline:
`TESTING_WORKFLOW.md`. Constraints: engine-neutral, no RNG in combat, transformation only via the
Seq-4 `assume_form`/GM directive, local commits only (repo is PUBLIC — never push), never print keys.

## Definition of "playable" (the acceptance bar for this sprint)

A person can launch the game and, with no external help:
1. Land in a title → new run → the opening lodging (not the dev City scene).
2. Get the first lead in-fiction, walk to it, and fight the butcher — **and see the hits/telegraphs**.
3. Talk to an NPC **without the window freezing**.
4. See the four meters (Doom/Madness/Notice/Heat) and feel them move.
5. Harvest a Characteristic and advance their Sequence once (Hunter kit grows).
6. Reach Ritual Night (by Doom filling or early assault), fight the climax spine, and **get a
   win or lose screen** — no softlock.
7. Die / lose control (60s rampage) and **restart into a fresh run** with meta intact.

## Milestone pipeline (each: build → review → fix → verify → commit)

Ordered so the tree stays coherent (shared-file milestones are sequential; net-new files reduce
contention). Playability blockers first (they turn the built butcher demo into a playable loop),
then the v2 systems, then the climax, then integration + polish.

- **M1 — Combat VFX wiring** (C1). Make combat visible: CombatProjectile/CombatZone scenes get
  sprites/particles from the orphaned `assets/fx/*`; hit-spark on `agent_attacked`, ichor on
  damage, dash afterimage, transform burst on `transformed`; an `fx`/`vfxId` field on abilities.
  *Isolated, highest visible ROI, validates the agent pipeline.*
- **M2 — Boot flow + run shell** (C6 + D5). project.godot boots to `Main.tscn` → title → new run →
  lodging → City; a `RunManager` autoload (7 in-game days, 3 phases/day, nightly checkpoint,
  death/rampage → meta → restart). Fix the boots-into-dev-scene + restart-leak (GAP-2.9).
- **M3 — Dialogue de-freeze** (GAP-2.3). Move `converse` onto a worker thread like `GMPanel`'s
  narrate; DialoguePanel gets a "thinking…" state. Kills the 20s main-thread hang.
- **M4 — Meters + Madness + HUD** (D2/D3). WorldState rework → Doom/Madness/Notice/Heat; Madness
  as a drain/refill cycle with the threshold ladder + the 60s rampage at 100; HUD shows the meters
  (progressive disclosure). Wire the meter drivers (power use → Notice/Heat/Madness; cult → Doom).
- **M5 — Sequence progression** (D1). `Progression` autoload: harvest Characteristic → digest
  (acting deed, DeedRunner) → advance Seq 9→7, Hunter kit grows; the 2 new ability rows
  `mark_prey` + `incendiary_round`.
- **M6 — Rumors → Leads** (D4). Lead system: NPCs surface perishable leads (converse + ambient);
  the board becomes the Leads board; GM slots leads per run; a cold lead bumps Doom + respawns.
- **M7 — Ritual Night + endings** (D7/§9 build map). The scoped spine (two-door entry → interrupt
  interactable/kill celebrant → avatar boss if slow → backlash wave → win/lose screen) + early
  assault w/ one relocation. Fix the no-ending softlock (GAP-2.11).
- **M8 — First-ten-minutes GM script** (§3). Guarantee the opening: butcher lead hot+close via
  constable_brom, the harvest fork, meter reveals, the two follow-up leads.
- **M9 — Gameplay-test pass**. Headless full-run sim harness (`tests/live_run.gd`-style) + a live
  LLM run + an adversarial whole-slice review + fix criticals. Prove the loop closes end-to-end.
- **M10 — Polish** (E2/E3/E4). Title/pause/save-load UX; the audit's remaining player-seat gaps.

Deferred (post-slice, tracked in the roadmap): audio (needs the sourcing decision — BLOCKED on
user), cross-run NPC memory, the 4-option interrupt menu, more adversaries, Yumina port.

## Running QUESTIONS for the user (answer anytime; none block the sprint)

*(The sprint proceeds with the sensible default noted; flag if you disagree.)*
- **Audio sourcing** (blocks all of Track B). Default: proceed with NO audio this sprint; audio is
  a post-sprint pass once you pick a source (CC0 packs vs commissioned).
- **Repo visibility + LICENSE** (it's PUBLIC now). Default: keep building locally, do NOT push.
- **Sprint budget/credit**: if agents start failing on credit, the sprint pauses here and I
  report where it stopped. Confirm the budget you want to allow.
- **The `mark_prey` / `incendiary_round` ability numbers** (Hunter kit): I'll author sensible
  values and note them; tune later in playtest.
- Any tone/aesthetic guardrails for the generated VFX/UI art beyond "Victorian occult-noir"?

## Progress log — SPRINT COMPLETE (tag `playable-slice-v1`)

All 10 milestones landed green, each build → adversarial review → fix, committed on green.
Suite climbed **1890 → 2066** passing, combat determinism (combat_sim 33/0, vectors 95/0) held at
every milestone. The 7-point "playable" bar is met; a whole-slice reviewer drove the live player
through a full run + restart and the fixer closed the 4 integration gaps it found.

| M | milestone | commit | verdict | suite |
|---|---|---|---|---|
| M1 | combat VFX (visible) | 9cccf3b | SHIP | 1907 |
| M2 | boot flow + run shell | c177bfd | SHIP-w-fixes (5 leaks caught) | 1920 |
| M3 | dialogue de-freeze | a3a9783 | SHIP-w-fixes | 1943 |
| M4 | 4 meters + Madness + rampage + HUD | 9197c4a | SHIP-w-fixes | 1955 |
| M5 | Sequence progression | 4812395 | SHIP | 1973 |
| M6 | rumors → leads | 4186b1a | SHIP | 1995 |
| M7 | Ritual Night + endings (softlock closed) | 3d918dc | SHIP | 2007 |
| M8 | first-ten-minutes opening | 42093b7 | SHIP | 2018 |
| M9 | full-run integration + whole-slice review | 3e60e40 | PLAYABLE (4 gaps fixed) | 2018/full_run 82 |
| M10 | pause/settings/HUD legend/VFX polish | 951a0db | SHIP | 2066 |

**Playable now:** title → new run → lodging → city; Brom's butcher lead → the two-phase butcher
fight (visible FX, mask-drop) → talk (no freeze) → four meters move → harvest → advance Hunter
Seq 9→8 (kit grows) → Ritual Night (Doom fills OR storm the crypt) → interrupt-win / fuse-lose /
avatar-boss / backlash → win/lose screen → die/rampage costs a day (nightly checkpoint) → restart,
meta persists. Pause menu + real accessibility settings.

**Stubbed / deferred (hooks in place, tracked):** Notice/Heat **hunter spawns** (meters signal but
no hunters spawn yet — the biggest "meters get teeth" follow-up), **Doom time-fill** (Doom rises on
rite-steps/leads but not passively with time), per-pathway Seq-4 rampage form (bieber placeholder),
the 4-option interrupt menu + stealth entry (post-slice), **audio** (blocked on the sourcing
decision), cross-run NPC memory (post-slice, your flagged signature feature).

## Post-slice questions for the user (answer anytime)
- **Audio source** (unblocks Track B): CC0 packs vs commissioned? (default: stay silent.)
- **Repo visibility + LICENSE** (PUBLIC now, unpushed): keep public + add a license, or make private?
- **Continue-the-sprint budget**: I'm proceeding into the next tier (hunter spawns → Doom
  time-fill → a 2nd adversary) per "keep going until done." Say stop anytime.
- Cross-run NPC memory: prototype now or hold? (Recommended: hold until the slice is play-tested.)
