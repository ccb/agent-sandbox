# agent-sandbox

A research test bed for **multi-agent simulated environments**. We take a classic
text-adventure engine, give its non-player characters their own minds, and let
multiple AI agents perceive, plan, and act in a shared world.

This is the summer 2026 research project for Chris Callison-Burch's group. The
inspiration is the Stanford [*Generative Agents*](https://arxiv.org/abs/2304.03442)
paper ("Smallville") and the [ReAct](https://arxiv.org/abs/2210.03629)
(Reason + Act) agent pattern.

!!! note "This documentation is local-only"
    There is no public website. These docs are served from your own machine for
    people working on the project. To read them, clone the repo and run:

    ```bash
    pip install -e .[docs]
    cd mkdocs && mkdocs serve     # then open http://127.0.0.1:8000
    ```

    `mkdocs build` produces a static site under `mkdocs/site/` (git-ignored) that
    you can zip and share with collaborators. Nothing is published to the internet.

    This site is the home page and API reference. The design notes and guides
    live in the repo's
    [`docs/`](https://github.com/ccb/agent-sandbox/tree/main/docs) directory and
    are read directly on GitHub.

## The idea

We build **one shared framework** that everyone contributes to, then each person
builds **their own application** on top of it. The framework supplies the world
model, the agents, the turn loop, and the planning machinery. The applications
take it in two broad directions:

1. **Games** — LLM-driven NPCs as believable characters in a playable game.
2. **Simulations** — SimCity / *The Sims*-style worlds where the goal is to model
   realistic group and social dynamics, not "fun."

## Why a text adventure?

Because it already solves the hard representational question cleanly. The engine
models a world as **locations**, **items**, and **characters**, and — crucially —
every action is governed by a **classical-planning action schema**: an action has
**preconditions** that must hold and **effects** it applies. You can't unlock a
door without the key. That gate is exactly what keeps an LLM agent honest: instead
of narrating "I take out a key and open the door," the agent must choose from the
actions actually available, and the engine decides whether they're allowed.

## Getting started

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .            # editable install of the engine
pip install -e .[dev]       # + black, nbformat, pytest
pip install -e .[llm]       # + openai, anthropic, tiktoken
pip install -e .[docs]      # + mkdocs-material, mkdocstrings (this site)
```

Run things:

```bash
python -m text_adventure_games.webapp.app          # Flask web UI at localhost:8080
pytest tests/ -v                                    # offline agent-layer + live-game suites
LLM_PROVIDER=mock python -m notebooks.hw1_llm.play  # ReAct NPCs, free + offline
```

To enable the LLM layer, set `LLM_PROVIDER` (`anthropic`, `openai`, or `mock` — a
free deterministic stand-in) and, for the real providers, the matching
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` before launching.

## Where to go next

- **[API reference](api.md)** — the engine's public classes and functions,
  generated from docstrings. (This is the one other page in this site.)

The longer-form guides and design notes are kept in the repo's `docs/` directory
and read on GitHub:

- **[Reading the output](https://github.com/ccb/agent-sandbox/blob/main/docs/reading-the-output.md)**
  — how to interpret what the game prints, including an agent's reasoning trace.
- **[Testing the agent layer](https://github.com/ccb/agent-sandbox/blob/main/docs/TESTING.md)**
  — running the offline, deterministic test suites with the mock LLM client.
- **[Design notes](https://github.com/ccb/agent-sandbox/tree/main/docs/design)**
  — proposals and specs for the multi-agent features (turn modes, simultaneous
  actions, memory, output rendering).
