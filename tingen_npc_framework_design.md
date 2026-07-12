# Neutral, Data-Driven NPC Framework — Design

**Status:** Design for review. Not yet implemented. Supersedes the character-coupled NPC logic currently
spread across `agent-sidecar/cognition/brain.py`, `tingen/src/Perception.gd`, `Critic.gd`,
`governance.py`, `ActionCommit.gd`, `AmbientSidecar.gd`. Rollout is **incremental and behavior-preserving**
(the cult behaves identically at each step; ~704 tests stay green).

**Why now.** Tingen is the test-bed for **Yumina** (the TS sibling). For that to mean anything, Tingen's
engine must be **neutral and generic over data** — the same property Yumina and the lab's **agent-sandbox**
already have. Today Tingen's engine "knows about the cult": it hardcodes the cult's goals, its rite script,
its offerings, its sites, and — the canonical sin — a cult-subjective sentence (`"…not one of the
faithful."`) inside the *generic* prompt builder. None of that can generalize to another NPC, and none of
it could be regenerated from data in Yumina.

---

## 1. The principle (agent-sandbox and Yumina, independently confirmed)

> **The engine is a generic interpreter over an array of NPC data records. It emits only OBJECTIVE
> perception — who/what is present, observable state, available actions — and never a verdict. Every
> interpretation (friend / threat / outsider; fight / greet / flee) lives in per-NPC DATA and is resolved
> by that NPC's own model.**

- **agent-sandbox**: one perception funnel (`describe_for`) renders `name + description + state +
  actions`; `Attack`'s preconditions check weapon/proximity/consciousness, **never** allegiance; a castle
  guard's hostility is a *sentence in its persona* (`"I am suspicious of anyone trying to enter…"`). Engine
  grep for `faction|enemy|hostile|outsider` → **zero**.
- **Yumina** (`/Yumina Master/yumina`): perception writes neutral observations (the player is *"the
  stranger"*); the NPC's **data** decides meaning via a `revealIfVariable` gate, a `knowsVariables`
  allowlist, persona prose, and `relationships[]`. Engine grep for character/faction string-equality in
  control flow → **zero**. *(Yumina today also carries `publicFaction/secretFaction` and a `hostile` flag;
  this design deliberately drops the faction-typed fields in favour of prose — see §2 — and a companion
  directive, `yumina-remove-faction-directive.md`, asks Yumina to do the same.)*

**The seam to replicate exactly: objective fact in the engine, interpretation in the data.** The cult
attacking a witness, or a shopkeeper greeting a customer, must both fall out of an NPC's *persona prose*
fed to one neutral engine — never from an `if faction == "cult"` branch, and never via a `faction` field
at all.

---

## 2. The NPC data record (mirrors Yumina's game-mode entity)

A character is a bag of fields in `data/npcs.json`. No engine code references any specific value.

```jsonc
{
  "id": "clerk_voss",
  "name": "Clerk Voss",
  "role": "leader",                    // a DESCRIPTIVE label only — never an `if role == …` branch

  // Identity, allegiance, group membership, AND how this character regards others all live in PROSE
  // here. There is NO `faction` field (see rationale below). The "undercover" nature is simply two
  // layers of prose — a public face in `description`, the truth in `secrets`:
  "description": "A fastidious shipping clerk with a cleric's calm, always squared ledgers, an ordinary face in the harbor crowd. In truth he leads the Iron Cross cell; he regards anyone who witnesses the work as a threat the faithful must remove, and he fears the lamplighters who hunt the cell.",
  "voice": "Measured and persuasive, never raises his voice; speaks of 'the work' only in euphemism.",
  "secrets": ["leads the Iron Cross cell", "means to pull the Descending One into Tingen", "has marked Pell as the sacrifice"],

  // intent: public cover-goal(s) always shown; secret goal(s) shown only once `revealed`
  "goals":       [ {"description": "Keep the cell hidden; pass as an ordinary clerk", "tier": "medium"} ],
  "secretGoals": [ {"description": "Summon the descending god and escape mortality", "tier": "long"} ],
  "revealIf":    { "variable": "cult_exposed", "equals": true },   // data gate: flips secrets/secretGoals into view

  // knowledge & secrecy
  "knowledge": ["the crypt rite beneath Saint Selena's", "the cell's members"],  // may state as fact
  "knowsVariables": ["cult_exposed"],   // world-state flags this NPC may reference; else redacted
  "concealsIdentity": true,             // generic per-agent flag: this NPC is hiding something, so the
                                        // secrecy invariant guards it. A property of the INDIVIDUAL, not a group.

  // combat / behavior knobs (data)
  "combat": { "hp": 100, "attack": 34 },

  // task that drives situational cues (replaces the hardcoded _cult_situation script)
  "task": { "ritual": "summoning_descent" },   // references data/rituals.json (site, ingredients, steps)

  // existing/auxiliary
  "tier": "full",                    // cognition budget (full | light)
  "quickPhrases": ["…"],             // converse fallbacks when the LLM is unavailable
  "schedule": { … }                  // phase routine (movement now owned by the data sim; see §6)
}
```

**No `faction` field — and why.** Identity, allegiance, group membership, and how a character regards
others are all carried in `description`/`voice`/`secrets` **prose**, exactly as agent-sandbox's castle
guard carries its suspicion in persona (`"I am suspicious of anyone trying to enter…"`). A categorical
`faction` string is **limiting and fragile**: it cannot express a wavering loyalty, a double agent, a
fresh convert, "trusts the harbor folk but fears the lamplighters," or any allegiance that shifts mid-run —
and it invites brittle `faction == "X"` branches throughout the engine. Prose captures all of that and the
LLM reads it directly. So the engine stores **no group label** and branches on **no allegiance**. Where a
*mechanical* hook is genuinely unavoidable it uses a **generic per-agent property** or **co-location**,
never a group identity: concealment → `concealsIdentity` (a boolean on the individual); "who feels a
nearby death" → everyone in the room (co-location); "who may work a rite" → the ritual's own data. A
standing directive to remove `faction` from **Yumina** for the same reasons lives in
`yumina-remove-faction-directive.md`.

**Field provenance.** `goals/secretGoals`, `revealIf`, `knowsVariables`, `quickPhrases` mirror Yumina's
`SceneBlueprintEntity` (`packages/sdk-core/src/scene-blueprint.ts`) — minus its `publicFaction/
secretFaction`, which this design drops (and the directive removes from Yumina). Disposition, which Yumina
keeps as a `relationships[]` list, is here folded into the `description` prose — the agent-sandbox route —
so there is no structured allegiance table to go stale.

**v1 vs later.** v1: the fields above. **Out of scope for v1** (note, don't build): Yumina's structured
`behavior` tree (Tingen decides via the LLM brain), `mood`, and a dynamic numeric relationship score
(static prose first; a score can be layered later without schema change).

---

## 3. The neutral engine contract (what each subsystem becomes)

| Subsystem | Today (character-coupled) | After (neutral, data-driven) |
|---|---|---|
| **Perception — others** | `_outsider_fact` emits `"…not one of the faithful."` (`brain.py`) | `nearby` renders only **objective** facts: `id, role, name, distance, downed` — **no faction**, no "outsider/faithful." The perceiver's own `description`/persona (its lens) is already in the prompt and does the interpreting. |
| **Goals** | `_goals_for` hardcodes 3 cult goal strings keyed on `faction=="cult"` (`Perception.gd`) | Forward `agent.goals` + (if `revealed`) `agent.secretGoals` + `adopted_goals`, straight from data. Delete `_goals_for`. |
| **Situation cue** | `_cult_situation` — a 38-line hardcoded gather→lay→invoke playbook with imperatives (`brain.py`) | Generic `_task_situation(perception)`: if the agent has a `task`, render **neutral facts** (holding X / at site S / S still needs Y) with **zero imperatives**. The "what to do" emerges from the LLM. |
| **Secrecy** | `_cult_secrecy` invariant keyed on `faction=="cult"`, `reveals_cult`, `REVEALING_VERBS={recruit,pray}` (`governance.py`, `brain.py`) | A generic **`secrecy`** invariant keyed on the per-agent boolean `concealsIdentity` (not a group) + a per-agent `revealingVerbs` list (data). Rename `cult_secrecy→secrecy`, `reveals_cult→reveals_membership`. |
| **Verbs / sites** | `SITES`/`crypt_altar` coords hardcoded; `perform_ritual_step` gated on `faction=="cult"`; `Critic` hardcodes `nighthawks/police/church` (`ActionCommit.gd`, `Critic.gd`) | Sites from data; `perform_ritual_step` eligibility = "the agent's own `task` references this ritual" (no faction; drop the ritual's `actor` field); `Critic` verb-eligibility from a data `verb → {roles}` map; exposure terms from data. |
| **Combat solidarity** | `Stimulus` fans a downing only to `"cult"`/`"ally"` (`Stimulus.gd`) | Fan a perceived event to **everyone co-located** (anyone in the room sees what happens in it). No group filter. |
| **Premise** | `"…Tingen…a cult races to summon a descending god"` literal, duplicated 3× | `world.setting_preamble` from campaign data; the prompt builder concatenates whatever it's given. |
| **Offline brain** | `AmbientSidecar` is an all-cult hardcode (`_is_cult`, `RITE_STEPS` litany) | Generic behavior from each agent's `task`/`goals` data; rite steps from the referenced ritual. |

**The objective-perception detail (the canonical fix).** There is no special "PRESENT: an outsider…" line
and no faction label. `nearby` is a plain objective list (`name`, `role`, where they are, what they're
doing). The perceiver's **own `description`/persona is its lens** — and it is already in the prompt, the way
agent-sandbox's guard always carries its suspicion in persona. So the cult reads "Klein Moretti, an
investigator, is here" and its *own prose* ("he regards anyone who witnesses the work as a threat the
faithful must remove") drives the reaction; a shopkeeper reads the same objective fact and its own prose
("a customer") drives a greeting. The engine authors no verdict and consults no group.

---

## 4. How this delivers BOTH goals at once

1. **The cult attacks a witness — via DATA, not a patch, never scripted.** Voss's `description` prose says
   he "regards anyone who witnesses the work as a threat the faithful must remove." The same neutral
   perception ("an investigator is here") → his *own persona prose* reads a witness as a threat → he attacks
   (verified earlier: an aggressive persona yields `attack` 8/8 on both haiku and sonnet). `brain.py` never
   learns the word "cult," and there is no `faction` to key on. This is the user's original "walk in on the
   rite → they attack" vision, delivered the right way.
2. **Tingen becomes a faithful Yumina test-bed** — same objective-perception seam, same prose-carries-
   character philosophy (and both drop `faction` together).
3. **A shopkeeper, a guard, a lamplighter** are each added as a pure data record whose `description` prose
   carries its own stance — zero engine change. That is the generalization test (see §7).

---

## 5. Migration — incremental, behavior-preserving

Each phase keeps the cult behaving **identically** (its new data says exactly what the engine used to
hardcode), keeps ~704 tests green, and adds new data-driven tests. The audit confirmed the data largely
**already exists** (`rituals.json` has `actor/ingredients/steps`; `npcs.json` has intent/secrets/knowledge)
— so most of this is **deletion + reading existing data**, not new architecture.

- **Phase A — Schema + data (additive, no behavior change).** Add the new fields to `Agent` (+ to_dict/
  from_dict round-trip) and fold each cult member's allegiance/disposition into its `description` prose
  + `secrets` + `goals/secretGoals`, so the data says exactly what the engine used to hardcode. Engine
  still hardcodes; data is just present and tested.
- **Phase B — Perception.** Replace `_goals_for` with `agent.goals` (data); replace `_cult_situation`
  with generic `_task_situation`; replace `_outsider_fact` with an objective `nearby` (no faction). Cult
  behaves the same (its persona prose now carries what the engine used to). New test: an NPC whose
  `description` says it removes witnesses attacks; one whose prose says it greets strangers greets.
- **Phase C — Secrecy + the `faction` removal.** Parameterize the `secrecy` invariant on `concealsIdentity`
  + per-agent `revealingVerbs` (data); rename `cult_secrecy→secrecy`, `reveals_cult→reveals_membership`.
  **Delete the `faction` field from `Agent`** and every `faction == …` branch (Critic, Stimulus,
  ActionCommit, AgentRegistry default, the player proxy); replace combat solidarity with co-location.
- **Phase D — Verbs / sites.** `perform_ritual_step` eligibility = the agent's `task` references this
  ritual (drop the ritual's `actor` field); `SITES` from data; `Critic` eligibility + exposure terms from
  data.
- **Phase E — Offline brain + premise + cleanup.** Generic `AmbientSidecar`; `setting_preamble` from data;
  delete the now-dead cult literals; grep the engine for `cult|rite|faithful|summon|faction` → only
  data/comments.

**Done-definition:** grep `agent-sidecar/cognition/` and `tingen/src/` for `"cult"` / `"faithful"` /
`faction` in control flow → **zero**. Adding an NPC is a pure data edit; there is no group variable to set.

---

## 6. Relationship to the placement-bug fix (already landed)

`NPC.gd` was just made a strict puppet of `agent.position` (the data sim owns movement; the body glides,
no navmesh/schedule). That is consistent with this framework's spirit (the engine renders data; it authors
no character-specific motion) and removes the stale per-NPC `schedule` *coordinates* as a movement source.
The `schedule` field stays in data for phase routines but no longer drives bound bodies.

---

## 7. Testing strategy

- **Behavior-preservation:** at each phase, the existing cult tests (~704) stay green — the cult's data
  reproduces its old hardcoded behavior.
- **Generalization (the payoff):** new tests prove the engine is neutral — e.g. a `merchant` NPC whose
  `description` says it welcomes strangers greets the player; an `enforcer` NPC whose `description` says it
  guards the work by force attacks a witness; **the same engine code, only the prose differs**. A test greps
  the engine source for `cult`/`faithful`/`faction` in control flow and asserts none remain.
- **Neutrality contract:** the perception builder, for any character, emits no value-laden words and no
  group label (extend the existing exact-string / banned-word neutrality tests).

---

## 8. Non-goals (v1)

- Yumina's structured `behavior` tree (Tingen decides via the LLM brain).
- A dynamic numeric relationship score (prose disposition first; a score is a later, additive layer).
- Any replacement *group* abstraction for `faction` (e.g. "teams", "tags"). The whole point is that prose
  + generic per-agent flags suffice; resist reintroducing a categorical under a new name.
- Re-authoring the world/scene-coordinate system or the portal graph (the placement fix already addressed
  the movement symptom).
- Changing the cult's *story* or tone — only moving its character from engine code into its data record.

---

## 9. Refinements landed + follow-ups (TODO)

Refinements after the A–E refactor (all green: 727 GDScript / 40 brain / 30 vectors / 8 converse):
- **Goals are goals.** Removed the `secret_goals` field + the public/secret goal split (agent-sandbox
  model): an agent's `goals` is a flat tiered list it fully knows; what it CONCEALS lives in `secrets`
  (still gated by `revealed`). The cult's aim ("Summon the descending god") is now just a long goal.
- **The engine is fully objective.** `_task_situation` states only facts (where you are, what you hold,
  what the site needs, where the site/cache are) — no command, no suggested verb. The agent chooses from
  facts + its goals. Site names come from the agent's `task` data, never the engine.
- **Secrecy is PURELY BEHAVIORAL.** Removed `conceals_identity`, the `secrecy` governance veto, and the
  whole witness/public/reveals-membership derivation. A character that wishes to stay hidden does so
  because its persona prose says to and the LLM judges accordingly — nothing hard-vetoes a "revealing"
  act, and a character always KNOWS its own `secrets` (they ride in its cognition, framed as concealed)
  and decides in character whether any slip. Recruit is likewise ungated (behavioral). The only
  governance left is physics/legality (`no_rite_without_site`). "Turning" a waverer is now a behavioral
  marker too — it adopts a defection goal (no flag).
- **Cleanup — faction/secrecy residue removed (post-refactor lint).** Deleted the inert `reveal_if` /
  `knows_variables` data hooks: no engine code read them and no `cult_exposed` flag exists, so they only
  advertised a guarantee the engine didn't enforce — secrecy is already enforced by the `/decide` secret
  non-forward + the player-gated exposure veto. Replaced the keyword-substring defection detector with a
  persisted typed marker: each `adopted_goals` entry is now `{text, kind}`, the `kind` decided ONCE at
  adoption (the brain may emit it on the `adopt_goal` action; otherwise it is classified at commit) and
  read thereafter — so a defection goal phrased outside any keyword list still turns a waverer, and a
  keyword-in-text non-defection no longer false-turns. Scrubbed the last comments that treated `faction`
  as a live mechanism (Critic, DialogueManager); the "no faction" notes stay. All green: 736 GDScript /
  39 brain / 26 vectors / 8 converse.

- **2026-07-02 buildout run (see `tingen_orchestrator_gm_design.md` for the GM half).** Landed in one
  autonomous pass: per-agent `vision_r` (agent-sandbox godot-ga-main port — room+radius nearby gate,
  perceiver-centric stimulus, same-room action guards); deterministic formation offsets (spawn
  stacking fixed at the data level); coordinate unification (CITY_SCALE 5.0, rite anchor at the real
  Warehouse, all placements validated against live scene colliders by test); decision-concurrency
  Phase 1 (client-owned stagger, continuation, `doing` facts, consume-once cache) + Coordinator v1
  (work-partition facts); GM panel (30s hybrid digests, `/narrate`); offline gather→deliver→rite
  ladder; 19-NPC roster + 20-building City.tscn + track-all RoomView; informed-failure facts.
  All via TDD; suite grew 736 → 1080.

**TODO / follow-ups:**
- **Model selection (TEMPORARY).** `ModelConfig` autoload + the `ModelPanel` debug UI (`9` to toggle) let
  you pick the model per character (GM/default + per-agent override); `HttpSidecar` stamps it on each
  `/decide`+`/converse` request. This is a stopgap — **replace it with a proper engine interface + a
  per-character node** once Tingen ships and we do the cognition refactor. (The emergent behavior needs a
  capable model; `default_model` is Sonnet so it shows.)
- **`Critic._is_exposing`** still hardcodes Tingen's authorities + exposure keywords. Acceptable today as
  *campaign-director* logic (like `CitySummoning`/`SummoningPlan`); move to a `data/world.json` campaign
  config if total engine neutrality is wanted. The `setting_preamble` data hook already exists for that.
- **No LLM "GM" yet.** Critic = coherence validator; Overseer = the deterministic director guardrail
  ("never exposed without the player"). A real narrator/GM agent would slot into the GM model row.
