# #760 batch 9 — the run that closed #826 (under rule 3, not by passing)

One run + its $0 mock gate, on `main` at `9d74a004` (first run with #891's
day-end clause; also #885/#870/#866).

**$6.01**, 4320 steps. Mock gate: `run-20260729-235340-9b0d93` (all zeros).

| | |
|---|---|
| run id | `run-20260730-000027-5118ae` |
| verdict | criterion 2 **PASS 0** (the #891 fix, first run aboard); criterion 1 **FAIL 67 min** on a fifth distinct mechanism → **#896** (a stop satisfied by an instantaneous verb can never be credited) |
| disposition | #826 **CLOSED under its endgame rule 3** — the breaching mechanism is again not #826's own; see the closing comment on #826 for the full six-batch table |

Criterion 1 across identical recipes: 55 → 0 → 67 (batches 7/8/9) — the
metric's residual variance samples which novel bug the day finds, not whether
#826's harm persists. #896 stays open under #760.

## Reproducing

```bash
STEPS=4320 \
OUT=godot-generative-agents/runs/issue-760-batch-9/runA \
SEED=42 TICK=0.05 PORT=8093 READY_TIMEOUT=900 \
  ./godot-generative-agents/runs/issue-760-batch-4/drive_run.sh \
  runA tanaka,maya,priya,theo,mateo 20 --model claude-sonnet-5 --effort medium
```

Numbers reproduce from `tools/analyze_run.py run-20260730-000027-5118ae
--usage runA/usage.json`. Run data git-ignored as always.
