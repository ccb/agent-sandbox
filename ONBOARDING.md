# Onboarding — start here

Welcome to the summer research team! This guide gets you from zero to
contributing. It's written for first- and second-year students — no prior
research experience assumed. Take your time, and lean on **Claude Code** to
explain anything that's unclear (more on that below).

The goal of week one is shared: everyone builds the same mental model of how the
engine works, so we can start extending it together.

## 0. Logistics

- **Where:** the lab. Core hours are roughly **10–4, Monday–Thursday**; Fridays
  flexible. Grab a free desk (7–16) and put your name on it.
- **Slack:** `#summer-research-26` is our main channel. Also join the reading-group
  and CCB-lab-members channels. Add your full name and a profile photo.
- **Claude Code:** you'll get a subscription. If you hit rate limits often, ping
  Chris to bump your plan up for the summer.
- **Let Chris know** any travel dates so we can plan around them.

## 1. Get the code running

Work inside an **isolated virtual environment** — don't install into your system
or Anaconda Python (that's the #1 source of "it won't import" headaches; see
Troubleshooting below).

We use [**uv**](https://docs.astral.sh/uv/) — one tool that creates the
environment, installs everything from the committed lockfile (so you get the exact
same versions as everyone else), and runs commands. Install it first if you
haven't: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
git clone https://github.com/ccb/agent-sandbox.git
cd agent-sandbox
uv sync --extra llm              # creates .venv/ and installs the engine + LLM SDKs
uv run python -m text_adventure_games.webapp.app   # then open http://localhost:8080
```

`uv run` automatically uses the project's `.venv/`, so there's nothing to
"activate" — every time you come back, just prefix commands with `uv run`. (If you
prefer the classic feel, `source .venv/bin/activate` once and drop the prefix.)
Stop the server with `Ctrl+C`.

Don't want uv? The classic flow still works:

```bash
python3 -m venv venv             # create an isolated environment
source venv/bin/activate         # activate it — your prompt should now show (venv)
pip install -e ".[llm]"          # install the engine + LLM SDKs into the venv
python -m text_adventure_games.webapp.app   # then open http://localhost:8080
```

Play through a bit of Action Castle in the browser so you know what the engine
*does* before you read how it works.

### Troubleshooting setup

- **`ModuleNotFoundError: No module named 'flask'` even though pip said it installed.**
  Your `pip` and your `python` are different interpreters. Always install with
  `python -m pip install -e ".[llm]"` (note the `python -m`) so pip installs into
  the *same* Python you run with. And make sure your venv is activated — the prompt
  should show `(venv)`.
- **You use Anaconda/Miniconda.** Anaconda's `python -m venv` is often broken
  (`ensurepip` errors), and bare `pip` may target a different interpreter than
  `python`. Use a conda env instead of a venv:
  ```bash
  conda create -n agent-sandbox python=3.12 -y
  conda activate agent-sandbox
  pip install -e ".[llm]"
  ```
- **`error: externally-managed-environment`.** You're trying to install into a
  Python that isn't yours to modify (system / Homebrew / uv-managed). Make and
  activate a venv (or conda env) first, then install — never use
  `--break-system-packages`.
- **Quote the extras** as `".[llm]"`. In some shells (zsh) the bare `.[llm]` is
  interpreted as a glob and fails.

## 2. Do HW1: Action Castle

Open `notebooks/hw1.ipynb`. It's a mostly-complete text adventure with a few holes
marked for you to fill in. Completing it teaches you the four core concepts the
whole project is built on:

- **Locations** and the connections between them (the world graph)
- **Items** and **Characters** (the things in the world)
- **Actions** with **preconditions** and **effects** (the rules of the world)
- **Blocks** (obstacles that gate movement until you solve them)

If you get stuck, `notebooks/hw1_solution/` has a complete version — but try first.

## 3. Learn to use Claude Code as a study partner

A parallel goal this summer is getting fluent with AI coding agents. While you
work through HW1 and read the engine, practice asking Claude Code things like:

- "Explain what `Game.end_turn()` in `games.py` does, step by step."
- "Trace what happens when the player types `unlock door with key`."
- "Why does the troll attack me? Show me the precondition that triggers it."
- "What's the difference between a `Block` and an action precondition?"

Try it on the **terminal** (Chris's preferred way), and also experiment with the
desktop app and an IDE integration (Mekides uses Cursor). Share anything cool you
learn in Slack — we're all figuring out the best workflows together.

### Recommended Claude Code plugins

We enable two [Claude Code plugins](https://code.claude.com/docs/en/plugins) for
everyone via `.claude/settings.json` — when you open the repo, Claude Code prompts
you to install them from the auto-registered `claude-plugins-official` marketplace:

- **`pyright-lsp`** — gives Claude live Python type-checking after every edit, so it
  catches mistakes as it works. Needs `pyright` on your machine
  (`uv tool install pyright`, or `npm i -g pyright`); without it the plugin just
  stays idle.
- **`github`** — native GitHub issue/PR context, so Claude reads and works with the
  tracker directly instead of shelling out to `gh`.

Browse more with `/plugin` (Discover tab). A couple worth trying solo:
`learning-output-style` / `explanatory-output-style` (Claude narrates *why*, nice
while you're still learning the engine) and `pr-review-toolkit` (dedicated PR-review
agents). Run `/reload-plugins` after installing to apply without restarting.

## 4. Read the engine (in this order)

Once HW1 makes sense, read the actual framework. A good reading order, smallest to
largest:

1. `text_adventure_games/things/base.py` → `characters.py`, `items.py`,
   `locations.py` — the `Thing` hierarchy.
2. `text_adventure_games/actions/` — the `Action` base class and a few subclasses.
   This is **the most important part**. Notice how `check_preconditions()` reads
   almost like English (`at()`, `has_property()`, `is_in_inventory()`).
3. `text_adventure_games/parsing.py` — the keyword parser. (It's intentionally
   brittle; replacing it with an LLM is one of our projects.)
4. `text_adventure_games/games.py` — the `Game` loop. Focus on `do_command()` and
   `end_turn()` — this is the **turn-based loop** where NPCs act each round.

Then read `tests/test_npc_behaviors.py` and run it narrated with
`pytest tests/test_npc_behaviors.py -s` to see the NPC system exercised
end-to-end (the troll escalating to an attack is a nice example).

> Skip `Game.from_primitive()` in `games.py` for now — it's gnarly save/load code
> and not important for understanding the engine.

## 5. Skim where we're heading

- Read [`ROADMAP.md`](ROADMAP.md) — the summer plan and who owns what.
- Skim [`FEATURE-ROADMAP.md`](FEATURE-ROADMAP.md) — the technical specs for the
  framework features we'll build. Don't worry if parts are over your head yet.
- Read the two background papers when you're ready: **Generative Agents**
  (the Smallville paper) and **ReAct**. We'll discuss them as a group.

## 6. Start exploring Godot (the game-leaning folks)

If you're drawn to the visual/game side, install [Godot 4](https://godotengine.org/)
and do a beginner tutorial or two. Try vibe-coding a tiny thing (a dice roller, a
sprite that moves) with Claude Code to see how well it knows GDScript. We'll
eventually render the simulation in Godot, so getting comfortable now pays off.

**Where your Godot/map work lands.** The Godot frontend —
`godot-generative-agents/`, which houses the backend, the viewer, and the
map-generation tooling under `godot-generative-agents/tools/geo/` — lives on
`main` like everything else (its old dedicated branch, `godot-ga-main`, was
retired in July 2026). Changes under that folder are reviewed by the Godot/geo
owners (@aking526 + @0frankie), so you're not blocked on the full engine review;
anything touching the shared engine (`text_adventure_games/`) gets the normal
`main` review.

## Done with week one?

You should be able to: run the game, explain the action precondition/effect system
in your own words, and point to where in `games.py` NPCs take their turns. Once
you're there, grab an issue from the tracker (look for the **`good first issue`**
and **`phase-1`** labels) and let's start building.
