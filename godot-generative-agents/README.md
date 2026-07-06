# godot-generative-agents

A tiny [Godot 4.6](https://godotengine.org) sandbox that renders the **real
University of Pennsylvania campus** in Godot and plays back a generative-agents
simulation walking across it. It's a *viewer*: the simulation runs offline in Python
(the rest of this repo) and Godot draws the world + the agents moving through it.

## What's in the scene

Two scenes render the same campus — the academic core block (34th–36th ×
Spruce–Walnut), built from OpenStreetMap data by the repo's geo tool
(`tools/geo/osm_to_tiled.py`) and drawn with **Kenney's RPG Urban Pack (CC0)**:

- **`scenes/campus_urban.tscn`** — the campus on its own (the **default** scene):
  brick buildings, asphalt streets, tan paving for Locust Walk, green lawns. Pan and
  zoom to explore it.
- **`scenes/penn_replay.tscn`** — the same campus with a **generative-agents
  simulation** playing on top: a few Penn personas walking between real buildings on
  their daily schedules (see *Watching the Penn agent simulation* below).

Both share a generic map renderer (`scripts/tiled_map.gd`) and a pan/zoom camera
(`scripts/camera_controls.gd`).

## How it works

**`tiled_map.gd`** (the `Map` node in both scenes). A *generic* renderer for any Tiled
map whose tileset is one packed image: it reads the `.tmj`, loads the referenced
sheet, registers every tile, and paints each layer by GID. We use it to show the
campus drawn with **real art** — `maps/upenn_core_urban.tmj`, baked with **Kenney's
RPG Urban Pack (CC0)** by the geo tool (`--theme urban`): brick buildings, asphalt
streets, tan paving for Locust Walk, green for the lawns. The geo tool rotates the map
so Penn's streets run **straight along the X/Y axes** (the real grid is ~8.6° off
north) instead of on a slant, and the renderer uses nearest filtering + tile padding
so there are **no seams** between tiles. This is the no-plugin equivalent of importing
that `.tmj` with the [YATI](https://github.com/Kiamo2/YATI) addon, and the same file
also loads natively in Phaser. (`maps/tilemap_packed.png` is the CC0 sheet it
references.)

`scripts/penn_replay.gd` drives the agent replay on top of that map — see *Watching
the Penn agent simulation* below.

### Regenerating / swapping the campus map

`maps/upenn_core_urban.tmj` is a **copy** of the geo tool's output. To refresh it, or
to render the full campus instead of the 34th–38th × Spruce–Walnut core subset:

```bash
uv run python tools/geo/osm_to_tiled.py --area core --theme urban   # Kenney CC0 map + sheet
cp tools/geo/out/upenn_core_urban.tmj  godot-generative-agents/maps/
cp tools/geo/out/tilemap_packed.png    godot-generative-agents/maps/

# Post-processes that the committed map bakes in (re-run after a fresh bake, in
# this order — both edit maps/upenn_core_urban.tmj in place and are re-run safe):
uv run python tools/geo/wall_all_buildings.py                        # brick wall every building
uv run python tools/geo/furnish_building.py --sector "Williams Hall" # open the roof + furnish
```

The committed `maps/upenn_core_urban.tmj` already includes those two post-processes
(brick-walled buildings + the furnished Williams Hall cutaway), so the demo renders
them out of the box. The wall colour is chosen automatically from each building's roof
tint; to hand-match a specific building, run `wall_building.py --sector "<name>"` with
the colour you want before `wall_all_buildings.py` (it leaves already-styled buildings
alone). Both post-processes need the map grid to match the sim matrix 1:1 (239×273).

`scripts/snapshot.gd` / `scenes/snapshot.tscn` are a small dev utility: run that scene
(optionally with `-- <scene.tscn> <out.png>`) to save a screenshot of a map, used to
verify the render.

## Running it

Open the project folder in the Godot 4.6 editor and press **Play** (F5), or from a
terminal:

```bash
# The campus in real Kenney CC0 urban art (the default scene):
/Applications/Godot.app/Contents/MacOS/Godot --path .

# Watch the agent simulation replay on the campus:
/Applications/Godot.app/Contents/MacOS/Godot --path . res://scenes/penn_replay.tscn

# Headless smoke test — load every scene and check its map painted (exit 0 = OK):
./run_smoke_test.sh
```

`run_smoke_test.sh` loads each content scene headless and fails (non-zero exit) if a
scene can't load or its campus map painted zero cells — so a broken `.tmj` / tileset
regen is caught in CI or before you push, instead of silently rendering an empty
world. It needs no GPU (it reads the tilemap's cell data, not pixels). `uv run pytest
tests/test_godot_smoke.py` runs the same check and skips cleanly when Godot isn't
installed.

The first run regenerates the `.godot/` import cache (git-ignored); the committed
`*.import` / `*.uid` sidecars let Godot recognize the assets without re-importing
everything.

## Watching the Penn agent simulation

`scenes/penn_replay.tscn` plays a **generative-agents simulation on the real
campus**: a few Penn personas (a student, a professor, an architecture grad)
walking between real buildings on their daily schedules. Godot is just the
*viewer* — the simulation runs offline in Python and writes a replay file the
scene reads (the same split as the upstream Phaser replay):

```bash
# 1. Run the sim -> maps/penn_replay.json (from the repo root, so uv finds the env):
uv run python godot-generative-agents/sim/generate_penn_replay.py --steps 400

# 2. Watch it:
/Applications/Godot.app/Contents/MacOS/Godot --path . res://scenes/penn_replay.tscn
```

The Penn world lives in [`sim/`](sim/): `world_data_upenn.yaml` (the cast — 3
active personas while the live-LLM MVP keeps runs cheap; 4 more are parked in
comments, ready to uncomment) and
`the_upenn/` (the OSM-derived navigation grid from `tools/geo/osm_to_ville.py`).
The agent *engine* (deciding, pathfinding) is reused from the `backend` package,
so this is the same simulation that runs there — just rendered here instead of in
Phaser. `scripts/penn_replay.gd` eases each persona tile-to-tile along the path the
sim chose, with a name + activity label above each sprite. (`sim/` carries a
`.gdignore` so Godot leaves the Python alone.)

### Live mode — follow a running sim (issue #263)

The same scene can **follow a live simulation over real HTTP + WebSocket**
instead of loading a baked file. `sim/serve_penn.py` steps the *same* configured
Penn world (`sim/penn_world.py`, shared with the bake so the two can't drift —
issue #297) inside the backend's self-stepping live loop (#349/#262), and the
viewer becomes a thin client of `backend/api.py`:

```bash
# 1. Serve the live Penn sim (mock brain: real requests, zero keys, zero spend).
#    From the repo root; needs the server extra (uv sync --extra server):
uv run python godot-generative-agents/sim/serve_penn.py --tick-seconds 0.1

# 2. Point the viewer at it (the same switch the run monitor uses):
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run_replay.sh
```

On boot the viewer does one `GET /live` handshake (world meta → spawn the cast),
one `GET /events?since=0` backfill (history so far → jump to the live head),
then opens a WebSocket to `/ws` and applies each pushed frame as it lands —
bubbles, conversation links, trails, minimap, heatmap and fog all work
unchanged, because live frames use the exact replay schema. A red **LIVE**
badge joins the clock and the timeline locks into a read-only progress bar
(you can't seek a live stream); the Pause button stays a *local* view-pause,
while the run monitor's Emergency stop is what actually pauses the backend.

The mock brain never speaks, so `serve_penn.py` also ports the bake's scripted
`meetings:` injector to run on the fly: a meeting's authored dialogue fires the
moment every participant is genuinely settled at its venue within perception
range — watch Diego showing Sofia around the Kamin Gallery partway into the
default run.

If the backend disappears the viewer holds the last pose, shows
"reconnecting…", and retries with backoff; on reconnect the socket re-attaches
with `?since=<last cursor>`, so no frame is lost or applied twice. `POST
/reset` on the server starts a fresh day (reload the viewer to re-handshake).

### Real-LLM live mode — Claude Haiku drives the cast (issue #261)

`--brain llm` swaps the deterministic mock for the model declared in the
simulation config (`sim/world_data_upenn.yaml`, the `llm:` block): **Anthropic
Claude Haiku (`claude-haiku-4-5`) on every model call** — each agent's
travel/perform decisions, every line of dialogue when the routing brings two
agents within perception range (the scripted `meetings:` dialogue stands down;
what you see is the model's own words), and the periodic reflection passes.
The daily itinerary stays on the authored schedules for now (a Penn-aware LLM
planner is follow-up work).

```bash
# One-time: the llm extra alongside server (installs the anthropic SDK):
uv sync --extra server --extra llm

# Serve with the real brain (terminal 1)…
export ANTHROPIC_API_KEY=sk-ant-...   # or: cp .env.example .env and fill it in —
                                      # every backend CLI loads the repo-root .env
uv run python godot-generative-agents/sim/serve_penn.py --brain llm

# …and watch it live (terminal 2), exactly as before:
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run_replay.sh
```

Key hygiene: only `ANTHROPIC_API_KEY` is ever read — never `LLM_PROVIDER` /
`LLM_API_KEY` / `OPENAI_API_KEY` — and the server refuses to start without it
(or with a non-Anthropic `provider:` in the config) rather than serving a day
of silently failing calls.

**The Start/Stop button.** Under `--brain llm` the loop boots **paused**: the
server is up and the viewer connects, but not a single model call is made
until you press **▶ Start simulation** in the left sidebar (it sends
`POST /resume`; `curl -X POST http://127.0.0.1:8080/resume` works too). Once
running, the same button reads **⏹ Stop simulation** (`POST /pause` — the same
control the run monitor's Emergency stop drives) and **▶ Resume** after a
stop, always reflecting the backend's actual state. The free mock brain keeps
auto-starting; `--start-paused` / `--no-start-paused` overrides either mode.

**Closing the viewer stops the backend.** In live mode the window close sends
`POST /shutdown` before quitting, so the sim — and its spend — never keeps
running with nobody watching (`serve_penn` opts into the endpoint; the
`shutdown_backend_on_exit` export on the scene turns the behavior off if you
want a backend that outlives the window).

Every request is printed to the server terminal as it happens (the **LLM
request monitor**, `backend/llm_monitor.py`; `--no-monitor` silences it):

```
 LLM calls -- one line per model request (#, time, role, actor, sim turn, model, tokens in (cache w/r), tokens out, latency, $ this call, Σ $ run):
 #    7 12:05:02  decide    Diego Torres        t  118  claude-haiku-4-5  in   1088 ( 912w/    0r)  out  102    731ms  $0.001238  Σ $0.021410
 #    8 12:09:44  converse  Sofia Ramirez       t  119  claude-haiku-4-5  in   1322 (   0w/ 1002r)  out   64    598ms  $0.000740  Σ $0.041007
```

**Cost & safety.** A full 3-agent 1200-step day is ≈ 55–60 Haiku calls ≈
**$0.10** (the per-call-site arithmetic is in
[`../docs/design/agent-llm-interface.md`](../docs/design/agent-llm-interface.md),
along with the exact tool schemas and prompts the model gets). The config's
`max_cost_usd` (default $5) is a hard kill-switch: the moment cumulative spend
reaches it the day ends — the live loop pauses and the run monitor's budget
row shows **TRIPPED**. Two operational notes: ticks run serially, so each
decision stretches its tick to the model's latency (the viewer just paces
slower; `--tick-seconds` still sets the floor), and a provider outage never
crashes the day — a failed call leaves that agent idle for one tick and it
simply asks again, but failed calls record no cost, so a stalled tokens/min
meter in the run monitor (not the budget row) is the outage signal.

### The run monitor (top-right)

A live real-LLM run spends money every step and can stall on the provider, so the
viewer carries a small **run monitor** (`scripts/live_hud.gd`): a token/cost meter,
backend health, and a one-click **Emergency stop**. The `-`/`+` button in its header
collapses it to just the title bar (the health dot stays visible); the meter keeps
counting underneath. Its data feed is pluggable (`scripts/hud_source.gd`):

- **Baked replay (the default):** no backend exists, so the monitor shows clearly
  labeled **simulated** usage that accrues while the replay plays
  (`scripts/hud_source_replay.gd`) — realistic numbers, zero dollars at risk. The
  stop button freezes playback and trips a mock budget gate; Play lifts it.
- **Live mode:** point the scene at a running backend (`backend/api.py`) by setting
  the `live_backend_url` export — or just `SIM_API_URL=http://127.0.0.1:8000` in the
  environment, no editor needed — and the same monitor polls the real `GET /usage` +
  `GET /health` and drives `POST /pause` (`scripts/hud_source_live.gd`), sending
  `SIM_API_TOKEN` as a bearer token when set.

Both feeds emit the engine's `UsageLedger.summary()` shape (what `GET /usage`
serves), which is what makes the mock → real-LLM switch a pure configuration change.

## Where this fits — the full-port proposals

This is a **mock**: a standalone proof that the Godot-native tilemap + sprite path works.
Two design docs in the repo sketch the road from here to a fully-wired Godot frontend:

- [`../docs/design/custom-world-authoring.md`](../docs/design/custom-world-authoring.md) —
  authoring our own world + sprites (map layers, semantic maze CSVs, personas, licensing).
- [`../generative-agents/NEXT-STEPS.md`](../generative-agents/NEXT-STEPS.md) (bottom section,
  "porting the replay frontend to Godot") — turning the file-based replay export into a Godot
  4 renderer.

## Assets & license

- **Campus tiles** — Kenney's [RPG Urban Pack](https://kenney.nl) (CC0, public
  domain), baked into `maps/tilemap_packed.png` by the geo tool. Interior cutaway art
  is credited separately in `maps/INTERIOR_CREDITS.md`.
- **Agent sprites** — the **Cute Fantasy (Free)** pack by Kenmi, kept under
  `Cute_Fantasy_Free/` with its original `read_me.txt`. Per that license it is **free
  for non-commercial use and may be modified, but not redistributed or resold**. It
  lives here only for this private research repo.
