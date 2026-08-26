# #760 batch 12 — post-#916 confirmation run

One run + its $0 mock gate, on `main` at `51415dc1` (#916/PR #917 on top of the
batch-11 five fixes). Recipe byte-matched to batches 10–11: cognition tools +
tiering (Sonnet 5 decide/plan/reflect/outcome, Haiku 4.5 converse/score/react),
seed 42, 4320 steps, effort medium.

**$5.37**, 906 calls, 0 failed — the cheapest paid day of the campaign.
Mock gate: `run-20260730-145716-3e4733` (all zeros).

| | |
|---|---|
| run id | `run-20260730-150317-7ed039` |
| verdict | **#916 confirmed fixed** — batch-11's Tanaka now arrives at Williams and runs her full session; criterion 2 PASS (nobody walking at day end); criterion 1's single 57-min "abandoned leg" is a self-correction (Maya misremembered the seminar venue, the mid-walk decide fixed it — notes at the real seminar by 15:44) |
| day | 20 convos, 2690 co-settled pair-steps, 21 commitments, 11 verbs (wait×10, study×10, get×5 first-try); read_plan×19 + recall×13 |
| evaluator | LLM-judged 4/5 (1 fallback, honestly flagged): plan coherence 6.1 (b11: 4.2), memory use 7.1 (b11: 4.8) |
| filed | nothing — remaining findings are model stochasticity (venue slip, self-corrected) and polish ("spending time" act label on a 295-chat-frame social morning) |
| recommendation | **the #878 showcase baseline** — strongest, most legible day of the campaign |

Full write-up: the batch-12 comment on #760.

## Reproducing

```bash
STEPS=4320 \
OUT=godot-generative-agents/runs/issue-760-batch-12/runA \
SEED=42 TICK=0.05 PORT=8099 READY_TIMEOUT=900 \
  ./godot-generative-agents/runs/issue-760-batch-4/drive_run.sh \
  runA tanaka,maya,priya,theo,mateo 20 \
  --model claude-sonnet-5 --effort medium \
  --model-for converse=claude-haiku-4-5 --model-for score=claude-haiku-4-5 \
  --model-for react=claude-haiku-4-5 --cognition-tools
```

Numbers reproduce from `tools/analyze_run.py run-20260730-150317-7ed039 --usage runA/usage.json`.
Run data git-ignored as always; the mock gate ran with the same flags plus `BRAIN=mock`.
