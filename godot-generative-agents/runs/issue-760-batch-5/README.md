# #760 batch 5 — the #826 validation run

One run, matched to batch 4's Run B so `arrived_then_departed` is comparable:
same cast, seed, window, model and effort, on `main` after #826, #831, #837 and
#838. **$6.08**, 683 calls, 4320 steps, 40 min wall clock.

| | |
|---|---|
| run id | `run-20260728-211113-e68900` |
| baseline | `run-20260727-190111-f15134` (batch 4, Run B) |
| write-up | https://github.com/ccb/agent-sandbox/issues/760#issuecomment-5110171090 |
| verdict | https://github.com/ccb/agent-sandbox/issues/826#issuecomment-5110173777 |

## Reproducing

No driver of its own — batch 4's honours an `OUT` override, so a second copy
would only be a second thing to keep in step:

```bash
OUT=godot-generative-agents/runs/issue-760-batch-5/runA \
STEPS=4320 SEED=42 TICK=0.05 PORT=8093 READY_TIMEOUT=900 \
  ./godot-generative-agents/runs/issue-760-batch-4/drive_run.sh \
  runA tanaka,maya,priya,theo,mateo 20 --model claude-sonnet-5 --effort medium
```

`--effort` needs #820. Run the same line with `BRAIN=mock STEPS=120` first: it
exercises the whole boot → `/config` → `/resume` → poll → `/usage` → `/shutdown`
dance for $0, so a typo costs nothing.

## What is here

* `runA/` — `config-applied.json`, `usage.json`, `live-final.json`, `run_id.txt`.
  The run directory itself (`frames.jsonl`, `cassette.jsonl`, 85 MB) is
  git-ignored, as in every previous batch.
* `thrash_kind.py` — splits `arrived_then_departed` into same-place oscillation
  (#849) and genuine cross-building retargeting (#826). This is the split #850
  asks `analyze_run.py` to adopt. **Note the prefix trap it documents**: a
  sub-place drops its building's qualifier, so `"Van Pelt — Moelis Reading Room"`
  reduces to `"Van Pelt"` and never equals `"Van Pelt Library"` — compare with a
  two-way `startswith`, not `==`. Scoring that wrong cost me two miscounted
  events in the first published table.
* `walk_legs.py` — longest unbroken walk and the still-walking-at-the-end tail
  per agent. The second number is the one that shows #826's motivating trace is
  fixed: Priya 135 min in the baseline, 0 here.

## Headline

| | baseline | batch 5 |
|---|---|---|
| `arrived_then_departed` | 20 | 22 |
| — same-place oscillation (#849) | 17 | 19 |
| — genuine retarget (#826) | 3 | 3 |
| longest abandoned leg | 57 min | 62 min |
| still walking when the day ends | 135 min | **0** |
| cost / calls | $9.81 / 1081 | $6.08 / 683 |

#826's acceptance test was re-specified on the strength of this run: the
combined counter is dominated by #849 in both runs, so it cannot arbitrate #826.
