# Tingen Agent-Sim — Vertical Slice Design Spec

**Date:** 2026-06-08
**Status:** Approved design, ready for implementation planning
**Engine:** Godot 4.6 (deterministic sim substrate) + external Python sidecar (LLM agents)
**Supersedes:** the detective-deduction framing of the prior occult specs — the **Gray-Fog
Hypothesis Board is cut**. The occult-tools and inventory specs survive, **demoted** to player
perception/action (see §8). See the GDD direction update (2026-06-08) and `DESIGN_DECISIONS.md`.

---

## 1. Vision (the pivot)

Tingen is **not a detective game with a fixed mystery to solve**. It is an **open-world,
real-time immersive simulation** of the city in which:

- **Every relevant NPC is an autonomous LLM agent** with its own intent, memory, and plans.
  Agents perceive and interact with each other and the world.
- A **cult faction genuinely intends to summon a descending evil god** and will *actually
  pursue and complete* that plan if no one stops it. Nothing is on rails.
- A **World-AI overseer** sits above the simulation: it receives the full event stream and can
  re-task an agent, cancel a plan, or coordinate several agents into a new beat — steering the
  emergent story so it stays dramatically interesting (e.g. the cult is never exposed/caught
  *by chance* — exposure is gated on the player's own involvement and information). The
  overseer also acts as a **critic that catches and kills boring or incoherent emergent
  threads**.
- **Combat is first-class**, the climax of confrontation — but it is one of several verbs in
  an immersive sim, not the only one.

This spec defines the **vertical slice**: the smallest end-to-end loop that proves the magic
is fun and affordable, before scaling to the full city.

### 1.1 Success criteria for the slice
1. A cult cell **autonomously** pursues a summoning in one district with **no scripted plot**.
2. The overseer demonstrably (a) prevents "caught by chance" and (b) can coordinate a group beat.
3. The critic catches at least one class of incoherent/illegal/boring proposed action.
4. The player can **discover → sabotage / turn / fight**, and accumulated **impede** scales the
   climax difficulty.
5. Runs at acceptable latency/cost: only **active** agents think; **fallback** behaviors hide
   deliberation; nothing stalls real-time play.
6. Headless tests pass with a **mocked** LLM (no live API needed in CI).

---

## 2. The slice premise

- **District:** Iron Cross Street (`iron_cross` in `districts.json`, highest corruption risk).
- **Target site:** the `iron_cross_warehouse` (reuses the existing `primary_ritual_site` slot
  candidate). The cell works toward a **minor summoning** there on a beat **countdown**.
- **Player:** a Seer-flavored (占卜家) investigator able to perceive (occult tools) and act
  (sabotage / social influence / combat).
- **Thread:** intent → autonomous action → player can interfere → consequence.

### 2.1 Cast (reuses existing roster + slots)
Drawn from existing NPC data and `WorldManager.SLOT_DEFS`; `npcs.json` is extended with
intents/relationships (it currently holds only `lamplighter_orin`, `fishwife_dalia`).

| Agent | Source id | Role in the cell | Intent sketch |
|-------|-----------|------------------|---------------|
| Clerk Voss | `clerk_voss` (decoy_courier candidate) | **Leader** | Found forbidden records; means to summon to escape mortality. Plans steps, recruits, hides the cell. |
| Dalia the Fishwife | `fishwife_dalia` (existing) | **Logistics acolyte** | Moves ritual ingredients through the harbor; runs decoy errands to mislead. |
| Orin the Lamplighter | `lamplighter_orin` (existing) | **Scout acolyte / waverer** | Lights lamps citywide = perfect scout, but a decent man having second thoughts — **socially turnable**. |
| Dockhand Pell | `dockhand_pell` (first_corrupted_civilian candidate) | **Vulnerable civilian** | Not a cultist; the cell's intended sacrifice/first corrupted victim. |

The `decoy_courier` slot (one of Voss/Dalia/Orin) ties in naturally: one agent runs decoy
errands the overseer can use to mislead a careless player.

---

## 3. Subsystems (each a unit with one job)

### (A) Sim substrate — Godot, deterministic
Evolves the existing autoloads; stays seeded and headless-testable.
- `Clock` drives **beats** (the deliberation cadence) on top of its existing day phases.
- `WorldManager` keeps world truth (slots, stage, pressures) + exposes **pacing hooks** the
  overseer reads/writes.
- `NpcDB` → **Agents**: each agent gets physical presence (position, navigation via the
  existing waypoint system), a `current_action`, and a **fallback behavior** (its old
  schedule) that runs while its LLM is deliberating so nothing ever stalls.
- **New `EventBus` (autoload):** an append-only log of every committed world event (agent
  action, player action, pressure change, beat tick). This is the overseer's single source of
  truth and the basis for deterministic replay/tests.

### (B) Agent runtime (per NPC)
An agent = `identity + intent/goals + short_memory + current_plan + perception`. On its beat
(or when an event targets it), the agent **proposes one action** chosen from a **constrained
action schema** — a typed verb set so every LLM output is validated and executable:

```
move_to(target)        talk_to(agent, topic)     gather_item(item_id)
perform_ritual_step(step)   hide()    flee(from)   attack(target)
recruit(agent)         report(to, info)          idle()
```

Cognition is **lean** (goals + recent memory + current plan). Full Generative-Agents memory
reflection/consolidation is **deferred**. The agent never mutates the world directly — it only
*proposes*; the substrate commits approved actions.

### (C) World-AI overseer + critic
Consumes the `EventBus`. Two responsibilities:
- **Director:** maintains dramatic pacing; issues **directives** to agents — retarget, cancel a
  plan, or coordinate a group beat — and enforces invariants such as *"the cell is not
  exposed/caught without the player's involvement."*
- **Critic ("catch & kill"):** validates each proposed action on three axes — (1) **legality**
  (valid schema + possible in current world state), (2) **coherence** (consistent with the
  agent's identity, memory, relationships), (3) **interestingness** (advances or complicates
  the thread). Verdict ∈ {approve, reroll, veto→fallback, amend}. This is the guardrail that
  kills boring/faulty simulation branches.

### (D) LLM orchestration — external Python sidecar
A local Python service (precedent: `asset-gen/`) that Godot talks to over **HTTP/stdio**.
- Python owns: prompt construction, Claude API calls, batching, caching, and **action-schema
  validation**. API keys live here, never in the engine (mirrors the `asset-gen` token rule).
- Godot sends **perception/state snapshots**; the sidecar returns **validated actions** (+
  overseer verdicts). **All nondeterminism is quarantined in the sidecar.**
- Saves store **outcomes, not prompts**. Tests run against a **mock sidecar** that returns
  scripted actions, so CI needs no live API.

### (E) Player perception + action (reuse + demote)
- **Occult tools survive as perception verbs** (divination / spirit-vision / dream → directional
  leads about agents/site). They no longer feed a deduction board.
- **Inventory survives** and gains teeth: **ritual ingredients are a real economy**, so
  **sabotage = removing ingredients** from the cell's supply.
- **New verbs:** `sabotage` (steal/destroy an ingredient or ritual fixture) and
  `social_influence` (turn the waverer → intel or defection).
- **Cut:** the Gray-Fog Hypothesis Board.

### (F) Combat — minimal but real
Real-time action combat sufficient for the climax: player (+ optionally one ally) vs.
cultists; HP, two attacks, one occult ability; **enemy strength scaled by accumulated
impede**. Party tactics / ability trees are deferred.

---

## 4. One beat — data flow

1. `Clock` ticks a beat. The substrate selects **active agents** (near the player or flagged
   relevant) and builds a **perception snapshot** for each.
2. Snapshots → sidecar → each active agent **proposes an action** (constrained schema).
3. **Overseer/critic** reviews the proposals (and may inject **directives**) → approve / reroll
   / veto→fallback / amend.
4. Approved actions return to Godot → **commit** to the world → append to `EventBus`. While an
   agent awaits its verdict, its **fallback behavior** runs.
5. The player perceives and acts in **real time** throughout. Player actions also append to the
   `EventBus` and can trigger **re-deliberation** of affected agents (e.g. a sabotage forces
   the leader to replan).

---

## 5. Impede → climax difficulty
Every successful interference (stolen/destroyed ingredient, turned acolyte, exposed scout)
lowers a hidden **impede/readiness** score. At the summoning beat, that score sets the
manifestation's strength: fewer ingredients/members → weaker descent, easier fight. Win = stop
it. Lose = the descent completes (slice "bad end"). The score is **never shown as a number** —
the player feels it through how the world reacts.

---

## 6. Determinism, save/load, tests

- **Substrate is seeded**; LLM nondeterminism is isolated in the sidecar.
- **Save/load:** world + agent state (positions, intents, memory summaries, plan, countdown,
  impede) persist via the existing `to_dict()/from_dict()` contract through `SaveManager`.
  Saves store **outcomes**, not prompts.
- **Headless tests (mock sidecar), extend `tingen/tests/run_tests.gd`:**
  1. **Schema validation** — a malformed/illegal proposed action is rejected.
  2. **Critic veto** — an incoherent action (e.g. a turned waverer suddenly performing a ritual
     step) is vetoed → agent falls back.
  3. **Overseer directive** — a directive cancels/retargets an agent's current plan.
  4. **No-chance-exposure invariant** — without player involvement, the cell is not auto-caught.
  5. **Sabotage → countdown** — removing an ingredient sets back the summoning beat.
  6. **Impede → difficulty** — higher impede yields a measurably weaker climax encounter.
  7. **Save/load round-trip** — world + agent state restores exactly.

---

## 7. Boundaries between units (interfaces)
- **Substrate ↔ Sidecar:** a single typed contract — `snapshot(agents) → [proposed_action]` and
  `commit(approved_action)`. The sidecar is replaceable (real LLM or mock) behind this.
- **Overseer ↔ Agents:** agents only *propose*; the overseer/critic *disposes*; the substrate
  *commits*. No agent writes world state directly.
- **Player verbs ↔ Substrate:** player actions are first-class `EventBus` events, identical in
  shape to agent actions, so the overseer reacts to the player the same way it reacts to agents.

---

## 8. Relationship to the prior specs
- **Inventory foundation spec** (`2026-06-08-inventory-system-design.md`): **still needed** —
  ingredients/economy power sabotage. Build largely as specced.
- **Occult tools + board spec** (`2026-06-06-...`): **occult tools survive** as perception
  verbs (the OOP `OccultTool` hierarchy + manager + `OccultRisk` still apply). **The Gray-Fog
  Hypothesis Board section is cut**; that file should be marked superseded on that point.

---

## 9. Out of scope (later specs / phases)
- Scaling to the **full city** (district streaming, large-N agent budgeting, offscreen
  abstraction beyond the slice).
- **Agent memory reflection/consolidation** (full Generative-Agents cognition).
- **Deep combat** (party-of-2 tactics, ability trees, enemy variety).
- The **broad ritual engine** (prayer / gray-fog transit / potion-brewing) — only the slice's
  summoning steps exist.
- Economy/shops, multiple concurrent plot threads, rumor propagation at scale.

---

## 10. Decision references
Logged in `DESIGN_DECISIONS.md` (2026-06-08 pivot): open-world real-time immersive sim;
per-NPC LLM agents + world-AI overseer/critic ("catch & kill"); vertical-slice-first; real-time
async deliberation with fallback behaviors; multi-path resolution with combat climax scaled by
impede; external Python sidecar orchestration; reuse existing roster/slots for the cell; Gray-Fog
Hypothesis Board cut; occult tools + inventory demoted to perception/action.
