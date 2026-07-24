# Breaking the groundhog-day conversation loop (issue #778)

Two co-located agents who keep choosing `talk_to` each other re-run
substantially the same conversation forever: they never `perform`, never
advance their schedule, and burn the run budget. This spec fixes the two
mechanisms behind that, both found by reading the live-LLM run artifacts in
PR #783.

Related: #582 (conversation consequences), #636 (failure memory), #760 (the
run log this came out of).

## What the run data actually shows

The evidence is `run-20260724-194343-78858a` (R2 in PR #783): cast
`nina, jamal, grace, aiden, chris`, `claude-haiku-4-5`, seed 42,
`--max-cost 1.00`, `plan_mode: "schedule"`. Aiden Park and Chris Donnelly are
the seeded just-met roommates. They held five near-identical conversations at
~95-step gaps and agreed to get food in every one. The pair spent $0.635 of
the run's $1.0035; the cap tripped at step 977 of 1200.

Three findings, in the order they matter.

### 1. The commitment is generated and then discarded

Issue #778 proposes feeding reflections into the decide prompt. **They are
already there.** Aiden retrieved a `reflection` record in 244 of his 977
frames, and at step 499 his own reasoning reads:

> Chris just arrived and we have a genuine connection; it's good to check in
> with him, though I should be mindful that I've been using food plans to
> avoid meeting my roommate.

He then called `talk_to`. The diagnosis reaches the prompt, the model restates
it, and the behaviour does not change. So surfacing reflections is a no-op
fix, and the real gap is elsewhere.

It is in the #582 outcome pass. Extracting every `conversation_outcome` call
from R2's cassette: **16 of 18 returned `plans_changed: true` with a concrete
commitment.** Not vague ones —

- `"Pizza place near campus with Chris Donnelly in about 20 minutes"`
- `"Going out to grab food with Chris Donnelly at a restaurant a couple
  blocks away from campus, leaving right now"`

Every one evaporated. `apply_conversation_outcome`
(`backend/cognition.py:1295-1303`) passes the commitment only as a
`RevisionTrigger` detail into `maybe_revise_plan`. R2 ran the default
`plan_mode: "schedule"`, so the planner is `MockPlanner`, whose `revise()` is
`return plan` (`backend/planner.py:61-65`). The commitment string is **never
written to memory**.

The `relationship_note` half of the same response *is* written — importance
8.0, `_IMPORTANCE_LOCKED`. So the social half of #582 persists forever and the
intentional half is dropped on every run that does not opt into `--plan llm`.
That asymmetry is the loop: the stream accumulates *"Chris is a good person to
grab food with"* at importance 8.0 and never *"I agreed to leave right now to
get food."*

### 2. Retrieval self-amplifies toward the conversation partner

Each conversation mints three to four partner memories at importance 7-8: the
locked relationship note, plus `talk_to` observations that #583's scorer rates
7-8. By step 594 *all six* of Aiden's retrieved memories were about Chris, and
the *"you're getting sidetracked"* reflection (importance 6.0) had been
crowded out of the block entirely.

This spec mitigates the amplifier rather than solving it — see
[Out of scope](#out-of-scope).

### 3. Schedule advance is perform-gated, so a talking agent's day freezes

`schedule.advance()` fires from exactly one place: the latch-expiry pre-pass
at `backend/run_simulation.py:316-335`, and only when `st["on_plan"]` is true.

- A successful `talk_to` is an instantaneous command. It routes through
  `_settle_after_dead_talk` (`run_simulation.py:147-159`), which sets
  `on_plan = False` deliberately — #689's reasoning is that "a dead talk never
  completed a real schedule stop".
- A talk that opens a *real* conversation takes the same path first, so it
  carries the same `on_plan = False`. When the conversation and its playback
  hold end, settle expiry routes through the deviation branch and the pointer
  does not move.

So no conversation ever advances a stop. Aiden's stop 0 activity was literally
*"sizing up a brand-new roommate"* at Houston Hall — Reading Room: the
conversation **was** the scheduled activity, and it earned no credit. He stayed
on stop 0 for the whole run, `activity` was never set, and every frame rendered
the `"spending time"` placeholder (`run_simulation.py:551,614`).

`BEHIND_SCHEDULE` cannot rescue him either — it requires `st["path"]` to be
non-empty (`run_simulation.py:303-309`), so it only fires while *walking*. A
stalled but stationary agent never triggers it, and under `plan_mode:
"schedule"` it would be a no-op anyway.

## The fix

Two independent changes. Fix A stops discarding the intention #582 already
produces; Fix C lets the conversation count as the scheduled activity it was.
Fix C mechanically separates a looping pair; Fix A gives them a reason to
separate that survives into the next decide. Together they close both
mechanisms, and each is useful without the other.

### Fix A — the commitment becomes a PLAN memory

In `apply_conversation_outcome`, after the existing
`result.get("plans_changed") is not True` gate, when the model supplied a
non-empty `commitment` string, write it into the agent's own stream:

```python
agent.memory.add_plan(
    f"I agreed with {partner_name}: {commitment}",
    turn=step,
    importance=RELATIONSHIP_NOTE_IMPORTANCE,
)
# ...and lock it, like the relationship note above.
```

Design points, each load-bearing:

- **Importance 8.0 and locked, symmetric with the relationship note.** This is
  the one number in the change that must not be lowered. `add_plan`'s default
  is 5.0, and finding 2 shows that a 5.0 intention is buried by the 8.0 locked
  notes the same conversation produces — a 5.0 here silently reproduces the
  bug. Locking is the same argument #582 already made for the note: this is a
  deliberate high signal, not an importance the #583 scorer should re-guess.
- **Reuses the constant, adds none.** `RELATIONSHIP_NOTE_IMPORTANCE` and
  `_IMPORTANCE_LOCKED` both already exist for the note.
- **Zero new LLM calls.** The commitment is already in the response body that
  is currently thrown away.
- **No prompt change.** `PLAN`-kind records already render as decide-prompt
  bullets — the t=0 `"Plan: go to ..."` memory is one.
- **Only on a real commitment string.** The existing "fall back to the
  transcript as the trigger detail" behaviour is unchanged, but the transcript
  is *not* written to memory: a whole transcript stored as a "plan" is noise.
- **Written whether or not the planner does anything.** The write happens
  before `maybe_revise_plan`, so it lands under `MockPlanner` too. That is the
  entire point — R2's 16 commitments died because the only consumer was a
  no-op planner.

Mock byte-identity: `apply_conversation_outcome` returns early when the brain
cannot tool-call, and the mock never converses, so this is unreachable on the
bake path.

### Fix C — a conversation at your scheduled place completes that stop

Two small edits.

**1. Stamp the credit when a real conversation finishes.** In
`cognition._advance_conversation`, in the `if ac.convo.happened:` branch
(`cognition.py:1761-1765`) where both participants are already being marked
`conversing`, for each participant whose `char.location.name` equals its
`schedule.destination`:

- set `state[nm]["convo_at_stop"] = True`
- set `char.set_property("activity", schedule.activity)`

**2. Honour the credit at settle expiry.** In `run_simulation`'s latch-expiry
block (`run_simulation.py:322`), pop the flag and treat it as on-plan:

```python
credited = st.pop("convo_at_stop", False)
if st.get("on_plan", True) or credited:
    if char.agent.schedule.advance():
        ...
```

The flag is popped unconditionally so a stale credit cannot leak into a later
stop.

Design points:

- **Place-match reuses the existing rule.** The same
  `char.location.name == schedule.destination` test already decides `on_plan`
  at `run_simulation.py:547`. No new concept, one authority.
- **Setting `activity` fixes the `"spending time"` placeholder** on this path,
  which is #778's fourth bullet. It follows the established pattern: actions
  set their own activity (`PerformPenn` at `actions.py:133`, `WaitPenn` at
  `actions.py:182`).
- **Any real conversation at the scheduled place counts**, regardless of
  whether the stop's authored activity was social. Accepted cost: a short chat
  also completes a long non-social stop. Requiring partial time served was
  considered and rejected as a new tunable plus a re-anchoring problem for no
  demonstrated benefit.

Mock byte-identity by vacuity: the mock never converses, so `convo_at_stop` is
never stamped and the pre-pass sees exactly what it sees today. This is the
same argument #636 used.

### Expected effect on R2

Aiden's stop 0 is *"sizing up a brand-new roommate"* at Houston Hall — Reading
Room, and the step-263 conversation happens there. Under Fix C he advances to
College Hall at settle expiry (~step 298) instead of re-latching. Chris's stop
0 is *"trading first impressions with a stranger"* in the same room, so he
advances to Van Pelt — Book Stacks. The pair physically separates, which is
precisely what distinguishes the healthy baseline run (R1, Diego + Sofia, whose
second conversation genuinely progressed) from this one. Under Fix A, even a
still-co-located pair carries *"I agreed with Chris: leaving right now to grab
food"* into the next decide, which argues for `travel`, not another `talk_to`.

## Rejected: a general stop deadline

The more general fix — advance the stop whenever elapsed time exceeds the
planned minutes, whatever the agent did — was explored and rejected. It fails
twice:

- **It risks the byte-identical bake.** `st["stop_since"]` re-anchors on
  arrival, and the mock decides `perform` on the tick *after* arrival, so
  `perform_until == arrival + 1 + steps` while a deadline on `stop_since` fires
  at `arrival + steps` — one tick early, which drifts the bake. Gating on
  `not st["performing"]` fixes that case, and anchoring on stop-start instead
  of arrival fixes another, but the guard then stays correct only while no walk
  is longer than a stop's duration. That is a latent trap inside a guard whose
  whole contract is to be invisible to the mock.
- **It would not have fixed the reported agent.** `stop_since` re-anchors on
  *any* arrival, including a deviation. Chris spent about half the run
  oscillating between the Houston Hall lobby and the Reading Room, so he would
  have reset his own deadline indefinitely.

The residual ceiling is real and should be recorded as a `ponytail:` comment
where the credit is honoured: an agent frozen by repeatedly *blocked* actions,
rather than by conversation, still does not advance. File a follow-up issue if
a later live run shows that shape.

## Tests

Extend `godot-generative-agents/tests/test_conversation_consequences_582.py`,
which already has a fake tool-calling client and both single- and
both-participant harnesses.

Fix A:

- A `plans_changed: true` result with a commitment writes exactly one `PLAN`
  record, text carrying partner and commitment, importance 8.0, importance
  locked.
- The same result with **no** commitment writes no `PLAN` record (the
  transcript-as-detail fallback still applies to the revision trigger — the
  existing `test_missing_commitment_falls_back_to_the_transcript_as_detail`
  must keep passing).
- `plans_changed: false` *with* a commitment present writes no `PLAN` record.
- The write lands under a no-op planner — i.e. it does not depend on
  `maybe_revise_plan` returning `True`. This is the regression that reproduces
  R2.

Fix C:

- A finished real conversation at the agent's scheduled place stamps
  `convo_at_stop` and sets `activity` to the stop's activity.
- The same conversation held somewhere else stamps neither.
- One loop-level test: after a credited conversation, settle expiry advances
  the schedule pointer; without the credit it does not (pinning today's
  behaviour so the change is visible).

Byte-identity: the existing `test_mock_brain_runs_no_outcome_calls` plus
`test_bake_is_byte_identical` (3× `PYTHONHASHSEED`) are the guard. Both must
run before the PR.

## Out of scope

- **Cooldown escalation.** Making repeated `talk_to` against the same target
  decay or lengthen the cooldown was considered and dropped: if A and C
  separate the pair, it never binds. Revisit only if a later run loops with
  both fixes in.
- **The retrieval amplifier itself.** Fix A *mitigates* finding 2 by giving the
  intention the same weight as the chatter; it does not solve it. That locked
  8.0 relationship notes accumulate without bound, and can crowd every other
  memory out of the retrieved block, deserves its own issue.
- **Reflection-to-decide plumbing.** Already working; see finding 1.
- **`--plan llm`.** These fixes deliberately work under the default
  `plan_mode: "schedule"`. Making the LLM planner consume the commitment better
  is a separate question, and per #760 no run has yet produced both `--plan
  llm` and a conversation.
