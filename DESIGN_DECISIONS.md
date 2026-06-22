# Tingen — Design Decisions Log

Running log of the choices I made while implementing TODO tasks 1–10 in the Godot
project, plus open questions for you to review. Where I had to guess, I picked what
seemed the best default and noted it here rather than stopping to ask.

Last updated after implementing all 10 "buildable now" tasks **and validating headless**:
project imports clean, the main scene boots with zero script errors, and the
`tests/run_tests.gd` suite reports **25/25 passing**.

---

## Architecture overview

Everything is wired as **autoload singletons** (globals) plus **data-driven JSON**
in [`tingen/data/`](tingen/data/). The singletons form a dependency chain (each only
depends on the ones above it):

```
WorldState     pressure vars + signal bus + current lead          (no deps)
Clock          day / minute / phase, ticks, day-night tint        (no deps)
WorldManager   6-stage machine, pressure simulation, slots        (WorldState, Clock)
EventManager   weighted event selection                           (WorldState, WorldManager)
ClueDB          clue library + collected state + unlocked topics    (WorldState, WorldManager)
DialogueManager branching topic/clue-aware dialogue                 (ClueDB, WorldState)
NpcDB          NPC schedules + dialogue links                      (—, read by NPCs)
SaveManager    serialize/restore everything to user://save.json   (all of the above)
DevConsole     debug overlay (autoloaded CanvasLayer scene)        (all of the above)
```

UI that must live in the scene tree (not autoloads): the **Toasts** layer, the
**District Map** modal, and the **Dialogue** panel all live inside
[`ui/HUD.tscn`](tingen/ui/HUD.tscn).

**Why autoloads + JSON:** matches the GDD's "data-driven, authorable" intent and the
Yumina docs' state-store/registry pattern, and keeps every system headless-testable
and save/load-serializable without scene coupling.

---

## Decisions by task

### Canon reconciliation (prerequisite)
- Replaced the scaffold's pressure vars with the canonical five:
  `corruption, panic, fatigue, cult_readiness, attention` (all 0–100).
- **`stability` is now derived, not stored:** `100 − (corruption·0.5 + panic·0.3 +
  cult_readiness·0.2)`, clamped. The HUD "Stability" meter reads this. Rationale: the
  docs list only the five pressures as state; stability is a player-facing summary.
  - *Open Q1:* Is that the formula/weighting you want for stability, or should
    `attention`/`fatigue` factor in too? Easy to change in `WorldState.stability()`.
- Dropped `player_trust` and `cult_affinity` (not in §8.3 canon). If they were
  intentional, say so and I'll re-add as a separate "alignment" sub-model (they map to
  the "corruption/alignment drift" later-bet).

### Task 3 — Clock
- 6 phases with the doc's minute boundaries. Default speed **1 real second = 1 game
  minute** (a full day = 24 real minutes); override via
  `Clock.real_seconds_per_game_minute`. Starts Day 1, 08:00 (morning).
  - *Open Q2:* The scaffold opened at "Night 02:14" (the suicide-awakening cold open).
    I default the clock to morning for general testing. Should the **intro** force the
    clock to late-night until the player leaves the room? I left a hook
    (`Clock.set_time()`) but did not force it.
- Day/night mood via a single `CanvasModulate` (`DayNightTint.gd`) that lerps tint per
  phase — zero art, matches TODO task 3.

### Task 1 — World Manager
- Stage machine advances **one stage per refresh** when the next stage's `enter_when`
  conditions pass (sequential, no skipping). Conditions supported:
  `clue_count_gte`, `pressure_gte`, `stage_duration_gte` (in refreshes).
- **Strategic refresh = 60 s** real time (GDD's number) on a `Timer`; each refresh runs
  pressure dynamics, threshold checks, stage-advance check, and the offscreen tick.
  - *Open Q3:* 60 s is slow for hands-on testing. The dev console can fast-forward
    refreshes; is a shorter default (say 15 s) better for the slice? Currently 60 s.
- Pressure dynamics per refresh (tunable constants at the top of `WorldManager.gd`):
  panic decays −1.5; corruption drifts up with stage + `cult_readiness`; `cult_readiness`
  rises by a per-stage activity coefficient; `fatigue` creeps up; `attention` tracks
  corruption. These are **placeholder curves** — flagged for balancing.
  - *Open Q4:* These numbers are guesses to make meters visibly move. Want me to derive
    them from a specific GDD pacing target (e.g. "ritual night by ~Day 5")?
- **Dynamic slots** (`primary_ritual_site`, `first_corrupted_civilian`, `decoy_courier`)
  resolved via a **seeded** `RandomNumberGenerator` from weighted candidate pools.
  Seed defaults to a random value at new-game and is **persisted** so loads are
  deterministic. Candidates are placeholder district/NPC ids.
- **Offscreen resolution** (§8.6) is a light stub: every refresh nudges `cult_readiness`
  by the current stage's coefficient. The "real" deterministic district sim is left as a
  later bet (it's flagged research-flavored in the docs).

### Task 2 — Weighted events
- `score = weight × state_match`. **As built:** every entry in an event's `conditions`
  array is a *hard gate* — all must pass or the event scores 0 (disqualified). `state_match`
  is then a soft multiplier (currently driven by an optional `prefer_stage` hint: 1.0 if it
  matches the current stage, 0.5 otherwise). `cooldown` (in refreshes) stops a beat repeating
  back-to-back.
- One eligible event is drawn **weighted-randomly** (not strictly highest-scoring) per
  strategic refresh, so the city doesn't feel deterministic. Effects: `pressure`
  (→ WorldState.adjust), `lead` (→ set lead), `collect` (→ ClueDB), and passive
  `notify` / `stage_hint` payloads the toast layer reads.
  - *Open Q5:* One event per refresh keeps the city legible. Should multiple low-weight
    "ambient" events be able to co-fire? Currently single-fire.
  - *Note:* The event RNG is seeded from `WorldManager.seed_value` so a reloaded save
    replays the same draws.
- Authored sample events live in [`data/events.json`](tingen/data/events.json) — replace
  freely; the schema is documented at the top of `EventManager.gd`.

### Task 5 — Clues + board
- Canonical `Clue` shape with `type ∈ {physical, behavioral, occult, testimony}` and
  `importance ∈ {pivotal, supporting, flavor}`. Library in
  [`data/clues.json`](tingen/data/clues.json); collected state (id → discovered-turn) in
  ClueDB and serialized by SaveManager.
- Examining an Interactable with a `clue_id` **collects** the clue and **unlocks its
  topics** (drives dialogue). The Investigation Board now renders collected clues
  dynamically grouped by type, with the open-threads list driven by the active lead.
  Drag-connect graph deferred per the docs ("ship flat gallery first").

### Task 4 — Dialogue
- Branching trees in [`data/dialogue.json`](tingen/data/dialogue.json), keyed by NPC id.
  Options support `requires_topic` / `requires_clue` gating (hidden until unlocked),
  `effects`, and a `contradiction` flag that renders the line differently (the
  "call-out known clues" mechanic). LLM dialogue intentionally **not** built (docs say
  avoid a visual dialogue tree / Ink — data + topic-gating covers it).
- Dialogue panel pauses player movement while open. No portraits (asset-gated).

### Task 6 — NPCs
- NPC is a stub `CharacterBody2D` (tinted rect) reading its schedule + dialogue link
  from [`data/npcs.json`](tingen/data/npcs.json). On `Clock.phase_changed` it re-targets
  the waypoint for the new phase and **straight-line steers** toward it.
  - *Decision:* No A* pathfinding yet — straight-line `move_toward` with wall sliding.
    Real waypoint-graph/navmesh pathfinding is a later polish item; the schedule logic
    (the interesting, art-agnostic part) is what's built. Flagged.
- Talking to an NPC opens its dialogue tree via the Task 4 system.

### Task 7 — Save / load
- One JSON blob at `user://save.json` capturing WorldState pressures + lead, Clock,
  WorldManager (stage, slots, **seed**, refresh count, threshold bookkeeping), collected
  clues + topics, and the current scene path + player position. Load restores all
  singletons then transitions to the saved scene and repositions the player.
- Round-trip is headless-testable (see Task 10 runner). The agent-sandbox
  "don't silently drop state" lesson: load fails **loudly** (push_error) on a malformed
  file rather than partially applying.

### Task 8 — Toasts
- Bottom-right queued toast stack in the HUD ([`ui/Toasts.tscn`](tingen/ui/Toasts.tscn)).
  Subscribes to `EventManager.event_fired`, `WorldManager.pressure_threshold_crossed`, and
  `WorldManager.stage_advanced`. Each card fades in, holds ~4 s, fades out and self-frees;
  at most 4 are visible (oldest evicted). **Cards are color-coded by `channel`**
  (`ambient` / `lead` / `alert` / `stage` / `system`) via a left accent bar, so severity
  is readable at a glance. The dev console can `push` a toast too (group `"toasts"`).

### Task 9 — District map
- Modal toggled with **M** ([`ui/DistrictMap.tscn`](tingen/ui/DistrictMap.tscn)). Districts
  are drawn in a custom `_draw()` (filled polygons + outlines + name labels) from
  [`data/districts.json`](tingen/data/districts.json) — **5 districts authored**. Each
  district's **risk tint** (green→red) blends its `base_risk` with the live citywide
  pressure it tracks (`risk_pressure`), so the map updates as the night degrades. Hovering
  a district shows a risk readout. (Chose hover-readout over click-select; no POI dots yet.)

### Task 10 — Dev console + tests
- **Dev console** toggled with **`** (backtick) — an autoloaded `CanvasLayer` that builds
  its own UI at runtime, so it works in any scene with no wiring. Commands: `set <p> <v>`,
  `adjust <p> <d>`, `pressures` (dump), `refresh`, `stage`, `advance` (force next stage),
  `time <h> <m>`, `event` (force a roll), `clue <id>`, `toast <msg>`, `save`, `load`,
  `help`. Output scrollback doubles as the "rule trace" log.
- **Tests: I did NOT add GUT.** GUT is an external addon and fetching it isn't reliable
  offline, so instead I wrote a dependency-free headless runner at
  [`tests/run_tests.gd`](tingen/tests/run_tests.gd) (run with
  `godot --headless -s res://tests/run_tests.gd`). It covers: pressure clamping,
  threshold crossing, event scoring, clock phase/day rollover, slot determinism (same
  seed → same slots), and save/load round-trip. Exits non-zero on failure so it can gate
  CI later.
  - *Open Q6:* Want me to swap this for real GUT once the addon can be vendored? The test
    *logic* ports directly.

---

## Cross-cutting decisions
- **Single source of truth:** pressures live only in WorldState; WorldManager mutates
  them through `WorldState.adjust` so the HUD, save, and console all stay in sync.
- **Turn/refresh counter:** I treat each 60 s strategic refresh as a "turn" for
  clue/stage timestamps (the docs use "turn" loosely). Noted in case you expect
  per-player-action turns instead.
- **No new third-party addons** were added (kept the project dependency-free).
- All new input actions added: `toggle_map` (M), `toggle_console` (backtick). Existing
  `interact`, `toggle_board`, movement unchanged.

## Open questions, collected
1. Stability formula/weighting — right?
2. Should the intro force the clock to late-night?
3. Strategic-refresh default 60 s vs shorter for testing?
4. Pressure-curve constants — balance to a specific pacing target?
5. One event per refresh vs multiple ambient co-fires?
6. Swap the headless test runner for GUT later?
7. Dropped `player_trust` / `cult_affinity` — intentional to remove, or fold into a
   later alignment model?

---

## Decision log — Occult Tools + Hypothesis Board (2026-06-06 brainstorm)

Each entry: the question asked, the choice made (**bold**), and a one-line note on the
alternatives that were rejected. (Standing rule: log every design decision this way —
chosen option + brief description of the alternatives.)

- **What to build next?** → **Occult tools + endgame** (closes the gather → act → ending
  loop). *Alts:* occult tools only; rumor-propagation system; "connective tissue" (quest
  log / cutscene / offscreen sim / NPC reactions).
- **How much of the occult toolkit in v1?** → **All four tools fully, including the full
  Gray-Fog hypothesis board with confidence scoring.** *Alts:* three tools + a lightweight
  "commit your theory" hypothesis; three tools only, defer the board to its own spec.
- **How does the endgame resolve?** → **Player must find the true ritual site and win a
  (light) combat to win; if the cult isn't stopped the ritual completes, an evil god
  descends and everyone dies; the more the player impeded the ritual, the weaker the cult
  in that final fight. Combat stays "secondary to prevention" per the story doc.** *Alts:*
  committed hypothesis alone grades the ending (no combat); pure world-state-threshold
  grade with the board as info-only.
- **How to structure the work?** → **Split into two specs: (1) Occult Tools + Hypothesis
  Board now, which produces the "impede/insight" score; (2) Ritual-Night endgame + combat
  next, consuming that score.** *Alts:* endgame/combat first with placeholder inputs; one
  combined design doc covering everything.
- **Can the occult tools mislead the player?** → **Yes — they degrade with corruption:
  vague-but-true when clean, noisier and capable of false leads as corruption/attention
  rise. Cost = fatigue per use + attention buildup.** *Alts:* always truthful but vague
  (resource-gated only); always truthful but ambiguity widens (never outright false).
- **How hands-on is the Gray-Fog board?** → **Hybrid auto-link + edit:** auto-links
  collected clues to the candidate answers they support and shows live confidence; player
  can add/remove links and flag uncertainties. *Alts:* guided (auto-scored only); manual
  (drag clue cards from scratch).
- **Does the player "submit / commit" a conclusion? (revised 2026-06-06)** → **No — there
  is no submission UI.** The board *merely organizes clues and occasionally highlights a
  next step.* The player must actually find the cult and physically go stop it; whether
  they correctly identify the true ritual site is on them, read off the organized board.
  "How much you figured out / impeded the cult" is derived **implicitly** from investigation
  state (clues found, leads resolved, pressures) and feeds the (separate) endgame's combat
  difficulty — it is not a graded quiz answer. *Alt (rejected):* commit a hypothesis per
  open question that the endgame checks for correctness.
- **Can the board name the true ritual site?** → **No — directional hints only.** The board
  organizes clues and occasionally raises a *directional* lead ("evidence is clustering in
  the harbor", "this ledger page matters") but never declares the answer or marks the site
  as an objective. The player infers the site themselves and physically goes to confront it;
  how right/thorough they were sets how weak the cult is in the endgame. *Alts (rejected):*
  name the site once pivotal clues are found; always show the current highest-confidence
  candidate with a percentage.
- **Code architecture?** → **Approach C: split the transient verbs (`OccultTools` autoload)
  from the persistent inference model (`HypothesisBoard` autoload), with a shared static
  risk helper (`OccultRisk`) that applies fatigue/attention cost and corruption-driven
  noise via a seed tied to `WorldManager.seed_value`.** *Alts (rejected):* a single
  `OccultManager` autoload that owns both verbs and state (A — simpler but mixes one-shot
  actions with long-lived save/load state); per-tool scene nodes (B — more files, awkward
  for shared cost/corruption logic and save/load).
- **Code architecture (revised 2026-06-08)?** → **OOP manager + per-tool subclasses.** An
  abstract `OccultTool` base class exposes `use()`, `compute_cost()`, `can_use()`, with a
  template-method `use()` that checks → pays cost → calls virtual `_perform()` → applies
  risk. Concrete subclasses (`DivinationTool`, `ResidueSightTool`, `DreamFragmentsTool`,
  `GrayFogTool`) own their tool-specific behavior, cost, and risk shape. An
  `OccultToolManager` autoload owns the tool roster, cooldowns, the seeded RNG (from
  `WorldManager.seed_value`), and inventory routing. `OccultRisk` is demoted to a library of
  **shared seeded-RNG primitives** the tools call (mislead/noise rolls), not the risk
  decision-maker. `HypothesisBoard` stays a separate autoload. *Supersedes the single
  `OccultTools` autoload of the prior C decision. Alts (rejected):* keep one `OccultTools`
  autoload holding all verbs + a decision-making `OccultRisk` (less extensible, risk logic
  not co-located with each tool); fully self-contained tools with no shared RNG helper
  (duplicates seeding logic, hurts deterministic testing).
- **Inventory system?** → **Build a general, data-driven inventory system; the occult tools
  are items in it, and tools may consume/produce items.** Item categories envisioned: occult
  tools, ritual ingredients (to perform rituals), sustenance (food/water), and regular tools.
  *Alts (rejected):* reuse only the clue inventory (`ClueDB`) (clues aren't carryable goods,
  no consume/produce); per-tool ad-hoc state (no shared item economy, can't support rituals).
- **Inventory build scope?** → **Inventory foundation now, ritual engine later.** Build
  `data/items.json` + an `Inventory` autoload (counts, add/remove/use, save/load) + tool-as-item
  + consume/produce now; the ritual recipe engine is designed with a later spec. *Alts
  (rejected):* inventory + basic rituals now (bigger, pulls endgame design forward); full
  inventory + rituals + crafting (largest, risks scope creep).
- **Carry limits?** → **Unlimited capacity; reagents/food stack, unique tools/key items
  don't.** Resource tension comes from ingredient scarcity, not bag space. *Alts (rejected):*
  slot/weight capacity (more survival-sim tension but more UI + balancing).
- **Item taxonomy (LotM-grounded)?** → **Categories:** `occult_tool`, `divination_focus`
  (pendulum/tarot/dowsing rod/scrying mirror — canon Seer methods), `ingredient` (chalk,
  candles, salt, incense, herbs, monster-parts), `characteristic` (rare potion main material,
  魔药特性), `medium` (belonging/name slip/relic/corpse-token, targets divination & séance),
  `sustenance` (eases `fatigue`), `tool` (lantern/lockpick), `key_item` (sealed artifacts).
  Verified against the LotM wiki (Seer divination methods; Potion System; Ritualistic Magic).
- **Ritual purpose (fiction, for later engine)?** → **Rituals are the unifying primitive for
  many LotM acts:** divination/fortune-telling, potion-brewing (魔药), questioning the dead /
  séance (通灵), prayer to deities (祈祷), gray-fog transit (上灰雾), the cult's summoning of the
  descending evil god (邪神降临, endgame), and warding/sealing (封印). A ritual = (foci +
  ingredients + place/time conditions) → effect. *Only the ingredient slots are built now; the
  ritual engine is deferred.* *Alts (rejected):* model each act as a bespoke mechanic (no shared
  ritual abstraction, more code, inconsistent).

## Decision log — Core game pivot to open-world LLM agent-sim (2026-06-08)

This pivot supersedes the detective-mystery framing. See
`docs/superpowers/specs/2026-06-08-tingen-agent-sim-vertical-slice-design.md` and the GDD
direction update (§0.1).

- **Genre / core loop?** → **Open-world, real-time immersive simulation with an AI-managed
  story** — not a fixed detective mystery. The cult genuinely intends to summon a descending
  evil god and completes it if unopposed; the story is steered, not scripted. *Alts (rejected):*
  keep the fixed-mystery detective game (no emergence, on-rails); pure sandbox with no story
  management (incoherent, no dramatic arc).
- **NPC intelligence?** → **Each NPC is an autonomous LLM agent** (intent + memory + plans) that
  perceives and interacts with other agents; a cheap schedule-based **fallback behavior** runs
  while it deliberates. *Alts (rejected):* the original heuristic "60-second strategic refresh"
  (not emergent enough); a single LLM puppeteering all NPCs (loses per-agent identity, harder to
  reason about).
- **Story management?** → **A World-AI overseer + critic.** Director can re-task an agent, cancel
  a plan, or coordinate a group beat, and enforces invariants (e.g. *cult never exposed/caught by
  chance — exposure gated on player involvement*). Critic **catches and kills** boring/incoherent/
  illegal proposed actions (legality + coherence + interestingness). *Alts (rejected):* heuristic
  storyteller only (less surprising); LLM director with no critic (boring/faulty sims slip
  through).
- **Build approach?** → **Vertical slice first** (~3–5 agents, Iron Cross Street, one summoning
  thread, end to end), then scale to the city. *Alts (rejected):* design the full city
  architecture first (slow to playable, over-specifies); substrate + overseer with stubbed agents
  first (delays seeing the emergent magic).
- **Time model?** → **Real-time immersive sim**; agents deliberate **async in the background** on
  a beat cadence (or on events), with fallback behaviors hiding latency. *Alts (rejected):*
  beat/turn-based (easier latency/testing but board-game feel); hybrid real-time + pause-for-beats
  (two time modes, seams).
- **Resolution paths?** → **Multi-path with combat as the climax:** investigate → sabotage / turn
  the waverer / fight; accumulated **impede** scales climax difficulty. *Alts (rejected):*
  combat-first (thin vs. the agent sim); combat as failure-state only (contradicts "combat is
  important").
- **LLM orchestration?** → **External Python sidecar** (HTTP/stdio); owns prompts, Claude API
  calls, batching, caching, schema validation; API keys + nondeterminism quarantined there; tests
  mock it. *Alts (rejected):* in-engine GDScript HTTPRequest (clumsy orchestration, keys/nondet in
  engine); defer the choice (leaves a load-bearing decision open).
- **Slice cast?** → **Reuse existing roster + slot candidates** (Clerk Voss leader, Dalia
  logistics, Orin scout/waverer, Dockhand Pell victim), extending `npcs.json` with intents. *Alts
  (rejected):* author a fresh dedicated cast (diverges from existing data, more content).
- **Gray-Fog Hypothesis Board?** → **Cut.** Detective deduction doesn't fit an emergent sim;
  occult tools instead give **directional perception leads**. *Alts (rejected):* keep the board
  (re-introduces fixed-mystery deduction). **NOTE — naming:** cutting this *board* does NOT
  remove **Gray Fog (灰雾) the world concept**, which is retained as lore. Canonical uses (for the
  deferred 上灰雾 / gray-fog-transit ritual): (1) above-the-gray-fog = the Tarot Club (塔罗会)
  meeting space / Fool's domain, entered by ritual, members shown only as identity-concealed
  outlines; (2) anti-divination shield + amplifier of one's own divination + shielding from
  High-Sequence Beyonders/deities; (3) object storage + send/receive relay; (4) information &
  Beyonder-ingredient/artifact exchange. In the slice this is **atmosphere only**, not a built
  mechanic.
- **Occult tools usable in combat + investigation?** → **Yes.** Tools are general-purpose verbs:
  perception/knowing information (divination/spirit-vision/dream → directional leads) AND combat
  (≥1 occult ability usable in the climax fight, more can extend the `OccultTool` hierarchy) AND
  feeding sabotage/social decisions. *Alts (rejected):* investigation-only tools (wastes the
  combat-relevant Seer abilities).
- **Occult tools + inventory specs?** → **Survive, demoted** to player **perception** (occult
  tools) and **action/economy** (inventory ingredients power sabotage). The OOP `OccultTool`
  hierarchy + manager + `OccultRisk` and the inventory foundation still apply. *Alts (rejected):*
  scrap them (lose the LotM-flavored verbs + the sabotage economy).

## Decision log — Vertical-slice implementation (6-plan build, 2026-06-08)

Decisions made while implementing Plans 1–6 (perception/commit/runtime, overseer/critic, player
verbs/combat). All landed with a green suite (189 passed, 0 failed) and two-stage review per task.

- **Autoload access from `class_name` scripts?** → **The `_al(name)` helper** —
  `(Engine.get_main_loop() as SceneTree).root.get_node("/root/" + name)` — used in every
  `class_name` lib that touches an autoload (Perception, ActionCommit, Critic, OccultTool & subs,
  Agent). In the headless `-s` harness, `class_name` scripts compile *before* autoloads register,
  so a bare global reference (`WorldState.corruption`) fails to compile with `Identifier not
  found`. *Alts (rejected):* bare autoload references (crash in the headless test harness, the
  primary CI path); converting the libs to autoloads (loses value-type/`RefCounted` semantics,
  pollutes the singleton namespace); a class-cache refresh (does not fix the compile-order issue).
- **"No exposure by chance" invariant — where enforced?** → **A single chokepoint in
  `Critic.review`**: an exposing `report` (to law/church/authorities, or naming cult/ritual/summon)
  is vetoed unless `Overseer.allows_exposure()` is true (i.e. the player is involved). Because every
  proposal funnels through the critic, the cult cannot be exposed by an unlucky autonomous beat.
  *Alts (rejected):* scatter the check across each verb's commit logic (bypassable, easy to forget
  one path); enforce it only in the sidecar/LLM prompt (non-deterministic, untestable, and the
  engine must hold the invariant regardless of the brain).
- **"World mutated only through ActionCommit" — how guaranteed?** → **`ActionCommit.commit` is the
  one place agents change world state**; the runtime never mutates agents directly and the critic
  is pure. *Alts (rejected):* let verbs apply their own effects inline at proposal time (multiple
  mutation paths, no single audit point); a generic event-sourced reducer (over-engineered for the
  slice's verb set).
- **No-name-site invariant for divination hints?** → **Enforced by a structural guard test**
  (`_test_divination_hints_never_name_site`) that asserts hint strings never contain the literal
  site name — divination gives a *direction*, never the address. *Alts (rejected):* rely on prose
  hygiene/code review only (silently regresses the moment someone edits a hint string); a
  single-RNG determinism test (proves repeatability, not the no-name promise).
- **Non-`approve` critic verdicts?** → **Fall straight back to the agent's schedule** (veto/reject
  → `tick_fallback`), logging `action_vetoed`/`action_rejected`; no synchronous re-ask. Keeps a beat
  bounded to one sidecar round-trip and keeps the world moving. *Alts (rejected):* re-ask the
  sidecar synchronously for a fresh proposal (unbounded beat latency, possible loops); freeze the
  agent until next beat (visibly inert NPCs).
- **Player verbs vs. agent actions?** → **Player verbs are first-class `EventBus` events**
  (`player_sabotage`, `player_social`, …) mirroring the agent-action shape, which is also what trips
  `Overseer.player_involved` and thus unlocks exposure. *Alts (rejected):* a separate player-input
  channel the overseer doesn't see (the exposure gate couldn't tell the player was involved); route
  player actions through the same propose→critic pipeline (the player isn't a deliberating agent;
  adds latency and pointless veto surface).
- **SummoningPlan countdown this slice?** → **Kept passive** — `countdown_beats`, `impede_score`,
  and `manifestation_strength()` are stored/queried but the countdown is **not** decremented yet;
  the forward-tick wiring is deferred to the scene-integration plan. Flagged by the integration
  reviewer (an Important finding) and accepted as a faithful, intentional slice boundary. *Alts
  (rejected):* wire the decrement to `Clock.beat_ticked` now (pulls scene-integration scope into
  the data-model slice, and the climax/manifestation consumer isn't built yet to observe it).
- **`EventBus` save/load replay?** → **`from_dict` restores the log but deliberately does NOT
  re-emit** the restored events on load — listeners (overseer, runtime) must not re-fire on a
  resumed game. *Alts (rejected):* replay events on load (double-counts `player_involved`, re-runs
  side effects, corrupts a resumed session).
- **GDScript↔Python schema parity — how tested? (Task #26)** → **A harness test runs the *real*
  sidecar code** — it imports `sidecar.py` and calls its actual `load_schema()` /
  `validate_action()` over a 16-action fixture battery (via `/usr/bin/env python3`), asserting
  identical verb sets, identical required-args per verb, and identical `(ok, reason)` verdicts
  against the engine's `ActionSchema`. Both sides read one shared `action_schema.json`, so the verb
  *data* can't drift; the real risk is the two independently hand-written *validators* diverging,
  which this locks down (verified by injecting a divergence and watching the test fail). *Alts
  (rejected):* reimplement the sidecar's validation in GDScript and compare (the copy is itself a
  new drift source); compare only the loaded JSON file (misses validator-behavior drift); defer the
  test until live-LLM wiring (drift would land silently first).
- **Parity test when no Python interpreter is present?** → **Skip loudly** — a new harness skip
  counter prints `=== N passed, M failed, K skipped ===` and a visible `SKIP` line, never failing
  the (otherwise pure-Godot) suite. *Alts (rejected):* hard-fail (breaks a Godot-only CI with no
  Python); silently pass (an unrun check masquerades as a passing one).
- **Fixtures handed to the Python helper?** → **A temp file path**, because a quote-laden JSON
  string does not survive an `OS.execute` argv intact (the double-quotes were stripped, mangling the
  JSON on the Python side). *Alts (rejected):* inline JSON arg (proved fragile in practice);
  stdin/pipe (Godot's `OS.execute` cannot feed stdin).

## Decision log — Live scene + UI panels (wire-up build, 2026-06-08)

The agent-sim brain (`AgentRuntime`/`Agents`/`Critic`/`SummoningPlan`) shipped headless and ran
*parallel to* the rendered `NPC.gd` nodes, which independently re-read `NpcDB` schedules in
`_physics_process`. `AgentRuntime.player_position` was a hardcoded `Vector2(440,300)`. This build
binds the brain to the scene and adds the four player-facing panels (character card, cult progress,
ritual, prayer). Split into six plans (A–F); A is the backbone the rest sit on.

- **On-screen NPCs vs. agent registry?** → **The rendered NPC node IS its `Agent` — it binds by id
  and reads its position FROM the registry each frame** (the beat loop moves the `Agent`; the node
  lerps to follow), and the live scene spawns one NPC per registry agent (data-driven) instead of
  hand-placing them. One source of truth for who's where. *Alts (rejected):* keep the two
  representations split and sync deltas both ways (two movement systems fighting, drift, double
  logic); let the node keep driving itself off `NpcDB` and ignore the brain (the visible world would
  contradict the simulation the panels report on).
- **`AgentRuntime.player_position`?** → **The live scene pushes the real player's `global_position`
  into `AgentRuntime` every frame** so "active agents near the player" is true to what's on screen.
  *Alts (rejected):* leave the hardcoded stand-in (attention budget keys off a phantom location);
  poll the player from inside the runtime (the autoload would need a scene reference, inverting the
  dependency).
- **Agent "thought" line?** → **New `Agent.thought` field**, set by the sidecar/critic when one
  speaks and otherwise **synthesized deterministically** from the agent's current action + intent,
  surfaced in the character card. *Alts (rejected):* reuse `intent` as the thought (intent is the
  long-horizon goal, not the moment-to-moment read; they want both shown); pure on-the-fly synthesis
  with no stored field (the real LLM needs somewhere to write a genuine thought).
- **Summoning countdown forward-tick + climax?** → **`SummoningPlan` decrements `countdown_beats`
  on `Clock.beat_ticked` and fires a `CombatEncounter(manifestation_strength())` climax at 0**,
  routed through a signal so the scene can present the fight. (Lifts the passive-countdown slice
  boundary noted in the previous build.) *Alts (rejected):* tick the countdown in the scene's
  `_process` (couples the doomsday clock to a scene being loaded — it must run in the headless sim
  too); fire the climax straight from `SummoningPlan` with no signal (the data model would reach up
  into scene/UI, inverting the dependency).
- **Prayer adjudication?** → **Through the same sidecar contract as agent actions** — a `pray`
  request returns one of four outcome categories the engine then applies; ships with a deterministic
  `MockSidecar` adjudicator now and a GDScript↔Python parity test, real LLM later. *Alts (rejected):*
  in-engine GDScript heuristic table (bakes the "mysterious, tarot-style" judgment the user wants the
  LLM to own into hardcoded rules); a separate prayer-only service (a second nondeterminism seam to
  secure and quarantine when the existing sidecar already adjudicates constrained verbs).
- **Prayer outcome vocabulary?** → **Four canon-faithful categories the adjudicator picks from:**
  Granted (应允 — a boon), Cryptic (神秘应答 — a riddling lead in the Fool's 愚者 register), Ignored
  (无应 — nothing happens), Punished (惩罚 — damage / corruption spike, up to death for defiling a
  god). Which one fires depends on the god, the player's standing, and the prayer's content — left to
  the adjudicator, per the user's canon call. *Alts (rejected):* a single "boon or nothing" roll
  (throws away the punishment + cryptic registers that are the whole point in LotM); free-text
  outcomes with no category (the engine can't apply mechanical effects to arbitrary prose).
- **Pantheon scope?** → **A focused Tingen set, not the full LotM 22-pathway pantheon:** the cult's
  descending outer god (外神/邪神), the Goddess of the Night / 黑夜女神 (Church of Evernight), the
  Eternal Blazing Sun / 永恒烈阳, and the Fool / 愚者. *Alts (rejected):* the full pantheon (content
  sprawl far beyond a vertical slice, most deities irrelevant to this district's story); a single
  prayer target (kills the standing/affinity contrast — praying to the Sun vs. the cult's god should
  read very differently).

### Planning refinements — prayer backend (Plans E/F)

- **Where prayer adjudication attaches to the contract?** → **A second method `adjudicate_prayer(request)`
  on `SidecarClient`, parallel to `propose(snapshots)` — not routed through the agents'
  propose→critic→commit action loop.** A prayer needs an *adjudicated outcome* (a verdict the engine
  then applies), not a world-mutating *action*; the shapes differ. *Alts (rejected):* feed prayer
  through `propose`/`Critic`/`ActionCommit` (forces a player petition into the agent-action shape and
  drags the critic into judging the player); a wholly separate prayer microservice (a second
  nondeterminism seam to quarantine when the existing sidecar boundary already fits).
- **Is `pray` still a real verb?** → **Yes — `pray` (args `god`,`prayer`) is added to the shared
  `action_schema.json`**, so it is validated, GDScript↔Python parity-checked, and available to agents
  too (a cultist can pray to 外神); the *rich* player-facing adjudication lives in `PrayerService`.
  *Alts (rejected):* a player-only prayer path with no schema verb (loses cross-language parity and
  forecloses agent prayer).
- **Are all gods mechanically symmetric?** → **No — asymmetric by design:** an opposing god's *Granted*
  boon **impedes the descent** (`SummoningPlan.add_impede`), while the descending god's (外神) *Granted*
  favor **feeds the gate** (raises `corruption` + `cult_readiness`). Praying to the evil god is a
  Faustian bargain. *Alts (rejected):* every Granted gives the same boon (flattens the central tension
  that the outer god's power is a trap).
- **How is "the LLM decides" modeled deterministically now?** → **Explicit scoring the mock + a Python
  reference share byte-for-byte:** respect/disrespect marker counts + domain-keyword hit + clamped
  standing vs. fixed thresholds; the Fool (愚者) always answers in the *cryptic* register; any
  disrespect always *punishes*. A `(outcome, severity)` parity test guards the two languages. Per-god
  **standing** lives in `PrayerService` and persists via `SaveManager`. *Alts (rejected):* random /
  weighted-roll outcomes (non-deterministic, untestable, no parity); deriving favor from existing
  pressure vars (couples unrelated systems and isn't per-god).

### Implementation notes — cult progress panel (Plan C)

- **How does the panel convey the threat?** → **Through proxies, never the hidden number:** a
  closeness bar derived from `countdown_beats / START_COUNTDOWN`, the cell's remaining ritual stock,
  and a *qualitative* `interference_band()` ("none/minor/significant/heavy") for the player's impede
  score. `manifestation_strength()` is never shown as a digit. The player reads danger the way the
  GDD intends — through how close and how supplied the cult looks, not a stat. *Alts (rejected):*
  surface the raw strength/impede numbers (collapses the "feel the threat through the world" tension
  into a min-max readout); show only a single percent with no stock/interference breakdown (hides
  that *the player's own sabotage* is what moves the needle).
- **How is the public-event feed kept from leaking cult secrets?** → **A default-deny allow-list
  (`PUBLIC_TYPES`):** only whitelisted EventBus types render; the cult's `agent_action` /
  `agent_action_amended` and the runtime's `action_rejected` / `action_vetoed` / `directive_rejected`
  reasoning are excluded *by construction*, so any new secret type added to `AgentRuntime` later
  cannot leak without an explicit opt-in. *Alts (rejected):* a deny-list of secret types (the unsafe
  inversion — a newly-added secret event is public until someone remembers to blacklist it); no
  filter, formatting every event (hands the player the cult's private move log, defeating the whole
  "never exposed by chance" premise). Non-emitted public categories (`event`, `world_pressure`) are
  pre-allowed and annotated, so wiring their emitters later just works.
- **What drives a refresh?** → **Both `EventBus.event_logged` and `WorldState.state_changed`** while
  visible, and `_fill()` clears with synchronous `free()` (not `queue_free`) so two refreshes in one
  frame can't stack duplicate rows. *Alts (rejected):* refresh on EventBus only (the interference
  band shifts via pressures that don't emit a bus event — the bar would go stale); a polling timer
  (wasteful, and laggy relative to the beat that just changed the state).

### Implementation notes — ritual & occult-tool panel (Plan D)

- **How does the panel read the player's occult tools?** → **A UI-facing `tool_views()` accessor on
  `OccultToolManager`** that flattens each tool's name/description/required-item/`compute_cost()`/
  uses-left/can-use into a plain dict (sorted by name), plus a one-line `description` added to each
  tool in `occult_tools.json`. The manager's `_tools` (live `OccultTool` objects bound to the seeded
  RNG) stay private. *Alts (rejected):* expose `_tools` to the panel (leaks RNG-coupled internals
  into UI code and lets a panel mutate gameplay state); have the panel re-read `occult_tools.json`
  and recompute costs/availability itself (duplicates the manager's cost + gating logic, which then
  drifts the moment either side changes).
- **What does the cult-rite half show, and where does it come from?** → **A read-only reference card
  (recipe + ordered steps) from a new `data/rituals.json`** — what the rite *requires in total* and
  the *procedure*, not live cult state. The live, dwindling ritual stock is the Cult Progress panel's
  job (Plan C). *Alts (rejected):* render `SummoningPlan.ingredients` here too (splits one truth
  across two panels — the player would see two different ingredient readouts); drop the rite section
  entirely (the request asks the panel to "specify usage **and requirements**" — without the rite the
  player can't see what the cult is assembling, hence what to deny them).
- **How are tool/rite rows cleared on refresh, and why an explicit `refresh()` after a Use?** →
  **Synchronous `free()`** (as in Plans B/C) because a single Use fires `item_removed` + `item_added`
  + the explicit `refresh()` in one frame; and the explicit refresh is **kept deliberately** so a
  tool that changes uses-left/can-use *without* touching the Inventory (a limited-use tool that spends
  no ingredient) still updates its row and Use button. *Alts (rejected):* `queue_free` (defers to
  end-of-frame, stacking duplicate rows under exactly this multi-refresh — the B4/C2 bug); rely on
  Inventory signals alone and drop the explicit refresh (a no-ingredient limited-use tool would leave
  a stale "uses left" and an incorrectly-enabled Use button).

### Implementation notes — prayer backend (Plan E)

- **Where does prayer judgment live?** → **A second method on the existing sidecar contract,
  `adjudicate_prayer(request)`, parallel to the agents' `propose(snapshots)`** — base neutral on
  `SidecarClient`, deterministic on `MockSidecar`, passthrough on `SidecarBridge`. The real LLM
  replaces the mock later behind the identical seam, exactly as for agent proposals, so no API key
  ever enters the engine (祈祷裁决 stays local/deterministic in-engine, quarantined LLM in the
  sidecar). *Alts (rejected):* a brand-new `PrayerSidecar`/second bridge (a parallel seam to keep in
  sync for no gain — prayer is "ask the brain to judge," the same shape as `propose`); bake judgment
  straight into `PrayerService` (couples gameplay orchestration to the nondeterministic brain and
  loses the mock/LLM swap that keeps CI offline).
- **How is GDScript↔Python adjudication kept honest?** → **Two byte-exact mirrored deterministic
  adjudicators (`MockSidecar.adjudicate_prayer` ↔ `agent-sidecar/prayer_adjudicator.py`) reading the
  same `gods.json`, guarded by a parity test** that runs a fixture battery through both and asserts
  identical `(outcome, severity)` — the same guard pattern as the action-schema parity test. `wrath`
  values (1.0/0.4/0.8/0.3) are chosen so `wrath*2` never lands on `.5` (GDScript and Python round
  `.5` oppositely). *Alts (rejected):* GDScript-only with no Python reference (the LLM sidecar is
  Python — without a reference the two would silently diverge the day the real adjudicator ships);
  share the scoring as JSON-config rules both languages interpret (a config interpreter in each
  language is more surface to drift than the ~30 lines it would parameterize).
- **Decision order in the scorer** → **disrespect → tarot → grant-threshold → cryptic-threshold →
  ignored**, checked in that order. Consequences are deliberate: *any* disrespect marker punishes
  regardless of god or standing (you do not get to insult a god and be granted), and the Fool
  (`register=="tarot"`) short-circuits to cryptic **before** the grant check, so **the Fool can never
  grant** no matter the standing — it only ever answers obliquely, matching its canon. *Alts
  (rejected):* fold disrespect into the numeric score (a high-standing supplicant could then insult a
  god and still be granted on net score — wrong tone); let the Fool grant at high score (contradicts
  "answers obliquely, if at all").
- **PrayerService is an autoload `Node`, not a `class_name`** → so it can use **bare** autoload refs
  (`WorldState`/`SummoningPlan`/`EventBus`/`SidecarBridge`/`GodDB`/`ActionSchema`) at runtime and
  join `SaveManager`'s `to_dict`/`from_dict` roster (per-god standing persists). *Alts (rejected):* a
  `class_name` helper (would need the `_al()` /root dance and can't be an autoload save participant).

**End-of-plan review triage (rejected items, with rationale):**
- **Substring marker matching** (`"disobey"` contains `"obey"`, etc.) is kept, not upgraded to
  word-boundary matching. It is *parity-safe* (both languages behave identically) and this scorer is
  an explicit deterministic stand-in for the LLM, which will replace it; word-boundary matching adds
  GDScript-regex↔Python-regex drift risk for a placeholder. *Alt (rejected):* regex word boundaries
  on both sides (new parity hazard for marginal realism on throwaway logic).
- **The Fool's +1 standing on every non-insulting prayer** is kept (not gated to score-earned
  cryptic). It is *mechanically inert*: because tarot short-circuits before the grant check, Fool
  standing never unlocks anything, so "farming" it does nothing — the bump is pure relationship
  flavor. *Alt (rejected):* zero standing for tarot-forced cryptic (extra branch for no mechanical
  effect).
- **`GodDB._ensure_loaded` sets `_loaded=true` before the parse** (so a missing file logs once and
  returns empty on later calls) is kept because it **mirrors the existing `ActionSchema` loader** —
  consistency across the two static loaders beats a lone divergent retry path; a missing `gods.json`
  is a packaging failure the single `push_error` surfaces. *Alt (rejected):* set the flag only after a
  successful parse (diverges from ActionSchema for a case that means the build is broken anyway).

### Implementation notes — prayer panel (Plan F)

- **The god buttons share one `ButtonGroup` (radio set)** → selecting another god clears the previous
  one, and re-clicking the active god can't toggle it off into an orphaned "nothing selected but a
  god is still chosen" visual state. *Alts (rejected):* independent toggle buttons with manual
  bookkeeping (re-click deselects the visual while `_selected` stays set — the state desyncs); plain
  (non-toggle) buttons (lose the persistent "which god am I petitioning" highlight).
- **`_build_gods()` clears children with synchronous `free()`, not `queue_free()`** → offering a
  prayer fires `_render_response → _build_gods` in the same frame the panel may already be rebuilding
  (the test offers two prayers back-to-back), and `queue_free` defers to end-of-frame, stacking
  duplicate god buttons — the same B4/C2/D2 double-refresh bug the other panels hit. *Alt (rejected):*
  `queue_free` (idiomatic for general teardown, but wrong for an immediately-rebuilt list).
- **The headless panel test uses `load("res://…")`, not `preload`, and registers as a coroutine**
  (`await _test_prayer_panel()` in `_init`) → under `-s tests/run_tests.gd`, `preload` resolves at
  parse time *before* autoloads register, so a scene whose script references autoloads via bareword
  breaks; and a test that `await`s `process_frame` is a coroutine that must be awaited at its call
  site or it silently no-ops. *Alts (rejected):* `preload` (parse-time autoload crash); calling the
  async test without `await` (assertions never run).

**End-of-plan review triage (rejected items, with rationale):**
- **BBCode escaping of `message`/`reason` before they reach the `RichTextLabel`** is deferred, not
  added now. Every current source of those strings (`PrayerService._compose_message`, the validator
  reasons) is internal and bracket-free, so there is no live injection surface; escaping today would
  be dead defensive code. *Alt (rejected, tracked):* escape `[`/`]` at render time — revisit when the
  real LLM sidecar can return free-form `message` text that might contain BBCode-like markup.

### Implementation notes — live-world staging, debug overlay & living NPCs (post-Plan-F)

The world boots but reads as a void: a 2×-too-wide camera over two flat polygons, NPCs stacked on
top of each other with unreadable labels, a stale detective-era lead in the top bar, and agents that
deliberate but rarely *move* on screen. This pass makes the live world legible and gives developers a
window into what the agent-sim is actually doing each beat.

- **Lead reframed from the detective premise to the cult-summoning premise.** The top-bar lead read
  "Work out what happened in this room." — a holdover from the room-escape scaffold, actively
  misleading now that the game is an open-world race to stop a descending god (外神). Rewrote it to
  point the player at the Iron Cross Street (铁十字街) warehouse and the rite. *Alts (rejected):* drive
  the lead from a quest/objective system (no such system exists yet — premature); leave it and fix
  later (it is the single most prominent line of text on screen, so it sets the wrong frame for every
  playtest).
- **Camera zoom set to 2× on the player rig.** At 1× the 1280×720 viewport showed so much empty world
  that NPCs were thumbnail-sized and labels illegible. 2× frames the player and nearby agents at a
  readable size without hiding the active radius. *Alts (rejected):* move the camera farther back and
  scale up sprites (fights the art's native resolution); per-scene Camera2D limits (the world is not
  yet bounded — no meaningful limits to set).
- **NPC morning waypoints spread apart in `npcs.json`.** Four NPCs (voss, dalia, orin, pell) all spawned
  within a ~40px cluster because their morning waypoints were authored close together; labels and
  bodies overlapped into an unreadable smear. Pushed them onto distinct positions around the warehouse
  so each is individually selectable and readable. *Alts (rejected):* runtime jitter/spread at spawn
  (hides the authored positions and fights the schedule system that drives NPCs *back* to waypoints);
  collision-based separation (overkill for static spawn legibility).
- **Re-pinned voss in the agent-runtime idle test instead of reverting the waypoint data.** Spreading
  voss's morning waypoint toward the warehouse made him drift out of the test's tight `active_radius=50`
  across the pre-idle beats, so on the idle beat he correctly fell back to his schedule (moving) — and
  the "idle leaves agent in place" assertion failed. The product behavior is right; the test was
  coupled to the old waypoint. Fixed by re-pinning `voss.position = Vector2(400, 300)` immediately
  before the idle sub-case. *Alts (rejected):* revert the legibility change (trades a real, visible
  improvement for a hidden test coupling); widen `active_radius` (changes what the test exercises).

**Debug event-log overlay (`DebugLogPanel`, toggle F1):**
- **A single overlay that mirrors the entire EventBus, not a per-system inspector.** The EventBus is
  already the append-only spine every system writes to (agent actions, amendments, schema rejections,
  critic vetoes, overseer directives, player verbs, combat, summoning, and — once wired — sidecar
  proposals/errors). One overlay reading `EventBus.events()` shows the whole simulation in causal order
  for free. *Alts (rejected):* separate panels per subsystem (duplicates the bus's own categorization,
  N panels to keep in sync); a file/stdout log (invisible during a live playtest, which is exactly when
  you need to see why an NPC did nothing).
- **Colored by event type, newest-first, capped at the last 50.** Color lets the log scan at a glance
  (greens = committed actions, reds = rejections/vetoes, blue = player, etc.); newest-first puts the
  most recent beat at the top where the eye lands; 50 lines keeps layout cheap while the bus retains up
  to 2000. *Alts (rejected):* render all retained events (layout thrash, unreadable wall); oldest-first
  (forces a scroll to see what just happened).
- **A "Brain:" header line names the live `SidecarClient` subclass plus beat/clock.** The single most
  important debugging question for living NPCs is *which brain is serving proposals* — Mock, Ambient, or
  the real Http sidecar. Reading it off `SidecarBridge.client`'s script name surfaces that without a
  separate status UI. *Alts (rejected):* infer the brain from event contents (fragile, indirect); a
  separate status widget (more UI to place for one line of text).
- **Synchronous `free()` on refresh, not `queue_free()`.** `event_logged` can fire several times in one
  frame; a deferred free would let a second refresh in the same frame stack duplicate child labels onto
  not-yet-reaped ones. Freeing synchronously before rebuild guarantees one label per shown event. *Alt
  (rejected):* `queue_free()` (same-frame double-refresh duplicate stacking — the exact bug this avoids).
- **F1 chosen for the toggle.** F1 is unbound and conventionally "debug/help"; the other panel toggles
  (Tab/M/C/R/P) are taken by player-facing panels. *Alt (rejected):* a backtick/console-style key
  (already reserved for `toggle_console`).

**Living NPCs — the offline ambient brain (`AmbientSidecar`):**
- **A new default brain that goal-seeks, replacing the scripted `MockSidecar` as the boot default.**
  `MockSidecar` returns a short canned script then falls to `idle`, so with no LLM the district froze
  after a few beats — NPCs deliberated but stopped moving. `AmbientSidecar` instead emits a fresh
  `move_to` every beat toward a faction-appropriate goal, so the world stays in motion with zero API
  cost. *Alts (rejected):* extend `MockSidecar`'s script to be longer (still finite, still freezes,
  and authoring per-NPC scripts does not scale); drive ambient movement from the engine's schedule
  system alone (schedules pull NPCs *to* waypoints and hold — no continuous on-screen life, and it
  would bypass the sidecar seam the whole sim is built around).
- **`AmbientSidecar extends MockSidecar` (not `SidecarClient` directly) so prayers still adjudicate.**
  Prayer adjudication is ~50 lines of deterministic logic living on `MockSidecar`; subclassing inherits
  it for free, so the offline brain answers prayers correctly instead of regressing to the base
  "ignored". *Alt (rejected):* extend `SidecarClient` and duplicate or re-stub prayer logic (copy-paste
  of the exact thing the parent already does right; the base stub would silently break live prayers).
- **Cultists (邪教) path to the warehouse; civilians follow their schedule waypoint.** The story is a
  cult racing to summon a descending god (外神) at the Iron Cross (铁十字街) warehouse, so faction is the
  one signal that should bias movement: `faction` containing "cult" → head to `WAREHOUSE (420,360)`,
  everyone else → their `NpcDB.waypoint_for(actor, phase)`. This makes the central conflict legible on
  screen without any LLM. *Alts (rejected):* random wander for all (no readable story, cult looks
  identical to bystanders); hard-code each NPC's destination (does not generalize as the roster grows).
- **Deterministic per-beat hash scatter around the goal instead of true randomness.** Agents sharing a
  goal (e.g. several cultists → one warehouse) would stack into one unreadable blob. A hash of
  `actor|axis|beat` yields a stable offset in ~[-28,28]px: same agent+beat always lands the same spot
  (so tests are deterministic and a re-proposed beat is idempotent), yet the cluster spreads and
  re-scatters each new beat for visible life. *Alts (rejected):* `randf()` jitter (non-deterministic —
  breaks the "same beat = same action" test and makes replays diverge); fixed per-agent offsets (static
  once arrived — no ongoing motion).

**Environment art — the procedural Iron Cross streetscape (`LiveDistrict._build_streetscape`):**
- **Generate the street in code from `districts.json`, not from authored art or a hand-built scene.**
  No streetscape art assets exist, and the district shapes already live as polygons in `districts.json`.
  Drawing tinted region polygons + authored set-dressing (roads, warehouse, lamps) procedurally means
  the visual *is* the data — move a polygon and the art follows — matching the project's data-driven
  ethos. *Alts (rejected):* commission/generate raster street tiles (no pipeline for it, heavy, and it
  would drift out of sync with the collision polygons); lay the scene out by hand in the `.tscn` (freezes
  the geometry away from `districts.json`, the single source of truth the sim already reads).
- **Streetscape lives under one `Streetscape` Node2D, built first in `_ready()` so it renders behind
  actors.** Z-order in Godot 2D follows tree order; building the backdrop before the player/agents spawn
  guarantees NPCs and the player draw on top without per-node `z_index` bookkeeping. A single parent node
  also gives the test a stable seam to assert against (`Streetscape` exists, child count, warehouse
  marker). *Alts (rejected):* per-element `z_index` (scatters ordering across many nodes, easy to get
  wrong); add pieces straight onto the root (no clean handle for teardown or for the wiring test).
- **ASCII-only on-screen labels ("Iron Cross Street", "The Harbor", "Warehouse").** The bundled fallback
  font has no CJK glyphs, so Chinese place-names would render as tofu boxes (□□□). Labels stay ASCII for
  legibility; the Chinese canon (铁十字街 etc.) stays in code comments and this doc. *Alt (rejected):* ship
  a CJK font just for set-dressing labels (weight and licensing cost for decoration the player barely
  reads — revisit when localized UI is a real goal).
- **A `has_warehouse_marker()` seam on `LiveDistrict` for the wiring test.** The warehouse is the
  story's focal site; the test needs to confirm it actually rendered without scraping the node tree for a
  magic label. A tiny query method (true when a `"Warehouse"` Label exists) is a stable contract the test
  can hold even if the backdrop's internals are reshuffled. *Alt (rejected):* assert on the raw child
  hierarchy in the test (brittle — every set-dressing tweak would break an unrelated assertion).

**Real LLM wiring — the threaded HTTP brain (`HttpSidecar`) + sidecar `decide()`:**
- **`HttpSidecar extends AmbientSidecar`, so every failure path is a live goal-seeking move, never a
  freeze.** A cold cache, an in-flight request, an unreachable sidecar, or a malformed reply all fall
  through to `super.propose()` — the ambient brain — so the world keeps moving whether or not the LLM
  answers. *Alts (rejected):* extend `SidecarClient` and fall back to `idle` on any miss (the freeze we
  just fixed); block the beat until the HTTP reply lands (a 15s real-time beat cannot wait seconds on a
  network call — it would stall the whole game).
- **Background `Thread` with one-beat latency, not a synchronous call.** The LLM round-trip takes
  seconds; the beat is 15 real seconds and must not block. `propose()` returns *this* beat instantly
  from a per-agent cache (ambient-filled for any agent not yet heard from) and kicks off a worker thread
  whose reply is applied on the *next* beat. One beat of staleness is invisible at human pace and buys a
  non-blocking sim. *Alts (rejected):* synchronous HTTP in `propose()` (stalls the frame for seconds);
  Godot's async `HTTPRequest` node (needs a node in the tree + signal plumbing, and still must marshal
  back to the main thread — more moving parts than a single worker thread for one POST).
- **All engine state touched only on the main thread; the worker does pure HTTP+JSON behind a mutex.**
  The worker thread never reads the cache, the EventBus, or any node — it returns `{actions, error}`
  through a mutex-guarded buffer that the next `propose()` drains and applies on the main thread. This
  keeps Godot's non-thread-safe scene API off the worker and confines all races to one small buffer.
  *Alt (rejected):* let the worker write the cache / emit events directly (data races on the scene tree
  and the EventBus — exactly what Godot's threading rules forbid).
- **Opt-in via the `TINGEN_SIDECAR_URL` env var; unset = pure offline ambient.** A bare checkout, CI, and
  the test suite must run with no network and no API key, so the real brain only engages when a URL is
  explicitly provided. Same pattern the asset-gen tooling uses for its token. *Alt (rejected):* default
  to `localhost:8777` and probe it (every offline boot eats a connection-refused round-trip, and tests
  would flake against whatever happens to be on that port).
- **The API key stays quarantined in the Python sidecar; Godot only ever sends snapshots.** The engine
  posts perception JSON and receives validated actions — it never holds `ANTHROPIC_API_KEY`. The sidecar
  reads the key from env/`--env-file`, uses it only to authenticate the Anthropic call, and logs
  *presence* not value. Keeps secrets out of the game binary and its logs entirely. *Alt (rejected):*
  call Anthropic from GDScript (puts the key in the shipped engine and its EventBus/logs — a secret-
  leak surface; also duplicates the prompt/validation logic the sidecar already owns).
- **Every action re-validated against the shared schema on the engine side too, even though the sidecar
  validates.** `apply_reply` runs `ActionSchema.validate` on each returned action before caching it;
  invalid ones are dropped and surfaced as `sidecar_error` in the debug overlay. The engine never trusts
  the brain — defense in depth against a buggy/old sidecar or a future non-Claude brain. *Alt (rejected):*
  trust the sidecar's own validation (one schema drift or a swapped brain and bad actions reach the
  runtime; the cost of re-checking is a few `if`s).

### Implementation notes — cult→summoning coupling (post-Plan-F)

Playtest gap: cult NPCs (邪教) walk to the warehouse and "perform ritual steps", but nothing they do
touches the doomsday clock — only the player's sabotage/social verbs fed `SummoningPlan`, and
`perform_ritual_step` was memory-only flavor in `ActionCommit`. The countdown ticked on a pure timer,
so the cell felt inert: you couldn't watch *them* drive the descent. This pass wires the cult's own
rite into the summoning clock so gathering at the warehouse visibly quickens the end.

- **The rite bites the clock in exactly one place — `ActionCommit._perform_ritual_step` — gated on
  `faction == "cult"` AND standing within `RITE_RADIUS` of the warehouse.** Commit is the single seam
  where agents mutate the world, so that is where the coupling belongs; a cultist working the rite *on
  site* calls `SummoningPlan.advance_rite(1)`, anyone else (or the same cultist mid-street) gets the old
  flavor-only outcome. *Alts (rejected):* let the brain (`AmbientSidecar`/`HttpSidecar`) decrement the
  clock when it proposes the rite (the brain must never own world mutation — a buggy or hostile/LLM brain
  could then race the countdown arbitrarily, bypassing the critic+commit pipeline every other effect goes
  through); rely on the Critic's existing cultist-only veto and skip the commit-time guard (the Critic
  judges *proposals*, not committed reality — re-checking faction+position at commit keeps the effect
  honest no matter how the action arrived, the same defense-in-depth the schema re-validation uses).
- **A dedicated `SummoningPlan.advance_rite(beats)` that shares a refactored `_fire_climax_if_due()` with
  `tick_countdown()`.** Both the steady timer and the cult's hands must resolve the descent identically —
  clamp at zero, never go negative, fire `summoning_climax` exactly once — so the climax block was lifted
  into one helper both paths call. *Alts (rejected):* make the rite call `tick_countdown()` N times (emits
  `countdown_changed` N times for one beat of work — UI thrash — and re-reads "hasten by N" as "N separate
  ticks"); inline a second copy of the climax-fire block inside `advance_rite` (duplicate logic that would
  drift the day one path changes — exactly the bug the shared helper prevents).
- **`AmbientSidecar` proposes `perform_ritual_step` only once a cultist is already within
  `ActionCommit.RITE_RADIUS`; farther cultists keep `move_to`-ing toward the warehouse.** The brain reuses
  the *same* radius constant the commit step enforces, so it never proposes a rite that commit would
  quietly treat as flavor — you watch them converge, then watch them work. *Alts (rejected):* let every
  cultist propose the rite from anywhere and let commit no-op the off-site ones (the debug log fills with
  rites that do nothing, and on screen a cultist "performs" alone in the street — misleading); give
  `AmbientSidecar` its own radius constant (two numbers that must be kept in lockstep — drift risk, so the
  threshold lives once on `ActionCommit` and the brain references it).
- **`ritual_advanced` is emitted for the debug overlay but deliberately NOT added to
  `CultProgressPanel.PUBLIC_TYPES`.** The readiness bar already reflects the rite (it reads
  `closeness_ratio()`), so the player *feels* the descent quicken without the panel ever printing a literal
  "the cult advanced the ritual" line — surfacing that would leak the secret cult moves the panel's
  default-deny allow-list exists to hide. *Alts (rejected):* add `ritual_advanced` to `PUBLIC_TYPES` so the
  panel lists it (breaks the secrecy design — the panel shows only the player's own deeds and public
  fallout); emit nothing at all (then a developer watching the F1 overlay can't see *why* the countdown
  suddenly leapt — the event is the only causal breadcrumb for an otherwise hidden mechanic).
- **Balance: the steady tick removes one beat; each cultist working the rite removes one more, on top.**
  A lone straggler barely moves a 40-beat countdown, but a cell of three at the warehouse burns it in ~10
  beats instead of 40 — so gathering the faithful is visibly the dominant driver, while the player's
  sabotage/social interference (which adds setback beats back) still reads as rewinding the clock. *Alts
  (rejected):* a larger per-rite jump (the countdown craters the instant two cultists arrive — no window to
  react); scale the jump by remaining ingredients or impede (extra coupling to tune a number the player only
  ever reads as "how fast is the bar moving" — premature, and the ingredient count already gates *strength*
  at the climax, not *speed*).

### Implementation notes — player interference wiring (post-Plan-F)

Playtest gap: `PlayerActions.sabotage`/`social_influence` were fully tested verbs that fed `SummoningPlan`,
but *nothing in the running game called them* — no interactable, no dialogue option, no console command.
The cult could now drive the doomsday clock (see the coupling pass above), yet the player could only
*watch*: the two counter-moves that decide the climax were unreachable. This pass builds the three reachable
controls — a warehouse sabotage point, an Orin persuade line, and dev-console commands — all funnelling into
the same two verbs, so the summoning's outcome becomes player-determined instead of sim-decided.

- **All three controls route through the existing `PlayerActions` verbs; no control re-implements the
  effect.** Sabotage strips an ingredient and adds impede in exactly one place, turning a waverer flips
  faction in exactly one place — so the world reacts identically whether the player pressed E at the
  warehouse, chose a dialogue line, or typed a console command, and the overseer's "player involved" flag
  lifts the same way for all three. *Alts (rejected):* let each control mutate `SummoningPlan` directly
  (three copies of the impede/event/setback logic that would drift, and three ways to forget to mark the
  player involved); add a fourth "interference manager" indirection (premature — the verbs already are the
  single seam, an extra layer buys nothing for three call sites).
- **A new `PlayerActions.sabotage_any() -> String` for the warehouse point — a single "spoil the cache"
  verb that picks a held ingredient deterministically (sorted keys, first) and routes it through
  `sabotage()`.** The player walking up to the rite shouldn't have to *know* ingredient names; one button
  strips whatever is there and reports what fell, returning `""` (a clean no-op) once the cache is bare.
  Naming a specific item stays a *console* affordance, for surgical testing. *Alts (rejected):* hard-code a
  fixed item id on the interactable (breaks the moment that ingredient is exhausted — the button would
  silently fail while three others remain); make the world point open a pick-an-ingredient menu (UI weight
  for a panic-button interaction, and the console already covers the by-name case).
- **The persuade option gates on a *live agent's current faction* via a new `requires_agent_faction`
  dialogue gate, not on a clue/flag.** Orin's "[Persuade]" line is visible while `lamplighter_orin.faction
  == "cult"` and vanishes the instant he's turned — the option tracks the world's actual state, so it's
  self-consistent no matter which control did the turning (dialogue, console, or a future one). *Alts
  (rejected):* a `forbids_clue` gate keyed on a "turned" clue (`ClueDB.collect` requires the clue be
  pre-registered in clues.json, so it would surface on the Investigation Board — persuasion bookkeeping
  leaking into the detective's evidence wall); a one-shot consumed-option flag local to the dialogue (goes
  stale if Orin is turned by any other path, leaving a dead "persuade the ally" line on offer).
- **Orin gets his own `orin_waverer` tree and a non-empty `dialogue_id`; he was previously unreachable.**
  His npcs.json `dialogue_id` was `""`, so `NPC._can_talk()` was false and the player could never open a
  conversation — the persuade lever had no door. The tree carries the social_influence effect on two entry
  points (the blunt opener and after he explains the rite) so the turn is reachable however the player
  navigates. *Alts (rejected):* graft the persuade option onto an existing NPC's tree (Orin *is* the
  waverer — the fiction and the `scout_waverer` role gate both point at him); a bespoke persuade UI outside
  the dialogue system (the dialogue tree already does gated, effect-bearing options — reusing it is free).
- **The verb logic is TDD'd in the autoloads; the `Interactable._use()` branch and the LiveDistrict spawn
  are thin scene glue, covered by a `has_sabotage_point()` seam + smoke.** Which item strips, the impede
  bump, the events, the empty-cache no-op, the faction gate — all asserted at the `PlayerActions`/
  `DialogueManager` level where they're pure and reproducible. The 3-line `_use()` dispatch and the
  `_spawn_rite_sabotage_point()` placement are wiring of the same kind as `NPC.gd`'s untested
  `DialogueManager.start(...)` call. *Alts (rejected):* drive the full Area2D interactable (player body,
  E-press, `_unhandled_input`) in a headless test (physics/input simulation is brittle and tests Godot, not
  our logic); leave the placement entirely unverified (a typo'd spawn would ship a warehouse with no
  reachable sabotage point and no test would notice — the cheap `has_sabotage_point()` seam guards exactly
  that regression).

### Implementation notes — NPC verbs (talk_to / gather_item / attack, Yumina-modeled, post-Plan-F)

Three of the eleven NPC verbs were stubs: `attack`, `gather_item`, and `talk_to` only wrote a `remember(...)`
line and returned a flavor dict — they changed nothing in the world. The cult could already drive the
doomsday clock and the player could already sabotage it, but the *agents* couldn't fight, carry, or pass word.
This pass gives the three verbs real mechanics, each modeled on how the Yumina reference engine (诡秘 web sim)
implements its equivalent, then adapted to Tingen's two structural differences: agents are thin and the cast is
a **fixed, saved roster** (no spawn/despawn). All mechanics stay inside `ActionCommit` (the one place agents
mutate the world) and announce themselves on the `EventBus`, consistent with the existing `_perform_ritual_step`.

- **`attack` = flat deterministic damage that *downs* (incapacitates) a target, never deletes it.** Yumina's
  `cast_ability` → `damageEntity` does `hp = clamp(hp - max(0, amount - def), 0, max)` with no RNG/crit, and on
  zero HP **deletes the entity and rolls loot**. Tingen copies the flat, crit-free damage model (`ATTACK_DAMAGE
  = 34`, ~3 strikes to fell, proximity-gated at `ATTACK_RADIUS = 64` exactly like the rite is gated at
  `RITE_RADIUS`), but at zero HP sets `downed = true` instead of deleting. *Alts (rejected):* delete-on-death
  like Yumina (our roster is fixed and round-trips through save/load — deleting an agent would orphan every
  `get_agent(id)` reference, the dialogue/critic/overseer that name specific NPCs, and force respawn machinery
  the slice doesn't have); RNG or crit damage (non-determinism breaks the pure, reproducible verdict/commit
  contract the whole test suite leans on). Emits `agent_attacked` per connecting blow and `agent_downed` once,
  the moment a target falls — the felt public signals that combat happened.
- **`gather_item` fills the *agent's own* inventory and deliberately does NOT restock the cult's shared rite
  cache.** *(User decision: when offered "restock the shared cache" vs. "build a per-agent inventory," the user
  chose the per-agent store over my recommendation.)* Each `Agent` now carries a flat `id -> count` dict
  (`add_item` / `item_count`), mirroring Yumina, where gathering is per-actor fieldwork into a personal store and
  **no shared cache exists anywhere**. A test asserts a cultist gathering `ritual_salt` leaves
  `SummoningPlan.ingredients` untouched. *Alts (rejected):* route gathered goods into the cult's shared
  `SummoningPlan` cache (this was my initial recommendation — rejected by the user, and rightly: it would make
  every cultist's ambient gathering a silent **anti-sabotage faucet**, refilling exactly what the player worked
  to strip and quietly erasing the climax lever; Yumina also has no such cache to model); reuse the player-only
  `Inventory` autoload (that store is the *player's* — agents writing into it would conflate NPC fieldwork with
  the detective's satchel). Unknown item ids are a safe no-op; emits `item_gathered`.
- **`talk_to` spreads the speaker's freshest *real* observation to the listener as hearsay, with an
  anti-hallucination guard.** Yumina's `talk_to_npc` writes a turn-stamped rumor into the **listener's**
  `heardFromOthers` log (capped), and only if the speaker actually has something observed — it never invents
  knowledge. Tingen copies both halves: the speaker's most recent `short_memory` entry is captured *before*
  recording "talked to …" (so the act of talking can't become its own rumor), then appended to the listener's
  memory as `"heard from <name>: <observation>"`; a speaker with empty memory shares nothing. Proximity-gated at
  `TALK_RADIUS = 96` (roomier than a blade's reach — conversation carries farther than a strike). This is how
  knowledge — including the player's exposure — actually travels between agents now, not just flavor. *Alts
  (rejected):* inject the action's `topic` string as the rumor regardless of what the speaker knows (pure
  hallucination — agents would "know" things never observed, and exposure could spread from thin air, breaking
  the no-caught-by-chance invariant); keep it one-way memory-only (the stub state — knowledge never travels, so
  the cult can never react to what its own scouts saw). Emits `rumor_spread`.
- **A downed agent is coherently frozen on *both* the propose side and the move side.** `Critic.review` vetoes
  every verb except `idle` for a `downed` agent, as its first/overriding check (a felled body can't crawl to the
  rite or swing — this trumps faction/role/interestingness); and `Agent.tick_fallback` early-returns for a
  downed agent so the cheap scheduled walk can't drift the body around the district. *Alts (rejected):* guard
  only at commit time and let the brain keep proposing move/attack (the agent would visibly "try," and the log
  would fill with no-op attempts — incoherent for a downed body); freeze only the fallback walk but leave the
  Critic open (a live LLM brain could still get a move/attack approved and committed, walking the corpse). The
  two guards mirror each other so the felled state reads the same whether an agent is on the cheap scheduler or
  the LLM brain.
- **All three verbs keep mutation in `ActionCommit` + an `EventBus` emit; no split resolver/mutator.** Yumina
  separates a pure resolver from a mutator "bridge"; Tingen collapses both into `ActionCommit`, the established
  single seam (`_perform_ritual_step` already works this way). *Alts (rejected):* fork a pure-resolver/mutator
  split to mirror Yumina exactly (premature — `ActionCommit` is already the one tested mutation point; a split
  forks the established pattern and buys nothing for the slice); mutate from the sidecar/brain directly (breaks
  the validate → review → commit pipeline and the "only ActionCommit changes the world" invariant).

### Implementation notes — endgame endings (two-gate climax + win/lose screen)

The doomsday clock could already hit zero, but the climax was a placebo: `LiveDistrict._on_climax` ran a
`CombatEncounter` the player *always won*, printed a 4.5s thought banner, and the run just carried on — no
win/lose state, no screen, no restart. This pass makes the deadline mean something. *(User reframed the canon:
"if descend happens the entire city dies; the combat only happens after the descend is stopped — so there
could be a near-good ending where descend is stopped but player dies, and an all-good ending where the player
lives and descend is stopped.")* That gives three endings, and the design is built backward from them.

- **The climax is a *two-gate* resolver, not one fight.** Gate 1 asks "was the descent (降临) stopped?" by
  comparing the manifestation strength at the deadline to `STOP_THRESHOLD = 60`; strength above it means the
  outer god (外神) fully manifests and **the city dies with no fight at all** (`city_dies`), faithful to the
  *Lord of the Mysteries* (诡秘之主) canon that a completed manifestation consumes everything — there is no
  heroic last stand against a fully-descended god. Only if the descent is stopped (strength ≤ 60) does Gate 2
  run the `CombatEncounter` against the weakened *residual*: winning is `all_good` (descent stopped **and** you
  live), losing is `near_good` (descent stopped, but the backlash takes you). *Alts (rejected):* a single binary
  "was the cache stripped bare?" ending (throws away the canon distinction between stopping the rite and
  surviving it, and makes the combat system we just built decorative); a "cult neutralized" boolean trigger
  divorced from manifestation strength (double-counts player interference — strength already integrates every
  sabotage and the Orin turn, so a second signal would drift out of sync with the bar the player actually sees).
- **`STOP_THRESHOLD` lives on `EndGameResolver`, not `SummoningPlan`.** The threshold is an *ending-resolution*
  rule, so it sits with the resolver that uses it, keeping `SummoningPlan` purely about advancing the rite and
  computing strength. *Alts (rejected):* park the constant on `SummoningPlan` (couples the clock to the endgame's
  win condition — `SummoningPlan` shouldn't know endings exist); hard-code 60 inline at the comparison (a magic
  number the ending-bands test couldn't reference symbolically).
- **`CombatEncounter` retuned to `enemy_max_hp = 2.5 × strength`, `enemy_damage = 0.40 × strength`** (player
  unchanged: 100 HP, 18 basic / 30 occult every 3rd round). Only `_init` changed. The fight now only ever runs at
  residual strength ≤ 60, and the curve is tuned so the win/lose crossover sits at ~strength 49–50: the mid-50s
  are lethal and the low-40s survivable. That is deliberate — it makes **player interference the difference
  between the two stopped endings**, not just between stopping and not. The canonical lever table (verified by
  `_test_endgame_ending_bands`): no interference → strength 100 → `city_dies`; 1 sabotage → 77.5 → `city_dies`;
  2 sabotages → 55 → `near_good`; 2 sabotages + turning Orin → 43 → `all_good`; 3 sabotages → 32.5 → `all_good`.
  *Alts (rejected):* keep the old always-win tuning (the player-survival gate would be meaningless — every
  stopped run would be `all_good`); make the residual fight unwinnable so stopping the descent always costs your
  life (collapses `all_good` into `near_good` and erases the reward for going further than the bare minimum).
- **A pure static `EndGameResolver` carries all the branching; the `EndGame` autoload is a thin pause + overlay
  shell.** `EndGameResolver.resolve(strength)` is deterministic, dependency-free, and headless-testable on its
  own (no nodes, no tree); `EndGame` just connects the climax signal, calls the resolver, freezes the world, and
  draws the screen. *Alts (rejected):* have the `EndGame` autoload build and run the `CombatEncounter` directly
  (buries the three-way decision inside a CanvasLayer that needs a live tree to test — the logic we most want to
  pin down becomes the hardest to assert); a resolver that returns only a string outcome (the overlay also needs
  rounds/HP for its copy, so the resolver returns the full result dict and the screen reads from it).
- **`EndGame` is a global autoload with `process_mode = ALWAYS`, not a node inside `LiveDistrict`.** The climax,
  its freeze, and its win/lose screen must outlive any world swap and keep responding while the tree is paused
  (its Restart/Quit buttons) — exactly the `DevConsole` pattern. So the climax connection moved *out* of
  `LiveDistrict` (whose orphaned `_on_climax` and the old `combat_resolved` event are deleted) and into the
  autoload. *Alts (rejected):* keep the handler in `LiveDistrict` (dies on a scene reload — the very thing
  Restart does — and a paused tree would freeze its own buttons); a one-shot scene pushed at climax time (heavier
  than a persistent CanvasLayer that's idle until the one moment it's needed).
- **Restart explicitly resets the stateful singletons, then guard-reloads the scene.** Autoloads persist across
  `reload_current_scene()`, so a reload alone would carry a finished run's state into the "new" game; `restart()`
  resets `SummoningPlan` / `Overseer` / `OccultToolManager` / `Agents` / `Clock` / `EventBus` first, and the
  reload is guarded (`if current_scene != null`) so the headless harness — which has no current scene — can call
  it safely. *Alts (rejected):* reload the scene and trust it to clear state (autoloads survive the reload — the
  cult's stripped cache and the ticked clock would leak into the restart); drive restart through `SaveManager`
  (it round-trips a *saved* run, the opposite of a clean slate — restart wants defaults, not the last save).
- **The two panels' climax feed retargeted from the dead `combat_resolved` to the new `endgame` event.**
  `CultProgressPanel`'s public allow-list and `DebugLogPanel`'s color map both keyed the old event; both now key
  `endgame`, so the panels keep surfacing the climax under the event that actually fires. *Alts (rejected):*
  emit both events for back-compat (leaves a dead event name on the bus forever and two sources of truth for one
  moment); drop the panel wiring entirely (the climax would silently vanish from the public feed and the dev log).

### Implementation notes — map panel (real map + markers + live tracker)

**Real `tingen_map.png` base with an isolated map-anchor overlay layer; the streetscape is left as-is.**
The panel renders the printed city map and overlays live risk-tinted district regions, point markers, and a
live player dot — all expressed in map-image space (the canonical anchor). *Alts (rejected):* (a) unify
world/agent coords into map space now — that is sub-project 2's job; pulling it forward bloats the slice and
re-risks the streetscape for no panel-side benefit. (b) draw the existing abstract `polygon`s over the map —
they land on the wrong geography (Harbor over dry land, not the east river).

**Pure `MapProjection` (`class_name`, `RefCounted`) owns the coordinate math; `DistrictMap` is a thin view.**
Three spaces (world, map-image, canvas), two transforms (`world_to_map`, `image_to_canvas`) plus the inverse
`canvas_to_image`. *Alts (rejected):* keep the math inside `DistrictMap.gd` — its `@onready` scene refs make it
node-bound and awkward to test headlessly; the `EndGameResolver` precedent (pure seam under a thin shell) is the
house pattern.

**Aspect-preserving (letterbox) fit, one transform shared by the art and every overlay.** *Alts (rejected):*
stretch-to-fill the control — distorts the map and silently misaligns markers when the panel's aspect ≠ 1.416:1.

**Warehouse marker derived via `world_to_map(WAREHOUSE_WORLD)`; district markers at polygon centroids; no new
landmark data file.** *Alts (rejected):* a separate `landmarks.json` — YAGNI for v1; the warehouse is derivable
(and stays consistent with the player dot's coordinate system) and the district focal points come free from
their regions.

**Copy `tingen_map.png` into `res://assets/maps/`.** *Alts (rejected):* reference it in `asset-gen/ref/` —
outside the Godot project tree, so it cannot be imported/loaded as a texture.

**Additive `map_polygon` per district; the old abstract `polygon` and the `base_risk`/`risk_pressure` risk model
are untouched.** The new field re-anchors each region onto the real map (river east) without disturbing the
streetscape or changing any risk value.

**Live tracker range is one district until sub-project 2.** `AgentRuntime.player_position` is real and the dot
follows it, but only the Iron Cross region is currently walkable, so that is the dot's range for now.

### Implementation notes — to-scale city world

- **Single global uniform transform (`CITY_SCALE = 3.5`), map-image space canonical.**
  *Alts (rejected):* (a) per-district piecewise remaps — keeps independent authoring, but
  the tracker stays locally-correct-only and seams appear at district borders; (b) author
  the world in world units and derive the map — inverts today's canonical source (the map
  art) and makes the panel the derived artifact, more churn. The uniform transform makes
  the existing `world_to_map` tracker correct city-wide for free.

- **`CITY_SCALE = 3.5` (match today's feel).**
  *Alts (rejected):* 1.0 (map px = world units) feels cramped — a district would be ~170
  units, crossed in ~1.4 s; larger (e.g. 7×) makes the city a long boring walk. 3.5 keeps
  the current Iron Cross district size and a ~29 s full-city traversal.

- **Data-driven `city_layout.json` + pure `CityLayout` loader.**
  *Alts (rejected):* hardcode geometry in `LiveDistrict` (current approach) — not
  headless-testable, mixes data with scene wiring; a Godot `TileMap` — overkill for
  polygonal building masses and harder to derive a navmesh from.

- **Many small building-mass blocks (true buildings).**
  *Alts (rejected):* a few large placeholder blocks — faster to author but reads as
  abstract zones, not a city, and produces a coarse navmesh with unrealistic detours.
  (User explicitly requested true small blocks.)

- **Navmesh in this run, NPCs via `NavigationAgent2D`.**
  *Alts (rejected):* defer navmesh and keep straight-line steering — NPCs would walk
  through the new buildings, immediately visibly broken. (User explicitly approved building
  the navmesh now.)

- **Map underlay default ON, with a toggle; hidden later.**
  *Alts (rejected):* no underlay — tracing blind against a separate window is error-prone;
  underlay permanently on — defeats the goal of a self-contained vector world. Default ON
  for tracing, flip OFF once geometry is faithful (per user: "do the underlay approach
  first, then hide it").

- **Full collision (water + every block) + city-edge boundary.**
  *Alts (rejected):* visual-only / no collision — player walks through buildings and off
  the map; collision on blocks only — player escapes off the city edge into the void.

- **Modern source-geometry navmesh bake (`add_traversable_outline` / `add_obstruction_outline` + `bake_from_source_geometry_data`), nav-map cell size pinned to the 1.0 bake default.**
  *Alts (rejected):* the deprecated `make_polygons_from_outlines` — emits warnings and is
  slated for removal; leaving cell sizes unpinned — risks a silent "cell size mismatch"
  that drops the region from the map and yields empty paths (the build's #1 navmesh risk).

### Implementation notes — final-review remediation

- **Keep NPC waypoints walkable by nudging the data, guarded by a test.** Four scheduled
  waypoints (Dalia morning/afternoon, Orin early-morning, Pell morning) had been authored
  inside building blocks; an in-obstacle goal is unreachable on the navmesh, so the NPC's
  `NavigationAgent2D` returns no path and it straight-lines into a wall. Moved the cult
  logistics/victim beats south into the warehouse courtyard (where they thematically belong)
  and the lamplighter-scout north onto the open street, and added a data-integrity test that
  fails if any waypoint lands in a block/water or outside the outline.
  *Alts (rejected):* runtime goal-snapping via `NavigationServer2D.map_get_closest_point()`
  before the straight-line fallback — robust to bad data, but adds a per-NPC cost every frame
  to paper over authoring mistakes the test now catches at build time; widen `arrive_radius`
  — hides the symptom without fixing the unreachable goal.

- **Treat `_outline`'s polygon as read-only (`poly.duplicate()`), guarded by a purity test.**
  `PackedVector2Array` assignment shares its backing buffer, so the old `var pts := poly;
  pts.append(...)` mutated the very array the collision body (and any future shared navmesh)
  is built from. Harmless today (a duplicate closing vertex is a zero-length edge, and the
  navmesh re-parses a fresh layout), but a trap the moment the double-parse is deduped.
  *Alts (rejected):* leave it and rely on the fresh re-parse — keeps a latent footgun that
  would silently corrupt navmesh holes after an unrelated refactor.

- **Poll the nav map until a path appears, instead of one fixed post-update sleep.**
  `NavigationServer2D` commits region changes on a physics-frame boundary, so a single
  `await create_timer(0.05)` after `map_force_update` was racy under the headless loop
  (~1-in-4 cold runs returned an empty path). The navmesh tests now force-update and step
  real frames until a path returns (small budget, usually one iteration).
  *Alts (rejected):* a longer fixed sleep — slows every run and still races on a slow host;
  asserting only `get_polygon_count()` and dropping the routing assertion — loses the proof
  that NPCs can actually path around the blocks.

### Implementation notes — authored traversal scene (CityBlocks.tscn)

- **Hand-authored ~50-building scene baked into `scenes/CityBlocks.tscn` as plain editor
  nodes — no scripts, no `@tool`, no runtime construction.** The procedural builder
  (`LiveDistrict.gd`, which constructs the whole city in `_ready()`) produced a city that
  was too small in scale, too sparse (only a handful of boxes), and invisible/uneditable in
  the editor viewport. Per the user's pivot ("stop making it procedural, I want everything
  in the editor"), the new scene is an 8×7 grid (2400×1700 world units) with a central 2×3
  plaza skipped, yielding 50 `StaticBody2D` buildings — each a `Polygon2D` + matching
  `CollisionPolygon2D` — wrapped in a `Buildings` container, with a 4-wall perimeter
  (`Walls`), a `Ground` polygon, and a `Player` instance spawned in the plaza center
  (1200,850) so the spawn can never land inside a building. Everything is a real node in the
  scene tree: selectable, movable, and editable in the Godot editor. A guard test
  (`_test_city_blocks_scene`) asserts the Buildings container exists, ~50 bodies are present,
  every body has a ≥3-point collider, and a Player is included, so the authored structure
  can't silently regress.
  *Alts (rejected):* keep the procedural `LiveDistrict` build — rejected by the user, and
  it leaves nothing to edit in the viewport; make the builder `@tool` so it draws in-editor —
  still generated rather than authored, and bakes a brittle generator into edit-time;
  trace the city true-to-scale from `tingen_map.png` — explicitly discarded "for now" in
  favor of a simple walkable grid. Kept `LiveDistrict.tscn` untouched (still booted by
  `Main.tscn`) so the existing 539-assertion suite stays green; `CityBlocks.tscn` is
  standalone (open + F6) until the user asks to wire it into `Main.tscn`.
  > **Superseded (see next entry):** `LiveDistrict.tscn`/`.gd` were later fully retired and
  > `Main.tscn` now boots `CityBlocks.tscn`. The "kept untouched / standalone" clause above
  > no longer holds.

### Implementation notes — retire LiveDistrict, boot CityBlocks, migrate the demo parts

- **Made `CityBlocks.tscn` the real world: rewired `Main.tscn`'s `World` subtree to instance
  it, deleted the procedural `LiveDistrict` stack and the old `City.tscn`/`IntroMain.tscn`
  hubs, and moved the demo parts (two NPCs + the interior-room transition doors + the
  `DayNight` tint) into `CityBlocks.tscn`.** Once the authored scene replaced the procedural
  build there was no reason to keep two parallel worlds, so `LiveDistrict.tscn`,
  `src/LiveDistrict.gd` (+`.uid`), `scenes/City.tscn`, and `scenes/IntroMain.tscn` were
  removed outright. `GameController` is world-agnostic (it records `World.get_child(0)`'s
  `scene_file_path` and hot-swaps on `WorldState.transition_requested`), so the boot rewire
  was a one-line ext_resource/node-name change in `Main.tscn` — no controller code touched.
  The migrated demo parts were repositioned into the open central plaza of the 8×7 grid:
  `Orin` (lamplighter) and `Dalia` (fishwife) NPCs, a `Nighthawk` talk hotspot, and the two
  doors — `HQDoor` → `NighthawksHQ.tscn` and `UniversityDoor` → `UniversityArchive.tscn`,
  each carrying its `lead_on_use` line. The three interior scenes' return doors
  (`IntroRoom`, `NighthawksHQ`, `UniversityArchive`) were repointed `City.tscn` →
  `CityBlocks.tscn`.
  *Tests:* extended `_test_city_blocks_scene` with four demo-part guards (4-wall ring,
  ≥2 NPCs, an HQ door, an Archive door); removed the five `LiveDistrict`-coupled suite
  functions (19 assertions: spawn-per-agent, player-start, block/water counts, underlay
  camera bounds, navmesh bake, NPC pathfinding, outline-immutability) since their scene is
  gone — net suite **548 → 529 passed, 0 failed**. The three standalone interior wiring
  tests were repointed to load `CityBlocks.tscn` and now find the HQ/Archive doors there
  (13 / 19 / 11, all green). A throwaway boot smoke confirmed `Main.tscn` hot-loads
  `CityBlocks.tscn` with both NPCs and both interior doors live in the running tree.
  *Alts (rejected):* keep `LiveDistrict.tscn` as a second bootable world — leaves two
  divergent city scenes to maintain and a dead procedural builder; delete `CityLayout.gd`
  + `city_layout.json` too (they only ever fed `LiveDistrict`) — out of scope and the loader
  is a harmless, headless-testable seam, so it was left in place (now unused, not broken);
  leave the interior return doors pointing at the deleted `City.tscn` — would dangle and
  break the back-transition, so they were repointed.

### Implementation notes — restore the warehouse rite site into CityBlocks

- **Made the authored scene agree with the simulation's locked rite world-position instead
  of moving the anchor: kept `MapProjection.WAREHOUSE_MAP` → `(1802.5, 1302.0)`, removed the
  one building (`B_r5_c6`) whose collider buried that point, and authored an open maroon
  `Warehouse` courtyard marker (降临 / rite site) plus a `WarehouseCache` sabotage
  interactable sitting exactly on it.** When `LiveDistrict` was retired the warehouse stopped
  being drawn, but the whole simulation still pivots on that one world-point: cultists (教徒)
  converge on `AmbientSidecar.WAREHOUSE`, the rite only bites the summoning clock within
  `ActionCommit.RITE_RADIUS` (80 px) of `ActionCommit.SITES.iron_cross_warehouse`, and the
  player's cache sabotage is staged there — all three derive from
  `map_to_world(WAREHOUSE_MAP)`. In `CityBlocks.tscn` that exact point happened to fall inside
  building `B_r5_c6`'s collider, so the player could never physically walk to the rite. The
  fix keeps the sim untouched (no `MapProjection`/`ActionCommit`/`AmbientSidecar` edit) and
  makes the *scene* honest: the burying body was deleted, an open `Polygon2D` courtyard
  (no collider, inserted between `Ground` and `Buildings` so it draws above the ground but
  below the buildings and actors render on top) with an "Iron Cross Warehouse" label marks
  the site, and the `sabotage_cache` interactable is placed on the anchor so "spoil the
  summoning cache" is reachable on foot.
  *Tests:* extended `_test_city_blocks_scene` with four rite-site guards — a named `Warehouse`
  marker exists, a `sabotage_cache` interactable exists, it sits within `RITE_RADIUS` of
  `SITES.iron_cross_warehouse`, and the anchor point is clear of every building collider
  (`Geometry2D.is_point_in_polygon`, i.e. actually walkable). Suite **529 → 533 passed, 0
  failed**; the building-body count assertion still holds at 49 (was 50, one removed). A
  throwaway `Main.tscn` boot smoke ran clean (no errors/warnings).
  *Alts (rejected):* move `WAREHOUSE_MAP` to a free grid cell — would break
  `_test_coordinate_anchors_consistent` and silently shift the cultist convergence, the rite
  gate, and the sabotage stage all at once (the anchor is deliberately a single source of
  truth, so it stays put); make the warehouse an enter-able interior with a door (like the HQ
  / Archive rooms) — breaks the street-level sim, which runs cultist convergence and the
  proximity-gated rite/sabotage in `CityBlocks` world space, not in a sub-scene; leave the
  point buried and just nudge the sabotage interactable somewhere walkable — the interactable
  isn't proximity-gated so it would "work," but the rite anchor itself would stay unreachable,
  so cultists would mass on a spot the player can't contest, which is exactly the dead-feeling
  bug being fixed.
