# #921 cost-scaling runs — the #879 chart data

How live-run cost scales with cast size, cognition tools, and sim duration.
Everything matches the frozen #878 showcase recipe (= batches 10–12): seed 42,
`TICK=0.05`, effort medium, Sonnet 5 decide/plan/reflect/outcome + Haiku 4.5
converse/score/react, cognition tools ON except the C-OFF cell, driven by
batch-4's `drive_run.sh`. Canonical cost = each cell's `usage.json`
`total_cost_usd` (sim.db / run.yaml lag it — batch 12 read $5.17 there vs the
real $5.37). Mock gate passed before the batch ($0, 7-agent cast, all flags).

Code: A1/D1080/D2160/A3 ran on `09eff48b` (feat/879 branch); engine code is
byte-identical to `main@7693ccb6` (diff touches only landing-page files).

| cell | cast | steps | cognition | cost | calls | status |
|---|---|---|---|---|---|---|
| A1 | tanaka | 4320 | ON | **$0.518** | 66 | done |
| A3 | tanaka,maya,priya | 4320 | ON | **$3.157** | 434 | done |
| A5 = baseline | showcase 5 | 4320 | ON | **$5.37 / $5.38 / $6.82** (mean $5.86) | 906/832/1109 | reused: batch 12 runA, batch 10 runA, batch 11 runB |
| A7 | showcase 5 + diego,sofia | 4320 | ON | **$8.575** | 1375 | done (2026-08-01, post-reset) |
| D1080 (3h) | showcase 5 | 1080 | ON | **$1.377** | 236 | done |
| D2160 (6h) | showcase 5 | 2160 | ON | **$2.957** | 509 | done |
| D4320 (12h) | = A5 baseline | 4320 | ON | = baseline | | reused |
| C-OFF | showcase 5 | 4320 | **OFF** | **$7.071** | 1131 | done (2026-08-01, post-reset) |

`C-OFF-aborted-apilimit/`: the first C-OFF attempt died at step 1921/4320
($3.03 partial, 5 consecutive 400s) when the **workspace API usage limit**
ran out mid-run (resets 2026-08-01 00:00 UTC) — a truncated run, never a
chart datapoint. Its boot log does confirm cognition resolved OFF (no
"Cognition tools: ON" line). Note the failure mode: the engine auto-pauses on
consecutive LLM errors, but `drive_run.sh`'s wait loop only terminates on
`paused && (step>=steps || over_budget)`, so it spins forever on an
error-pause.

Findings: duration is linear ($1.38 → $2.96 → $5.86 for 3h/6h/12h,
~$0.49/sim-hour); agents are **super-linear at the low end then near-linear**
($0.52 → $3.16 → $5.86 → $8.57 for 1/3/5/7) — a solo agent has no
conversations or reactions, so the social Haiku calls vanish (66 calls vs
~900 at five agents), and past three agents the marginal agent costs
~$1.2–1.4/day. **Cognition OFF cost MORE than ON** ($7.07 vs the $5.86
baseline mean, above the 5.37–6.82 replicate range; 1131 calls vs ~900) —
the tools' extra retrieval calls are cheap, and agents deciding without
recalled context appear to spend more calls overall. One run — a direction,
not a measurement.

The C-OFF/A7 runs (2026-08-01) ran on the same recipe post-reset; the first
C-OFF attempt (2026-07-30) died to the workspace API limit and is preserved
as `C-OFF-aborted-apilimit/`. `cost_scaling.csv` has one row per
cell/replicate — 9 rows, complete.
