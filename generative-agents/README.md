# Generative Agents ("Smallville") — ported onto our engine

This folder runs Stanford's [Generative Agents](https://github.com/joonspk-research/generative_agents)
**visualization** (the Smallville tile map and character sprites), but drives it
with a backend built on this repo's `text_adventure_games` engine instead of the
original `reverie` server. For now there is **no live LLM**: the cast is driven by
the engine's mock LLM client, producing a **simplified ~1-hour simulation** of
three agents going about their morning.

It's a first step toward a full port. See `../docs/design/generative-agents-port.md`
for the survey of the upstream world and cast that this builds on.

![what you'll see: Isabella, Maria, and Klaus moving around Smallville]

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
   become `Location`s, the three personas become `Character`s with first-person
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

You need **two Python environments** (this is the one fiddly part):

| Piece | Python | Why |
|-------|--------|-----|
| Backend (sim generator) | this repo's `venv` (the engine's) | imports `text_adventure_games` |
| Frontend (Django visualizer) | a **separate Python 3.9** venv | Django 2.2 doesn't run on modern Python |

```bash
cd generative-agents

# 1. Copy the visualizer + ~38MB of map/sprite assets from the external/ clone.
#    (The full upstream frontend is ~1GB of example sims we don't need.)
./setup.sh

# 2. Generate a 1-hour simulation using the engine's venv.
../venv/bin/python -m backend.run_simulation            # 360 steps (1 hour)
#    fewer steps:  ../venv/bin/python -m backend.run_simulation --steps 120

# 3. Run the Django frontend in its OWN Python 3.9 venv.
python3.9 -m venv frontend-venv
./frontend-venv/bin/pip install -r requirements-frontend.txt
(cd frontend && ../frontend-venv/bin/python manage.py runserver)

# 4. Open the replay in your browser:
#    http://localhost:8000/replay/mock_the_ville_isabella_maria_klaus/0/
```

> **The map lives at the `/replay/...` URL above, not at the root.** Opening
> `http://localhost:8000/` just shows a status page ("environment server is up and
> running") — now with a link to the replay. If you only see that text, click the
> link or go straight to the `/replay/...` URL.

You should see Isabella, Maria, and Klaus wake at their homes, walk believable
paths through town, and settle into their morning activities — Isabella tending
the Hobbs Cafe counter (☕), Maria studying there (📚), and Klaus writing his paper
in the Oak Hill College library (✍️). Click a character to see their state panel.

## The simulation

Three agents, starting 8:00 AM on Feb 13 (the town is asleep at the base sim's
midnight, so we start later). Each has a simple morning goal:

| Agent | From | Goes to | Does |
|-------|------|---------|------|
| Isabella Rodriguez | her apartment | Hobbs Cafe | tends the cafe counter ☕ |
| Maria Lopez | the dorm | Hobbs Cafe | studies at a table 📚 |
| Klaus Mueller | the dorm | Oak Hill College | writes in the library ✍️ |

One step = 10 in-game seconds; 360 steps = one hour.

## Tests

Offline, no Django, no LLM. From this directory, with the engine's venv:

```bash
../venv/bin/python -m pytest tests/ -v
```

They cover the world build + mock-driven decisions, address→tile resolution and
collision-free pathing, and the exported movement-file contract. (They skip if
the maze assets aren't present — run `./setup.sh` first.)

## Extending it

- **Different routines / more activities:** edit `PERSONAS` in
  `backend/build_world.py` (destination, activity, emoji, start tile). The mock
  brain in `backend/smallville_agents.py` reads each agent's current location and
  chooses travel-vs-perform; a multi-stop schedule is a natural next step.
- **More of the cast (up to 25):** add personas + their home/destination
  `Location`s. The world and tile addresses are data-driven.

## Not done yet (future work)

- **Live LLM agents** — swap `SmallvilleMockClient` for a real client via the
  engine's `client_from_env()`; the `Agent.decide` seam is identical.
- **Conversations** (`chat`), the **memory stream**, and the **full 25-agent town**.
- **Live (non-replay) mode**, where the backend serves `update_environment`
  step-by-step instead of pre-generating the whole run.

## Layout

```
generative-agents/
  setup.sh                    # copy frontend + assets from the external/ clone
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
  frontend/                   # (git-ignored) populated by setup.sh
```

## Credits

The map art, sprites, and the Django visualizer are from the Generative Agents
project (Park et al., UIST '23), Apache-2.0. This port only adds the engine-backed
backend under `backend/`.
