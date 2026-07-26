# SimulationConfig Design

**Status:** **Implemented** for the landed sections (Phase A + B) in
`backend/sim_config.py`. `SimulationConfig` is the
generative-agents counterpart to the engine's [`GameConfig`](../configuration.md):
it **composes** a `GameConfig` and adds the sim's run-time and memory-retrieval
knobs. Sections for later phases — perception (Phase C), planning (Phase D), and
per-persona cognition overrides — are **deferred**: those phases aren't built, so a
config field for them would be dead config. They land with their phase. This doc
doubles as the variable registry; each row is tagged **implemented** or
**deferred**.

*A single, global configuration object for the Smallville generative-agents
simulation — gathering the run-time knobs (start time, steps, seconds-per-step) and
the memory-retrieval knobs (recency × relevance × importance weights, decay, how
many memories to surface) that used to live scattered across CLI flags and engine
constants — into one place you build once (in Python, from a YAML/JSON file, or
from the environment) and hand to the simulation runner.*

---

## 1. Why a SimulationConfig

The engine already has [`GameConfig`](../configuration.md): one object that gathers
the library's tuning knobs (LLM, agent, engine loop, clock, render, observability)
so a game author sets them in one place instead of editing library source. The
generative-agents port needs the *same idea* for its own knobs, which used to be
scattered:

- **Run-time knobs** were CLI-only flags on `backend/run_simulation.py` (`--start`,
  `--steps`, `--sec-per-step`, `--sim-code`, `--base-sim`; #74). A scenario couldn't
  ship them in a file.
- **Memory-retrieval knobs** were *not configurable at all*: the recency / relevance
  / importance weights, decay, and limits lived as module constants in
  `text_adventure_games/memory.py`, with the sim always calling `retrieve()` at its
  defaults.
- **Engine knobs** are already covered by `GameConfig` (turn mode, clock, LLM,
  observability) and are *reused, not duplicated*.

`SimulationConfig` consolidates these. As with `GameConfig`, **every field defaults
to today's behavior**, so an empty `SimulationConfig()` (or passing none) changes
nothing.

## 2. Relationship to `GameConfig`

`SimulationConfig` **composes** `GameConfig`, it does not fork it. The engine-level
knobs stay in `GameConfig` (reachable under the `game:` section) and keep working
for every project on the engine; `SimulationConfig` *embeds* one and *adds* the
sim's sections:

```
SimulationConfig                      # backend/sim_config.py
├── game: GameConfig                  # the engine config, reused as-is (game: section)
│   └── llm / agent / engine / clock / render / observability
├── simulation: SimulationRuntimeConfig   # start, steps, sec_per_step, seed (frontend-agnostic)
├── retrieval: RetrievalConfig            # recency × relevance × importance scoring
├── cognition: CognitionConfig            # perception radius + conversation pacing
├── smallville: SmallvilleConfig          # Smallville/Phaser-only: sim_code, base_sim, num_agents
└── embedding: EmbeddingConfig | None     # relevance backend; None = keyword overlap
```

Most sections are **frontend-agnostic** — they tune the shared agent engine, so they
apply whether the sim drives the Smallville/Phaser replay or the UPenn/Godot campus
replay. A few knobs only one frontend reads live in their **own sub-section** so the
shared sections stay clean: `smallville` holds the `the_ville`-specific run-directory
knobs that only `run_simulation` reads (§3.4). There is **no `upenn` section yet** — the
UPenn/Godot runners don't read `SimulationConfig` at all today, and per the "no dead
config" rule (§1) a section appears only once a runner actually reads it.

Construction mirrors `GameConfig`: `SimulationConfig()` (all defaults),
`.from_file(path)` (YAML/JSON), `.from_dict(data)`, `.from_env()`, `.to_dict()`,
plus `.build_embedding_client()` and `.build_llm_client()` conveniences.

The two tiny helpers `_build` (reject unknown keys) and `_asdict` are **duplicated
locally** in `sim_config.py` rather than imported from the engine's private
`config` module — the port reuses the engine's *public* API only.

---

## 3. Variable registry

### 3.1 `simulation` — run-time (`SimulationRuntimeConfig`) — **implemented**

How long the sim runs and how its clock maps to in-game time. **Frontend-agnostic** —
any world (the_ville or the_upenn) honors these. They mirror `run_simulation`'s CLI
flags (#74); the config gives them a declarative home. An explicit CLI flag still wins
(see §4). The `the_ville`-only run-directory knobs (`sim_code` / `base_sim` /
`num_agents`) used to live here too but moved to the `smallville` section (§3.4).

| Field | Type | Default | Meaning | Status |
|---|---|---|---|---|
| `start` | ISO datetime str | `2023-02-13 08:00:00` | Sim start timestamp; parsed by the runner. `--start`. | implemented |
| `steps` | int | `1080` | Steps to simulate (1080 × 10s = 3 hours). `--steps`. | implemented |
| `sec_per_step` | int | `10` | In-game seconds advanced per step. `--sec-per-step`. | implemented |
| `seed` | int \| None | `None` | Global RNG seed for reproducible runs. Carried for forward use; **not yet consumed** (pairs with future record/replay — [llm-cost-observability.md](llm-cost-observability.md) piece 4). | implemented (inert) |

`ville_dir` / `storage` are intentionally **not** in the config — they're
machine-layout paths, not portable scenario parameters, so they stay CLI-only flags
(the same reasoning a `GameConfig` doesn't carry filesystem paths).

### 3.2 `retrieval` — recency × relevance × importance (`RetrievalConfig`) — **implemented**

Which memories get pulled into an observation before the agent decides. Every field
maps 1:1 onto a parameter of
[`AgentMemory.retrieve()`](../../text_adventure_games/memory.py); defaults equal the
engine's `memory.py` module constants, so `RetrievalConfig()` reproduces today's
scoring exactly. Making the three **weights** tunable required a small,
backward-compatible engine change (three optional `alpha_*` params on `retrieve()`,
defaulting to the constants).

| Field | Type | Default | Meaning | Status |
|---|---|---|---|---|
| `alpha_recency` | float | `1.0` | Weight on the recency term. | implemented |
| `alpha_importance` | float | `1.0` | Weight on the importance term. | implemented |
| `alpha_relevance` | float | `1.0` | Weight on the relevance (query-similarity) term. | implemented |
| `recency_decay` | float | `0.95` | Exponential decay per turn: `decay ** (turn - last_accessed)`. (Upstream personas use `0.995`; that per-persona knob lands with Phase C/D persona overrides.) | implemented |
| `max_records` | int | `6` | How many top-scored memories may surface. | implemented |
| `token_budget` | int | `800` | Token ceiling for the rendered memory block. | implemented |

The speculative `top_k` / `relevance_method` / `normalize_scores` knobs from the
scaffold are **not** added: `max_records` *is* the top-k, and the relevance method
isn't a string knob — it's chosen by the presence or absence of an embedding client
(below).

### 3.3 `cognition` — perception + conversation (`CognitionConfig`) — **implemented**

Per-resident cognition defaults that used to be bare module constants in
`smallville_agents.py`, gathered into the config now that perception (#80/#82) and
conversation (#86) have landed. Defaults equal those constants, so `CognitionConfig()`
reproduces today's behavior. A persona may still set its own `vision_r` per-entry in
`world_data.yaml`; this section is the global default.

| Field | Type | Default | Meaning | Status |
|---|---|---|---|---|
| `vision_r` | int | `8` | Perception radius in tiles: under a `TiledGame`, residents within this many tiles perceive each other and nearby objects (`SMALLVILLE_VISION_R`). | implemented |
| `conversation_cooldown_steps` | int | `90` | Minimum steps between a given pair's conversations; each one they hold adds another window to their next wait, up to 3 (#803), so repeats space out instead of re-opening the moment the window lapses. `0` disables pair cooldowns (`CONVERSATION_COOLDOWN_STEPS`). | implemented |
| `conversation_max_exchanges` | int | `6` | Max back-and-forth lines per conversation (`CONVERSATION_MAX_EXCHANGES`). | implemented |

These only bite with a real brain — perception widens co-presence, and conversation is
a no-op under the deterministic mock — so the default mock replay stays byte-identical.

### 3.4 `smallville` — Smallville/Phaser run-directory knobs (`SmallvilleConfig`) — **implemented**

**Frontend-specific.** These knobs are read **only** by the Smallville/Phaser runner
(`run_simulation`); they're all `the_ville`-flavored — they name the exported run
directory and select the base sim whose persona memory is copied into it — so they
don't belong in the frontend-agnostic `simulation` section. The UPenn/Godot runners
ignore them entirely (they write a single `penn_replay.json` and load their own cast).
Defaults reproduce today's behavior, so an unconfigured `SmallvilleConfig()` is a no-op.
Mirror `run_simulation`'s `--sim-code` / `--base-sim` flags (an explicit flag still wins).

| Field | Type | Default | Meaning | Status |
|---|---|---|---|---|
| `sim_code` | str | `mock_the_ville_n25` | Names the exported run directory. `--sim-code`. | implemented |
| `base_sim` | str | `base_the_ville_n25` | Persona-memory source copied into the run. `--base-sim`. | implemented |
| `num_agents` | int | `5` | How many residents actually run. The full `n25` roster always loads; the runner slices the first N (matches `build_world.MAX_ACTIVE_PERSONAS`). Raise up to 25 to run more of the town. | implemented |

> **Why no `upenn` section?** The UPenn/Godot runners (`run_upenn`,
> `generate_penn_replay`) don't read `SimulationConfig` yet — they take a `--steps`
> flag and otherwise hardcode their world. Per the "no dead config" rule (§1), a
> `upenn: UPennCampusConfig` section appears only once that runner actually reads one;
> until then there are no UPenn-exclusive config variables to home.

### 3.5 `embedding` — relevance backend (`EmbeddingConfig | None`) — **implemented (reused)**

The embedding backend that scores the *relevance* term. This **reuses the engine's
existing** [`EmbeddingConfig`](../../text_adventure_games/embedding_client.py)
(issue #76) rather than defining a new one. `None` (the default) means
keyword-overlap relevance — the free, offline path.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `provider` | `EmbeddingProvider` \| str | *(required when set)* | `local` (model2vec, offline, ~30 MB; needs `uv sync --extra embeddings`) / `mock` (deterministic, offline) / `sentence-transformers` / `openai`. |
| `model` | str \| None | provider default | Specific model id (e.g. `text-embedding-3-small`). |
| `api_key` | str \| None | env fallback | Key for hosted backends. |
| `base_url` | str \| None | `None` | Proxy/base URL for hosted backends. |

**How embedding is selected (issue #102 seam, reused):** the `--embeddings
[PROVIDER]` flag wins, else the `EMBEDDING_PROVIDER` env var, else a config-file
`embedding:` section, else `None` (keyword overlap). The runner degrades gracefully
to keyword overlap if a chosen backend can't be created (e.g. the extra isn't
installed), so the default run stays free, offline, and CI-safe. The deterministic
mock brain ignores the retrieved block, so the exported replay is **byte-identical**
regardless of the relevance mode — `backend/compare_retrieval.py` shows the diff.

### 3.6 Inherited from `GameConfig` (the `game:` section) — **not re-declared**

These already exist and are documented in [`configuration.md`](../configuration.md);
`SimulationConfig` reuses them through its embedded `game` field. Listed only for
completeness.

| Section | Affects |
|---|---|
| `llm` | LLM connection (`provider`, `model`, `max_*_tokens`, `base_url`) |
| `agent` | NPC decision params (`temperature`, `max_tokens`, `max_retries`, `max_duration`) |
| `engine` | turn loop (`turn_mode` — the port uses `simultaneous`), triggers, hints |
| `clock` | the in-game clock (`start_hour`, `minutes_per_turn`, `periods`) |
| `render` | terminal output (`level`, `width`, `no_color`) |
| `observability` | LLM cost/usage logging (`log_path`, `log_prompts`) |

### 3.7 Deferred sections (land with their phase)

Not in the implemented dataclass — adding fields nothing reads would be dead config.
Kept here as a forward-looking registry.

| Future section | Knobs | Lands with |
|---|---|---|
| `memory` | memory-stream eviction / retention | when stream management lands. *(The reflection-importance threshold already lives on `GameConfig.agent.reflection_threshold` — see §3.6.)* |
| `planning` | daily-plan granularity, replan triggers | only generated by a live planner today (#83); a tuning section lands if/when the mock path needs it |
| `persona` | per-agent cognition *overrides* (`recency_w`, `relevance_w`, `importance_w`, `recency_decay=0.995`, per-agent `vision_r`, …) merged from each `scratch.json` | when per-persona cognition is wired (NEXT-STEPS Phase C/D) |

---

## 4. Precedence

Highest priority to lowest, as implemented in `run_simulation.main()`:

1. **An explicit CLI flag** (`--steps`, `--start`, `--sec-per-step`, `--sim-code`,
   `--base-sim`, `--embeddings`). The run-time flags default to `None`, so a flag
   only overrides the config when actually given.
2. **A value in the `SimulationConfig`** — from `--config <file>` (or its built-in
   defaults). For embedding, also `EMBEDDING_PROVIDER` (which `from_env` folds into
   the config) ranks here, ahead of a config-file `embedding:` section.
3. **The built-in default** (today's value, on `SimulationRuntimeConfig` /
   `RetrievalConfig` / `SmallvilleConfig`).

Per-persona overrides from `scratch.json` (item between 1 and 2 in the original
scaffold) are **future work** — see §3.7.

## 5. Usage

```yaml
# simulation.yaml — every section is optional; omitted fields keep their defaults.
game:                       # the embedded GameConfig (see docs/configuration.md)
  engine: { turn_mode: simultaneous }
  observability: { log_path: runs/ }
simulation:                 # run-time knobs
  steps: 120
  start: "2023-02-13 18:00:00"
retrieval:                  # memory-retrieval scoring
  max_records: 4
  alpha_relevance: 2.0      # favor relevance over recency/importance
smallville:                 # Smallville/Phaser-only run-directory knobs
  sim_code: my_demo_run     # names the exported run directory
  num_agents: 10            # run 10 of the n25 roster instead of the default 5
embedding:                  # optional; omit for keyword-overlap relevance
  provider: mock
```

```bash
# From the generative-agents directory:
uv run python -m backend.run_simulation --config simulation.yaml
# An explicit flag overrides the file:
uv run python -m backend.run_simulation --config simulation.yaml --steps 24
```

In Python / tests:

```python
from backend.sim_config import SimulationConfig, RetrievalConfig
from backend.run_simulation import simulate

sim = SimulationConfig(retrieval=RetrievalConfig(max_records=4, alpha_relevance=2.0))
frames = simulate(world_map, sim.simulation.steps,
                  embedding_client=sim.build_embedding_client(),
                  retrieval=sim.retrieval)
```

## 6. What shipped vs. what's next

**Shipped (this PR):** `SimulationConfig` composing `GameConfig` + `simulation` +
`retrieval` + `embedding`; the minimal `retrieve()` weight-threading in the engine;
`run_simulation` builds the config and threads it through `simulate` →
`observe_and_decide`; `from_file`/`from_dict`/`from_env`/`to_dict` with strict
unknown-key validation; offline tests mirroring `tests/test_config.py`.

**Next:** backfill `memory` (reflection threshold) when periodic reflection lands;
`perception` / `planning` with Phases C/D; per-persona cognition overrides merged
from `scratch.json` (the `persona` section + `recency_decay` 0.95-vs-0.995
reconciliation). Whether the cognition sub-configs eventually graduate into the
engine's `GameConfig` (so non-Smallville sims inherit them) is an open call to make
when a second consumer appears.

## 7. References

- Engine config this mirrors: [`docs/configuration.md`](../configuration.md),
  `text_adventure_games/config.py`.
- Implementation: `backend/sim_config.py`,
  `backend/run_simulation.py`.
- Roadmap & phases: [`generative-agents/NEXT-STEPS.md`](../../generative-agents/NEXT-STEPS.md).
- Memory + retrieval: [`agent-memory.md`](agent-memory.md), `text_adventure_games/memory.py`
  (issues #75, #76).
- Embedding backend: `text_adventure_games/embedding_client.py` (issues #76, #102).
- Per-persona cognition knobs (future): [`generative-agents-port.md`](generative-agents-port.md).
