# Penn simulation, viewer, and web companion

This directory contains the Penn-specific application built on the shared
`text_adventure_games` engine.

```text
backend/     simulation loop, cognition, Penn world, API, run/replay tooling
godot/       Godot 4.6 native viewer
tools/geo/   map generation, furnishing, and TMJ↔matrix validation
web/         public React/Vite writeup and browser replay
runs/        minimal aggregate/case-study evidence (not a development RunStore)
```

## Free live workflow

One-time setup first: the viewer's licensed art packs are **not in the
repository** (their licenses forbid redistribution). `ASSETS.md` at the
repository root lists the three packs, where to get them, and the exact
drop-in paths — without them the viewer runs but the map renders gray.

From the repository root, install the backend and start it:

```bash
uv sync --extra server
uv run python godot-generative-agents/backend/penn/serve_penn.py \
  --brain mock --tick-seconds 0.1
```

In a second terminal, launch the viewer:

```bash
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```

The mock brain is deterministic, uses the real world/action/replay paths, needs
no key, and spends no money. The server listens on loopback by default. A
non-loopback bind requires `SIM_API_TOKEN` and bearer authentication.

`run.sh` locates Godot on `PATH` or in the standard macOS application location,
imports assets on a fresh clone, and opens the landing menu. Pass a scene path to
launch it directly.

## Baked replay

Generate the Penn replay without retaining a local run:

```bash
uv run python godot-generative-agents/backend/penn/generate_penn_replay.py \
  --no-persist
./godot-generative-agents/run.sh
```

The generated native-viewer file is ignored. The reviewed browser showcase
artifact lives at `web/public/replay/penn_replay.json`; regenerate it through
`web/scripts/gen-replay.sh` only when intentionally updating the publication.

## Paid live workflow

Copy the root `.env.example` to `.env`, set `ANTHROPIC_API_KEY`, and run with an
explicit step budget and cost ceiling:

```bash
uv sync --extra server --extra llm
uv run python godot-generative-agents/backend/penn/serve_penn.py \
  --brain llm --steps 360 --max-cost 1.00
```

Under `--brain llm` the loop boots **paused**, so nothing is spent until you
start the day. Launch the viewer in a second terminal exactly as in the free
workflow; the menu detects the paused backend and opens the **setup screen**,
where you pick the cast, adjust the run knobs (tick pacing, brain, planner,
thinking depth, model), and press **Start** — that posts the configuration and
resumes the loop. To rehearse the same screen without a key or a bill, add
`--start-paused` to the free mock command above; `--no-start-paused` skips it
and starts an llm run immediately.

The model recipe defaults come from `backend/penn/world_data_upenn.yaml` and may
be overridden by supported CLI/config options. Watch the terminal monitor. A
cost ceiling is a safety boundary, not a prediction; historical measurements
are documented in `runs/cost-scaling/README.md`.

## What's on by default

Not every faculty is always running, and the difference matters for reading run
costs. **Four things are unconditional:** the tick loop, perception, the memory
stream with its retrieval, and the precondition gate. They need no language
model at all — which is what lets the bundled replay bake and the test suite run
offline, for free, and still exercise real perception and real retrieval. **The
generative faculties are gated on a real provider:** conversation, reflection,
importance scoring, and model-written plans exist only when one is attached.
**The rest are knobs that default off:** the cognition tools (an opt-in pull
channel of recall/knowledge/plan tools), embedding-based relevance (unset means
keyword overlap), and reactive interruption, which lets a perception cut into an
activity mid-stop. Each is a field in the same configuration object as the
retrieval constants, so a run is described by its config rather than by a code
change.

The public showcase run enables most of them: a real provider with model
tiering — a larger model for the deliberative roles, a cheaper one for the
conversational ones — model-written plans, medium reasoning effort, cognition
tools on, keyword relevance, and a fixed seed. Reactive interruption is off, so
plans in that run change from falling behind, from a refused action, or from a
conversation — never from a perception interrupt.

## If something goes wrong

- **`Godot 4 not found.`** — `run.sh` probes `godot`, then `godot4`, then
  `/Applications/Godot.app/Contents/MacOS/Godot`. Install Godot 4.6 or put it on
  `PATH` under one of those names.
- **An import error naming the LLM extra** — `--brain llm` needs
  `uv sync --extra server --extra llm`. The server exits with that instruction
  rather than starting without a brain.
- **`--brain llm needs ANTHROPIC_API_KEY`** — export it in the serving terminal
  or put it in a repo-root `.env` (template: `.env.example`). An already-exported
  variable wins over `.env`, and no other key variable is consulted.
- **`ANTHROPIC_API_KEY was rejected by the API`** — the key is present but not
  valid. One free models-list request verifies it at boot, so a typo'd or revoked
  key stops the server here instead of leaving the cast frozen at $0 spend for a
  whole simulated day.
- **`Can't reach … — is the backend running?`** in the viewer's menu — start the
  server terminal first, and check `SIM_API_URL` matches its `--host`/`--port`
  (default `http://127.0.0.1:8080`).
- **The server dies with an address-in-use error** — something else owns 8080.
  Pass `--port` to the server and match it in `SIM_API_URL`.
- **The map renders gray, with errors naming `interior_franuka.png` or other
  sheets** — the licensed art packs are missing. `ASSETS.md` at the repository
  root has the packs and drop-in paths; `run.sh` re-imports on the next launch,
  and `run_smoke_test.sh` fails loudly if a sheet is still misplaced.
- **The setup screen refuses to Start** — the server rejected the configuration,
  and the message under the Start button names the offending field (for
  example, a planner, thinking depth, or model choice on a free brain). Adjust
  the knob and press Start again; nothing was applied.

## Penn world and extension points

- `backend/penn/world_data_upenn.yaml`: cast, schedules, relationships, meetings,
  and model defaults.
- `backend/penn/personas/`: reusable persona definitions.
- `backend/penn/penn_world.py`: the one shared world factory used by live and
  baked execution.
- `backend/penn/serve_penn.py`: live controls and the replay-compatible stepper.
- `backend/promptviz_chains/cognition.yaml`: static cognition-flow source used by
  the writeup.
- `godot/maps/upenn_core_urban.tmj`: authored visual map.
- `backend/penn/the_upenn/`: pathfinding matrix consumed by the simulation.

Forks can add a world builder to the scenario registry, but each shipped scenario
must provide its world data, tests, documentation, and replay contract together.

## Adding your own verb

The framework exists so that other people can build simulations on it, which
means adding to the world has to be cheap. A new verb is one class:

```python
from text_adventure_games.actions.base import Action


class MyVerb(Action):
    # What the parser matches on, and what the agent's tool is called.
    ACTION_NAME = "my_verb"
    # The one line the model sees when this verb appears in its menu.
    ACTION_DESCRIPTION = "what this verb does, in a short phrase"
    # Optional. Offer the verb only where the world affords it: some thing in
    # scope -- an item, or the room itself -- must carry this property.
    REQUIRED_AFFORDANCES = ("my_affordance",)

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        # Who is acting. Action's helpers match names against what this
        # character can actually see, so nothing off-screen can be referenced.
        self.character = self.acting_character(command, hint="who is acting")

    def check_preconditions(self) -> bool:
        # The gate. Return False and the world does not change. Whatever you
        # pass to parser.fail becomes a memory the agent can retry against,
        # so say why, specifically.
        if not self.has_affordance_in_scope(self.character, "Not possible here."):
            return False
        return True

    def apply_effects(self):
        # Runs only if the gate opened. Change state, then narrate it -- the
        # narration is what other characters can perceive.
        self.character.set_property("my_state", True)
        self.parser.ok(f"{self.character.name} does the thing.")
```

Pass it to the game as `custom_actions=[MyVerb]` and it becomes three things at
once: a command a human player can type, an option a scripted NPC can take, and
a typed tool in every agent's menu — offered only where the declared affordance
is in scope. That last one is the engine's default wiring; a simulation that
curates its own verb list, as the Penn cast does, names the verb there instead.
The full engine reference, generated from these same sources, lives in
`mkdocs/`.

## Map changes

The TMJ picture and backend matrix must remain synchronized. See
`tools/geo/README.md` for the authoring pipeline, then run:

```bash
uv run pytest godot-generative-agents/tools/geo/ -q
uv run python godot-generative-agents/tools/geo/validate_tmj.py
```

Asset credits beside the map are part of the distribution. Preserve them and
verify the license of every added tile, sprite, font, and dataset.

## Validation

```bash
uv run pytest godot-generative-agents/tests/ -q
./godot-generative-agents/run_smoke_test.sh

cd godot-generative-agents/web
pnpm install --frozen-lockfile
pnpm lint && pnpm test && pnpm build
```

The smoke test imports the Godot project, runs its GDScript tests, and loads the
important scenes headlessly. Run it after viewer, map, asset, or replay changes.
