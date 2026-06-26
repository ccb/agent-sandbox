"""Flask app for the prompt-chain visualizer.

A thin JSON API over one or more chain specs; the browser (Cytoscape) draws the
DAG and a side panel fetches each node's prompt on click. Everything is read
offline -- no LLM call.

Routes:

* ``GET /``                         -- the single page (loads the Cytoscape app)
* ``GET /chains``                   -- ``[{id, label, description}]`` for the dropdown
* ``GET /graph.json?chain=<id>``    -- Cytoscape elements + overlay metadata
* ``GET /prompt/<chain>/<node_id>`` -- one node's prompt detail (+ actuals when overlaid)
* ``GET /healthz``                  -- ``"ok"``

Run it::

    python -m text_adventure_games.promptviz.app                  # bundled Action Castle chain
    python -m text_adventure_games.promptviz.app --runlog run.jsonl
    python -m text_adventure_games.promptviz.app --spec path/to/smallville.yaml
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

from .overlay import Overlay, load_runlog, map_to_chain
from .spec import ChainSpec, load_spec
from .templates import node_prompt

_CHAINS_DIR = Path(__file__).parent / "chains"


def _graph_elements(spec: ChainSpec, overlay: Overlay | None) -> dict:
    """Build Cytoscape ``elements`` (nodes + edges) for a chain, tagging which
    fired if an overlay is active."""
    fired_nodes = overlay.fired_nodes if overlay else set()
    fired_edges = overlay.fired_edges if overlay else set()

    nodes = [
        {
            "data": {
                "id": n.id,
                "label": n.label,
                "kind": n.kind,
                "template": n.template,
                "description": " ".join((n.description or "").split()),
                "fired": n.id in fired_nodes,
            }
        }
        for n in spec.nodes
    ]
    edges = [
        {
            "data": {
                "id": f"e{i}",
                "source": e.source,
                "target": e.target,
                "label": e.label,
                "condition": e.condition,
                "fired": (e.source, e.target) in fired_edges,
            }
        }
        for i, e in enumerate(spec.edges)
    ]
    return {"nodes": nodes, "edges": edges}


def create_app(chains: list[ChainSpec], runlog_path: str | None = None) -> Flask:
    """Build the Flask app over already-loaded ``chains``.

    If ``runlog_path`` is given, it's parsed once and mapped onto each chain so
    ``/graph.json`` and ``/prompt`` can highlight and annotate the fired paths.
    """
    if not chains:
        raise ValueError("create_app needs at least one chain spec")

    here = Path(__file__).parent / "webapp"
    app = Flask(
        __name__,
        template_folder=str(here / "templates"),
        static_folder=str(here / "static"),
    )

    registry = {c.name: c for c in chains}
    default_chain = chains[0].name

    overlays: dict[str, Overlay] = {}
    if runlog_path:
        runlog = load_runlog(runlog_path)
        for c in chains:
            overlays[c.name] = map_to_chain(runlog, c)

    def _get_chain(chain_id: str) -> ChainSpec:
        spec = registry.get(chain_id)
        if spec is None:
            abort(404, f"unknown chain {chain_id!r}")
        return spec

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            default_chain=default_chain,
            overlay_active=bool(runlog_path),
            runlog_name=Path(runlog_path).name if runlog_path else None,
        )

    @app.route("/chains")
    def chains_list():
        return jsonify(
            [
                {
                    "id": c.name,
                    "label": c.name.replace("_", " ").title(),
                    "description": " ".join((c.description or "").split()),
                }
                for c in chains
            ]
        )

    @app.route("/graph.json")
    def graph_json():
        chain_id = request.args.get("chain", default_chain)
        spec = _get_chain(chain_id)
        ov = overlays.get(chain_id)
        payload = {
            "chain": chain_id,
            "elements": _graph_elements(spec, ov),
            "overlay": {
                "active": ov is not None,
                "provider": ov.provider if ov else None,
                "model": ov.model if ov else None,
                "seed": ov.seed if ov else None,
                "call_count": ov.call_count if ov else 0,
                "note": ov.note if ov else "",
            },
        }
        return jsonify(payload)

    @app.route("/prompt/<chain_id>/<node_id>")
    def prompt(chain_id: str, node_id: str):
        spec = _get_chain(chain_id)
        node = spec.node(node_id)
        if node is None:
            abort(404, f"unknown node {node_id!r} in chain {chain_id!r}")

        detail = {
            "id": node.id,
            "label": node.label,
            "kind": node.kind,
            "template": node.template,
            "description": " ".join((node.description or "").split()),
        }
        if node.template:
            detail.update(
                node_prompt(node.template, node.example_vars, spec.templates_for(node))
            )
        elif node.kind in ("start", "gate"):
            detail["note"] = "Control point -- no prompt (no LLM call here)."
        else:
            detail["note"] = (
                "No prompt template wired yet for this call site "
                "(e.g. a mock brain that ignores prompts)."
            )

        ov = overlays.get(chain_id)
        if ov is not None:
            detail["actual"] = ov.actuals.get(node_id, [])
        return jsonify(detail)

    @app.route("/healthz")
    def healthz():
        return "ok"

    return app


def _collect_specs(args: argparse.Namespace) -> list[ChainSpec]:
    """Resolve chain specs from CLI args.

    The bundled chains/ are always loaded (so an app's own ``--spec`` shows up
    *alongside* Action Castle in the dropdown -- the cross-both case) unless
    ``--no-bundled`` is passed. ``--spec`` / ``--chains-dir`` add to them.
    """
    paths: list[Path] = []
    if not args.no_bundled:
        paths.extend(sorted(_CHAINS_DIR.glob("*.yaml")))
    for s in args.spec or []:
        paths.append(Path(s))
    if args.chains_dir:
        paths.extend(sorted(Path(args.chains_dir).glob("*.yaml")))

    specs, seen = [], set()
    for p in paths:
        spec = load_spec(p)
        if spec.name in seen:
            continue
        seen.add(spec.name)
        specs.append(spec)
    if not specs:
        raise SystemExit("no chain specs found (use --spec or --chains-dir)")
    return specs


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Prompt-chain visualizer for text_adventure_games agents."
    )
    parser.add_argument(
        "--spec",
        action="append",
        help="path to a chain-spec YAML (repeatable); added alongside the bundled chains",
    )
    parser.add_argument("--chains-dir", help="directory of chain-spec YAML files")
    parser.add_argument(
        "--no-bundled",
        action="store_true",
        help="don't load the bundled chains/ (show only --spec / --chains-dir)",
    )
    parser.add_argument(
        "--runlog",
        help="RunLog JSONL from a mock run to overlay (best with log_prompts=True)",
    )
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args(argv)

    specs = _collect_specs(args)
    app = create_app(specs, runlog_path=args.runlog)
    print(
        f"promptviz: serving {len(specs)} chain(s) "
        f"[{', '.join(s.name for s in specs)}] on http://{args.host}:{args.port}"
        + (f"  (overlay: {Path(args.runlog).name})" if args.runlog else "")
    )
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
