# Alistair's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md). [Reading List](#reading-list)

<!-- Copy the template from README.md to the top each working day. -->

## 2026-06-25

**Focus:** push the UPenn campus replay to a watchable state (camera, terrain, Williams Hall interior); land the prompt-management + visualizer stack; plan the backend unification

**Done today:**
- **PR #166** (UPenn campus agent world) — a full day of Godot rendering polish on `feat/campus-kenney-tiles`:
  - **Camera:** borderless-fullscreen launch that scales the 1920×1080 frame to the screen; **pan + zoom controls** with the default view unchanged; capped zoom-out at the default view, locked the map at the default view (pan only when zoomed in), and kept the camera inside the map so there's never a grey margin top/bottom.
  - **Terrain / tiles:** cropped the core map to the block bounded by its four streets; used each terrain block's **centre tile** so cells stop showing corner specks; switched trees to **rounded standalone sprites** so canopies aren't cut off and stood them on the ground (not a grey box), with discrete green + autumn trees; added a thin concrete **kerb** around the lawns (a thin stroke, not a full concrete cell) and outlined the stone slabs' bare top/right edges.
  - **Williams Hall interior** (`0972a18`): new `tools/geo/furnish_building.py` opens a sector's roof (roof = sector ∩ collision) and appends two interior tilesets (Franuka pack, committed) + `williams_floor` / `williams_furniture` layers to `upenn_core_urban.tmj` as a **top-down cutaway** — idempotent, reusable via `--sector`, visual-only (a navigable interior is the follow-up); no renderer change. Black-formatted `furnish_building.py`.
  - Fixed `generate_penn_replay` to pass `world_map` through its `build_world_fn`.
- **PR #150** (prompt management + visualizer): templatized the **gen-agents dialogue, reflection-synthesis, and daily-plan** prompts, and added a **per-node templates override** plus the rewritten **Smallville live-LLM cognition chain** to `promptviz` — incorporating Frankie's just-merged #168 / #169 / #170. Rebased onto post-#168 `main`, CI green. With the gen-agents half folded in (#161, see 6/23), **#150 now covers all of #145**.
- Opened **issue #179**: unify the backend — one canonical package + one HTTP API behind every frontend (the Flask webapp, the Smallville replay, and the Godot port each reach the engine differently today). Folded **PR #100** (`SimulationConfig`) into the extraction plan on tracking **PR #167** rather than landing it standalone.

**Phase C/D/E closed for me by teammate merges:**
- **PR #106** (my vision-perception branch) merged → closes **#80** (vision-radius perception) and **#82** (Smallville proximity mapping).
- Frankie's **#168 / #169 / #170** merged → close **#83** (daily planning), **#84** (periodic reflection), **#86** (dialogue seam); **#78** (real LLM brain) also landed.
- **PR #180** (#87 surface chat) and **PR #175** (#90 world-state export API) merged → both GA issues closed. MaEnqi also shipped **#177** (headless HTTP server) — the backbone for #179.

**Blockers / questions:**
- none

**Next:**
- Land **#166** (campus replay) and **#150** (prompts + visualizer); then run the **#167 / #179** backend extraction + unification now that the HTTP server (#177) and export API (#90) are in.
- Navigable Williams Hall interior; world-authoring research (**#147**); **#85** (time mapping) is the last open Phase D item.

## 2026-06-24

**Focus:** render the real UPenn campus in Godot from OSM map data; wire it to a parameterized replay backend

**Done today:**
- Opened + merged **PR #165** (`geo/osm-to-tiled-poc`): an **OSM → Tiled converter** plus a Penn campus tilemap — a POC for new **issue #164** (import real-world GeoJSON/OSM map data into Godot tiles). Added a **`core` area preset** (34th–38th × Spruce–Walnut) for prototyping.
- Merged **PR #162** (godot-generative-agents) and combined it with the OSM work into **PR #166** (`feat/campus-kenney-tiles`): the **UPenn campus agent world** — real OSM map → matrix (the_ville format) + a parameterized backend + a **Godot replay** where agents walk the real campus over the OSM-derived tilemap. Overlaid the campus first with **Cute Fantasy** tiles, then with real **Kenney CC0 urban** tiles; added a `run_replay.sh` launcher.
- Visual-variety pass on the urban campus: varied roofs, marked roads, added a tree layer, then **real multi-tile trees** and **composed tree stands**; iterated the core resolution down to **1 m/tile**, limited the core to **34th–36th St (Spruce–Walnut)** recentred, shrank replay sprites so people read smaller than buildings, and tuned the camera (portrait → 1920×1080 cover-fit → full-campus overview).
- Opened tracking **PR #167**: extract the gen-agents backend into its own package and fold in **`SimulationConfig`** (#100), sequenced **after #166** (added the tracking/blocked note).
- Opened **issue #163**: keep the memory / retrieval / reasoning + persona inspector (the web companion) when the visuals move to Godot.

**Blockers / questions:**
- none

**Next:**
- Polish the campus replay (camera, interiors); land **#166**, then do the **#167** backend extraction.

## 2026-06-23

**Focus:** start the Godot replay frontend; ship a prompt-chain visualizer; extend prompt management to the generative-agents prompts

**Done today:**
- **PR #109** (5-agent replay UI) and **PR #144** (Claude Code plugins) both merged.
- Opened **PR #162** (`feat/godot-generative-agents`): first cut of a **Godot** frontend for the agent sim — imports Cute Fantasy sprites that auto-wander, over a tiled ground (grass, paths, pond) with trees rendered using **y-sort**. The start of the Godot renderer the #146 guidance laid out; retargeted the port-proposal docs off the closed **#146** onto this PR and tied them to the mock world.
- Opened **PR #161** (`feat/ga-prompt-management`): port the **generative-agents** LLM prompts onto in-repo **`.prompty`** templates — the Smallville half of **#145** (the library half is PR #150). Later **folded into #150** and closed #161, so one PR now carries all of #145.
- Added the **`promptviz`** tool (`e066c21`): an **offline web DAG of LLM call sites** (Flask + Cytoscape/dagre, no model call) to see the prompt chain across the engine + sim; made it always load the bundled chains so a `--spec` shows alongside them. Lives on PR #150.
- **#106** follow-up: a `perceivable_locations` perf note + a replay-only embedding-determinism check.

**Blockers / questions:**
- none

**Next:**
- Build out the Godot replay with the real campus map (OSM); keep **#150** moving.

## 2026-06-22

**Focus:** finish the replay-UI polish; team tooling; propose *and* start a prompt-management system; forward-looking Godot / world-authoring research

**Done today:**
- Continued **PR #109** (replay UI): turned the **State Details** page into an in-place **popup** (now spans most of the screen, densified card), wired it to show **real memory** sliced to the current replay step and **live-sync** with the replay, added a **flash** when a new memory arrives (with a reduced-motion fallback and row padding so it isn't clipped at the edge), and **grouped same-timestamp memories** under one time header. Still all under `generative-agents/`; engine untouched.
- Opened **PR #144** (`chore/claude-code-plugins`): enable two recommended **Claude Code plugins** for the team via `.claude/settings.json` — **`pyright-lsp`** (live type diagnostics on this pure-Python repo) and **`github`** (MCP for our `gh pr` / `gh issue` workflow). Both come from the auto-registered `claude-plugins-official` marketplace; documented in `ONBOARDING.md` §3.
- Opened **issue #145**: proposal to adopt a **prompt management system** (in-repo **Jinja + Prompty**). A quick survey found ~15 inline f-string prompt sites (e.g. `npc.py`'s ReAct decision instruction) with no central registry — they're getting hard to find, edit, version, and test as the port grows.
- Opened **PR #150** (`feat/prompt-management`): a first implementation of **#145**, scoped to the **`text_adventure_games`** library. Moved the engine's LLM prompts out of inline f-strings into **eight versioned `.prompty` templates** (YAML frontmatter + Jinja2 body) under a new `prompt_templates/` package, rendered in-process via the **prompty** library — no external prompt service, so a prompt change stays a normal code change. Covers `npc.py`'s ReAct `npc_decision` plus the seven `llm_parser.py` narration / intent / entity-matching instructions; output is **byte-identical** (full suite **628 passed, 1 skipped**, new `tests/test_prompt_templates.py` pins each template's exact text), with a `prompt_templates/README.md` usage map and a CLAUDE.md keep-in-sync note. Named `prompt_templates/` to avoid colliding with the in-game `prompts.py` (the Prompt choice mechanism, #110). Does **not** close **#145** — the generative-agents / Smallville prompts are a follow-up.
- Opened **PR #146** (`docs/godot-frontend-port-guidance`): two forward-looking research docs, guidance only (no engine/sim code). (1) A "porting the replay frontend to **Godot**" section appended to `generative-agents/NEXT-STEPS.md` — the dependency-ordered prerequisites for swapping the Django/Phaser web replay for a Godot 4 renderer (freeze the JSON export as the renderer-agnostic contract, confirm replay needs no server, reuse the Tiled map + sprite assets, rebuild the view + tile-motion layer in Godot, a live-mode-only Godot↔Python transport, carry chat through once it lands; cross-links ROADMAP Phase 3, the `JSONRenderer`/Stage 10 work, the playground survey, #9/#10). (2) `docs/design/custom-world-authoring.md` — research notes on authoring **our own world + sprites** instead of reusing the upstream `the_ville` assets (asset provenance, the data contract that defines a world, what the 2025 Godot project did + its asset-licensing caveats, three authoring options, open questions); backs new **issue #147** ([GA] Research: author our own world + sprites).

**Blockers / questions:**
- none

**Next:**
- Get **PR #109**, **#144**, **#146**, and **#150** reviewed/merged; land **#106** (perception) and **#100** (`SimulationConfig`).
- Port the remaining **generative-agents / Smallville** prompts onto `.prompty` to fully close **#145**; pick up the world-authoring research (**#147**). **#61** / **#62** still awaiting review.
- Phase D next: daily planning (#83), periodic reflection (#84), time mapping (#85).

## 2026-06-21

**Focus:** make the Smallville replay watchable — a 5-agent run with on-screen cognition

**Done today:**
- Opened **PR #109** (`ga-5-agents-memory-reasoning-ui`): run **5 active agents** (the other 20 are kept, not deleted) and surface **memory + reasoning on each agent card**, then added **daily schedules**, a **speed slider**, and richer memory cards so the morning actually evolves and is easy to follow. The UI is a *replay of exported JSON frames*, so memory/reasoning are captured during the sim and baked into each movement frame before render.

**Blockers / questions:**
- none

**Next:**
- Polish the State Details view; open the plugins chore.

## 2026-06-20

**Focus:** finish Phase B integration in the sim; start Phase C perception

**Done today:**
- Merged **PR #98** (closes **#79**): the 25 residents now start the day with social structure + a partial world model instead of as blank slates.
- Landed **embeddings in the Smallville sim** (issue **#102**, commit `e0787be`, via PR #104): the sim now does semantic memory retrieval through the #76 `EmbeddingClient`. (#104 shows CLOSED on GitHub — it was a worktree branch — but the work is on `main`; **#102** closed.)
- Opened **PR #106** (`feat/vision-perception`): Phase C perception end to end — **#80** vision-radius perception (engine) + **#82** Smallville tile-proximity mapping. New `Game.perceivable_locations()` visibility seam (BFS over `connections` to `vision_r` hops) and one `AgentMemory.perceive()` entry point, unifying perception across the sequential/simultaneous/Smallville call sites that had diverged. Superseded an earlier cut (**#105**, closed).

**Blockers / questions:**
- none

**Next:**
- Get **#106** reviewed; build the watchable replay UI.

## 2026-06-19

**Focus:** land the Generative Agents port and the whole Phase A + B foundation

**Done today:** (big merge day)
- Merged **PR #72**: the **Generative Agents (Smallville) port** — mock-LLM backend pre-generates a ~1-hour, **25-resident** morning replay through the real `Agent.decide` seam; everything under `generative-agents/`, **no engine code changed**.
- Merged **PR #59** (issue **#47**): the temp multi-step **planning-benchmark plan**; moved it from in-flight to Shipped in `PROGRESS.md`.
- **Phase A landed:**
  - **PR #91** (closes **#73**): **LLM cost & token observability** — `chat()` / `call_tool()` now capture the response `usage` block (previously discarded), plus a per-agent cost report and run artifacts. Prompt caching and record/replay scoped out as separate follow-ups.
  - **PR #95**: unified **`GameConfig`** (`AgentConfig` / `EngineConfig` / `ClockConfig` / `RenderConfig` + existing `LlmConfig`) — gathers scattered module constants and inline literals into one object a game author builds once (Python or YAML/JSON). Every field defaults to today's behavior.
- **Phase B landed:**
  - **PR #94** (closes **#75**): append-only **agent memory stream** — every `Agent` gets a private, timestamped, importance-scored memory (`memory.py`, mirrors `knowledge.py`), and the Smallville residents perceive / remember / retrieve through that same `Agent.memory` seam.
  - **PR #99** (issue **#76**, squash `beb062e`): pluggable **`EmbeddingClient`** for memory-retrieval relevance — 4 backends (mock, `model2vec` default, sentence-transformers, openai), pure-Python cosine, opt-in (keyword default). GitHub marks #99 CLOSED (stacked on #94's branch) but the work is on `main`. Opened follow-up **#102** (use embeddings in the sim); also opened+closed a redundant re-PR **#103** by mistake.
  - Opened **PR #98** (closes **#79**, stacked on #94): seed the 25 residents at t=0 — relationships → turn-0 memories (importance 3.0), known places → `Knowledge` beliefs, from the upstream `the_ville_n25` bootstrap data; port-only.
- **Phase C started:** merged **PR #96** (closes **#81**): generalize action target resolution so any co-located agent can be targeted, and an unnamed non-player target fails cleanly instead of silently misfiring at the player.
- Merged **PR #101** (refs **#97**): survey doc for a 2025 Godot multi-agent playground (project + assets).
- Opened **PR #100**: real **`SimulationConfig`** for the generative-agents sim — composes `GameConfig`, adds sim knobs (start / steps / sec-per-step, retrieval, …); every field defaults to current behavior.
- Tooling: added a manual **`/update-progress`** slash command and made `PROGRESS.md` sync **manual-only** (not a `PostToolUse` hook); ignored Claude Code local worktrees in `.gitignore`.

**Blockers / questions:**
- none

**Next:**
- Merge **#98** (seed personas) and the embeddings-in-sim work (#102); review **#100**.
- **#61** / **#62** still awaiting review.

## 2026-06-18

**Focus:** turn the Generative Agents port into a sequenced production roadmap; open the first implementation PRs

**Done today:**
- Broke the Generative Agents work into a full **Phase A–F roadmap** — opened issues **#73–#90**:
  - **Phase A (foundations):** #73 LLM cost & token observability, #74 sim params via CLI flags, #78 swap the Smallville mock for a real LLM client.
  - **Phase B (memory):** #75 append-only memory stream on `Agent`, #76 retrieval scoring (recency × relevance × importance), #77 inject retrieved memories into the observation, #79 seed personas at t=0.
  - **Phase C (perception / targeting):** #80 vision-radius perception, #81 let actions target other agents, #82 map Smallville proximity onto perception.
  - **Phase D (planning / reflection / time):** #83 daily planning (day → hourly → minute), #84 periodic reflection (memory synthesis), #85 continuous Smallville time ↔ engine turns.
  - **Phase E (dialogue):** #86 agent-to-agent dialogue seam, #87 surface chat end to end.
  - **Phase F:** #88 live (non-replay) step-by-step serving.
  - **[GA] cross-cutting:** #89 grow the offline test suite, #90 structured observations + world-state export API.
- **#63 closed:** Chris approved prioritizing the agent-memory layer alongside the planning benchmark — Phase B is greenlit.
- Opened the first implementation PRs: **#91** (Phase A cost observability, closes #73), **#94** (Phase B append-only memory stream, #75), **#95** (unified `GameConfig`). Closed **#74** (superseded by the `GameConfig` / `SimulationConfig` config approach) and **#77** (duplicate of #76's inject step).
- Docs hygiene on `main`: filed the implemented design docs under `docs/design/implemented/` and pointed lingering `simultaneous-actions.md` references at the new path; tidied `PROGRESS.md`.

**Blockers / questions:**
- none

**Next:**
- Land the Phase A/B PRs (#91, #94, #95); finally merge **#72** (the port) and **#59** (planning-benchmark plan).

## 2026-06-17

**Focus:** land the repo-hygiene queue (#64–#65, #68–#69); open the Generative Agents port for review (#72)

**Done today:**
- Merged **PR #64**: adopt **uv** as the default project workflow — committed `uv.lock`, `.python-version`, and README/CLAUDE.md updates; plain `venv`/conda paths stay documented as fallbacks.
- Merged **PR #65**: **`PROGRESS.md`** — single at-a-glance status board for shipped features, open PRs, and design docs (replaces the scattered issues/PRs/`docs/design/` view).
- Merged **PR #68**: resync the local-only **MkDocs API reference** to the engine — new `api/knowledge.md` (#45), `turns.phase_rank` (#42), and string-literal `__all__` fixes so `mkdocs build --strict` passes.
- Merged **PR #69**: reorganize **`notebooks/`** into a numbered feature walkthrough (`01_engine_tutorial` … `08_world_mechanics`) with offline mock-LLM demos for output/traces (#31), persuasion (#46), containers/durations (#43/#24), plus a coverage matrix in `notebooks/README.md`.
- Opened **PR #72** (`feat/generative-agents-port`): port Stanford's **Generative Agents (Smallville)** onto the engine — mock-LLM backend pre-generates movement files, upstream Phaser/Django frontend replays them; full **25-resident** town, camera zoom/pan, split map/agent-panel UI, synthetic-maze offline tests + CI step. Supersedes **#71** (base branch deleted when #64 merged). Everything under `generative-agents/`; **no engine code changed.**

**Blockers / questions:**
- none

**Next:**
- Get **PR #72** reviewed/merged.
- Get **#59**, **#61**, and **#62** reviewed.

## 2026-06-16

**Focus:** start the Generative Agents (Smallville) port; docs-site polish

**Done today:**
- **Late 6/15** (after the journal entry): merged **PR #54** (issue #45, per-character **knowledge / belief layer**) and **PR #67** (#66, disambiguate `MockReActClient` decisions from `tool_calls`).
- Opened **PR #70** (`external-generative-agents`): survey doc cataloging Smallville's world hierarchy (19 sectors, ~62 arenas), the 25 personas, memory/cognition structure, and porting correspondences to our `Location`/`Character` model — plus `.gitignore` for `/external/` where the upstream repo is cloned locally. Closed when folded into the implementation PR.
- Opened **PR #71** (`feat/generative-agents-port`): first cut of the port — engine-backed backend pre-generates the frontend's movement JSON, mock LLM drives three agents (Isabella, Maria, Klaus) through the real `Agent.decide` seam, vendored pathfinder + `setup.sh` copies upstream assets into a git-ignored `frontend/`. Closed when GitHub auto-closed it after the `chore/uv-project-workflow` base branch merged via #64 (can't reopen once the base is gone).
- Pushed docs hygiene to `main`: MkDocs serve/build instructions in **README**, theme switch **Material → Read the Docs**, and `/external/` in **`.gitignore`**.

**Blockers / questions:**
- none

**Next:**
- Land **#64** / **#65**, then rebase the Generative Agents branch onto `main` and reopen as a fresh PR.
- Expand the port from 3 agents to the full 25-resident cast.

## 2026-06-15

**Focus:** land contested-resource resolution in simultaneous mode (#42); repo hygiene (progress tracker, uv, ScienceWorld clones)

**Done today:**
- Merged **PR #49** (issue #42): **contested resources + retry policy** in simultaneous turn mode — stages 1–4 of `docs/design/implemented/simultaneous-actions.md` (#35). The resolve step now runs **claim → arbitrate → recover**: `Intent` carries ranked `fallbacks`, `resolve_order()` sorts by `(phase, -initiative, gather_index)` with an optional `Game` override, opt-in `Game.phases` buckets actions (`communicate < move < manipulate < fight`), and losers get a specific contention failure fed into the capped reflect-retry instead of a generic `"I don't see it."`
- Pushed `chore: ignore local benchmarks/ clones (e.g. ScienceWorld)` to `main` — keeps upstream benchmark repos (and their bundled JARs) out of our tree when cloned under `benchmarks/`.
- Opened **PR #64** (`chore/uv-project-workflow`): adopt **uv** as the default project workflow with a committed lockfile, while keeping plain `venv`/conda paths documented as fallbacks.
- Opened **PR #65** (`docs/progress-tracker`): **`PROGRESS.md`** — a single at-a-glance status board for shipped features, open PRs, and design docs (was scattered across issues/PRs/`docs/design/`).
- Teammate PRs also landed on `main` today: **#32** (issue #24, per-turn NPC time budget), **#52** (#43, container/capacity inventory), **#57** (#44, structured tool/function-calling on LLM clients), **#58** (#46, goal-influencing dialogue), **#48** (engine-wide enums), **#53** (affordance tags).

**Blockers / questions:**
- none

**Next:**
- Get **PR #54** (knowledge/belief layer, #45), **#59**, **#61**, **#62**, **#64**, and **#65** reviewed/merged.
- Follow up on **issue #63** (Chris sign-off on prioritizing agent memory alongside the planning benchmark).

## 2026-06-13

**Focus:** ScienceWorld benchmark interface; align Phase 2 memory with the planning benchmark (#47)

**Done today:**
- Opened **PR #62** (`docs/scienceworld-interface`): design for plugging the engine into the [**ScienceWorld**](https://github.com/allenai/ScienceWorld) benchmark — local clone under `benchmarks/`, adapter shape, evaluation loop. Documentation only for now.
- Opened **issue #63**: ask Chris to **prioritize and approve** the agent-memory layer (#37) and agree we should build it **in parallel** with the planning-benchmark work (#47), not after it.

**Blockers / questions:**
- Waiting on Chris for #63 (memory prioritization + design sign-off).

**Next:**
- Land **PR #49** (#42 contested resources).
- Keep iterating **PR #54** (#45 knowledge layer).

## 2026-06-11

**Focus:** first CI + docs site; fix Claude Code hook; planning/reproducibility design docs

**Done today:**
- Merged **PR #39** (issue #38): coverage-hook launcher resolves the interpreter (`venv/bin/python` → `python3` → `python`) instead of hard-coding `venv/bin/python` — fixes noisy hook failures on conda/lab machines.
- Merged **PR #50**: local-only **MkDocs** documentation site (`pip install -e .[docs]` → `mkdocs serve` at `127.0.0.1:8000`). Material theme + mkdocstrings; no public deploy yet.
- Merged **PR #51**: moved `test_npc_behaviors.py` into `tests/` so `pytest tests/` collects the narrated NPC behavior suite automatically.
- Merged **PR #55**: first **GitHub Actions CI** — mirrors the `/check` gates (`black --check`, `pytest tests/`, `test_npc_behaviors.py`) on push/PR across Python 3.11–3.13.
- Merged **PR #56**: `docs/design/llm-cost-observability.md` — long-term design for token accounting, cost reduction, and reproducible LLM runs (usage ledger, price table, build order).
- Opened **PR #59** (`docs/planning-benchmark-plan`): temp plan for issue **#47** (multi-step planning benchmark harness) in `docs/design/planning-benchmark.md`.
- Opened **PR #60** then closed it in favor of **PR #61** (`feat/reproducible-runs`): unified design + implementation for record/replay, YAML run records, and pinning nondeterminism — companion to the planning benchmark.

**Blockers / questions:**
- none

**Next:**
- Land **PR #49** and **#54**.
- Get **#59** / **#61** reviewed.

## 2026-06-10

**Focus:** Phase 2 agent memory design; start knowledge layer (#45) and contested resources (#42)

**Done today:**
- Merged **PR #37**: `docs/design/agent-memory.md` — Phase 2 proposal for per-agent memory (memory streams, retrieval by recency/importance/relevance, reflection, planning, privacy, save/load, build order). Documentation only; marks the start of memory work after simultaneous turns shipped.
- Opened **PR #54** (issue #45): per-character **knowledge / belief layer** — private world-model beliefs (`Knowledge`/`Belief`) distinct from episodic memory (#37); composes via separate `describe_for` sections, no `memory.py` dependency.
- Opened **PR #49** (issue #42): contested resources + retry policy in simultaneous mode — scoped the #35 design's claim/arbitrate/recover path for when two NPCs target the same resource.

**Blockers / questions:**
- none

**Next:**
- Land infra/docs PRs (#39, #50, #51, #55, #56).
- Get **#49** and **#54** to review-ready.

## 2026-06-09

**Focus:** land the output/trace rendering stack (#31); rebase #30 onto a much-changed `main`; ship shared Claude Code automations and a sim-action design doc

**Done today:**
- Merged **PR #31** (unified output & agent-trace rendering) into `main`. Added a final commit first — `docs: add user-facing guide to reading game output` — so the merge ships the `Message`/`Channel`/`Renderer` seam (rich terminal + `PlainRenderer` fallback) together with a reader-facing guide. Two teammate PRs also landed on `main` today around the same window (**#28** tiered goals, **#33** scenario integration tests), so the merge base shifted under everything in flight.
- Rebased **PR #30** (issue #25, simultaneous turn mode) onto the new `origin/main` and got it back to **MERGEABLE/CLEAN**. This took several reconciling commits against the day's landings:
  - `fix: sync agent goals from character in simultaneous gather phase` — gather now pulls each agent's goal from its character so the tiered-goals API (#28) feeds the decide step correctly.
  - `docs: migrate multi-agent notebook to the tiered-goals API (issue #23)` — moved the notebook off the old goal shape onto #28's API.
  - `fix: adapt to #31 output/trace rendering after rebase` — wired the simultaneous path through the new rendering seam now that #31 is on `main`.
  - Merged `main` into the branch (resolving a notebook conflict from the `Force rich rendering` commit), then `docs: split multi-agent notebook into sequential + simultaneous (issue #25)` — the notebook is now two clear walkthroughs instead of one overloaded cell.
- Committed `Force rich rendering in multi-agent notebook` to `main` so the committed notebook output renders via the rich renderer rather than the plain fallback.
- Opened **PR #34** (`chore/claude-code-automations`): project-shared Claude Code automations — a renderer-coverage guard hook plus a `/sync-renderer` command — so the rendering seam stays in sync as new output paths get added.
- Opened **PR #35** (`docs/simultaneous-actions-design`): a design doc for simultaneous action resolution, capturing the gather→resolve→react model behind #30.
- Merged **PR #30**, **#34**, and **#35** into `main` (finishing the day's queue).

**Blockers / questions:**
- none

**Next:**
- Phase 2: agent memory (#37).

## 2026-06-07

**Focus:** clear the merge queue (#20, #22); implement simultaneous turns (#25)

**Done today:**
- Merged **PR #20** (multi-agent demo notebook) and **PR #27** (issue #22) into `main`. #21 (issue #5, ReAct wired into the live game) had merged on the 4th, so the whole ReAct + notebook + world-state stack is now on `main`.
- Opened **PR #30** (issue #25): opt-in **simultaneous turn mode**. New `turns.py` runs a `gather → resolve → react → advance` round per the `docs/design/multi-character-play.md` §3/§8 spec — every NPC agent decides against the **turn-start snapshot** (no peeking at others' actions this round), then commands resolve player-first and in `initiative` order (ties keep gather order). Contention settles at the precondition gate: the loser's command fails, the failure reason is fed back for a capped reflect-retry (`route_with_retry`), and an unrecovered failure is logged as an `action_failed` event.
- Added `Game(..., turn_mode="simultaneous")` (validated flag; default `"sequential"` path byte-for-byte unchanged, `end_turn()` untouched) and first-class `Character.set_agent(agent)` so gather can call `decide()` directly. Refactored `npc.py` to share the decide→route→reflect core (`decide_and_route`) between sequential and simultaneous modes — behavior-preserving, same `1 + max_retries` attempt budget.
- `tests/test_simultaneous_turns.py`: 10 offline `ScriptedAgent` tests (NPC-vs-NPC contention, player-vs-NPC snapshot contention, gather-order tie-break, death between gather and resolve, failed player command, `decide() -> None`, legacy-behavior compat, turn-mode validation, sequential regression). Full suite 162 passing; `test_npc_behaviors.py` green.
- Demoed the mode offline in `notebooks/multi_agent_action_castle.ipynb` (§10): a one-fish standoff where the guard's initiative beats the troll's gather order, the player's resolve-first priority defeats both NPCs, the troll's reflect-retry recovers, and the guard's unrecovered failure lands in the event log. Sequential walkthrough re-executed, unchanged (same 47 events).

**Blockers / questions:**
- none

**Next:**
- Get **PR #30** reviewed/merged.
- Future work parked in #25's design doc: the session layer ("Someone else got there first" narration, `/switch`, party control) and dry-run preconditions.
- Phase 2: agent memory.

## 2026-06-05

**Focus:** issue #22 — stop NPC mechanics from depending on narration text

**Done today:**
- Opened **PR #27** (issue #22): gate NPC mechanics on **world state, not narration strings**. `describe_for()` now renders a dedicated "Your state:" section so agent brains can read their own properties (which observations otherwise omit) and decide on mechanics from state rather than substring-matching the prose. Stacked on PR #20; planned to retarget to `main` once #20 landed (it did, 6/7).
- Black-formatted `test_npc_behaviors.py`.

**Blockers / questions:**
- none

**Next:**
- Land #20 then retarget/merge #27.

## 2026-06-04

**Focus:** reconcile **PR #21** with the actor seam (#19); start a reading list in the journal

**Done today:**
- On `main`: added a **Reading List** section to this journal — core papers on generative agents, ReAct, text worlds, and Concordia, plus a lower-priority tier. Corrected publication dates/ordering and added an arXiv column with links.
- On **PR #21** (issue #5): after **PR #19** (actor seam) merged, pushed a reconcile commit so hw1 custom NPC actions (`Growl`, `Snarl`, `Pound_Fists`, `Warn`, `Threaten`, `Haunt`, `Ghost_Touch`) resolve the acting character via `Action.acting_character()` instead of scanning text before the verb. ReAct already routes commands as `parse_command(cmd, actor=character)` with no name prefix, so the old scan mis-attributed narration (e.g. "The player growls menacingly at The player.") and let a banished ghost keep haunting by checking `is_banished` on the wrong character. Scripted behaviors (prefixed commands, no actor) are unchanged. Live-game tests now pin full narration strings, subject included, so this class of bug cannot slip through substring checks again.

**Blockers / questions:**
- none

**Next:**
- Get **PR #20** and **PR #21** reviewed/merged.
- Phase 2: agent memory.

## 2026-06-03

**Focus:** landed the time model (#7); notebooks reorg + multi-agent demo; wired ReAct into the live game (#5)

**Done today:**
- Landed **PR #18** (issue #7, time model): stateless `GameClock` (`clock.py`), opt-in `Game(time_config=...)`, `schedule_event` as sugar for a non-repeatable `at_turn(turn)` trigger, time in prompt/`describe()`, clock-config serialization, 378-line offline test suite (`tests/test_time_model.py`). Closed the old WIP #15 in favor of the clean stacked version.
- Opened **PR #20**: renamed `homeworks/` → `notebooks/` and added `multi_agent_action_castle.ipynb`, a multi-agent Action Castle demo. Iterated to stream the transcript live and make the play cell safely re-runnable; re-ran for clean committed output.
- Opened **PR #21** (issue #5): wired ReAct LLM behavior into the live game end-to-end. Added `MockReActClient` (provider `"mock"`) — a free, deterministic stand-in that drives the full ReAct loop offline — plus `client_from_env()` gating, a pure-ReAct `homeworks/hw1_llm/play.py` entry point, and webapp wiring via `build_game(llm_client=...)` (hybrid: ReAct with scripted fallback). Fixed an `LlmParser.fail` bug that broke the Reflect step. New `tests/test_react_live_game.py` runs ReAct against the real Action Castle game.
- Follow-up commit on #21: agents now reply in a labeled `Reasoning:`/`Action:` format and each decision is traced as `name [reasoning] ...` / `name [action] ...` via `parser.npc_log`, kept out of `command_history` so one NPC's thoughts never leak into another's observations.

**Blockers / questions:**
- The mock ReAct brain is string-coupled to Action Castle's room/item names — fine for tests, worth noting before anyone reuses it for another game.

**Next:**
- Get #20 and #21 reviewed/merged.
- Phase 2: agent memory.

## 2026-06-02

**Focus:** addressing review feedback and landing yesterday's PRs; started #7 (time model)

**Done today:**
- Addressed review on #13: rebased onto `main` to resolve the duplicate `pytest` entry in `setup.py`, and moved `test_agent_layer.py` into `tests/` to standardize test location.
- Merged #13 (squash) after #11; closed #12 in favor of the journal convention now on `main`.
- Continued #7 (time model) on **draft PR #15** (still WIP, not merged). Reworked it later in the day to build on the #6 trigger system instead of being a parallel mechanism: rebased/stacked the branch on PR #16 (#6 event log + triggers), which must merge first. `schedule_event` is now **sugar for a non-repeatable `at_turn(turn)` trigger** rather than its own post-round hook, so scheduled events follow trigger semantics (fire once in the react phase, recorded in the event log) — one loop, one clock, one react phase. Recurring events re-schedule themselves or use `add_trigger` with `every(n)`.
- Current shape on the branch: stateless `GameClock` (`clock.py`, turn → in-game time + named day periods), opt-in `Game(time_config=...)`, time shown in prompt/`describe()`/`describe_for()`, clock config serialization, now 34 offline tests in `tests/test_time_model.py` (full branch suite 91 passing).
- Deliberately deferred in #15: time-of-day in location descriptions (blocked on the `View` work, #9), webapp time display, and an NPC-schedule example.

**Blockers / questions:**
- (Resolved) Had a design question on whether `schedule_event` should stay its own mechanism or become sugar for #6's timer triggers — settled on building it on the #6 trigger system (`at_turn(turn)`), so we don't ship two overlapping time mechanisms. #15 now stacked on #16; **#16 needs to merge first**, then rebase #15 onto `main` and retarget before it can land.

**Next:**
- Start issue #3 (Agent class on the agent layer), on its own branch.
- Land #15 once #16 merges (rebase onto `main`, retarget, final review).

## 2026-06-01

**Focus:** test infrastructure + #2 mock LLM client

**Done today:**
- Opened #11: fixed `Thing.get_property()` fallback in `things/base.py`, added `pytest` to deps, and added `tests/test_base.py`. (Merged.)
- Opened #13 for issue #2: deterministic `MockLlmClient` in `llm_client.py` (queued responses + callable responder, call recording, `None` = simulated API failure), plus `test_agent_layer.py` covering keyword fast-path, LLM fallbacks, failure handling, and the ReAct retry path. Added `docs/TESTING.md`.
- Opened #12 to store multi-agent design iteration notes for reference. (Later closed.)

**Blockers / questions:**
- none

**Next:**
- Get #11 and #13 reviewed/merged (rebase #13 after #11 lands).

## Reading List

| Title | Authors | Journal/Conference | Date Published | arXiv | Notes |
|-------|---------|-------------------|----------------|-------|-------|
| ExpeL: LLM Agents Are Experiential Learners | Tsinghua University | AAAI | February 2024 | [2308.10144](https://arxiv.org/abs/2308.10144) | |
| Generative agent-based modeling with actions grounded in physical, social, or digital space using Concordia | Google DeepMind; Google Research; Technion; University of Toronto | arXiv | December 2023 | [2312.03664](https://arxiv.org/abs/2312.03664) | |
| CLIN: A Continually Learning Language Agent for Rapid Task Adaptation and Generalization | Allen Institute for AI; University of Arizona; University of Pennsylvania | COLM | October 2023 | [2310.10134](https://arxiv.org/abs/2310.10134) | |
| Generative Agents: Interactive Simulacra of Human Behavior | Stanford University; Google Research; Google DeepMind | UIST | April 2023 | [2304.03442](https://arxiv.org/abs/2304.03442) | |
| ReAct: Synergizing Reasoning and Acting in Language Models | Princeton University; Google Research | ICLR | October 2022 | [2210.03629](https://arxiv.org/abs/2210.03629) | |
| A Systematic Survey of Text Worlds as Embodied Natural Language Environments | University of Arizona | Wordplay | July 2021 | [2107.04132](https://arxiv.org/abs/2107.04132) | |

### Lower priority 

| Title | Authors | Journal/Conference | Date Published | arXiv | Notes |
|-------|---------|-------------------|----------------|-------|-------|
| Large Language Models are Superpositions of All Characters: Attaining Arbitrary Role-play via Self-Alignment | Alibaba Inc. | ACL | January 2024 | [2401.12474](https://arxiv.org/abs/2401.12474) | |
| Humanoid Agents: Platform for Simulating Human-like Generative Agents | University of Washington; NVIDIA; University of Hong Kong | EMNLP | October 2023 | [2310.05418](https://arxiv.org/abs/2310.05418) | |

### Quick links

- [ChatGPT conversation](https://chatgpt.com/share/6a30535f-3760-83ea-a7d0-7fd40d21cc99)
