# Generative Agents ("Smallville") — ported onto our engine

This folder runs Stanford's [Generative Agents](https://github.com/joonspk-research/generative_agents)
**visualization** (the Smallville tile map and character sprites), but drives it
with a backend built on this repo's `text_adventure_games` engine instead of the
original `reverie` server. By default the cast is driven by a **deterministic mock
LLM client** (free, offline) producing a **simplified ~1-hour simulation** of the full
25-resident town going about its morning; set `LLM_PROVIDER` (anthropic / openai) to
drive the travel/perform decisions and daily planning with a **live model** instead
(#78 / Phase A — see [Not done yet](#not-done-yet-future-work)).

The sections below cover **running it, contributing, and where the files live**.
The substance — what it is and how it works — is further down, under
[How it works](#how-it-works).

![what you'll see: the 25 residents of Smallville moving around town]

## Quick start

```bash
cd generative-agents
./run-replay.sh
```

`run-replay.sh` does the whole dance for you: it sets up the frontend assets if
needed, **generates the simulation only if it hasn't been generated already**
(otherwise it skips straight to serving), creates the Django venv on first run, then
starts the frontend and prints the replay URL (and opens it on macOS). Re-running is
safe and fast. Flags: `--rebuild` (force-regenerate the sim), `--steps N` (sim
length, passed through), `--port N` (default 8000).

That's it. The rest of this section explains what it does under the hood, for
debugging or running the pieces by hand.

### Prerequisite: the upstream clone

The frontend assets (map, sprites, the Django visualizer) are **not committed** —
they're copied from a local clone of the upstream repo that you provide once:

```bash
git clone https://github.com/joonspk-research/generative_agents.git \
  ../external/generative_agents
```

`setup.sh` reads from `../external/generative_agents/environment/frontend_server`.
The `external/` directory is git-ignored at the repo root, so this clone is a
local-only prerequisite. (`run-replay.sh` runs `setup.sh` for you; you just need
the clone to exist.)

### Under the hood (manual steps)

You need **two Python environments** (this is the one fiddly part):

| Piece | Python | Why |
|-------|--------|-----|
| Backend (sim generator) | the repo's **uv project env** (`uv run`) | imports `text_adventure_games` |
| Frontend (Django visualizer) | a **separate Python 3.9** venv (uv-managed) | Django 2.2 doesn't run on modern Python |

```bash
cd generative-agents

# 1. Copy the visualizer + ~38MB of map/sprite assets from the external/ clone.
#    (The full upstream frontend is ~1GB of example sims we don't need.)
./setup.sh

# 2. Generate a 1-hour simulation. `uv run` finds the repo's project env (one
#    level up) and provisions it with the engine on first use.
uv run python -m backend.run_simulation                 # 360 steps (1 hour)
#    fewer steps:  uv run python -m backend.run_simulation --steps 120
#    other clock:  uv run python -m backend.run_simulation \
#                      --start "2023-02-13 18:00:00" --sec-per-step 60
#    embeddings:   uv sync --extra embeddings    # one-time; then:
#                  uv run python -m backend.run_simulation --embeddings local
#    (--help lists all flags: --steps, --start, --sec-per-step, --embeddings, ...)

# 3. Run the Django frontend in its OWN Python 3.9 venv. uv fetches a managed
#    CPython 3.9 if you don't have one, so there's nothing to install by hand.
uv venv --python 3.9 frontend-venv
uv pip install --python frontend-venv -r requirements-frontend.txt
(cd frontend && ../frontend-venv/bin/python manage.py runserver)

# 4. Open the replay in your browser:
#    http://localhost:8000/replay/mock_the_ville_n25/0/
```

> **The map lives at the `/replay/...` URL above, not at the root.** Opening
> `http://localhost:8000/` just shows a status page ("environment server is up and
> running") — now with a link to the replay. If you only see that text, click the
> link or go straight to the `/replay/...` URL.

## Tests

Offline, no Django, no LLM. From this directory (`uv run` uses the repo's project env):

```bash
uv run pytest tests/ -v
```

They cover the world build + mock-driven decisions, address→tile resolution and
collision-free pathing, and the exported movement-file contract. (They skip if
the maze assets aren't present — run `./setup.sh` first.)

## Trying it with a live LLM (Phase A)

By default everything runs on the free, offline **mock** brain. To drive the
agents' travel/perform decisions **and** their daily plans with a real model,
install the LLM extra and set `LLM_PROVIDER`:

```bash
uv sync --extra llm                     # installs openai + anthropic
export LLM_PROVIDER=anthropic           # or: openai
export ANTHROPIC_API_KEY=sk-...         # or OPENAI_API_KEY; LLM_API_KEY also works
# optional: export LLM_MODEL=claude-opus-4-8   # else the provider default
```

**Smoke-test first** (cheap, fast, **needs no `setup.sh` assets**). This builds the
world, generates a couple of agents' days with the live model, and runs a handful
of real decisions through the precondition gate — enough to catch prompt / parsing
/ key / latency problems before a full run:

```bash
uv run python -m backend.smoke_llm                  # 2 agents, 6 decision rounds
uv run python -m backend.smoke_llm --agents 3 --steps 10
```

It prints each generated plan, then each decision with whether it passed the gate
(the usual failure is the model naming a place that isn't a known location — shown
with the gate's reason), and finally a token/cost summary. With `LLM_PROVIDER`
unset or `mock` it exits with a message instead of running.

**Then a full replay** with the same env set (this *does* need the maze assets, so
run `./setup.sh` first). Start small to keep cost down:

```bash
uv run python -m backend.run_simulation --steps 120
```

`run_simulation` prints which brain it's using (`LLM brain: anthropic …` vs
`LLM brain: none …`), how many agents the model actually planned (`Daily plans: N
generated by the model, …`), and a per-run cost summary; it writes a usage log when
`--llm-log DIR` (or the config's `observability.log_path`) is set. Unset
`LLM_PROVIDER` (or set it to `mock`) to return to the deterministic, byte-identical
offline replay.

Each run also **saves every agent's generated plan** to
`storage/<sim>/personas/<Name>/daily_plan.json`. To inspect one persona's static
schedule beside the plan the last run used — fast and free, no model calls:

```bash
uv run python -m backend.compare_plans --resident "Klaus Mueller"
```

Add `--generate` to make a *fresh* plan with the live model instead (3 calls,
nondeterministic) when you haven't run the sim or want generation in isolation.

## Extending it

- **Different routines / more activities:** edit `PERSONAS` in
  `backend/build_world.py` (destination, activity, emoji, start tile). The mock
  brain in `backend/smallville_agents.py` reads each agent's current location and
  chooses travel-vs-perform; a multi-stop schedule is a natural next step.
- **Add or change residents:** each persona is one dict in `PERSONAS` and each
  place one dict in `_LOCATIONS` — both data-driven. A new resident just needs a
  sprite named to match (`First_Last.png` under `static_dirs/assets/characters/`).
- **Compare memory retrieval (issue #102):** `uv run python -m
  backend.compare_retrieval --embeddings local` accrues a real memory stream for
  each resident, then prints keyword-overlap vs semantic (embedding) retrieval
  side by side — the believability check for whether semantic recall surfaces
  better memories. Offline and needs no `setup.sh` assets (`build_world` only).

## Where the files live

Committed to the repo (this folder):

```
generative-agents/
  run-replay.sh               # one command: generate-if-needed + serve the replay
  setup.sh                    # copy frontend + assets from the clone, then apply overrides
  requirements-frontend.txt   # Django 2.2 etc. (frontend venv only)
  backend/
    build_world.py            # Smallville world + cast in the engine
    actions.py                # custom Travel / Act actions
    smallville_agents.py      # mock-LLM brains (SmallvilleMockClient)
    world_map.py              # maze loader: address -> tiles, walk paths
    path_finder.py            # vendored BFS pathfinder (Apache-2.0, upstream)
    exporter.py               # write the frontend's movement/environment/meta files
    run_simulation.py         # the driver + CLI entry point
  tests/                      # offline tests
  frontend_overrides/         # committed replay-UI files setup.sh copies into frontend/
```

Local-only, **not committed** (you generate or clone these — see the
[prerequisite](#prerequisite-the-upstream-clone) and `.gitignore`):

```
../external/generative_agents/   # the upstream clone you provide; setup.sh reads from it
generative-agents/
  frontend/                   # populated by setup.sh (upstream tree + frontend_overrides)
  frontend/storage/<sim>/     # the movement/environment/meta files the backend generates
  frontend-venv/              # the frontend's separate Python 3.9 / Django 2.2 venv
  **/__pycache__/, *.pyc      # Python caches
```

> Because `frontend/` itself is git-ignored, edits made directly under it are **not
> tracked** and get wiped by `setup.sh`'s `rsync --delete`. Replay-UI changes belong
> in `frontend_overrides/` (committed), which `setup.sh` copies over the freshly
> rsynced upstream tree on every run.

---

## How it works

The original frontend and backend talk through a tiny file contract. In **replay
mode** the browser only ever talks to Django: Django reads
`storage/<sim>/movement/<step>.json` and feeds it to the browser, which animates
the sprites. **Nothing about replay needs a live backend** — it just needs those
movement files to exist.

So the port is split cleanly in two:

```
   our engine + mock LLM            files on disk              upstream Django
  ┌───────────────────────┐      ┌────────────────┐         ┌─────────────────┐
  │ backend/              │ ───► │ frontend/      │  ◄────► │ browser (Phaser)│
  │  build world,         │write │  storage/<sim>/│  serve  │  replays the    │
  │  decide w/ mock LLM,   │      │   movement/*.json│        │  movement files │
  │  walk tiles, export   │      │   environment/  │         │                 │
  └───────────────────────┘      │   reverie/meta  │         └─────────────────┘
                                  └────────────────┘
```

The backend (`backend/`) does three things:

1. **Builds the world in the engine** (`build_world.py`): Smallville's places
   become `Location`s, the 25 personas become `Character`s with first-person
   persona text, and two custom actions (`actions.py`) let them `travel` and
   `perform` through the normal precondition gate.
2. **Decides with the mock LLM** (`smallville_agents.py`): each persona is driven
   by a `SmallvilleMockClient` (a subclass of the engine's `MockReActClient`) — a
   deterministic stand-in for a model. The decision flows through the engine's
   real `Agent.decide` → parser seam; it's just not a live model.
3. **Bridges to tiles and exports** (`world_map.py`, `run_simulation.py`,
   `exporter.py`): the engine is a graph of places, but the frontend needs an
   `(x, y)` tile per character per step. `world_map.py` loads the upstream maze
   data and (via the vendored `path_finder.py`) turns "go to Hobbs Cafe" into a
   tile-by-tile walk; `exporter.py` writes the movement files the frontend reads.

When you open the replay you should see all 25 residents wake at their homes, walk
believable paths through town, and settle into their morning activities — Isabella
tending the Hobbs Cafe counter (☕), Maria studying there (📚), Klaus writing his
paper in the Oak Hill College library (✍️), Arthur opening the pub (🍺), Wolfgang
out for a run (🏃), and so on. Click a character to see their state panel.

## The simulation

The full **25-resident** town, starting 8:00 AM on Feb 13 (the town is asleep at
the base sim's midnight, so we start later). Each resident wakes at home and heads
to where they spend their day:

| Destination | Residents |
|-------------|-----------|
| **Hobbs Cafe** ☕ | Isabella (tends counter), Maria (studies), Ryan (codes), Adam (writes), Abigail (animates), Hailey (novel), Tamara (kids' book) |
| **Oak Hill College** 📚 | Klaus (paper), Ayesha (studies), Eddy (composes), Mei (teaches), Giorgio (math), Yuriko (tax filings) |
| **Johnson Park** 🌳 | Wolfgang (run), Carlos (poetry), Francisco (comedy), Latoya (photos), Rajiv (paints), Jennifer (watercolors), Sam (strolls) |
| **Willows Market & Pharmacy** 🛒 | John (pharmacy), Tom (grocery), Jane (shopping) |
| **Harvey Oak Supply Store** 🔧 | Carmen (minds the store) |
| **The Rose and Crown Pub** 🍺 | Arthur (tends the bar) |

One step = 10 in-game seconds; 360 steps = one hour. Personas, traits, and home
addresses are lifted from the upstream `the_ville` base sim; each name also picks
the matching sprite (`John Lin` → `John_Lin.png`).

This is a first step toward a full port. See
`../docs/design/generative-agents-port.md` for the survey of the upstream world
and cast that this builds on.

## Not done yet (future work)

- **Live LLM agents** — ✅ wired (#78). Set `LLM_PROVIDER` (anthropic / openai) and
  `run_simulation` drives each agent's travel/perform decision through a real model
  (and generates the day with `LLMPlanner`); a `SmallvilleMockClient` still paces the
  schedule. Unset or `mock` keeps the deterministic mock as both brain and driver, so
  the offline replay is byte-identical. Not yet run against a live model end to end.
- **Conversations** (`chat`) — residents follow a fixed wake → travel → perform
  routine and don't yet talk to each other. They *do* now carry a private
  **memory stream** (issue #75): each perceives co-located neighbors, remembers
  its own actions, and has the retrieved memories folded into every observation
  (`backend/smallville_agents.py`). Memory relevance can now be scored
  *semantically* with embeddings (issue #102, `--embeddings`) instead of keyword
  overlap; `backend/compare_retrieval.py` measures the difference directly. The
  deterministic mock brain still decides from location alone, so the replay is
  unchanged either way — but a live LLM would reason over those retrieved
  memories. Reflection and plan *generation* (design Stages 5–7) remain future work.
- **Live (non-replay) mode**, where the backend serves `update_environment`
  step-by-step instead of pre-generating the whole run.

## Known issues

_(none open — the replay-map fill bug below is resolved.)_

### Resolved: replay map black space / didn't fill the view

The replay map used to render with black space along the top and left (the world
shoved toward the bottom-right) and with stretches of black on the right and
bottom. This was **two independent bugs**, both now fixed in
`frontend_overrides/templates/home/main_script.html`:

1. **Black on the top/left** — a Phaser camera zooms around its *origin*, which
   defaults to the center `(0.5, 0.5)`. At our zoomed-out "cover" default
   (fractional zoom < 1, since the map dwarfs the canvas) that meant `scroll = 0`
   put a *negative* world coordinate at the screen's top-left corner, so the
   map's top/left edges floated in black. Fixed by pivoting the camera around its
   top-left: `camera.setOrigin(0, 0)`.
2. **Black on the right/bottom** — Phaser 3.55's tile culling under-counts which
   tiles are on-screen at fractional zoom, so most of the map (the base grass
   layer especially — only ~4,400 of 14,000 tiles were drawn) silently dropped
   out. Fixed by disabling per-tile culling on this small map
   (`tilemapLayer.setSkipCull(true)` on every layer).
3. **Black when you zoomed all the way out** — even with the map drawn correctly,
   the minimum zoom used to be the "fit the whole map" zoom, which on a window
   whose aspect ratio differs from the map's (≈1.4) leaves slack — and thus black
   bars — on one axis (the right on a typical wide window). Fixed by making the
   zoom floor the *cover* zoom instead: the most zoomed-out view now exactly fills
   the canvas, and the off-screen axis is reached by panning rather than by zooming
   out into a void. (`minZoom = coverZoom`; the Reset button returns to it.)

Verified headless at devicePixelRatio 2 from a clean template load: the camera's
top-left pixel maps to world `(0, 0)`, all 14,000 base tiles draw, and after
mashing zoom-out the camera stops at the cover zoom with the whole canvas still
full of map. The **Hide map** button remains as a convenience for reading the
agent-info panels, not a workaround.

## Credits

The map art, sprites, and the Django visualizer are from the Generative Agents
project (Park et al., UIST '23), Apache-2.0. This port only adds the engine-backed
backend under `backend/`.
