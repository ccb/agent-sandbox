# promptviz -- prompt-chain / LLM-call-chain visualizer

A small, offline web app that draws the **DAG of LLM call sites an agent run
flows through**, reading the prompts straight from the `.prompty` templates --
no model call required. Click a node to read its prompt; optionally overlay a
recorded mock run to see which paths fired and the real prompts/responses.

```bash
# the bundled Action Castle chain (engine NPCs + LLM-fallback parser)
uv run python -m text_adventure_games.promptviz.app
# -> open http://127.0.0.1:8080

# overlay a free mock run (see "Overlay" below)
uv run python -m text_adventure_games.promptviz.app --runlog run.jsonl

# a different chain / app (e.g. generative-agents, run from that dir)
cd generative-agents
uv run --project .. python -m text_adventure_games.promptviz.app \
  --spec backend/promptviz_chains/smallville.yaml
```

`--host`/`--port` (or the `HOST`/`PORT` env vars) change the address.

## How it works

The app is generic: it's parameterized by a **chain spec** (a YAML file) and the
**prompt-templates package** that spec names. The same engine renders any chain,
so it covers both `text_adventure_games` (real model prompts today) and
`generative-agents` (memory/belief content now; real prompts once it's wired to a
live LLM -- no visualizer change needed, just a `template:` on the node).

- `spec.py` -- `Node`/`Edge`/`ChainSpec` + `load_spec()` + `validate()`.
- `templates.py` -- `node_prompt()` reads a template's frontmatter and raw body
  (`prompty.load`) and renders an example via the package's own `render()`, so the
  preview is byte-identical to what the engine sends. Offline; never calls a model.
- `overlay.py` -- `load_runlog()` + `map_to_chain()` map a `RunLog` JSONL onto the
  chain (fired nodes/edges + real calls).
- `app.py` -- Flask JSON API; the browser draws the graph with Cytoscape + dagre
  (vendored under `webapp/static/vendor/`, so it runs with no internet).

## Chain specs

A chain spec is a **hand-authored teaching diagram**, not auto-derived from code,
so each node names its real call site in `description:` to keep the two honest.
A test (`tests/test_promptviz.py`) asserts every node renders identically to the
engine's `render()`, which catches a renamed or removed template.

```yaml
name: my_chain
description: one-line summary
templates: text_adventure_games.prompt_templates   # dotted module exposing render()
nodes:
  - id: decide
    label: Decide
    kind: decision        # start | decision | parse | narrate | gate
    template: npc_decision # <stem>.prompty; omit for gate/start, or for a not-yet-wired call site
    description: where this call happens in the code
    example_vars: {}      # optional; defaults to the template's own `sample`
edges:
  - { from: decide, to: gate, label: route, condition: optional_machine_tag }
```

`start`/`gate` are control points (no template). `decision`/`parse`/`narrate` are
LLM call sites; a template is optional so you can show a call site whose prompt
isn't wired yet (e.g. the gen-agents mock brain).

## Overlay (optional)

Generate a `RunLog` JSONL from a free mock run with `log_prompts=True`:

```python
import os; os.environ["LLM_PROVIDER"] = "mock"
from text_adventure_games.adventures import action_castle
from text_adventure_games.llm_client import client_from_env
from text_adventure_games.usage import RunLog

with RunLog("run.jsonl", log_prompts=True, provider="mock", model="mock") as rl:
    game = action_castle.build_game(llm_client=client_from_env(run_log=rl))
    for cmd in ["look", "go out", "south"]:
        game.do_command(cmd)
```

Then pass `--runlog run.jsonl`. Fired nodes/edges are highlighted and each node's
panel shows the real calls. Calls are matched to nodes by their system-message
text (needs `log_prompts=True`); `attempt > 0` lights the reflect-and-retry edge.

## Scope / limits

- The DAG is a curated model of the cognitive flow, not an exhaustive trace.
- The Graphviz `dot` binary is **not** required -- dagre lays out in the browser.
- Overlay node-matching is best-effort (content prefix + structural fields).
