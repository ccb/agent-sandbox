# Tingen — Orchestrator / GM Design

Status: **Phases 1 + 2 SHIPPED** (2026-07-02; authored same day from the concurrency + scene research
sweep). Live Sonnet validation: distinct-action beats rose from ~0 to 5-9 of each run's multi-actor
beats; emergent in-character coordination observed (a cultist negotiating an item handoff by speech).
Live findings folded back in: off-cohort task-bearers HOLD (never drift to day-job schedules);
failed gathers leave informed facts ("none left" / "hands were full"); the Coordinator publishes
`all_claimed` when every outstanding material is already carried. Phase 3 (LLM GM) remains open —
the `/narrate` seam (GM panel) and the `focus` seam are its entry points.
Related: `tingen_npc_framework_design.md` (neutral-engine principle), agent-sandbox `turns.py` (simultaneous-turn precedent).

## 1. The problem this solves

Observed in playtests: all cult members perform the **same action every beat**. The research audit traced
it to three stacked causes:

1. **Simultaneous decisions from identical snapshots.** `AgentRuntime.run_beat` builds every
   deliberator's snapshot back-to-back with no commits interleaved, then ships them as ONE batched
   `/decide` POST; the sidecar fans them to Claude concurrently. Same goals + same world + same rite
   ledger + zero cross-agent visibility → N independent calls converge on the modal action.
2. **One-beat stale decisions.** `HttpSidecar` serves last beat's cached decisions while refreshing this
   beat's (by design), so even sequential commits can't inform any same-beat decision.
3. **Cache replay amplifier.** `HttpSidecar._cache` is never invalidated after an action commits; with
   the single in-flight slot, a slow LLM beat replays each agent's last action verbatim for multiple
   beats (Critic only vetoes repeated `hide`/`idle`).

There is **no contention handling**: two agents gathering the same item both act on stale premises and
the loser is never told why (contrast agent-sandbox `turns.py::_handle_contention` — the loser gets a
conflict event and an informed retry).

## 2. Is the Orchestrator the same thing as the "world manager GM"?

**Yes — one conceptual component ("the GM"), three separable roles, built as three small units:**

| Role | What it does | When it runs | Today's status |
|---|---|---|---|
| **Coordinator** (the "orchestrator") | Decides *what each agent attends to* — partitions outstanding work, resolves contention, staggers deliberation | every beat, pre-deliberation | **build now (Phase 1+2)** |
| **Narrator** | Summarizes world events for the player-facing GM panel | every 30s wall-clock | **build now (GM panel)** |
| **Director** | Guardrails on outcomes (exposure gating, campaign pacing) | per-action commit | already exists: `Overseer` + `Critic` |

They share one identity to the player (the "GM" row in the model panel drives the Narrator's — and any
future LLM Coordinator's — model), but they are **separate small units** with their own seams, because
they run at different frequencies and have different determinism requirements: the Coordinator must be
deterministic and engine-side (replayable, testable, free); the Narrator is cosmetic and may be an LLM;
the Director stays the deterministic guardrail it already is. A future "LLM GM" slots in behind the
SAME seams (Coordinator directives / Narrator prose) without engine changes.

**Scope: whole game, not per-scene.** Agents act across rooms whether or not the player watches;
coordination is about the agent SIM, not the loaded scene. (The panel shows the whole world's digest for
the same reason.)

## 3. Design principles (constraints, non-negotiable)

- **The engine states facts; agents choose.** The Coordinator never commands. It publishes *facts about
  the plan* into perception ("the plan currently allocates the candle to you") — the LLM still decides
  in character. No imperative verbs in engine strings.
- **Neutral + data-driven.** The Coordinator partitions *subtasks derived from task data* (e.g.
  outstanding `task.site` materials). No cult/faction branch; ANY group of agents sharing a task gets
  coordinated identically.
- **Offline-deterministic.** Every Phase 1/2 mechanism is a pure function of (world state, beat) so the
  AmbientSidecar world stays reproducible and unit-testable.

## 4. Implementation plan

### Phase 1 — decorrelate decisions (engine-only, small)
1. **Stagger deliberation (option b).** Partition deliberators across beats: agent deliberates when
   `md5(agent.id) % STAGGER_K == beat % STAGGER_K` (K=2, a property of the BRAIN — deterministic
   clients return 1). Later cohorts see earlier cohorts' *committed* effects (positions, ground
   items, rite ledger). AS BUILT: the stagger applies unconditionally — the originally sketched
   "always_active agents exempt on fresh-event beats" is NOT implemented (an attacked agent can
   react up to K-1 beats late); acceptable at K=2, revisit if K grows.
2. **Intent visibility (option c).** Extend `Perception._nearby` entries with the peer's last committed
   action as an objective fact: `doing: "<verb> <target>"` (from `other.current_action`). Render in
   `brain.py`'s Nearby line: `voss (clerk, gathering the candle)`. Objective, no interpretation.
3. **Cache invalidation.** Clear an agent's `HttpSidecar._cache` entry once its action is consumed by a
   commit — a slow LLM beat now falls back to schedule/hold instead of replaying a stale verb forever.
4. **Contention facts.** When `gather_item`/`perform_ritual_step` degrades because another agent got
   there first, write the loser a short_memory fact. AS BUILT: the fact is unattributed ("reached
   for the candle, but found none left" / "hands were full") — WHO took it arrives separately via
   the vision-gated witness channel, keeping each fact within what the agent could actually know.
5. **Dead payload fix.** `recent_events` was computed in `build_snapshot` but never forwarded on
   `/decide`. AS BUILT: **deleted**, not forwarded — a global event feed would leak omnisciently
   past each agent's `vision_r` (the vision port landed first and superseded the original
   "forward capped at 8" call); peer awareness rides the vision-gated Stimulus channel instead.

### Phase 2 — Coordinator v1 (deterministic work partition)
- New autoload `Coordinator` (or folded into `Overseer` — kept separate for testability; Overseer stays
  the Director). Each beat, for every group of agents sharing the same `task` (same ritual id):
  compute outstanding subtasks (`SummoningPlan.materials_outstanding()` + site occupancy), and assign
  each agent at most ONE unclaimed subtask, deterministically (stable sort by agent id + subtask id).
- Publish as **perception fact**, not command: snapshot gains `focus: {"subtask": "candle", "why":
  "unclaimed"}`; `brain.py` renders "The plan currently allocates to you: fetch the candle (unclaimed)."
- The Critic does NOT enforce focus (an agent may ignore it in character); coordination emerges from
  information, not force. This is what separates this design from scripted behavior.

### Phase 3 — LLM GM (later, not today)
- The Narrator seam (GM panel `/narrate`) and the Coordinator's assignment table are the two places an
  LLM GM can later take over: a `/direct` endpoint returning assignments through the SAME `focus` field,
  and richer narration. Model comes from the "GM" model row that already exists in ModelPanel.

## 5. What is explicitly NOT in scope
- No turn-based lockstep (option a): highest fidelity but multiplies wall-time by N and reworks the
  one-beat-latency pipeline; revisit only if Phase 1+2 prove insufficient.
- No temperature tuning (option e): identical context converges regardless; diversity comes from
  information + staggering.
- No LLM in the decision loop for coordination (cost + determinism); LLM stays in the two seams above.

## 6. Testing
- Stagger: cohort membership is a pure function of (id, beat); assert exact cohorts over 4 beats.
- Intent visibility: peer's committed action appears objectively in the next snapshot's nearby entry.
- Cache: consumed action never replays; slow-beat fallback engages.
- Contention: two agents targeting one item → exactly one gets it; loser's short_memory carries the fact.
- Coordinator: 3 same-task agents + 3 outstanding materials → bijective assignment, stable across
  replays; a 4th agent gets no assignment; a bystander (no task) gets none.
- Live-LLM validation: 2-3 beats with Sonnet; assert the cult splits across distinct verbs/targets in
  the play log (manual review, budgeted).
