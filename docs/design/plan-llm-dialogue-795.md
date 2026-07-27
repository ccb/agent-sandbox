# Dynamic LLM planning *and* dialogue — design for issue #795

**Issue:** [#795](https://github.com/ccb/agent-sandbox/issues/795) — "The #787
default day has no co-settled moments — `--plan llm` makes conversation
structurally impossible (0 eligible pair-steps vs 399)".

**Status:** design approved 2026-07-26; implementation not started.

**Related:** `docs/design/daily-planning.md` (the #83 planner design, cited by
`backend/planner.py` as "§6-§9"). This spec implements part of its §10 time
mapping, which was specified and never built.

---

## 1. Problem

Since #787, `--plan` defaults to `auto`, which resolves to `llm` under
`--brain llm`. On the default 3-agent Penn cast the resulting day contains **no
moment where any two agents are settled in the same room**, so the proximity scan
in `maybe_converse` never sees an eligible pair. Conversation is not rarer — it is
impossible.

Measured on the same cast (`diego, tanaka, sofia`), same seed (42), same 1200
steps, `--decide-workers 0`; the planner is the only difference:

| | R1 `--plan schedule` | R7 `--plan llm` (the default) |
|---|---|---|
| co-settled pair-steps | 399 | **0** |
| conversations | 3 | **0** |
| decisions | 47 | 18 |
| cost | $0.3465 | $0.1283 |

Every downstream feature that depends on conversation — #582 outcomes, #778
commitments, #779 relationship seeding, the conversation feed, relationship notes,
and the persona library's ten authored interaction threads (#762/#774) — is
silently inert on the default path.

## 2. Root causes

The issue hypothesised that the planner "packs each agent's day efficiently and
independently". That is true but not actionable. Tracing the code gives four
specific causes, three of which are fixable in the planner.

### RC1 — the commitment memory reaches only the day outline

`attach_agents` (`godot-generative-agents/backend/cognition.py`) already seeds each
agent's authored `schedule:` as a t=0 PLAN memory at importance 5.0, explicitly
commented *"Done before planning so a generative planner can reason over them."*
Tanaka's t=0 memory reads:

> Plan: go to Irvine Auditorium and setting up for an afternoon guest lecture.
> Today's stops: setting up for an afternoon guest lecture at Irvine Auditorium,
> then holding a problem session for her physics class at Williams Hall —
> Classroom A.

Retrieval takes the top 6 and at t=0 the stream is tiny, so it *is* retrieved. The
bug is where it goes (`backend/planner.py`, `LLMPlanner.generate`):

```python
mem   = self._memory_block(memory, "what matters for my day today", turn=0)
day   = self._day_outline(persona_text, mem)   # memory stops here
hours = self._hourly(persona_text, day)        # sees only 4-6 summaries
stops = self._minute(persona_text, hours)      # picks place + steps, blind
```

Memory reaches only `_day_outline`. Every *place* and *duration* is chosen two
lossy summarisation hops downstream — "afternoon: teaching and student time", and
Irvine Auditorium is gone. **Under `--plan llm`, Tanaka does not know she is
giving a lecture.** Her `persona:` blurb never mentions it; the obligation lives
only in `schedule:`, which the planner is not shown.

### RC2 — the minute level has no clock and no budget

`_window_line()` ("This simulation runs from 08:00 to 14:00 today") is wired into
`_day_outline` and `_hourly` but **not** `_minute`. The full minute-level user
message is:

```
{persona}
Your hourly plan: {hourly}.
Known places: {...}.
Turn it into concrete stops.
```

No run length, no step→time conversion, no notion that travel costs anything. So
every `steps:` value is an ungrounded guess in a unit the model has no intuition
for. Worse, `steps` is the **perform** duration only: `run_simulation.py` sets
`perform_until = step_idx + steps` and charges the walk *on top*, unbudgeted. In
R7 one cross-campus walk cost Diego 136 steps — 11% of the run.

`docs/design/daily-planning.md` §10 already specifies the fix ("Hourly→minute
decomposition just makes each hour's stops' `steps` sum to that hour's step
budget"). It was never implemented, and §10 does not account for travel either.

### RC3 — nothing about the world is publicly knowable

Tanaka's guest lecture exists only inside her own schedule and memory. No other
agent can learn of it, so nobody can independently choose to attend. There is no
world-level announcement concept. Under `--plan schedule` this did not matter
because the author hand-tuned the stops to intersect; under `--plan llm` the only
shared anchors are ones every agent can independently know about.

### RC4 — conversation requires co-*settlement* (context; not fixed here)

`maybe_converse`'s pair scan requires both agents `performing and not path`.
Co-location is not enough: `travel` moves `char.location` immediately and the tile
path is the animation catching up (`run_simulation.py:526`), so in R7 Diego was
*in* the Kamin Gallery for 136 steps while still walking to it. Long authored
dwell times (Tanaka 800 steps at Irvine, Sofia 220 in the gallery) are what
absorbed arrival jitter under `--plan schedule`. This is not a bug and this spec
does not change the gate; RC2's grounding is the lever on it.

## 3. Goal and non-goals

**Goal.** A default `--brain llm` run makes conversation *possible* again, and
reports when it did not happen. Free play is preserved: no agent is forced to
meet another.

**Explicit non-goals:**

- **Not** guaranteeing a rendezvous. Turning `meetings:` into a hard planner
  constraint would need clock-anchored stops (a `Stop` schema change, a driver
  change) and would undo what #787 was for.
- **Not** reverting #787's default.
- **Not** changing the co-settlement gate, `Stop`, the driver, or `MockPlanner`.
- **Not** enabling `--react` by default. It is a real lever on RC4 and it is
  already built, but it spends money per consult and is orthogonal to the planner.
  Revisit if the live run shows RC1-RC3 were not enough.

### Rejected: showing the planner other agents' plans

The obvious fix — plan the cast in order and show each agent the stops already
committed by the ones before it — was rejected as **epistemically dishonest**. An
agent would be acting on knowledge nobody told it, which breaks the premise that
agents act on what they perceive and remember. It is also unnecessary: the
authored world already puts Diego and Sofia in the same gallery because each has
their own reason to be there.

### Rejected: seeding `meetings:` as shared arrangements

`meetings:` blocks (label, place, participants, authored dialogue) are already
parsed and cast-validated by `build_world`, and the injector stands down entirely
under `--brain llm` — so the data is discarded exactly when the model plans. But
they are **scripted scenes, not prior agreements**. "Diego shows Sofia around the
gallery" pairs a grad student with a first-year who is deliberately authored
knowing nobody (`sofia.yaml` has no `relationships:` block). Seeding "Sofia and I
are meeting at the gallery" into both streams would invent a relationship that
does not exist. Honestly translated, a meeting anchor is just each participant
separately intending to be at that place — which is RC1's commitment memory,
already seeded.

## 4. Design

Four parts. Parts 1-2 are the fix; parts 3-4 are how we know it worked.

### Part 1 — planner plumbing (RC1 + RC2)

Entirely within `backend/planner.py` and one `.prompty` file. No new classes, no
driver change, no data-model change.

**Carry memory to every level.** Pass `mem` into `_hourly` and `_minute` as well
as `_day_outline`. Three signatures, one extra rendered line each, reusing the
existing `_memory_line(mem)` helper.

**Ground the minute level.** `_minute` gains `_window_line()` (already written,
never called there) plus a budget line, and the tool answers in **minutes**:

- Rename `MINUTE_TOOL`'s `steps` property to `minutes`, updating its description.
  A model has no intuition for "a step" and a very good one for "90 minutes at the
  library".
- Convert in `_minute_from_user`, where the `steps > 0` validation already lives:
  `clock.steps_for_seconds(minutes * 60)` (`SimClock.steps_for_seconds` exists).
  With no clock — the tests that omit it — `minutes` is read as steps, preserving
  today's behaviour.
- `Stop.steps` stays the internal unit, so nothing downstream changes.

The budget line, in units the model can act on:

```
This simulation runs 08:00-14:00 today (about 6 hours).
`minutes` is time spent AT a place — travel is charged on top of it,
and crossing campus can take about 45 minutes.
```

The travel figure must be **computed, not guessed**: the median pairwise walk
length over `known_places` from the world map, converted to minutes, computed once
at planner construction. When no map is available the clause is **omitted
entirely** rather than shipping a fabricated constant. This requires threading the
world map (or a precomputed median) into `LLMPlanner.__init__` alongside
`known_places`.

**Fix the system prompt.** `plan_system.prompty` still says *"a resident of the
town of Smallville."* The world has been Penn since #481. One line, and it is
actively lying to the model.

`revise()` already calls `_memory_block` itself and routes through
`_minute_from_user`, so it inherits both the memory and the grounding for free.

### Part 2 — public events (RC3)

**Data.** A new top-level `events:` list in the world YAML, sibling to `cast:` and
`locations:`:

```yaml
events:
- label: a guest lecture on gravitational waves
  at: Irvine Auditorium
  when: this afternoon
  host: Professor Tanaka        # optional
```

`label`, `at` and `when` are required; `host` is optional. `when` is free prose,
deliberately not clock-coupled — it becomes memory text, not a scheduling
constraint.

**Validation** in `build_world`, mirroring the existing `meetings:` rules: an
unknown `at` (not a world location) or unknown `host` (not a known persona)
raises; an event whose `host` is not in the *active* cast is dropped, exactly as a
meeting is dropped when a participant leaves the cast. Host-less events always
survive.

**Seeding.** A new `public_event.prompty` renders one t=0 observation —

> There's a guest lecture on gravitational waves at Irvine Auditorium this
> afternoon, hosted by Professor Tanaka. It's open to anyone.

— seeded through the existing `seed.seed_relationships` path, tagged
`{"seed", "event"}`, at importance **4.0**: above a background acquaintance (3.0)
and below the agent's own commitments (5.0). Importance is **locked** against #583
rescoring the way #794 locks relationship seeds.

**Not seeded to the host.** Tanaka's own schedule already gives her the commitment
at 5.0; the noticeboard phrasing would put "hosted by me" in her memory.

**Gated on `planner_client is not None`.** Frames carry retrieved memories
(`run_simulation.py:467`, `st["memories"] = memories_for_frame(...last_retrieved)`),
so seeding into every agent shifts the top-6 retrieval, changes `st["memories"]`
and changes the mock bake. `MockPlanner` replays the authored schedule and ignores
memory entirely, so seeding there perturbs the replay while informing nothing.
Gating on the LLM planner's presence is precise about why the memory exists, keeps
the bake untouched, and matches how `score_new_memories`, `maybe_reflect` and
`conversation_enabled` are already gated.

**Penn authoring: one event** — Tanaka's Irvine lecture, nothing else. It gives all
three of the default cast a legitimate reason to converge on one room: she is
obliged to be there, Diego's seeded #779 edge already says he sits in on her
lectures, and Sofia is curious about everything. A second event is a four-line
YAML addition if the live run shows one is not enough.

Note the division of labour: RC3 makes the Irvine convergence *structural*, while
the Diego-Sofia gallery encounter is recovered only *probabilistically* by
RC1+RC2 — both already intend the gallery, and whether their windows intersect
depends on the durations the model now picks with grounding.

### Part 3 — the co-settled metric

**Definition.** A *co-settled pair-step* is one step in which two agents are both
settled (`performing and not path`) and share a `char.location`. Counted **before**
the cooldown/busy/conversing filters: this measures *opportunity*, not
eligibility. A pair mid-conversation or on cooldown still counts, which is what
makes the 399-vs-0 comparison meaningful.

**Counter.** A plain O(n²) pair scan in `run_simulation.step()` after movement
resolves, filling a caller-owned out-dict — the pattern `decide_info` already
uses. At ~25 agents that is 300 pair tests per tick, the budget `maybe_react`'s
existing scan already pays. Gated on `conversation_enabled` (real brain), so the
mock bake gains no scan and no output.

The stepper accumulates a **total plus a per-pair breakdown**. Per-pair is what
diagnoses a run: the issue's own evidence is "Diego+Sofia 248, Tanaka+Sofia 90,
Diego+Tanaka 61", and a bare total would have hidden that R1's 399 was mostly one
pair.

**Three surfaces, all existing:**

| Surface | Change |
|---|---|
| `GET /usage` | `stepper.run_usage()` gains a `social` block: total, `by_pair`, conversations |
| `RunRecord.result` | gains `co_settled_pair_steps`, `by_pair` and `conversations` next to the existing `steps` and `cost_usd` (`_write_run_record`) |
| `_finish_run()` | prints one warning line when a real-brain run finishes with zero |

The warning is the issue's direction 2 — *"nothing reports that"*. Now something
does, on the default path, without anyone remembering to analyse anything.

### Part 4 — the offline tool

Promote batch-2's `godot-generative-agents/runs/issue-760-batch-2/analyze_run.py`
to `godot-generative-agents/tools/`, next to `most_common_actions.py`, stdlib-only,
and add the co-settled computation it currently lacks.

One honesty constraint: from frames alone the only available signal is `act` not
starting with `"walking to "`, which counts an *idle* agent as settled and can
over-report. So the tool reads `RunRecord.result` when present and falls back to
the frame proxy only for runs saved before the counter existed, stating in its
output which it used. **The backend counter is authoritative.** Two documented
definitions beat widening the replay contract with a `settled` flag.

## 5. Testing

Offline, five groups:

1. **Prompt pins** (`tests/test_prompt_templates.py`, per CLAUDE.md): pin the new
   `public_event.prompty` output exactly; update the `plan_system.prompty` pin for
   the Smallville→Penn fix; update the usage table in
   `prompt_templates/README.md`.
2. **Planner**, against the deterministic fake client it is already tested with:
   the memory block reaches all three levels' user messages (the RC1 regression);
   the minute prompt carries the window line and the minutes framing (RC2);
   `minutes`→steps converts with a clock and passes through unchanged without one;
   the travel clause is absent when no world map is supplied.
3. **Events**: unknown `at` or `host` raises; a host outside the active cast drops
   the event; seeded to everyone but the host at locked 4.0; **not seeded at all
   when `planner_client is None`**.
4. **Byte-identity** — the real guard that this is entirely a real-brain change:
   the mock bake test and #640's 3×`PYTHONHASHSEED` determinism test both pass
   untouched. If either moves, the gating is wrong.
5. **Metric**: two agents settled in one room counts; one of them walking does
   not. Plus `test_full_feature_mock` — the existing social-deadness tripwire —
   stays green.

## 6. Acceptance

A **live A/B run gates the merge**, matching R7's conditions exactly so the
comparison is honest: cast `diego, tanaka, sofia`, seed 42, 1200 steps,
`--decide-workers 0`, `--brain llm`, `--plan` left at its `auto` default.
Estimated $0.15-0.35 by batch-2's numbers. Poll `/usage` **before** shutdown.
Artifacts and a write-up go to #760, as batches 1 and 2 did.

**The bar: non-zero co-settled pair-steps and at least one conversation.** Not
R1's 399. A model-authored day is legitimately busier than the hand-tuned one, and
the issue's complaint is *"structurally impossible"*, not *"less social"*.
Matching the authored day would mean we had simply rebuilt `--plan schedule`.

**Shape: one PR.** The four parts are only provable together by a single live run;
splitting them means paying for two.

## 7. Risks

- **Grounding could backfire.** Telling the model it has six hours might make it
  plan *more* stops, not fewer, worsening overlap. The prompt leans against this
  ("travel is charged on top"), but only the live run settles it.
- **A 4.0 event memory might simply be ignored.** If the run shows the event
  retrieved but absent from the plans, the fallback is to name events in the
  minute prompt directly rather than relying on retrieval — a cheap second
  attempt, but a second live run.
- **Prompt changes invalidate recorded cassettes.** Runs saved before this cannot
  be re-run against the new code (`CassetteMiss`). Unavoidable for any prompt
  edit; stated so it is not later discovered as a bug.
- **Threading the world map into `LLMPlanner`** is the only new coupling in Part
  1. If it proves awkward at the `attach_agents` call site, pass a precomputed
  median-walk-minutes integer instead — the planner needs the number, not the map.
