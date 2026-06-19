# Notebooks

Two things live here:

1. A numbered **feature walkthrough** (`01`–`09`) — a guided tour of the library, each
   notebook focused on one capability. Read them in order, or jump to the feature you want.
2. The **onboarding assignment** (`hw1*`) — the day-one "Action Castle" exercise that
   teaches the engine by having you build a game.

Everything here runs **offline** with the deterministic mock LLM — no API key required:

```bash
pip install -e .[llm]                 # once, for the LLM client (mock included)
LLM_PROVIDER=mock jupyter lab         # then open any notebook
```

## Feature walkthrough

| # | Notebook | What it shows | Driver |
|---|----------|---------------|--------|
| 01 | `01_engine_tutorial.ipynb` | The engine basics: locations, items, characters, custom **actions** (precondition → effect), **blocks**, and a graphviz map. Build a tiny game from scratch. | none |
| 02 | `02_agents_react.ipynb` | The agent layer: the **ReAct loop** (observe → decide → act → reflect), per-character **goals**, the game **clock**, **triggers** & scheduled events, and the **event log** — every NPC driven by a mock agent. | mock LLM |
| 03 | `03_output_and_traces.ipynb` | How the engine prints: the **Message / Channel / Renderer** seam, **verbosity** (quiet / normal / verbose), and swapping renderers (plain, rich, capture). | synthetic + engine |
| 04 | `04_knowledge_beliefs.ipynb` | The per-character **knowledge / belief** layer (#45): asymmetric world-models, the "What you know:" observation section, and **perception gating** of hidden things. | scripted agent |
| 05 | `05_persuasion_dialogue.ipynb` | **Goal-influencing dialogue** (#46): speaking (`say` / `say to`), the room-scoped **heard** buffer, `adopt goal` / `drop goal`, and **persona** as the gate on persuasion. | mock LLM |
| 06 | `06_simultaneous_turns.ipynb` | The opt-in **simultaneous** turn mode (#25): a gather → resolve round, `initiative`, and basic conflict when two NPCs want the same thing. | scripted agents |
| 07 | `07_contested_resources.ipynb` | **Contested resources** (#42): ranked-fallback intents, informed retry after losing, and action-**phase** ordering. (Deep dive on top of `06`.) | scripted agents |
| 08 | `08_world_mechanics.ipynb` | Two opt-in world features: **containers / carry capacity** (#43) and **action durations** + the per-turn time budget (#24). | mock LLM |
| 09 | `09_agent_memory.ipynb` | The per-agent **memory** stream (#75): append-only timestamped records, **retrieval** by *recency × importance × relevance*, **perceiving** visible `Game.events`, and memory woven into the **live ReAct loop** — a failed action is remembered and fed back into the next turn's prompt. | mock LLM |

**Suggested order:** `01` (engine) → `02` (agents) → `03` (reading their output) → `04`
(what they know) → `05` (how they talk & persuade) → `06`/`07` (acting at once, and
fighting over resources) → `08` (extra world mechanics) → `09` (what they remember).

`01` and the `hw1*` notebooks are large and meant to be **run interactively** (their
outputs aren't committed). The rest ship with committed mock-LLM transcripts; re-execute
them with `LLM_PROVIDER=mock jupyter nbconvert --to notebook --execute --inplace <nb>`
(or the `rerun-notebooks` skill).

## Onboarding assignment

The day-one ramp (see [`../ONBOARDING.md`](../ONBOARDING.md)):

- `hw1.ipynb` — the assignment: build Action Castle by filling in the `TODO` actions and
  blocks.
- `hw1_solution/` — the completed answer key. `hw1_solution/action_castle.py` is also the
  **shared `build_game()` library** that the webapp and several demo notebooks import.
- `hw1_llm/play.py` — a CLI that re-wires the Action Castle NPCs with **pure ReAct** agents
  (no scripted fallback), to watch the LLM drive a real game:

  ```bash
  LLM_PROVIDER=mock python -m notebooks.hw1_llm.play     # offline, free
  LLM_PROVIDER=anthropic python -m notebooks.hw1_llm.play  # needs ANTHROPIC_API_KEY
  ```

## Feature → notebook coverage

| Feature | Notebook |
|---------|----------|
| Things / actions / blocks / parser | `01`, `hw1*` |
| ReAct agent loop, `Agent.decide`, scripted vs LLM agents | `02` |
| Goals & `GoalType` | `02`, `05` |
| Game clock & time periods | `02` |
| Triggers & event log | `02` |
| Output channels, verbosity, renderers (`reporting.py`) | `03` |
| Knowledge / beliefs, `describe_for`, perception gating | `04` |
| Agent memory: records, retrieval (recency/importance/relevance), `ingest_events` | `09` |
| Dialogue, `heard` buffer, audience, adopt/drop goal, persona gating | `05` |
| Simultaneous turn mode (gather → resolve, initiative) | `06` |
| Contested resources, ranked fallbacks, informed retry, phases | `07` |
| Containers & carry capacity | `08` |
| Action durations & per-turn budget | `08` |
| LLM provider selection (mock / anthropic / openai) | every notebook (`LLM_PROVIDER`) |

**Not yet demoable (design-only):** the **ScienceWorld / benchmark** interface (#47) is
designed but not implemented, so it has no notebook yet.
