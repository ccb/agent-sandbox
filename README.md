# agent-sandbox

A research test bed for **multi-agent simulated environments**. We take a classic
text-adventure engine, give its non-player characters their own minds, and let
multiple AI agents perceive, plan, and act in a shared world — first as text,
later as a 2D game in [Godot](https://godotengine.org/).

This is the summer 2026 research project for Chris Callison-Burch's group. The
inspiration is the Stanford [*Generative Agents: Interactive Simulacra of Human
Behavior*](https://arxiv.org/abs/2304.03442) paper (the "Smallville" demo) and
the [ReAct](https://arxiv.org/abs/2210.03629) (Reason + Act) agent pattern.

## The idea

We build **one shared framework** that everyone contributes to, then each person
builds **their own application** on top of it. The framework supplies the world
model, the agents, the turn loop, and the planning machinery. The applications
take it in two broad directions:

1. **Games** — LLM-driven NPCs as believable characters in a playable game.
2. **Simulations** — SimCity / *The Sims*-style worlds where the goal is to model
   realistic group and social dynamics, not "fun."

Both run on the same engine. The bet behind the simulation direction: putting AI
agents through realistic simulated environments may be a way to teach them about
the world before they're deployed in it.

## Why a text adventure?

Because it already solves the hard representational question cleanly. The engine
models a world as **locations**, **items**, and **characters**, and — crucially —
every action is governed by a **classical-planning action schema**: an action has
**preconditions** that must hold and **effects** it applies. You can't unlock a
door without the key. That gate is exactly what keeps an LLM agent honest: instead
of narrating "I take out a key and open the door," the agent must choose from the
actions actually available, and the engine decides whether they're allowed.

We start in text because it's the fastest way to prototype the agent layer. The
world model is presentation-agnostic, so the same simulation can later be rendered
as a 2D JRPG-style game.

## What's in here

```
text_adventure_games/      The engine (the shared framework)
  things/                  Thing -> Location / Item / Character hierarchy
  actions/                 Action system: check_preconditions() -> apply_effects()
  blocks/                  Obstacles that gate movement until a condition is met
  parsing.py               Keyword command parser
  games.py                 Game loop, world state, turn-based NPC rounds
  npc.py                   ReAct NPC behavior (SKELETON — see Roadmap)
  llm_client.py            Provider-agnostic LLM client (OpenAI / Anthropic)
  llm_parser.py            LLM-backed parser (keyword-first, LLM fallback)
  webapp/                  Flask web UI for playing in the browser
notebooks/                 Notebooks: HW1 "Action Castle" onboarding + framework demos
tests/                     Pytest suite (agent layer, ReAct live game, NPC behaviors)
FEATURE-ROADMAP.md         Technical specs for the framework features to build
ROADMAP.md                 The summer plan: phases, who owns what
ONBOARDING.md              Start here on day one
```

## What already works vs. what we're building

**Works today:** the full text-adventure engine; a real **turn-based loop** where
NPCs take a turn each round (`do_command()` → `end_turn()` → `Character.take_turn()`),
with NPC actions correctly gated through `check_preconditions()`; scripted NPC
behaviors (troll, guard, ghost); a provider-agnostic LLM client and an
LLM-backed parser; terminal, Jupyter, and Flask front ends.

**We're building** (this is the summer): promoting NPCs to **first-class agents**
with goals and memory; a real **ReAct loop with a Reflect step** (today `npc.py` is
an untested skeleton with no reflection and isn't wired into the live game); an
**event/trigger** system; a **time** model; **agent-to-agent** interaction; and a
**Godot 2D bridge**. See [`ROADMAP.md`](ROADMAP.md) and
[`FEATURE-ROADMAP.md`](FEATURE-ROADMAP.md).

**Longer-term, lower priority** (not on the critical path — revisit as agent
counts grow and real-provider runs get costly): LLM **cost & observability** —
per-call token/usage accounting, Anthropic prompt caching, per-run usage logs,
and reproducible (seeded / replayable) runs. Design sketch in
[`docs/design/llm-cost-observability.md`](docs/design/llm-cost-observability.md).

## Setup

This project is set up for **[uv](https://docs.astral.sh/uv/)** — it's the default
path and the fastest. The committed `uv.lock` + `.python-version` give everyone the
same dependency versions and interpreter (Python 3.12), and `uv` manages the
`.venv/` for you, so there's no `pip`-vs-`python` mismatch to trip over.

```bash
uv sync --extra llm                   # creates .venv/, installs engine + openai, anthropic, tiktoken
# or: uv sync                         # engine only
# or: uv sync --extra dev             # + black, nbformat, pytest (dev team)
```

Then prefix commands with `uv run` (it auto-uses `.venv/`, no activation needed) —
or `source .venv/bin/activate` once if you prefer. Don't have uv?
`curl -LsSf https://astral.sh/uv/install.sh | sh`.

<details>
<summary><b>No uv? Plain <code>venv</code> + <code>pip</code> still works</b></summary>

Always work inside an **isolated virtual environment** so you don't fight your
system / Anaconda / Homebrew Python.

```bash
python3 -m venv venv
source venv/bin/activate              # prompt should now show (venv)
pip install -e ".[llm]"               # engine + openai, anthropic, tiktoken
# or: pip install -e "."              # engine only
# or: pip install -e ".[dev]"         # + black, nbformat, pytest (dev team)
```

**If you use Anaconda/Miniconda**, use a conda env instead (Anaconda's `venv` is
often broken):

```bash
conda create -n agent-sandbox python=3.12 -y && conda activate agent-sandbox
pip install -e ".[llm]"
```

> **`ModuleNotFoundError` after install?** Your `pip` and `python` are different
> interpreters. Install with `python -m pip install -e ".[llm]"` so it lands in the
> same Python you run with, and confirm your venv/conda env is activated. See
> `ONBOARDING.md` for the full troubleshooting list. (This whole class of problem
> is why uv is the default above.)

</details>

### Run the game in your browser

```bash
uv run python -m text_adventure_games.webapp.app   # or activate first, then drop `uv run`
# open http://localhost:8080
```

### Running the LLM version (LLM-driven NPCs + natural-language parser)

By default the NPCs use hand-scripted behaviors and the parser is keyword-based.
Set a provider before launching and the troll/guard/ghost become **LLM-driven**
and the player's parser accepts **natural language**.

You need a pay-as-you-go **API key** (from console.anthropic.com or
platform.openai.com) — this is *separate* from a Claude Code subscription; the SDK
bills per token.

```bash
export LLM_PROVIDER=anthropic        # the on-switch: "anthropic" or "openai"
export ANTHROPIC_API_KEY=sk-ant-...  # or OPENAI_API_KEY=sk-... for openai
export LLM_VERBOSE=1                  # optional: print every LLM call (great for debugging)
uv run python -m text_adventure_games.webapp.app
```

Optional env vars: `LLM_MODEL` (defaults: Anthropic → `claude-sonnet-4-20250514`,
OpenAI → `gpt-4o-mini`), `LLM_NARRATION_STYLE` (a tone hint for the narrator),
`LLM_BASE_URL` (for an OpenAI-compatible endpoint).

Then walk to the **Drawbridge** and loiter near the troll; with `LLM_VERBOSE=1`
you'll see the prompts and the NPC's chosen commands in the terminal. Try
natural-language commands too, e.g. *"give the fish to the troll."*

**What this is (and isn't):** with a provider set, each NPC uses
`make_hybrid_behavior` (`npc.py`) — it asks the LLM for an action, runs it through
the same `check_preconditions()` gate as the player, and on failure **Reflects**:
the parser's actual failure reason is fed back to the agent, which retries with a
different action. If the LLM errors entirely, the NPC **falls back to the scripted
behavior**. Still no memory — that's Phase 2; see [`ROADMAP.md`](ROADMAP.md).

### The free offline demo (no API key)

`LLM_PROVIDER=mock` swaps in `MockReActClient` — a deterministic stand-in that
reads the same prompts a real model would see and picks in-character commands.
The whole ReAct loop runs end-to-end at no cost:

```bash
LLM_PROVIDER=mock uv run python -m notebooks.hw1_llm.play          # terminal
LLM_PROVIDER=mock uv run python -m text_adventure_games.webapp.app  # browser
```

`notebooks/hw1_llm/` is a thin wrapper around the HW1 game: same world, but
troll/guard/ghost are driven by **pure ReAct** (`make_react_behavior`, no
scripted fallback), so every NPC action you see was reasoned by the agent.
Each decision is traced with explicit labels. Walk to the Drawbridge (`go
out`, `go north`, `go east`) and `wait` a few times:

```
troll [reasoning] Growling and snarling didn't drive the intruder off. Attack.
troll [action] attack player
troll doesn't have a weapon.                <- rejected by check_preconditions()
troll [reasoning] My attack failed because I never said which weapon to use.
troll [action] attack player with club      <- the Reflect step fed the reason back
troll attacked The player with the club.
```

New to reading this output — the colors, prefixes, and indented agent blocks?
See [`docs/reading-the-output.md`](docs/reading-the-output.md), a guide to
interpreting what the game prints (and how to show more or less of it).

### Run the tests

```bash
uv run pytest tests/ -v                     # full suite: agent layer, ReAct live game, NPC behaviors
uv run pytest tests/test_npc_behaviors.py -s  # watch the NPC behavior suite, narrated
```

### Browse the documentation site

A local [MkDocs](https://www.mkdocs.org/) site (Material theme) serves this home
page plus an API reference pulled from the engine's docstrings. It's **local-only**
— nothing is published to the internet.

```bash
source venv/bin/activate
pip install -e ".[docs]"             # mkdocs-material + mkdocstrings
cd mkdocs && mkdocs serve            # then open http://127.0.0.1:8000
```

`mkdocs build` (also from the `mkdocs/` directory) renders a static site under
`mkdocs/site/` (git-ignored) that you can zip and share with collaborators. The
design notes and guides in [`docs/`](docs/) are read directly on GitHub and aren't
part of this site.

### Onboarding assignment

The HW1 "Action Castle" notebook in [`notebooks/`](notebooks/) is the day-one ramp.
See [`ONBOARDING.md`](ONBOARDING.md). The same folder holds a numbered walkthrough of
the library's features — start with [`notebooks/README.md`](notebooks/README.md) for the
reading order. [`02_agents_react.ipynb`](notebooks/02_agents_react.ipynb) is the agent
framework demo (mock-LLM agents, clock, triggers, event log).

## Credits

Engine adapted from the UPenn Interactive Fiction class
([interactive-fiction-class.org](https://interactive-fiction-class.org/)),
itself inspired by the Adventuron Classroom design by Chris Ainsley. Licensed MIT.
