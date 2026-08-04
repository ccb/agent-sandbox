"""Serialize a prompt-chain specification for the static web visualizer."""

from __future__ import annotations

from .spec import ChainSpec


def graph_elements(spec: ChainSpec) -> dict:
    """Return Cytoscape-compatible nodes and edges for ``spec``.

    The public showcase precomputes this data during its build. Runtime overlays
    and the former Flask application are intentionally outside the public
    package.
    """
    nodes = [
        {
            "data": {
                "id": node.id,
                "label": node.label,
                "kind": node.kind,
                "template": node.template,
                "description": " ".join((node.description or "").split()),
                "fired": False,
            }
        }
        for node in spec.nodes
    ]
    edges = [
        {
            "data": {
                "id": f"e{index}",
                "source": edge.source,
                "target": edge.target,
                "label": edge.label,
                "condition": edge.condition,
                "fired": False,
            }
        }
        for index, edge in enumerate(spec.edges)
    ]
    return {"nodes": nodes, "edges": edges}
