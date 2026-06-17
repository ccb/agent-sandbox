# Generative Agents ("Smallville") — ported onto our engine

This folder runs Stanford's [Generative Agents](https://github.com/joonspk-research/generative_agents)
**visualization** (the Smallville tile map and character sprites), but drives it
with a backend built on this repo's `text_adventure_games` engine instead of the
original `reverie` server. For now there is **no live LLM**: the cast is driven by
the engine's mock LLM client, producing a **simplified ~1-hour simulation** of the
full 25-resident town going about its morning.

It's a first step toward a full port. See `../docs/design/generative-agents-port.md`
for the survey of the upstream world and cast that this builds on.

![what you'll see: the 25 residents of Smallville moving around town]

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

You should see all 25 residents wake at their homes, walk believable paths
through town, and settle into their morning activities — Isabella tending the
Hobbs Cafe counter (☕), Maria studying there (📚), Klaus writing his paper in the
Oak Hill College library (✍️), Arthur opening the pub (🍺), Wolfgang out for a run
(🏃), and so on. Click a character to see their state panel.

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

## Tests

Offline, no Django, no LLM. From this directory (`uv run` uses the repo's project env):

```bash
uv run pytest tests/ -v
```

They cover the world build + mock-driven decisions, address→tile resolution and
collision-free pathing, and the exported movement-file contract. (They skip if
the maze assets aren't present — run `./setup.sh` first.)

## Extending it

- **Different routines / more activities:** edit `PERSONAS` in
  `backend/build_world.py` (destination, activity, emoji, start tile). The mock
  brain in `backend/smallville_agents.py` reads each agent's current location and
  chooses travel-vs-perform; a multi-stop schedule is a natural next step.
- **Add or change residents:** each persona is one dict in `PERSONAS` and each
  place one dict in `_LOCATIONS` — both data-driven. A new resident just needs a
  sprite named to match (`First_Last.png` under `static_dirs/assets/characters/`).

## Not done yet (future work)

- **Live LLM agents** — swap `SmallvilleMockClient` for a real client via the
  engine's `client_from_env()`; the `Agent.decide` seam is identical.
- **Conversations** (`chat`) and the **memory stream** (agents currently follow a
  fixed wake → travel → perform routine rather than reasoning over memories).
- **Live (non-replay) mode**, where the backend serves `update_environment`
  step-by-step instead of pre-generating the whole run.

## Known issues

- **Replay map doesn't fill the view on some setups (UNRESOLVED).** The map is
  meant to fill the view from the top-left, with camera zoom/pan (`Scale.RESIZE`,
  a "cover" default zoom, on-screen +/-/Reset). On at least one machine it instead
  renders centered / pushed to the bottom-right with black space along the top and
  left, and rightward panning is limited. The camera/scale logic verifies correct
  in headless Chrome at devicePixelRatio 1 and 2, so the root cause is still
  unknown. **Workaround:** click **Hide map** on the replay page to collapse the
  map and read the agent-info panels (current action, location, conversation)
  directly — the replay keeps running while the map is hidden. See the notes in
  `setup.sh` and `frontend_overrides/templates/home/main_script.html`.

## Layout

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
  frontend/                   # (git-ignored) populated by setup.sh (clone + overrides)
```

## Credits

The map art, sprites, and the Django visualizer are from the Generative Agents
project (Park et al., UIST '23), Apache-2.0. This port only adds the engine-backed
backend under `backend/`.
