# Static prompt-chain data

The Penn showcase includes an interactive diagram of the simulation's cognition
pipeline. This package supplies the Python-side build primitives:

- `spec.py` loads and validates a YAML chain specification;
- `templates.py` reads the referenced `.prompty` files and renders examples;
- `graph.py` serializes the chain to Cytoscape-compatible nodes and edges.

The public chain is
`godot-generative-agents/backend/promptviz_chains/cognition.yaml`. Regenerate
the browser data from the repository root with:

```bash
cd godot-generative-agents/web
pnpm gen:promptviz
```

This is an offline build step. It does not call a model or start a Python web
server.
