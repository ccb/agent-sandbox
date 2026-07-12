# Combat Spec (language-neutral)

**Status:** v1 — the M9 back-port contract for the Tingen combat engine (GDScript, shipped) and
the eventual Yumina port (TypeScript, `packages/engine/src/combat/`).

This spec defines the deterministic combat stack from the design's **A "Orders & Styles" chassis +
C "Compiled reflexes" + B's shared ability schema**. Every rule in §§1–5 is a pure function of its
inputs, so the **same `combat_test_vectors.json` fixtures must pass in both the GDScript
implementation (Tingen: `CombatResolver.gd` / `ReflexRules.gd` / `TacticalBrain.gd`) and the
TypeScript implementation (Yumina, later).** When the two diverge, the fixtures are the arbiter.
Expected values in the fixtures are **machine-generated against the GDScript reference**
(`tingen/tests/dump_combat_vectors.gd`) — never hand-computed, never hand-edited.

Division of labor: Tingen owns the reference implementation and the vectors (now); Yumina adopts
the contract on top of its existing `combat/types.ts` catalog (§2 maps the fields). The cognition
layer (`SPEC.md` beside this file) is the same pattern one level up.

**The non-negotiables this spec encodes** (combat plan §1):
- The LLM is **never on the frame path**. Cadences: reflex ≤ 300 ms · tactical ~8 Hz · intent ~15 s.
- **No RNG** anywhere in combat resolution. Hit/miss is geometry; damage is authored numbers.
- The world **never pauses** for combat.
- Damage flows only through the engine's one damage pipe (`Agent.take_damage` in Tingen); a downed
  body is **never deleted**.
- Telegraphs precede all damage, and combat perception is the same vision-gated channel as every
  other stimulus — never global.

---

## 1. The layer stack

| layer | cadence | pure core (vector surface) | engine shell (not vectored) |
|---|---|---|---|
| L1 intent | ~15 s (LLM beat) | verb/style vocabulary + `combat_intent` fact shape | ActionCommit, Critic legality |
| L2 tactical | ~8 Hz | `bands_for` / `band_of` / `choose` (style masks) | steering, protect/disengage loops |
| L3 reflex | per frame, reactions fire 150–800 ms | `evaluate(rules, event, self, now, fired)` | scheduling, perceiver gate, dodge motion |
| L4 resolver | frame rate | `apply_ability` / `apply_status` / `tick_statuses` / ledger | executor FSM, projectiles, zones, events |

### 1.1 Intent layer — orders & styles (the LLM's only handle on combat)

The LLM emits **one intent verb per beat**; committing it **publishes a fact and applies no
damage**. The fact is `agent.combat_intent`:

```
combat_intent {
  mode:        "engage" | "disengage" | "protect"
  target?:     string      # engage: who to fight
  via?:        string      # disengage: optional named exit (a navigable site)
  agent?:      string      # protect: the ward
  style:       "aggressive" | "cautious" | "defensive" | "desperate"   # engage only
  set_at_beat: int
}
```

Verbs (wire args in the action schema):
- **`engage {target, style?}`** — commit to fighting `target`. `style` is OPTIONAL and validated at
  commit: an unknown or absent style commits as the default **`aggressive`** (never rejected — the
  tactical layer must never read junk). A valid engage also **enters combat mode** (emits
  `combat_started`). Constants: `ENGAGE_STYLES`, `DEFAULT_ENGAGE_STYLE` (pinned in the fixtures).
- **`disengage {via?}`** — commit to breaking off; **exits combat mode** (emits `combat_ended`).
  `via` names a navigable site; resolution to coordinates is engine-side and only within the
  agent's own room (cross-room coordinates are wrong-space).
- **`protect {agent}`** — a published stance, not an act; the tactical layer holds a guard post.
- **`cast_ability {ability}`** — the **GM/Director seam** (corruption loss-of-control transform,
  Overseer directives). Deliberately **NOT on the LLM's /decide menu**; a Critic vetoes it from a
  proposal unless the agent is already fighting. Timing refusals (busy/stunned) park the cast for
  the executor's retry; real refusals (unknown/cooldown/silenced/downed) drop it.

Semantics of "orders + styles": the **mode** is the order (who/whether to fight); the **style** is
a *mask over the tactical layer* (§1.2), not a behavior script. One selection function consumes the
mask; there is no per-style branching. Committing any **non-combat** verb clears a standing
`combat_intent` (the stance is only as durable as the LLM keeps choosing it); the combat verbs
manage the field themselves.

Style precedence when the tactical layer picks a mask (pinned):
**intent's validated `style` > a reflex `style` override > the combat form's authored
`default_style` > `aggressive`.**

Mode precedence per tactical tick (pinned): **a reflex `flee` latch OR an empty kit → disengage**
(civilians run, they don't spar) **> the standing intent's mode > default `engage`** (no intent yet
→ fight whoever last damaged you — the default posture).

### 1.2 Tactical layer — bands & style masks (~8 Hz)

Reads **published facts only** (intent, kit, cooldown ledger, own hp, statuses, distance); acts
only through `try_cast` + steering directives. Pure statics, all vector-pinned:

**Band derivation is DATA-driven** — no per-form numbers in code:

```
bands_for(kit_defs) -> {melee, near}
  melee = max range over kit abilities with class == "strike"     (0 -> DEFAULT_MELEE_BAND 48)
  near  = max range over kit abilities with class == "projectile"
  if near <= melee: near = max(melee * 2, DEFAULT_NEAR_BAND 160)

band_of(dist, bands) -> "melee" | "near" | "far"     # inclusive upper edges: dist <= melee -> melee; dist <= near -> near
```

**Style masks are data** (the `STYLES` table, pinned verbatim in the fixtures' constants):

| style | band | class_pref | rank | retreat_hp | counter_only | reckless |
|---|---|---|---|---|---|---|
| aggressive | melee | strike, movement, projectile, spell, effect | damage | 0 | no | no |
| cautious | near | projectile, spell, effect, strike, movement | damage | 1/3 | no | no |
| defensive | hold | strike, projectile, spell, effect, movement | damage | 0 | **yes** | no |
| desperate | melee | *(empty — anything)* | cooldown | 0 | no | **yes** |

**The one selector** `choose(view, style) -> {cast, steer}` with
`view = {kit, dist, ledger, now_ms, hp_frac, recent_hit, bands, current_form}`:

- **Ability selection** — deterministic lexicographic ranking by
  `(class_pref index, rank score, ability id)` ascending, where `rank score` is the authored
  `cooldown` when `rank == "cooldown"` (spam the fastest) else `-Σ damage-effect amounts` (biggest
  hit first). A class not in `class_pref` ranks after all listed classes (index = list length; the
  empty desperate list ranks everything equally at 0). Ties fall to **ascending ability id** —
  never dict/iteration order, never RNG.
- **Castability gates** (in ranking, pinned): an ability on cooldown is skipped
  (`ledger_ready`, §1.4); a **`transform`-class ability is NEVER a tactical pick** (plan §0 — the
  monster reveal belongs to authored reflex rows, the LLM's own choice, or a GM directive; the
  deterministic layer must not decide it); a `target_type: "self"` ability is castable at any
  distance; a `movement`-class ability with **no effects** is pure repositioning — steering's job,
  never a cast; everything else requires `dist <= range`.
- **`counter_only`** (defensive): cast only when `recent_hit` is true (the executor supplies
  "was hit / witnessed a hit within `COUNTER_WINDOW_MS` 2000"). No recent hit → no cast.
- **Steering** (`_band_move`, pinned by the choose vectors): if `retreat_hp > 0 and
  hp_frac <= retreat_hp` → `{kind: back_away}` overriding everything. Else by the mask's band —
  `melee`: beyond the band pursue to it (`{kind: pursue, stop_at: melee}`); inside it strafe, or
  keep pursuing to 0 when `reckless`. `near`: inside melee back away; beyond near pursue to near;
  in the ring strafe. `hold`: `{kind: hold}`.
- An **unknown style degrades to `aggressive`** (vector-pinned).

Engine-side (contract stated, not vectored): the instance tick loop (target resolution, per-target
`band_entered` transition events, protect-post geometry `protect_post(ward, threat, guard_r=48)` =
the point on the ward→threat line `min(guard_r, dist/2)` from the ward; disengage exits combat
after sustaining > 2× near-band distance from every combatant for 2000 ms; `TACTICAL_HZ` 8 /
`TICK_MS` 125 on the executor's accumulated clock, never wall time).

### 1.3 Reflex layer — compiled reflexes (data-authored, per frame)

```
rule row:  {when: <trigger>, do: <action>, delay_ms?: int, max_fires?: int}
evaluate(rules, event, self_state, now_ms, fired_counts)
  -> [ {do, delay_ms, fire_at_ms, rule_index} ]   # every due row, in rule order
```

**Trigger vocabulary** (`when.kind`; unknown kinds NEVER match — authoring drift stays inert):
- `telegraph {of?: ability class, ability?: id, at_me?: bool}` — a perceived `ability_cast_started`.
  Every present key must match (`of` against the event's `class`, `ability` against its id;
  `at_me: true` requires the event's `at_me`). A row without `at_me` matches telegraphs aimed
  anywhere.
- `hp_below {value}` — reads **self state** (`self_state.hp_frac`), so it fires on ANY evaluation
  including a bare frame tick (`event = {}`). **Strict `<`**: exactly at the threshold does not fire.
- `ally_downed` — matches on event kind alone.
- `band_entered {band}` — the fight crossed into melee/near/far vs the current target (the tactical
  layer emits transitions); matches only its band.
- `cooldown_ready {ability}` — a watched cooldown elapsed (the executor watches the **edge**
  not-ready→ready, only for abilities named by rules); matches only its ability.

**Action vocabulary** (`do.kind`, executed by the executor, never by the rule engine):
`cast {ability}` · `dodge {dir?: away|side}` · `style {style}` · `flee`.

**Clamps & caps (pinned):** `delay_ms` — the authored human-feel reaction time — is clamped to
**[150, 800]** ms (default **250** when absent); `fire_at_ms = now_ms + clamped delay`.
`max_fires` (absent or 0 = unlimited) is enforced against the **caller-owned**
`fired_counts {rule_index: fires}`; the caller increments when it **schedules** a reaction.
`evaluate` is pure: it never mutates rules, state, or counts, and returns EVERY due row.

**Perceiver gating (engine-side, load-bearing):** rules are evaluated **only against events the
agent PERCEIVED** — the shared vision gate (same room AND within the *viewer's* `vision_r`; an
event with no position falls back to room co-location). Reflexes react to what the agent can see,
never to the raw world log. A telegraph that can't be seen produces no dodge.

**Wire-format binding note:** JSON objects force string keys, so the fixtures carry
`fired_counts` as `{"0": 2}`; implementations key by **integer rule index** — the runner converts
at the boundary (see `fill_reflex` in `tingen/tests/run_combat_vectors.gd`).

### 1.4 Resolver — the deterministic core (pure, frame rate)

Operates on plain JSON-safe values only: state dicts, `[x, y]` arrays, **integer milliseconds**.

**Combat state** (normalization defaults pinned by the `normalization` vector):

```
state {
  hp:              float   (default 100)
  max_hp:          float   (default 100)
  statuses:        Status[] (default [])
  poise:           float   (default 0 — accumulated poise DAMAGE, not a pool that drains)
  i_frame_until_ms: int    (default 0)
}
Status {
  kind:          "slow" | "stun" | "dot" | "shield" | "frenzy" | "silence" | <unknown, inert>
  magnitude:     float    # slow: movement cut fraction; shield: absorb pool; frenzy: attack-speed mult; dot: damage per tick
  duration_ms:   int
  applied_at_ms: int
  tick_ms?:      int      # dot only (default DEFAULT_DOT_TICK_MS 500)
  last_tick_ms?: int      # dot bookkeeping (implementation-managed)
  stat?:         string   # frenzy-family bookkeeping from buff effects (e.g. "attack_speed")
  source?:       string   # optional attribution
}
```

**`apply_ability(caster, target, ability, ctx {now_ms, dir:[x,y]}) -> deltas`** applies **one**
ability hit. Order of operations (pinned):

1. **I-frame check first**: if `now_ms < target.i_frame_until_ms` (strict) return
   `{dodged: true}` — the WHOLE hit is zeroed: no damage, statuses, poise, knockback, zone report,
   or transform report. At exactly `i_frame_until_ms` the hit lands.
2. **Effects walk** (in authored order): `damage` amounts accumulate; `status` builds a Status —
   a bare name takes `NAMED_STATUS_DEFAULTS` (slow 0.5/1200 ms, silence 1.0/1200, stun 1.0/400),
   authored `magnitude`/`duration` (seconds) override field-wise, an unknown name lands inert
   (magnitude 1, duration 0), a `dot` gets `tick_ms` (authored `tick` seconds, default 500 ms) —
   then merges into the target (stacking rules below); `buff {stat, mult, duration}` is a
   **frenzy-family status on the TARGET** (self-casts pass self as target) with
   `magnitude = mult`; `transform {form}` only **REPORTS** `deltas.transform_to` (the executor
   swaps sprite/kit/`combat_form`); `zone {radius, duration, tick, statuses[]}` is **REPORTED** in
   `deltas.zones`, never applied here (the executor spawns the zone; its ticks apply the named
   statuses to whoever stands inside, never its owner).
3. **Shields absorb before hp**: any ACTIVE `shield` status pays first; a partially spent pool
   keeps its remainder as its new magnitude; a depleted pool is pruned. (Stacking merges same-kind
   statuses, so at most ONE shield pool exists via the public API.) Shields stop damage, **never
   poise**. An expired shield absorbs nothing and is left in place (only `tick_statuses` prunes).
4. **hp floors at 0** (`clamp(hp - dealt, 0, max_hp)`); `deltas.damage_dealt` reports the
   post-shield amount even when it overkills. Downing (hp ≤ 0 → downed) is the CALLER's threshold,
   applied through the engine's damage pipe — the resolver never sets a downed flag.
5. **Poise**: the ability's `poise_damage` accumulates on the target;
   `pool >= POISE_BREAK (100)` → `deltas.staggered = true` and the pool RESETS to 0. (The
   executor turns a stagger into: cast interrupt reason `stagger` + a 400 ms stun status + the
   knockback motion over ~150 ms.)
6. **Knockback** = authored pixels along the **normalized** `ctx.dir` (zero dir → zero knockback).

`deltas` (the projection the vectors pin): `{damage_dealt, poise_damage, staggered, dodged,
knockback [x,y], statuses_added [Status], zones [effect], transform_to?, target_state,
caster_state}`. The caster's state is carried through **untouched and unread** — v1 has no
caster-stat damage scaling (frenzy compresses the *executor's* windup/recovery, never resolver
damage).

**`apply_status(state, status) -> state`** — stacking (pinned): same `kind` **merges** into one
status keeping the **STRONGER magnitude** (never sums, never multiplies) with the **incoming
window** (new `applied_at_ms`/`duration_ms` — a weaker re-apply still refreshes the clock); a
dot's `last_tick_ms` bookkeeping survives the merge (no free extra tick on refresh). Different
kinds coexist.

**`tick_statuses(state, now_ms) -> {state, dot_damage}`** — advances time: prunes statuses on the
**half-open** activity window (gone at exactly `applied + duration`); accumulates dot ticks
(`magnitude` per `tick_ms`) with ticks landing while `last + tick <= min(now, expiry)` — i.e. **a
tick landing exactly at expiry counts** (pinned asymmetry vs the half-open activity window), and
re-ticking the same instant double-counts nothing. **The returned hp is UNTOUCHED** — the caller
lands `dot_damage` through its own damage pipe (attribution label `"dot"`; never registers as a
threat).

**Status queries**: `has_status` / `status_magnitude(state, kind, now_ms)` — a status is active on
`applied_at_ms <= now < applied_at_ms + duration_ms`; magnitude is the strongest active one, 0.0
when none.

**Cooldown ledger** (plain dict `ability_id -> ready_at_ms`; identical shape to Yumina's
`CooldownLedger`): `ledger_ready(ledger, id, now)` iff `now >= ready_at` (ready the exact instant
it elapses; unmarked = ready); `ledger_mark(ledger, id, now, cooldown_ms)` returns a NEW ledger
with `ready_at = now + cooldown_ms`. **The mark happens at CAST ACCEPT** (before the windup), and
there is deliberately **no refund operation: an interrupted cast stays spent** — pinned as
intended (dodging a telegraph really costs the caster the cooldown; the same rule makes a
cost-paying cast spend at accept).

### 1.5 Executor contract (engine-side shell — stated for the port, not vectored)

- Cast FSM `idle → windup → active → recovery → idle` on the executor's own accumulated clock
  (headless == live). The windup end is the strike moment; targeted casts re-aim at the strike and
  the flight line **locks** — afterwards geometry alone decides (that is what makes projectiles
  dodgeable, no to-hit rolls).
- `try_cast` refusal chain, **in order** (portable observable): `downed` → `busy` (mid-FSM) →
  `unknown_ability` → `stunned` → `silenced` (**windup abilities only** — silence blocks the START
  of a windup, never an instant motion like a dash) → `cooldown` → cost refusal (a bound cost
  provider is asked LAST, so a refused cost burns neither pool nor cooldown; paying deducts at
  accept, exactly like the cooldown mark).
- Frenzy (`attack_speed` mult, floor 1.0) compresses windup and recovery; the telegraph advertises
  the EFFECTIVE windup. Slow scales movement-skill speed (`1 - magnitude`, floored at 10%).
- Melee sweeps dedup per swing (one swing hits once); zones tick on `tick` cadence applying their
  named statuses to occupants (never the owner); movement skills carry authored `i_frames`
  (seconds) that set `i_frame_until_ms`.
- Damage flows ONLY through the engine's damage pipe; a lethal hit downs (never deletes), emits
  `agent_downed` exactly once, and force-exits combat mode for the felled body.

## 2. Ability schema — field table + Yumina parity

The authored ability shape (Tingen `data/abilities.json`, loaded/validated by `AbilityDB`; kits +
`default_style` + reflex rows per form in `data/combat_forms.json`):

| field | type | unit | req | consumed by |
|---|---|---|---|---|
| `id` | string | — | ✓ | everything (ledger key, kit refs, reflex `ability` keys) |
| `description` | string | — | – | LLM-facing fiction (facts, not commands) |
| `class` | `strike\|projectile\|spell\|movement\|effect\|transform` | — | ✓ | band derivation, style `class_pref`, telegraph `of`, executor dispatch |
| `cast_time` | float | **seconds** | ✓ | telegraph window (0 = instant, no windup to silence/interrupt) |
| `cooldown` | float | **seconds** | ✓ | ledger mark (`round(s*1000)` ms) |
| `cost` | object `{resource: amount}` | — | – | executor cost seam (v1 enforces player costs only). The `ammo` key is NOT a pool: it resolves through a CARRIED weapon/tool item (`items.json`) whose `grants` names the ability, and consumes that weapon's `ammo_item` from the caster's id→count inventory — refusals `no_weapon` (no carried granting weapon) then `no_ammo` (too few rounds). `stamina`/`spirituality` stay pools. |
| `range` | float | px | ✓ | castability gate, band derivation |
| `target_type` | `enemy\|point\|self` | — | ✓ | aim resolution; `self` bypasses range |
| `projectile` | `{speed}` | px/s | – | projectile flight (collision-dodgeable) |
| `motion` | `{kind: dash\|charge\|blink, distance}` | px | – | movement skills |
| `i_frames` | float | **seconds** | – | dodge window on movement skills |
| `aoe_radius` | float | px | – | melee sweep / area casts |
| `poise_damage` | float | poise | – | resolver §1.4.5 |
| `knockback` | float | px | – | resolver §1.4.6 |
| `effects` | Effect[] | — | ✓ | resolver effects walk (order matters) |
| `anim` | string | — | – | body animation key |

Effect union (resolver vocabulary; unknown kinds warn at load and no-op):
`{kind: "damage", amount}` · `{kind: "status", status, magnitude?, duration?(s), tick?(s)}` ·
`{kind: "buff", stat, mult, duration(s)}` · `{kind: "zone", radius, duration(s), tick(s), statuses[names]}` ·
`{kind: "transform", form}`.

### 2.1 Parity map vs Yumina `packages/engine/src/combat/types.ts`

| Tingen | Yumina | parity notes |
|---|---|---|
| `id` | `id` | = |
| `description` | `description?` | = (both LLM-facing fiction) |
| — | `name` | **Yumina extra** (display; Tingen renders from id) |
| `cast_time` (s, float) | `castTimeMs` (ms, int) | **unit differs** — convert `round(s*1000)` (§5 rounding); same telegraph semantics (0 = instant/uncounterable) |
| `cooldown` (s) | `cooldownMs` (ms) | **unit differs**, same conversion; same ledger |
| `cost {res: amt}` (multi-key dict) | `costVariableId?` + `costAmount?` (single) | shape differs; v1 data is single-key in practice — port maps the one pair; Tingen enforces at the executor seam, Yumina validates in the resolver |
| `range` (px) | `range?` (tiles) | **unit differs** (px vs tiles); Yumina `undefined` = unlimited/self, Tingen uses `target_type: "self"` for that |
| `aoe_radius` (px) | `aoeRadius` (tiles) | unit differs; Yumina requires it for `targetType "area"` |
| `target_type: "enemy"` | `targetType: "enemy"` | = |
| `target_type: "self"` | `targetType: "self"` | = |
| `target_type: "point"` | `targetType: "area"` | rename — both are ground-targeted |
| `effects[]` | `effects[]` | discriminated unions, order matters in both; member map below |
| `anim` | `animationStateId?` | = in intent (caster sprite state) |
| `class` | — | **Yumina lacks** — REQUIRED for the port (bands §1.2, class_pref masks, telegraph `of` triggers, executor dispatch) |
| `poise_damage` | — | **Yumina lacks** (needs the poise/stagger runtime) |
| `knockback` | — | **Yumina lacks** |
| `projectile {speed}` | — (closest: `damageMode: "collision"` + VFX collision payload) | Yumina's collision-VFX damage is the same *idea* (dodgeable travel); the port should keep ONE canonical projectile driven by ability data |
| `motion {kind, distance}` | — (closest: effect `{kind: "teleport", range}`) | Yumina's teleport is caller-resolved like Tingen's motion; port folds teleport into `motion {kind: "blink"}` |
| `i_frames` | — | **Yumina lacks** (needs the i-frame window on the combatant snapshot) |
| — | `iconUrl`, `vfxId`, `sfxId` | **Yumina extras** (renderer concerns — keep) |
| — | `damageMode` | **Yumina extra**; Tingen's equivalent is structural (`class: "projectile"` ⇒ collision) |

Effect-member map: `damage {amount}` ↔ `damage {amount, damageType?}` (Tingen has no damage
types; `"true-"` prefix reserved on their side). `status {status, magnitude?, duration s}` ↔
`status {statusId, durationMs}` (**Yumina lacks `magnitude`** — needed for slow/shield/frenzy
strength; unit differs). `buff {stat, mult, duration}` ↔ `buff {stat, delta, durationMs}` —
**semantic difference: Tingen `mult` is a multiplier, Yumina `delta` is additive**; the port keeps
multiplicative for `attack_speed` (frenzy) or maps at the boundary. `heal` — **Tingen lacks**
(Yumina keeps; a Tingen heal would be a negative-damage decision NOT taken in v1 — add as its own
effect kind, never negative damage). `zone`, `transform` — **Yumina lacks**, both required for the
slice (paper_charm, assume_form). `teleport` — see `motion` above.

Combatant snapshot: Yumina `{id, hp, maxHp, attack?, defense?, variables?}` vs Tingen state
`{hp, max_hp, statuses, poise, i_frame_until_ms}` — the port **adds statuses/poise/i-frames** to
its runtime snapshot; Tingen v1 consumes **no flat attack/defense** (no damage scaling — keep
theirs dormant or drop). Resolver result: Yumina `AbilityResolution` folds validation
(`applied: false, reason`) into the resolver; Tingen validates in the executor (`try_cast`
refusals §1.5) and the resolver **always applies** — the port should keep refusal reporting
wherever it lives, but the *applied* deltas must match §1.4. `CooldownLedger`
`Record<string, number>` is **identical** in shape and meaning (ready-at timestamp) — but port it
onto the **sim clock**, not wall-clock (see §8).

## 3. Events (telegraph + combat lifecycle)

All events ride the engine's event bus and fan through the **vision-gated Stimulus channel** (an
agent reacts only to events it can perceive, §1.3). `dir` travels as a JSON-safe `[x, y]` array.

| event | payload | emitted |
|---|---|---|
| `ability_cast_started` | `{caster, ability, target, dir: [x,y], cast_time}` | the instant a cast is accepted — **this IS the telegraph**; `cast_time` is the EFFECTIVE windup seconds (frenzy-compressed). Damage NEVER precedes it. |
| `ability_cast_finished` | `{caster, ability}` | the strike moment (windup resolved; projectile spawns / melee sweeps / zone plants NOW) |
| `ability_cast_interrupted` | `{caster, ability, reason: "stagger"\|"stun"\|"downed"}` | a windup broke (poise break, stun status landing mid-windup, or the caster downed). Silence is NOT an interrupt — it blocks the next windup's START. |
| `combat_started` | `{agent}` | the one place the combat mask flips ON (damage on a standing agent, a valid engage, or a GM cast). Idempotent, no form/kit side effects. |
| `combat_ended` | `{agent}` | mask OFF (disengage sustained, or a downing force-exits). Clears parked casts. |
| `agent_attacked` | `{actor, target, damage, target_hp, downed}` | every landed strike (one emitter), AFTER the damage pipe applied it |
| `agent_downed` | `{actor, target}` | exactly once, the moment a target is felled |

Reflex `telegraph` triggers consume `ability_cast_started` re-shaped by the perceiving executor to
`{kind: "telegraph", ability, class, at_me, caster}` (`at_me` = the telegraph names ME as target
or aims within my hurtbox line; the *perceiver* computes it).

## 4. Determinism rules (all pinned by vectors where a pure surface exists)

1. **Integer-millisecond arithmetic.** All times/durations inside the combat core are int ms on
   the executor's accumulated sim clock (never wall time). Authored data uses seconds; convert
   ONCE at the boundary: `ms = round(seconds * 1000)`.
2. **Rounding is HALF-AWAY-FROM-ZERO** (GDScript `round()`). **JS `Math.round` differs on
   negative halves** (GDScript `round(-2.5) = -3`, JS `Math.round(-2.5) = -2`) — v1 data has no
   negative durations, but the port MUST implement half-away-from-zero:
   `const roundHalf = (x) => Math.sign(x) * Math.round(Math.abs(x))`. The fixtures carry a
   positive canary (`0.0005 s -> 1 ms`, catching floor/truncate implementations).
3. **No RNG.** No crits, no damage ranges, no random dodges. Hit/miss is binary and geometric
   (locked flight lines, i-frame windows).
4. **Stronger-wins status stacking** (§1.4): same kind merges to ONE status, max magnitude,
   incoming window, dot bookkeeping preserved. Statuses never sum or multiply; **shields never
   sum** (a 15-pool re-shielded with 20 is one 20-pool).
5. **Shield-before-hp**; shields never absorb poise; depleted pools prune; expired pools are
   inert but linger until `tick_statuses`.
6. **Poise breaks at `>= 100`** and the pool resets to 0 on the breaking hit.
7. **I-frames are strict**: dodged iff `now < i_frame_until_ms`; a dodge zeroes the ENTIRE hit
   (damage, statuses, poise, knockback, zones, transform).
8. **Status activity is half-open** `[applied, applied+duration)`; **dot ticks close at expiry**
   (a tick landing exactly at `applied+duration` counts). Pinned asymmetry — port it exactly.
9. **Cooldown burns on interrupt**: the ledger marks at cast ACCEPT; no refund operation exists.
   Ready iff `now >= ready_at` (ready at the exact instant).
10. **hp clamps to `[0, max_hp]`**; `damage_dealt` reports the post-shield hit, not the
    overkill-clamped delta; downing is the caller's threshold through the one damage pipe.
11. **`tick_statuses` never touches hp** — dot damage returns to the caller and lands through the
    same damage pipe as any strike (events/EndGame wiring stay live).
12. **Tactical selection is order-free**: lexicographic `(class_pref index, rank score, id)`;
    id-ascending ties; transform never picked; reflex delay clamps [150, 800]; `hp_below` strict.
13. **Reflex evaluation is pure and complete**: every due row returns, in rule order; the caller
    owns `fired_counts` (increment at schedule time) and every clock.
14. **Wire binding**: JSON numbers are all floats — compare numerically (1e-6), never by type;
    JSON object keys are strings — `fired_counts` re-keys to int at the boundary.

## 5. Explicit non-goals (v1 — decisions, not omissions)

- **No world pause.** Yumina's `COMBAT_PAUSE_SOURCE` / `COMBAT_TACTICAL_PAUSE_SOURCE` clock
  acquisition is explicitly NOT ported; the world clock advances during every fight (asserted by
  the Tingen sim harness).
- **No entity deletion.** Lethal damage downs (with consequences); bodies persist.
- **No post-fight coach.** Reflex rules are pre-authored data in v1; the LLM add/edit channel and
  the coach loop are future work (Yumina-later).
- **No automatic transform reveal.** Never an engine rule — only reflex rows, the LLM's choice, or
  a GM/Director directive cast a `transform` ability (vector-pinned in `choose`).
- **No locational damage / graze windows** (binary hit; graze is a data-driven maybe, off).
- **No LLM on the frame path**, no Tier-C per-action actor loop in combat.
- **No resolver-side cost validation** (executor seam; v1 enforces player pools only). No flat
  attack/defense scaling. No `heal` effect kind yet.
- **No RNG**, restated because it is the one most tempting to add.

## 6. Fixture file & runners

`combat_test_vectors.json` (beside this spec) — categories and counts:

| category | vectors | surface |
|---|---|---|
| `constants` | 16 checks | every pinned constant + the full STYLES mask table |
| `resolver_apply` | 21 | one-hit `apply_ability` deltas (damage/shields/i-frames/knockback/statuses/buff/transform/zone/clamps/rounding canary) |
| `resolver_chain` | 3 | multi-hit poise accumulate→stagger→reset (threaded target state) |
| `resolver_sequence` | 6 | `apply_status`/`tick_statuses`/queries op-scripts (stacking, dot ticks, expiry edges) |
| `resolver_ledger` | 2 | cooldown ledger ops incl. the interrupt-burn pin |
| `reflex` | 19 | every trigger kind fires/doesn't, at_me discrimination, clamp edges 149/150/800/801, max_fires, multi-due, unknown-kind inertness |
| `tactical_bands` | 6 | band derivation from kit data incl. fallbacks |
| `tactical_band_of` | 5 | inclusive band edges |
| `tactical_choose` | 17 | the four-style fixed-scenario pin + range/cooldown/retreat/counter/tie-break/transform-never/self-target/reposition cases |

All ability/kit fixtures are **embedded** in the file (`vx_`-prefixed) — the vectors never read the
shipped `data/*.json`, so authored-data edits can't break them. Runners:

- **GDScript (reference):** `tingen/tests/run_combat_vectors.gd`
  (`godot --headless --path tingen -s tests/run_combat_vectors.gd`; also folded into
  `tests/run_tests.gd` as `_test_combat_vectors` for CI-equivalence). Prints
  `=== N passed, M failed ===`, exits non-zero on failure.
- **Regeneration:** `tingen/tests/dump_combat_vectors.gd` re-fills every `expected` by running the
  live implementation through the SAME fill statics the runner compares with. Change the
  algorithm (or add vector inputs) → regenerate → both runners + the TS runner must go green.
  Never hand-edit an `expected`.
- **TypeScript (Yumina, later):** a vitest/jest runner mirroring `run_combat_vectors.gd`'s fill
  functions 1:1 (see §8). Tolerance 1e-6 on floats; exact on strings/bools/shapes.

## 7. What is NOT fixtured (backstopped engine-side — add vectors before the port relies on them)

The executor FSM & refusal chain (§1.5), telegraph event payloads (§3), perceiver gating, zone
tick application, frenzy windup compression, knockback/stagger motion, protect-post geometry, and
the intent-commit side effects (§1.1) are covered by Tingen's GDScript suite
(`tests/run_tests.gd`: executor/tactical/reflex-wiring blocks) and the headless fight harness
(`tests/combat_sim.gd`), not by language-neutral vectors. They are contract-stated here; a TS port
should replicate them from §§1.1/1.5/3 and add shared fixtures if divergence ever bites.

## 8. Porting to Yumina — checklist

**Keep (already right in `packages/engine/src/combat/`):**
- `types.ts` `Ability`/`AbilityEffect` discriminated-union catalog and "resolver walks effects,
  bridge applies deltas" purity split — extend, don't replace (§2.1: add `class`, `poise_damage`,
  `knockback`, `projectile`, `motion`, `i_frames`; add `zone` + `transform` effect members; add
  `magnitude` to `status`).
- `CooldownLedger` `Record<string, number>` + `cooldowns.ts` helpers — identical contract to
  §1.4's ledger; **re-base it from wall-clock (`Date.now`) onto the combat sim clock** so
  save/reload and pauseless play stay deterministic, and adopt the no-refund pin.
- `CombatEndReason` reaction branching, renderer-facing extras (`iconUrl`/`vfxId`/`sfxId`),
  `animationStateId`.
- The Combatant-snapshot projection pattern (runtime → pure snapshot) — extend the snapshot with
  `{statuses, poise, i_frame_until_ms}`.
- The entity inventory (id→count) — already the right shape for the `ammo` cost key: resolve the
  carried granting weapon's `ammo_item` and consume from inventory (§2 `cost` row); no ammo pool.

**Replace / delete:**
- **`COMBAT_PAUSE_SOURCE` / `COMBAT_TACTICAL_PAUSE_SOURCE` acquisition** — the world never pauses
  for combat (§5). Combat runs on the live clock; the Esc-breather concept goes with it.
- **1v1 / encounter-scoped sessions** (`CombatSessionState.encounterId` as the world boundary) —
  combat is per-room and N-body; non-combatants keep acting; "session state" becomes per-agent
  facts (`in_combat`, `combat_intent`, `combat_form`) + the room's live executors.
- **Client-owned `combat_start`** — the combat mask flips engine-side from its two drivers
  (damage on a standing agent; a committed `engage`, §1.1) and `combat:start/end` become emitted
  facts, never client commands.
- Resolver-internal cost/target validation as the ONLY gate — keep the reporting shape if wanted,
  but move timing refusals (busy/stunned/silenced) to the executor equivalent so parked/retried
  casts behave like §1.5.

**Add (net-new on their side, all specced above):**
- The status runtime (§1.4 stacking + `tick_statuses`), poise/stagger, i-frames, knockback.
- The reflex rule engine (§1.3) + perceiver gating on their perception seam.
- The tactical layer (§1.2 bands + STYLES masks + the one selector) driven by `combat_intent`.
- Telegraph events (§3) with `castTimeMs` as the reaction window.

**Where the vectors slot in their test setup:** copy (or submodule-reference) this directory's
`combat_test_vectors.json` + `COMBAT_SPEC.md` into the engine package (e.g.
`packages/engine/src/combat/__tests__/combat-vectors.test.ts` loading the JSON), implement the
eight fill functions against their `resolver/reflex/tactical` modules exactly as
`run_combat_vectors.gd` does (including the `fired_counts` re-keying and 1e-6 numeric compare),
and wire it into `pnpm --filter @yumina/engine test` CI. A change to the algorithm on EITHER side
changes the fixtures *first* (regenerated from the reference implementation), then both suites
must pass — same governance as the cognition `test_vectors.json`.

### 8.1 State lifetime & persistence table

Every piece of combat state has exactly one of three lifetimes. A port that persists an
"ephemeral" row (or drops a "persisted" one) will diverge on save/reload even with all vectors
green — this table is the contract (final-review #8).

| State | Lives on | Lifetime | Rationale |
|---|---|---|---|
| `in_combat` | agent | **persisted** | The mask-flip is a world fact; reloading mid-fight resumes the fight. (Engine guard: a save never carries a phantom fight — a downed agent lowers it before write.) |
| `combat_form` | agent | **persisted** | What shape the body wears is a world fact — a monster stays transformed across reload. |
| `combat_intent` | agent | **persisted** | The last committed intent is a published fact the tactical layer re-reads on the first post-load tick. |
| `hp` / `downed` / `position` | agent | **persisted** | Ordinary body state (pre-combat contract). |
| cooldown ledger | executor | **ephemeral** | Rebuilt empty on load: sub-second timers aren't worth save-format weight, and the no-refund pin (§4) makes "fresh ledger" strictly generous, never exploitable mid-cast. |
| statuses / poise | executor | **ephemeral** | Seconds-scale decay; reload clears the smear. Poise pools reset full. |
| `pending_cast` | executor | **ephemeral** | A windup in flight at save time is LOST, not resumed — resuming would fire a telegraph nobody perceived. The cooldown was never charged (burns on interrupt/complete only), so nothing is owed. |
| pending reflexes / `fired_counts` | executor | **ephemeral + reset on form swap** | Reactions are perceiver-moment-bound; `fired_counts` re-key when `bind()` re-reads the new form's rows after `assume_form`, so per-fight caps are per-form. |
| projectiles / zones in flight | room (CombatOrphans) | **ephemeral** | Die with the scene; a saved mid-flight bullet resolves as a miss by omission. |

Yumina port note: `CooldownLedger` re-based onto the sim clock (above) should adopt the same
"rebuilt empty on load" rule rather than serializing timestamps.
