# Summer 2026 Roadmap

This is the **project plan**: the phases, the order we build in, and who owns what.
For the *technical* specs of individual framework features, see
[`FEATURE-ROADMAP.md`](FEATURE-ROADMAP.md).

## The shape of the summer

We build **one shared framework** together, then each person builds **their own
application** on top of it. The framework comes first (or at least far enough to
build on); the applications grow in parallel once the foundation is solid.

The presentation ladder — deliberately incremental, easiest rung first:

```
text adventure  ->  + first-class agents  ->  + memory/planning  ->  2D Godot game
   (works today)       (Phase 1)               (Phase 2)             (Phase 3+)
```

3D environments are a related but separate track (see Maui below); we are **not**
attempting 3D agent worlds in a 10-week summer.

## Phases

### Phase 0 — Onboarding (Week 1, everyone)
See [`ONBOARDING.md`](ONBOARDING.md). Everyone does HW1 Action Castle, reads the
engine, and gets fluent with Claude Code. Outcome: a shared mental model of
`Thing` / `Action` / preconditions / the turn loop.

### Phase 1 — First-class agents + real ReAct (Weeks 2–3, whole team)
Turn the agent layer from a skeleton into a working system.
- Promote NPCs from "a callable attached to a `Character`" to a first-class
  **`Agent`** with a persona, goals, and memory.
- Build the real **ReAct loop**: Observe → Think → Act → **Reflect**. Today
  `npc.py` has no reflect step and isn't wired into the live game; fix both.
- Add a **mockable LLM client** so the agent layer can be tested without API calls.
- Background reading: the **Generative Agents** and **ReAct** papers.

### Phase 2 — The framework features the apps need (Weeks 4–5, split ownership)
- **Events / triggers** (FEATURE-ROADMAP #5) — needed for simulations.
- **Time model** (FEATURE-ROADMAP #4) — NPC schedules, timed events.
- **Agent-to-agent interaction** — today most actions default to targeting the
  player; agents need to act on each other.
- **Structured observations** + a clean **world-state export API** — the
  foundation the Godot renderer will read from.

### Phase 3 — 2D Godot bridge (Weeks 5–6, the game-leaning folks, in parallel)
- A minimal Godot renderer that subscribes to the world-state feed and draws the
  world + agents. See "Reference material" below for a proven websocket protocol.

### Phase 4 — Individual applications (Weeks 6–10)
Everyone builds their own thing on the shared framework. Weekly demos.

## Who owns what

| Person | Focus | Direction |
|--------|-------|-----------|
| **Mekides** | Multi-agent behavior, non-game angle | Possibly pairs with Grace's multi-agent persona work |
| **Alistair** | Realistic simulation | SimCity / *Sims*-style social & group dynamics |
| **Frankie** | Realistic simulation | SimCity / *Sims*-style social & group dynamics |
| **Mark** | Games with LLM NPCs | Game-oriented; Godot front end |
| **Maui** | 3D environment generation | Separate track; arrives later |

Phases 1–2 are collaborative — everyone builds the shared foundation. Phase 4 is
where each person's direction takes over. Ownership is a starting point, not a
cage; swap and pair freely.

## Reference material (study, don't copy)

There is an **earlier prototype**, "Generative Action Castle" (a Smallville-style
simulator with a Python backend and a Godot front end), that lives on Chris's
machine — it is **not** in this repo. It's incomplete and has known bugs, so it is
**not a starting point**, but several parts are worth studying as reference once
we reach the relevant phase:

- A clean, correct implementation of the **Generative-Agents memory-retrieval
  scoring** (recency × importance × relevance) — the best reference for Phase 1/2
  memory work.
- A **data-driven (YAML) version of the action preconditions/effects engine** and
  the full Action Castle quest as data — a nice "same idea, different
  representation" contrast with our Python `Action` subclasses.
- Five richly-written **agent personas** (innate/learned traits, goals with
  priorities and time horizons) — good prompt-engineering examples.
- A **Godot ↔ Python websocket protocol** that actually works end to end — a
  proven blueprint for the Phase 3 bridge.

Ask Chris for access when you get to a phase where one of these helps. Treat its
bugs as cautionary tales (and good "find the bug" exercises), not as gospel.

## Working agreement

- Feature branches, reviewed via PR before merging to `main`.
- Use Claude Code freely — but read and understand what it writes; you own the code.
- Demo something every week, however small. Momentum > polish.
- Ask questions early and often, in Slack or in person.
