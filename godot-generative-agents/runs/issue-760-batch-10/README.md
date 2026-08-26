# #760 batch 10 — first cognition-tools (#358/#512) + tiered-models (#368) paid run

One run + its $0 mock gate + one aborted attempt, on `main` at `d93ea289`
(first run with #900's manifest tiering map and #902's effort-follows-the-tier fix).

**$5.38**, 4320 steps, 832 calls, 0 failed. Mock gate: `run-20260730-023002-ef1dc0`
(all zeros — and structurally blind to both new features: the mock brain reaches
neither the tool loop nor the Anthropic adapter).

| | |
|---|---|
| run id | `run-20260730-025718-889dac` |
| deltas vs batch 9 | `--cognition-tools`; Sonnet 5 decide/plan/reflect/outcome + Haiku 4.5 converse/score/react |
| verdict | **both #826 criteria PASS for the first time** (worst leg 18 ≤ 30; end-of-day walking 0; oscillation 0) |
| cognition tools | 13 `recall` + 11 `read_plan`, mostly pre-`speak`; memory→dialogue grounding observably working |
| tiering | cheaper than all-Sonnet batch 9 ($5.38 vs $6.01) with tools ON; converse+score = $0.92 on Haiku |
| filed | #904 follow→lobby dissolves a meetup; #905 unbounded wait-for-person; #906 stationary "walking home @ None" ×303 min; #907 ungroundable food items → breakfast thrash; #908 believability LLM judge 10/10 malformed on Haiku |
| aborted attempt | `runA-aborted-400/` — #901 (effort×tiering 400s every Haiku call), $0.62, fixed in PR #902 before runA |

Full write-up: the batch-10 comment on #760.

## Reproducing

```bash
STEPS=4320 \
OUT=godot-generative-agents/runs/issue-760-batch-10/runA \
SEED=42 TICK=0.05 PORT=8095 READY_TIMEOUT=900 \
  ./godot-generative-agents/runs/issue-760-batch-4/drive_run.sh \
  runA tanaka,maya,priya,theo,mateo 20 \
  --model claude-sonnet-5 --effort medium \
  --model-for converse=claude-haiku-4-5 --model-for score=claude-haiku-4-5 \
  --model-for react=claude-haiku-4-5 --cognition-tools
```

Numbers reproduce from `tools/analyze_run.py run-20260730-025718-889dac --usage runA/usage.json`.
`runA/believability.md` is the heuristic-fallback evaluator report (see #908).
Run data git-ignored as always; the mock gate ran with the same flags plus `BRAIN=mock`.
