# #760 batch 7 — first measurement on #870 + #866, and the run that armed #885

One scoring run. On `main` at `74e94a7b` — the first run where plan revisions
keep their `start_hour` anchors (#870, PR #871) and the decide prompt's walk
prices are real BFS distances (#866, PR #872). Ran under the endgame rules on
[#826](https://github.com/ccb/agent-sandbox/issues/826): a full-day **mock
gate first** (`run-20260729-193915-911d5a`, $0, both criteria at zero), paid
run only on a pass.

**$6.58**, 4320 steps, ~35 min wall clock.

| | |
|---|---|
| run id | `run-20260729-210056-e1ba5b` |
| baselines | `run-20260729-172619-d09e1d` (batch 6), `run-20260728-211113-e68900` (batch 5) |
| verdict | criterion 1 **FAIL 55 min** (ceiling 30), criterion 2 **PASS 0** (ceiling 10); endgame-rule 3 breach → filed **#885**, fixed in PR #888; run B withheld |

Same-place oscillation 0 (batch 5: 19). Genuine retargets 2 (abandoned 55 +
24 min). Both prior fixes verifiably worked in-run: every revision kept 6–13
anchors (batch 6: 0–4); the prices agents quoted were the BFS numbers.

The 55-min leg is #885's trap, in one line: an anchor-held agent's prompt said
"your next stop is Van Pelt — Moelis Reading Room (15 min from now)" while the
same-place travel policy offered **no Van Pelt destination at all**, so the
model picked the only "Reading Room" on the menu — Houston Hall's, 53 min away,
its own reasoning saying "not Houston Hall".

`runA-aborted-529/` is a first attempt that died in an Anthropic 529
Overloaded storm (the resilience layer self-paused the loop at step 51;
$0.53 of boot planning). Kept because its server.log is the evidence trail.

## Reproducing

```bash
STEPS=4320 \
OUT=godot-generative-agents/runs/issue-760-batch-7/runA \
SEED=42 TICK=0.05 PORT=8093 READY_TIMEOUT=900 \
  ./godot-generative-agents/runs/issue-760-batch-4/drive_run.sh \
  runA tanaka,maya,priya,theo,mateo 20 --model claude-sonnet-5 --effort medium
```

Every number above reproduces from `tools/analyze_run.py
run-20260729-210056-e1ba5b --usage runA/usage.json`. The run directory itself
(frames.jsonl 100 MB, cassette.jsonl) is git-ignored, as in every batch.
