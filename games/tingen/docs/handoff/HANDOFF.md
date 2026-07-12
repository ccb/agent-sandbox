# HANDOFF — Fable → Opus 4.8 (2026-07-03)

The Fable session that built the combat arc, the city fill, the interiors, and the item-backed
ammo system is ending (credit limit). This directory is the complete state transfer. **Read this
file first, then the doc that matches your task.**

## The one-paragraph state

Tingen is a Godot 4.6 **occult-noir action-RPG roguelite** (RPG + open-world + roguelite — see
`tingen_game_direction_v2.md`; the detective/investigation framing was DROPPED 2026-07-03) where
19 LLM-driven NPCs live double lives on real schedules; a cult runs a summoning plot toward a
doomsday climax; the player hunts the monsters hiding among the people, grows their Beyonder
pathway, and can fight. The **combat system is COMPLETE and live-verified** (two-layer LLM-intent /
deterministic-execution stack, 11/11 live acceptance with real Sonnet — see RUNLOG.md). The
**city map is built** but ~half the density-fill sprites are mispositioned or sliced (user-flagged,
diagnosis done, apply-loop is YOUR job — `DESIGN_fill_rework.md`). The **7 interior scenes are
DONE and wired** (two-way portals, city doors, `f0ae6ac`). **Ammo is item-backed** through the
new weapon/tool system (commit `cc4e2e2`). Everything is local-committed on `main` and **NOT
pushed** (44 commits ahead of `origin/main`). ⚠️ **The remote
`github.com/MaEnqiMark/Tingen-Game` is PUBLIC** (audit finding 2.7; earlier docs wrongly said
"no remote") and has **no LICENSE**. Keys are safe (`.env` gitignored + untracked, verified).
**Do not push without the user's explicit say-so** — pushing publishes tonight's combat work and
any secrets-in-data to a public repo. Tingen also syncs into `ccb/agent-sandbox` `game/tingen`
via git subtree (see `reference_tingen_integration`). See `PRODUCTION_GAPS.md` §2.7 for the
license/visibility decision the user must make.

## Docs in this handoff

| file | what it is |
|---|---|
| `HANDOFF.md` | this index + state + protocols |
| `DESIGN_fill_rework.md` | the city-fill fix: diagnosis results, tooling semantics, exact resume steps |
| `DESIGN_interiors_wiring.md` | interior scenes: what landed, what remains, conventions |
| `DESIGN_ammo_items_followups.md` | the weapon/tool system as built + its designed-but-unbuilt extensions |
| `PRODUCTION_GAPS.md` | the evidence-cited audit: 13 blockers, design gaps, loopholes (Tingen + Yumina) + raw per-auditor appendix |
| `PRODUCTION_ROADMAP.md` | the complete-a-polished-game plan: audio, VFX/animation/cinematics, content/adversaries/storyline, UI/UX/meta, feel/perf/ship (tracks A–F) |
| `TESTING_WORKFLOW.md` | the full verification pyramid incl. live-LLM gates and the computer-use playtest protocol |
| `WORKFLOWS.md` | the reusable multi-agent orchestration patterns (with copy-paste script templates) |
| `TODO_NEXT_AGENTS.md` | prioritized, self-contained work queue |

Also read `/CLAUDE.md` at repo root (conventions + commands — written for you) and `RUNLOG.md`
(the chronological engineering journal; every decision tonight has an entry).

## Commit timeline of the final session (all local, `main`)

- `ccb2bf3` combat M6+M9 (Kell slice + Yumina back-port spec & 95 vectors)
- `05a61d8` final combat arc review SHIP-WITH-FIXES: all 9 findings + scenario.json refactor + fill first placement
- `c599011` live LLM acceptance of the §0 Butcher script — 11/11 PASSED (`tests/live_butcher.gd`)
- `5db0647` ability display names (HUD telegraph polish)
- `cc4e2e2` ammo → item-backed weapon/tool system (user directive; TDD + adversarial review, verdict SHIP)
- `f0ae6ac` interiors wiring: 7 rooms, two-way portals, city doors, suite 1895/0/0

## Invariants you must not break (user- and design-binding)

1. **Facts, not commands**: the engine publishes perception facts; the LLM chooses. No engine
   code may branch on a specific NPC identity (roster/spots live in `data/*.json`).
2. **Secrets never ride /decide**: `secrets`, `combat_form`, `combat_intent` are stripped from
   every LLM-bound payload (`Perception.decide_request`, `HttpSidecar._launch_refresh`).
   Peers' hp is BANDED, never exact.
3. **Transformation is an ability** (`assume_form`), cast by an NPC's own layers or a GM
   corruption directive — NEVER an automatic engine reveal, NEVER a tactical-layer pick.
4. **No locational damage** — binary hit/miss ("graze" is a rejected idea; don't reintroduce).
5. **Combat perception is vision-gated** like every stimulus; the world never pauses; downed
   bodies are never deleted; no RNG in combat resolution.
6. **The LLM is never on the frame path** (reflex ≤300ms / tactical 8Hz / intent ~15s beats).
7. **TDD + review-re-edit are mandatory** for every milestone (see TESTING_WORKFLOW.md §6).
8. **Key safety**: Anthropic key in `agent-sidecar/.env`, OpenAI key in
   `/Users/markma/Desktop/Yumina Master/yumina/.env`. Pass via `--env-file`; NEVER print/echo/cat
   values (presence/length only). Subagents get the same instruction verbatim.
9. **Do not push. Local commits only.** Confirm with the user before creating shared-state
   artifacts (GitHub issues/PRs) — standing user preference.

## Budget ledger (image generation, user-authorized $100)

≈ $40 spent at handoff: buildings ≈$24 + interiors $1.75 + fill $7 + combat asset strips ≈$5 +
live-LLM test runs ≈$4 (Anthropic side, separate). Ledger entries live in RUNLOG.md. Remaining
image budget is available for the fill regenerations (`DESIGN_fill_rework.md`).

## In-flight at handoff (check before starting anything)

1. **Fill diagnosis verdicts: IN-REPO** — `docs/handoff/fill_diagnosis_verdicts.json`
   (14 blocks + 6 whole-map critic findings); summary table + judge cautions in
   `DESIGN_fill_rework.md` §3. The apply-loop (§4 there) is the next session's first job (P0.1).
2. **Interiors wiring: LANDED** — commit `f0ae6ac`, suite 1895/0/0 (see
   `DESIGN_interiors_wiring.md` for the room table + load-bearing judgment calls, incl.
   RaphaelCemetery deliberately absent until the fill rework re-places it).
3. **Suite baseline: 1895 passed / 0 failed** at `f0ae6ac`. combat_sim 33/0.
   run_combat_vectors 95/0. Python: 75/26/13/8.

## The sidecar (needed for anything live-LLM)

```
cd agent-sidecar && python3 sidecar.py --env-file .env --port 8777
# health check: curl -s http://127.0.0.1:8777/health   -> {"ok": true, "have_key": true, ...}
# game/harness attach: TINGEN_SIDECAR_URL=http://127.0.0.1:8777
# decision traces (sidecar stderr): TINGEN_DECIDE_LOG=1 on the SIDECAR process (never prints prompts;
# prompts ride the `_prompt` field of /decide responses)
```
A sidecar process holds its Python in memory — **restart it after editing brain.py** (a stale
sidecar burned an hour tonight; see RUNLOG "stale sidecar").
