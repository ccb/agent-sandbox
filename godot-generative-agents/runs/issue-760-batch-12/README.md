# Selected Penn run: batch 12

This directory retains the minimal evidence for the public case study, not a
re-runnable private RunStore.

Run `run-20260730-150317-7ed039` used source commit `51415dc1`, seed 42, five
personas, 4,320 steps at ten simulated seconds per step, and 0.05-second live
ticks. It used Anthropic Sonnet 5 at medium effort for the primary cognition
roles and Haiku 4.5 for conversation/scoring/reaction, with cognition tools on.

The retained files are:

- `runA/config-applied.json`: resolved cast, brain, planning, model, effort, run
  length, tick rate, and safety ceiling;
- `runA/usage.json`: 906 calls, 0 failed, token counts, role/actor/tool splits,
  and $5.37355 total estimated cost;
- `runA/believability.md`: analyzer output, including its model/heuristic fallback
  disclosure and per-agent evidence.

The run produced 20 conversations and 2,690 co-settled pair-steps. Its published
believability summary scored 7.38/10 overall; one of five agent evaluations fell
back to the heuristic and is clearly labeled in the report.

Raw frames, events, prompts/responses, cassettes, server/driver logs, run IDs, and
the database were removed for privacy and package focus. Consequently this
evidence can be audited and cited, but this exact stochastic provider run cannot
be replayed byte-for-byte from the public files. Use the documented Penn live
workflow to produce a new bounded run with current provider access.
