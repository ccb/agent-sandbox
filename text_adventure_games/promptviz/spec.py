"""Chain-spec model and loader for the prompt-chain visualizer.

A *chain spec* is a small YAML file that declares the DAG of LLM call sites an
agent run goes through: **nodes** (each usually backed by a ``.prompty``
template) and **edges** (the transitions between them, including loops such as
reflect-and-retry). The spec is hand-authored -- a readable teaching diagram of
the agent's cognitive flow -- and is read entirely offline. Rendering a node's
prompt (see :mod:`text_adventure_games.promptviz.templates`) never calls a model.

See ``promptviz/chains/action_castle.yaml`` for a worked example.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# A node's ``kind`` decides its shape/color in the graph. ``start`` (the turn's
# entry point) and ``gate`` (a non-LLM control point such as the precondition
# check) carry no template. The LLM kinds (decision/parse/narrate) usually name a
# ``.prompty`` template by its stem, but may omit it for a call site whose prompt
# isn't wired yet.
NODE_KINDS = ("start", "decision", "parse", "narrate", "gate")
_TEMPLATELESS_KINDS = ("start", "gate")


@dataclass
class Node:
    """One LLM call site (or control point) in the chain."""

    id: str
    label: str
    kind: str
    description: str = ""
    template: str | None = None
    # Variables passed to ``render(template, **example_vars)`` for the static
    # preview. ``None`` means "fall back to the template's own ``sample``".
    example_vars: dict | None = None
    # Optional per-node override of the chain's ``templates`` package. Lets one
    # chain mix templates from more than one package -- e.g. the Smallville chain
    # shows gen-agents memory templates (``backend.prompt_templates``) alongside
    # the engine cognition it reuses (``text_adventure_games.prompt_templates``).
    templates: str | None = None


@dataclass
class Edge:
    """A directed transition between two nodes."""

    source: str
    target: str
    label: str = ""
    # Optional machine tag the overlay uses to recognize a fired transition
    # (e.g. ``"precondition_failure"`` for the reflect-and-retry back-edge).
    condition: str | None = None


@dataclass
class ChainSpec:
    """A whole chain: its metadata, nodes, and edges."""

    name: str
    description: str
    # Dotted module that exposes ``render(name, /, **vars)`` and holds the
    # ``.prompty`` files, e.g. ``"text_adventure_games.prompt_templates"``.
    templates: str
    nodes: list[Node]
    edges: list[Edge]
    path: Path | None = None

    def node(self, node_id: str) -> Node | None:
        """Return the node with ``node_id``, or ``None`` if there isn't one."""
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def templates_for(self, node: Node) -> str:
        """The templates package to render ``node`` with: its own override if it
        sets one, else the chain's default ``templates``."""
        return node.templates or self.templates

    def validate(self) -> ChainSpec:
        """Check the spec is internally consistent; raise ``ValueError`` if not.

        Enforces unique node ids, a valid ``kind`` on every node, the
        template-presence rule for that kind, and that every edge endpoint
        names a real node. Returns ``self`` so callers can chain the call.
        """
        ids = [n.id for n in self.nodes]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate node ids: {duplicates}")
        known = set(ids)

        for n in self.nodes:
            if n.kind not in NODE_KINDS:
                raise ValueError(
                    f"node {n.id!r}: unknown kind {n.kind!r} "
                    f"(expected one of {list(NODE_KINDS)})"
                )
            # ``start``/``gate`` are control points and must not name a template.
            # The LLM kinds (decision/parse/narrate) usually do, but a template is
            # optional so a chain can show a call site whose prompt isn't wired yet
            # -- e.g. the generative-agents decision currently runs on a mock brain
            # that ignores prompts. Such a node renders with a "not wired" note.
            if n.kind in _TEMPLATELESS_KINDS and n.template:
                raise ValueError(
                    f"node {n.id!r}: kind {n.kind!r} is a control point and "
                    f"must not set a template"
                )

        for e in self.edges:
            if e.source not in known:
                raise ValueError(
                    f"edge {e.source!r} -> {e.target!r}: unknown source {e.source!r}"
                )
            if e.target not in known:
                raise ValueError(
                    f"edge {e.source!r} -> {e.target!r}: unknown target {e.target!r}"
                )
        return self


def load_spec(path: str | Path) -> ChainSpec:
    """Load and validate a chain spec from a YAML file.

    Edges use ``from``/``to`` keys in YAML (which read naturally); they map to
    :class:`Edge`'s ``source``/``target`` here because ``from`` is a Python
    keyword.
    """
    path = Path(path)
    data = yaml.safe_load(path.read_text()) or {}

    for key in ("name", "templates"):
        if not data.get(key):
            raise ValueError(f"{path.name}: missing required top-level key {key!r}")

    nodes = []
    for raw in data.get("nodes", []) or []:
        if "id" not in raw:
            raise ValueError(f"{path.name}: a node is missing its 'id'")
        nodes.append(
            Node(
                id=raw["id"],
                label=raw.get("label", raw["id"]),
                kind=raw.get("kind", "decision"),
                description=raw.get("description", ""),
                template=raw.get("template"),
                example_vars=raw.get("example_vars"),
                templates=raw.get("templates"),
            )
        )

    edges = []
    for raw in data.get("edges", []) or []:
        if "from" not in raw or "to" not in raw:
            raise ValueError(f"{path.name}: an edge is missing 'from' or 'to'")
        edges.append(
            Edge(
                source=raw["from"],
                target=raw["to"],
                label=raw.get("label", ""),
                condition=raw.get("condition"),
            )
        )

    spec = ChainSpec(
        name=data["name"],
        description=data.get("description", ""),
        templates=data["templates"],
        nodes=nodes,
        edges=edges,
        path=path,
    )
    return spec.validate()
