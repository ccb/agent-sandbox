# godot-generative-agents

A tiny [Godot 4.6](https://godotengine.org) sandbox that renders the **real
University of Pennsylvania campus** in Godot and plays back a generative-agents
simulation walking across it. It's a *viewer*: the simulation runs offline in Python
(the rest of this repo) and Godot draws the world + the agents moving through it.

## Project layout

Three parts sit side by side here. You run the game and choose replay-vs-live from
the **in-game menu** — there's no separate "replay" vs "live" launch script anymore:

- **`godot/`** — the Godot 4.6 game and the `res://` project root. Open *this* folder
  in the editor (or run `./run.sh`). Holds the scenes, scripts, art, and campus maps.
- **`backend/`** — the Python simulation engine + headless HTTP API (imported as the
  top-level `backend` package). The Penn world lives under **`backend/penn/`**: the
  cast (`world_data_upenn.yaml`), the OSM-derived navigation grid (`the_upenn/`), and
  the replay/live entry points (`generate_penn_replay.py`, `serve_penn.py`).
- **`web/`** — a React/Vite shell that wraps a WebAssembly export of the game.

Paths below are relative to the Godot project (`godot/`) unless noted.

## What's in the scene

The game opens on a **landing menu** — the front door where you pick how to enter
the viewer (a replay, a local replay file, or a live backend). Behind it, two scenes
render the same campus — the academic core block (34th–36th × Spruce–Walnut), built
from OpenStreetMap data by the repo's geo tool (`godot-generative-agents/tools/geo/osm_to_tiled.py`) and
drawn with **Kenney's RPG Urban Pack (CC0)**:

- **`scenes/main_menu.tscn`** — the **front door** (the default scene): choose *Watch
  a replay* (the bundled one or a local `.json` you point it at) or *Run a live
  simulation* (connect to a running backend), and it hands off to the viewer. Its
  backdrop is the campus itself, rendered live behind the menu.
- **`scenes/campus_urban.tscn`** — the campus on its own: brick buildings, asphalt
  streets, tan paving for Locust Walk, green lawns. Pan and zoom to explore it.
- **`scenes/viewer.tscn`** — the same campus with a **generative-agents
  simulation** playing on top: a few Penn personas walking between real buildings on
  their daily schedules (see *Watching the Penn agent simulation* below). The
  sidebar's 🏠 button returns to the menu.

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

`scripts/viewer.gd` drives the agent replay on top of that map — see *Watching
the Penn agent simulation* below.

### Regenerating / swapping the campus map

`maps/upenn_core_urban.tmj` is a **copy** of the geo tool's output. To refresh it, or
to render the full campus instead of the 34th–38th × Spruce–Walnut core subset:

```bash
uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --area core --theme urban   # Kenney CC0 map + sheet
cp godot-generative-agents/tools/geo/out/upenn_core_urban.tmj  godot-generative-agents/godot/maps/
cp godot-generative-agents/tools/geo/out/tilemap_packed.png    godot-generative-agents/godot/maps/

# Post-processes that the committed map bakes in (re-run after a fresh bake, in
# this order — both edit maps/upenn_core_urban.tmj in place and are re-run safe):
uv run python godot-generative-agents/tools/geo/wall_all_buildings.py                        # brick wall every building
uv run python godot-generative-agents/tools/geo/furnish_building.py --sector "Williams Hall" # open the roof + furnish
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

Open the **`godot/`** folder in the Godot 4.6 editor and press **Play** (F5), or from
a terminal (these commands assume you're in this `godot-generative-agents/` folder):

```bash
# Launch the game — opens the landing menu, where you pick a replay or a live backend:
./run.sh

# The same thing by hand (godot/ is the res:// project root, not this folder):
/Applications/Godot.app/Contents/MacOS/Godot --path godot

# Skip the menu and jump straight to a scene (deep links, unaffected by the menu):
/Applications/Godot.app/Contents/MacOS/Godot --path godot res://scenes/campus_urban.tscn
/Applications/Godot.app/Contents/MacOS/Godot --path godot res://scenes/viewer.tscn

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

`scenes/viewer.tscn` plays a **generative-agents simulation on the real
campus**: a few Penn personas (a student, a professor, an architecture grad)
walking between real buildings on their daily schedules. Godot is just the
*viewer* — the simulation runs offline in Python and writes a replay file the
scene reads (the same split as the upstream Phaser replay):

```bash
# 1. Run the sim -> maps/penn_replay.json (from the repo root, so uv finds the env).
#    The bake also saves the run to the shared store by default (#752): every entry
#    point (viewer / this script / web companion) default-saves into
#    godot-generative-agents/runs/, so a bake shows up in Past runs and is re-runnable.
#    Add --no-persist for a throwaway bake (replay file only, no store row):
uv run python godot-generative-agents/backend/penn/generate_penn_replay.py

# 2. Watch it:
/Applications/Godot.app/Contents/MacOS/Godot --path . res://scenes/viewer.tscn
```

**Boil-water demo (#592).** For a short, self-contained view of the
drink → sicken → boil → recover arc (#300) — instead of scrubbing to the tail of a
long full-cast bake — pass `--scenario boil`. It bakes a one-persona replay
(`maps/penn_replay_boil.json`) where the three events land early and spread across
the timeline; the landing menu then shows a **"Play the boil-water demo"** button
(it self-hides until this file exists). The full cast / bundled replay is untouched.

```bash
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --scenario boil
```

The Penn world lives in [`backend/penn/`](backend/penn/): `world_data_upenn.yaml`
(the world: locations, the `llm:` block, and a `cast: [diego, tanaka, sofia]` list
resolved from the `personas/` library — 7 personas total, 3 in the default cast
while the live-LLM MVP keeps runs cheap; see `backend/penn/personas/README.md`)
and `the_upenn/` (the OSM-derived navigation
grid from `godot-generative-agents/tools/geo/osm_to_ville.py`). The agent *engine* (deciding, pathfinding) is
the surrounding `backend` package, so this is the same simulation that runs there —
just rendered here instead of in Phaser. `scripts/viewer.gd` eases each persona
tile-to-tile along the path the sim chose, with a name + activity label above each
sprite. (`backend/` sits beside the Godot project, not inside it, so Godot never
touches the Python.)

Two pop-ups let you interrogate the run at any point while it plays: the
**movement heatmap** (`H`, or the sidebar's flame button) shows *where* everyone
has spent their time so far, and the **social graph** (`G`, or the three-linked-nodes
button; issue #252) shows *who has talked to whom* so far — edges thicken with more
and more-recent conversations, and `←`/`→` flips to the authored t=0 **seed
relationships** (the `relationships:` blocks in `backend/penn/personas/*.yaml`) so you can
compare who *started out* knowing whom against who actually met during the day.

You can also **snapshot the campus** as it plays (issue #253): the sidebar's camera
button (or `C`) grabs the current view — UI chrome hidden, so it's the bare
campus + agents — and stamps it with the world time. The stacked-photos button opens
a **gallery** of every snapshot taken this session, each captioned with its timestamp;
click one to enlarge it (`←`/`→` to browse, `Esc` to close). Snapshots live in memory
for the session — saving them to disk is a separate follow-up.

**Analyzing a saved run offline.** `tools/analyze_run.py` (promoted from a
batch-2 scratch script, #795) summarises one `runs/<id>/` directory: verbs,
`talk_to` share, conversations, and co-settled pair-steps (two agents settled
in the same room, with a per-pair breakdown):

```bash
uv run python godot-generative-agents/tools/analyze_run.py <run-id>
uv run python godot-generative-agents/tools/analyze_run.py <run-id> --json
uv run python godot-generative-agents/tools/analyze_run.py --self-check
```

Co-settled prefers the count `run.yaml`'s `result:` block already carries
(the backend's own tally) and only falls back to approximating it from
`frames.jsonl` for runs saved before that counter existed — frames alone
can't tell settled from merely-idle, so the fallback can over-report. Either
way the output states which source it used. Like the sibling
`most_common_actions.py` / `most_wanted_actions.py`, it's stdlib-only and
reads a run without importing the engine, so it stays runnable against an
archived run long after the code that wrote it has moved on.

### Live mode — follow a running sim (issue #263)

The same scene can **follow a live simulation over real HTTP + WebSocket**
instead of loading a baked file. `backend/penn/serve_penn.py` steps the *same* configured
Penn world (`backend/penn/penn_world.py`, shared with the bake so the two can't drift —
issue #297) inside the backend's self-stepping live loop (#349/#262), and the
viewer becomes a thin client of `backend/api.py`:

```bash
# 1. Serve the live Penn sim (mock brain: real requests, zero keys, zero spend).
#    From the repo root; needs the server extra (uv sync --extra server):
uv run python godot-generative-agents/backend/penn/serve_penn.py --tick-seconds 0.1

# 2. Point the viewer at it (the same switch the run monitor uses):
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```

`--scenario` picks which world the live loop steps, using the bake's scenario
names: `penn` (default, the full campus cast), `boil` (the #592 demo above), or
`boil_hard` (#728 — the boil demo with the stove relocated to a separate Sweeten
`Kitchen` and the perception radius pinned to 0, so finding it takes actually
traveling there; the matching experiment harness is
`backend/penn/experiments/boil_hard_connect_dots.py`).

Or skip the env var entirely: launch the viewer normally so it opens the landing
menu, type the backend's URL (and its token, if the server sets `SIM_API_TOKEN`)
into **Run a live simulation**, and press **Connect**. The menu probes `GET /live`
first, so a wrong URL or a backend with no live loop is reported right there instead
of the viewer silently retrying. (`SIM_API_URL` / `SIM_API_TOKEN`, when set, prefill
that form.)

On boot the viewer does one `GET /live` handshake (world meta → spawn the cast),
one `GET /events?since=0` backfill (history so far → jump to the live head),
then opens a WebSocket to `/ws` and applies each pushed frame as it lands —
bubbles, conversation links, trails, minimap, heatmap, social graph and fog all
work unchanged, because live frames use the exact replay schema. A red **LIVE**
badge joins the clock and the timeline locks into a read-only progress bar
(you can't seek a live stream); the Pause button stays a *local* view-pause,
while the run monitor's Emergency stop is what actually pauses the backend.

The mock brain never speaks, so `serve_penn.py` also ports the bake's scripted
`meetings:` injector to run on the fly: a meeting's authored dialogue fires the
moment every participant is genuinely settled at its venue within perception
range — watch Diego showing Sofia around the Kamin Gallery partway into the
default run.

**`--brain scripted`** — a deterministic, key-free brain that drives the *full*
backend offline: the per-verb tool loop, cognition tools, conversation, and
reflection all run (unlike `--brain mock`, which stays on the schedule driver and
never reaches them). No `ANTHROPIC_API_KEY`, no spend. Use it to exercise or test
the live-brain code paths without a provider. Works for both `serve_penn.py` and
`generate_penn_replay.py`. (Issue #563.)

If the backend disappears the viewer holds the last pose, shows
"reconnecting…", and retries with backoff; on reconnect the socket re-attaches
with `?since=<last cursor>`, so no frame is lost or applied twice. `POST
/reset` on the server starts a fresh day (reload the viewer to re-handshake).

### Real-LLM live mode — Claude Haiku drives the cast (issue #261)

`--brain llm` swaps the deterministic mock for the model declared in the
simulation config (`backend/penn/world_data_upenn.yaml`, the `llm:` block): **Anthropic
Claude Haiku (`claude-haiku-4-5`) on every model call** — each agent's
travel/perform decisions, every line of dialogue when the routing brings two
agents within perception range (the scripted `meetings:` dialogue stands down;
what you see is the model's own words), and the periodic reflection passes.
The daily itinerary is the model's too: since #787 `--plan` defaults to `auto`,
which under a paying brain means `LLMPlanner` (#397) authors each agent's day
at attach — so the plan is something the agent can also *revise* when the day
turns, which the authored schedule never could. Pass `--plan schedule` to force
the hand-authored days back; their stop windows are tuned so agents converge for
the scripted rendezvous, which a free-play generated day does not guarantee.
The mock and scripted brains are unaffected (no client to plan with), so the
bundled bake and every offline replay stay byte-identical.

```bash
# One-time: the llm extra alongside server (installs the anthropic SDK):
uv sync --extra server --extra llm

# Serve with the real brain (terminal 1)…
export ANTHROPIC_API_KEY=sk-ant-...   # or: cp .env.example .env and fill it in —
                                      # every backend CLI loads the repo-root .env
uv run python godot-generative-agents/backend/penn/serve_penn.py --brain llm

# …and watch it live (terminal 2), exactly as before:
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```

Key hygiene: only `ANTHROPIC_API_KEY` is ever read — never `LLM_PROVIDER` /
`LLM_API_KEY` / `OPENAI_API_KEY` — and the server refuses to start without it
(or with a non-Anthropic `provider:` in the config) rather than serving a day
of silently failing calls. The key is also **verified at boot** with one free
models-list request: an *invalid* key (typo, placeholder, revoked) aborts with
a one-line fix instead of what it used to produce — a sim that ticks normally
while every agent sits frozen on "waking up" at $0 spend, because a rejected
call degrades to an idle-and-retry tick by design and never reaches the
budget ledger. (Network trouble during the check only warns; the run's own
retry path handles transient failures.)

#### Model tiering (#368)

Every LLM call is stamped with its call-site role — `decide`, `plan`,
`reflect`, `converse`, `outcome`, `score`, `react` — and by default one model
(the `llm:` block's `model`) serves them all. To route a role to a different
model, add a `models:` map to the world YAML's `llm:` block, or override per
run:

    uv run python godot-generative-agents/backend/penn/serve_penn.py \
        --brain llm --plan llm \
        --model-for plan=claude-sonnet-4-6 --model-for reflect=claude-sonnet-4-6

Recommended tiering: a stronger model for the low-volume reasoning sites
(`plan`, `reflect`, `outcome`) and the cheap default for the high-volume ones
(`decide`, `converse`, `score`, `react`). Per-role spend is visible in
`GET /usage` (`by_role`) and in each run log's summary line; the
`LLM_MAX_COST`-style budget ceiling (`max_cost_usd`) stays global across
tiers.

#### Tuning the live sim: `--config` (#564)

Every sim knob lives in one declarative `SimulationConfig` file
(`backend/sim_config.py`; see `docs/design/simulation-config.md`) — pass it to
the live server instead of growing per-knob flags:

```yaml
# sim.yaml — every omitted field keeps today's default
retrieval:            # memory-retrieval scoring at each decide
  alpha_recency: 3.0  # recency-heavy: recent memories dominate
  max_records: 2
cognition:
  vision_r: 4         # perception radius, in tiles
game:
  agent:
    temperature: 0.0  # deterministic decides under --brain llm
```

    uv run python godot-generative-agents/backend/penn/serve_penn.py \
        --brain llm --config sim.yaml

The `retrieval:` weights change which memories surface at every decide (watch
`role: decide` requests in the monitor, or the agent card's retrieved
memories); `game.agent.temperature: 0.0` makes decisions deterministic;
`reflection_threshold` rides along for when a reflector is wired. The
batch-runner sections (`simulation:`, `embedding:`) are ignored on the live
path, existing flags keep working (`--cognition-tools` / `--react` force their
feature on over the file), and the config is recorded in the run's manifest so
`--re-run` reproduces it. Without `--config`, behavior is byte-identical to
before.

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

**Going back to the menu does not.** The sidebar's 🏠 button returns to the
landing page *without* shutting the backend down — it's for re-picking what to
watch, not for ending the run. The menu prefills the URL you just left, so
**Connect** reattaches to the same sim (the socket resumes with `?since=` and
loses no frames). Use the window close, the run monitor's Emergency stop, or
`POST /shutdown` when you actually want the sim to stop.

**Boil-from-memory experiment (#595).** `uv run python -m backend.penn.experiments.boil_from_memory --trials 5` (from `godot-generative-agents/`, needs `ANTHROPIC_API_KEY`) runs a live Haiku brain on the single-persona boil world with vs without a seeded "the unboiled water made me sick" memory, and prints the boil-before-drink rate for each arm. Add `--offline` for a key-free plumbing check (scripted brain, not a real measurement).

Every request is printed to the server terminal as it happens (the **LLM
request monitor**, `backend/llm_monitor.py`; `--no-monitor` silences it):

```
 LLM calls -- one line per model request (#, time, role, actor, sim turn, model, tokens in (cache w/r), tokens out, latency, $ this call, Σ $ run):
 #    7 12:05:02  decide    Diego Torres        t  118  claude-haiku-4-5  in   1088 ( 912w/    0r)  out  102    731ms  $0.001238  Σ $0.021410
 #    8 12:09:44  converse  Sofia Ramirez       t  119  claude-haiku-4-5  in   1322 (   0w/ 1002r)  out   64    598ms  $0.000740  Σ $0.041007
```

The same rows appear inside the viewer: the run monitor's **LLM requests** box
(under the usage meter) logs each call as it happens —
`12:09:44 converse Ramirez 1.3k→64 $0.0007`, newest at the bottom, hover a row
for the full detail (sim turn, model, cache split, latency, cumulative spend).
The rows ride the live event feed (`serve_penn`'s `drain_events()` publishes
the monitor's records as `llm_call` events), so the box needs no extra
polling — and `--no-monitor` silences it together with the terminal.
Engine `GameEvent`s (e.g. the boil-water `sickness` event) ride the same feed
as `game_event` records (#467); the HUD's generic rows currently render only
`text`-bearing records, so surfacing these on-screen is #302/#264 follow-up.

**Cost & safety.** A full 3-agent 1200-step day is ≈ 55–60 Haiku calls ≈
**$0.10** (the per-call-site arithmetic is in
[`../docs/design/agent-llm-interface.md`](../docs/design/agent-llm-interface.md),
along with the exact tool schemas and prompts the model gets). The config's
`max_cost_usd` (default $5) is a hard kill-switch: the moment cumulative spend
reaches it the day ends — the live loop pauses and the run monitor's budget
row shows **TRIPPED**. Two operational notes on latency (#366): under
`--brain llm` the agents at a decision point decide **concurrently** (one
worker per persona by default; `--decide-workers N` caps how many model calls
run at once — tune it under your provider's rate limit — and `0` restores the
strictly serial path), so a decision tick costs roughly the *slowest* decision rather
than the sum — and the loop's sleep subtracts each tick's wall time, so
walk-only ticks keep the `--tick-seconds` cadence while decision ticks start
the next tick immediately. A decision that outlives `--decide-timeout`
(default 30 s) leaves that agent idle for the tick — the skip is printed, the
in-flight call's usage still lands in the ledger, and its answer is applied at
the agent's next decision point once it resolves (never billed twice); a
provider outage degrades to the same idle-and-retry (failed calls record no
cost, so a stalled tokens/min meter in the run monitor — not the budget row —
is the outage signal). Every `frame` feed record carries `tick_ms` (+
`deciders`), so a client can tell "thinking" from "stuck" (the viewer-side
indicator is #372). To *feel* the
stalls without spending anything: `--mock-latency 5 --decide-workers 3` under
the mock brain. `deciding` — a per-agent decision lifecycle record
(`{agent, state: "begin"|"end", step, elapsed_ms?}`, #551), emitted under a
real/scripted brain; the viewer shows a per-agent "thinking" bubble from it
(and the global badge prefers it over stall-inference). The `begin` is
published the moment the decide starts — mid-tick, out-of-band (#605) — so
the bubble lights for the decide's whole duration even when it begins and
ends within one tick; the `end` follows at the tick boundary.

### The run monitor (top-right)

A live real-LLM run spends money every step and can stall on the provider, so the
viewer carries a small **run monitor** (`scripts/live_hud.gd`): a token/cost meter,
an **LLM requests** log (one timestamped line per model call — the in-viewer twin
of the terminal monitor above), backend health, and a one-click **Emergency stop**.
The `-`/`+` button in its header collapses it to just the title bar (the health dot
stays visible); the meter keeps counting underneath. Its data feed is pluggable
(`scripts/hud_source.gd`):

- **Baked replay (the default):** no backend exists, so the monitor shows clearly
  labeled **simulated** usage (and simulated request-log rows) that accrue while
  the replay plays (`scripts/hud_source_replay.gd`) — realistic numbers, zero
  dollars at risk. The stop button freezes playback and trips a mock budget gate;
  Play lifts it.
- **Live mode:** point the scene at a running backend (`backend/api.py`) by setting
  the `live_backend_url` export — or just `SIM_API_URL=http://127.0.0.1:8000` in the
  environment, no editor needed — and the same monitor polls the real `GET /usage` +
  `GET /health` and drives `POST /pause` (`scripts/hud_source_live.gd`), sending
  `SIM_API_TOKEN` as a bearer token when set; the request log fills from the event
  feed's `llm_call` records instead of the simulation.

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
