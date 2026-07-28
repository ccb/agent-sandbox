# “Right now” means next: immediate conversation commitments

Design for [#829](https://github.com/ccb/agent-sandbox/issues/829). Builds on
conversation consequences ([#582](https://github.com/ccb/agent-sandbox/issues/582),
PR #610), durable commitment memories (#778), the clock-anchor fix
([#821](https://github.com/ccb/agent-sandbox/issues/821), PR #828), and the
clock-gated advance added by [#838](https://github.com/ccb/agent-sandbox/issues/838)
(PR #842).

**Status:** implemented on `fix/immediate-commitment-preemption-829`.

## Decision

An agent may say “now” casually in ordinary dialogue, but when its structured
post-conversation outcome classifies a concrete commitment as **immediate**, that
classification is binding:

> Finish the conversation, end the current stop, and make the commitment the
> next stop the agent executes.

“Immediate” does not mean interrupting a line of dialogue or the viewer’s
playback hold. It means the first action boundary after the completed
conversation. A future or unspecified commitment continues to use ordinary
tail-only plan revision.

This chooses issue #829’s first option. Continuing to emit, remember, and
retrieve “right now” while leaving execution unchanged is not a coherent
contract for a visible simulation.

## The failure in the current seam

`apply_conversation_outcome()` does two useful things when
`plans_changed == true`:

1. writes the commitment as a durable PLAN memory (#778); and
2. calls `maybe_revise_plan()` with a `CONVERSATION` trigger (#582).

`maybe_revise_plan()` then protects every stop through
`schedule.stop_index`:

```python
plan.stops[: after + 1] + proposed.stops[after + 1 :]
```

That protection is the right default. It prevents a planner from rewriting the
activity currently visible on screen. It is also why a revision cannot make an
immediate commitment immediate by itself:

- the planner is not told which stop is current;
- the revised commitment is not required to be the first unstarted stop; and
- even if it is first in the tail, the running activity keeps its original
  `perform_until`, so the pointer may not reach that tail for another hour.

The motivating Diego trace shows all three failures together. The commitment
memory and revised text survived; execution did not move until 10:56.

Recent changes do not close this:

- #821/#828 preserves a stop’s `start_hour` and checks the planner’s arithmetic;
- #838/#842 prevents `advance()` from entering a future anchored stop early;
- #831/#836 and #837/#843 determine when an activity or conversation earns stop
  credit.

None gives a conversation outcome authority to end the current activity or
name the first stop after it.

## Invariants

The design keeps these existing rules:

1. **The executed/current stop is never rewritten.** It remains in the plan’s
   protected prefix with the text and place it had while visible.
2. **A plan remains an intention, not movement.** Preemption changes which stop
   is next; the resulting travel or activity still goes through the parser and
   action preconditions.
3. **The conversation remains visible through playback.** No resident walks
   away while its last line is still being displayed.
4. **The mock path is unchanged.** The mock does not hold real conversations,
   so no immediate outcome is classified and the committed bake stays
   byte-identical.
5. **Failure is conservative.** If the planner produces no usable changed tail,
   keep the commitment memory but do not end the current activity.
6. **No new mid-walk cancellation.** The actionable preemption path requires the
   participant to have an activity latch that the normal pre-pass can consume.
   Reactive conversations that begin while walking (#370) have no such latch;
   they retain the revised tail and commitment memory, but do not cancel the
   in-flight path. That separate policy needs replay evidence before changing.

The apparent collision with `daily-planning.md` §8 is resolved by distinguishing
**rewriting a stop** from **finishing one at an event boundary**. An immediate
conversation outcome does not mutate the current stop. The real conversation
credits that stop through the existing #778/#831/#837 path, and the immediate
outcome shortens its execution window so the already-earned credit can be
consumed after playback.

## Implemented contract

### 1. Classify urgency structurally

Add a required `commitment_timing` enum to `CONVERSATION_OUTCOME_TOOL`:

```json
{
  "commitment_timing": "immediate | scheduled | unspecified"
}
```

- `immediate`: the participant agreed to start as soon as this conversation
  ends — “now”, “right now”, “let’s go”.
- `scheduled`: the commitment names a later time or an explicit delay.
- `unspecified`: plans changed, but the transcript does not establish when.

For `plans_changed == false`, the value must be `unspecified`. An immediate
classification is actionable only with a non-blank `commitment`.

Do not infer this later with a regex over commitment prose. “Not right now”,
quoted speech, and “I need it now, but let’s meet at two” make string matching
both brittle and hard to test. The outcome call already reads the whole
transcript and is the existing classification seam.

The prompt and tool description should say that `immediate` is a behavioral
promise, not a synonym for “important”. Repository convention requires pinning
the exact `.prompty` render and updating
`backend/prompt_templates/README.md`.

### 2. Tell the planner where execution actually is

Extend `RevisionTrigger` with backward-compatible execution context:

```python
@dataclass(frozen=True)
class RevisionTrigger:
    reason: str
    step: int
    detail: str = ""
    current_stop_index: int | None = None
    urgency: str = "normal"
```

`maybe_revise_plan()` already reads `schedule.stop_index`; it should copy that
value onto the trigger **before** calling `planner.revise()`. This removes the
current mismatch where cognition knows the protected boundary and the planner
does not.

For an immediate conversation outcome:

```python
RevisionTrigger(
    CONVERSATION,
    step,
    commitment,
    current_stop_index=after,
    urgency="immediate",
)
```

`LLMPlanner.revise()` should render the stops with explicit status:

```text
0. completed: ...
1. current: ...
2. upcoming: ...
```

For `urgency == "immediate"`, use a dedicated revision tool whose response is a
tail, not another ambiguous full-day list:

```json
{
  "next_stop": {
    "place": "...",
    "activity": "...",
    "emoji": null,
    "minutes": 20
  },
  "later_stops": []
}
```

Its instruction is:

> Turn the immediate commitment into `next_stop`. Return only what remains
> after the current stop; do not repeat completed or current stops.

The planner validates `next_stop` and `later_stops` with the same duration and
known-place checks as `_minute_from_user()`, then constructs the proposal
itself:

```python
stops = (
    plan.stops[: current_stop_index + 1]
    + [next_stop]
    + later_stops
)
```

This is stronger than asking the model to reproduce a full list and trusting
that the commitment happens to land at `after + 1`. The response shape names
the semantic role directly, while cognition still owns the protected prefix.

Normal revisions keep their existing behavior. `MockPlanner.revise()` remains a
no-op.

This is a small extension of the existing planner protocol, not a second
planner call. The same one-call-per-participant outcome and one revision call
already paid by #582 remain the ceiling.

### 3. Commit the tail before granting preemption

Change `maybe_revise_plan()` from a bare boolean to a small result:

```python
@dataclass(frozen=True)
class PlanRevisionResult:
    changed: bool = False
    immediate_next: bool = False
```

The few callers that inspect the existing boolean switch to `.changed`; most
current trigger sites ignore the return value. Do not give the dataclass a
surprising truthiness overload.

`immediate_next` is true only when all of these hold:

1. the trigger requested immediate urgency;
2. the immediate revision tool returned a valid `next_stop`;
3. the guarded plan has that stop at `current_stop_index + 1`; and
4. committing that guarded tail changed the running schedule.

Before committing an immediate first-tail stop, clear its `start_hour`.
`start_hour` means “do not advance before this hour” after #838; retaining a
future anchor on a stop explicitly classified as starting now would recreate
the bug at the next seam. Clearing it is not a heuristic: immediacy supersedes
the old future time for this revision.

The existing prefix graft remains as defense in depth:

```python
kept_prefix = plan.stops[: after + 1]
revised_tail = proposed.stops[after + 1 :]
```

The immediate revision tool returns only `next_stop` and its later tail.
`LLMPlanner` places that tail after the current index deterministically;
cognition still reapplies the guard and does not trust a model to rewrite
history.

If the planner returns an empty, malformed, unchanged, or too-short plan,
`immediate_next` is false. The commitment memory still lands, exactly as #778
requires, but execution is not interrupted for a stop that does not exist.

### 4. End the current stop at the conversation boundary

Return the revision result from `apply_conversation_outcome()` through
`_finish_conversation()` to `_advance_conversation()`, which already owns
`state`. Each participant is independent: one may classify the agreement as
immediate while the other does not.

When `immediate_next` is true **and the participant has an existing activity
latch**, set that latch to expire on the conversation’s end step:

```python
state[name]["perform_until"] = step
```

Do not advance the schedule here. `_advance_conversation()` keeps
`state[name]["conversing"] = True` for the playback hold, and the normal
schedule pre-pass already refuses to consume an expired activity while
`conversing`. On the first tick after release it:

1. sees the expired latch;
2. consumes the conversation’s existing `credit_stop`;
3. advances to the newly first upcoming stop; and
4. makes the agent decision-due.

This reuses the single schedule-advance authority instead of adding a second
pointer mutation inside cognition. It also composes with #837’s successful
`talk_to` latch and with settled `maybe_converse` participants.

A #370 conversation can pin a resident mid-walk, where `performing` is false
and no `perform_until` consumption site exists. In that case do not manufacture
credit, cancel the path, or move the pointer. The plan and memory still revise,
but `immediate_next` is not actionable at this boundary. This is the same
deliberate distinction #837 makes: loosening the credit guard writes an inert
flag and blurs a real activity boundary. A follow-up may define “abandon an
in-flight journey” if a live trace shows immediate commitments arising there.

The transition is:

```text
perform current stop
  → converse
  → outcome: immediate tail committed, current latch expires
  → playback hold
  → normal pre-pass advances once
  → travel/perform the commitment through ordinary action gates
```

## Why this is not general priority scheduling

This design adds one priority level at one explicit event boundary. It does not
introduce a heap, arbitrary stop priorities, deadlines, or mid-walk
interruption:

- agents are already not re-decided while walking (#826);
- the rejected general stop deadline in `run_simulation.py` remains rejected;
- scheduled commitments continue to use `start_hour`;
- only a completed, model-classified conversation can request this transition.

That narrowness matters. A general queue API would have to define conflicts
between clock anchors, deadlines, travel in progress, user interventions, and
multiple commitments. #829 has evidence for only one rule: a concrete agreement
to start now should be next after the conversation.

## Rejected alternatives

### Treat “right now” as non-binding

Prompting residents never to say “now” would reduce the visible contradiction,
but it would also discard a useful social behavior the system already extracts
as a plan change. The structured outcome pass gives a cleaner contract: casual
dialogue remains free, while classified commitments are honored.

### Search commitment text for `now`

Cheap but semantically wrong for negation, quotations, and later times. It also
duplicates classification already performed by the outcome model.

### Rewrite only the revision prompt

Putting the commitment first in the returned tail is necessary but
insufficient. The current activity can retain an hour-long `perform_until`, so
the first tail stop would still not run now.

### Mutate `stop_index` in `apply_conversation_outcome`

That creates a second schedule-advance authority, can move an agent while
dialogue is still playing, and bypasses the #831/#837 credit rules and #838
clock gate. Expiring the latch and letting the normal pre-pass advance is
smaller and preserves those invariants.

### Rewrite the current stop

This is the exact desynchronization `daily-planning.md` §8 prevents: the replay
would show one activity while the plan/API claims another. The current stop is
finished, retained as history, and followed by a new stop instead.

## Testing

All implementation tests are offline with fake outcome clients and planners.

1. **Outcome schema and prompt**
   - exact property set, required enum, and enum values;
   - exact rendered `.prompty` output;
   - immediate without a non-blank commitment is non-actionable.
2. **Planner execution context**
   - `maybe_revise_plan()` stamps the real `schedule.stop_index` before the
     planner call;
   - the LLM revision prompt labels completed/current/upcoming stops;
   - the tool returns `next_stop` plus `later_stops`, never a reproduced prefix;
   - an immediate revision puts `next_stop` at `after + 1`.
3. **Prefix safety**
   - executed and current stops remain byte-for-byte equal;
   - only the unstarted tail changes;
   - the immediate stop’s stale `start_hour` is cleared;
   - malformed/no-op/short revisions return `immediate_next == false`.
4. **Conversation-to-execution integration**
   - begin with a long-running current activity;
   - complete an immediate agreement;
   - assert the pointer does not move during playback;
   - release playback and assert the normal pre-pass advances exactly once;
   - assert the next decision travels to or performs the commitment stop.
5. **Non-immediate control**
   - the same changed plan with `scheduled` timing does not shorten
     `perform_until`;
   - its `start_hour` remains intact and #838 gates it normally.
6. **Two-participant disagreement**
   - only the participant whose own outcome is immediate gets an expired latch;
     the other participant keeps its current activity.
7. **Reactive mid-walk control**
   - an immediate outcome without an activity latch does not cancel `path`,
     advance the pointer, or invent stop credit;
   - its commitment memory and revised tail still persist.
8. **Mock/determinism**
   - existing mock conversation and bake guards remain unchanged;
   - direct Penn bake comparison against the merge base is byte-identical, not
     only seed-deterministic.

Changing the outcome tool schema and prompt invalidates recorded outcome
requests because `recording.request_key` hashes both. That is expected for
pre-change live cassettes and should be called out in the implementation PR.

## Live validation

Offline tests prove the queue transition, not that a model classifies the right
transcripts. Validate against the next #760 live batch with:

- an outcome whose commitment says “now” or “right now” is classified
  `immediate`;
- the revised plan’s first unstarted stop represents that commitment;
- departure/action begins on the first decision after playback, not at the old
  current stop’s deadline;
- Diego-like repeated immediate commitments fall from three to at most one.

The useful latency is:

```text
first commitment action step - conversation outcome step
```

It should equal the remaining playback hold plus at most one decision tick. A
non-immediate commitment is excluded from this metric.

## Files changed

Paths below are relative to `godot-generative-agents/` unless stated otherwise.

| file | change |
|---|---|
| `backend/cognition.py` | timing enum, revision result, immediate outcome plumbing |
| `backend/planner.py` | status-aware revision prompt and immediate-tail tool |
| `backend/prompt_templates/conversation_outcome.prompty` | define timing semantics |
| `backend/prompt_templates/README.md` | update prompt usage contract |
| `tests/test_conversation_consequences_582.py` | schema/prompt and non-immediate controls |
| `tests/test_immediate_commitment_829.py` | prefix, playback, advancement, and failure regressions |
| `../text_adventure_games/planning.py` | backward-compatible trigger execution context |
| `../docs/design/daily-planning.md` | record the conversation-boundary exception to §8 |

This is backend-owned work under the current `CLAUDE.md` review convention:
changes under `godot-generative-agents/` are reviewed by the Godot/geo owners,
and all feature work targets `main`.
