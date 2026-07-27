# Believability — Score Progress, Not Repetition (#781)

**Issue:** #781 · **Branch:** `fix/believability-progress-781` off `main` ·
**Review track:** Godot/geo owners (`godot-generative-agents/backend/eval/` +
tests). Sub-issue of #760 (the live-LLM run log). Depends on the merged #799
(central `_merge_growth_windows`) and #780 (`meta.locations` + the
`world_grounding` dimension).

## Goal

`backend/eval/believability.py --no-llm` ranks the worst run in the #760
batch-1 five highest and the healthiest lowest. Make the heuristic judge
reward a day that *progresses* instead of a day that *repeats*, so a
believability score is usable for run-over-run comparison again.

## Current state (verified 2026-07-27 against the batch-1 runs)

The five runs live on `runs/issue-760-live-batch-1`, not `main`. Re-running
today's `main` over them reproduces the inversion the issue reports:

| run | overall | plan | temporal | social | world | memory |
|---|---|---|---|---|---|---|
| R4 `…e8c405` | **9.19** | 9.64 | 8.46 | 8.67 | `n/a` | 9.76 |
| R2 `…78858a` *(the loop)* | 9.17 | **10.0** | 8.66 | 8.26 | `n/a` | 9.78 |
| R3 `…584ead` | 8.67 | **10.0** | 7.94 | 8.42 | `n/a` | 8.26 |
| R5 `…e51349` *(zero conversations)* | 8.60 | **10.0** | 7.80 | `n/a` | `n/a` | 8.00 |
| R1 `…d528ec` *(the best run)* | **8.05** | 9.5 | 8.07 | 8.30 | `n/a` | 6.33 |

Four findings change the issue's own account of the cause.

**The conversation double-count is already fixed.** #799 moved
`_merge_growth_windows` into `build_evidence`. R1 now reads 2 / 1 / 3
conversations per agent, not the 12 the issue reports. That bullet should be
struck from #781 rather than implemented.

**`world_grounding` is `n/a` on all five runs.** They were baked before #780
added `meta.locations`, so the dimension designed to catch R4's boathouse
hallucination cannot fire on the run that motivated it (see *Spin-off issues*).

**`memory_use` does not reward volume — it rewards vocabulary collapse.** The
test is "does a retrieved memory share **one** content word with the act or
reasoning" (`believability.py:900-936`). Chris Donnelly's looping pair hit
977/977 because the single word `aiden` accounted for 4,775 of his overlaps:
every decision was about Aiden and every memory mentioned Aiden. Diego's
varied day hit 599/1200. The metric measures topical uniformity, which
repetition maximises.

Compounding it, the denominator counts **repainted frames**. Frames carry the
same `(act, memories)` every step and each repaint is scored, so Diego's "1200
decisions" are 14 real ones and one lucky match is counted hundreds of times.
This is the same bug class #799 fixed for conversations.

**`plan_coherence` is saturated, not merely loop-blind.** Every one of the 23
agents across the batch scores **100% coverage**, because the act string
carries its `@ UPenn:Building:Room` address and the address always shares a
word with some schedule stop. Only `order` discriminates, and `order` is 1.0
whenever the day has few segments — so standing on the `"spending time"`
placeholder for 977 steps scores a perfect 10.

The unifying defect: **every dimension is a fraction whose denominator the
agent controls.** Doing less shrinks the denominator and raises the score.
Monotony is a global attractor, which is why the worst run wins.

## Design

Five changes, all in `backend/eval/believability.py`. Four are
`HeuristicJudge` methods; two are `audit()`-level and therefore judge-agnostic.

### 1. `_plan_coherence` → schedule progress × order

Replace `0.5·coverage + 0.5·order` with `progress × order`, where **progress**
is the longest in-order run of *distinct* matched stop indices over
`len(ev.schedule)` — "how far through your plan did you actually get".

`coverage` goes away: it reads 100% for every agent in the batch and
discriminates nothing. `order` stays as the second factor because it is the
term that catches frame shuffling, which progress alone cannot (a shuffled day
still reaches the same stops).

A product rather than a weighted blend, deliberately: it needs no weight
constant, penalises the loop hardest, and leaves both existing acceptance
controls with more margin than any blend tested (`0.7/0.3` and `0.5/0.5` were
both measured and are worse on both counts).

Normalising by "stops the run had time for" instead of `len(ev.schedule)` was
measured and gives identical results on all five runs, so it is not written.

*Effect:* R2's loop pair 10.0 → 5.5.

### 2. `_memory_use` → one entry per decision, not per frame

Walk `ev.retrievals` and keep an entry only when `(act, memories)` changes —
the same collapse-repainted-frames idiom as `_segments_for` and
`_merge_growth_windows`. Relevance is otherwise unchanged.

*Effect:* Diego 5.5 → 8.7 (his 1200 frames are 14 decisions).

### 3. `_social_grounding` → a novelty term

Per conversation, the fraction of content words not present in any *earlier*
conversation between the same participants. Weights go `0.4 / 0.4 / 0.2` →
**`0.3` co-location, `0.3` grounding, `0.1` speaker validity, `0.3` novelty**;
validity was always the light term.

Measured novelty per conversation:

```
R1  Diego+Sofia   1.00  0.67
R4  Casey+Dana    1.00  0.61  0.55
R2  Aiden+Chris   1.00  0.64  0.58  0.39  0.38  0.25  0.24  0.04
R3  Hannah+Ravi   1.00  0.69  0.67  0.42  0.38  0.38  0.21
```

Monotone decay on both loops, no threshold needed. The issue suggests
comparing opening lines instead; that was measured and is too noisy to
separate R3's loop (max 0.43) from R1's healthy pair (0.18).

*Effect:* the loop pairs lose their perfect 10.0 for re-running one
conversation eight times.

### 4. A silent agent who had the chance gets scored

`_social_grounding` returns `None` when an agent held no conversations. If that
agent stood within `vision_r` of another agent for **≥10% of the run**, score
it `1.0` with a note naming the fraction; below that, keep `None`.

Measured co-location for the batch's silent agents — the floor separates
"never spoke" from "never had anyone to speak to":

| agent | co-located | outcome |
|---|---|---|
| R4 Wesley Okafor | 23% | scored |
| R3 Tessa Byrne, Professor Ellis | 16% | scored |
| R4 Leon Brooks | 2% | `None` |
| R5 Diego, Tanaka, Sofia | 0% | `None` |

*Effect:* Wesley 9.67 → 7.50. He was the highest-scoring agent in the entire
batch, for never saying a word.

*Known tension:* a flat 1/10 conflates "didn't socialise" with "confabulated",
since the dimension nominally measures grounding. A sixth dimension would
separate them and was ruled out as too large for #781. The note keeps the
distinction legible to a reader.

### 5. `audit()` → weakest agent and a pathology flag

`summary` gains two fields, both judge-agnostic:

- **`weakest`**: `{"name", "score"}` for the lowest-scoring agent, rendered
  under the mean. A run with a broken pair reads as `mean 8.89, weakest 8.04
  (Aiden Park)` instead of one flattering number.
- **`loops`**: repeat-conversation pathologies, from a module-level
  `_repeat_loops(evidence)`. Flag a participant pair with **≥3 conversations
  and mean novelty < 0.60**.

The flag catches exactly the two known #778 loops and nothing else:

```
run  pair                n   mean novelty   flagged
R2   Aiden + Chris       8       0.44         yes
R3   Hannah + Ravi       7       0.54         yes
R4   Casey + Dana        3       0.72         no
R1   Diego + Sofia       2       0.84         no
```

The gap between flagged and clean is wide, and a false positive costs one line
of report text rather than a ranking — so this threshold carries far less
weight than a score constant would.

Rendered form:

```
## Summary
overall (mean)   8.89
weakest agent    8.04  Aiden Park

⚠ repeat-conversation loop
   Aiden Park ↔ Chris Donnelly
   8 conversations, mean novelty 0.44
```

## Acceptance

Run-mean ordering is **not** the bar. R2 still tops the mean after every fix
(8.89 vs R1's 8.52), because three of its five agents genuinely were healthy
and a mean averages them in. Reaching R1-first from here means fitting weights
to five runs, which would not survive batch 2. The flag reports the pathology
instead of trying to compress it into one number — which answers the issue's
actual closing complaint, that scores from this batch cannot be used to
compare runs.

What must hold, measured on batch-1 with the Penn locations injected:

1. **The loop agents rank at the bottom of their own run.** Chris was 2nd of 5
   (9.25) and Aiden 4th (9.15); they become the two lowest (8.20, 8.04). Ravi
   and Hannah were 2nd and 3rd of 7 (9.12 each); they fall to mid-pack.
2. **The silent free-rider stops topping the batch.** Wesley 9.67 → 7.50, the
   lowest in R4.
3. **R1 leaves last place.** 8.05 (5th) → 8.52 (2nd).
4. **R2 and R3 are flagged; R1, R4, R5 are not.**
5. **Both existing acceptance controls keep margin** — scrambled frames −1.68
   overall, swapped plans `plan_coherence` 10.0 → 5.5.

Full ordering after the change: `R2 8.89 > R1 8.52 > R4 8.39 > R5 7.90 >
R3 7.75`.

## Testing

Extend `godot-generative-agents/tests/test_believability_eval.py`, using its
existing synthetic two-persona replay as the fixture pattern.

| test | assertion |
|---|---|
| stalled agent | one act all run, matching 1 of 2 stops → `plan_coherence` well below the intact fixture's 10.0 |
| repainted frames | 40 identical `(act, memories)` frames plus 2 changes → 3 decisions counted, not 42 |
| repeat conversations | a pair re-running one transcript scores below the same pair having two distinct ones |
| silent + co-located | scored, and the note names the co-location fraction |
| silent + alone | stays `None` |
| summary rollup | `weakest` carries name and score |
| loop flag | `loops` names the pair, its conversation count, and its mean novelty |
| controls hold | the two existing acceptance tests keep the margins pinned above |

The last row is the guard against a future change quietly re-saturating a
dimension, which is how the current state arose.

## Batch-1 validation

A documented procedure, not committed code — the runs are on
`runs/issue-760-live-batch-1`, not `main`, so a committed script could not run.
Same pattern as `runs/issue-760-batch-1/README.md`.

```bash
# 1. extract the runs without touching the working tree
mkdir -p /tmp/b1 && git archive runs/issue-760-live-batch-1 \
  godot-generative-agents/runs | tar -x -C /tmp/b1
R=/tmp/b1/godot-generative-agents/runs

# 2. audit each run; inject Penn's meta.locations first so world_grounding
#    can fire on these pre-#780 bakes (see spin-off issue 1)
for id in run-20260724-193817-d528ec run-20260724-194343-78858a \
          run-20260724-195642-584ead run-20260724-201036-e8c405 \
          run-20260724-202121-e51349; do
  uv run python -m backend.eval.believability "$R/$id" --no-llm --format json
done
```

Compare against the acceptance table above; record the before/after in the PR
body and as a #760 comment.

## Out of scope

- **The LLM judge's rubric text.** #781 is about `--no-llm`; the model judge
  reads evidence, not these mechanics. It does inherit `weakest` and `loops`.
- **A `--locations` flag.** `believability.py` stays world-agnostic; the
  batch-1 backfill lives in the validation procedure only.
- **True memory *carry*** — the issue's "does a conversation reference a
  concrete detail first introduced in an earlier one". Real, but larger than
  #781; the novelty term is the cheap proxy that does the work here.
  Retrieval *reach* was measured as an alternative and is backwards: R2's loop
  reaches back **further** than R1 (median 185 steps vs 111).
- **A sixth dimension** for socialisation, and any change to
  `_temporal_sanity`.

## Spin-off issues to file

1. **`world_grounding` reads `n/a` on every pre-#780 bake.** The dimension
   cannot fire on the runs that motivated it. `meta.locations` is derived
   purely from the Penn world YAML (`penn_world.py:634`,
   `generate_penn_replay.py:341`), so it is backfillable. A #780 follow-up.
2. **Memory carry as a scored signal** — see *Out of scope*.

And on #781 itself: strike the "collapse cumulative chat states before
counting" bullet, already delivered by #799.
