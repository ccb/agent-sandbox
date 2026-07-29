# Telling an agent its stop is already done — #826 criterion 1

Status: design, 2026-07-29. Issue [#826] criterion 1 ("no single abandoned leg
exceeds 30 sim-minutes"). Companion to [`arrival-thrash-826.md`](arrival-thrash-826.md),
which covers the first half of #826 (shipped as #830).

## The one-sentence version

`run_simulation.step` already knows when a finished stop is being held back by
the next stop's `start_hour`; it throws that fact away, so the decide prompt
presents a completed errand as the agent's current, overdue objective — and the
agent walks back across campus to do it again.

## Evidence

Batch 5 (`run-20260728-211113-e68900`, on `main` after #826/#831/#837/#838)
scored one abandoned leg of **62 sim-minutes**, twice the criterion's ceiling.
It is Maya Chen's, and her cassette makes the whole chain legible.

Her plan (accepted at t=0, cassette entry 7):

| stop | place | `start_hour` |
|---|---|---|
| 4 | Houston Hall — coffee break and quick bite | 13 |
| 5 | College Hall — settle in for the seminar | **14** |

Her day, decide by decide (cassette entries 355–478):

| time | what the prompt told her | what she did |
|---|---|---|
| 12:48 | current stop: coffee at Houston Hall | `perform` coffee, 10 min |
| 12:58 | current stop: coffee, elapsed 10 min | `perform` coffee **again**, 5 min |
| 13:03 | current stop: coffee, elapsed 15 min | `travel` to Van Pelt (62 min) |
| 14:05 | current stop: coffee, **elapsed 77 min** | `travel` back to Houston Hall |
| 15:07 | current stop: coffee | `perform` coffee a **third** time |
| 15:22 | current stop: College Hall | `travel` to College Hall |

At 12:58 her first coffee `perform` completed. The stop was credited (#831), and
`advance(12)` was refused because stop 5 is anchored at 14 (#838) — the
`waiting_for_anchor` branch at `run_simulation.py:395`. She un-latched,
re-performed the same coffee, and at 13:03 `advance(13)` was refused again for
the same reason.

Nothing in the prompt says any of that. `decide_context.prompty` renders a held
stop exactly like a live one, so she read her own finished errand as debt and
said so in her tool call:

> "I'm way behind schedule on my coffee break (77 min for a planned 15) and my
> plan says I should be at Houston Hall for it, so I need to head there now."

She was obeying the context. Both of her bad moves quote it.

### What is *not* the cause

- **Not a missing travel budget.** `cognition.walk_minutes_line` (#830) priced
  every destination in every one of these prompts. At 11:50 she read
  `Houston Hall 27 min` and answered *"even though it's a long walk from here."*
  She had the number and accepted the cost.
- **Not mid-walk retargeting.** Still doesn't exist; the decide gate is
  `not st["path"]`. Every destination change sits on an arrival boundary.
- **Not an interruption.** The run has `react: false`.
- **Not #849.** Van Pelt and Houston Hall are different buildings, so this is a
  genuine retarget under `analyze_run.py`'s split (#850), not oscillation.

### A measurement trap this uncovered

`analyze_run.py` reported `#778 commit 0 commitment memories (none)` and
`#779 seeds 0 relationship memories (NONE)` for this run. Both are **artifacts**:
`runs/sim.db` holds 2145 memory rows but **zero** for this run id, so those
counters were reading an empty set, not a broken mechanism. #778's commitment
memories are plainly present in the run's own prompts. Batch 6 will be misled
the same way unless the tool distinguishes "zero" from "not recorded".

## Design

Thread the state that already exists to the prompt, and end the hold when its
reason expires.

### 1. `ScheduleMockClient.next_stop` (`cognition.py`, beside `_stop`:331)

A property returning the stop dict after the current one, or `None`. `advance()`
(`cognition.py:366`) already indexes `self.schedule[self.stop_index + 1]`
inline; both it and the new context read the next stop through this one
definition, following the `at_scheduled_stop` precedent ("one definition of
'on plan'", #826 review).

### 2. Persist the held flag (`run_simulation.py:395`, `:408`)

`waiting_for_anchor` is computed and discarded. Store it as
`st["waiting_for_anchor"]`, and clear it in the existing `if advanced:` branch
that already re-stamps `stop_since`.

### 3. Thread it to the decide (`run_simulation.py`)

The same path `stop_since` takes today, which is the complete set of sites —
found by grepping `stop_since` **inward**, the enumeration discipline #826 got
wrong twice:

- `_decide_one` signature `:80` and its docstring `:89`
- the `observe_and_decide` call `:113`
- both decide sites: parallel `:452`, serial `:529`

### 4. `decide_context_block(..., waiting=False)` (`cognition.py:1182`)

When `waiting`, pass `finished=True` plus the next stop's place, activity, and
start hour (formatted off the clock, e.g. `2 PM`), and `next_due` =
`clock.hour_at(step) >= start_hour`.

### 5. `decide_context.prompty`

`finished` **replaces** the elapsed clause rather than adding to it — that
clause is the sentence Maya read as debt:

```jinja
Your plan's current stop: {{ activity }} at {{ place }}{% if minutes %} (planned ~{{ minutes }} min){% endif %}.
{%- if finished %} You have already finished this stop.
  {%- if next_place %} Your next stop is {{ next_activity }} at {{ next_place }}
    {%- if next_due %}, due now.{% else %}, starting at {{ next_hour }}.{% endif %}
  {%- endif %}
{%- elif elapsed %} This has been your current stop for {{ elapsed }} min.{% endif %}
```

The `next_due` branch is reachable and load-bearing: the retry below is skipped
while an agent is performing something else, so a passed anchor can still be
current, and printing "starting at 2 PM" at 2:30 PM would be exactly the #812
false-time-word class.

Per the repo's prompt convention, the same change updates the
`decide_context.prompty` row of
`godot-generative-agents/backend/prompt_templates/README.md`, which currently
documents the elapsed clause as unconditional.

### 6. End the hold at the hour it named (`run_simulation.py`, same pre-pass)

Today the held `advance()` is retried **only when a perform completes**. Maya
had no perform for two hours, so at 14:05 the anchor hour had already passed
and the pointer was still parked. Add: if `st["waiting_for_anchor"]` and the
agent is not performing, retry `schedule.advance(current_hour)`; on success
stamp `stop_since` and clear the flag.

This keeps #838's hold — it does not move the gate to the perform side — and
only makes the hold end when the clock it cited arrives.

## Why the prompt, and not the mechanism

Two alternatives were considered and rejected:

- **Advance the pointer and let `start_hour` gate *performing* instead.** The
  agent would learn its next objective immediately and could walk there and
  wait. Rejected: it re-opens a mechanism merged the day before, and invites
  agents to arrive an hour early everywhere and burn ticks on `wait`.
- **A hard travel gate** — refuse any leg whose walk cost exceeds the time left
  before the next anchored stop. Guarantees criterion 1 by construction, but
  blocks legitimate deviation and piles a second policy onto
  `travel_destination_allowed`, which #856 has just changed. Held in reserve: if
  batch 6 still breaks the ceiling with truthful context, this is the next lever.

The evidence favors the prompt fix. Every bad decision in the trace cites the
context's own claims, so an agent reading a truthful block is the cheapest
thing that could work — and it is verifiable offline before any live spend.

## Bake safety

No authored Penn stop or persona sets `start_hour` (`grep -c start_hour
world_data_upenn.yaml personas/*.yaml` → 0), so `waiting_for_anchor` is never
true on the mock path, the new template branch never renders, and the committed
bake cannot move. Confirm with `cmp` against the merge base, not only the
3-seed tripwire — `test_bake_is_byte_identical` has no committed golden and
proves seed-determinism alone (see #640).

## Verification, in cost order

Each gate before the next:

1. `godot-generative-agents/tests/test_decide_context.py` (already byte-pins
   this template): held renders both sentences with the right hour; **not**-held
   renders today's string unchanged; a passed anchor renders "due now".
2. A pre-pass test in `tests/test_start_hour_advance_838.py` (which already owns
   the anchor gate): a credited-held agent with no perform advances *at* the
   anchor hour, and not before it.
3. **Mutation check on every test above** — revert the fix, the test must go
   red. Batch 5's guard test looked fine and passed just as happily with the fix
   reverted, because it looped over the constant it was meant to pin.
4. Bake byte-identity by `cmp`, per "Bake safety" above.
5. **Offline cassette A/B (~$0.20).** Replay Maya's 13:03 and 14:05 decides from
   `run-20260728-211113-e68900` with the new context, one arm per signal: does
   she still leave for Van Pelt, and does she still turn around? This is the
   gate before spending on a live run.
6. Live: batch 6 and batch 7. Read `retarget_abandoned_minutes_max` ≤ 30 off
   `analyze_run.py` (#854), plus #826's regression guard — nobody still walking
   more than 10 sim-minutes when the run ends.

## Non-goals

- **No better distance estimate.** The Chebyshev lower bound still under-reports
  ~2× on this campus; the ponytail note in `walk_minutes_line` records the BFS
  upgrade path. Maya's decisions cited her plan, not the distance.
- **No mechanical fix for the repeated `perform`.** She did the same coffee three
  times; truthful context should remove the reason. Measured in batch 6, not
  gated on.
- **#849 stays with #856.** Same-place oscillation is a different mechanism and
  must not share this metric.

## Risk

Any prompt change rehashes `recording.request_key`, so every pre-existing
cassette stops being byte-identical for #715's re-run bridge. Unavoidable for a
prompt fix; note it in the PR.

[#826]: https://github.com/ccb/agent-sandbox/issues/826
