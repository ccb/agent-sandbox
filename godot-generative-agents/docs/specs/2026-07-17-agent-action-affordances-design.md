# Agent action layer: affordance-curated verbs — design spec

**Date:** 2026-07-17 · **Status:** draft (awaiting AK review) · **Branch:** see §5 (spans `main` + `godot-ga-main`)
**Issues:** the implementation split of design anchor #446 · first engine consumer #464 · rides on #356 (per-action tools), #581 (pacing), #582 (conversation consequences) · related #594 (drives), #580 (decide context)

## Context

The Penn agents' action vocabulary is still `travel` + `perform` (plus the
boil-room verbs from #300). The #446 thread converged on the design but stopped
at the meeting; the 7/16 sync produced no binding decisions, so this spec **is**
the position, cut into implementation issues.

What exists to build on:

- **Per-action typed tools** (#356/#485): `npc.tools_for()` derives one tool per
  verb from `ARGUMENTS_SCHEMA`; Penn's `cognition.action_tools_for()` enriches it
  (destination enums). But the *set* of verbs offered is static —
  `agent.action_names` is computed once at attach time (`cognition.py`), so every
  decide offers every verb regardless of where the agent stands.
- **Affordance tags** (#40): properties on Things (`EDIBLE`, `READABLE`,
  `is_device`, …), surfaced in `WorldState`. `Location` is a `Thing`, so arena
  tags are the same mechanism.
- **The gate**: `check_preconditions() → apply_effects()` stays the sole
  authority over world mutation, always.
- **Perception**: `vision_r` (tiles) + `TiledGame.get_locations_in_vision` +
  `memory.perceive` presence.
- **Pacing** (#581): verbs opt into `duration_minutes`/`emoji` meta-slots;
  the executed action owns pacing.

## Decisions (brainstorm 2026-07-17, AK)

1. **The verb declares its placement requirement as data** (rubric axis 5 from
   the #446 thread): `REQUIRED_AFFORDANCES` on the `Action` class; world objects
   only carry tags. "Actions available on this object" is the computed inverse,
   never authored per object — one fact, read by both the toolset builder and
   the precondition gate, so they cannot drift.
2. **Offers are in-scope only.** Perception radius never widens the toolset: a
   verb is offered ⇔ its place-check would pass *right now*. Visible-but-distant
   affordances surface in the **observation** ("Nearby: Van Pelt Reading Room —
   studyable"), motivating `travel`; the verb appears on arrival. No failed-gate
   rounds by construction, no composite travel+act actions.
3. **Engine-first.** The mechanism lands in the engine library (every game gets
   it; #464's lifted verbs are the next consumer), not prototyped Penn-locally.
   New Penn verbs themselves stay backend-local per the #300/`DrinkPenn`
   precedent — lifted only when another game wants them.

## §1 The mechanism (engine → `main`) — issue E1

- `Action` base gains `REQUIRED_AFFORDANCES: tuple[str, ...] = ()`. Empty
  (the inherited default) = **universal**: always offered. A tagged verb
  declares e.g. `("is_device",)`.
- One shared helper on the base — `affordance_in_scope(character, game)`:
  True iff some thing in the actor's action scope (items at the current
  location, inventory, **or the location itself**) carries every property in
  the tuple. Multi-entry tuples are ALL-of on a single thing; the common case
  is one tag.
- `npc.tools_for()` filters: a verb with a non-empty declaration is offered
  only when its helper passes. Verbs with `()` are untouched, so **existing
  behavior is unchanged until a verb opts in**.
- The same helper becomes the verb's place-precondition (called from
  `check_preconditions()`), which is what makes the invariant structural:
  *offered ⇔ the gate's place-check passes*. The gate still checks more than
  place (possession, `is_on`, `checked_out_by`) and remains sole authority.
- Declarations added in E1 to the engine verbs this batch consumes:
  `Eat` → `(Property.EDIBLE,)`, `Read` → `(Property.READABLE,)`. Note: this
  drops those verbs from toolsets where no qualifying thing is in scope — a
  strictly-good change (those picks were guaranteed gate failures), but engine
  tests that assert full tool lists need updating.
- #464 (activate/deactivate lift) declares `("is_device",)` on arrival — E1
  names it as the follow-on consumer but does not absorb it.

## §2 Penn wiring (→ `godot-ga-main`, after sync) — issue P1

- `action_tools_for` inherits the filter (it already delegates to
  `tools_for`); verify no Penn-side re-listing bypasses it.
- The decide context block (#580) gains a **nearby-affordances line**: arenas
  within `vision_r` and the tags they'd unlock, from
  `TiledGame.get_locations_in_vision` + location/item tags. This is the
  perception half of decision 2 — desire → travel → act.
- Arena tags land in `world_data_upenn.yaml`: `studyable` on Van Pelt reading
  arenas, `dining` on Houston Hall.
- **Byte-identical guard**: the mock/schedule brain never enters the tool
  path, so the bundled replay must stay byte-identical; P1's acceptance
  includes the regen-and-diff check.

## §3 The verbs (→ `godot-ga-main`) — issues P2–P4

All go through the gate; duration-bearing verbs opt into the #581 pacing
slots, one-tick verbs don't.

| Verb | Offered when | Gate (place = declaration) | Visible state change | Memory hook | Pacing |
|---|---|---|---|---|---|
| `wait` | always | anywhere | none — honest idle | "waited; nothing needed doing" | yes |
| `talk_to <person> [about …]` | another character co-located | target co-located + alive + conversations enabled | conversation starts (bubbles, feed) | #582 consequences wholesale: plan revision + relationship note | no (convo loop owns it) |
| `study [topic]` | arena tagged `studyable` | in a `studyable` arena | activity label; `studied_minutes` accumulates | "studied X for N min" | yes |
| `eat <food>` | `EDIBLE` in scope | engine `Eat`'s gate | item consumed; `is_hungry` clears (engine-modeled) | satiety; drives stay #594 | no |
| `check_out_book <book>` | book in scope | at shelf; gate alone rejects already-checked-out | shelf → inventory; `checked_out_by` set | "I have <book>"; unlocks `read` | no |
| `read <book>` | `READABLE` in scope/inventory | engine `Read`'s gate | reading activity; content → memory | payoff of the checkout loop | yes |

- **P2 — universal verbs.** Offer the engine's existing `wait` (revisits the
  deliberate exclusion in `cognition.py` — the pacing slot makes idle *settle*
  like `perform`, killing the sit-idle-every-tick objection that motivated the
  exclusion). New Penn-local `talk_to`: makes conversation **agent-initiated**
  (today it only fires engine-side on co-location); enters the existing #582
  conversation loop with the topic threaded into the opener. Implementation
  checks the engine `talk.py` family for reuse before adding a verb. Curation:
  offered only when another character is co-located — same fact the gate reads.
- **P3 — arena tier.** Penn-local `study` (declaration `("studyable",)`);
  EDIBLE meal items authored at Houston Hall so the engine's `Eat` becomes
  offerable there. No new eat code.
- **P4 — object tier.** Book Items + shelf in Van Pelt (`READABLE`, short
  content text), Penn-local `check_out_book` (move to inventory +
  `checked_out_by`), engine `read` offered via its E1 declaration. Penn's
  first real addressable objects outside the boil room.

New standardized properties: `studyable` (arena), `checked_out_by`,
`studied_minutes`. Everything else reuses existing flags.

## §4 What this deliberately does not do

- No vision-radius-widened offers, no auto-composed travel+act (rejected in
  brainstorm — see Decisions 2).
- No per-object verb allowlists/denylists (YAGNI until a real exception case).
- No exam verb, no needs/drives loop (#594), no engine lift of the new
  Penn-local verbs, no `meta.relationships` mutation.
- No object-tier `game_object` address work beyond the Van Pelt books —
  promoting furniture sprites to addressable objects stays future work.

## §5 Issue decomposition

| # | Track | Title (gist) | Depends on |
|---|---|---|---|
| E1 | `main` | Affordance-curated toolsets: `REQUIRED_AFFORDANCES` as data | — |
| P1 | `godot-ga-main` | Penn wiring: curated per-decide toolset + nearby-affordances observation + arena tags | E1 + sync |
| P2 | `godot-ga-main` | Universal verbs: offer `wait`, add agent-initiated `talk_to` | P1 |
| P3 | `godot-ga-main` | Arena verbs: `study` + `eat` at tagged arenas | P1 |
| P4 | `godot-ga-main` | Object tier: the Van Pelt library book loop | P1 |

P2/P3/P4 parallelize after P1. #446 gets this spec as a comment (its
deliverable); it closes when the batch is filed or stays open as the umbrella —
decided at filing time. #464 proceeds independently against E1's seam.

## §6 Testing & invariants

- **E1**: engine unit tests (`tiny_game()` pattern) — universal verb always
  offered; tagged verb appears/disappears with scope; helper == the gate's
  place-check (the invariant, asserted directly); existing full-tool-list
  tests updated.
- **P1–P4**: `godot-generative-agents/tests` patterns (live stepper, drain
  events); byte-identical replay regen-and-diff wherever world data changes;
  each new verb gets an offered-then-gated test (offered in the right arena,
  absent elsewhere, gate rejects the non-place failure modes).
- **Error handling**: nothing new — gate failures keep flowing through the
  step loop's existing feedback/revision path (#581).
