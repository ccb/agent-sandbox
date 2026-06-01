# Multi-Character Play — v2: Meshing with the Team Roadmap

*Personal working notes. Reconciles my earlier [MULTI_CHARACTER.md](./MULTI_CHARACTER.md)
brainstorm with the team's [ROADMAP.md](../ROADMAP.md),
[FEATURE-ROADMAP.md](../FEATURE-ROADMAP.md), and the GitHub issues (#1–#10).*

---

## TL;DR — the one insight

My v1 design and the team roadmap are mostly **two different layers** of the same
system, not two competing plans:

| Layer | What it decides | Owner doc |
|-------|-----------------|-----------|
| **Agent layer** | *How* a character decides what to do (LLM ReAct, persona, memory) | Roadmap / issues #2–#5 |
| **Orchestration + presentation layer** | *Who* acts, *when*, in what *order*, and *what each character sees* | My MULTI_CHARACTER.md |

My v1 explicitly said "**No LLMs**." The roadmap is LLM-first. That's not a conflict —
it means my layer sits *underneath/around* theirs. The team builds the brain; my
design builds the **turn structure, the actor-threading, the per-viewer observations,
and the event log** that the brain plugs into.

So the move is: **don't build my `Session` framework now.** Instead, contribute the
pieces of it that the shared framework *already needs* (issues #8 and #9 especially),
and save the rest (slash commands, party control, conflict resolution) for my own
Phase 4 simulation app.

---

## Vocabulary reconciliation (do this first to avoid two rival systems)

My v1 invented words that overlap with words the team is about to standardize. I
should adopt theirs and map mine onto them, so we don't end up with two competing
abstractions.

| My v1 term | Team term (issue) | Resolution |
|------------|-------------------|------------|
| `controller = "npc"` + `NPCController.plan()` | first-class **`Agent`** (#3) | An `Agent` is *what drives* a character whose `controller != "human"`. My `plan()` seam **is** the agent's decision call. Don't ship a rival `NPCController` protocol — fold it into `Agent`. |
| `ScriptedController` / `IdleController` (no-LLM) | "non-LLM NPCs via callables" (FEATURE #1) + mockable client (#2) | Scripted controllers become the **offline/test** implementation of the same `Agent` interface. This is literally what #2 (mockable LLM client) wants for testing. |
| `Session.run_tick()` phased loop | turn-based loop restructure (FEATURE #1, wired in #5) | **One loop, not two.** My gather→validate→resolve→narrate phases are a *refinement* of the team's player-then-NPC loop, not a parallel engine. |
| `View` / `describe_viewer()` | "structured observations" (Phase 2) + world-state export (#9) | My `View.build(game, viewer)` **is** the structured-observation API. Same thing, two names. |
| `GameEvent` event log | events/triggers (#6) + export feed (#9) | My append-only log is the data source both #6 and #9/#10 need. |
| `Intent` (structured command) | (no direct equivalent) | Useful internal plumbing for #8; introduce only if it earns its keep. |

**Action item:** when issue #3 design discussion happens, raise that
`controller`/`Agent` should be one concept, and that scripted behaviors are the
mock path for #2. Coordinate *before* building (the issue explicitly says so).

---

## Crosswalk: my v1 concepts → required issues

What in my v1 maps onto already-required work, and how I should treat each.

| v1 concept | Maps to issue | Relationship | My stance |
|------------|---------------|--------------|-----------|
| Actor-centric `Character` (`controller`, `has_acted_this_tick`, `action_budget`) | #3 Agent, FEATURE #1 loop | **Overlap** | Contribute during Phase 1. Keep it minimal; let `Agent` own persona/goals/memory. |
| Phased tick (gather/validate/resolve/narrate) | #5 wire ReAct, FEATURE #1 | **Extends** | Offer phases as the structure that makes #5's "reason → act → gated by preconditions" clean. Don't over-engineer; start with player-first, NPC-after. |
| `parse_action(..., actor=)` — thread actor through actions | **#8 agent-to-agent** | **Direct overlap** | This is the single biggest win. #8 *is* "stop defaulting targets to the player." My actor-threading notes are a ready-made design for #8. |
| `View` / `describe_viewer` / visibility rules | **#9 export API** + Phase 2 observations | **Direct overlap** | Champion `View` as the structured-observation layer. One viewer-centric builder serves both the human UI and the Godot feed. |
| `GameEvent` append-only log | #6 triggers, #9 export, #10 Godot | **Enables** | Build a small, serializable event record. #9 explicitly complains that current to/from_primitive drops history — the log fixes that. |
| Conflict resolution policy (initiative/order) | emerges from #8 + multi-actor | **Builds on** | Defer to Phase 4 unless two agents contend in Phase 2 demos. |
| `Session.turn` counter | **#7 time model** | **Overlap** | The turn counter belongs to #7. My session reads it, doesn't own a second clock. |
| Slash/meta commands (`/switch`, `/who`, `/party`) | *(none)* | **New, mine** | Pure addition. **Phase 4 app layer.** Do not push into shared framework. |
| Party / hot-seat human control | *(none)* | **New, mine** | Core to my Sims-style sim. **Phase 4.** |
| Save/load session blob | *(none, save/load is broken)* | **Out of scope** | Defer. CLAUDE.md flags save/load as incomplete; not my battle. |

---

## Where my design is genuinely useful to the *shared* framework

Two issues are where I can contribute multi-character thinking *without jumping the
queue*, because the team already needs them in Phase 2:

### Issue #8 — agent-to-agent interaction  ← my actor-threading
The issue: actions resolve targets against the player by default; agents need to act
on each other. My v1 already worked this out:
- Pass `actor` explicitly into `parse_action` / action constructors instead of
  re-scanning the command string for names.
- `determine_intent` uses `actor.location`, not `game.player.location`.
- Keep the `name, verb` author override (`gravedigger, go north`) as a secondary path.

This is the cleanest, most reusable slice of my v1. I should volunteer for / lean into #8.

### Issue #9 — world-state export API  ← my View / split world-vs-presentation
The issue: Godot needs a structured feed of locations/agents/items/recent events; the
current serializer drops blocks and history. My v1's two ideas land directly:
- **Split world truth from presentation.** The world graph is canonical; each
  consumer (human terminal, Godot, an agent's prompt) gets a *view* built on demand.
- **`View.build(game, viewer)`** with visibility rules = "structured observations."
  The same builder feeds (a) the human's room description, (b) an LLM agent's
  observation prompt, and (c) the Godot per-entity state.
- The **event log** is the "recent events" half of the feed.

Framing `View` as "one observation builder, three consumers" is a strong argument to
make when #9 is designed — it avoids three bespoke serializers.

---

## Tensions / things to NOT do

1. **Don't build a second game loop.** My `Session.run_tick` must be *the* loop from
   FEATURE #1 / #5, refined — not a parallel engine bolted on. Two loops = chaos.
2. **Don't ship `NPCController` as a rival to `Agent`.** Same seam, one name (`Agent`).
   Scripted = the offline/mock implementation (helps #2).
3. **Don't introduce a second clock.** Turn counter is #7's. Session reads it.
4. **Don't front-load slash commands / party / conflict rules.** Those are my Phase 4
   app, not shared framework. Building them in Phase 1–2 jumps the professor's order
   and bloats the shared core.
5. **Validate-without-mutating (dry-run preconditions)** from my v1 is a real refactor
   the team hasn't scoped. Propose it as *optional/incremental*; don't make it a
   blocker. Current `check_preconditions()` is fine to start.
6. **Save/load session** — drop it. Save/load is already broken (CLAUDE.md), not worth
   coupling my design to.

---

## Phase-aligned plan (respects issue order)

What I actually do, when, without getting ahead of the roadmap.

### Phase 0 (now) — onboarding
- Do #1 (`get_property` → False) and HW1 like everyone.
- Keep these notes; don't build yet.

### Phase 1 (whole team) — agents + ReAct (#2–#5)
- Contribute the **minimal actor fields** on `Character` (`controller`,
  `has_acted_this_tick`) where they help the turn loop (#5) — *coordinated with #3*.
- Argue in the #3 design chat for: `Agent`-drives-controller unification; scripted
  agents as the #2 mock path.
- Resist building `Session`/slash commands. Note them here as "Phase 4."

### Phase 2 (split ownership) — framework features (#6–#9)
- **Lean into #8** with my actor-threading design. This is my highest-leverage,
  on-roadmap contribution.
- **Lean into #9** with `View`/split-world as the structured-observation layer.
- Let the event log fall out of #6/#9 naturally.
- Read the world-state through #7's turn clock; don't duplicate it.

### Phase 3 (parallel) — Godot (#10)
- My event log + `View` feed the websocket protocol. Support whoever owns #10.

### Phase 4 (mine) — Sims/SimCity-style social simulation
This is where the *rest* of MULTI_CHARACTER.md becomes my app, built **on top of** the
shared framework:
- `Session` orchestration object, **party + hot-seat `/switch`/`/who`/`/party`**.
- **Conflict resolution** (initiative, contested pickups) — exactly the "group
  dynamics" my ownership row calls for.
- Multi-character control as the interface to a social sim where many agents act and
  the human steers a household/party.
- This is the natural home for my v1's meta layer, tick modes, and conflict policy.

---

## What stays uniquely mine (Phase 4 app, not shared framework)

- The `Session` object and tick *modes* (immediate vs plan-then-`/endturn`).
- All slash/meta commands and the command router.
- Party management and hot-seat switching.
- Conflict resolution policy between contending actors.
- The "social & group dynamics" simulation itself.

These build *on* the shared agent layer, structured observations (#9), and event log —
they don't need to live in the common core, and pushing them there early would
overstep the roadmap.

---

## Concrete next steps

1. **Phase 0:** finish onboarding + #1; leave this doc as my north star.
2. **Before #3 is built:** post the vocabulary-reconciliation point (controller =
   Agent; scripted = mock) in the design discussion.
3. **When Phase 2 opens:** volunteer for **#8** (actor-threading) and contribute the
   **`View`-as-observations** framing to **#9**.
4. **Keep a running list** here of any v1 idea I'm tempted to build early, and check it
   against "is this on the roadmap yet?" before writing code.

---

*Summary: my v1 is ~30% already-required shared framework (most valuably #8 actor
threading and #9 structured observations/event log) and ~70% my own Phase 4
simulation app (Session, slash commands, party, conflict rules). Mesh = contribute the
former on the team's schedule, defer the latter to Phase 4, and never build a rival
loop, agent abstraction, or clock.*
