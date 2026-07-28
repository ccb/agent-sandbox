# Live-LLM run batch 2 — artifacts index (#760)

Two runs, 2026-07-25, both `claude-haiku-4-5`, seed 42, 1200 steps,
`--tick-seconds 0.05`, `--decide-workers 0`. **Total spend: $1.336.**

Each is a controlled A/B against a specific batch-1 run, chosen to test the four
fixes that landed after batch 1: #778, #779, #782, #787.

| | run id | cast | plan | steps | cost | baseline |
|---|---|---|---|---|---|---|
| **R6** | `run-20260725-234739-186474` | omar, bethany, tessa, ellis, ravi, hannah, tanaka | `schedule` | 1200 ✅ | $1.2074 | R3 (`run-20260724-195642-584ead`) |
| **R7** | `run-20260726-000752-1fbb26` | diego, tanaka, sofia | `llm` (#787 default) | 1200 ✅ | $0.1283 | R1 / R5 |

Write-ups are comments on [#760](https://github.com/ccb/agent-sandbox/issues/760).

## Verdicts on the batch-1 fixes

| issue | verdict | evidence |
|---|---|---|
| **#779** seed relationships | ✅ **fixed** | 8/8 edge endpoints seeded in R6 (was 0 across all of batch 1), 2/2 in R7 |
| **#782** plan spend | ✅ **fixed** | R7: boot run $0.017604 + configured run $0.110683 = $0.128287 = ledger, to the cent |
| **#778** groundhog loop | ⚠️ **partly** | commitments persist (8 in R6) and schedules now advance — but `talk_to` share rose 76.2% → 83.3% |
| **#787** `--plan` default | ❌ **bad default** | R7 has **zero** both-settled-and-co-located pair-steps and 0 conversations; R1 on the same cast+seed had 399 and 3 |

## New issues this batch filed

See the sub-issues of #760 filed 2026-07-25. In short:

1. **`talk_to` reports success on a request that is silently dropped** — 148 of R6's
   160 `talk_to` decisions opened no conversation, $0.371 = **30.7% of the run**. The
   agent gets no failure memory, so it re-decides `talk_to` every tick (Omar: a
   112-decision unbroken streak).
2. **#779's seeded relationship memories are re-scored by #583**, discarding the
   authored 3.0. Proven by A/B: the identical edge persists at 3.0 under `--brain mock`
   (no scorer) and at 6.0–8.0 under `--brain llm`.
3. **The #787 default day has no co-settled moments** — agents pass through the same
   room but are never both *settled* there, so conversation is structurally impossible.

## Directory contents

- `r6/`, `r7/` — the driver's captures per run: `usage.json` (**taken before
  `/shutdown`** — tokens and `by_tool`/`by_role` live only in the in-process ledger),
  `config-applied.json`, `live-final.json`, `run_id.txt`. The driver also writes a
  `server.log` (the per-call monitor lines) but `*.log` is git-ignored repo-wide and
  it is redundant anyway: the cassette holds every call, `usage.json` the aggregates.
- `drive_run.sh` — boots the paused server, `POST /config` (the only way to pick a
  cast), `/resume`, polls, captures `/usage`, `/shutdown`. `BRAIN=mock` rehearses the
  whole sequence offline and free.
- `analyze_run.py` — the per-run table. `--self-check` pins the conversation-counting
  rule. Stdlib only, so it keeps working against archived run directories.

## Notes for whoever reads these next

- **Run dirs stay flat in `runs/`** — `RunStore` resolves `root / run_id`, so this
  folder is an index only, not a container.
- **Two extra `reset` run dirs are intentional.** `POST /config` closes the boot run
  and opens the configured one, so each run leaves a 0-step `reset` row.
  `run-20260726-000730-0ea0b2` holds **$0.017604 of real spend** — the boot run's
  LLM-authored day. Deleting it would drop that money off the books, which is exactly
  why #782 left the cleanup to #714.
- **Batch 1's index is not on `main` yet** — it is still open in PR #783.
- Don't rank these with `believability --no-llm`: #781 is open and it rewards memory
  volume (it ranked batch 1's groundhog-loop run highest and the healthiest lowest).
- `cache_read_input_tokens` is **0** across both runs and 981k input tokens, same as
  batch 1. Still the biggest untapped cost lever.
- #776 is still open, so `.env` must be sourced before launch; `drive_run.sh` does it,
  including the worktree fallback (a worktree never has its own `.env`).
