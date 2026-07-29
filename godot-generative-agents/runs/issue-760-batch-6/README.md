# #760 batch 6 — the first measurement of #826 on fixed code

One run, matched to batch 4's Run B and to batch 5 (same cast, seed, window,
model and effort) so both of #826's criteria are comparable across all three.
On `main` at `885026f8` — the first run to include **#862**, which stops
presenting a *finished* stop as the agent's current one. #862's three
predecessors (#830, #831, #838) had never had criterion 1 measured on fixed code.

**$6.24**, 605 calls, 4320 steps, 38 min wall clock.

| | |
|---|---|
| run id | `run-20260729-172619-d09e1d` |
| baselines | `run-20260727-190111-f15134` (batch 4 Run B), `run-20260728-211113-e68900` (batch 5) |
| verdict | **both criteria fail**; decision-rule branch 3 (new mechanism) |

## Reproducing

No driver of its own — batch 4's honours an `OUT` override, so a second copy
would only be a second thing to keep in step:

```bash
STEPS=4320 \
OUT=godot-generative-agents/runs/issue-760-batch-6/runA \
SEED=42 TICK=0.05 PORT=8093 READY_TIMEOUT=900 \
  ./godot-generative-agents/runs/issue-760-batch-4/drive_run.sh \
  runA tanaka,maya,priya,theo,mateo 20 --model claude-sonnet-5 --effort medium
```

`--effort` needs #820. Run the same line with `BRAIN=mock STEPS=120` first: it
exercises the whole boot → `/config` → `/resume` → poll → `/usage` → `/shutdown`
dance for $0, so a typo costs nothing. (Done for this batch; it passed.)

## What is here

* `runA/` — `config-applied.json`, `usage.json`, `live-final.json`, `run_id.txt`.
  The run directory itself (`frames.jsonl` 100 MB, `cassette.jsonl` 3.4 MB) is
  git-ignored, as in every previous batch.

Every number below comes out of the maintained analyzer (#850 folded batch 5's
two scratch scripts into it, so this batch shipped none of its own):

```bash
uv run python godot-generative-agents/tools/analyze_run.py run-20260729-172619-d09e1d
```

## Headline

| | batch 4 (Run B) | batch 5 | **batch 6** |
|---|---|---|---|
| **crit. 1** longest abandoned leg (≤ 30 min) | 57 min | 62 min | **52 min — FAIL** |
| **crit. 2** still walking at day's end (≤ 10 min) | 135 min | 4 min | **18 min — FAIL** |
| `arrived_then_departed` (combined) | 20 | 22 | 1 |
| — same-place oscillation (#849) | 17 | 19 | 0 |
| — genuine cross-building retarget (#826) | 3 | 3 | 1 |
| abandoned-leg minutes (sum) | 133 | 94 | 52 |
| cost / calls | $9.81 / 1081 | $6.08 / 683 | $6.24 / 605 |

Criterion 1 improved but still fails. Criterion 2 regressed from passing to
failing. **Neither number is clean evidence about #862** — see the caveat below.

## Attribution: the breach is not #862's mechanism

#862's fix is self-labelling, so the cassette answers this for free. The one
criterion-1 breach is Maya Chen, 10:23 → 11:15, Irvine Auditorium → Houston
Hall, 52 min abandoned. Both ends of that leg, from `cassette.jsonl`:

**Leg start, 10:23 — #862's context present, truthful, and it worked:**

> Your plan's current stop: Serious orgo exam review … at Van Pelt — Moelis
> Reading Room (planned ~60 min). **You have already finished this stop.** Your
> next stop is … attend Professor Tanaka's guest lecture on gravitational waves
> at Irvine Auditorium, starting at 11 AM (37 min from now).
>
> Walking from here takes at least about: … **Irvine Auditorium 26 min** …
>
> → `travel(Irvine Auditorium)` — *"the lecture starts at 11 AM and travel takes
> 26 minutes."*

That is exactly the decision #862 was built to produce: she did **not** walk back
to redo a finished stop, she left for her next anchored one, on a stated budget.

**The breach, 11:15 — the sentence is absent:**

> Your plan's current stop: Quick coffee break to recharge before catching up on
> schedule at **Houston Hall** (planned ~15 min). **This has been your current
> stop for 15 min.**
>
> → `travel(Houston Hall)` — *"I've had my coffee break, time to head to Houston
> Hall to catch up on my schedule."*

`You have already finished this stop.` is **not** in the breaching prompt. So on
the decision rule this is branch 3: **not #862's mechanism.**

What actually happened, with Priya Nair as the control — she left Van Pelt on the
*same* step 861 for the same destination:

| | Maya | Priya |
|---|---|---|
| departs for Irvine | step 861 (10:23) | step 861 (10:23) |
| arrives | never | **step 1170 (11:15)** — walk cost ~52 min |
| step 1175 (11:15) | turns around for Houston Hall | performs the lecture |

So the leg was rational at its start, the advertised price was **26 min against a
real ~52 min**, and Maya's plan pointer advanced *twice* past the Irvine lecture
while she was still in transit — five steps short of the door. Her breaching
prompt then asserted she had been on a Houston Hall coffee break for 15 minutes,
in a building she had never entered, and she read that back as *"I've had my
coffee break."*

That is the **mirror** of #862: #862 fixed a *finished* stop rendered as current;
this is an *unreached* stop rendered as current-and-elapsed.

Criterion 2's breach (Priya, 18 min) has the same shape and also lacks the
sentence: at 19:41 she left Meyerson Hall for an on-plan Houston Hall debrief
with 19 minutes of day left. A run-out-of-day tail rather than #826's
arriving-nowhere failure — the class #826's own wording calls "not the failure
mode" — but 18 > 10, so the guard fails as written.

**#860 repeat check:** batch 5's signature (Maya having the same coffee three
times) is **absent**. `same_place_total` is 0, down from 19.

## Caveat: this run lost agent-time, so the low counts are not a clean pass

Four of five agents ended the day frozen on an unbounded `perform`, and one
froze mid-day: **Maya Chen stopped deciding at 13:26 and held one activity for
394 sim-minutes** — 55% of her day, 15 decides against ~30 for everyone else,
$0.36 of LLM spend against $0.53–$0.82. `run_simulation.py:746-749` settles an
on-plan stop with no duration "for the rest of the run" without checking that it
is the *last* stop; LLM-planned stops routinely carry no duration.

An agent that stops deciding cannot retarget, so part of the 22 → 1 drop in
`arrived_then_departed` is lost agent-time, not a fix. This is the failure class
`analyze_run.py` warns about in `_turnarounds` ("a run with thrash near 0 … is
this failure mode, not a fix"), reached by a different route. Filed separately;
it does not block #826.
