# Cost-scaling evidence

`cost_scaling.csv` is the canonical aggregate behind the showcase cost chart. Raw
runs, prompts, responses, logs, cassettes, and the development database are
intentionally not published.

The experiment used seed 42, 0.05-second ticks, medium effort, Sonnet 5 for
decide/plan/reflect/outcome, Haiku 4.5 for converse/score/react, and cognition
tools on except for `C-OFF`. A full day is 4,320 ten-second steps (12 simulated
hours). Source runs are identified in the CSV for provenance; most were produced
from source commit `09eff48b`, engine-equivalent to `main@7693ccb6`. The reused
five-agent batch-12 run documents source commit `51415dc1` in its companion case
study.

Key observations:

- one agent, 12 hours: $0.518 / 66 calls;
- five agents, 3 hours: $1.377 / 236 calls;
- five agents, 6 hours: $2.957 / 509 calls;
- five agents, 12 hours: $5.374–$6.818 / 832–1,109 calls;
- seven agents, 12 hours: $8.575 / 1,375 calls;
- five agents without cognition tools, 12 hours: $7.071 / 1,131 calls.

Costs are provider-price estimates captured in July/August 2026, not current
quotes or guarantees. Cast effects include social-call opportunities, and the
cognition comparison is a single directional run rather than a controlled
estimate. Always use a step budget and live cost ceiling.

The CSV contains no prompt content or personal credentials and is sufficient to
rebuild the published aggregate chart.
