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
Every number below comes out of the maintained analyzer — this batch shipped two
scratch scripts (`thrash_kind.py`, `walk_legs.py`) and #850 folded both into
`analyze_run.py` in #854, so they were deleted rather than left to rot:

```bash
uv run python godot-generative-agents/tools/analyze_run.py run-20260728-211113-e68900
```

Its `thrash` and `legs` lines print the split and the walk tails directly. The
trap the scratch split documented is now pinned by a test in there: a sub-place
drops its building's qualifier, so `"Van Pelt — Moelis Reading Room"` reduces to
`"Van Pelt"` and never *equals* `"Van Pelt Library"` — compare with a two-way
`startswith`, not `==`. Scoring that wrong cost two miscounted events in the
first published table.

## Headline

| | baseline | batch 5 |
|---|---|---|
| `arrived_then_departed` | 20 | 22 |
| — same-place oscillation (#849) | 17 | 19 |
| — genuine retarget (#826) | 3 | 3 |
| longest abandoned leg | 57 min | 62 min |
| still walking when the day ends | 135 min | **4 min** (Mateo) |
| cost / calls | $9.81 / 1081 | $6.08 / 683 |

The last row was first published as `0`, a rounding artefact off a coarse scan;
`analyze_run.py` reports Mateo mid-leg at the final frame, 29 steps ≈ 4 min.
Corrected on #826 and #760, and #826's regression guard reads as a ceiling
rather than a literal zero because of it.

#826's acceptance test was re-specified on the strength of this run: the
combined counter is dominated by #849 in both runs, so it cannot arbitrate #826.
