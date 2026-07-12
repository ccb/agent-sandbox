# Tingen Combat — Research Findings & Candidate Designs

Status: research complete, **awaiting design pick** (2026-07-02). Brief: an overarching LLM layer
for INTENT + an underlying spontaneous layer for execution; comprehensive kit — movement skills,
spell casting, effect casting; GDD §16: "short, lethal, tactical, information-sensitive,
tight tactical real-time with optional pause."

## 1. What the research found

### 1.1 The video — "I Gave ChatGPT a Body" (Art of the Problem, May 2026)
A ~$80 bipedal robot ("GrowBot"): local RL policies run at **50 Hz** on the device ("the speed of
your unconscious motor reflexes"); a cloud LLM mind (~1–4 s latency) drives them **like a remote
control** — select policy + energy/speed parameters. Key transferable mechanisms:
- **Parameterized skills as the mind↔body API** (policy + intensity knobs, not raw motor commands).
- **LLM writes code** that composes skills + manual moves; **repeated behaviors compile locally**
  and replay at body speed with no LLM call.
- **Standing trigger rules** installed into memory ("play dead when I touch you") fire without
  fresh deliberation — reflexes authored by the mind, executed by the body.
- **Model tiering**: cheap fast model for frequent calls; smart model for rare "dream"
  consolidation passes over memory.
- **Its central failure is free for us**: the robot lacked a fast predictive world model
  ("it couldn't imagine the next second"), so anticipation failed. In Godot **the engine IS the
  world model** — a deterministic frame-rate layer can own anticipation outright.

### 1.2 Public repos (licenses checked)
| Repo | License | What we take |
|---|---|---|
| quiver-dev/template-beat-em-up | MIT | The exact two-layer FSM split: AI-state "brain" issues intents → separate frame-rate action FSM; `_decide_next_behavior()` hook = drop-in LLM seam; hurt-interrupt/resume protocol |
| limbonaut/limboai | MIT, active | Behavior trees + HSM; **blackboard as the intent injection point**; distance-band conditions, cooldown/pacing decorators, telegraphs as animation tasks |
| Pyxus/fray | MIT | Windup/active/recovery encoded as **animation-keyed hitbox bitmasks**; buffered-input manual-advance FSM (an AI can feed synthetic inputs; buffer pause = cancel windows) |
| uheartbeast/youtube-action-rpg | MIT | Minimal correct top-down kit: hitbox/hurtbox Area2Ds, Stats resource, knockback-as-velocity — copyable nearly verbatim |
| gdquest 2d-space-game | MIT | Combat **piloting as weighted steering blend** (pursue+face+separation+avoid each physics frame), fire gated on facing alignment |
| flareteam/flare-engine | GPL-3 (**patterns only, no code**) | Distance-band power lists, aggro/de-aggro ranges, two-stage attack activation (choose → fire on active frame), half-dead triggers |
| Unity open-project-1 | Apache-2 | Data-composed FSMs as assets → our Resources |

### 1.3 LLM-over-game-AI precedents
- **Halo 2 (the best-fit contract)**: above the 30 Hz behavior tree sit exactly two knobs —
  **orders** (where/what to fight) and **styles** (behavior masks: aggressive disables
  self-preservation, defensive disables charge). Danger reactions enter from BELOW as stimulus
  behaviors. This is precisely an LLM-sized interface.
- **F.E.A.R.**: goal injection + `ReplanRequired` interrupts (getting shot forces replan).
- **Generative Agents**: cheap "should I react?" check → replan from the interruption point.
- **Voyager / GrowBot**: code-as-skill; the slow layer authors executable behaviors.
- **Figure Helix / NVIDIA GR00T** (hard cadence numbers): System-2 at 7–10 Hz asynchronously
  refreshes a shared goal; System-1 at 120–200 Hz **never blocks on System-2**.
- **NVIDIA ACE shipped-game pattern**: cognition picks from a designer-defined action registry;
  the game's native combat code does the fighting.
- **SIMA 2 = documented anti-pattern**: the LLM on the critical control path.

### 1.4 Internal state (the seams and the breaks)
- Today: `attack {target}` = flat 34 dmg inside 64px, once per ~15–30 s beat — slow-motion
  pantomime vs the GDD. Player has **no attack at all** (only the headless climax auto-resolve).
- **Biggest break**: NPC bodies are strict puppets; no frame-rate combat authority exists anywhere.
- **LLM can't reason about health**: perception snapshots carry no hp/downed for self or peers.
- **Survives intact**: take_damage/downed, Critic downed-veto, EndGame player_downed wiring,
  vision-gated combat witnessing, per-room encounter scoping.
- **Yumina already built most of layer-2**: Ability-as-data (castTimeMs telegraph, cooldownMs,
  cost, range, targetType, effects[damage|heal|status|buff|teleport], damageMode
  instant|collision=dodgeable projectile), per-actor cooldown ledger, pure resolver; tier ladder
  A/AB/ABC; a two-LLM split (movement actor @800ms + A* stepper @250ms; event-triggered cast
  actor); **coach-authored learned reactions** (deterministic WHEN-player-casts-X→THEN-Y rules,
  150–800 ms human-feel delay, fire-count caps). Its clock-pause + 1v1 scoping do NOT map —
  Tingen combat must be a mode on agents inside a continuously running world.
- **Art reality**: only `bieber_monster` (+ player revolver/charm) has full combat strips →
  the natural vertical slice is **Bram Kell's reveal fight**.

## 2. The ability schema (common to all designs — covers the full kit)
One `Ability` resource type, data-driven, shared-shape with Yumina:
`{id, class: strike|projectile|movement|spell|effect, cast_time (telegraph; 0=instant),
cooldown, cost {stamina|spirituality}, range, aoe_radius, target_type self|enemy|point|area,
motion {dash|blink|charge dir/dist} , projectile {speed, collision-dodgeable}, effects[]
damage|heal|status(stun|slow|dot|silence)|buff|shield|zone{radius,duration,tick}, anim, vfx}`.
Movement skills = `class: movement` (dash/blink/charge with i-frame windows); spell casting =
cast_time + interruptible + telegraph event; effect casting = status/buff/zone effects with
stacking rules. Kits are per `combat_form` data (wraith_shadow ≠ bieber_monster ≠ descent_horror);
the player's revolver/charm/dodge use the same schema.

## 3. Candidate designs

### Design A — "Orders & Styles" (Halo-shaped, fully deterministic below the LLM)
- **L1 · Intent (existing ~15s beat, LLM)**: new verbs `engage {target, style}`,
  `disengage {via}`, `protect {agent}` ride the existing propose→Critic→commit pipeline;
  commit writes `Agent.combat_intent` (a published fact — no damage applied at this layer).
  Styles are masks: aggressive / cautious / defensive / desperate.
- **L2 · Tactical (deterministic, 5–10 Hz)**: per-combat_form behavior tree (LimboAI-style,
  or quiver's AI-FSM) reads intent + style + blackboard, classifies distance bands, and picks
  the next Ability from the kit by utility + cooldowns. Stimulus behaviors interject from below
  (hurt→stagger, telegraph-seen→dodge roll, hp<25%→style override if permitted).
- **L3 · Action (frame rate)**: action FSM per body — windup/active/recovery keyed on animation
  (Fray-style), hitbox/hurtbox Area2Ds (HeartBeast-style), steering-blend piloting (GDQuest),
  knockback/i-frames/poise. Bodies get a `combat` mode releasing them from strict-puppet;
  the executor writes results back through `take_damage`/EventBus so all existing wiring holds.
- LLM cadence unchanged; interrupts below; **zero LLM latency/cost during fights**; Tier A
  townsfolk = L2+L3 without any LLM (flee/panic trees).

### Design B — "Yumina port" (LLM actors in the loop)
Port Yumina's tiered actors: beat-level intent PLUS a cheap movement actor (~800 ms) and an
event-triggered cast actor for named characters; learned-reactions coach for bosses.
- Pros: maximal mid-fight aliveness; shared code/spec with the sibling project; the coach is
  genuinely novel ("it learns your revolver pattern").
- Cons: LLMs on a warm path (cost: N fighters × calls/second; latency spikes = frozen dodges —
  the SIMA anti-pattern risk); needs surgery to shed clock-pause + 1v1 assumptions; hard to test
  deterministically (our whole suite culture is deterministic).

### Design C — "Compiled reflexes" (GrowBot-shaped: the LLM authors rules, never acts in-loop)
Execution identical to A's L2+L3, but the LLM's combat output goes further than intent: it
**authors and edits standing reaction rules** (`WHEN telegraph(revolver) THEN dash_side (0.2s
delay)`, `WHEN ally_downed THEN style=desperate`) — per character, persisted as data, evaluated
deterministically in <1 frame. A post-fight "coach" pass (smart model, one call) consolidates
rules — the video's "dreams" + Yumina's learned reactions, generalized.
- Pros: personality-rich reflexes with zero in-fight LLM; deterministic, replayable, testable;
  scales to crowds; boss fights evolve BETWEEN encounters.
- Cons: needs a well-designed trigger vocabulary; less improvisational than B mid-fight.

## 4. Recommendation
**A as the chassis, C layered on top, B's ability schema as the shared data model** — and keep
B's event-triggered cast actor as an optional Tier-ABC add-on for the descent_horror setpiece
only (one boss, one warm LLM, bounded cost).
Rationale: matches every strong precedent (Halo orders/styles, Helix never-block, ACE
native-combat, GrowBot compiled reflexes), preserves Tingen's determinism-first test culture,
keeps the neutral-engine doctrine (intent and rules are published data; the engine states facts),
and the tier ladder maps 1:1 onto the roster.

**Enablers to build first (any design needs them):** hp/downed (+ peer `doing`+hp) in perception;
intent verbs in the action schema; combat mode on bodies; telegraph events
(`ability_cast_started` — also powers the GDD's divination dodge-cue).

**Vertical slice:** Bram Kell caught moving a corpse at night → bieber_monster reveal fight —
full art both sides (monster strips + player revolver/charm), one room, Tier AB.
