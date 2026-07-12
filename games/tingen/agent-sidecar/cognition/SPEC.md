# Agent Cognition Spec (language-neutral)

**Status:** v1 — the contract for the Tingen "brain" (Python sidecar) and the eventual
Yumina bridge (TypeScript) port.

This spec defines the **cognition + governance** layer that sits in front of the LLM
decision call: per-agent **memory** (a retrievable stream), **tiered goals**, **reflection**,
and a **propose-time hard veto** (narrative governance). It is deliberately
implementation-agnostic — every rule here is a pure function of its inputs, so the **same
`test_vectors.json` fixtures must pass in both the Python implementation (Tingen, now) and the
TypeScript implementation (Yumina bridge, later).** When the two diverge, the fixtures are the
arbiter.

Division of labor this serves (from Yumina's `06-agent-cognition-gaps.md`):
> agent-sandbox owns cognition depth (retrieval, reflect-retry, tiered goals) · Tingen owns
> narrative governance (the hard veto) · Yumina owns the production substrate (the bridge).

Sections 1–4 (memory, retrieval, goals, reflection) mirror agent-sandbox's `memory.py` /
`Goal` exactly. Section 5 (the veto) is Tingen's contribution. Section 6 is the wire protocol.

---

## 1. Memory model

Each agent owns a **private, append-only stream** of `MemoryRecord`s. Records are never edited
or deleted (an honest log); the only mutation at read time is bumping `last_accessed_turn`.

```
MemoryRecord {
  id:                 int        # 0-based, assigned in append order; ties break by HIGHER id (newer)
  kind:               "observation" | "reflection" | "plan"
  text:               string     # one short natural-language sentence
  created_turn:       int
  last_accessed_turn: int        # starts == created_turn; bumped to `turn` when retrieved
  importance:         float      # 1..10 ("poignancy"); clamped to [0,10] in scoring
  actor:              string?    # who the record is about, or null
  tags:               string[]   # optional
}
```

- **observation** — something the agent perceived or did (default importance 1.0).
- **reflection** — a higher-level inference synthesized from memories (default importance 5.0).
- **plan** — an intention the agent formed (default importance 5.0).

The stream also tracks `importance_since_reflection` (sum of appended importances since the
last reflection) — see §4.

## 2. Retrieval (the core algorithm — must match `memory.py` byte-for-byte in behavior)

Given a `query` string and the current `turn`, score **every** record and return the most
useful ones. All three ingredients are on `[0,1]`; equal weights combine them additively.

```
ALPHA_RECENCY = ALPHA_IMPORTANCE = ALPHA_RELEVANCE = 1.0
DEFAULT_DECAY = 0.95
DEFAULT_MAX_RECORDS = 6          # top-k cap
DEFAULT_TOKEN_BUDGET = 800       # trim so the block can't crowd out the live observation
CHARS_PER_TOKEN = 4              # token-cost estimate divisor (below)

recency(record, turn)   = DECAY ** max(0, turn - record.last_accessed_turn)
importance(record)      = clamp(record.importance, 0, 10) / 10
relevance(query, text)  = |tokens(query) ∩ tokens(text)| / |tokens(query)|   # 0 if query has no content words
score(record)           = 1.0*recency + 1.0*importance + 1.0*relevance
```

- **`tokens(s)`**: lowercase `s`, split on non-word characters, drop empties and stop-words
  (see `STOP_WORDS` in `test_vectors.json` — the canonical list both ports use). Relevance is
  the share of the **query's** content words that also appear in the memory text.
- **Selection:** sort by `(score, id)` **descending** (so ties break toward the newer record),
  take the first `max_records`, then walk that list accumulating an estimated token cost and
  stop before the first record that would exceed `token_budget` — **except the first chosen
  record is always kept**, even if it alone exceeds the budget.
- **Token estimate (must match exactly):** a record's cost is
  `max(1, floor(len(bullet) / CHARS_PER_TOKEN))` where `bullet` is the rendered line
  `" - [{kind}, turn {created_turn}] {text}"` (note the leading space, and `kind` is the lowercase
  enum value). `CHARS_PER_TOKEN = 4`, integer floor division. The walk accumulates these costs; the
  cut and the first-record-always-kept edge are exercised by the `retrieval` fixtures with a finite
  `token_budget`.
- **Touch:** every returned record has `last_accessed_turn := turn` (attending to a memory keeps
  it fresh), *unless* `touch=false` (a read-only retrieval for inspection).
- **Optional semantic relevance:** with an embedding backend, `relevance` becomes
  `cosine_similarity(embed(query), record.embedding)` clamped to `[0,1]` (0 when either vector is
  zero). Off by default; keyword overlap is the deterministic, dependency-free path the fixtures
  assume.

The retrieved records (newest-relevant-important first) are rendered into the prompt as a
`RELEVANT MEMORIES` block — **only retrieved records enter the prompt, never the whole stream.**

## 3. Tiered goals (mirrors agent-sandbox `Goal` / `GoalType`)

```
Goal { description: string, tier: "short" | "medium" | "long", done: bool, secret: bool }
```

- An agent holds a list of goals across the three tiers. **Active goals** are those with
  `done == false`.
- `active_goals_by_tier(tier)` returns the active goals of that tier, **in insertion order**.
- Prompt rendering order: **long → medium → short** (long-horizon aim first as standing context,
  short-term goals last as the immediate push). Each tier rendered only if it has active goals.
- `public` vs `secret` goal split (Yumina parity): a goal may be flagged secret; **secret goals
  are omitted from any prompt that is `revealed == false`** (the cult's true aim never leaks into
  a perception the player could see).
- **Coercion of the wire `goals` (must match exactly):** each incoming goal is normalized —
  a full object passes through; a partial object fills missing fields with
  `{ description: "", tier: "short", done: false, secret: false }` (note: a missing `tier`
  defaults to **short**); a bare **string** `s` becomes `{ description: s, tier: "long",
  done: false, secret: false }` (a legacy single-intent line is treated as the long-horizon aim).

This replaces the single `intent`/`currentGoalLine` string that both Tingen-Godot and Yumina
currently use.

## 4. Reflection

When `importance_since_reflection >= REFLECTION_THRESHOLD` (default **30.0**), the brain marks
`reflected = true` for that beat and **resets `importance_since_reflection := 0`** (so `reflected`
is an **edge-triggered pulse**, not a level that latches true forever once the threshold is crossed).

The brain owns the **trigger + reset** (deterministic). The *synthesis* — the LLM step that turns the
trigger into new `reflection` records — is **caller-optional and is NOT performed inside `decide` in
v1** (it is the only non-deterministic part and is not fixture-tested). A full synthesis pass is:

1. Take the most recent `N` records (default 30).
2. Ask the LLM for 1–3 salient questions answerable from them.
3. For each, retrieve supporting memories (§2) and ask for one grounded inference.
4. Append each inference as a `reflection` record (importance default 5.0), citing the supporting
   record ids in `tags`/evidence.

When the caller appends reflection records, they participate in retrieval like any record.

> **v1 fixture status:** reflection has **no fixture** in `test_vectors.json` yet (the trigger/reset
> are covered by the Python integration test `test_brain.py`). A TS port MUST replicate the
> edge-trigger + reset; before reflection is relied on cross-language, add a fixture giving a
> sequence of `(importance ingests)` → expected `(reflected, importance_since_reflection)`.

## 5. Propose-time hard veto — narrative governance (Tingen's contribution)

Yumina's director only **soft-nudges/escalates** (`director.ts`: `narrate|nudge_npc|inject_event|escalate|idle`).
It cannot *guarantee* a narrative invariant. Tingen adds a **hard veto at propose time**: after an
agent proposes an action and it passes the legality/schema gate, the governance layer may
**approve / amend / veto** it against a set of declared invariants.

```
review(proposed_action, actor, world_state, invariants) -> Verdict
Verdict { decision: "approve" | "amend" | "veto", reason: string, invariant?: string, amended_action?: Action }

Action { verb: string, args: object, actor: string, public?: bool, reveals_cult?: bool }
actor  { agent_id: string, faction: string, role: string, position?: [x,y] }
```

Rules:
- Evaluate invariants in order; the **first** that fires decides the verdict. If none fires →
  `approve`. (Order is load-bearing: an action that matches BOTH invariants takes the **first**
  one's verdict — see the overlap fixture in `test_vectors.json`.)
- An invariant is a predicate over `(action, actor, world_state)` plus a verdict it returns when it
  matches.
- A `veto` means the action does not happen; the caller falls the agent back to its schedule/idle
  (it does **not** silently mutate the world).
- An `amend` returns a replacement `amended_action` (already legal) to commit instead.

**Governance tags are DERIVED, not LLM-supplied.** The LLM proposes only `{verb, args}`; it never
emits `public`/`reveals_cult`. So before `review`, the brain derives them (a caller-supplied flag, if
present, wins):
- `reveals_cult := actor.faction == "cult" and verb ∈ REVEALING_VERBS`, where
  `REVEALING_VERBS = { "recruit", "pray" }` — overt social betrayals. `perform_ritual_step` is
  **deliberately excluded** (the rite is governed by `no_rite_without_site`, and rite sites are
  hidden, so secrecy must never veto the rite itself).
- `public := world_state.public` if the engine sets it, else `verb != "hide" and an outsider witness
  is present` (a non-cult, conscious agent in `perception.nearby`).

**v1 invariants (Tingen):**
1. **`cult_secrecy`** — *the cult is never exposed by chance.* If `actor.faction == "cult"` and the
   action is **publicly observable** (`action.public == true`) and would **reveal cult membership**
   (`action.reveals_cult == true`) and is **not player-driven** (`world_state.player_triggered == false`)
   → **veto** (reason: "cult exposure must be player-earned, never incidental"). The same action with
   `player_triggered == true` → **approve** (the player uncovering them is the whole game). *(v1 status:
   `player_triggered` is supplied by the engine and is `false` today — no player-exposure mechanic
   exists yet, so all current AI-driven exposure is correctly vetoable; the approve branch goes live
   when an action the player forces carries `player_triggered = true`.)*
2. **`no_rite_without_site`** — a `perform_ritual_step` by a non-cultist, or by a cultist **not at a
   rite site** (`world_state.actor_at_rite_site == false`), is **amended** to `idle` (reason: "rite
   only bites at the altar"). *(This generalizes the engine's existing proximity gate into the
   governance layer so the rule is declared, testable, and portable.)*

Invariants are data-declared so Yumina's bridge can adopt the **same set** in TS; only the
predicate wiring is per-language.

## 6. Brain protocol (stateful)

The brain is a **stateful per-(session, agent)** service. The renderer/engine stays thin and talks
to it over a frozen, language-neutral request/response (HTTP now; the same shape ports to Yumina's
WebSocket bridge).

**Request — `decide` (one per agent per beat):**
```
{
  "session_id": string,
  "agent_id":   string,
  "turn":       int,
  "events":     [ { "text": string, "importance": float, "seq"?: int, "actor"?: string, "kind"?: "observation"|"plan" } ],
  "perception": { agent_id, display_name, faction, role, nearby:[{id,faction,role,...}], locations:[string], pressures:{...} },
  "goals":      [ Goal | string ],   # authoritative goal list (engine-owned); coerced per §3
  "world_state": { "player_triggered": bool, "actor_at_rite_site": bool, "public"?: bool, ... },
  "revealed"?:  bool                 # default FALSE; true only for a player-visible render (see below)
}
```

- **`revealed`** (default **false**): gates secret goals (§3). The agent's own decision prompt is the
  agent's private cognition, so secret goals are filtered from it on a hidden beat and from the
  retrieval query (§6.2). A port that omits `revealed` defaults to false → secret goals stay hidden
  (fail-safe). It is set true only when rendering a surface the player can see.
- **Idempotent ingest / `seq`:** the engine may resend the same observation across beats (its memory
  buffer is a capped sliding window). Each event may carry a monotonic absolute **`seq`** (lifetime
  observation index). The brain ingests an event **only once** (`seq > last_seq` for that agent),
  tracking `last_seq` in state. Events **without** `seq` are always ingested (legacy/tests). A `seq`
  that jumps **backwards** (max incoming `seq < last_seq`) signals a memory **reload** (save-load), so
  the brain resets `last_seq` and re-ingests the restored window. **Event `importance` is
  caller-supplied** (the engine owns the importance policy); the brain's ingest default is `1.0` for
  an observation, `5.0` for a plan.

**Per request the brain:**
1. **Ingests** new `events` (idempotent per `seq`) into this agent's stream as records (§1),
   updating `importance_since_reflection`.
2. Builds a retrieval `query` (§6.2), **retrieves** (§2).
3. Builds the prompt (§6.3): persona + **tiered active goals** (§3, secret-filtered by `revealed`) +
   **RELEVANT MEMORIES** (retrieved) + a situation cue + nearby + pressures + the verb menu.
4. Calls the LLM → a proposed action (`{verb, args}`).
5. Derives governance tags (§5) and runs **`review`**; on `veto` returns `idle`, on `amend` returns the
   amendment, on `approve` returns the action.
6. May **reflect** (§4 — edge-trigger + reset) when the threshold trips.

**§6.2 Query construction (must match exactly).** The retrieval query string is, in order:
the descriptions of the **active goals** rendered long→medium→short and **secret-filtered by the
request's `revealed`** (so a secret aim does not seed retrieval on a hidden beat), then
`perception.role`, then each `perception.nearby[].id`; joined by single spaces with empty parts
dropped.

**§6.3 Prompt structure (sections + gating are the contract; exact wording is not).** In order:
the framing line; `Character` persona `{agent_id, display_name, faction, role}`; a **SITUATION cue**
— for a **cult** agent only, "you are STANDING ON the rite site … perform_ritual_step THIS beat" when
`world_state.actor_at_rite_site`, else "you are NOT yet at the rite site; move_to it" (this cue is
behavior-critical: without it a cultist loops `move_to` and never starts the rite); the tiered goals
block (§3); a `RELEVANT MEMORIES` block (retrieved, one bullet each); `Nearby`; `World pressures`; the
**verb menu** (`- {verb}: requires [args]`, sorted; from the engine's verb schema); a **valid-targets**
line (`perception.locations` + `nearby[].id`); and the **JSON-only output contract**
(`Respond with ONLY a JSON object … No prose, no markdown fence`). Prompt *text* is the only
non-deterministic part (§ Determinism) and is not fixtured; the section set + the cue gating are.

**Response — single `decide`:**
```
{ "ok": true, "action": Action, "verdict": "approve"|"amend"|"veto", "invariant": string|null, "reflected": bool }
```
`retrieved` (the agent's own memory text) and `stream_size` are debug-only and are **omitted from the
HTTP response by default** — memory stays server-side; they appear only when tracing is enabled.

**Response — batch `decide` (`{ "requests": [ ... ] }`).** The engine sends one POST per beat carrying
every active agent's request; agents are decided **concurrently**. The reply mirrors `/propose`:
```
{ "ok": bool, "actions": [ Action ], "results": [ <single-response per request> ] }
```
`ok` is false if any per-agent decide errored; a failed agent's `action` is a safe `idle` tagged with
`_error` so the client surfaces it and ambient-fills rather than masking it as success.

**State & persistence:** per `(session_id, agent_id)` the brain holds `{ stream, importance_since_reflection,
next_id }`. v1 keeps this in-process (a dict); production swaps the store for Redis/Postgres keyed by
`(session_id, agent_id)` with no change to the algorithm (the same lesson as Yumina's persisted bridge).
Turn numbers come from the engine's beat counter.

**Determinism:** §§2–3 and §5 are pure and fixture-tested (`test_vectors.json`). §4's *trigger* is
deterministic; its *text* is not. The LLM call in step 4 is the only non-deterministic part of a
`decide`.

---

## Portability checklist (Python now → TS later)
- Keep §§2,3,5 as **pure functions** with no engine/Godot/Node coupling.
- Both implementations import the **same `STOP_WORDS`** and constants (incl. `CHARS_PER_TOKEN`) from a
  shared data file.
- Both run `test_vectors.json` in CI; a change to the algorithm changes the fixtures *first*.
- The `decide` request/response shape (§6), the query recipe (§6.2), the prompt section set + cue
  gating (§6.3), and the goal coercion (§3) are all part of the frozen wire; renderers never see the
  brain's language.
- **Engine-owned (NOT in the brain or the fixtures):** the per-event `importance` value (e.g. Tingen's
  keyword heuristic) and the `seq` numbering are produced by the engine and handed in. The brain only
  applies the documented ingest defaults. A TS port pairs with its own engine's importance policy; the
  fixtures freeze the brain's *scoring/retrieval/goals/veto*, not the engine's importance choices.
- **Fixture coverage today:** scoring, retrieval (incl. a finite-`token_budget` trim case), goal
  active/prompt-order, and veto (incl. an invariant-ordering overlap case). **Not yet fixtured:**
  reflection (§4), query construction (§6.2), and prompt structure (§6.3) — backstopped by the Python
  `test_brain.py` only; add language-neutral fixtures before a TS port relies on them.
