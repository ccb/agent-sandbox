# LLM cost and observability

Every provider call should be attributed to a run, agent, role, model, and phase.
Usage ledgers record input/output/cache tokens, failures, and estimated USD using
the checked-in price table. The live monitor exposes progress and spend while a
run is active; manifests and reviewed aggregate evidence make comparisons
reproducible afterward.

Safety rules:

- paid runs require explicit step and cost limits;
- stop automatically at the cost ceiling or after repeated provider failures;
- do not treat an estimate as a provider invoice;
- do not commit keys, raw prompts/responses, or cassettes;
- report model, effort, seed, configuration, source commit, calls, and analyzer
  method with any public cost number.

Aggregate measurements live in
`godot-generative-agents/runs/cost-scaling/cost_scaling.csv`; its README documents
the experimental caveats.
