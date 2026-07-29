# #760 batch 8 — first measurement on #885: criterion 1 hits literal zero, criterion 2 breaches on #891

One run + its $0 mock gate, on `main` at `34509b7f` (first run with #885's
anchor travel gate + next-stop-offered menu; also carries #870/#866).

**$8.08**, 4320 steps. Mock gate: `run-20260729-221246-9b923b` (both criteria
zero).

| | |
|---|---|
| run id | `run-20260729-224130-e4ba43` |
| baseline | `run-20260729-210056-e1ba5b` (batch 7 A) |
| verdict | criterion 1 **PASS 0** (zero retargets, zero abandoned minutes — 57→62→52→55→0 across the campaign); criterion 2 **FAIL** (Mateo 22 min, Maya 14 min still walking at 20:00) → filed **#891**, fixed in PR #892; run B held |

The criterion-2 legs were motivated, not thrash (Mateo answering Elena's text
toward Houston Hall at 19:37 — ~50 min leg, 23 min of day left; Maya to the
Book Stacks at 19:45): nothing tells the decide context when the day ends,
and the #885 gate has no future pin to bind on after the last anchor.

This run also closed **#860** (with batches 6/7): 0 re-performs-under-hold in
68 hold decides across the three runs; see the closing comment on #860.

## Reproducing

```bash
STEPS=4320 \
OUT=godot-generative-agents/runs/issue-760-batch-8/runA \
SEED=42 TICK=0.05 PORT=8093 READY_TIMEOUT=900 \
  ./godot-generative-agents/runs/issue-760-batch-4/drive_run.sh \
  runA tanaka,maya,priya,theo,mateo 20 --model claude-sonnet-5 --effort medium
```

Numbers reproduce from `tools/analyze_run.py run-20260729-224130-e4ba43
--usage runA/usage.json`. Run data (frames/cassette) git-ignored as always.
