---
description: Re-execute the demo notebook(s) offline with the mock LLM, then show the diff
argument-hint: "[notebook paths…]"
---

When the engine changes, the demo notebook's committed outputs go stale. This
command re-runs them offline (free, deterministic) so the outputs match the
current engine.

**Target:** `$ARGUMENTS` if any notebook paths were given; otherwise default to the
lightweight feature-demo walkthrough notebooks (all offline via the mock LLM):
`notebooks/02_agents_react.ipynb`, `notebooks/03_output_and_traces.ipynb`,
`notebooks/04_knowledge_beliefs.ipynb`, `notebooks/05_persuasion_dialogue.ipynb`,
`notebooks/06_simultaneous_turns.ipynb`, `notebooks/07_contested_resources.ipynb`,
`notebooks/08_world_mechanics.ipynb`. Do **not** touch the large
`notebooks/01_engine_tutorial.ipynb` or the `hw1*.ipynb` assignment notebooks unless
they are passed explicitly.

For each target notebook, from the repo root:

1. Execute it in place with the mock provider:
   ```
   LLM_PROVIDER=mock venv/bin/jupyter nbconvert --to notebook --execute --inplace <notebook>
   ```
2. If execution **fails**, stop and surface the traceback from nbconvert — the
   engine likely broke the notebook and that needs fixing first.
3. If it **succeeds**, run `git diff --stat -- <notebook>` so the resulting churn
   is visible.

After all targets are done, summarize which notebooks ran and what changed. Do
**not** commit — leave staging/committing to the user so they can review the
output diff first.
