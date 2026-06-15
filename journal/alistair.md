# Alistair's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md). [Reading List](#reading-list)

<!-- Copy the template from README.md to the top each working day. -->

## 2026-06-15

**Focus:** land contested-resource resolution in simultaneous mode (#42); repo hygiene (progress tracker, uv, ScienceWorld clones)

**Done today:**
- Merged **PR #49** (issue #42): **contested resources + retry policy** in simultaneous turn mode — stages 1–4 of `docs/design/simultaneous-actions.md` (#35). The resolve step now runs **claim → arbitrate → recover**: `Intent` carries ranked `fallbacks`, `resolve_order()` sorts by `(phase, -initiative, gather_index)` with an optional `Game` override, opt-in `Game.phases` buckets actions (`communicate < move < manipulate < fight`), and losers get a specific contention failure fed into the capped reflect-retry instead of a generic `"I don't see it."`
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
