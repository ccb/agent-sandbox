# Tingen Combat — Implementation Plan (A+C hybrid)

Design basis: `tingen_combat_design_research.md` (approved: **A "Orders & Styles" chassis + C
"Compiled reflexes" + B's ability schema as shared data model**; Yumina's cast actor optional later
for the descent_horror setpiece only). Overnight autonomous run, 2026-07-02→03. Journal: `RUNLOG.md`.

## 0. Acceptance script (the approved playthrough)
"The Butcher of Iron Cross" (REVISED per user 2026-07-02 23:1x): player fires `revolver_shot`
(0.25s cast telegraph) at Kell → the telegraph reaches him ONLY if he can perceive it (same room +
within HIS vision_r — combat perception is the same vision-gated Stimulus channel, never global) →
his data-authored reflex dodges within 150–300ms (projectile collision-dodgeable; hit/miss is
binary — no locational damage; optional later: data-driven graze window, off by default) → damage
flips his COMBAT MODE only (fights back as the human butcher; body authority → combat executor;
world does NOT pause) → **transformation is the `assume_form` ABILITY in his kit** (class:
transform, long horrible telegraph) cast by HIS OWN layers (reflex `hp_below(50%) → cast
assume_form` or intent choice) — OR invoked by the GM/Director via the existing Overseer directive
seam when corruption crosses a loss-of-control threshold. NEVER an automatic engine reveal rule. →
next LLM beat emits ONE intent verb that re-masks the tactical layer → charm zone, poise break
staggers → downed (never deleted) with consequences, or player_downed → existing ending.
NO post-fight coach (Yumina-later idea; reflex rules are pre-authored data only tonight).
Cadences: reflex ≤300ms · tactical ~8Hz · intent ~15s. **The LLM is never on the frame path.**

## 1. Non-negotiable principles
- Neutral engine: intents/styles/reflex rules are published DATA facts; no identity branches;
  prompts state facts, never commands. Secrets never ride /decide.
- Determinism-first: the resolver + rule engine are pure functions covered by language-neutral
  vectors (M9); anything frame-dependent gets a headless harness. No RNG in damage.
- Existing wiring is load-bearing: take_damage/downed, Critic downed-veto, EndGame player_downed,
  vision-gated Stimulus, per-room scoping, formation offsets, stagger cohorts — build on, not around.
- World never pauses for combat (Yumina's COMBAT_PAUSE explicitly not ported).

## 2. Milestones (sequential; M7 assets parallel all night)

### M1 — Enablers
- Perception: snapshot + /decide gain self `hp/max_hp/downed` and nearby entries gain `hp_band`
  (healthy/hurt/critical/downed — banded, not exact, for peers) — brain.py renders both.
- Verbs: `engage {target, style}` (style ∈ aggressive|cautious|defensive|desperate),
  `disengage {via?}`, `protect {agent}` in action_schema; Critic coherence (downed can't engage;
  victim role restrictions unchanged); ActionCommit writes `Agent.combat_intent =
  {mode, target, style, via, set_at_beat}` — publishes a fact, applies no damage.
- Telegraphs: `ability_cast_started {caster, ability, target|dir, cast_time}` +
  `ability_cast_finished|interrupted` EventBus events; Stimulus fans vision-gated.
- Combat mode: `Agent.in_combat` + `combat_form` fields; `combat_started/combat_ended` events;
  NPC.gd puppet branch defers to a CombatExecutor child when in_combat (authority handoff seam).
- Ability schema (shared-shape with Yumina types.ts): data/abilities.json + per-form kits in
  data/combat_forms.json; AbilityDB autoload (defs, validation).

### M2 — Action layer (frame rate, deterministic core)
- `CombatResolver` (class, pure): apply_ability(caster_state, target_state, ability, ctx) →
  deltas {damage, statuses, knockback, poise}; cooldown ledger; status stacking rules
  (slow/stun/dot/shield); poise → stagger threshold; i-frame windows. Vector-tested (M9 seeds).
- `CombatExecutor` (node, per combat body): ability FSM windup→active→recovery (animation-keyed
  where strips exist, timer-keyed otherwise); steering (pursue/strafe/back-away blend);
  movement skills (dash/charge/blink) with i-frames + collision; projectile scene (speed,
  collision-dodgeable, owner, ability ref); zone scene (radius, duration, tick).
- Hitbox/hurtbox Area2Ds with owner/dedup/i-frame validation (HeartBeast pattern).
- Damage flows ONLY through Agent.take_damage; events through EventBus (existing panels/log work).

### M3 — Tactical layer + reflexes
- `TacticalBrain` (per executor, ~8Hz tick): reads combat_intent + style mask + kit + bands
  (melee/near/far/flee) + cooldowns → picks next ability or movement; default posture per
  combat_form when no intent yet.
- `ReflexRules` (data, per agent): triggers {telegraph(kind, at_me), hp_below(x), ally_downed,
  band_entered(b), cooldown_ready(a)} → actions {cast(a), dodge(dir), style(s), flee} with
  delay_ms (clamped 150–800) + max_fires; triggers only fire on events the agent PERCEIVED
  (vision-gated Stimulus channel); evaluated deterministically each frame; authored in
  npcs.json/combat_forms defaults; the LLM may add/edit via a data channel (C design), coach at M6.

### M4 — Intent integration
- brain.py: combat situation block (self hp, engaged-by, peers' hp_band + doing) + verb menu
  guidance (facts only); test_brain + vectors updated.
- AmbientSidecar ladder: attacked → engage attacker (aggressive if task threatened, else flee for
  civilians); offline demo remains fully functional.
- GM digest lines for combat; Coordinator ignores in_combat agents for work partition.
- GM/Director corruption path: when corruption crosses the loss-of-control threshold, the Director
  issues an `assume_form` cast directive through Overseer (transformation as GM's move).
- LIVE validation: scripted provocation, assert intent verbs arrive + tactical obeys style.

### M5 — Player combat
- Input: `attack` (LMB/space), `dash` (shift), `use_charm` (Q); aim = mouse direction.
- PlayerCombat node on Player.tscn using the SAME schema (revolver_shot ammo-costed,
  dash i-frames, paper_charm zone); HUD: hp hearts, ammo, cooldown pips; hurt/death anims exist.
- Player damage keeps flowing through the proxy Agent (EndGame untouched).

### M6 — Kell slice (NO coach — cut per user)
- Night trigger: Kell's late-night schedule gains a corpse-moving waypoint; witnessing it (vision)
  or damaging him flips combat MODE (human-form fight: cleaver, shove).
- Transformation = `assume_form` ability in his kit, cast by his reflex/intent layers — or forced
  by a GM/Director directive on corruption loss-of-control (Overseer.issue_directive seam).
  Form swap applies bieber_monster sprite + kit as the ability's transform effect resolves.
- Consequences: clue `bram_kell_revealed`, attention/panic pressure, witness facts, GM line.
- Acceptance = §0 script, executed by the headless sim harness + a live run.

### M7 — Assets (parallel track, image-2, ≤$100 total logged)
Anim strips (match existing 8-frame side-strip format, style-anchor = existing bieber strips):
cultist_robed attack/hurt/death; wraith_shadow attack/hurt/death (for later fights — not slice
blockers). VFX sprites/flipbooks: muzzle flash, bullet tracer, charm glyph + zone ring, dash
afterimage, hit spark, ichor splatter, stagger stars, status icons (slow/stun/dot/shield).
Alpha-verified, contact sheets, copied under tingen/assets/fx|anim.

### M8 — Review-re-edit loop (every milestone)
suites → code-review agent (diff vs THIS plan + neutrality/determinism principles) → headless
combat-sim agent (harness asserts: fight ends 20–90s vs GDD "short lethal"; telegraphs precede all
damage; dodge-with-i-frames avoids a scripted shot; reflex delay within clamp; poise break
interrupts; world clock advanced during fight) → fix criticals → checkpoint commit → RUNLOG entry.

### M9 — Back-port spec (Yumina parity deliverable)
`agent-sidecar/cognition/COMBAT_SPEC.md` + `combat_test_vectors.json`: resolver vectors
(damage/cooldown/status stacking/poise/i-frames), reflex rule-engine vectors, intent contract
(orders/styles), telegraph event names, ability schema field parity table vs Yumina types.ts —
"both implementations MUST pass" per the cognition SPEC pattern. GDScript vector runner in suite.

## 3. Fight-harness design (the self-review core)
tests/combat_sim.gd (SceneTree, offline): stages Kell + player-bot (scripted ability caster with
optional perfect-dodger policy) in one room; runs N simulated frames (fixed dt, physics stepped);
prints per-second combat log + final assertions (§M8 list). Deterministic seed = reflex/tactical
purity ⇒ repeatable. Used by playtest agents every milestone.

## 4. Budgets & logging
OpenAI (assets) + Anthropic (live checks, coach tests) combined ≤$100; every spend logged in
RUNLOG.md. Checkpoint commit per milestone (no push).
