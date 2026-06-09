# Multi-Character / Multi-Agent System Design

**Status:** Proposal — not yet adopted. A design doc for discussion, not a
description of current behavior. See issue #3.

**Author:** Alistair King. This consolidates the v1 and v2 brainstorms originally
posted in PR #12 into a single canonical document.

*A unified design for turning `text_adventure_games` into a multi-agent simulated
environment. Sequenced to the team plan in [ROADMAP.md](../../ROADMAP.md) /
[FEATURE-ROADMAP.md](../../FEATURE-ROADMAP.md) and GitHub issues #1–#10.*

---

## 1. What we're building

A world where **every character can act** — the human-controlled one and any number
of AI-driven ones — all moving through the **same action pipeline**
(`check_preconditions()` → `apply_effects()`). Each character decides for itself, sees
only what it could plausibly see, and the world advances in discrete turns. The same
world state can be rendered three ways: as text for a human, as an observation prompt
for an LLM agent, and as a structured feed for a 2D renderer.

The design has four layers. They stack cleanly; you can build the lower ones and run a
playable game before the upper ones exist.

```
┌─────────────────────────────────────────────────────────┐
│  Presentation     human terminal · agent prompt · Godot   │  ← Views, export API
├─────────────────────────────────────────────────────────┤
│  Agents           Agent: persona, goals, memory, ReAct    │  ← decides actions
├─────────────────────────────────────────────────────────┤
│  Orchestration    turn loop · phases · events · time      │  ← who acts, when, order
├─────────────────────────────────────────────────────────┤
│  World model      Location · Item · Character · Action     │  ← exists today
└─────────────────────────────────────────────────────────┘
```

---

## 2. World model (today, lightly extended)

The existing `Thing` hierarchy and `Action` system stay as the single source of truth.
Two small additions make characters first-class actors:

- **`Character` gains actor fields** used by the loop:
  | Field | Purpose |
  |-------|---------|
  | `controller` | `"human"`, `"agent"`, or `"none"` (scenery/corpses) — who supplies the command |
  | `has_acted_this_turn` | reset each turn; set when an action resolves |
  | `action_budget` | actions per turn (default 1) |
- **Actions take an explicit actor.** Action constructors and parsing accept the acting
  character instead of defaulting targets to `game.player`. This is the backbone of
  agent-to-agent interaction (talk/give/attack between any two characters).

Everything else — preconditions, effects, blocks, the `Thing` property bag — is unchanged.

---

## 3. Orchestration: the turn loop

One loop drives the whole world. A **turn** is one unit of simulation time: the human
(or active character) acts, then every AI character acts, then the world reacts.

```
each turn:
  1. gather   collect one intended command per acting character
                - human: from input
                - agents: from Agent.decide(observation)
  2. resolve  for each actor in order: route command through the parser,
                run check_preconditions(); if it passes, apply_effects()
  3. react    fire any triggers whose conditions are now true (§7)
  4. advance  increment turn / clock, reset has_acted_this_turn, narrate results
```

Key rules:
- **Player/active character acts first**, then AI characters in a fixed order.
- **Preconditions are never bypassed.** An agent's chosen action is gated exactly like a
  human's; an illegal choice simply fails (and is fed back to the agent — §4).
- **One action per character per turn** to start; `action_budget` allows more later.
- A `gather → resolve` split lets two characters target the same thing in one turn;
  conflicts are settled at resolve time (§8).

---

## 4. Agents

An **`Agent`** is the decision-maker attached to a character whose `controller` is not
`"human"`. It owns the character's *mind*: persona, goals, memory, and the decision loop.

```
class Agent:
    persona: str            # who they are, how they talk/act
    goals: list             # what they want, optionally prioritized
    memory: Memory          # what they've observed/done (Phase 2)
    def decide(observation) -> command   # returns a raw command string
```

**Decision loop (ReAct + Reflect):**

1. **Observe** — build the agent's `View` (§5): its location, visible items/characters,
   recent events it would know about, plus persona and goals.
2. **Think** — ask the LLM what to do and why.
3. **Act** — return a command; the turn loop routes it through the parser and the
   precondition gate.
4. **Reflect** — if preconditions fail, feed the failure message back and retry (cap
   2–3 attempts) so the agent can recover instead of wasting the turn.

**Pluggable backends behind one interface:**
- **LLM backend** — real reasoning via the provider-agnostic client.
- **Mock/scripted backend** — deterministic rules (`if at churchyard: "take shovel"`),
  used for tests and for cheap NPCs that don't need an LLM.

Both implement the same `decide()` seam, so the loop, tests, and games don't care which
is driving a character. This is what makes the agent layer testable without API calls.

---

## 5. Observations & presentation (split world from view)

The world graph is canonical truth. What anyone *perceives* is a **`View`** built on
demand for a viewer — and the same builder serves all three consumers.

```
View.build(game, viewer) -> {
    location, visible_exits, visible_items,
    visible_characters, inventory, recent_events
}
```

Visibility rules (defaults): you see your room, items there + your inventory, other
characters in the room, and events you'd have witnessed; you do **not** see distant
rooms or others' inventories unless something reveals them.

One builder, three renderings:

| Consumer | Rendering of the View |
|----------|----------------------|
| Human terminal | prose room description (`describe_viewer(viewer)`) |
| LLM agent | the "Observe" block of its prompt |
| 2D renderer (Godot) | structured per-entity JSON over the export feed |

This replaces the hard-coded `game.player` description path and is the foundation of the
world-state export API the renderer subscribes to.

---

## 6. Time

A turn counter advances once per loop. On top of it, an optional clock maps turns to
in-game time (e.g. start 8:00 AM, 15 min/turn) or named periods (dawn/day/dusk/night).
Time is opt-in: with no clock configured the counter still increments. Time feeds
schedules and time-of-day in descriptions.

---

## 7. Events & triggers

Two related mechanisms record and react to change:

- **Event log** — an append-only list of small records (`turn, actor, action, summary,
  payload`). It is the "recent events" half of every `View`, the source for "what did I
  miss?" summaries, and the change feed the renderer streams.
- **Triggers** — `(condition, action, repeatable)` rules evaluated in the *react* phase,
  after all characters have acted. Built-in conditions: timer (`turn >= N`), location
  (a character entered X), property (`is_X` became true), and compound `and`/`or`.
  Trigger actions either mutate state directly or instantiate a normal `Action` (so they
  too pass through the precondition gate). Cap cascading at a fixed depth.

---

## 8. Multiple human-controlled characters (the simulation layer)

For richer simulations the human can steer more than one character. This is a thin
**session** on top of the loop — it changes *who you control*, never the world directly.

- **`active_character`** — receives unprefixed commands; the prompt shows it
  (`[gravedigger@churchyard] >`).
- **Meta commands** (prefix `/`, handled before the turn loop, no preconditions):
  `/who`, `/switch <name>`, `/party [add|remove] <name>`, `/status`, `/log`.
- **Conflict resolution** — when two characters' commands contend for the same target in
  one turn, settle by an `initiative` order (fallback: gather order); the loser's action
  fails with a clear reason. PR #30 ships this initiative-order version;
  [simultaneous-actions.md](simultaneous-actions.md) proposes how to grow it into a
  pluggable resolution policy (situational priority, conflict-aware retries, dialog phases).

This layer is what makes a *Sims/SimCity-style* social simulation playable: many agents
living their lives while the human nudges one or several of them.

---

## 9. Build order

Sequenced to the issues so the lower layers are solid before the upper ones build on them.

| Stage | Issues | Deliverable |
|-------|--------|-------------|
| **Foundation** | #1 | `get_property` returns `False`; warm-up. |
| **Agents + ReAct** | #2–#5 | `Agent` with persona/goals; mock + LLM backends; ReAct **with Reflect**; LLM agents wired into the live turn loop, precondition-gated, in a full playthrough. |
| **Framework features** | #6–#9 | Event log + triggers (#6); time model (#7); **actor-threaded actions** for agent-to-agent (#8); `View`/export API as structured observations (#9). |
| **Renderer** | #10 | Godot subscribes to the export feed + event log and draws world + agents. |
| **Simulation app** | Phase 4 | Session/active-character, meta commands, party control, conflict resolution → a social/group-dynamics sim on the shared framework. |

Each stage keeps single-character games working: with no agents, no session, and
`party == [player]`, the loop behaves like today's game.

---

## 10. Design invariants

- **One pipeline for all actors.** Humans and agents change the world only through
  `check_preconditions()` → `apply_effects()`. No actor cheats the gate.
- **One loop, one clock.** A single turn loop and a single turn counter; no parallel
  engines or duplicate time sources.
- **World vs. view stay split.** State lives in the world graph; everything anyone sees
  is a `View` built from it.
- **The decision seam is pluggable.** Mock/scripted and LLM agents are interchangeable
  behind `decide()`, so the system is testable offline.
- **Layers are opt-in.** A game can use the world model alone, add agents, then add the
  session layer — each is additive and backward compatible.

---

## Appendix: implementation sketches

Concrete artifacts carried over from the original (v1) brainstorm. These are
illustrative starting points for whoever implements a stage, not final API.

### Proposed module layout

```
text_adventure_games/
├── session.py       # Session, Intent, GameEvent, tick runner
├── meta.py          # MetaCommandRegistry, built-in /commands
├── views.py         # View.build, visibility rules
├── reporting.py     # Message, Reporter (decouple output from effects)
├── npc.py           # agent/controller protocol, reference implementations
├── games.py         # Game uses session; describe_viewer
└── parsing.py       # router; parse_action(..., actor=...)
```

Games opt in via a `MultiCharacterGame(Game)` subclass or a flag on
`Game.__init__(multi_character=True)`.

### Example session (human steering more than one character)

Setup: `you` in garden (human), `gravedigger` in churchyard (agent), `ghost` in crypt
(`controller="none"`).

```text
> look
You are in a walled garden...
Exits:
North to churchyard

> /who
* you (garden)
  gravedigger (churchyard)

> go north
You enter the churchyard. The gravedigger mutters over a fresh plot.
[Turn 1] gravedigger: take shovel — Gravedigger picked up the shovel.

> /switch gravedigger
Now controlling: gravedigger (churchyard)

> inventory
In your inventory: shovel

> /switch you
Now controlling: you (churchyard)

> get shovel
Someone else got there first.
[Gravedigger already took the shovel this turn.]
```

### Migration checklist (rough order)

1. **`Session` + `active_character`** — minimal; no phased tick yet.
2. **Meta commands** — `/switch`, `/who`, `/party`, `/help`.
3. **`describe_viewer` / `View`** — remove `game.player` from description paths.
4. **`parse_action(..., actor=)`** — thread the actor through actions.
5. **`Reporter`** — decouple printing from effects (buffer messages).
6. **Phased tick + agent gather** — the `gather → resolve → react → advance` loop.
7. **`GameEvent` log + `/log`**.
8. **Conflict policy + dry-run preconditions** — polish simultaneous effects.
9. **Save/load session blob** — full continuity.

Each step should keep single-character games working when the session is absent or
`party == [player.name]` only.

### Notes

- **Slash vs. colon:** `/switch` avoids clashing with in-world verbs; an optional colon
  prefix (`gravedigger: go north`) can remain for author-style commands.
- **Testing:** inject `handle_input(game, line)` without stdin; assert on the event log
  and the world graph after each tick.
- **Performance:** the event log can be capped (ring buffer) for long sessions; `/log`
  reads from the tail.
