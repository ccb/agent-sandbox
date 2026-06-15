# Simultaneous Action Resolution — Design

**Status:** Stages 1–4 implemented (issue #42); stages 5–7 remain future work.
It extends the **simultaneous turn mode** added by PR #30 (issue #25): this doc
takes `turns.py` and its `gather → resolve → react → advance` loop as the
starting point and grows it. The ordering seam, phase map, claim/arbitrate pass,
and ranked fallbacks (§4, §5) now ship in `turns.py`/`npc.py`, with one refinement
to §5.2 noted there.

**Author:** Alistair King.

*A design for making simultaneous turns fair, recoverable, and order-stable —
and for laying the groundwork for live agent-to-agent dialog. This is the
**Orchestration** layer from
[multi-character-play.md](multi-character-play.md) §3 (the turn loop) and §8
(conflict resolution), taken from "settle by an `initiative` order" to a
pluggable resolution policy. The code it builds on lives in
[`../../text_adventure_games/turns.py`](../../text_adventure_games/turns.py).*

---

## 1. What we're building

PR #30 lets every character act in the *same* turn: each agent decides against the
turn-start snapshot (gather), then the chosen commands run through the parser one
at a time in a fixed order (resolve). It works, but the order is a single static
field, a failed action just gets logged, and who-wins-a-tie depends on who happens
to resolve first.

This proposal keeps #30's loop and makes the **resolve step smarter** in four ways:

- **(a) Priority comes from the situation, not a field.** A pluggable ordering
  *function* replaces the lone `initiative` sort, so a game can say "the defender
  acts before the attacker this turn" instead of "character X is always faster."
- **(b) Contention is handled, not just logged.** When two characters reach for
  the same thing, the loser learns *why* ("someone got there first") and gets a
  fallback or an informed retry — not a bare failure line.
- **(c) Resolve order becomes a designed policy.** Who wins a contested resource
  is decided by the priority function up front, so the outcome is explainable and
  repeatable rather than an accident of mutation order.
- **(d) Dialog has a home.** Speech becomes the earliest "phase," which is the
  first step toward agents that actually talk to each other (§7).

It sits in the Orchestration layer; everything below it already exists:

```
┌─────────────────────────────────────────────────────────┐
│  Presentation   Message + Renderer: terminal · web · JSON │
├─────────────────────────────────────────────────────────┤
│  Agents         persona, goals, ReAct (Observe→…→Reflect) │
├─────────────────────────────────────────────────────────┤
│  Orchestration  turn loop · RESOLUTION POLICY · events     │  ← THIS DOC
├─────────────────────────────────────────────────────────┤
│  World model    Location · Item · Character · Action       │
└─────────────────────────────────────────────────────────┘
```

The design is **opt-in and additive**: with nothing configured it reduces to
exactly PR #30's behavior, and sequential mode is untouched.

---

## 2. Where PR #30 leaves us

The simultaneous round (`turns.py:run_simultaneous_round`) is four phases:

```
each round (simultaneous mode):
  1. gather    one intended command per acting character,
                 every agent deciding against the SAME turn-start snapshot
  2. resolve   for each intent in resolve_order(...): route through the parser,
                 run check_preconditions(); if it passes, apply_effects()
  3. react     fire triggers whose conditions are now true
  4. advance   turn += 1   (before NPC resolution, mirroring end_turn)
```

The gather/resolve split is what makes "simultaneous" meaningful: everyone *chooses*
blind to everyone else, then the choices are reconciled. The reconciliation is where
the three limitations live.

### 2.1 Ordering is a single static field

Resolve order is decided by one line:

```python
def resolve_order(intents):
    # higher `initiative` resolves first; ties keep gather order (stable sort)
    return sorted(intents, key=lambda intent: -int(intent.character.get_property("initiative")))
```

`initiative` is a property *of the character*, fixed for the whole game. There is
no way to say "in this situation, this character should go first." A guard should
outrank a thief when defending a door, but the *same* thief should go first when
fleeing — the action and the context should matter, and here they can't.

### 2.2 Retry is thin

When a resolve-time command fails, `route_with_retry` reflects once against the
*live* world and tries again; if that also fails, the round records:

```python
game.log_event(
    character.name, "action_failed",
    summary=reason, payload={"command": intent.command},
)
```

`reason` is the parser's tactical message — typically `"I don't see it."`. The
agent is never told *that another character took the item first*, there's no
cheap fallback action, and there's no way to **defer** an action whose
prerequisite is still pending this same turn (e.g. a door being unlocked by
someone else). A wasted turn is logged and the agent moves on.

### 2.3 State depends on resolve order

Effects mutate the live world *during* resolve, so a later intent sees the world a
earlier intent left behind. The #30 test makes this concrete: Alice
(`initiative=1`) and Bob (`initiative=5`) both decide `take gem` against the
snapshot. Bob resolves first and the gem enters his inventory; Alice's `take gem`
now fails its precondition, her reflect-retry fires against a world where the gem
is gone, and the round logs her failure. Flip the initiative and Alice wins
instead. **The final world state is a function of resolve order**, and the only
knob on that order is the static field from §2.1. There is no principled way to
say "they both wanted it — here's who gets it, and why."

These three are really two problems: **what order do we resolve in** (§4), and
**what happens when intents collide** (§5). §6 is honest about how far collision
handling can push us toward order-independence.

---

## 3. Principles & invariants

Carried over from the multi-character design, plus the ones this proposal adds:

- **One pipeline for all actors.** Every command — human or agent — still passes
  `check_preconditions()` → `apply_effects()`. Nothing here bypasses the gate.
- **Resolve order is explainable policy, not an accident.** Who wins a tie should
  be answerable by pointing at a rule, not at "they were earlier in the dict."
- **Default behavior == PR #30.** With no phase map, no fallbacks, and no
  contention, everything below must reduce to the current `initiative`-only sort.
- **Sequential mode is untouched.** All new machinery lives behind
  `turn_mode == "simultaneous"`.
- **Deterministic.** Same snapshot + same intents ⇒ same outcome. (Reinforces the
  engine's existing ban on `Date.now()`/`random` in this path.)
- **A seam, not an engine.** Favor a small, readable resolution policy that a
  first-year can trace over a general transaction system. The heavyweight option
  is documented (§6.1) but not the recommendation.

---

## 4. Ordering: from a field to a priority function

Replace the inline sort with a pluggable seam the game can override:

```python
def resolve_order(intents, game):
    """Return intents in resolution order. Default policy below; a Game
    subclass can override to express situational priority."""
    return sorted(intents, key=lambda intent: _resolve_key(intent, game))
```

The default key is a **tuple**, sorted lexicographically:

```python
def _resolve_key(intent, game):
    return (
        phase_rank(intent, game),                       # 1. WHAT kind of action
        -int(intent.character.get_property("initiative")),  # 2. WHO (PR #30's field)
        intent.gather_index,                            # 3. stable tiebreak
    )
```

Each component is a fallback for the one before it:

| Component | Question it answers | Source |
|-----------|--------------------|--------|
| `phase_rank` | *What kind* of action is this? (talk before move before fight) | action→phase map (§4.1) |
| `-initiative` | *Which character* is faster? | `get_property("initiative")` — unchanged from #30 |
| `gather_index` | Everything else equal, who decided first? | order added in `gather_intents` |

**This is the unification.** Phases (direction #2 in the brainstorm) aren't a
separate mechanism — they're the *first component* of the priority function
(direction #1). And they're **opt-in**: if a game defines no phase map,
`phase_rank` returns a constant for every action, the first tuple element is a
tie for everyone, and the key collapses to `(-initiative, gather_index)` — which
is exactly PR #30's stable initiative sort. Phases are *emergent*: they only
start mattering when a game (or dialog, §7) puts actions in different phases.

### 4.1 The phase map

A phase is a coarse category of action. The default ordering, lowest rank first:

```
communicate  <  move  <  manipulate  <  fight
   (say)        (go)    (get/drop/      (attack)
                         give/unlock)
```

`phase_rank` keys on the action — `ACTION_NAME` or the resolved `Action` class —
through a small, overridable map:

```python
DEFAULT_PHASES = {
    "speak": 0, "say": 0,                      # communicate
    "go": 1,                                   # move
    "get": 2, "drop": 2, "give": 2, "unlock": 2,  # manipulate
    "attack": 3, "hit": 3,                     # fight
}
def phase_rank(intent, game):
    actions = game.phases or {}                # empty -> everything ties at 0
    return actions.get(intent.action_name, len(actions) or 0)
```

Why this order is a sensible default: communication can't be "missed" by being
late, so it goes first; movement settles *where* everyone is before anyone
interacts; manipulation (picking things up, handing them over) happens among the
now-settled positions; combat resolves last, against a fully-arranged board. A
game is free to disagree — that's what the override is for.

### 4.2 Situational priority

Because `resolve_order` receives `game` and the full intent list, priority can
depend on the *situation*, not just static fields — the thing §2.1 couldn't do.
A game overrides the seam and inspects the intents:

```python
class DuelGame(Game):
    def resolve_order(self, intents):
        # On any turn where someone is attacked, the target resolves first
        # (a chance to dodge/flee) regardless of initiative.
        targeted = {i.target.name for i in intents if i.action_name in ("attack", "hit")}
        def key(intent):
            defending = intent.character.name in targeted
            return (phase_rank(intent, self), 0 if defending else 1,
                    -int(intent.character.get_property("initiative")), intent.gather_index)
        return sorted(intents, key=key)
```

"In different situations different characters should take priority" becomes a
plain function of the turn's intents and world state — exactly what the static
`initiative` field could not express.

---

## 5. Conflict & retry: claim → arbitrate → fallback

Limitations §2.2 (thin retry) and §2.3 (order-dependent state) are the same
problem seen from two sides: **two intents want the same thing, and only one can
have it.** Handle the collision explicitly and both improve at once.

The idea: before mutating anything, find out which intents *contend*, decide who
wins by the §4 priority, and give the losers something better than a bare failure.

```
resolve (revised):
  order   = resolve_order(intents, game)         # §4
  claims  = claim_pass(order)                    # §5.1  who targets what
  for intent in order:
    if loses_a_claim(intent, claims):            # §5.2  arbitrate by order
      handle_contention(intent, winner)          # §5.3  reason + fallback/retry
      continue
    route_and_apply(intent)                       # unchanged #30 path
  # §5.4 optional: re-resolve intents that failed on a PENDING prerequisite
```

### 5.1 Detect contention before mutating

A lightweight pre-resolve pass records the **target** of each intent — the item,
character, or destination the command is about. We don't need every `Action` to
declare a full read/write set (that's §6.1); the parser *already* resolves the
target when it matches the command, via `match_item` / `get_character` /
`was_matched`. The claim key is just that matched object (plus the verb's phase,
so `take gem` and `examine gem` don't falsely collide):

```python
def claim_pass(ordered_intents):
    claims = {}                          # resource -> first (highest-priority) intent
    for intent in ordered_intents:       # already in resolve order
        resource = intent.target         # the parsed item/character/destination
        if resource is None:
            continue                     # untargeted action (e.g. "look") — no claim
        claims.setdefault(resource, intent)   # first writer wins the claim
    return claims
```

This catches the common, painful cases — two characters taking one item, two
walking onto one single-occupancy tile, two giving to the same recipient — without
touching the precondition/effect core.

### 5.2 Arbitrate by the same priority order

Because `claim_pass` walks intents already in `resolve_order`, `setdefault`
records the **highest-priority** claimant as the winner. The winner is now a
*designed* outcome of the §4 policy — not "whoever mutated first." Lower-priority
claimants on the same resource are the losers, and crucially the decision is made
*before* any effect runs, so it no longer depends on mutation order. (§6 bounds
how complete this guarantee is.)

> **Implementation note (issue #42).** The shipped `turns.py` refines this to
> declare a contest lost only when the higher-priority claimant *actually
> secures* the resource (tracked in a `secured` map as the resolve loop runs),
> rather than purely from the pre-mutation claim. This keeps the loser's reason
> honest: if the designated winner's own command fails for an unrelated reason —
> most commonly the **player** grabbed the thing first, since the player resolves
> ahead of every NPC — nobody "won," so the later intent gets a plain failure
> instead of a fabricated "someone beat me to it." In the common case (two NPCs,
> the higher-priority one succeeds) the outcome is identical to the claim_pass
> above.

### 5.3 Conflict-aware failure & fallback

A loser is not handed `"I don't see it."` It gets a reason that names the
contention, and a way forward:

```python
def handle_contention(intent, winner):
    reason = f"{winner.character.name} got the {intent.target.name} first this turn."
    game.log_event(intent.character.name, "conflict",   # §5.5 — first-class event
                   summary=reason, payload={"command": intent.command,
                                            "winner": winner.character.name})
    if intent.fallbacks:                  # cheap: a backup the agent pre-chose at gather
        return route_first_workable(intent.character, game, intent.fallbacks)
    return route_with_retry(              # #30 path, but seeded with the REAL reason
        intent.character, game, intent.agent, intent.command, conflict_reason=reason)
```

Two improvements over §2.2:
- **Ranked fallback intents.** If the agent supplied a backup at gather time
  (`["take gem", "take coin"]`), the loser takes it immediately — no second LLM
  round-trip. This is an additive change to the decision seam: `Agent.decide` may
  return a `str` (today) *or* a ranked `list[str]` (new), and `gather_intents`
  stores the tail as `Intent.fallbacks`.
- **Informed reflection.** When there's no fallback, the existing reflect-retry
  runs, but seeded with the true conflict reason instead of the parser's generic
  message — so the agent reflects on "someone beat me to it," not on a phantom
  missing object.

### 5.4 Deferred re-resolution (optional, later stage)

Not every failure is contention. Some are **ordering false-negatives**: B's
`go north` fails the locked-door precondition only because A's `unlock door` —
which *will* succeed this turn — hasn't resolved yet. For these, run a second
resolve pass over *only the failed intents*, repeating until a pass makes no
progress (a fixpoint), capped at a fixed depth like the trigger cascade limit in
[multi-character-play.md](multi-character-play.md) §7. The pass must distinguish
**blocked-by-a-pending-prerequisite** (worth retrying) from **genuinely
impossible** (fail now) so it terminates. This is powerful but adds real
complexity, so it's a later stage (§8), not part of the core.

### 5.5 Emit `conflict` events, not bare failures

Contention is recorded on its own `conflict` channel rather than reused
`action_failed`, so PR #31's renderer can show it *as* contention — "Alice and Bob
both reached for the gem; Bob won" — a legible story instead of a stray failure
line. This is a small addition to the `Channel` set in
[output-and-trace-rendering.md](output-and-trace-rendering.md) §3.

---

## 6. Order-independence: how far we go

It's worth being precise about what §5 buys, because "simultaneous" tempts people
to expect *full* order-independence and this proposal deliberately stops short.

After the claim pass:
- **Independent actions are order-free by construction.** Two characters acting on
  different resources (different items, different rooms) never collide, so their
  relative resolve order can't change the outcome.
- **Single-resource contention is policy-ordered, not mutation-ordered.** Who wins
  the gem is decided in §5.2 before any effect runs, so it no longer depends on who
  the loop reached first.

What remains order-sensitive: **cascading effects not captured by a single
target.** `attack` knocks a victim unconscious and drops their whole inventory;
if another intent that turn wanted one of those dropped items, the claim key
(which saw only each command's direct target) didn't model the interaction. The
recommendation is to **accept policy-ordered resolution for these** and document
it, rather than build a general dependency tracker. Two heavier alternatives were
considered:

### 6.1 Transactional two-phase commit (considered, not recommended now)

Each `Action` declares a **read-set** and **write-set**; detect conflicts on the
turn-start snapshot (overlapping writes, or one writing what another reads),
arbitrate by §4 priority, then apply only the surviving effects "simultaneously."
This is the only approach that's *fully* order-independent, including cascades. The
cost is that every `Action` subclass must expose its read/write sets — a large,
invasive change to the precondition/effect core and a harder model for the
first/second-year audience to follow. Worth revisiting if simulations grow complex
enough to need it; out of scope for now.

### 6.2 Dry-run preconditions on the snapshot (folds into §5.1)

Before any mutation, run every intent's `check_preconditions()` against the
turn-start snapshot to drop the impossible ones up front — the "dry-run
preconditions" from [multi-character-play.md](multi-character-play.md)'s migration
checklist (step 8). Lighter than §6.1 and complementary to the claim pass; it can
be folded into §5.1 as an extra filter. **Caveat:** preconditions today emit
`parser.fail(...)` messages as a side effect, so a dry run needs a quiet mode — the
precondition helpers (`at`, `has_property`, `is_in_inventory`, …) already take a
`describe_error` flag that suppresses the message, which is the hook for this.

---

## 7. Live agent dialog (forward-looking)

Dialog is the motivating reason phases exist at all. The hook is already in §4:
`say`/`speak` sit in the earliest phase, so **speech resolves before movement,
manipulation, and combat** within a turn. What an agent says lands before anyone
acts on it.

**Reaction model: next turn.** A speech act resolves and is recorded as a
`conflict`-style event this turn; listeners in earshot **observe it in their View
next turn** and may respond. This keeps PR #30's core rule intact — exactly one
`decide()` per character per turn, everyone deciding against a stable snapshot —
and lets a conversation span turns naturally:

```
turn N    : alice  say "Want to trade the gem for my coin?"   (phase 0, resolves first)
            -> logged as a speech event; bob is in the room
turn N+1  : bob observes alice's offer in his View, decide() -> say "Deal."
turn N+2  : alice observes the acceptance, decide() -> give coin to bob
            bob (same turn or next)               -> give gem to alice
```

Phases stay opt-in here too: a turn in which nobody uses `say` has every intent in
one phase and resolves exactly like #30.

**Deferred: same-turn re-decide.** The livelier model — speech resolves, listeners
*re-observe and decide again within the same turn* so they can react immediately —
is the eventual endgame. It's deliberately out of scope because it breaks the
snapshot invariant (a second `decide()` pass per turn, with all the prompt-cost and
determinism questions that opens). Next-turn reaction gets believable conversation
with zero changes to the decision contract; same-turn is a later, separate design.

---

## 8. Build order

Sequenced so each stage ships independently and keeps the default behavior equal
to PR #30. Stop after any stage and the engine still works.

| Stage | Deliverable | Backward-compat check |
|-------|-------------|----------------------|
| **1. Ordering seam** | `resolve_order(intents, game)` + tuple key; `phase_rank` flat by default | Pure refactor of #30 — identical output |
| **2. Phases** | Action→phase map + opt-in `Game.phases`; default `communicate<move<manipulate<fight` | No map ⇒ all actions tie ⇒ #30 order |
| **3. Claim/arbitrate** | Pre-resolve claim pass (§5.1–5.2), conflict-aware reasons (§5.3), `conflict` events (§5.5) | No contention ⇒ no claims ⇒ #30 path |
| **4. Fallback intents** | `Agent.decide` may return `list[str]`; `Intent.fallbacks`; loser takes next workable | `decide` returning `str` unchanged |
| **5. Deferred re-resolution** *(optional)* | Fixpoint pass for pending-prerequisite failures (§5.4); optional dry-run preconditions (§6.2) | Off by default |
| **6. Live dialog** *(future)* | `say` as earliest phase + next-turn reaction (§7) | No `say` ⇒ single phase ⇒ #30 |
| **7. Far future** | Transactional two-phase commit (§6.1) / same-turn dialog | — |

Stage 1 is the only one that touches `turns.py`'s existing sort; everything after
it is additive.

---

## 9. Design invariants

- **Default == PR #30.** Flat phase map + no fallbacks + no contention reduces to
  the current `initiative`-only stable sort.
- **Sequential mode untouched.** All new machinery is behind
  `turn_mode == "simultaneous"`.
- **Preconditions never bypassed.** Claims and arbitration decide *who gets to
  try*; the gate still decides *whether it succeeds*.
- **Resolve order is explainable policy.** Every tie has a rule behind it.
- **Deterministic.** Same snapshot + same intents ⇒ same resolution.
- **A readable seam, not a transaction engine.** Complexity is opt-in and staged.

---

## Appendix: implementation sketches

Illustrative starting points, not final API. The code each stage touches:
`turns.py` (`resolve_order`, `gather_intents`, `run_simultaneous_round`,
`route_with_retry`, `Intent`), `npc.py` (`Agent.decide` ranked return),
`reporting.py` (the `conflict` `Channel`), `parsing.py` (exposing the matched
target so the claim pass can read it).

### Default resolution policy

```python
# turns.py
def resolve_order(intents, game):
    return sorted(intents, key=lambda intent: _resolve_key(intent, game))

def _resolve_key(intent, game):
    return (
        phase_rank(intent, game),
        -int(intent.character.get_property("initiative")),
        intent.gather_index,
    )

def phase_rank(intent, game):
    phases = getattr(game, "phases", None) or {}   # empty -> flat -> #30 behavior
    return phases.get(intent.action_name, len(phases))
```

### The claim pass

```python
def claim_pass(ordered_intents):
    """Map each contested resource to its highest-priority claimant.
    `ordered_intents` is already in resolve_order, so the first writer wins."""
    claims = {}
    for intent in ordered_intents:
        resource = intent.target           # parser-matched item / character / destination
        if resource is not None:
            claims.setdefault(resource, intent)
    return claims

def loses_a_claim(intent, claims):
    resource = intent.target
    return resource is not None and claims[resource] is not intent
```

### Intent, extended

```python
# turns.py — Intent gains an ordering index, the parsed target, and fallbacks.
@dataclass
class Intent:
    character: "Character"
    agent: "Agent | None"
    command: "str | None"
    gather_index: int = 0          # stable tiebreak (assigned in gather order)
    action_name: "str | None" = None   # for phase_rank
    target: "Thing | None" = None      # for the claim pass
    fallbacks: list = field(default_factory=list)  # ranked backups from decide()
```

### Notes

- **Where `target` comes from.** The parser already resolves the command's object
  while matching (`match_item`, `get_character`, exit lookup). The cheapest path is
  to surface that matched object on the intent during gather — no new parsing, and
  it stays `None` for untargeted commands like `look`, which correctly never claim.
- **Ranked `decide`.** `gather_intents` accepts either a `str` or a `list[str]`
  from `agent.decide(...)`; the head becomes `Intent.command`, the tail
  `Intent.fallbacks`. Existing scripted/mock agents that return a `str` are
  unaffected.
- **Testing.** Reuse #30's contested-gem scenario: assert the *winner* is the
  higher-priority intent regardless of `gather` order (proving §5.2 is
  order-independent), that the loser's logged reason names the winner (§5.3), and
  that a flat phase map reproduces #30's output byte-for-byte (§9).
