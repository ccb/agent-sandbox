# #760 batch 11 — the five-fix validation run

One run + its $0 mock gate + one tool-killed attempt, on `main` at `9557f002`
(all five batch-10 fix PRs merged: #910/#912/#913/#914/#915). Recipe
byte-matched to batch 10: cognition tools + tiering (Sonnet 5
decide/plan/reflect/outcome, Haiku 4.5 converse/score/react), seed 42,
4320 steps, effort medium.

**$6.82**, 1109 calls, 1 failed (transient 500). Mock gate:
`run-20260730-050553-7d1211` (all zeros).

| | |
|---|---|
| run id | `run-20260730-053001-294a5c` |
| verdict | **every batch-10 pathology verified gone** (#904/#905/#906/#907/#908); most social day of the campaign (23 convos, 3752 co-settled pair-steps, 26 commitments, 11 verbs) |
| criteria | 1 FAIL (106 min abandoned — all one new mechanism, filed #916, fixed PR #917); 2 marginal (Mateo 11 min vs 10, an informed choice — his reasoning quotes the #891 day-end line) |
| evaluator | first genuinely LLM-judged report (0/5 fallbacks, $0.27); harsher + directionally accurate (weakest agent = Tanaka 6.2, matching the manual read) |
| filed | #916 — decide context misleads a walking agent (elapsed counts the walk; #905 hold clause fires on stale pre-walk activity) |
| aborted attempt | `runA-aborted-driverkill/` — killed by the tooling's 10-min background cap (EXIT trap took the server down), ~$2.30, dead at step ~950; run B ran the driver detached |

Full write-up: the batch-11 comment on #760.

## Reproducing

```bash
STEPS=4320 \
OUT=godot-generative-agents/runs/issue-760-batch-11/runB \
SEED=42 TICK=0.05 PORT=8097 READY_TIMEOUT=900 \
  ./godot-generative-agents/runs/issue-760-batch-4/drive_run.sh \
  runB tanaka,maya,priya,theo,mateo 20 \
  --model claude-sonnet-5 --effort medium \
  --model-for converse=claude-haiku-4-5 --model-for score=claude-haiku-4-5 \
  --model-for react=claude-haiku-4-5 --cognition-tools
```

Numbers reproduce from `tools/analyze_run.py run-20260730-053001-294a5c --usage runB/usage.json`.
`runB/believability.md` is the LLM-judged report (post-#908 judge). Run data
git-ignored as always; the mock gate ran with the same flags plus `BRAIN=mock`.
